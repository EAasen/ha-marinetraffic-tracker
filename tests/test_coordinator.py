"""Tests for MarineTrafficCoordinator.

Covers:
1.  Vessel appears and is tracked (count = 1).
2.  Ghost ship purged after stale_timeout (count = 0).
3.  Empty response drops count to zero (genuine empty area).
4.  UpdateFailed raised on network error / HTTP error.
5.  429 Too Many Requests → empty list returned, no exception.
6.  Vessel type filter excludes tankers when filter=["70"] (cargo only).
7.  marinetraffic_vessel_entered fires on first observation.
8.  marinetraffic_vessel_exited fires on stale purge.
9.  No duplicate entered events on repeated observation.
10. MIN_UPDATE_INTERVAL floor enforced in coordinator constructor.
11. Bounding-box mode fetches correctly (tracking_mode=box).
12. Jitter sleep called with value in [0, DEFAULT_JITTER_MAX].
13. Second update merges a new vessel without losing the first.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.marinetraffic_tracker.const import (
    CONF_EAST,
    CONF_FILTER_VESSEL_TYPES,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NORTH,
    CONF_RADIUS_KM,
    CONF_SOUTH,
    CONF_STALE_TIMEOUT,
    CONF_TRACKING_MODE,
    CONF_UPDATE_INTERVAL,
    CONF_WEST,
    DEFAULT_JITTER_MAX,
    DEFAULT_STALE_TIMEOUT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MIN_UPDATE_INTERVAL,
    TRACKING_MODE_BOX,
    TRACKING_MODE_RADIUS,
)
from custom_components.marinetraffic_tracker.coordinator import MarineTrafficCoordinator

from .conftest import MOCK_VESSEL_CARGO, MOCK_VESSEL_TANKER

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_radius_entry(
    stale_timeout: int = DEFAULT_STALE_TIMEOUT,
    update_interval: int = DEFAULT_UPDATE_INTERVAL,
    filter_types: list[str] | None = None,
) -> MockConfigEntry:
    """Return a MockConfigEntry configured for radius mode."""
    options: dict[str, Any] = {}
    if filter_types is not None:
        options[CONF_FILTER_VESSEL_TYPES] = filter_types
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TRACKING_MODE: TRACKING_MODE_RADIUS,
            CONF_LATITUDE: 59.9,
            CONF_LONGITUDE: 10.7,
            CONF_RADIUS_KM: 50.0,
            CONF_UPDATE_INTERVAL: update_interval,
            CONF_STALE_TIMEOUT: stale_timeout,
        },
        options=options,
    )


def _make_box_entry() -> MockConfigEntry:
    """Return a MockConfigEntry configured for bounding-box mode."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TRACKING_MODE: TRACKING_MODE_BOX,
            CONF_NORTH: 60.0,
            CONF_EAST: 11.0,
            CONF_SOUTH: 59.0,
            CONF_WEST: 10.0,
            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_STALE_TIMEOUT: DEFAULT_STALE_TIMEOUT,
        },
        options={},
    )


async def _make_coordinator(
    hass: HomeAssistant,
    client: MagicMock,
    entry: MockConfigEntry | None = None,
) -> MarineTrafficCoordinator:
    """Create and initialise a coordinator with jitter disabled."""
    if entry is None:
        entry = _make_radius_entry()
    coordinator = MarineTrafficCoordinator(hass, entry, client)
    with patch("custom_components.marinetraffic_tracker.coordinator.asyncio.sleep"):
        await coordinator.async_refresh()
    return coordinator


async def _refresh(coordinator: MarineTrafficCoordinator) -> None:
    """Trigger another coordinator poll with jitter disabled."""
    with patch("custom_components.marinetraffic_tracker.coordinator.asyncio.sleep"):
        await coordinator.async_refresh()


# ---------------------------------------------------------------------------
# 1. Vessel appears and is tracked
# ---------------------------------------------------------------------------

async def test_vessel_appears_and_is_tracked(
    hass: HomeAssistant,
    mock_client: MagicMock,
) -> None:
    """A newly observed vessel must appear in coordinator.data."""
    mock_client.get_vessels_in_radius.return_value = [MOCK_VESSEL_CARGO]
    coordinator = await _make_coordinator(hass, mock_client)

    assert coordinator.data is not None
    assert MOCK_VESSEL_CARGO.mmsi in coordinator.data
    assert len(coordinator.data) == 1


# ---------------------------------------------------------------------------
# 2. Ghost ship purged after stale_timeout
# ---------------------------------------------------------------------------

async def test_stale_vessel_is_purged(
    hass: HomeAssistant,
    mock_client: MagicMock,
) -> None:
    """A vessel not seen for longer than stale_timeout is removed."""
    mock_client.get_vessels_in_radius.return_value = [MOCK_VESSEL_CARGO]
    entry = _make_radius_entry(stale_timeout=600)
    coordinator = await _make_coordinator(hass, mock_client, entry)

    assert MOCK_VESSEL_CARGO.mmsi in coordinator.data

    # Make the vessel appear stale by backdating last_seen.
    coordinator._vessels[MOCK_VESSEL_CARGO.mmsi].last_seen = (
        datetime.now(UTC) - timedelta(seconds=700)
    )
    mock_client.get_vessels_in_radius.return_value = []
    await _refresh(coordinator)

    assert coordinator.data == {}


# ---------------------------------------------------------------------------
# 3. Empty response drops count to zero
# ---------------------------------------------------------------------------

async def test_empty_response_clears_vessels(
    hass: HomeAssistant,
    mock_client: MagicMock,
) -> None:
    """A genuinely empty area response must leave no active vessels."""
    mock_client.get_vessels_in_radius.return_value = []
    coordinator = await _make_coordinator(hass, mock_client)

    assert coordinator.data == {}


# ---------------------------------------------------------------------------
# 4. Network / API error raises UpdateFailed
# ---------------------------------------------------------------------------

async def test_network_error_raises_update_failed(
    hass: HomeAssistant,
    mock_client: MagicMock,
) -> None:
    """A network error must be wrapped in UpdateFailed."""
    mock_client.get_vessels_in_radius.side_effect = OSError("Connection refused")
    coordinator = await _make_coordinator(hass, mock_client)

    # After initial (failed) refresh, last_update_success is False.
    assert coordinator.last_update_success is False


# ---------------------------------------------------------------------------
# 5. 429 Too Many Requests returns empty list — no exception
# ---------------------------------------------------------------------------

async def test_429_returns_empty_list(
    hass: HomeAssistant,
    mock_client: MagicMock,
) -> None:
    """A 429 response must be handled as an empty vessel list, not an error."""
    # Simulate client returning [] on 429 (as client.py:213 does).
    mock_client.get_vessels_in_radius.return_value = []
    coordinator = await _make_coordinator(hass, mock_client)

    assert coordinator.last_update_success is True
    assert coordinator.data == {}


# ---------------------------------------------------------------------------
# 6. Vessel type filter — tankers excluded when filter=["70"] (cargo only)
# ---------------------------------------------------------------------------

async def test_vessel_type_filter_excludes_non_matching(
    hass: HomeAssistant,
    mock_client: MagicMock,
) -> None:
    """Only vessels whose type is in the filter set must appear in data."""
    mock_client.get_vessels_in_radius.return_value = [MOCK_VESSEL_CARGO, MOCK_VESSEL_TANKER]
    entry = _make_radius_entry(filter_types=["70"])  # cargo only
    coordinator = await _make_coordinator(hass, mock_client, entry)

    assert MOCK_VESSEL_CARGO.mmsi in coordinator.data
    assert MOCK_VESSEL_TANKER.mmsi not in coordinator.data


async def test_empty_filter_allows_all_types(
    hass: HomeAssistant,
    mock_client: MagicMock,
) -> None:
    """An empty filter list must allow all vessel types through."""
    mock_client.get_vessels_in_radius.return_value = [MOCK_VESSEL_CARGO, MOCK_VESSEL_TANKER]
    entry = _make_radius_entry(filter_types=[])
    coordinator = await _make_coordinator(hass, mock_client, entry)

    assert MOCK_VESSEL_CARGO.mmsi in coordinator.data
    assert MOCK_VESSEL_TANKER.mmsi in coordinator.data


# ---------------------------------------------------------------------------
# 7. marinetraffic_vessel_entered fires on first observation
# ---------------------------------------------------------------------------

async def test_vessel_appears_fires_entered_event(
    hass: HomeAssistant,
    mock_client: MagicMock,
) -> None:
    """A newly appearing vessel must fire exactly one entered event."""
    mock_client.get_vessels_in_radius.return_value = []
    coordinator = await _make_coordinator(hass, mock_client)

    events: list[Any] = []
    hass.bus.async_listen("marinetraffic_vessel_entered", events.append)

    mock_client.get_vessels_in_radius.return_value = [MOCK_VESSEL_CARGO]
    await _refresh(coordinator)

    assert len(events) == 1
    assert events[0].data["mmsi"] == MOCK_VESSEL_CARGO.mmsi
    assert events[0].data["name"] == MOCK_VESSEL_CARGO.name
    assert events[0].data["vessel_type"] == MOCK_VESSEL_CARGO.vessel_type
    assert events[0].data["latitude"] == MOCK_VESSEL_CARGO.latitude
    assert events[0].data["longitude"] == MOCK_VESSEL_CARGO.longitude
    assert events[0].data["destination"] == MOCK_VESSEL_CARGO.destination
    assert events[0].data["eta"] == MOCK_VESSEL_CARGO.eta
    assert "entry_id" in events[0].data


# ---------------------------------------------------------------------------
# 8. marinetraffic_vessel_exited fires on stale purge
# ---------------------------------------------------------------------------

async def test_vessel_exits_fires_exited_event(
    hass: HomeAssistant,
    mock_client: MagicMock,
) -> None:
    """A vessel aging out past the stale timeout must fire exactly one exited event."""
    mock_client.get_vessels_in_radius.return_value = [MOCK_VESSEL_CARGO]
    entry = _make_radius_entry(stale_timeout=600)
    coordinator = await _make_coordinator(hass, mock_client, entry)

    events: list[Any] = []
    hass.bus.async_listen("marinetraffic_vessel_exited", events.append)

    mock_client.get_vessels_in_radius.return_value = []
    coordinator._vessels[MOCK_VESSEL_CARGO.mmsi].last_seen = (
        datetime.now(UTC) - timedelta(seconds=700)
    )
    await _refresh(coordinator)

    assert len(events) == 1
    assert events[0].data["mmsi"] == MOCK_VESSEL_CARGO.mmsi
    assert events[0].data["name"] == MOCK_VESSEL_CARGO.name
    assert events[0].data["vessel_type"] == MOCK_VESSEL_CARGO.vessel_type
    assert "entry_id" in events[0].data


async def test_exited_event_payload_has_last_known_values(
    hass: HomeAssistant,
    mock_client: MagicMock,
) -> None:
    """Exit event payload must contain the last-known vessel fields."""
    mock_client.get_vessels_in_radius.return_value = [MOCK_VESSEL_TANKER]
    entry = _make_radius_entry(stale_timeout=600)
    coordinator = await _make_coordinator(hass, mock_client, entry)

    events: list[Any] = []
    hass.bus.async_listen("marinetraffic_vessel_exited", events.append)

    mock_client.get_vessels_in_radius.return_value = []
    coordinator._vessels[MOCK_VESSEL_TANKER.mmsi].last_seen = (
        datetime.now(UTC) - timedelta(seconds=700)
    )
    await _refresh(coordinator)

    assert len(events) == 1
    assert events[0].data["mmsi"] == MOCK_VESSEL_TANKER.mmsi
    assert events[0].data["name"] == MOCK_VESSEL_TANKER.name
    assert events[0].data["destination"] is None
    assert events[0].data["eta"] is None


# ---------------------------------------------------------------------------
# 9. No duplicate entered events on repeated observation
# ---------------------------------------------------------------------------

async def test_repeated_refreshes_do_not_refire_entered(
    hass: HomeAssistant,
    mock_client: MagicMock,
) -> None:
    """Subsequent polls with the same vessel must not fire duplicate entered events."""
    mock_client.get_vessels_in_radius.return_value = [MOCK_VESSEL_CARGO]
    coordinator = await _make_coordinator(hass, mock_client)

    events: list[Any] = []
    hass.bus.async_listen("marinetraffic_vessel_entered", events.append)

    for _ in range(3):
        await _refresh(coordinator)

    assert len(events) == 0, "No entered event should fire for an already-tracked vessel"


# ---------------------------------------------------------------------------
# 10. MIN_UPDATE_INTERVAL floor enforced in coordinator constructor
# ---------------------------------------------------------------------------

async def test_coordinator_clamps_interval_below_floor(
    hass: HomeAssistant,
    mock_client: MagicMock,
) -> None:
    """Coordinator must enforce MIN_UPDATE_INTERVAL even if config says lower."""
    entry = _make_radius_entry(update_interval=5)  # below the 30s floor
    coordinator = MarineTrafficCoordinator(hass, entry, mock_client)

    assert coordinator.update_interval.total_seconds() >= MIN_UPDATE_INTERVAL


async def test_coordinator_respects_interval_above_floor(
    hass: HomeAssistant,
    mock_client: MagicMock,
) -> None:
    """A configured interval >= MIN_UPDATE_INTERVAL must not be clamped."""
    entry = _make_radius_entry(update_interval=120)
    coordinator = MarineTrafficCoordinator(hass, entry, mock_client)

    assert coordinator.update_interval.total_seconds() == 120


# ---------------------------------------------------------------------------
# 11. Bounding-box mode fetches correctly
# ---------------------------------------------------------------------------

async def test_box_mode_calls_get_vessels_in_box(
    hass: HomeAssistant,
    mock_client: MagicMock,
) -> None:
    """In box mode the coordinator must call get_vessels_in_box, not in_radius."""
    mock_client.get_vessels_in_box.return_value = [MOCK_VESSEL_CARGO]
    entry = _make_box_entry()
    coordinator = await _make_coordinator(hass, mock_client, entry)

    mock_client.get_vessels_in_box.assert_called()
    mock_client.get_vessels_in_radius.assert_not_called()
    assert MOCK_VESSEL_CARGO.mmsi in coordinator.data


# ---------------------------------------------------------------------------
# 12. Jitter sleep called with value in [0, DEFAULT_JITTER_MAX]
# ---------------------------------------------------------------------------

async def test_jitter_sleep_is_called(
    hass: HomeAssistant,
    mock_client: MagicMock,
) -> None:
    """asyncio.sleep must be called once per poll cycle for jitter."""
    mock_client.get_vessels_in_radius.return_value = []
    entry = _make_radius_entry()
    coordinator = MarineTrafficCoordinator(hass, entry, mock_client)

    with patch(
        "custom_components.marinetraffic_tracker.coordinator.asyncio.sleep",
        new_callable=AsyncMock,
    ) as mock_sleep:
        await coordinator.async_refresh()

    mock_sleep.assert_called_once()
    sleep_arg = mock_sleep.call_args[0][0]
    assert 0 <= sleep_arg <= DEFAULT_JITTER_MAX


# ---------------------------------------------------------------------------
# 13. Second update merges new vessel without losing first
# ---------------------------------------------------------------------------

async def test_second_update_merges_new_vessel(
    hass: HomeAssistant,
    mock_client: MagicMock,
) -> None:
    """A new vessel appearing in a subsequent poll must be added without evicting the first."""
    mock_client.get_vessels_in_radius.return_value = [MOCK_VESSEL_CARGO]
    coordinator = await _make_coordinator(hass, mock_client)

    assert MOCK_VESSEL_CARGO.mmsi in coordinator.data
    assert MOCK_VESSEL_TANKER.mmsi not in coordinator.data

    mock_client.get_vessels_in_radius.return_value = [MOCK_VESSEL_CARGO, MOCK_VESSEL_TANKER]
    await _refresh(coordinator)

    assert MOCK_VESSEL_CARGO.mmsi in coordinator.data
    assert MOCK_VESSEL_TANKER.mmsi in coordinator.data
    assert len(coordinator.data) == 2


# ---------------------------------------------------------------------------
# Additional coverage: filtered vessel does not fire entered event
# ---------------------------------------------------------------------------

async def test_filtered_vessel_does_not_fire_entered_event(
    hass: HomeAssistant,
    mock_client: MagicMock,
) -> None:
    """A vessel excluded by the type filter must not trigger an entered event."""
    mock_client.get_vessels_in_radius.return_value = []
    entry = _make_radius_entry(filter_types=["70"])  # cargo only; tanker (80) is excluded
    coordinator = await _make_coordinator(hass, mock_client, entry)

    events: list[Any] = []
    hass.bus.async_listen("marinetraffic_vessel_entered", events.append)

    # Only the tanker is in the response — it should be filtered out.
    mock_client.get_vessels_in_radius.return_value = [MOCK_VESSEL_TANKER]
    await _refresh(coordinator)

    assert len(events) == 0
    assert MOCK_VESSEL_TANKER.mmsi not in coordinator.data


async def test_none_destination_and_eta_in_payload(
    hass: HomeAssistant,
    mock_client: MagicMock,
) -> None:
    """Event payload must tolerate destination=None and eta=None without raising."""
    mock_client.get_vessels_in_radius.return_value = []
    coordinator = await _make_coordinator(hass, mock_client)

    events: list[Any] = []
    hass.bus.async_listen("marinetraffic_vessel_entered", events.append)

    mock_client.get_vessels_in_radius.return_value = [MOCK_VESSEL_TANKER]
    await _refresh(coordinator)

    assert len(events) == 1
    assert events[0].data["destination"] is None
    assert events[0].data["eta"] is None
