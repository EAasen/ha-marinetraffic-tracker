"""Tests for per-vessel device_info on MarineTrafficVesselEntity subclasses.

Covers:
- MarineTrafficVesselSensor.device_info — per-vessel device with correct identifiers
- MarineTrafficVesselTracker.device_info — per-vessel device with correct identifiers
- device name falls back to MMSI when vessel is absent
- device model reflects vessel type
- via_device links back to the integration-level device
- MarineTrafficEntity.device_info — shared integration device unchanged
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from custom_components.marinetraffic_tracker.client import VesselData
from custom_components.marinetraffic_tracker.const import DOMAIN, VESSEL_TYPE_MAP
from custom_components.marinetraffic_tracker.device_tracker import (
    MarineTrafficVesselTracker,
)
from custom_components.marinetraffic_tracker.entity import MarineTrafficEntity
from custom_components.marinetraffic_tracker.sensor import (
    MarineTrafficCountSensor,
    MarineTrafficVesselSensor,
)

ENTRY_ID = "test_entry_id"
MMSI = "123456789"


def _make_vessel(
    mmsi: str = MMSI,
    name: str = "Test Vessel",
    vessel_type: int = 70,
) -> VesselData:
    return VesselData(
        mmsi=mmsi,
        name=name,
        vessel_type=vessel_type,
        latitude=59.9,
        longitude=10.7,
        heading=90,
        course=91,
        speed=12.5,
        status="Under Way Using Engine",
        origin=None,
        destination=None,
        eta=None,
        last_seen=datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC),
    )


def _make_coordinator(vessels: dict[str, VesselData]) -> MagicMock:
    coord = MagicMock()
    coord.last_update_success = True
    coord.data = vessels
    coord.anchored_vessels = {}
    coord.get_position_history = MagicMock(return_value=[])
    return coord


def _make_vessel_sensor(
    vessel: VesselData | None,
    mmsi: str = MMSI,
    entry_id: str = ENTRY_ID,
) -> MarineTrafficVesselSensor:
    sensor = MarineTrafficVesselSensor.__new__(MarineTrafficVesselSensor)
    coord = _make_coordinator({vessel.mmsi: vessel} if vessel else {})
    sensor.coordinator = coord
    sensor._entry_id = entry_id
    sensor._mmsi = mmsi
    sensor._attr_unique_id = f"{entry_id}_vessel_{mmsi}"
    return sensor


def _make_vessel_tracker(
    vessel: VesselData | None,
    mmsi: str = MMSI,
    entry_id: str = ENTRY_ID,
) -> MarineTrafficVesselTracker:
    tracker = MarineTrafficVesselTracker.__new__(MarineTrafficVesselTracker)
    coord = _make_coordinator({vessel.mmsi: vessel} if vessel else {})
    tracker.coordinator = coord
    tracker._entry_id = entry_id
    tracker._mmsi = mmsi
    tracker._attr_unique_id = f"{entry_id}_tracker_{mmsi}"
    return tracker


def _make_count_sensor(entry_id: str = ENTRY_ID) -> MarineTrafficCountSensor:
    sensor = MarineTrafficCountSensor.__new__(MarineTrafficCountSensor)
    coord = _make_coordinator({})
    sensor.coordinator = coord
    sensor._entry_id = entry_id
    sensor._attr_unique_id = f"{entry_id}_count"
    sensor._attr_name = "Vessel Count"
    return sensor


# ---------------------------------------------------------------------------
# MarineTrafficEntity — shared integration device (unchanged)
# ---------------------------------------------------------------------------


class TestIntegrationDeviceInfo:
    """The global count sensor must still use the shared integration device."""

    def test_count_sensor_uses_shared_device(self) -> None:
        sensor = _make_count_sensor()
        info = sensor.device_info
        assert (DOMAIN, ENTRY_ID) in info["identifiers"]

    def test_count_sensor_device_name(self) -> None:
        sensor = _make_count_sensor()
        assert sensor.device_info["name"] == "MarineTraffic Tracker"

    def test_count_sensor_manufacturer(self) -> None:
        sensor = _make_count_sensor()
        assert sensor.device_info["manufacturer"] == "MarineTraffic"


# ---------------------------------------------------------------------------
# VesselSensor — per-vessel device_info
# ---------------------------------------------------------------------------


class TestVesselSensorDeviceInfo:
    """MarineTrafficVesselSensor must produce a per-vessel device."""

    def test_identifier_is_per_vessel(self) -> None:
        vessel = _make_vessel()
        sensor = _make_vessel_sensor(vessel)
        info = sensor.device_info
        assert (DOMAIN, f"{ENTRY_ID}_{MMSI}") in info["identifiers"]

    def test_identifier_differs_from_integration_device(self) -> None:
        vessel = _make_vessel()
        sensor = _make_vessel_sensor(vessel)
        info = sensor.device_info
        assert (DOMAIN, ENTRY_ID) not in info["identifiers"]

    def test_device_name_is_vessel_name(self) -> None:
        vessel = _make_vessel(name="EVER GIVEN")
        sensor = _make_vessel_sensor(vessel)
        assert sensor.device_info["name"] == "EVER GIVEN"

    def test_device_name_falls_back_to_mmsi_when_vessel_absent(self) -> None:
        sensor = _make_vessel_sensor(None, mmsi="999888777")
        assert sensor.device_info["name"] == "Vessel 999888777"

    def test_device_model_is_vessel_type_label(self) -> None:
        vessel = _make_vessel(vessel_type=70)
        sensor = _make_vessel_sensor(vessel)
        expected = VESSEL_TYPE_MAP.get(70, "Type 70")
        assert sensor.device_info["model"] == expected

    def test_device_model_is_none_when_vessel_absent(self) -> None:
        sensor = _make_vessel_sensor(None)
        assert sensor.device_info["model"] is None

    def test_manufacturer_is_marinetraffic_tracker(self) -> None:
        vessel = _make_vessel()
        sensor = _make_vessel_sensor(vessel)
        assert sensor.device_info["manufacturer"] == "MarineTraffic Tracker"

    def test_via_device_links_to_integration_device(self) -> None:
        vessel = _make_vessel()
        sensor = _make_vessel_sensor(vessel)
        assert sensor.device_info["via_device"] == (DOMAIN, ENTRY_ID)

    def test_different_mmsi_produces_different_device(self) -> None:
        v1 = _make_vessel(mmsi="111111111")
        v2 = _make_vessel(mmsi="222222222")
        s1 = _make_vessel_sensor(v1, mmsi="111111111")
        s2 = _make_vessel_sensor(v2, mmsi="222222222")
        assert s1.device_info["identifiers"] != s2.device_info["identifiers"]

    def test_different_entry_id_produces_different_device(self) -> None:
        vessel = _make_vessel()
        s1 = _make_vessel_sensor(vessel, entry_id="entry_a")
        s2 = _make_vessel_sensor(vessel, entry_id="entry_b")
        assert s1.device_info["identifiers"] != s2.device_info["identifiers"]


# ---------------------------------------------------------------------------
# VesselTracker — per-vessel device_info
# ---------------------------------------------------------------------------


class TestVesselTrackerDeviceInfo:
    """MarineTrafficVesselTracker must produce a per-vessel device."""

    def test_identifier_is_per_vessel(self) -> None:
        vessel = _make_vessel()
        tracker = _make_vessel_tracker(vessel)
        info = tracker.device_info
        assert (DOMAIN, f"{ENTRY_ID}_{MMSI}") in info["identifiers"]

    def test_identifier_differs_from_integration_device(self) -> None:
        vessel = _make_vessel()
        tracker = _make_vessel_tracker(vessel)
        info = tracker.device_info
        assert (DOMAIN, ENTRY_ID) not in info["identifiers"]

    def test_device_name_is_vessel_name(self) -> None:
        vessel = _make_vessel(name="SEA TITAN")
        tracker = _make_vessel_tracker(vessel)
        assert tracker.device_info["name"] == "SEA TITAN"

    def test_device_name_falls_back_to_mmsi_when_vessel_absent(self) -> None:
        tracker = _make_vessel_tracker(None, mmsi="555444333")
        assert tracker.device_info["name"] == "Vessel 555444333"

    def test_device_model_is_vessel_type_label(self) -> None:
        vessel = _make_vessel(vessel_type=80)
        tracker = _make_vessel_tracker(vessel)
        expected = VESSEL_TYPE_MAP.get(80, "Type 80")
        assert tracker.device_info["model"] == expected

    def test_manufacturer_is_marinetraffic_tracker(self) -> None:
        vessel = _make_vessel()
        tracker = _make_vessel_tracker(vessel)
        assert tracker.device_info["manufacturer"] == "MarineTraffic Tracker"

    def test_via_device_links_to_integration_device(self) -> None:
        vessel = _make_vessel()
        tracker = _make_vessel_tracker(vessel)
        assert tracker.device_info["via_device"] == (DOMAIN, ENTRY_ID)

    def test_sensor_and_tracker_share_same_device_identifier(self) -> None:
        """Vessel sensor and tracker must resolve to the same device."""
        vessel = _make_vessel()
        sensor = _make_vessel_sensor(vessel)
        tracker = _make_vessel_tracker(vessel)
        assert sensor.device_info["identifiers"] == tracker.device_info["identifiers"]
