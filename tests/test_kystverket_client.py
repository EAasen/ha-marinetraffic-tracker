"""Tests for the Kystverket / BarentsWatch client parser."""

from __future__ import annotations

from custom_components.marinetraffic_tracker.kystverket_client import KystverketClient


def _make_client() -> KystverketClient:
    """Return a client instance without a network session."""
    return KystverketClient.__new__(KystverketClient)


_BASE_ROW = {
    "mmsi": 123456789,
    "name": "TEST VESSEL",
    "shipType": 70,
    "latitude": 60.39,
    "longitude": 5.32,
    "trueHeading": 181,
    "courseOverGround": 182.4,
    "speedOverGround": 12.5,
    "navigationalStatus": 0,
    "destination": "BERGEN",
    "imoNumber": 9876543,
    "callsign": "LAABC",
    "shipLength": 120,
    "shipBreadth": 20,
    "draught": 6.2,
    "rateOfTurn": 5,
    "msgtime": "2026-05-22T20:00:00+00:00",
    "eta": "2026-05-23T09:30:00+00:00",
}


def test_parse_row_maps_core_fields() -> None:
    """Core telemetry should map to the existing vessel model."""
    client = _make_client()
    vessel = client._parse_row(_BASE_ROW)

    assert vessel is not None
    assert vessel.mmsi == "123456789"
    assert vessel.name == "TEST VESSEL"
    assert vessel.speed == 12.5
    assert vessel.heading == 181
    assert vessel.course == 182
    assert vessel.status == "Under Way Using Engine"
    assert vessel.source == "kystverket"
    assert vessel.msgtime == "2026-05-22T20:00:00+00:00"
    assert vessel.eta == "2026-05-23T09:30:00+00:00"
    assert vessel.last_seen.isoformat() == "2026-05-22T20:00:00+00:00"


def test_parse_row_requires_mmsi_and_position() -> None:
    """Rows missing required identity or coordinates should be skipped."""
    client = _make_client()
    assert client._parse_row({"latitude": 60.0, "longitude": 5.0}) is None
    assert client._parse_row({"mmsi": 123456789, "latitude": 60.0}) is None


def test_parse_row_supports_geojson_feature() -> None:
    """GeoJSON features should be flattened into vessel data."""
    client = _make_client()
    vessel = client._parse_row(
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [5.32, 60.39]},
            "properties": {
                "mmsi": 123456789,
                "name": "TEST VESSEL",
                "shipType": 70,
            },
        }
    )

    assert vessel is not None
    assert vessel.longitude == 5.32
    assert vessel.latitude == 60.39


def test_parse_response_accepts_list_payload() -> None:
    """Standard JSON array responses should be parsed into vessels."""
    client = _make_client()
    vessels = client._parse_response([_BASE_ROW])

    assert len(vessels) == 1
    assert vessels[0].destination == "BERGEN"


def test_parse_row_supports_open_positions_field_names() -> None:
    """GeoJSON/openpositions property names should map into the vessel model."""
    client = _make_client()
    vessel = client._parse_row(
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [5.32, 60.39]},
            "properties": {
                "mmsi": 123456789,
                "name": "TEST VESSEL",
                "type": 70,
                "heading": 181,
                "cog": 182.4,
                "sog": 12.5,
                "navStat": 0,
                "dest": "BERGEN",
                "imo": 9876543,
                "etaUtc": "2026-05-23T09:30:00Z",
                "timestamp": "2026-05-22T20:00:00Z",
            },
        }
    )

    assert vessel is not None
    assert vessel.heading == 181
    assert vessel.course == 182
    assert vessel.speed == 12.5
    assert vessel.destination == "BERGEN"
    assert vessel.imo == "9876543"
    assert vessel.eta == "2026-05-23T09:30:00+00:00"
    assert vessel.msgtime == "2026-05-22T20:00:00+00:00"
    assert vessel.last_seen.isoformat() == "2026-05-22T20:00:00+00:00"


def test_parse_row_derives_dimensions_from_offsets() -> None:
    """A/B/C/D-style offsets should be converted into vessel length and beam."""
    client = _make_client()
    vessel = client._parse_row(
        {
            **_BASE_ROW,
            "shipLength": None,
            "shipBreadth": None,
            "a": 70,
            "b": 50,
            "c": 10,
            "d": 10,
        }
    )

    assert vessel is not None
    assert vessel.length == 120
    assert vessel.beam == 20


def test_parse_row_derives_dimensions_from_nested_dimension_object() -> None:
    """Dimension objects from the OpenAPI schema should be handled safely."""
    client = _make_client()
    vessel = client._parse_row(
        {
            **_BASE_ROW,
            "shipLength": None,
            "shipBreadth": None,
            "dimensions": {
                "toBow": 70,
                "toStern": 50,
                "toPort": 10,
                "toStarboard": 10,
            },
        }
    )

    assert vessel is not None
    assert vessel.length == 120
    assert vessel.beam == 20


def test_parse_row_leaves_optional_barentswatch_fields_empty_when_missing() -> None:
    """Missing optional voyage/static fields should stay None without errors."""
    client = _make_client()
    vessel = client._parse_row(
        {
            "mmsi": 123456789,
            "name": "TEST VESSEL",
            "shipType": 70,
            "latitude": 60.39,
            "longitude": 5.32,
        }
    )

    assert vessel is not None
    assert vessel.destination is None
    assert vessel.eta is None
    assert vessel.imo is None
    assert vessel.callsign is None
    assert vessel.draught is None
    assert vessel.msgtime is None


def test_parse_ndjson_ignores_invalid_lines() -> None:
    """Line-delimited JSON fallback should skip malformed lines."""
    client = _make_client()
    rows = client._parse_ndjson('{"mmsi": 1, "latitude": 60, "longitude": 5}\nnot-json\n')

    assert rows == [{"mmsi": 1, "latitude": 60, "longitude": 5}]
