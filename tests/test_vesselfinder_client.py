"""Tests for VesselFinderClient._parse_row and _parse_response."""

from __future__ import annotations

from custom_components.marinetraffic_tracker.vesselfinder_client import VesselFinderClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client() -> VesselFinderClient:
    """Return a client instance without an HTTP session (not needed for parse tests)."""
    return VesselFinderClient.__new__(VesselFinderClient)


# A minimal valid VesselFinder compact vessel row:
# [mmsi, name, lat, lon, speed, course, heading, status, type, flag, imo, callsign, length]
_BASE_ROW: list = [
    123456789,    # 0: MMSI
    "TEST VESSEL",  # 1: Name
    59.9,          # 2: Latitude
    10.7,          # 3: Longitude
    12.5,          # 4: Speed (knots)
    182.0,         # 5: Course (degrees)
    180,           # 6: Heading (degrees)
    0,             # 7: Nav status (0 = Under Way Using Engine)
    70,            # 8: Type (Cargo)
    "NO",          # 9: Flag (Norway)
    9123456,       # 10: IMO
    "LAABC",       # 11: Callsign
    225,           # 12: Length (metres)
]


# ---------------------------------------------------------------------------
# _parse_row: core fields
# ---------------------------------------------------------------------------


class TestVesselFinderParseRowCore:
    """Tests for mandatory and core optional fields."""

    def test_valid_row_returns_vessel_data(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None

    def test_mmsi_is_set(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.mmsi == "123456789"

    def test_name_is_set(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.name == "TEST VESSEL"

    def test_name_fallback_to_mmsi(self) -> None:
        client = _make_client()
        row = list(_BASE_ROW)
        row[1] = ""
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.name == "Vessel 123456789"

    def test_latitude_and_longitude(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.latitude == 59.9
        assert vessel.longitude == 10.7

    def test_speed_set(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.speed == 12.5

    def test_course_set(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.course == 182

    def test_heading_set(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.heading == 180

    def test_heading_sentinel_511_is_none(self) -> None:
        """AIS heading sentinel 511 means 'not available'."""
        client = _make_client()
        row = list(_BASE_ROW)
        row[6] = 511
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.heading is None

    def test_nav_status_mapped(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.status == "Under Way Using Engine"

    def test_vessel_type_set(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.vessel_type == 70

    def test_not_a_list_returns_none(self) -> None:
        """Non-list input must return None."""
        client = _make_client()
        assert client._parse_row({}) is None
        assert client._parse_row("string") is None

    def test_empty_list_returns_none(self) -> None:
        client = _make_client()
        assert client._parse_row([]) is None

    def test_mmsi_zero_returns_none(self) -> None:
        """MMSI of 0 is invalid and must be skipped."""
        client = _make_client()
        row = [0, "NO NAME", 59.9, 10.7, 0, 0, 511, 15, 0, "", 0, "", 0]
        assert client._parse_row(row) is None


# ---------------------------------------------------------------------------
# _parse_row: optional fields
# ---------------------------------------------------------------------------


class TestVesselFinderParseRowOptionalFields:
    """Tests for optional fields available in the compact format."""

    def test_flag_populated(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.flag == "NO"

    def test_flag_empty_is_none(self) -> None:
        client = _make_client()
        row = list(_BASE_ROW)
        row[9] = ""
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.flag is None

    def test_imo_populated(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.imo == "9123456"

    def test_imo_zero_is_none(self) -> None:
        """IMO of 0 means unknown."""
        client = _make_client()
        row = list(_BASE_ROW)
        row[10] = 0
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.imo is None

    def test_callsign_populated(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.callsign == "LAABC"

    def test_callsign_empty_is_none(self) -> None:
        client = _make_client()
        row = list(_BASE_ROW)
        row[11] = ""
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.callsign is None

    def test_length_populated(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.length == 225

    def test_length_zero_is_none(self) -> None:
        """Length of 0 means unknown."""
        client = _make_client()
        row = list(_BASE_ROW)
        row[12] = 0
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.length is None

    def test_origin_always_none(self) -> None:
        """VesselFinder compact format does not include last port."""
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.origin is None

    def test_destination_always_none(self) -> None:
        """Destination not available in VesselFinder compact format."""
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.destination is None

    def test_short_row_does_not_crash(self) -> None:
        """Rows with fewer optional fields must still parse the mandatory fields."""
        client = _make_client()
        short_row = [123456789, "VESSEL", 59.9, 10.7]
        vessel = client._parse_row(short_row)
        assert vessel is not None
        assert vessel.mmsi == "123456789"
        assert vessel.latitude == 59.9
        assert vessel.flag is None
        assert vessel.imo is None
        assert vessel.length is None


# ---------------------------------------------------------------------------
# _parse_response: envelope handling
# ---------------------------------------------------------------------------


class TestVesselFinderParseResponse:
    """Tests for the _parse_response method."""

    def test_valid_list_returns_vessels(self) -> None:
        client = _make_client()
        vessels = client._parse_response([_BASE_ROW])
        assert len(vessels) == 1
        assert vessels[0].mmsi == "123456789"

    def test_empty_list_returns_empty(self) -> None:
        client = _make_client()
        assert client._parse_response([]) == []

    def test_non_list_response_returns_empty(self) -> None:
        """Non-list responses (e.g. an error dict) must return an empty list."""
        client = _make_client()
        assert client._parse_response({}) == []
        assert client._parse_response("string") == []

    def test_multiple_vessels_parsed(self) -> None:
        client = _make_client()
        row2 = [987654321, "VESSEL TWO", 30.0, 32.5, 8.0, 90, 91, 0, 80, "DE", 0, "", 180]
        vessels = client._parse_response([_BASE_ROW, row2])
        assert len(vessels) == 2

    def test_invalid_row_is_skipped(self) -> None:
        """Invalid rows (non-list or missing MMSI) must be skipped silently."""
        client = _make_client()
        # Mix of valid and invalid rows.
        vessels = client._parse_response([_BASE_ROW, {}, [], [0, "X", 0, 0]])
        assert len(vessels) == 1
        assert vessels[0].mmsi == "123456789"

    def test_all_fields_parsed_correctly(self) -> None:
        """Verify all expected fields map correctly from VesselFinder format."""
        client = _make_client()
        vessels = client._parse_response([_BASE_ROW])
        assert len(vessels) == 1
        v = vessels[0]
        assert v.mmsi == "123456789"
        assert v.name == "TEST VESSEL"
        assert v.latitude == 59.9
        assert v.longitude == 10.7
        assert v.speed == 12.5
        assert v.course == 182
        assert v.heading == 180
        assert v.status == "Under Way Using Engine"
        assert v.vessel_type == 70
        assert v.flag == "NO"
        assert v.imo == "9123456"
        assert v.callsign == "LAABC"
        assert v.length == 225
