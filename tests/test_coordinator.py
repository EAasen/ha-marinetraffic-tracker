"""Coordinator tests for the MarineTraffic Tracker integration.

All tests are fully mocked — no real MarineTraffic endpoints are contacted.
The jitter sleep in the coordinator is patched to zero so tests run fast.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.marinetraffic_tracker.client import VesselData
from custom_components.marinetraffic_tracker.const import (
    CONF_FILTER_VESSEL_TYPES,
    CONF_STALE_TIMEOUT,
    EVENT_VESSEL_ENTERED,
    EVENT_VESSEL_EXITED,
)


# ---------------------------------------------------------------------------
# Helper: suppress jitter delay so tests are instant
# ---------------------------------------------------------------------------

_NO_JITTER = patch(
    "custom_components.marinetraffic_tracker.coordinator.asyncio.sleep",
    new=AsyncMock(return_value=None),
)


# ---------------------------------------------------------------------------
# 1. Vessel appears and is tracked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_vessel_appears_and_is_tracked(
    hass: Any,
    make_coordinator: Any,
    mock_client: Any,
    cargo_vessel: VesselData,
) -> None:
    """A vessel returned by the API should appear in coordinator.data."""
    mock_client.get_vessels_in_radius.return_value = [cargo_vessel]

    coordinator = make_coordinator()
    with _NO_JITTER:
        await coordinator.async_refresh()

    assert cargo_vessel.mmsi in coordinator.data
    assert coordinator.data[cargo_vessel.mmsi].name == cargo_vessel.name


# ---------------------------------------------------------------------------
# 2. Ghost ship is purged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ghost_ship_is_purged(
    hass: Any,
    make_coordinator: Any,
    mock_client: Any,
    cargo_vessel: VesselData,
) -> None:
    """A vessel that disappears from API results is removed after stale timeout."""
    stale_timeout = 60  # seconds
    mock_client.get_vessels_in_radius.return_value = [cargo_vessel]

    coordinator = make_coordinator(
        extra_data={CONF_STALE_TIMEOUT: stale_timeout}
    )
    with _NO_JITTER:
        # First refresh — vessel appears.
        await coordinator.async_refresh()
    assert cargo_vessel.mmsi in coordinator.data

    # Make the vessel appear stale by backdating last_seen.
    coordinator._vessels[cargo_vessel.mmsi].last_seen = datetime.now(timezone.utc) - timedelta(
        seconds=stale_timeout + 1
    )

    # Second refresh returns no vessels.
    mock_client.get_vessels_in_radius.return_value = []
    with _NO_JITTER:
        await coordinator.async_refresh()

    assert cargo_vessel.mmsi not in coordinator.data


# ---------------------------------------------------------------------------
# 3. Empty response drops count to zero
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_response_drops_count(
    hass: Any,
    make_coordinator: Any,
    mock_client: Any,
    cargo_vessel: VesselData,
) -> None:
    """After vessels exist, an empty response eventually clears coordinator data."""
    stale_timeout = 60
    mock_client.get_vessels_in_radius.return_value = [cargo_vessel]

    coordinator = make_coordinator(
        extra_data={CONF_STALE_TIMEOUT: stale_timeout}
    )
    with _NO_JITTER:
        await coordinator.async_refresh()
    assert len(coordinator.data) == 1

    # Backdate last_seen so it is considered stale, then send empty response.
    coordinator._vessels[cargo_vessel.mmsi].last_seen = datetime.now(timezone.utc) - timedelta(
        seconds=stale_timeout + 1
    )
    mock_client.get_vessels_in_radius.return_value = []
    with _NO_JITTER:
        await coordinator.async_refresh()

    assert len(coordinator.data) == 0


# ---------------------------------------------------------------------------
# 4. 403 Forbidden is handled gracefully
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_403_raises_update_failed(
    hass: Any,
    make_coordinator: Any,
    mock_client: Any,
) -> None:
    """A 403 error from the client should raise UpdateFailed, not crash."""
    mock_client.get_vessels_in_radius.side_effect = Exception("403 Forbidden")

    coordinator = make_coordinator()
    with _NO_JITTER, pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


# ---------------------------------------------------------------------------
# 5. 429 Too Many Requests is handled gracefully
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_429_raises_update_failed(
    hass: Any,
    make_coordinator: Any,
    mock_client: Any,
) -> None:
    """A 429 error from the client should raise UpdateFailed, not crash."""
    mock_client.get_vessels_in_radius.side_effect = Exception("429 Too Many Requests")

    coordinator = make_coordinator()
    with _NO_JITTER, pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


# ---------------------------------------------------------------------------
# 6. Entered event is fired once
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_entered_event_fired_once(
    hass: Any,
    make_coordinator: Any,
    mock_client: Any,
    cargo_vessel: VesselData,
) -> None:
    """Exactly one marinetraffic_vessel_entered event is fired when vessel first appears."""
    mock_client.get_vessels_in_radius.return_value = [cargo_vessel]
    entered_events: list[Any] = []
    hass.bus.async_listen(EVENT_VESSEL_ENTERED, lambda event: entered_events.append(event))

    coordinator = make_coordinator()
    with _NO_JITTER:
        await coordinator.async_refresh()

    # Allow the event to propagate.
    await hass.async_block_till_done()

    assert len(entered_events) == 1
    assert entered_events[0].data["mmsi"] == cargo_vessel.mmsi

    # Second refresh — same vessel, no new entered event.
    with _NO_JITTER:
        await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(entered_events) == 1


# ---------------------------------------------------------------------------
# 7. Exited event is fired once
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exited_event_fired_once(
    hass: Any,
    make_coordinator: Any,
    mock_client: Any,
    cargo_vessel: VesselData,
) -> None:
    """Exactly one marinetraffic_vessel_exited event is fired when vessel goes stale."""
    stale_timeout = 60
    mock_client.get_vessels_in_radius.return_value = [cargo_vessel]
    exited_events: list[Any] = []
    hass.bus.async_listen(EVENT_VESSEL_EXITED, lambda event: exited_events.append(event))

    coordinator = make_coordinator(
        extra_data={CONF_STALE_TIMEOUT: stale_timeout}
    )
    with _NO_JITTER:
        await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert cargo_vessel.mmsi in coordinator.data

    # Make the vessel stale and stop returning it from the API.
    coordinator._vessels[cargo_vessel.mmsi].last_seen = datetime.now(timezone.utc) - timedelta(
        seconds=stale_timeout + 1
    )
    mock_client.get_vessels_in_radius.return_value = []
    with _NO_JITTER:
        await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(exited_events) == 1
    assert exited_events[0].data["mmsi"] == cargo_vessel.mmsi

    # Third refresh — vessel already gone, no duplicate exited event.
    with _NO_JITTER:
        await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(exited_events) == 1


# ---------------------------------------------------------------------------
# 8. Vessel type filter excludes non-matching vessels
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_vessel_type_filter_excludes_non_matching(
    hass: Any,
    make_coordinator: Any,
    mock_client: Any,
    cargo_vessel: VesselData,
    tanker_vessel: VesselData,
) -> None:
    """When filter_vessel_types is set, only matching types remain in coordinator data."""
    mock_client.get_vessels_in_radius.return_value = [cargo_vessel, tanker_vessel]

    # Filter to tankers only (type 80).
    coordinator = make_coordinator(
        extra_data={CONF_FILTER_VESSEL_TYPES: [80]}
    )
    with _NO_JITTER:
        await coordinator.async_refresh()

    assert tanker_vessel.mmsi in coordinator.data
    assert cargo_vessel.mmsi not in coordinator.data


# ---------------------------------------------------------------------------
# 9. Optional fields with None do not break updates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_optional_none_fields_do_not_break_updates(
    hass: Any,
    make_coordinator: Any,
    mock_client: Any,
) -> None:
    """A vessel with destination=None and eta=None is handled without exceptions."""
    vessel_with_nones = VesselData(
        mmsi="111000111",
        name="GHOST FREIGHTER",
        vessel_type=70,
        latitude=58.0,
        longitude=9.0,
        heading=None,
        course=None,
        speed=None,
        status=None,
        origin=None,
        destination=None,
        eta=None,
        last_seen=datetime.now(timezone.utc),
    )
    mock_client.get_vessels_in_radius.return_value = [vessel_with_nones]

    coordinator = make_coordinator()
    with _NO_JITTER:
        await coordinator.async_refresh()

    assert vessel_with_nones.mmsi in coordinator.data
    v = coordinator.data[vessel_with_nones.mmsi]
    assert v.destination is None
    assert v.eta is None
