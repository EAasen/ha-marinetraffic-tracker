"""Tests for anchored vessel optimization and exclude_anchored toggle."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.marinetraffic_tracker.const import (
    ANCHOR_SWING_THRESHOLD_KM,
    ANCHORED_STATUSES,
    CONF_EXCLUDE_ANCHORED,
    CONF_FILTER_VESSEL_TYPES,
    CONF_STALE_TIMEOUT,
    CONF_UPDATE_INTERVAL,
    DEFAULT_EXCLUDE_ANCHORED,
    DEFAULT_STALE_TIMEOUT,
)
from custom_components.marinetraffic_tracker.coordinator import MarineTrafficCoordinator

from .conftest import MOCK_VESSEL_CARGO, MOCK_VESSEL_PASSENGER, MOCK_VESSEL_TANKER

# MOCK_VESSEL_TANKER (mmsi=987654321) has status "At Anchor" — verified in conftest.py.
# MOCK_VESSEL_PASSENGER (mmsi=555555555) has status "Moored" — verified in conftest.py.
# MOCK_VESSEL_CARGO (mmsi=123456789) has status "Under Way Using Engine" — verified in conftest.py.
_ACTIVE_VESSEL = MOCK_VESSEL_CARGO  # status "Under Way Using Engine"
_ANCHORED_VESSEL = MOCK_VESSEL_TANKER  # status "At Anchor"
_MOORED_VESSEL = MOCK_VESSEL_PASSENGER  # status "Moored"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(options: dict | None = None, data: dict | None = None) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "test_entry_anchored"
    entry.data = data or {
        CONF_UPDATE_INTERVAL: 60,
        CONF_STALE_TIMEOUT: DEFAULT_STALE_TIMEOUT,
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
    exclude_anchored: bool = False,
    stale_timeout: int = DEFAULT_STALE_TIMEOUT,
) -> MarineTrafficCoordinator:
    options: dict = {CONF_EXCLUDE_ANCHORED: exclude_anchored}
    entry = _make_entry(options=options)
    entry.data[CONF_STALE_TIMEOUT] = stale_timeout
    return MarineTrafficCoordinator(hass, entry, client)


# ---------------------------------------------------------------------------
# ANCHORED_STATUSES constant tests
# ---------------------------------------------------------------------------


def test_anchored_statuses_contains_at_anchor() -> None:
    """ANCHORED_STATUSES must include 'At Anchor'."""
    assert "At Anchor" in ANCHORED_STATUSES


def test_anchored_statuses_contains_moored() -> None:
    """ANCHORED_STATUSES must include 'Moored'."""
    assert "Moored" in ANCHORED_STATUSES


def test_anchor_swing_threshold_is_positive() -> None:
    """ANCHOR_SWING_THRESHOLD_KM must be a positive value."""
    assert ANCHOR_SWING_THRESHOLD_KM > 0


def test_default_exclude_anchored_is_false() -> None:
    """DEFAULT_EXCLUDE_ANCHORED must default to False (opt-in feature)."""
    assert DEFAULT_EXCLUDE_ANCHORED is False


# ---------------------------------------------------------------------------
# Exclude anchored toggle: off (default behaviour)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anchored_vessel_included_when_toggle_off() -> None:
    """With exclude_anchored=False, anchored vessels appear in coordinator.data."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()
    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(
        return_value=[_ACTIVE_VESSEL, _ANCHORED_VESSEL]
    )

    coordinator = _make_coordinator(hass, client, exclude_anchored=False)
    result = await coordinator._async_update_data()

    assert _ACTIVE_VESSEL.mmsi in result
    assert _ANCHORED_VESSEL.mmsi in result
    assert len(coordinator._anchored_vessels) == 0


# ---------------------------------------------------------------------------
# Exclude anchored toggle: on
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anchored_vessel_excluded_from_data_when_toggle_on() -> None:
    """With exclude_anchored=True, anchored vessels must NOT appear in coordinator.data."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()
    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[_ACTIVE_VESSEL, _ANCHORED_VESSEL])

    coordinator = _make_coordinator(hass, client, exclude_anchored=True)
    result = await coordinator._async_update_data()

    assert _ACTIVE_VESSEL.mmsi in result, "Active vessel must remain in coordinator.data"
    assert _ANCHORED_VESSEL.mmsi not in result, "Anchored vessel must be excluded from data"


@pytest.mark.asyncio
async def test_anchored_vessel_stored_in_anchored_dict_when_toggle_on() -> None:
    """With exclude_anchored=True, anchored vessels must be in _anchored_vessels."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()
    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[_ANCHORED_VESSEL])

    coordinator = _make_coordinator(hass, client, exclude_anchored=True)
    await coordinator._async_update_data()

    assert _ANCHORED_VESSEL.mmsi in coordinator._anchored_vessels
    assert _ANCHORED_VESSEL.mmsi not in coordinator._vessels


@pytest.mark.asyncio
async def test_moored_vessel_excluded_when_toggle_on() -> None:
    """Moored vessels must also be excluded when exclude_anchored=True."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()
    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[_MOORED_VESSEL])

    coordinator = _make_coordinator(hass, client, exclude_anchored=True)
    result = await coordinator._async_update_data()

    assert _MOORED_VESSEL.mmsi not in result
    assert _MOORED_VESSEL.mmsi in coordinator._anchored_vessels


@pytest.mark.asyncio
async def test_anchored_vessels_property_returns_anchored_dict() -> None:
    """anchored_vessels property must expose the _anchored_vessels dict contents."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()
    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[_ANCHORED_VESSEL])

    coordinator = _make_coordinator(hass, client, exclude_anchored=True)
    await coordinator._async_update_data()

    anchored = coordinator.anchored_vessels
    assert _ANCHORED_VESSEL.mmsi in anchored


@pytest.mark.asyncio
async def test_anchored_vessels_property_empty_when_toggle_off() -> None:
    """anchored_vessels property must be empty when exclude_anchored=False."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()
    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[_ANCHORED_VESSEL])

    coordinator = _make_coordinator(hass, client, exclude_anchored=False)
    await coordinator._async_update_data()

    assert coordinator.anchored_vessels == {}


@pytest.mark.asyncio
async def test_vessel_transitions_from_active_to_anchored() -> None:
    """A vessel that becomes anchored must move from _vessels to _anchored_vessels."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()
    client = AsyncMock()

    # Start: vessel is active (under way)
    client.get_vessels_in_radius = AsyncMock(return_value=[_ACTIVE_VESSEL])
    coordinator = _make_coordinator(hass, client, exclude_anchored=True)
    await coordinator._async_update_data()

    assert _ACTIVE_VESSEL.mmsi in coordinator._vessels

    # Vessel drops anchor
    now_anchored = replace(_ACTIVE_VESSEL, status="At Anchor")
    client.get_vessels_in_radius = AsyncMock(return_value=[now_anchored])
    await coordinator._async_update_data()

    assert _ACTIVE_VESSEL.mmsi not in coordinator._vessels, (
        "Vessel must leave _vessels after anchoring"
    )
    assert _ACTIVE_VESSEL.mmsi in coordinator._anchored_vessels, (
        "Vessel must appear in _anchored_vessels after anchoring"
    )


@pytest.mark.asyncio
async def test_vessel_transitions_from_anchored_to_active() -> None:
    """A previously anchored vessel that gets underway must move back to _vessels."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()
    client = AsyncMock()

    # Start: vessel is anchored
    client.get_vessels_in_radius = AsyncMock(return_value=[_ANCHORED_VESSEL])
    coordinator = _make_coordinator(hass, client, exclude_anchored=True)
    await coordinator._async_update_data()

    assert _ANCHORED_VESSEL.mmsi in coordinator._anchored_vessels

    # Vessel gets under way
    now_active = replace(_ANCHORED_VESSEL, status="Under Way Using Engine", speed=10.0)
    client.get_vessels_in_radius = AsyncMock(return_value=[now_active])
    await coordinator._async_update_data()

    assert _ANCHORED_VESSEL.mmsi in coordinator._vessels, (
        "Vessel must return to _vessels when it leaves anchor"
    )
    assert _ANCHORED_VESSEL.mmsi not in coordinator._anchored_vessels, (
        "Vessel must leave _anchored_vessels when under way"
    )


# ---------------------------------------------------------------------------
# Stale purging for anchored vessels
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_anchored_vessel_is_purged() -> None:
    """An anchored vessel not seen within stale_timeout must be purged."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()
    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[_ANCHORED_VESSEL])

    coordinator = _make_coordinator(hass, client, exclude_anchored=True, stale_timeout=600)
    await coordinator._async_update_data()

    # Backdate so anchored vessel becomes stale
    mmsi = _ANCHORED_VESSEL.mmsi
    stale_ts = datetime.now(UTC) - timedelta(seconds=700)
    coordinator._anchored_vessels[mmsi] = replace(
        coordinator._anchored_vessels[mmsi], last_seen=stale_ts
    )
    client.get_vessels_in_radius = AsyncMock(return_value=[])
    await coordinator._async_update_data()

    assert mmsi not in coordinator._anchored_vessels


@pytest.mark.asyncio
async def test_stale_anchored_vessel_fires_exited_event() -> None:
    """A purged anchored vessel must fire the vessel_exited event."""
    hass = MagicMock()
    fired_events: list[dict] = []

    def capture_event(event_type: str, data: dict) -> None:
        fired_events.append({"event_type": event_type, "data": data})

    hass.bus = MagicMock()
    hass.bus.async_fire = capture_event

    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[_ANCHORED_VESSEL])

    coordinator = _make_coordinator(hass, client, exclude_anchored=True, stale_timeout=600)
    await coordinator._async_update_data()

    mmsi = _ANCHORED_VESSEL.mmsi
    stale_ts = datetime.now(UTC) - timedelta(seconds=700)
    coordinator._anchored_vessels[mmsi] = replace(
        coordinator._anchored_vessels[mmsi], last_seen=stale_ts
    )
    client.get_vessels_in_radius = AsyncMock(return_value=[])
    await coordinator._async_update_data()

    exited = [e for e in fired_events if e["event_type"] == "marinetraffic_vessel_exited"]
    assert len(exited) == 1
    assert exited[0]["data"]["mmsi"] == _ANCHORED_VESSEL.mmsi


# ---------------------------------------------------------------------------
# Position history optimisation for anchored vessels
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anchored_vessel_first_observation_always_recorded() -> None:
    """The first position history entry for an anchored vessel must always be stored."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()
    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[_ANCHORED_VESSEL])

    coordinator = _make_coordinator(hass, client)
    await coordinator._async_update_data()

    history = coordinator.get_position_history(_ANCHORED_VESSEL.mmsi)
    assert len(history) == 1


@pytest.mark.asyncio
async def test_anchored_vessel_no_movement_skips_history() -> None:
    """Repeated polls with an anchored vessel at the same position must not
    grow the position history beyond the first entry."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()
    client = AsyncMock()
    # Same position every poll — no movement.
    client.get_vessels_in_radius = AsyncMock(return_value=[_ANCHORED_VESSEL])

    coordinator = _make_coordinator(hass, client)
    for _ in range(5):
        await coordinator._async_update_data()

    history = coordinator.get_position_history(_ANCHORED_VESSEL.mmsi)
    assert len(history) == 1, (
        "Position history must not grow when anchored vessel hasn't moved"
    )


@pytest.mark.asyncio
async def test_anchored_vessel_large_movement_records_new_entry() -> None:
    """An anchored vessel that drifts beyond the threshold must get a new history entry."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()
    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[_ANCHORED_VESSEL])

    coordinator = _make_coordinator(hass, client)
    await coordinator._async_update_data()

    # Move the vessel well beyond ANCHOR_SWING_THRESHOLD_KM (0.1 km = 100 m).
    # A 0.5 degree latitude shift ≈ 55 km — clearly beyond the threshold.
    moved_vessel = replace(
        _ANCHORED_VESSEL,
        latitude=_ANCHORED_VESSEL.latitude + 0.5,
    )
    client.get_vessels_in_radius = AsyncMock(return_value=[moved_vessel])
    await coordinator._async_update_data()

    history = coordinator.get_position_history(_ANCHORED_VESSEL.mmsi)
    assert len(history) == 2, (
        "A new position history entry must be recorded when anchored vessel moves "
        "beyond the swing threshold"
    )


@pytest.mark.asyncio
async def test_active_vessel_always_records_position_history() -> None:
    """Active (non-anchored) vessels must record position history on every poll."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()
    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[_ACTIVE_VESSEL])

    coordinator = _make_coordinator(hass, client)
    for _ in range(4):
        await coordinator._async_update_data()

    history = coordinator.get_position_history(_ACTIVE_VESSEL.mmsi)
    assert len(history) == 4, (
        "Active vessel must have a history entry for every poll cycle"
    )


# ---------------------------------------------------------------------------
# Anchored vessel entered/exited events still fire
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anchored_vessel_fires_entered_event() -> None:
    """A newly-seen anchored vessel must still fire a vessel_entered event."""
    hass = MagicMock()
    fired_events: list[dict] = []

    def capture_event(event_type: str, data: dict) -> None:
        fired_events.append({"event_type": event_type, "data": data})

    hass.bus = MagicMock()
    hass.bus.async_fire = capture_event

    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[])

    coordinator = _make_coordinator(hass, client, exclude_anchored=True)
    await coordinator._async_update_data()

    client.get_vessels_in_radius = AsyncMock(return_value=[_ANCHORED_VESSEL])
    await coordinator._async_update_data()

    entered = [e for e in fired_events if e["event_type"] == "marinetraffic_vessel_entered"]
    assert len(entered) == 1
    assert entered[0]["data"]["mmsi"] == _ANCHORED_VESSEL.mmsi
