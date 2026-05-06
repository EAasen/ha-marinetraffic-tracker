"""Tests for sensor attribute consistency with the device_tracker platform.

Verifies that MarineTrafficVesselSensor.extra_state_attributes:
- Uses the canonical ATTR_* constant names from const.py
- Exposes all fields that the device_tracker platform also exposes
  (plus latitude/longitude which are native TrackerEntity properties
  and therefore sensor-only extras)
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from custom_components.marinetraffic_tracker.client import VesselData
from custom_components.marinetraffic_tracker.const import (
    ATTR_BEAM,
    ATTR_CALLSIGN,
    ATTR_COURSE,
    ATTR_DESTINATION,
    ATTR_DRAUGHT,
    ATTR_ETA,
    ATTR_FLAG,
    ATTR_HEADING,
    ATTR_IMO,
    ATTR_LAST_SEEN,
    ATTR_LENGTH,
    ATTR_MMSI,
    ATTR_ORIGIN,
    ATTR_RATE_OF_TURN,
    ATTR_SPEED,
    ATTR_STATUS,
    ATTR_VESSEL_NAME,
    ATTR_VESSEL_TYPE,
)
from custom_components.marinetraffic_tracker.device_tracker import (
    MarineTrafficVesselTracker,
)
from custom_components.marinetraffic_tracker.sensor import MarineTrafficVesselSensor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_full_vessel(mmsi: str = "123456789") -> VesselData:
    """Return a VesselData with all optional fields populated."""
    return VesselData(
        mmsi=mmsi,
        name="FULL VESSEL",
        vessel_type=70,
        latitude=59.9,
        longitude=10.7,
        heading=90,
        course=91,
        speed=12.5,
        status="Under Way Using Engine",
        origin="OSLO",
        destination="ROTTERDAM",
        eta="2026-06-01 08:00",
        imo="9123456",
        flag="NO",
        callsign="LAABC",
        length=225,
        draught=62.0,
        rate_of_turn=5,
        beam=32,
        last_seen=datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC),
    )


def _make_minimal_vessel(mmsi: str = "987654321") -> VesselData:
    """Return a VesselData with only mandatory fields and all optionals as None."""
    return VesselData(
        mmsi=mmsi,
        name="MINIMAL VESSEL",
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
        last_seen=datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC),
    )


def _make_coordinator(vessel: VesselData) -> MagicMock:
    coord = MagicMock()
    coord.last_update_success = True
    coord.data = {vessel.mmsi: vessel}
    return coord


def _make_sensor(vessel: VesselData) -> MarineTrafficVesselSensor:
    sensor = MarineTrafficVesselSensor.__new__(MarineTrafficVesselSensor)
    sensor.coordinator = _make_coordinator(vessel)
    sensor._entry_id = "test_entry"
    sensor._mmsi = vessel.mmsi
    sensor._attr_unique_id = f"test_entry_vessel_{vessel.mmsi}"
    return sensor


def _make_tracker(vessel: VesselData) -> MarineTrafficVesselTracker:
    tracker = MarineTrafficVesselTracker.__new__(MarineTrafficVesselTracker)
    tracker.coordinator = _make_coordinator(vessel)
    tracker._entry_id = "test_entry"
    tracker._mmsi = vessel.mmsi
    tracker._attr_unique_id = f"test_entry_tracker_{vessel.mmsi}"
    return tracker


# ---------------------------------------------------------------------------
# Sensor uses canonical ATTR_* keys
# ---------------------------------------------------------------------------


class TestSensorAttributeKeys:
    """Sensor must use the canonical ATTR_* constant names."""

    def test_mmsi_key_is_canonical(self) -> None:
        attrs = _make_sensor(_make_full_vessel()).extra_state_attributes
        assert ATTR_MMSI in attrs

    def test_vessel_name_key_is_canonical(self) -> None:
        attrs = _make_sensor(_make_full_vessel()).extra_state_attributes
        assert ATTR_VESSEL_NAME in attrs

    def test_vessel_type_key_is_canonical(self) -> None:
        attrs = _make_sensor(_make_full_vessel()).extra_state_attributes
        assert ATTR_VESSEL_TYPE in attrs

    def test_speed_key_is_canonical(self) -> None:
        attrs = _make_sensor(_make_full_vessel()).extra_state_attributes
        assert ATTR_SPEED in attrs

    def test_heading_key_is_canonical(self) -> None:
        attrs = _make_sensor(_make_full_vessel()).extra_state_attributes
        assert ATTR_HEADING in attrs

    def test_course_key_is_canonical(self) -> None:
        attrs = _make_sensor(_make_full_vessel()).extra_state_attributes
        assert ATTR_COURSE in attrs

    def test_status_key_is_canonical(self) -> None:
        attrs = _make_sensor(_make_full_vessel()).extra_state_attributes
        assert ATTR_STATUS in attrs

    def test_origin_key_is_canonical(self) -> None:
        attrs = _make_sensor(_make_full_vessel()).extra_state_attributes
        assert ATTR_ORIGIN in attrs

    def test_destination_key_is_canonical(self) -> None:
        attrs = _make_sensor(_make_full_vessel()).extra_state_attributes
        assert ATTR_DESTINATION in attrs

    def test_eta_key_is_canonical(self) -> None:
        attrs = _make_sensor(_make_full_vessel()).extra_state_attributes
        assert ATTR_ETA in attrs

    def test_imo_key_is_canonical(self) -> None:
        attrs = _make_sensor(_make_full_vessel()).extra_state_attributes
        assert ATTR_IMO in attrs

    def test_callsign_key_is_canonical(self) -> None:
        attrs = _make_sensor(_make_full_vessel()).extra_state_attributes
        assert ATTR_CALLSIGN in attrs

    def test_length_key_is_canonical(self) -> None:
        attrs = _make_sensor(_make_full_vessel()).extra_state_attributes
        assert ATTR_LENGTH in attrs

    def test_flag_key_is_canonical(self) -> None:
        attrs = _make_sensor(_make_full_vessel()).extra_state_attributes
        assert ATTR_FLAG in attrs

    def test_last_seen_key_is_canonical(self) -> None:
        attrs = _make_sensor(_make_full_vessel()).extra_state_attributes
        assert ATTR_LAST_SEEN in attrs

    def test_draught_key_is_canonical(self) -> None:
        attrs = _make_sensor(_make_full_vessel()).extra_state_attributes
        assert ATTR_DRAUGHT in attrs

    def test_rate_of_turn_key_is_canonical(self) -> None:
        attrs = _make_sensor(_make_full_vessel()).extra_state_attributes
        assert ATTR_RATE_OF_TURN in attrs

    def test_beam_key_is_canonical(self) -> None:
        attrs = _make_sensor(_make_full_vessel()).extra_state_attributes
        assert ATTR_BEAM in attrs


# ---------------------------------------------------------------------------
# Sensor and tracker expose the same canonical keys
# ---------------------------------------------------------------------------


class TestSensorTrackerAttributeConsistency:
    """Sensor and tracker extra_state_attributes must share the same ATTR_* keys.

    The tracker inherits lat/lon from TrackerEntity and therefore doesn't include
    them in extra_state_attributes.  The sensor adds them as extras instead.
    Those two fields are the only expected difference.
    """

    def test_sensor_has_all_tracker_keys(self) -> None:
        """Every key the tracker exposes must also be present in the sensor."""
        vessel = _make_full_vessel()
        sensor_attrs = _make_sensor(vessel).extra_state_attributes
        tracker_attrs = _make_tracker(vessel).extra_state_attributes

        tracker_only_missing = set(tracker_attrs.keys()) - set(sensor_attrs.keys())
        assert tracker_only_missing == set(), (
            f"Sensor is missing these tracker keys: {tracker_only_missing}"
        )

    def test_sensor_extra_keys_are_lat_lon_only(self) -> None:
        """Sensor may have latitude/longitude extras that tracker does not."""
        vessel = _make_full_vessel()
        sensor_attrs = _make_sensor(vessel).extra_state_attributes
        tracker_attrs = _make_tracker(vessel).extra_state_attributes

        sensor_extra = set(sensor_attrs.keys()) - set(tracker_attrs.keys())
        assert sensor_extra <= {"latitude", "longitude"}, (
            f"Unexpected sensor-only keys: {sensor_extra - {'latitude', 'longitude'}}"
        )


# ---------------------------------------------------------------------------
# Sensor attribute values with full vessel
# ---------------------------------------------------------------------------


class TestSensorAttributeValues:
    """Sensor attribute values must reflect the underlying VesselData."""

    def test_flag_value(self) -> None:
        attrs = _make_sensor(_make_full_vessel()).extra_state_attributes
        assert attrs[ATTR_FLAG] == "NO"

    def test_callsign_value(self) -> None:
        attrs = _make_sensor(_make_full_vessel()).extra_state_attributes
        assert attrs[ATTR_CALLSIGN] == "LAABC"

    def test_length_value(self) -> None:
        attrs = _make_sensor(_make_full_vessel()).extra_state_attributes
        assert attrs[ATTR_LENGTH] == 225

    def test_vessel_name_value(self) -> None:
        attrs = _make_sensor(_make_full_vessel()).extra_state_attributes
        assert attrs[ATTR_VESSEL_NAME] == "FULL VESSEL"

    def test_draught_value(self) -> None:
        attrs = _make_sensor(_make_full_vessel()).extra_state_attributes
        assert attrs[ATTR_DRAUGHT] == 62.0

    def test_rate_of_turn_value(self) -> None:
        attrs = _make_sensor(_make_full_vessel()).extra_state_attributes
        assert attrs[ATTR_RATE_OF_TURN] == 5

    def test_beam_value(self) -> None:
        attrs = _make_sensor(_make_full_vessel()).extra_state_attributes
        assert attrs[ATTR_BEAM] == 32

    def test_optional_fields_none_when_absent(self) -> None:
        attrs = _make_sensor(_make_minimal_vessel()).extra_state_attributes
        assert attrs[ATTR_FLAG] is None
        assert attrs[ATTR_CALLSIGN] is None
        assert attrs[ATTR_LENGTH] is None
        assert attrs[ATTR_DRAUGHT] is None
        assert attrs[ATTR_RATE_OF_TURN] is None
        assert attrs[ATTR_BEAM] is None

    def test_empty_attrs_when_vessel_absent(self) -> None:
        sensor = MarineTrafficVesselSensor.__new__(MarineTrafficVesselSensor)
        coord = MagicMock()
        coord.last_update_success = True
        coord.data = {}
        sensor.coordinator = coord
        sensor._entry_id = "test_entry"
        sensor._mmsi = "000000000"
        sensor._attr_unique_id = "test_entry_vessel_000000000"
        assert sensor.extra_state_attributes == {}
