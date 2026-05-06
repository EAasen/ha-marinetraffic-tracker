"""Tests for MarineTrafficClient._parse_row and _nav_status_to_str."""

from __future__ import annotations

from custom_components.marinetraffic_tracker.client import (
    MarineTrafficClient,
    VesselData,
    _nav_status_to_str,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client() -> MarineTrafficClient:
    """Return a client instance without an HTTP session (not needed for parse tests)."""
    return MarineTrafficClient.__new__(MarineTrafficClient)


_BASE_ROW: dict = {
    "MMSI": "123456789",
    "SHIPNAME": "TEST VESSEL",
    "SHIPTYPE": 70,
    "LAT": 59.9,
    "LON": 10.7,
    "HEADING": 90,
    "COURSE": 91,
    "SPEED": 12.5,
    "NAVSTAT": 0,
    "LASTPORT": "OSLO",
    "DESTINATION": "ROTTERDAM",
    "ETA_CALC": "2026-05-15 14:00",
    "IMO": "9123456",
}


# ---------------------------------------------------------------------------
# _parse_row: existing fields
# ---------------------------------------------------------------------------


class TestParseRowCore:
    """Tests for the mandatory and previously-supported optional fields."""

    def test_valid_row_returns_vessel_data(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert isinstance(vessel, VesselData)

    def test_mmsi_is_set(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.mmsi == "123456789"

    def test_missing_mmsi_returns_none(self) -> None:
        client = _make_client()
        assert client._parse_row({}) is None
        assert client._parse_row({"MMSI": ""}) is None
        assert client._parse_row({"MMSI": "   "}) is None

    def test_shipname_fallback_to_mmsi(self) -> None:
        client = _make_client()
        row = {**_BASE_ROW, "SHIPNAME": ""}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.name == "Vessel 123456789"

    def test_imo_populated(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.imo == "9123456"

    def test_imo_absent_is_none(self) -> None:
        client = _make_client()
        row = {k: v for k, v in _BASE_ROW.items() if k != "IMO"}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.imo is None


# ---------------------------------------------------------------------------
# _parse_row: newly-populated fields (flag, callsign, length)
# ---------------------------------------------------------------------------


class TestParseRowNewFields:
    """Tests for flag, callsign, and length fields added to _parse_row."""

    def test_flag_populated_when_present(self) -> None:
        client = _make_client()
        row = {**_BASE_ROW, "FLAG": "NO"}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.flag == "NO"

    def test_flag_stripped_of_whitespace(self) -> None:
        client = _make_client()
        row = {**_BASE_ROW, "FLAG": "  NO  "}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.flag == "NO"

    def test_flag_absent_is_none(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.flag is None

    def test_flag_empty_string_is_none(self) -> None:
        client = _make_client()
        row = {**_BASE_ROW, "FLAG": ""}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.flag is None

    def test_callsign_populated_when_present(self) -> None:
        client = _make_client()
        row = {**_BASE_ROW, "CALLSIGN": "LAABC"}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.callsign == "LAABC"

    def test_callsign_stripped_of_whitespace(self) -> None:
        client = _make_client()
        row = {**_BASE_ROW, "CALLSIGN": "  LAABC  "}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.callsign == "LAABC"

    def test_callsign_absent_is_none(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.callsign is None

    def test_callsign_empty_string_is_none(self) -> None:
        client = _make_client()
        row = {**_BASE_ROW, "CALLSIGN": ""}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.callsign is None

    def test_length_populated_when_present(self) -> None:
        client = _make_client()
        row = {**_BASE_ROW, "LENGTH": 225}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.length == 225

    def test_length_as_string_is_coerced(self) -> None:
        """LENGTH coming in as a string (e.g. "225") must still be an int."""
        client = _make_client()
        row = {**_BASE_ROW, "LENGTH": "225"}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.length == 225

    def test_length_absent_is_none(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.length is None

    def test_length_invalid_value_is_none(self) -> None:
        """A non-numeric LENGTH must not crash; it should fall back to None."""
        client = _make_client()
        row = {**_BASE_ROW, "LENGTH": "N/A"}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.length is None

    def test_all_new_fields_populated_together(self) -> None:
        """All three new fields parse correctly in a single row."""
        client = _make_client()
        row = {**_BASE_ROW, "FLAG": "GB", "CALLSIGN": "GBXYZ", "LENGTH": 180}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.flag == "GB"
        assert vessel.callsign == "GBXYZ"
        assert vessel.length == 180


# ---------------------------------------------------------------------------
# _parse_row: draught, rate_of_turn, and beam fields
# ---------------------------------------------------------------------------


class TestParseRowAisExtendedFields:
    """Tests for draught, rate_of_turn, and beam fields added to _parse_row."""

    def test_draught_populated_when_present(self) -> None:
        client = _make_client()
        row = {**_BASE_ROW, "DRAUGHT": 62}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.draught == 62.0

    def test_draught_as_string_is_coerced(self) -> None:
        client = _make_client()
        row = {**_BASE_ROW, "DRAUGHT": "8.5"}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.draught == 8.5

    def test_draught_absent_is_none(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.draught is None

    def test_draught_invalid_value_is_none(self) -> None:
        client = _make_client()
        row = {**_BASE_ROW, "DRAUGHT": "N/A"}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.draught is None

    def test_rate_of_turn_populated_when_present(self) -> None:
        client = _make_client()
        row = {**_BASE_ROW, "ROT": 5}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.rate_of_turn == 5

    def test_rate_of_turn_negative_value(self) -> None:
        client = _make_client()
        row = {**_BASE_ROW, "ROT": -10}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.rate_of_turn == -10

    def test_rate_of_turn_sentinel_minus_128_is_none(self) -> None:
        """AIS sentinel –128 means 'no turn information'; must map to None."""
        client = _make_client()
        row = {**_BASE_ROW, "ROT": -128}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.rate_of_turn is None

    def test_rate_of_turn_absent_is_none(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.rate_of_turn is None

    def test_rate_of_turn_invalid_value_is_none(self) -> None:
        client = _make_client()
        row = {**_BASE_ROW, "ROT": "N/A"}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.rate_of_turn is None

    def test_beam_derived_from_c_and_d(self) -> None:
        client = _make_client()
        row = {**_BASE_ROW, "C": 12, "D": 8}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.beam == 20

    def test_beam_as_strings_is_coerced(self) -> None:
        client = _make_client()
        row = {**_BASE_ROW, "C": "15", "D": "10"}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.beam == 25

    def test_beam_absent_when_c_missing(self) -> None:
        client = _make_client()
        row = {**_BASE_ROW, "D": 8}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.beam is None

    def test_beam_absent_when_d_missing(self) -> None:
        client = _make_client()
        row = {**_BASE_ROW, "C": 12}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.beam is None

    def test_beam_absent_when_both_missing(self) -> None:
        client = _make_client()
        vessel = client._parse_row(_BASE_ROW)
        assert vessel is not None
        assert vessel.beam is None

    def test_beam_invalid_value_is_none(self) -> None:
        client = _make_client()
        row = {**_BASE_ROW, "C": "N/A", "D": 8}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.beam is None

    def test_all_three_fields_populated_together(self) -> None:
        """All three new AIS fields parse correctly in a single row."""
        client = _make_client()
        row = {**_BASE_ROW, "DRAUGHT": 55, "ROT": 3, "C": 10, "D": 12}
        vessel = client._parse_row(row)
        assert vessel is not None
        assert vessel.draught == 55.0
        assert vessel.rate_of_turn == 3
        assert vessel.beam == 22


# ---------------------------------------------------------------------------
# _nav_status_to_str: full code coverage (0–15)
# ---------------------------------------------------------------------------


class TestNavStatusToStr:
    """Tests for all 16 AIS navigational status codes."""

    def test_code_0_under_way_engine(self) -> None:
        assert _nav_status_to_str(0) == "Under Way Using Engine"

    def test_code_1_at_anchor(self) -> None:
        assert _nav_status_to_str(1) == "At Anchor"

    def test_code_2_not_under_command(self) -> None:
        assert _nav_status_to_str(2) == "Not Under Command"

    def test_code_3_restricted_manoeuvrability(self) -> None:
        assert _nav_status_to_str(3) == "Restricted Manoeuvrability"

    def test_code_4_constrained_by_draught(self) -> None:
        assert _nav_status_to_str(4) == "Constrained By Draught"

    def test_code_5_moored(self) -> None:
        assert _nav_status_to_str(5) == "Moored"

    def test_code_6_aground(self) -> None:
        assert _nav_status_to_str(6) == "Aground"

    def test_code_7_fishing(self) -> None:
        assert _nav_status_to_str(7) == "Engaged In Fishing"

    def test_code_8_under_way_sailing(self) -> None:
        assert _nav_status_to_str(8) == "Under Way Sailing"

    def test_code_9_high_speed_craft(self) -> None:
        result = _nav_status_to_str(9)
        assert result is not None
        assert result != ""

    def test_code_10_wing_in_ground(self) -> None:
        result = _nav_status_to_str(10)
        assert result is not None
        assert result != ""

    def test_code_11_reserved(self) -> None:
        result = _nav_status_to_str(11)
        assert result is not None

    def test_code_12_reserved(self) -> None:
        result = _nav_status_to_str(12)
        assert result is not None

    def test_code_13_reserved(self) -> None:
        result = _nav_status_to_str(13)
        assert result is not None

    def test_code_14_ais_sart(self) -> None:
        """Code 14 (AIS-SART emergency) must return a non-None string."""
        result = _nav_status_to_str(14)
        assert result is not None
        assert "SART" in result or "AIS" in result or "MOB" in result or "EPIRB" in result

    def test_code_15_undefined(self) -> None:
        result = _nav_status_to_str(15)
        assert result is not None

    def test_none_input_returns_none(self) -> None:
        assert _nav_status_to_str(None) is None

    def test_invalid_string_returns_none(self) -> None:
        assert _nav_status_to_str("not_a_number") is None

    def test_out_of_range_code_returns_none(self) -> None:
        assert _nav_status_to_str(99) is None

    def test_string_digit_is_coerced(self) -> None:
        """The function must accept a string representation of a valid code."""
        assert _nav_status_to_str("0") == "Under Way Using Engine"
        assert _nav_status_to_str("5") == "Moored"


# ---------------------------------------------------------------------------
# _parse_response: envelope parsing
# ---------------------------------------------------------------------------


class TestParseResponse:
    """Tests for the _parse_response envelope handling."""

    def test_data_rows_envelope(self) -> None:
        """Primary envelope {"data": {"rows": [...]}} returns vessels."""
        client = _make_client()
        raw = {"data": {"rows": [_BASE_ROW]}}
        vessels = client._parse_response(raw)
        assert len(vessels) == 1
        assert vessels[0].mmsi == "123456789"

    def test_flat_rows_envelope(self) -> None:
        """Fallback envelope {"rows": [...]} also returns vessels."""
        client = _make_client()
        raw = {"rows": [_BASE_ROW]}
        vessels = client._parse_response(raw)
        assert len(vessels) == 1
        assert vessels[0].mmsi == "123456789"

    def test_non_dict_response_returns_empty(self) -> None:
        """A non-dict response (e.g. a list) yields an empty result."""
        client = _make_client()
        assert client._parse_response([]) == []
        assert client._parse_response("string") == []

    def test_empty_rows_returns_empty(self) -> None:
        """An empty rows list yields an empty result."""
        client = _make_client()
        assert client._parse_response({"data": {"rows": []}}) == []
        assert client._parse_response({"rows": []}) == []

    def test_missing_rows_key_returns_empty(self) -> None:
        """A dict without 'rows' yields an empty result."""
        client = _make_client()
        assert client._parse_response({}) == []
        assert client._parse_response({"data": {}}) == []

    def test_multiple_vessels_parsed(self) -> None:
        """All valid rows in the envelope are returned."""
        client = _make_client()
        row2 = {**_BASE_ROW, "MMSI": "987654321", "SHIPNAME": "VESSEL TWO"}
        raw = {"data": {"rows": [_BASE_ROW, row2]}}
        vessels = client._parse_response(raw)
        assert len(vessels) == 2

    def test_row_without_mmsi_is_skipped(self) -> None:
        """Rows missing MMSI are silently dropped; valid rows still returned."""
        client = _make_client()
        bad_row: dict = {k: v for k, v in _BASE_ROW.items() if k != "MMSI"}
        raw = {"data": {"rows": [bad_row, _BASE_ROW]}}
        vessels = client._parse_response(raw)
        assert len(vessels) == 1
        assert vessels[0].mmsi == "123456789"

    def test_all_confirmed_field_names_parsed(self) -> None:
        """All field names confirmed against the MarineTraffic live-map endpoint parse correctly."""
        client = _make_client()
        row = {
            "MMSI": "123456789",
            "SHIPNAME": "MY VESSEL",
            "SHIPTYPE": 70,
            "LAT": 59.123,
            "LON": 10.456,
            "HEADING": 180,
            "COURSE": 182,
            "SPEED": 12.5,
            "NAVSTAT": 0,
            "LASTPORT": "HAMBURG",
            "DESTINATION": "OSLO",
            "ETA_CALC": "2024-01-15 08:00",
            "IMO": "9876543",
            "FLAG": "DE",
            "CALLSIGN": "DABC",
            "LENGTH": 180,
            "DRAUGHT": 62,
            "ROT": 5,
            "C": 12,
            "D": 8,
        }
        vessels = client._parse_response({"data": {"rows": [row]}})
        assert len(vessels) == 1
        v = vessels[0]
        assert v.mmsi == "123456789"
        assert v.name == "MY VESSEL"
        assert v.vessel_type == 70
        assert v.latitude == 59.123
        assert v.longitude == 10.456
        assert v.heading == 180
        assert v.course == 182
        assert v.speed == 12.5
        assert v.status == "Under Way Using Engine"
        assert v.origin == "HAMBURG"
        assert v.destination == "OSLO"
        assert v.eta == "2024-01-15 08:00"
        assert v.imo == "9876543"
        assert v.flag == "DE"
        assert v.callsign == "DABC"
        assert v.length == 180
        assert v.draught == 62.0
        assert v.rate_of_turn == 5
        assert v.beam == 20  # C(12) + D(8)
