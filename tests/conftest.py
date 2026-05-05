"""Shared pytest fixtures for the MarineTraffic Tracker test suite.

All fixtures are fully mocked — no network access is required.
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
    DOMAIN,
    TRACKING_MODE_RADIUS,
)
from custom_components.marinetraffic_tracker.coordinator import MarineTrafficCoordinator


# ---------------------------------------------------------------------------
# Vessel fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cargo_vessel() -> VesselData:
    """A cargo vessel (AIS type 70)."""
    return VesselData(
        mmsi="123456789",
        name="CARGO QUEEN",
        vessel_type=70,
        latitude=59.0,
        longitude=10.0,
        heading=180,
        course=182,
        speed=12.5,
        status="Under Way Using Engine",
        origin="HAMBURG",
        destination="OSLO",
        eta="2024-06-01 08:00",
        imo="9876543",
        flag="NO",
        callsign="LABC1",
        length=200,
        last_seen=datetime.now(timezone.utc),
    )


@pytest.fixture
def tanker_vessel() -> VesselData:
    """A tanker vessel (AIS type 80)."""
    return VesselData(
        mmsi="987654321",
        name="OIL RUNNER",
        vessel_type=80,
        latitude=59.5,
        longitude=10.5,
        heading=90,
        course=92,
        speed=8.0,
        status="Under Way Using Engine",
        origin="ROTTERDAM",
        destination="STAVANGER",
        eta="2024-06-02 12:00",
        imo="1234567",
        flag="NO",
        callsign="LDEF2",
        length=250,
        last_seen=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Mock client fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_client() -> MagicMock:
    """Return a mock MarineTrafficClient with configurable return values."""
    client = MagicMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[])
    client.get_vessels_in_box = AsyncMock(return_value=[])
    return client


# ---------------------------------------------------------------------------
# Coordinator factory fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def make_coordinator(hass: Any, mock_client: MagicMock):
    """Factory that creates a MarineTrafficCoordinator with configurable options."""

    def _factory(
        extra_data: dict | None = None,
        extra_options: dict | None = None,
    ) -> MarineTrafficCoordinator:
        base_data: dict[str, Any] = {
            CONF_TRACKING_MODE: TRACKING_MODE_RADIUS,
            CONF_LATITUDE: 59.0,
            CONF_LONGITUDE: 10.0,
            CONF_RADIUS_KM: 50.0,
            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_STALE_TIMEOUT: DEFAULT_STALE_TIMEOUT,
        }
        if extra_data:
            base_data.update(extra_data)

        entry = MagicMock()
        entry.entry_id = "test_entry_id"
        entry.data = base_data
        entry.options = extra_options or {}

        return MarineTrafficCoordinator(hass, entry, mock_client)

    return _factory
