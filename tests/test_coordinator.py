"""Tests for the MarineTrafficCoordinator — vessel filtering and hard floor enforcement."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.marinetraffic_tracker.client import VesselData
from custom_components.marinetraffic_tracker.const import (
    CONF_FILTER_VESSEL_TYPES,
    CONF_STALE_TIMEOUT,
    CONF_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
)
from custom_components.marinetraffic_tracker.coordinator import MarineTrafficCoordinator

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

_CARGO_VESSEL = VesselData(
    mmsi="123456789",
    name="EVER GIVEN",
    vessel_type=70,  # Cargo
    latitude=29.98,
    longitude=32.55,
    heading=180,
    course=182,
    speed=12.5,
    status="Under Way Using Engine",
    origin="SUEZ",
    destination="ROTTERDAM",
    eta="2026-05-15 14:00",
    last_seen=datetime.now(timezone.utc),
)

_TANKER_VESSEL = VesselData(
    mmsi="987654321",
    name="SEA TITAN",
    vessel_type=80,  # Tanker
    latitude=30.01,
    longitude=32.60,
    heading=90,
    course=91,
    speed=8.0,
    status="At Anchor",
    origin="JEDDAH",
    destination=None,
    eta=None,
    last_seen=datetime.now(timezone.utc),
)


def _make_entry(options: dict | None = None, data: dict | None = None) -> MagicMock:
    """Return a fake ConfigEntry-like mock with controllable data/options."""
    entry = MagicMock()
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
) -> MarineTrafficCoordinator:
    """Build a coordinator with optional vessel type filter and update interval."""
    options: dict = {}
    if filter_types is not None:
        # Selector stores values as strings
        options[CONF_FILTER_VESSEL_TYPES] = [str(t) for t in filter_types]
    if update_interval != 60:
        options[CONF_UPDATE_INTERVAL] = update_interval

    entry = _make_entry(options=options)
    return MarineTrafficCoordinator(hass, entry, client)


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
    hass.bus = MagicMock()
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
    hass.bus = MagicMock()
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
    hass.bus = MagicMock()
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
    """Filter values stored as strings (from SelectSelector) must work correctly."""
    hass = MagicMock()
    hass.bus = MagicMock()
    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[_CARGO_VESSEL])

    # Simulate SelectSelector storage: list of strings
    entry = _make_entry(options={CONF_FILTER_VESSEL_TYPES: ["70"]})
    coordinator = MarineTrafficCoordinator(hass, entry, client)
    result = await coordinator._async_update_data()

    assert "123456789" in result


@pytest.mark.asyncio
async def test_vessel_with_none_destination_does_not_raise() -> None:
    """Vessels with None destination/ETA must not cause exceptions."""
    hass = MagicMock()
    hass.bus = MagicMock()
    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[_TANKER_VESSEL])

    coordinator = _make_coordinator(hass, client)
    # Should not raise
    result = await coordinator._async_update_data()

    assert result["987654321"].destination is None
    assert result["987654321"].eta is None
