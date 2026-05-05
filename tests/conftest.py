"""Shared fixtures for MarineTraffic Tracker tests."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.marinetraffic_tracker.client import VesselData

# ---------------------------------------------------------------------------
# Shared mock vessel instances
# ---------------------------------------------------------------------------

MOCK_VESSEL_CARGO = VesselData(
    mmsi="123456789",
    name="EVER GIVEN",
    vessel_type=70,
    latitude=29.98,
    longitude=32.55,
    heading=180,
    course=182,
    speed=12.5,
    status="Under Way Using Engine",
    origin="SUEZ",
    destination="ROTTERDAM",
    eta="2026-05-15 14:00:00",
    last_seen=datetime.now(timezone.utc),
)

MOCK_VESSEL_TANKER = VesselData(
    mmsi="987654321",
    name="SEA TITAN",
    vessel_type=80,
    latitude=30.01,
    longitude=32.60,
    heading=90,
    course=91,
    speed=8.0,
    status="At Anchor",
    origin="JEDDAH",
    destination=None,
    eta=None,
    last_seen=datetime.now(timezone.utc),
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_client() -> MagicMock:
    """Return a mock MarineTrafficClient with async methods."""
    client = MagicMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[])
    client.get_vessels_in_box = AsyncMock(return_value=[])
    return client
