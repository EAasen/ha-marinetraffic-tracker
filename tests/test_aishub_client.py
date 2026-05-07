"""Tests for AISHubClient._parse_row and _parse_response."""

from __future__ import annotations

from custom_components.marinetraffic_tracker.aishub_client import AISHubClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client() -> AISHubClient:
    """Return a client instance without an HTTP session (not needed for parse tests)."""
    return AISHubClient.__new__(AISHubClient)


# A minimal valid AISHub vessel row with all common fields populated.
_BASE_ROW: dict = {
    "MMSI": 123456789,
    "NAME": "TEST VESSEL",
    "TYPE": 70,
    "LATITUDE": 59.9,
    "LONGITUDE": 10.7,
    "HEADING": 180,
    "COG": 182.0,
    "SOG": 12.5,
    "ROT": 5,
    "NAVSTAT": 0,
    "IMO": 9123456,
    "CALLSIGN": "LAABC",
    "A": 100,
    "B": 80,
    "C": 12,
    "D": 8,
    "DRAUGHT": 62,
    "DEST": "OSLO",
    "ETA": "05/15 14:00",
}


# ---------------------------------------------------------------------------
# _parse_row: core fields
# ---------------------------------------------------------------------------


class TestAISHubParseRowCore:
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

    def test_mmsi_as_integer_is_coerced(self) -> None:
        """AISHub returns MMSI as an integer; it must be converted to string."""
        client = _make_client()
        vessel = client._parse_row({**_BASE_ROW, "MMSI": 987654321})
        assert vessel is not None
        assert vessel.mmsi == "987654321"

    def test_missing_mmsi_returns_none(self) -> None:
        client = _make_client()
        assert client._parse_row({}) is None

    def test_name_is_set(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.name == "TEST VESSEL"

    def test_name_fallback_to_mmsi(self) -> None:
        client = _make_client()
        row = {**_BASE_ROW, "NAME": ""}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.name == "Vessel 123456789"

    def test_speed_set_from_sog(self) -> None:
        """AISHub uses SOG (Speed Over Ground) field."""
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.speed == 12.5

    def test_course_set_from_cog(self) -> None:
        """AISHub uses COG (Course Over Ground) field."""
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
        row = {**_BASE_ROW, "HEADING": 511}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.heading is None

    def test_vessel_type_set(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.vessel_type == 70

    def test_latitude_and_longitude(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.latitude == 59.9
        assert vessel.longitude == 10.7


# ---------------------------------------------------------------------------
# _parse_row: optional/extended fields
# ---------------------------------------------------------------------------


class TestAISHubParseRowOptionalFields:
    """Tests for optional AISHub fields."""

    def test_imo_populated(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.imo == "9123456"

    def test_imo_zero_is_none(self) -> None:
        """AISHub sends IMO=0 when the IMO number is unknown."""
        client = _make_client()
        row = {**_BASE_ROW, "IMO": 0}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.imo is None

    def test_imo_absent_is_none(self) -> None:
        client = _make_client()
        row = {k: v for k, v in _BASE_ROW.items() if k != "IMO"}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.imo is None

    def test_callsign_populated(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.callsign == "LAABC"

    def test_callsign_stripped(self) -> None:
        client = _make_client()
        row = {**_BASE_ROW, "CALLSIGN": "  LAABC  "}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.callsign == "LAABC"

    def test_callsign_empty_is_none(self) -> None:
        client = _make_client()
        row = {**_BASE_ROW, "CALLSIGN": ""}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.callsign is None

    def test_destination_populated(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.destination == "OSLO"

    def test_destination_empty_is_none(self) -> None:
        client = _make_client()
        row = {**_BASE_ROW, "DEST": ""}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.destination is None

    def test_eta_populated(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.eta == "05/15 14:00"

    def test_origin_is_always_none(self) -> None:
        """AISHub does not provide last-port information."""
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.origin is None

    def test_flag_is_always_none(self) -> None:
        """AISHub does not expose flag/country in the free API."""
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.flag is None

    def test_draught_populated(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.draught == 62.0

    def test_draught_absent_is_none(self) -> None:
        client = _make_client()
        row = {k: v for k, v in _BASE_ROW.items() if k != "DRAUGHT"}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.draught is None

    def test_beam_derived_from_c_and_d(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.beam == 20  # C(12) + D(8)

    def test_beam_absent_when_c_or_d_missing(self) -> None:
        client = _make_client()
        row = {k: v for k, v in _BASE_ROW.items() if k not in {"C", "D"}}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.beam is None

    def test_rate_of_turn_populated(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.rate_of_turn == 5

    def test_rate_of_turn_sentinel_minus_128_is_none(self) -> None:
        """AIS ROT sentinel –128 means 'no information'."""
        client = _make_client()
        row = {**_BASE_ROW, "ROT": -128}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.rate_of_turn is None

    def test_rate_of_turn_absent_is_none(self) -> None:
        client = _make_client()
        row = {k: v for k, v in _BASE_ROW.items() if k != "ROT"}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.rate_of_turn is None


# ---------------------------------------------------------------------------
# _parse_response: envelope handling
# ---------------------------------------------------------------------------


class TestAISHubParseResponse:
    """Tests for the _parse_response envelope handling."""

    def test_valid_response_returns_vessels(self) -> None:
        client = _make_client()
        raw = [{"ERROR": False, "RECORDS": 1}, [_BASE_ROW]]
        vessels = client._parse_response(raw)
        assert len(vessels) == 1
        assert vessels[0].mmsi == "123456789"

    def test_error_true_returns_empty(self) -> None:
        """AISHub error responses (ERROR: true) must return an empty list."""
        client = _make_client()
        raw = [{"ERROR": True, "ERROR_MESSAGE": "Invalid credentials"}, []]
        vessels = client._parse_response(raw)
        assert vessels == []

    def test_non_list_response_returns_empty(self) -> None:
        client = _make_client()
        assert client._parse_response({}) == []
        assert client._parse_response("string") == []

    def test_too_short_list_returns_empty(self) -> None:
        """Response with fewer than 2 elements must return empty."""
        client = _make_client()
        assert client._parse_response([]) == []
        assert client._parse_response([{"ERROR": False}]) == []

    def test_empty_vessel_list_returns_empty(self) -> None:
        client = _make_client()
        raw = [{"ERROR": False, "RECORDS": 0}, []]
        vessels = client._parse_response(raw)
        assert vessels == []

    def test_multiple_vessels_parsed(self) -> None:
        client = _make_client()
        row2 = {**_BASE_ROW, "MMSI": 987654321, "NAME": "VESSEL TWO"}
        raw = [{"ERROR": False, "RECORDS": 2}, [_BASE_ROW, row2]]
        vessels = client._parse_response(raw)
        assert len(vessels) == 2

    def test_row_without_mmsi_is_skipped(self) -> None:
        client = _make_client()
        bad_row = {k: v for k, v in _BASE_ROW.items() if k != "MMSI"}
        raw = [{"ERROR": False, "RECORDS": 2}, [bad_row, _BASE_ROW]]
        vessels = client._parse_response(raw)
        assert len(vessels) == 1
        assert vessels[0].mmsi == "123456789"

    def test_all_fields_parsed_correctly(self) -> None:
        """All expected fields should map correctly from AISHub format."""
        client = _make_client()
        raw = [{"ERROR": False, "RECORDS": 1}, [_BASE_ROW]]
        vessels = client._parse_response(raw)
        assert len(vessels) == 1
        v = vessels[0]
        assert v.mmsi == "123456789"
        assert v.name == "TEST VESSEL"
        assert v.vessel_type == 70
        assert v.latitude == 59.9
        assert v.longitude == 10.7
        assert v.heading == 180
        assert v.course == 182
        assert v.speed == 12.5
        assert v.status == "Under Way Using Engine"
        assert v.destination == "OSLO"
        assert v.eta == "05/15 14:00"
        assert v.imo == "9123456"
        assert v.callsign == "LAABC"
        assert v.beam == 20
        assert v.draught == 62.0
        assert v.rate_of_turn == 5
