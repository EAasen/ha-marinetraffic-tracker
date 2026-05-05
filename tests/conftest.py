"""Shared pytest fixtures for MarineTraffic Tracker tests.

All fixtures are mocked — no real MarineTraffic network traffic is made.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.marinetraffic_tracker.client import VesselData
from custom_components.marinetraffic_tracker.const import (
    CONF_FILTER_VESSEL_TYPES,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_RADIUS_KM,
    CONF_STALE_TIMEOUT,
    CONF_TRACKING_MODE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_STALE_TIMEOUT,
    DEFAULT_UPDATE_INTERVAL,
    TRACKING_MODE_RADIUS,
)


# ---------------------------------------------------------------------------
# Vessel fixtures
# ---------------------------------------------------------------------------


def make_vessel(
    mmsi: str = "123456789",
    name: str = "Test Vessel",
    vessel_type: int = 70,  # Cargo
    latitude: float = 59.9,
    longitude: float = 10.7,
    destination: str | None = "OSLO",
    eta: str | None = "2024-01-15 08:00",
) -> VesselData:
    """Create a VesselData instance with sensible defaults for testing."""
    return VesselData(
        mmsi=mmsi,
        name=name,
        vessel_type=vessel_type,
        latitude=latitude,
        longitude=longitude,
        heading=180,
        course=182,
        speed=12.5,
        status="Under Way Using Engine",
        origin="HAMBURG",
        destination=destination,
        eta=eta,
        last_seen=datetime.now(timezone.utc),
    )


CARGO_VESSEL = make_vessel(mmsi="123456789", name="Cargo Ship", vessel_type=70)
TANKER_VESSEL = make_vessel(mmsi="987654321", name="Tanker Ship", vessel_type=80)


# ---------------------------------------------------------------------------
# Config entry fixture
# ---------------------------------------------------------------------------


def make_config_entry(
    entry_id: str = "test_entry_id",
    update_interval: int = DEFAULT_UPDATE_INTERVAL,
    stale_timeout: int = DEFAULT_STALE_TIMEOUT,
    filter_vessel_types: list[int] | None = None,
    options: dict[str, Any] | None = None,
) -> MagicMock:
    """Build a mock ConfigEntry with the given parameters."""
    entry = MagicMock()
    entry.entry_id = entry_id

    data: dict[str, Any] = {
        CONF_TRACKING_MODE: TRACKING_MODE_RADIUS,
        CONF_LATITUDE: 59.9,
        CONF_LONGITUDE: 10.7,
        CONF_RADIUS_KM: 50.0,
        CONF_UPDATE_INTERVAL: update_interval,
        CONF_STALE_TIMEOUT: stale_timeout,
    }
    if filter_vessel_types is not None:
        data[CONF_FILTER_VESSEL_TYPES] = filter_vessel_types

    entry.data = data
    entry.options = options or {}
    return entry


# ---------------------------------------------------------------------------
# Coordinator factory fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_hass():
    """Return a minimal mock HomeAssistant instance."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()
    return hass


@pytest.fixture
def mock_client():
    """Return a mock MarineTrafficClient with a configurable response."""
    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[])
    return client


def make_coordinator(hass, client, entry):
    """Instantiate a coordinator with the given mocks, bypassing jitter."""
    from custom_components.marinetraffic_tracker.coordinator import (
        MarineTrafficCoordinator,
    )

    return MarineTrafficCoordinator(hass, entry, client)
