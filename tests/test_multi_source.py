"""Tests for multi-source concurrent polling in MarineTrafficCoordinator.

Covers:
- Concurrent fetch with results merged from multiple sources.
- MMSI collision resolution (most-recent last_seen wins).
- Partial failure (one source returns None, others succeed).
- All sources fail → UpdateFailed raised.
- Min interval clamped to API floor when any extra client is AISHub.
- source field propagation on VesselData.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.marinetraffic_tracker.aishub_client import AISHubClient
from custom_components.marinetraffic_tracker.client import VesselData
from custom_components.marinetraffic_tracker.const import (
    CONF_STALE_TIMEOUT,
    CONF_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL_API,
)
from custom_components.marinetraffic_tracker.coordinator import MarineTrafficCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed

from .conftest import MOCK_VESSEL_CARGO, MOCK_VESSEL_TANKER, MOCK_VESSEL_PASSENGER


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(options: dict | None = None, data: dict | None = None) -> MagicMock:
    """Return a fake ConfigEntry-like mock."""
    entry = MagicMock()
    entry.entry_id = "test_multi_source_entry"
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


def _make_mock_client(vessels: list[VesselData] | None) -> MagicMock:
    """Return a mock client whose get_vessels_in_radius returns *vessels*."""
    client = MagicMock()
    client.get_vessels_in_radius = AsyncMock(return_value=vessels if vessels is not None else None)
    client.get_vessels_in_box = AsyncMock(return_value=vessels if vessels is not None else None)
    return client


# ---------------------------------------------------------------------------
# Concurrent fetch / merge tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multi_source_merges_unique_vessels() -> None:
    """Vessels from two different sources with different MMSIs should both appear."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()

    primary_client = _make_mock_client([MOCK_VESSEL_CARGO])
    extra_client = _make_mock_client([MOCK_VESSEL_TANKER])

    entry = _make_entry()
    coordinator = MarineTrafficCoordinator(
        hass, entry, primary_client, extra_clients=[extra_client]
    )
    result = await coordinator._async_update_data()

    assert MOCK_VESSEL_CARGO.mmsi in result, "Cargo vessel from primary source should be present"
    assert MOCK_VESSEL_TANKER.mmsi in result, "Tanker vessel from extra source should be present"
    assert len(result) == 2


@pytest.mark.asyncio
async def test_mmsi_collision_keeps_most_recent() -> None:
    """When the same MMSI appears in two sources, the freshest last_seen wins."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()

    now = datetime.now(UTC)
    older_vessel = replace(MOCK_VESSEL_CARGO, speed=5.0, last_seen=now - timedelta(seconds=30))
    newer_vessel = replace(MOCK_VESSEL_CARGO, speed=12.5, last_seen=now)

    primary_client = _make_mock_client([older_vessel])
    extra_client = _make_mock_client([newer_vessel])

    entry = _make_entry()
    coordinator = MarineTrafficCoordinator(
        hass, entry, primary_client, extra_clients=[extra_client]
    )
    result = await coordinator._async_update_data()

    assert MOCK_VESSEL_CARGO.mmsi in result
    # The newer observation (speed=12.5) should win over the older (speed=5.0)
    # Note: coordinator stamps last_seen=now, so we compare the source speed.
    assert result[MOCK_VESSEL_CARGO.mmsi].speed == 12.5


@pytest.mark.asyncio
async def test_partial_failure_primary_still_succeeds() -> None:
    """When extra source fails (returns None), primary results are still used."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()

    primary_client = _make_mock_client([MOCK_VESSEL_CARGO])
    failing_client = _make_mock_client(None)
    # Make the failing client raise an exception to trigger None return
    failing_client.get_vessels_in_radius = AsyncMock(side_effect=Exception("Connection failed"))

    entry = _make_entry()
    coordinator = MarineTrafficCoordinator(
        hass, entry, primary_client, extra_clients=[failing_client]
    )
    result = await coordinator._async_update_data()

    assert MOCK_VESSEL_CARGO.mmsi in result, "Primary result should still be present"
    assert len(result) == 1


@pytest.mark.asyncio
async def test_partial_failure_extra_fails_primary_succeeds() -> None:
    """When only the primary fails, extra source results are still used."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()

    failing_primary = _make_mock_client(None)
    failing_primary.get_vessels_in_radius = AsyncMock(side_effect=Exception("Network error"))
    extra_client = _make_mock_client([MOCK_VESSEL_TANKER])

    entry = _make_entry()
    coordinator = MarineTrafficCoordinator(
        hass, entry, failing_primary, extra_clients=[extra_client]
    )
    result = await coordinator._async_update_data()

    assert MOCK_VESSEL_TANKER.mmsi in result, "Extra source result should be present"
    assert len(result) == 1


@pytest.mark.asyncio
async def test_all_sources_fail_raises_update_failed() -> None:
    """When every source returns None or raises, UpdateFailed must be raised."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()

    failing_primary = _make_mock_client(None)
    failing_primary.get_vessels_in_radius = AsyncMock(side_effect=Exception("Timeout"))
    failing_extra = _make_mock_client(None)
    failing_extra.get_vessels_in_radius = AsyncMock(side_effect=Exception("503"))

    entry = _make_entry()
    coordinator = MarineTrafficCoordinator(
        hass, entry, failing_primary, extra_clients=[failing_extra]
    )

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_three_sources_all_contribute() -> None:
    """All three data sources should contribute unique vessels to the merged result."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()

    primary_client = _make_mock_client([MOCK_VESSEL_CARGO])
    extra1 = _make_mock_client([MOCK_VESSEL_TANKER])
    extra2 = _make_mock_client([MOCK_VESSEL_PASSENGER])

    entry = _make_entry()
    coordinator = MarineTrafficCoordinator(
        hass, entry, primary_client, extra_clients=[extra1, extra2]
    )
    result = await coordinator._async_update_data()

    assert MOCK_VESSEL_CARGO.mmsi in result
    assert MOCK_VESSEL_TANKER.mmsi in result
    assert MOCK_VESSEL_PASSENGER.mmsi in result
    assert len(result) == 3


# ---------------------------------------------------------------------------
# Min-interval floor with extra AISHub client
# ---------------------------------------------------------------------------


def test_extra_aishub_client_uses_api_floor() -> None:
    """When any extra client is AISHub, the coordinator must use MIN_UPDATE_INTERVAL_API."""
    hass = MagicMock()
    primary_client = MagicMock()  # non-AISHub primary

    # Create an AISHub-like extra client (we can mock it as the isinstance check uses type)
    aishub_extra = MagicMock(spec=AISHubClient)

    entry = _make_entry(
        data={
            CONF_UPDATE_INTERVAL: 5,  # below API floor
            CONF_STALE_TIMEOUT: 600,
            "tracking_mode": "radius",
            "latitude": 59.9,
            "longitude": 10.7,
            "radius_km": 50.0,
            "data_source": "marinetraffic",
        }
    )
    coordinator = MarineTrafficCoordinator(
        hass, entry, primary_client, extra_clients=[aishub_extra]
    )
    # With AISHub in extra_clients, the floor is MIN_UPDATE_INTERVAL_API (5 s).
    assert coordinator.update_interval.total_seconds() == MIN_UPDATE_INTERVAL_API


def test_no_aishub_uses_scraper_floor() -> None:
    """Without AISHub, the coordinator must use MIN_UPDATE_INTERVAL (30 s)."""
    hass = MagicMock()
    primary_client = MagicMock()
    extra_client = MagicMock()  # non-AISHub extra

    entry = _make_entry(
        data={
            CONF_UPDATE_INTERVAL: 5,  # below scraper floor
            CONF_STALE_TIMEOUT: 600,
            "tracking_mode": "radius",
            "latitude": 59.9,
            "longitude": 10.7,
            "radius_km": 50.0,
            "data_source": "marinetraffic",
        }
    )
    coordinator = MarineTrafficCoordinator(
        hass, entry, primary_client, extra_clients=[extra_client]
    )
    assert coordinator.update_interval.total_seconds() == MIN_UPDATE_INTERVAL


# ---------------------------------------------------------------------------
# Backward compat: fallback_client still works
# ---------------------------------------------------------------------------


def test_fallback_client_treated_as_extra() -> None:
    """A fallback_client passed to the coordinator is included in _extra_clients."""
    hass = MagicMock()
    primary_client = MagicMock()
    fallback_client = MagicMock()

    entry = _make_entry()
    coordinator = MarineTrafficCoordinator(
        hass, entry, primary_client, fallback_client=fallback_client
    )
    assert fallback_client in coordinator._extra_clients


@pytest.mark.asyncio
async def test_fallback_client_provides_vessels_on_primary_failure() -> None:
    """Fallback client vessels should appear when primary fails."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()

    failing_primary = MagicMock()
    failing_primary.get_vessels_in_radius = AsyncMock(side_effect=Exception("Down"))

    fallback_client = _make_mock_client([MOCK_VESSEL_CARGO])

    entry = _make_entry()
    coordinator = MarineTrafficCoordinator(
        hass, entry, failing_primary, fallback_client=fallback_client
    )
    result = await coordinator._async_update_data()

    assert MOCK_VESSEL_CARGO.mmsi in result


# ---------------------------------------------------------------------------
# source field on VesselData
# ---------------------------------------------------------------------------


def test_vessel_data_source_field_defaults_none() -> None:
    """VesselData.source defaults to None for backward compat."""
    vessel = VesselData(
        mmsi="123456789",
        name="Test Vessel",
        vessel_type=70,
        latitude=59.9,
        longitude=10.7,
        heading=None,
        course=None,
        speed=None,
        status=None,
        origin=None,
        destination=None,
        eta=None,
    )
    assert vessel.source is None


def test_vessel_data_source_field_can_be_set() -> None:
    """VesselData.source can be set to a source name string."""
    vessel = VesselData(
        mmsi="123456789",
        name="Test Vessel",
        vessel_type=70,
        latitude=59.9,
        longitude=10.7,
        heading=None,
        course=None,
        speed=None,
        status=None,
        origin=None,
        destination=None,
        eta=None,
        source="aishub",
    )
    assert vessel.source == "aishub"
