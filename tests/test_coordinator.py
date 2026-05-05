"""Mocked coordinator test suite for MarineTraffic Tracker.

All 13 cases are covered here.  No real network traffic is generated —
all API responses are controlled through mock_client fixtures.

Test matrix
-----------
1.  Vessel appears and is tracked
2.  Ghost ship is purged after stale timeout
3.  Empty response ultimately drops tracked count to zero
4.  403 Forbidden is handled gracefully as an update failure
5.  429 Too Many Requests is handled gracefully as an update failure
6.  Entered event is fired once (new vessel)
7.  Exited event is fired once (stale vessel removed)
8.  Vessel type filter excludes non-matching vessels
9.  Optional fields with None do not break updates
10. Update interval below 30 s is clamped to 30 s
11. Repeated refreshes with the same vessel do not duplicate entered events
12. Invalid/missing MMSI yields no entity_picture
13. Per-vessel entities are disabled by default; aggregate remains enabled
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.marinetraffic_tracker.const import (
    CONF_FILTER_VESSEL_TYPES,
    CONF_UPDATE_INTERVAL,
    EVENT_VESSEL_ENTERED,
    EVENT_VESSEL_EXITED,
    MIN_UPDATE_INTERVAL,
)
from custom_components.marinetraffic_tracker.coordinator import MarineTrafficCoordinator
from custom_components.marinetraffic_tracker.device_tracker import MarineTrafficVesselTracker
from custom_components.marinetraffic_tracker.entity import vessel_photo_url
from custom_components.marinetraffic_tracker.sensor import (
    MarineTrafficCountSensor,
    MarineTrafficVesselSensor,
)

from .conftest import make_vessel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _refresh(coordinator: MarineTrafficCoordinator) -> None:
    """Trigger a coordinator update, suppressing the jitter sleep."""
    with patch("custom_components.marinetraffic_tracker.coordinator.asyncio.sleep"):
        await coordinator.async_refresh()


# ---------------------------------------------------------------------------
# Test 1: Vessel appears and is tracked
# ---------------------------------------------------------------------------


async def test_vessel_appears_and_is_tracked(
    coordinator: MarineTrafficCoordinator,
    mock_client: AsyncMock,
    cargo_vessel,
) -> None:
    """A vessel returned by the API appears in coordinator.data."""
    mock_client.get_vessels_in_radius.return_value = [cargo_vessel]

    await _refresh(coordinator)

    assert cargo_vessel.mmsi in coordinator.data
    tracked = coordinator.data[cargo_vessel.mmsi]
    assert tracked.name == cargo_vessel.name
    assert tracked.vessel_type == cargo_vessel.vessel_type


# ---------------------------------------------------------------------------
# Test 2: Ghost ship purged after stale timeout
# ---------------------------------------------------------------------------


async def test_stale_vessel_is_purged(
    coordinator: MarineTrafficCoordinator,
    mock_client: AsyncMock,
    cargo_vessel,
) -> None:
    """A vessel not seen for longer than stale_timeout is removed."""
    mock_client.get_vessels_in_radius.return_value = [cargo_vessel]
    await _refresh(coordinator)
    assert cargo_vessel.mmsi in coordinator.data

    # Age the vessel beyond the stale timeout.
    stale_time = datetime.now(UTC) - timedelta(seconds=coordinator.stale_timeout_seconds + 1)
    coordinator._vessels[cargo_vessel.mmsi].last_seen = stale_time

    # Next poll returns nothing — stale vessel should be purged.
    mock_client.get_vessels_in_radius.return_value = []
    await _refresh(coordinator)

    assert cargo_vessel.mmsi not in coordinator.data


# ---------------------------------------------------------------------------
# Test 3: Empty response drops tracked count to zero
# ---------------------------------------------------------------------------


async def test_empty_response_drops_count_to_zero(
    coordinator: MarineTrafficCoordinator,
    mock_client: AsyncMock,
    cargo_vessel,
) -> None:
    """After stale timeout with no vessels returned, coordinator.data is empty."""
    mock_client.get_vessels_in_radius.return_value = [cargo_vessel]
    await _refresh(coordinator)
    assert len(coordinator.data) == 1

    # Age the vessel past the timeout then poll with empty response.
    stale_time = datetime.now(UTC) - timedelta(seconds=coordinator.stale_timeout_seconds + 1)
    coordinator._vessels[cargo_vessel.mmsi].last_seen = stale_time
    mock_client.get_vessels_in_radius.return_value = []
    await _refresh(coordinator)

    assert len(coordinator.data) == 0


# ---------------------------------------------------------------------------
# Test 4: 403 Forbidden handled as update failure
# ---------------------------------------------------------------------------


async def test_403_raises_update_failed(
    coordinator: MarineTrafficCoordinator,
    mock_client: AsyncMock,
) -> None:
    """A 403 response from the client causes last_update_success = False."""
    mock_client.get_vessels_in_radius.side_effect = aiohttp.ClientResponseError(
        request_info=MagicMock(),
        history=(),
        status=403,
        message="Forbidden",
    )

    await _refresh(coordinator)

    assert coordinator.last_update_success is False


# ---------------------------------------------------------------------------
# Test 5: 429 Too Many Requests handled as update failure
# ---------------------------------------------------------------------------


async def test_429_raises_update_failed(
    coordinator: MarineTrafficCoordinator,
    mock_client: AsyncMock,
) -> None:
    """A 429 response from the client causes last_update_success = False."""
    mock_client.get_vessels_in_radius.side_effect = aiohttp.ClientResponseError(
        request_info=MagicMock(),
        history=(),
        status=429,
        message="Too Many Requests",
    )

    await _refresh(coordinator)

    assert coordinator.last_update_success is False


# ---------------------------------------------------------------------------
# Test 6: Entered event fired once for a new vessel
# ---------------------------------------------------------------------------


async def test_entered_event_fired_once(
    hass,
    coordinator: MarineTrafficCoordinator,
    mock_client: AsyncMock,
    cargo_vessel,
) -> None:
    """marinetraffic_vessel_entered is fired exactly once when a vessel appears."""
    fired_events: list[dict] = []

    hass.bus.async_listen(
        EVENT_VESSEL_ENTERED,
        lambda event: fired_events.append(event.data),
    )

    mock_client.get_vessels_in_radius.return_value = [cargo_vessel]
    await _refresh(coordinator)

    assert len(fired_events) == 1
    assert fired_events[0]["mmsi"] == cargo_vessel.mmsi


# ---------------------------------------------------------------------------
# Test 7: Exited event fired once when vessel is removed
# ---------------------------------------------------------------------------


async def test_exited_event_fired_once(
    hass,
    coordinator: MarineTrafficCoordinator,
    mock_client: AsyncMock,
    cargo_vessel,
) -> None:
    """marinetraffic_vessel_exited is fired exactly once when a vessel is purged."""
    fired_events: list[dict] = []

    hass.bus.async_listen(
        EVENT_VESSEL_EXITED,
        lambda event: fired_events.append(event.data),
    )

    mock_client.get_vessels_in_radius.return_value = [cargo_vessel]
    await _refresh(coordinator)

    # Age vessel past stale timeout.
    stale_time = datetime.now(UTC) - timedelta(seconds=coordinator.stale_timeout_seconds + 1)
    coordinator._vessels[cargo_vessel.mmsi].last_seen = stale_time
    mock_client.get_vessels_in_radius.return_value = []
    await _refresh(coordinator)

    assert len(fired_events) == 1
    assert fired_events[0]["mmsi"] == cargo_vessel.mmsi


# ---------------------------------------------------------------------------
# Test 8: Vessel type filter excludes non-matching vessels
# ---------------------------------------------------------------------------


async def test_vessel_type_filter_excludes_non_matching(
    hass,
    mock_client: AsyncMock,
    cargo_vessel,
    tanker_vessel,
    mock_entry,
) -> None:
    """With a cargo-only filter, tankers are excluded from coordinator.data."""
    # Configure the entry to allow only cargo (type 70).
    mock_entry.data[CONF_FILTER_VESSEL_TYPES] = ["70"]
    coordinator = MarineTrafficCoordinator(hass, mock_entry, mock_client)

    mock_client.get_vessels_in_radius.return_value = [cargo_vessel, tanker_vessel]
    await _refresh(coordinator)

    assert cargo_vessel.mmsi in coordinator.data
    assert tanker_vessel.mmsi not in coordinator.data


# ---------------------------------------------------------------------------
# Test 9: Optional fields with None do not break updates
# ---------------------------------------------------------------------------


async def test_optional_fields_none_do_not_break(
    coordinator: MarineTrafficCoordinator,
    mock_client: AsyncMock,
) -> None:
    """Vessel with destination=None and eta=None processes without exception."""
    vessel = make_vessel(mmsi="111222333", destination=None, eta=None)
    mock_client.get_vessels_in_radius.return_value = [vessel]

    await _refresh(coordinator)

    assert "111222333" in coordinator.data
    tracked = coordinator.data["111222333"]
    assert tracked.destination is None
    assert tracked.eta is None


# ---------------------------------------------------------------------------
# Test 10: Update interval below 30 s is clamped to 30 s
# ---------------------------------------------------------------------------


async def test_update_interval_clamped_to_minimum(hass, mock_entry, mock_client) -> None:
    """A configured interval below MIN_UPDATE_INTERVAL is clamped at runtime."""
    mock_entry.data[CONF_UPDATE_INTERVAL] = 10  # below minimum

    coordinator = MarineTrafficCoordinator(hass, mock_entry, mock_client)

    expected = timedelta(seconds=MIN_UPDATE_INTERVAL)
    assert coordinator.update_interval == expected


# ---------------------------------------------------------------------------
# Test 11: No duplicate entered events across repeated refreshes
# ---------------------------------------------------------------------------


async def test_no_duplicate_entered_events(
    hass,
    coordinator: MarineTrafficCoordinator,
    mock_client: AsyncMock,
    cargo_vessel,
) -> None:
    """The same vessel triggers entered only once across two identical polls."""
    entered_count = 0

    def _counter(event) -> None:
        nonlocal entered_count
        entered_count += 1

    hass.bus.async_listen(EVENT_VESSEL_ENTERED, _counter)

    mock_client.get_vessels_in_radius.return_value = [cargo_vessel]
    await _refresh(coordinator)
    await _refresh(coordinator)

    assert entered_count == 1


# ---------------------------------------------------------------------------
# Test 12: Invalid/missing MMSI yields no entity_picture
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mmsi",
    [
        None,
        "",
        "12345",  # too short
        "1234567890",  # too long
        "12345678X",  # non-digit
    ],
)
def test_invalid_mmsi_no_entity_picture(mmsi: str | None) -> None:
    """vessel_photo_url returns None for any non-9-digit MMSI."""
    assert vessel_photo_url(mmsi) is None


def test_valid_mmsi_returns_entity_picture() -> None:
    """vessel_photo_url returns a non-empty URL for a valid 9-digit MMSI."""
    url = vessel_photo_url("123456789")
    assert url is not None
    assert "123456789" in url


# ---------------------------------------------------------------------------
# Test 13: Per-vessel entities disabled by default; aggregate remains enabled
# ---------------------------------------------------------------------------


def test_per_vessel_entities_disabled_by_default() -> None:
    """MarineTrafficVesselSensor and VesselTracker default to disabled.

    HA's ABCCachedProperties metaclass stores ``_attr_*`` class attributes under
    a ``__attr_*`` (double-underscore) key in the class ``__dict__``.  We check
    that key to confirm the class-level declaration is correctly processed.
    """
    assert MarineTrafficVesselSensor.__dict__["__attr_entity_registry_enabled_default"] is False
    assert MarineTrafficVesselTracker.__dict__["__attr_entity_registry_enabled_default"] is False


def test_count_sensor_enabled_by_default() -> None:
    """MarineTrafficCountSensor must remain enabled by default."""
    # CountSensor must NOT override _attr_entity_registry_enabled_default to False.
    assert (
        MarineTrafficCountSensor.__dict__.get("__attr_entity_registry_enabled_default") is not False
    )
