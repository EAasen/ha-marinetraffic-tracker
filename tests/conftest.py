"""Shared fixtures for MarineTraffic Tracker tests.

All tests use mocked network I/O — no real MarineTraffic endpoints are hit.
"""

from __future__ import annotations

from datetime import UTC, datetime
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
    DEFAULT_FILTER_VESSEL_TYPES,
    DEFAULT_STALE_TIMEOUT,
    DEFAULT_UPDATE_INTERVAL,
    TRACKING_MODE_RADIUS,
)
from custom_components.marinetraffic_tracker.coordinator import MarineTrafficCoordinator

# ---------------------------------------------------------------------------
# Vessel fixtures
# ---------------------------------------------------------------------------


def make_vessel(
    mmsi: str = "123456789",
    name: str = "TEST VESSEL",
    vessel_type: int = 70,
    latitude: float = 59.9,
    longitude: float = 10.7,
    destination: str | None = "OSLO",
    eta: str | None = "2024-01-15 08:00",
) -> VesselData:
    """Build a VesselData instance for testing."""
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
        last_seen=datetime.now(UTC),
    )


@pytest.fixture
def cargo_vessel() -> VesselData:
    """A cargo vessel (type 70)."""
    return make_vessel(mmsi="123456789", name="CARGO SHIP", vessel_type=70)


@pytest.fixture
def tanker_vessel() -> VesselData:
    """A tanker vessel (type 80)."""
    return make_vessel(mmsi="987654321", name="TANKER SHIP", vessel_type=80)


# ---------------------------------------------------------------------------
# Client + config entry fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client() -> AsyncMock:
    """AsyncMock of MarineTrafficClient returning no vessels by default."""
    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[])
    client.get_vessels_in_box = AsyncMock(return_value=[])
    return client


@pytest.fixture
def entry_data() -> dict:
    """Minimal config entry data for radius tracking."""
    return {
        CONF_TRACKING_MODE: TRACKING_MODE_RADIUS,
        CONF_LATITUDE: 59.9139,
        CONF_LONGITUDE: 10.7522,
        CONF_RADIUS_KM: 50.0,
        CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
        CONF_STALE_TIMEOUT: DEFAULT_STALE_TIMEOUT,
        CONF_FILTER_VESSEL_TYPES: DEFAULT_FILTER_VESSEL_TYPES,
    }


@pytest.fixture
def mock_entry(entry_data: dict) -> MagicMock:
    """Mock ConfigEntry with default radius tracking configuration."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = entry_data
    entry.options = {}
    return entry


@pytest.fixture
def coordinator(hass, mock_entry, mock_client) -> MarineTrafficCoordinator:
    """A MarineTrafficCoordinator wired to a mock client and HA instance."""
    return MarineTrafficCoordinator(hass, mock_entry, mock_client)
