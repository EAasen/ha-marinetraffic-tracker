"""Tests for entity_picture support in MarineTraffic Tracker vessel entities."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, PropertyMock

import pytest

from custom_components.marinetraffic_tracker.client import VesselData
from custom_components.marinetraffic_tracker.const import vessel_photo_url
from custom_components.marinetraffic_tracker.device_tracker import (
    MarineTrafficVesselTracker,
)
from custom_components.marinetraffic_tracker.sensor import MarineTrafficVesselSensor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vessel(
    mmsi: str = "123456789",
    destination: str | None = None,
    eta: str | None = None,
) -> VesselData:
    """Return a minimal :class:`VesselData` for use in tests."""
    return VesselData(
        mmsi=mmsi,
        name="Test Vessel",
        vessel_type=70,
        latitude=59.0,
        longitude=10.0,
        heading=None,
        course=None,
        speed=None,
        status="Under Way Using Engine",
        origin=None,
        destination=destination,
        eta=eta,
        last_seen=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


def _make_coordinator(vessel: VesselData | None) -> MagicMock:
    """Return a mocked coordinator whose ``data`` contains *vessel* (if given)."""
    coord = MagicMock()
    coord.last_update_success = True
    if vessel is not None:
        coord.data = {vessel.mmsi: vessel}
    else:
        coord.data = {}
    return coord


def _make_sensor(coordinator: MagicMock, mmsi: str) -> MarineTrafficVesselSensor:
    """Instantiate a :class:`MarineTrafficVesselSensor` with mocked HA internals."""
    sensor = MarineTrafficVesselSensor.__new__(MarineTrafficVesselSensor)
    sensor.coordinator = coordinator
    sensor._entry_id = "test_entry"
    sensor._mmsi = mmsi
    sensor._attr_unique_id = f"test_entry_vessel_{mmsi}"
    return sensor


def _make_tracker(coordinator: MagicMock, mmsi: str) -> MarineTrafficVesselTracker:
    """Instantiate a :class:`MarineTrafficVesselTracker` with mocked HA internals."""
    tracker = MarineTrafficVesselTracker.__new__(MarineTrafficVesselTracker)
    tracker.coordinator = coordinator
    tracker._entry_id = "test_entry"
    tracker._mmsi = mmsi
    tracker._attr_unique_id = f"test_entry_tracker_{mmsi}"
    return tracker


# ---------------------------------------------------------------------------
# vessel_photo_url unit tests
# ---------------------------------------------------------------------------

class TestVesselPhotoUrl:
    """Unit tests for the ``vessel_photo_url`` helper."""

    def test_valid_mmsi_returns_url(self) -> None:
        url = vessel_photo_url("123456789")
        assert url is not None
        assert "123456789" in url
        assert url.startswith("https://")

    def test_valid_mmsi_url_contains_thumb(self) -> None:
        url = vessel_photo_url("987654321")
        assert url is not None
        assert "thumb" in url

    def test_none_mmsi_returns_none(self) -> None:
        assert vessel_photo_url(None) is None

    def test_empty_mmsi_returns_none(self) -> None:
        assert vessel_photo_url("") is None

    def test_whitespace_only_mmsi_returns_none(self) -> None:
        assert vessel_photo_url("   ") is None

    def test_non_digit_mmsi_returns_none(self) -> None:
        assert vessel_photo_url("ABCDEF") is None

    def test_alphanumeric_mmsi_returns_none(self) -> None:
        assert vessel_photo_url("123ABC") is None

    def test_mmsi_with_leading_trailing_spaces_is_accepted(self) -> None:
        """Whitespace around a valid digit-only MMSI should be stripped."""
        url = vessel_photo_url("  123456789  ")
        assert url is not None
        assert "123456789" in url


# ---------------------------------------------------------------------------
# MarineTrafficVesselSensor — entity_picture tests
# ---------------------------------------------------------------------------

class TestVesselSensorEntityPicture:
    """Verify entity_picture on MarineTrafficVesselSensor."""

    def test_valid_mmsi_produces_non_empty_url(self) -> None:
        mmsi = "123456789"
        vessel = _make_vessel(mmsi=mmsi)
        coord = _make_coordinator(vessel)
        sensor = _make_sensor(coord, mmsi)

        pic = sensor.entity_picture
        assert pic is not None
        assert len(pic) > 0
        assert mmsi in pic

    def test_missing_mmsi_returns_none(self) -> None:
        sensor = _make_sensor(_make_coordinator(None), "")
        assert sensor.entity_picture is None

    def test_non_digit_mmsi_returns_none(self) -> None:
        sensor = _make_sensor(_make_coordinator(None), "BADMMSI")
        assert sensor.entity_picture is None

    def test_entity_picture_does_not_crash_when_vessel_absent(self) -> None:
        """entity_picture must never raise even if vessel data is gone."""
        coord = _make_coordinator(None)
        sensor = _make_sensor(coord, "123456789")
        # Should return a URL (MMSI is stored on the entity, not on vessel data)
        pic = sensor.entity_picture
        assert pic is not None

    def test_optional_destination_none_does_not_break_attributes(self) -> None:
        mmsi = "111222333"
        vessel = _make_vessel(mmsi=mmsi, destination=None, eta=None)
        coord = _make_coordinator(vessel)
        sensor = _make_sensor(coord, mmsi)

        attrs = sensor.extra_state_attributes
        assert attrs["destination"] is None
        assert attrs["eta"] is None
        assert sensor.entity_picture is not None

    def test_native_value_with_optional_fields_none(self) -> None:
        mmsi = "111222333"
        vessel = _make_vessel(mmsi=mmsi, destination=None, eta=None)
        coord = _make_coordinator(vessel)
        sensor = _make_sensor(coord, mmsi)

        assert sensor.native_value == "Under Way Using Engine"


# ---------------------------------------------------------------------------
# MarineTrafficVesselTracker — entity_picture tests
# ---------------------------------------------------------------------------

class TestVesselTrackerEntityPicture:
    """Verify entity_picture on MarineTrafficVesselTracker."""

    def test_valid_mmsi_produces_non_empty_url(self) -> None:
        mmsi = "987654321"
        vessel = _make_vessel(mmsi=mmsi)
        coord = _make_coordinator(vessel)
        tracker = _make_tracker(coord, mmsi)

        pic = tracker.entity_picture
        assert pic is not None
        assert len(pic) > 0
        assert mmsi in pic

    def test_missing_mmsi_returns_none(self) -> None:
        tracker = _make_tracker(_make_coordinator(None), "")
        assert tracker.entity_picture is None

    def test_non_digit_mmsi_returns_none(self) -> None:
        tracker = _make_tracker(_make_coordinator(None), "NOTANMMSI")
        assert tracker.entity_picture is None

    def test_entity_picture_does_not_crash_when_vessel_absent(self) -> None:
        coord = _make_coordinator(None)
        tracker = _make_tracker(coord, "123456789")
        pic = tracker.entity_picture
        assert pic is not None

    def test_optional_destination_none_does_not_break_attributes(self) -> None:
        mmsi = "444555666"
        vessel = _make_vessel(mmsi=mmsi, destination=None, eta=None)
        coord = _make_coordinator(vessel)
        tracker = _make_tracker(coord, mmsi)

        attrs = tracker.extra_state_attributes
        assert attrs["destination"] is None
        assert attrs["eta"] is None
        assert tracker.entity_picture is not None

    def test_latitude_longitude_accessible(self) -> None:
        mmsi = "444555666"
        vessel = _make_vessel(mmsi=mmsi)
        coord = _make_coordinator(vessel)
        tracker = _make_tracker(coord, mmsi)

        assert tracker.latitude == 59.0
        assert tracker.longitude == 10.0
