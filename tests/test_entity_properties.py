"""Tests for entity property coverage gaps.

Covers:
- MarineTrafficVesselSensor.icon — returns type-specific MDI icon
- MarineTrafficVesselSensor.available — False when vessel is stale/absent
- MarineTrafficVesselSensor.name — fallback to MMSI when vessel absent
- MarineTrafficVesselSensor extra_state_attributes data_source field
- MarineTrafficVesselTracker.source_type — always GPS
- MarineTrafficVesselTracker.location_accuracy — always 10
- MarineTrafficVesselTracker.latitude/longitude — None when vessel absent
- MarineTrafficVesselTracker.available — False when vessel absent
- MarineTrafficVesselTracker.name — fallback to MMSI when vessel absent
- MarineTrafficVesselTracker extra_state_attributes data_source field
- MarineTrafficCountSensor.anchored_vessel_count / anchored_vessels
- Coordinator stale_timeout_seconds reads options before data
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from homeassistant.components.device_tracker.const import SourceType

from custom_components.marinetraffic_tracker.client import VesselData
from custom_components.marinetraffic_tracker.const import (
    ATTR_DATA_SOURCE,
    DEFAULT_VESSEL_ICON,
    VESSEL_TYPE_ICONS,
)
from custom_components.marinetraffic_tracker.coordinator import MarineTrafficCoordinator
from custom_components.marinetraffic_tracker.device_tracker import (
    MarineTrafficVesselTracker,
)
from custom_components.marinetraffic_tracker.sensor import (
    MarineTrafficCountSensor,
    MarineTrafficVesselSensor,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_vessel(
    mmsi: str = "123456789",
    vessel_type: int = 70,
    status: str | None = "Under Way Using Engine",
    source: str | None = "marinetraffic",
) -> VesselData:
    return VesselData(
        mmsi=mmsi,
        name="Test Vessel",
        vessel_type=vessel_type,
        latitude=59.9,
        longitude=10.7,
        heading=90,
        course=91,
        speed=12.5,
        status=status,
        origin=None,
        destination=None,
        eta=None,
        last_seen=datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC),
        source=source,
    )


def _make_coordinator_with_vessels(vessels: dict[str, VesselData]) -> MagicMock:
    coord = MagicMock()
    coord.last_update_success = True
    coord.data = vessels
    coord.anchored_vessels = {}
    coord.get_position_history = MagicMock(return_value=[])
    return coord


def _make_sensor(vessel: VesselData | None, mmsi: str = "123456789") -> MarineTrafficVesselSensor:
    sensor = MarineTrafficVesselSensor.__new__(MarineTrafficVesselSensor)
    coord = _make_coordinator_with_vessels({vessel.mmsi: vessel} if vessel else {})
    sensor.coordinator = coord
    sensor._entry_id = "test_entry"
    sensor._mmsi = mmsi
    sensor._attr_unique_id = f"test_entry_vessel_{mmsi}"
    return sensor


def _make_tracker(vessel: VesselData | None, mmsi: str = "123456789") -> MarineTrafficVesselTracker:
    tracker = MarineTrafficVesselTracker.__new__(MarineTrafficVesselTracker)
    coord = _make_coordinator_with_vessels({vessel.mmsi: vessel} if vessel else {})
    tracker.coordinator = coord
    tracker._entry_id = "test_entry"
    tracker._mmsi = mmsi
    tracker._attr_unique_id = f"test_entry_tracker_{mmsi}"
    return tracker


def _make_count_sensor(
    vessels: dict[str, VesselData],
    anchored: dict[str, VesselData] | None = None,
) -> MarineTrafficCountSensor:
    sensor = MarineTrafficCountSensor.__new__(MarineTrafficCountSensor)
    coord = MagicMock()
    coord.last_update_success = True
    coord.data = vessels
    coord.anchored_vessels = anchored or {}
    sensor.coordinator = coord
    sensor._entry_id = "test_entry"
    sensor._attr_unique_id = "test_entry_count"
    sensor._attr_name = "Vessel Count"
    return sensor


# ---------------------------------------------------------------------------
# VesselSensor — icon property
# ---------------------------------------------------------------------------


class TestVesselSensorIcon:
    """Tests for the icon property of MarineTrafficVesselSensor."""

    def test_known_cargo_type_returns_ship_wheel(self) -> None:
        """Vessel type 70 (Cargo) must return the mdi:ship-wheel icon."""
        vessel = _make_vessel(vessel_type=70)
        sensor = _make_sensor(vessel)
        assert sensor.icon == VESSEL_TYPE_ICONS[70]

    def test_known_tanker_type_returns_water_icon(self) -> None:
        """Vessel type 80 (Tanker) must return the mdi:water icon."""
        vessel = _make_vessel(vessel_type=80)
        sensor = _make_sensor(vessel)
        assert sensor.icon == VESSEL_TYPE_ICONS[80]

    def test_known_passenger_type_returns_ferry_icon(self) -> None:
        """Vessel type 60 (Passenger) must return the mdi:ferry icon."""
        vessel = _make_vessel(vessel_type=60)
        sensor = _make_sensor(vessel)
        assert sensor.icon == VESSEL_TYPE_ICONS[60]

    def test_known_fishing_type_returns_fish_icon(self) -> None:
        """Vessel type 30 (Fishing) must return the mdi:fish icon."""
        vessel = _make_vessel(vessel_type=30)
        sensor = _make_sensor(vessel)
        assert sensor.icon == VESSEL_TYPE_ICONS[30]

    def test_known_sailing_type_returns_sail_boat_icon(self) -> None:
        """Vessel type 36 (Sailing) must return the mdi:sail-boat icon."""
        vessel = _make_vessel(vessel_type=36)
        sensor = _make_sensor(vessel)
        assert sensor.icon == VESSEL_TYPE_ICONS[36]

    def test_unknown_vessel_type_returns_default_icon(self) -> None:
        """A vessel type not in VESSEL_TYPE_ICONS must return the default icon."""
        vessel = _make_vessel(vessel_type=9999)
        sensor = _make_sensor(vessel)
        assert sensor.icon == DEFAULT_VESSEL_ICON

    def test_absent_vessel_returns_default_icon(self) -> None:
        """When the vessel is not in coordinator data, default icon must be returned."""
        sensor = _make_sensor(None)
        assert sensor.icon == DEFAULT_VESSEL_ICON


# ---------------------------------------------------------------------------
# VesselSensor — available property
# ---------------------------------------------------------------------------


class TestVesselSensorAvailable:
    """Tests for the available property of MarineTrafficVesselSensor."""

    def test_available_when_vessel_present(self) -> None:
        """Sensor is available when the vessel is in coordinator data."""
        vessel = _make_vessel()
        sensor = _make_sensor(vessel)
        assert sensor.available is True

    def test_unavailable_when_vessel_absent(self) -> None:
        """Sensor is unavailable when the vessel has been purged from data."""
        sensor = _make_sensor(None)
        # _make_sensor with None creates a coordinator with empty data dict.
        assert sensor.available is False

    def test_unavailable_when_last_update_failed(self) -> None:
        """When last_update_success is False the sensor must be unavailable."""
        vessel = _make_vessel()
        sensor = _make_sensor(vessel)
        sensor.coordinator.last_update_success = False
        assert sensor.available is False


# ---------------------------------------------------------------------------
# VesselSensor — name fallback
# ---------------------------------------------------------------------------


class TestVesselSensorName:
    """Tests for the name property of MarineTrafficVesselSensor."""

    def test_name_returns_vessel_name(self) -> None:
        vessel = _make_vessel()
        sensor = _make_sensor(vessel)
        assert sensor.name == "Test Vessel"

    def test_name_fallback_to_mmsi_when_vessel_absent(self) -> None:
        """When the vessel is absent, name must fall back to 'Vessel <MMSI>'."""
        mmsi = "999888777"
        sensor = _make_sensor(None, mmsi=mmsi)
        assert sensor.name == f"Vessel {mmsi}"


# ---------------------------------------------------------------------------
# VesselSensor — data_source in extra_state_attributes
# ---------------------------------------------------------------------------


class TestVesselSensorDataSource:
    """Tests for the data_source attribute in sensor extra_state_attributes."""

    def test_data_source_is_present(self) -> None:
        vessel = _make_vessel(source="marinetraffic")
        sensor = _make_sensor(vessel)
        assert ATTR_DATA_SOURCE in sensor.extra_state_attributes

    def test_data_source_marinetraffic(self) -> None:
        vessel = _make_vessel(source="marinetraffic")
        sensor = _make_sensor(vessel)
        assert sensor.extra_state_attributes[ATTR_DATA_SOURCE] == "marinetraffic"

    def test_data_source_aishub(self) -> None:
        vessel = _make_vessel(source="aishub")
        sensor = _make_sensor(vessel)
        assert sensor.extra_state_attributes[ATTR_DATA_SOURCE] == "aishub"

    def test_data_source_vesselfinder(self) -> None:
        vessel = _make_vessel(source="vesselfinder")
        sensor = _make_sensor(vessel)
        assert sensor.extra_state_attributes[ATTR_DATA_SOURCE] == "vesselfinder"

    def test_data_source_none_when_source_not_set(self) -> None:
        vessel = _make_vessel(source=None)
        sensor = _make_sensor(vessel)
        assert sensor.extra_state_attributes[ATTR_DATA_SOURCE] is None


# ---------------------------------------------------------------------------
# VesselTracker — source_type and location_accuracy
# ---------------------------------------------------------------------------


class TestVesselTrackerProperties:
    """Tests for TrackerEntity-specific properties on MarineTrafficVesselTracker."""

    def test_source_type_is_gps(self) -> None:
        """AIS positioning is GPS-based; source_type must be SourceType.GPS."""
        vessel = _make_vessel()
        tracker = _make_tracker(vessel)
        assert tracker.source_type == SourceType.GPS

    def test_location_accuracy_is_10(self) -> None:
        """AIS Class A transponders report to within ~10 metres."""
        vessel = _make_vessel()
        tracker = _make_tracker(vessel)
        assert tracker.location_accuracy == 10

    def test_latitude_returns_vessel_latitude(self) -> None:
        vessel = _make_vessel()
        tracker = _make_tracker(vessel)
        assert tracker.latitude == 59.9

    def test_longitude_returns_vessel_longitude(self) -> None:
        vessel = _make_vessel()
        tracker = _make_tracker(vessel)
        assert tracker.longitude == 10.7

    def test_latitude_none_when_vessel_absent(self) -> None:
        """Latitude must be None when the vessel is stale/absent."""
        tracker = _make_tracker(None)
        assert tracker.latitude is None

    def test_longitude_none_when_vessel_absent(self) -> None:
        """Longitude must be None when the vessel is stale/absent."""
        tracker = _make_tracker(None)
        assert tracker.longitude is None


# ---------------------------------------------------------------------------
# VesselTracker — available and name
# ---------------------------------------------------------------------------


class TestVesselTrackerAvailable:
    """Tests for the available property on MarineTrafficVesselTracker."""

    def test_available_when_vessel_present(self) -> None:
        vessel = _make_vessel()
        tracker = _make_tracker(vessel)
        assert tracker.available is True

    def test_unavailable_when_vessel_absent(self) -> None:
        tracker = _make_tracker(None)
        assert tracker.available is False

    def test_unavailable_when_update_failed(self) -> None:
        vessel = _make_vessel()
        tracker = _make_tracker(vessel)
        tracker.coordinator.last_update_success = False
        assert tracker.available is False


class TestVesselTrackerName:
    """Tests for the name property on MarineTrafficVesselTracker."""

    def test_name_returns_vessel_name(self) -> None:
        vessel = _make_vessel()
        tracker = _make_tracker(vessel)
        assert tracker.name == "Test Vessel"

    def test_name_fallback_when_absent(self) -> None:
        mmsi = "777666555"
        tracker = _make_tracker(None, mmsi=mmsi)
        assert tracker.name == f"Vessel {mmsi}"


# ---------------------------------------------------------------------------
# VesselTracker — icon property
# ---------------------------------------------------------------------------


class TestVesselTrackerIcon:
    """Tests for the icon property on MarineTrafficVesselTracker."""

    def test_cargo_type_returns_ship_wheel(self) -> None:
        vessel = _make_vessel(vessel_type=70)
        tracker = _make_tracker(vessel)
        assert tracker.icon == VESSEL_TYPE_ICONS[70]

    def test_unknown_type_returns_default_icon(self) -> None:
        vessel = _make_vessel(vessel_type=1234)
        tracker = _make_tracker(vessel)
        assert tracker.icon == DEFAULT_VESSEL_ICON

    def test_absent_vessel_returns_default_icon(self) -> None:
        tracker = _make_tracker(None)
        assert tracker.icon == DEFAULT_VESSEL_ICON


# ---------------------------------------------------------------------------
# VesselTracker — extra_state_attributes
# ---------------------------------------------------------------------------


class TestVesselTrackerAttributes:
    """Tests for extra_state_attributes on MarineTrafficVesselTracker."""

    def test_empty_when_vessel_absent(self) -> None:
        tracker = _make_tracker(None)
        assert tracker.extra_state_attributes == {}

    def test_data_source_in_attributes(self) -> None:
        vessel = _make_vessel(source="aishub")
        tracker = _make_tracker(vessel)
        assert tracker.extra_state_attributes[ATTR_DATA_SOURCE] == "aishub"

    def test_tracker_has_no_latitude_longitude_in_extra_attrs(self) -> None:
        """Tracker uses TrackerEntity lat/lon; they must not appear as extra attrs."""
        vessel = _make_vessel()
        tracker = _make_tracker(vessel)
        attrs = tracker.extra_state_attributes
        assert "latitude" not in attrs
        assert "longitude" not in attrs


# ---------------------------------------------------------------------------
# CountSensor — anchored vessel info
# ---------------------------------------------------------------------------


class TestCountSensorAnchoredVessels:
    """Tests for anchored_vessel_count and anchored_vessels in CountSensor."""

    def test_anchored_count_is_zero_when_no_anchored_vessels(self) -> None:
        vessel = _make_vessel()
        sensor = _make_count_sensor({vessel.mmsi: vessel}, anchored={})
        attrs = sensor.extra_state_attributes
        from custom_components.marinetraffic_tracker.const import ATTR_ANCHORED_COUNT
        assert attrs[ATTR_ANCHORED_COUNT] == 0

    def test_anchored_count_reflects_anchored_registry(self) -> None:
        """anchored_vessel_count must equal the number of anchored vessels."""
        from custom_components.marinetraffic_tracker.const import ATTR_ANCHORED_COUNT
        anchored1 = _make_vessel(mmsi="111111111", status="At Anchor")
        anchored2 = _make_vessel(mmsi="222222222", status="Moored")
        sensor = _make_count_sensor({}, anchored={
            anchored1.mmsi: anchored1,
            anchored2.mmsi: anchored2,
        })
        attrs = sensor.extra_state_attributes
        assert attrs[ATTR_ANCHORED_COUNT] == 2

    def test_anchored_vessels_list_is_present(self) -> None:
        """anchored_vessels attribute must be a list."""
        from custom_components.marinetraffic_tracker.const import ATTR_ANCHORED_VESSELS
        sensor = _make_count_sensor({}, anchored={})
        attrs = sensor.extra_state_attributes
        assert ATTR_ANCHORED_VESSELS in attrs
        assert isinstance(attrs[ATTR_ANCHORED_VESSELS], list)

    def test_anchored_vessels_list_contains_mmsi_and_name(self) -> None:
        """Each entry in anchored_vessels must include mmsi and vessel_name."""
        from custom_components.marinetraffic_tracker.const import (
            ATTR_ANCHORED_VESSELS,
            ATTR_MMSI,
            ATTR_VESSEL_NAME,
        )
        anchored = _make_vessel(mmsi="333333333", status="At Anchor")
        anchored = VesselData(
            mmsi="333333333",
            name="ANCHORED VESSEL",
            vessel_type=80,
            latitude=30.0,
            longitude=32.5,
            heading=None,
            course=None,
            speed=0.0,
            status="At Anchor",
            origin=None,
            destination=None,
            eta=None,
            last_seen=datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC),
            source="marinetraffic",
        )
        sensor = _make_count_sensor({}, anchored={anchored.mmsi: anchored})
        attrs = sensor.extra_state_attributes
        entries = attrs[ATTR_ANCHORED_VESSELS]
        assert len(entries) == 1
        assert entries[0][ATTR_MMSI] == "333333333"
        assert entries[0][ATTR_VESSEL_NAME] == "ANCHORED VESSEL"

    def test_active_vessels_not_in_anchored_list(self) -> None:
        """Active vessels must appear in the main vessels list, not anchored_vessels."""
        from custom_components.marinetraffic_tracker.const import ATTR_ANCHORED_VESSELS
        active = _make_vessel(mmsi="444444444", status="Under Way Using Engine")
        sensor = _make_count_sensor({active.mmsi: active}, anchored={})
        attrs = sensor.extra_state_attributes
        assert attrs[ATTR_ANCHORED_VESSELS] == []


# ---------------------------------------------------------------------------
# Coordinator.stale_timeout_seconds — reads options before data
# ---------------------------------------------------------------------------


class TestCoordinatorStaletimeout:
    """Tests for the stale_timeout_seconds property on MarineTrafficCoordinator."""

    def _make_entry(self, data: dict, options: dict | None = None) -> MagicMock:
        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.data = data
        entry.options = options or {}
        return entry

    def test_reads_from_data_when_options_absent(self) -> None:
        """stale_timeout_seconds should read from data when options is empty."""
        entry = self._make_entry(
            data={
                "tracking_mode": "radius",
                "latitude": 59.9,
                "longitude": 10.7,
                "radius_km": 50.0,
                "update_interval": 60,
                "stale_timeout": 1200,
            }
        )
        coordinator = MarineTrafficCoordinator(MagicMock(), entry, MagicMock())
        assert coordinator.stale_timeout_seconds == 1200

    def test_options_override_data(self) -> None:
        """Options value for stale_timeout must take precedence over data."""
        entry = self._make_entry(
            data={
                "tracking_mode": "radius",
                "latitude": 59.9,
                "longitude": 10.7,
                "radius_km": 50.0,
                "update_interval": 60,
                "stale_timeout": 1200,
            },
            options={"stale_timeout": 300},
        )
        coordinator = MarineTrafficCoordinator(MagicMock(), entry, MagicMock())
        assert coordinator.stale_timeout_seconds == 300

    def test_default_stale_timeout_when_not_configured(self) -> None:
        """When stale_timeout is absent from both data and options, default is used."""
        from custom_components.marinetraffic_tracker.const import DEFAULT_STALE_TIMEOUT
        entry = self._make_entry(
            data={
                "tracking_mode": "radius",
                "latitude": 59.9,
                "longitude": 10.7,
                "radius_km": 50.0,
                "update_interval": 60,
            }
        )
        coordinator = MarineTrafficCoordinator(MagicMock(), entry, MagicMock())
        assert coordinator.stale_timeout_seconds == DEFAULT_STALE_TIMEOUT
