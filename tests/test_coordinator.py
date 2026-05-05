"""Tests for MarineTrafficCoordinator — entry/exit event firing."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.marinetraffic_tracker.const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_RADIUS_KM,
    CONF_STALE_TIMEOUT,
    CONF_TRACKING_MODE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_STALE_TIMEOUT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    TRACKING_MODE_RADIUS,
)
from custom_components.marinetraffic_tracker.coordinator import MarineTrafficCoordinator

from .conftest import MOCK_VESSEL_CARGO, MOCK_VESSEL_TANKER


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(
    stale_timeout: int = DEFAULT_STALE_TIMEOUT,
    update_interval: int = DEFAULT_UPDATE_INTERVAL,
) -> MockConfigEntry:
    """Return a MockConfigEntry with minimal required fields."""
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
        options={},
    )


async def _make_and_init_coordinator(
    hass: HomeAssistant,
    client: MagicMock,
    stale_timeout: int = DEFAULT_STALE_TIMEOUT,
) -> MarineTrafficCoordinator:
    """Create a coordinator and call async_refresh with jitter disabled."""
    entry = _make_entry(stale_timeout=stale_timeout)
    coordinator = MarineTrafficCoordinator(hass, entry, client)
    # Disable jitter to keep tests deterministic.
    with patch("custom_components.marinetraffic_tracker.coordinator.asyncio.sleep"):
        await coordinator.async_refresh()
    return coordinator


async def _refresh(coordinator: MarineTrafficCoordinator) -> None:
    with patch("custom_components.marinetraffic_tracker.coordinator.asyncio.sleep"):
        await coordinator.async_refresh()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_vessel_appears_fires_entered_event(
    hass: HomeAssistant,
    mock_client: MagicMock,
) -> None:
    """A newly appearing vessel must fire exactly one entered event."""
    mock_client.get_vessels_in_radius.return_value = []
    coordinator = await _make_and_init_coordinator(hass, mock_client)

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


async def test_vessel_exits_fires_exited_event(
    hass: HomeAssistant,
    mock_client: MagicMock,
) -> None:
    """A vessel aging out past the stale timeout must fire exactly one exited event."""
    mock_client.get_vessels_in_radius.return_value = [MOCK_VESSEL_CARGO]
    # Use a short stale_timeout so we can trigger purge quickly.
    coordinator = await _make_and_init_coordinator(hass, mock_client, stale_timeout=600)

    events: list[Any] = []
    hass.bus.async_listen("marinetraffic_vessel_exited", events.append)

    # Vessel no longer returned by API and last_seen is old enough to be stale.
    mock_client.get_vessels_in_radius.return_value = []
    coordinator._vessels[MOCK_VESSEL_CARGO.mmsi].last_seen = (
        datetime.now(timezone.utc) - timedelta(seconds=700)
    )
    await _refresh(coordinator)

    assert len(events) == 1
    assert events[0].data["mmsi"] == MOCK_VESSEL_CARGO.mmsi
    assert events[0].data["name"] == MOCK_VESSEL_CARGO.name
    assert events[0].data["vessel_type"] == MOCK_VESSEL_CARGO.vessel_type
    assert "entry_id" in events[0].data


async def test_repeated_refreshes_do_not_refire_entered(
    hass: HomeAssistant,
    mock_client: MagicMock,
) -> None:
    """Subsequent polls with the same vessel must not fire duplicate entered events."""
    mock_client.get_vessels_in_radius.return_value = [MOCK_VESSEL_CARGO]
    coordinator = await _make_and_init_coordinator(hass, mock_client)

    events: list[Any] = []
    hass.bus.async_listen("marinetraffic_vessel_entered", events.append)

    # Poll three more times — the vessel is still there each time.
    for _ in range(3):
        await _refresh(coordinator)

    assert len(events) == 0, "No entered event should fire for an already-tracked vessel"


async def test_none_destination_and_eta_in_payload(
    hass: HomeAssistant,
    mock_client: MagicMock,
) -> None:
    """Event payload must tolerate destination=None and eta=None without raising."""
    mock_client.get_vessels_in_radius.return_value = []
    coordinator = await _make_and_init_coordinator(hass, mock_client)

    events: list[Any] = []
    hass.bus.async_listen("marinetraffic_vessel_entered", events.append)

    mock_client.get_vessels_in_radius.return_value = [MOCK_VESSEL_TANKER]
    await _refresh(coordinator)

    assert len(events) == 1
    assert events[0].data["destination"] is None
    assert events[0].data["eta"] is None


async def test_exited_event_payload_has_last_known_values(
    hass: HomeAssistant,
    mock_client: MagicMock,
) -> None:
    """Exit event payload must contain the last-known vessel fields."""
    mock_client.get_vessels_in_radius.return_value = [MOCK_VESSEL_TANKER]
    coordinator = await _make_and_init_coordinator(hass, mock_client, stale_timeout=600)

    events: list[Any] = []
    hass.bus.async_listen("marinetraffic_vessel_exited", events.append)

    mock_client.get_vessels_in_radius.return_value = []
    coordinator._vessels[MOCK_VESSEL_TANKER.mmsi].last_seen = (
        datetime.now(timezone.utc) - timedelta(seconds=700)
    )
    await _refresh(coordinator)

    assert len(events) == 1
    assert events[0].data["mmsi"] == MOCK_VESSEL_TANKER.mmsi
    assert events[0].data["name"] == MOCK_VESSEL_TANKER.name
    assert events[0].data["destination"] is None
    assert events[0].data["eta"] is None
