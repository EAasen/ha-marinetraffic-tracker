"""Tests for MarineTrafficCoordinator — vessel filtering, hard floor, and event firing."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.marinetraffic_tracker.client import VesselData
from custom_components.marinetraffic_tracker.const import (
    CONF_FILTER_VESSEL_TYPES,
    CONF_STALE_TIMEOUT,
    CONF_UPDATE_INTERVAL,
    DEFAULT_STALE_TIMEOUT,
    DEFAULT_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
)
from custom_components.marinetraffic_tracker.coordinator import MarineTrafficCoordinator

from .conftest import MOCK_VESSEL_CARGO, MOCK_VESSEL_TANKER

# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------

_CARGO_VESSEL = MOCK_VESSEL_CARGO
_TANKER_VESSEL = MOCK_VESSEL_TANKER


def _make_entry(options: dict | None = None, data: dict | None = None) -> MagicMock:
    """Return a fake ConfigEntry-like mock with controllable data/options."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = data or {
        CONF_UPDATE_INTERVAL: 60,
        CONF_STALE_TIMEOUT: 600,
        "tracking_mode": "radius",
        "latitude": 59.9,
        "longitude": 10.7,
        "radius_km": 50.0,
    }
    entry.options = options or {}
    return entry


def _make_coordinator(
    hass: MagicMock,
    client: AsyncMock,
    *,
    filter_types: list[int] | None = None,
    update_interval: int = 60,
    stale_timeout: int = DEFAULT_STALE_TIMEOUT,
) -> MarineTrafficCoordinator:
    """Build a coordinator with optional vessel type filter and update interval."""
    options: dict = {}
    if filter_types is not None:
        # cv.multi_select stores values as strings; mirror that here.
        options[CONF_FILTER_VESSEL_TYPES] = [str(t) for t in filter_types]
    if update_interval != 60:
        options[CONF_UPDATE_INTERVAL] = update_interval

    entry = _make_entry(options=options)
    entry.data[CONF_STALE_TIMEOUT] = stale_timeout
    return MarineTrafficCoordinator(hass, entry, client)


async def _refresh(coordinator: MarineTrafficCoordinator) -> None:
    """Refresh coordinator with jitter disabled for deterministic tests."""
    with patch("custom_components.marinetraffic_tracker.coordinator.asyncio.sleep"):
        await coordinator.async_refresh()


# ---------------------------------------------------------------------------
# Hard floor tests
# ---------------------------------------------------------------------------

def test_hard_floor_clamped() -> None:
    """An interval below MIN_UPDATE_INTERVAL must be silently clamped to the floor."""
    raw = 5
    enforced = max(raw, MIN_UPDATE_INTERVAL)
    assert enforced == MIN_UPDATE_INTERVAL, (
        f"Hard floor must clamp any interval below {MIN_UPDATE_INTERVAL}s"
    )


def test_hard_floor_value_is_30() -> None:
    """MIN_UPDATE_INTERVAL must equal 30 seconds."""
    assert MIN_UPDATE_INTERVAL == 30


def test_coordinator_enforces_hard_floor() -> None:
    """Coordinator __init__ must use MIN_UPDATE_INTERVAL when entry has a lower value."""
    hass = MagicMock()
    client = AsyncMock()
    entry = _make_entry(data={
        CONF_UPDATE_INTERVAL: 5,  # below floor
        CONF_STALE_TIMEOUT: 600,
        "tracking_mode": "radius",
        "latitude": 59.9,
        "longitude": 10.7,
        "radius_km": 50.0,
    })
    coordinator = MarineTrafficCoordinator(hass, entry, client)
    assert coordinator.update_interval.total_seconds() == MIN_UPDATE_INTERVAL


def test_coordinator_respects_valid_interval() -> None:
    """Coordinator must use the configured interval when it is >= MIN_UPDATE_INTERVAL."""
    hass = MagicMock()
    client = AsyncMock()
    entry = _make_entry(data={
        CONF_UPDATE_INTERVAL: 120,
        CONF_STALE_TIMEOUT: 600,
        "tracking_mode": "radius",
        "latitude": 59.9,
        "longitude": 10.7,
        "radius_km": 50.0,
    })
    coordinator = MarineTrafficCoordinator(hass, entry, client)
    assert coordinator.update_interval.total_seconds() == 120


# ---------------------------------------------------------------------------
# Vessel type filter tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_filter_excludes_non_matching_types() -> None:
    """Only vessels whose type is in the filter list should appear in coordinator.data."""
    hass = MagicMock()
    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(
        return_value=[_CARGO_VESSEL, _TANKER_VESSEL]
    )

    coordinator = _make_coordinator(hass, client, filter_types=[80])  # Tankers only
    result = await coordinator._async_update_data()

    assert "987654321" in result, "Tanker should be included"
    assert "123456789" not in result, "Cargo should be excluded"


@pytest.mark.asyncio
async def test_empty_filter_includes_all_vessels() -> None:
    """An empty filter list must include all vessel types."""
    hass = MagicMock()
    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(
        return_value=[_CARGO_VESSEL, _TANKER_VESSEL]
    )

    coordinator = _make_coordinator(hass, client, filter_types=[])
    result = await coordinator._async_update_data()

    assert "123456789" in result
    assert "987654321" in result


@pytest.mark.asyncio
async def test_filter_includes_multiple_types() -> None:
    """Multiple types in the filter must each be included."""
    hass = MagicMock()
    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(
        return_value=[_CARGO_VESSEL, _TANKER_VESSEL]
    )

    coordinator = _make_coordinator(hass, client, filter_types=[70, 80])
    result = await coordinator._async_update_data()

    assert "123456789" in result
    assert "987654321" in result


@pytest.mark.asyncio
async def test_filter_with_string_values() -> None:
    """Filter values stored as strings (from cv.multi_select) must work correctly."""
    hass = MagicMock()
    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[_CARGO_VESSEL])

    # Simulate cv.multi_select storage: list of strings
    entry = _make_entry(options={CONF_FILTER_VESSEL_TYPES: ["70"]})
    coordinator = MarineTrafficCoordinator(hass, entry, client)
    result = await coordinator._async_update_data()

    assert "123456789" in result


@pytest.mark.asyncio
async def test_vessel_with_none_destination_does_not_raise() -> None:
    """Vessels with None destination/ETA must not cause exceptions."""
    hass = MagicMock()
    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[_TANKER_VESSEL])

    coordinator = _make_coordinator(hass, client)
    # Should not raise
    result = await coordinator._async_update_data()

    assert result["987654321"].destination is None
    assert result["987654321"].eta is None


# ---------------------------------------------------------------------------
# Entry/exit event tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_vessel_appears_fires_entered_event() -> None:
    """A newly appearing vessel must fire exactly one entered event."""
    hass = MagicMock()
    fired_events: list[dict] = []

    def capture_event(event_type: str, data: dict) -> None:
        fired_events.append({"event_type": event_type, "data": data})

    hass.bus = MagicMock()
    hass.bus.async_fire = capture_event

    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[])

    coordinator = _make_coordinator(hass, client)
    await coordinator._async_update_data()

    # Vessel appears
    client.get_vessels_in_radius = AsyncMock(return_value=[_CARGO_VESSEL])
    await coordinator._async_update_data()

    entered = [e for e in fired_events if e["event_type"] == "marinetraffic_vessel_entered"]
    assert len(entered) == 1
    assert entered[0]["data"]["mmsi"] == _CARGO_VESSEL.mmsi
    assert entered[0]["data"]["name"] == _CARGO_VESSEL.name
    assert entered[0]["data"]["vessel_type"] == _CARGO_VESSEL.vessel_type


@pytest.mark.asyncio
async def test_vessel_exits_fires_exited_event() -> None:
    """A vessel aging past the stale timeout must fire exactly one exited event."""
    hass = MagicMock()
    fired_events: list[dict] = []

    def capture_event(event_type: str, data: dict) -> None:
        fired_events.append({"event_type": event_type, "data": data})

    hass.bus = MagicMock()
    hass.bus.async_fire = capture_event

    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[_CARGO_VESSEL])

    coordinator = _make_coordinator(hass, client, stale_timeout=600)
    await coordinator._async_update_data()

    # Vessel disappears and becomes stale
    client.get_vessels_in_radius = AsyncMock(return_value=[])
    coordinator._vessels[_CARGO_VESSEL.mmsi].last_seen = (
        datetime.now(timezone.utc) - timedelta(seconds=700)
    )
    await coordinator._async_update_data()

    exited = [e for e in fired_events if e["event_type"] == "marinetraffic_vessel_exited"]
    assert len(exited) == 1
    assert exited[0]["data"]["mmsi"] == _CARGO_VESSEL.mmsi


@pytest.mark.asyncio
async def test_repeated_refreshes_do_not_refire_entered() -> None:
    """Subsequent polls with the same vessel must not fire duplicate entered events."""
    hass = MagicMock()
    fired_events: list[dict] = []

    def capture_event(event_type: str, data: dict) -> None:
        fired_events.append({"event_type": event_type, "data": data})

    hass.bus = MagicMock()
    hass.bus.async_fire = capture_event

    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[_CARGO_VESSEL])

    coordinator = _make_coordinator(hass, client)
    # First refresh: vessel enters
    await coordinator._async_update_data()
    entered_before = len([e for e in fired_events if e["event_type"] == "marinetraffic_vessel_entered"])

    # Three more refreshes: same vessel, no new entered events
    for _ in range(3):
        await coordinator._async_update_data()

    entered_after = len([e for e in fired_events if e["event_type"] == "marinetraffic_vessel_entered"])
    assert entered_after == entered_before, "No entered event should fire for an already-tracked vessel"
