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


def test_parse_ndjson_ignores_invalid_lines() -> None:
    """Line-delimited JSON fallback should skip malformed lines."""
    client = _make_client()
    rows = client._parse_ndjson('{"mmsi": 1, "latitude": 60, "longitude": 5}\nnot-json\n')

    assert rows == [{"mmsi": 1, "latitude": 60, "longitude": 5}]
