"""Mocked tests for the MarineTraffic Tracker coordinator.

All tests are fully mocked — no real MarineTraffic network traffic is made.

Test matrix:
1.  Vessel appears and is tracked.
2.  Ghost ship is purged after stale timeout.
3.  Empty response ultimately drops tracked count to zero.
4.  403 Forbidden is handled gracefully as UpdateFailed.
5.  429 Too Many Requests is handled gracefully as UpdateFailed.
6.  Entered event is fired once.
7.  Exited event is fired once.
8.  Vessel type filter excludes non-matching vessels.
9.  Optional fields with None do not break updates.
10. Update interval below 30 is clamped.
11. Repeated refreshes with same vessel do not duplicate entered events.
12. Invalid/missing MMSI yields no entity_picture.
13. Per-vessel entities are disabled by default; aggregate remains enabled.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.marinetraffic_tracker.const import (
    EVENT_VESSEL_ENTERED,
    EVENT_VESSEL_EXITED,
    MIN_UPDATE_INTERVAL,
    vessel_photo_url,
)
from custom_components.marinetraffic_tracker.coordinator import MarineTrafficCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed

from .conftest import (
    make_config_entry,
    make_coordinator,
    make_vessel,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def run_update(coordinator: MarineTrafficCoordinator) -> dict:
    """Run a single coordinator update with jitter disabled."""
    with patch("asyncio.sleep", return_value=None):
        return await coordinator._async_update_data()


# ---------------------------------------------------------------------------
# Test 1: vessel appears and is tracked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vessel_appears_and_is_tracked(mock_hass, mock_client):
    """A vessel returned by the client should appear in coordinator.data."""
    cargo = make_vessel(mmsi="123456789", vessel_type=70)
    mock_client.get_vessels_in_radius = AsyncMock(return_value=[cargo])

    entry = make_config_entry()
    coordinator = make_coordinator(mock_hass, mock_client, entry)

    result = await run_update(coordinator)

    assert "123456789" in result
    assert result["123456789"].name == cargo.name


# ---------------------------------------------------------------------------
# Test 2: ghost ship is purged after stale timeout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ghost_ship_purged_after_stale_timeout(mock_hass, mock_client):
    """A vessel not seen within stale_timeout should be removed."""
    cargo = make_vessel(mmsi="123456789")
    # First update: vessel appears
    mock_client.get_vessels_in_radius = AsyncMock(return_value=[cargo])
    entry = make_config_entry(stale_timeout=60)
    coordinator = make_coordinator(mock_hass, mock_client, entry)

    await run_update(coordinator)
    assert "123456789" in coordinator._vessels

    # Backdate last_seen so the vessel is beyond the stale threshold
    coordinator._vessels["123456789"].last_seen = datetime.now(timezone.utc) - timedelta(
        seconds=120
    )

    # Second update: empty response — stale vessel should be purged
    mock_client.get_vessels_in_radius = AsyncMock(return_value=[])
    result = await run_update(coordinator)

    assert "123456789" not in result
    assert "123456789" not in coordinator._vessels


# ---------------------------------------------------------------------------
# Test 3: empty response drops tracked count to zero
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_response_drops_count_to_zero(mock_hass, mock_client):
    """After a vessel leaves and enough time passes, tracked count reaches 0."""
    cargo = make_vessel(mmsi="111111111")
    mock_client.get_vessels_in_radius = AsyncMock(return_value=[cargo])
    entry = make_config_entry(stale_timeout=30)
    coordinator = make_coordinator(mock_hass, mock_client, entry)

    await run_update(coordinator)
    assert len(coordinator._vessels) == 1

    # Backdate last_seen and poll with empty response
    coordinator._vessels["111111111"].last_seen = datetime.now(timezone.utc) - timedelta(seconds=60)
    mock_client.get_vessels_in_radius = AsyncMock(return_value=[])
    result = await run_update(coordinator)

    assert len(result) == 0


# ---------------------------------------------------------------------------
# Test 4: 403 Forbidden is handled gracefully as UpdateFailed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_403_raises_update_failed(mock_hass, mock_client):
    """A 403 error from the client should raise UpdateFailed."""
    mock_client.get_vessels_in_radius = AsyncMock(side_effect=Exception("HTTP 403 Forbidden"))
    entry = make_config_entry()
    coordinator = make_coordinator(mock_hass, mock_client, entry)

    with pytest.raises(UpdateFailed):
        await run_update(coordinator)


# ---------------------------------------------------------------------------
# Test 5: 429 Too Many Requests is handled gracefully as UpdateFailed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_429_raises_update_failed(mock_hass, mock_client):
    """A 429 error from the client should raise UpdateFailed."""
    mock_client.get_vessels_in_radius = AsyncMock(
        side_effect=Exception("HTTP 429 Too Many Requests")
    )
    entry = make_config_entry()
    coordinator = make_coordinator(mock_hass, mock_client, entry)

    with pytest.raises(UpdateFailed):
        await run_update(coordinator)


# ---------------------------------------------------------------------------
# Test 6: entered event is fired once
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_entered_event_fired_once(mock_hass, mock_client):
    """The entered event should fire exactly once when a new vessel appears."""
    cargo = make_vessel(mmsi="123456789")
    mock_client.get_vessels_in_radius = AsyncMock(return_value=[cargo])
    entry = make_config_entry()
    coordinator = make_coordinator(mock_hass, mock_client, entry)

    await run_update(coordinator)

    fired_events = [
        c for c in mock_hass.bus.async_fire.call_args_list if c[0][0] == EVENT_VESSEL_ENTERED
    ]
    assert len(fired_events) == 1
    payload = fired_events[0][0][1]
    assert payload["mmsi"] == "123456789"


# ---------------------------------------------------------------------------
# Test 7: exited event is fired once
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exited_event_fired_once(mock_hass, mock_client):
    """The exited event should fire exactly once when a vessel leaves the area."""
    cargo = make_vessel(mmsi="123456789")
    mock_client.get_vessels_in_radius = AsyncMock(return_value=[cargo])
    entry = make_config_entry(stale_timeout=30)
    coordinator = make_coordinator(mock_hass, mock_client, entry)

    # First update: vessel enters
    await run_update(coordinator)
    mock_hass.bus.async_fire.reset_mock()

    # Backdate and poll with empty response: vessel should exit
    coordinator._vessels["123456789"].last_seen = datetime.now(timezone.utc) - timedelta(seconds=60)
    mock_client.get_vessels_in_radius = AsyncMock(return_value=[])
    await run_update(coordinator)

    fired_events = [
        c for c in mock_hass.bus.async_fire.call_args_list if c[0][0] == EVENT_VESSEL_EXITED
    ]
    assert len(fired_events) == 1
    payload = fired_events[0][0][1]
    assert payload["mmsi"] == "123456789"


# ---------------------------------------------------------------------------
# Test 8: vessel type filter excludes non-matching vessels
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vessel_type_filter_excludes_non_matching(mock_hass, mock_client):
    """Only vessel types in the filter list should appear in coordinator.data."""
    cargo = make_vessel(mmsi="111111111", vessel_type=70)  # Cargo
    tanker = make_vessel(mmsi="222222222", vessel_type=80)  # Tanker

    mock_client.get_vessels_in_radius = AsyncMock(return_value=[cargo, tanker])
    # Filter to cargo only
    entry = make_config_entry(filter_vessel_types=[70])
    coordinator = make_coordinator(mock_hass, mock_client, entry)

    result = await run_update(coordinator)

    assert "111111111" in result  # cargo passes
    assert "222222222" not in result  # tanker excluded


# ---------------------------------------------------------------------------
# Test 9: optional fields with None do not break updates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optional_none_fields_do_not_raise(mock_hass, mock_client):
    """A vessel with None destination and eta should not break the update."""
    vessel = make_vessel(mmsi="333333333", destination=None, eta=None)
    mock_client.get_vessels_in_radius = AsyncMock(return_value=[vessel])
    entry = make_config_entry()
    coordinator = make_coordinator(mock_hass, mock_client, entry)

    result = await run_update(coordinator)

    assert "333333333" in result
    v = result["333333333"]
    assert v.destination is None
    assert v.eta is None


# ---------------------------------------------------------------------------
# Test 10: update interval below 30 is clamped
# ---------------------------------------------------------------------------


def test_update_interval_below_30_is_clamped(mock_hass, mock_client):
    """A configured interval below MIN_UPDATE_INTERVAL should be clamped."""
    entry = make_config_entry(update_interval=10)  # Below 30s floor
    coordinator = make_coordinator(mock_hass, mock_client, entry)

    # The coordinator's update_interval must be at least MIN_UPDATE_INTERVAL
    assert coordinator.update_interval.total_seconds() >= MIN_UPDATE_INTERVAL


# ---------------------------------------------------------------------------
# Test 11: repeated refreshes with same vessel do not duplicate entered events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_duplicate_entered_events(mock_hass, mock_client):
    """Repeated polls with the same vessel should not re-fire entered."""
    cargo = make_vessel(mmsi="444444444")
    mock_client.get_vessels_in_radius = AsyncMock(return_value=[cargo])
    entry = make_config_entry()
    coordinator = make_coordinator(mock_hass, mock_client, entry)

    # Run three consecutive updates with the same vessel
    await run_update(coordinator)
    await run_update(coordinator)
    await run_update(coordinator)

    entered_events = [
        c for c in mock_hass.bus.async_fire.call_args_list if c[0][0] == EVENT_VESSEL_ENTERED
    ]
    # Entered should fire only once (on the first poll)
    assert len(entered_events) == 1


# ---------------------------------------------------------------------------
# Test 12: invalid/missing MMSI yields no entity_picture
# ---------------------------------------------------------------------------


def test_invalid_mmsi_yields_no_entity_picture():
    """vessel_photo_url should return None for invalid or missing MMSI values."""
    assert vessel_photo_url(None) is None
    assert vessel_photo_url("") is None
    assert vessel_photo_url("abc") is None  # Non-numeric
    assert vessel_photo_url("12345") is None  # Too short
    assert vessel_photo_url("1234567890") is None  # Too long (10 digits)

    # Valid 9-digit MMSI should return a URL
    url = vessel_photo_url("123456789")
    assert url is not None
    assert "123456789" in url


# ---------------------------------------------------------------------------
# Test 13: per-vessel entities are disabled by default; aggregate is enabled
# ---------------------------------------------------------------------------


def test_entity_registry_defaults():
    """Per-vessel entities must be disabled by default; count sensor enabled."""
    from custom_components.marinetraffic_tracker.sensor import (
        MarineTrafficCountSensor,
        MarineTrafficVesselSensor,
    )
    from custom_components.marinetraffic_tracker.device_tracker import (
        MarineTrafficVesselTracker,
    )

    # Check the entity_registry_enabled_default property on bare instances.
    # HA's ABCCachedProperties metaclass converts _attr_* class attributes
    # into cached properties, so we must check via an instance (not the class).
    count_instance = object.__new__(MarineTrafficCountSensor)
    assert count_instance.entity_registry_enabled_default is True, (
        "Count sensor must be enabled by default"
    )

    sensor_instance = object.__new__(MarineTrafficVesselSensor)
    assert sensor_instance.entity_registry_enabled_default is False, (
        "Per-vessel sensor must be disabled by default"
    )

    tracker_instance = object.__new__(MarineTrafficVesselTracker)
    assert tracker_instance.entity_registry_enabled_default is False, (
        "Per-vessel tracker must be disabled by default"
    )
