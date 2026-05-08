"""Tests for the HTTP layer of all three vessel data clients.

Covers:
- MarineTrafficClient.get_vessels_in_box — successful response, 429, HTTP errors,
  network errors, unexpected exceptions.
- MarineTrafficClient.get_vessels_in_radius — delegates to get_vessels_in_box and
  applies a Haversine post-filter.
- AISHubClient.get_vessels_in_box — successful response, HTTP errors, network errors.
- AISHubClient.get_vessels_in_radius — bounding-box → Haversine filter.
- VesselFinderClient.get_vessels_in_box — successful response, 429, HTTP errors.
- VesselFinderClient.get_vessels_in_radius — bounding-box → Haversine filter.
- _haversine_km helper — same-point = 0, known distances, symmetry.
- VesselFinder _radius_to_zoom — same logic as MarineTraffic, duplicated module.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.marinetraffic_tracker.aishub_client import AISHubClient
from custom_components.marinetraffic_tracker.client import (
    MarineTrafficClient,
    _haversine_km,
)
from custom_components.marinetraffic_tracker.vesselfinder_client import (
    VesselFinderClient,
)
from custom_components.marinetraffic_tracker.vesselfinder_client import (
    _radius_to_zoom as vf_radius_to_zoom,
)

# ---------------------------------------------------------------------------
# Shared mock builders
# ---------------------------------------------------------------------------

_BASE_MT_ROW: dict = {
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

_BASE_AISHUB_ROW: dict = {
    "MMSI": 123456789,
    "NAME": "TEST VESSEL",
    "TYPE": 70,
    "LATITUDE": 59.9,
    "LONGITUDE": 10.7,
    "HEADING": 180,
    "COG": 91.0,
    "SOG": 12.5,
    "NAVSTAT": 0,
}

_BASE_VF_ROW: list = [
    123456789,   # MMSI
    "TEST VESSEL",
    59.9,        # lat
    10.7,        # lon
    12.5,        # speed
    91.0,        # course
    90,          # heading
    0,           # nav status
    70,          # type
    "NO",        # flag
    9123456,     # IMO
    "LAABC",     # callsign
    225,         # length
]


def _make_response_cm(
    status: int,
    json_data: object | Exception,
    *,
    text_data: str = "",
) -> MagicMock:
    """Return an async-context-manager mock that yields an HTTP response mock."""
    resp = MagicMock()
    resp.status = status
    resp.raise_for_status = MagicMock()
    if isinstance(json_data, Exception):
        resp.json = AsyncMock(side_effect=json_data)
    else:
        resp.json = AsyncMock(return_value=json_data)
    resp.text = AsyncMock(return_value=text_data)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _make_error_response_cm(exc: Exception) -> MagicMock:
    """Return a context manager whose __aenter__ raises *exc*."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(side_effect=exc)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _make_raise_for_status_cm(status: int, exc: Exception) -> MagicMock:
    """Return a context manager that raises *exc* from raise_for_status()."""
    resp = MagicMock()
    resp.status = status
    resp.raise_for_status = MagicMock(side_effect=exc)
    resp.json = AsyncMock(return_value={})

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


# ---------------------------------------------------------------------------
# MarineTrafficClient — HTTP layer
# ---------------------------------------------------------------------------


class TestMarineTrafficHTTP:
    """Tests for MarineTrafficClient.get_vessels_in_box HTTP layer."""

    @pytest.mark.asyncio
    async def test_successful_response_returns_vessels(self) -> None:
        """A 200 response with valid JSON must return parsed vessels."""
        session = MagicMock()
        session.get = MagicMock(
            return_value=_make_response_cm(
                200, {"data": {"rows": [_BASE_MT_ROW]}}
            )
        )
        client = MarineTrafficClient(session)
        vessels = await client.get_vessels_in_box(60.0, 11.0, 59.0, 10.0)
        assert len(vessels) == 1
        assert vessels[0].mmsi == "123456789"

    @pytest.mark.asyncio
    async def test_429_response_returns_empty_list(self) -> None:
        """A 429 Too Many Requests response must return an empty list (not raise)."""
        session = MagicMock()
        resp = MagicMock()
        resp.status = 429
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=resp)
        cm.__aexit__ = AsyncMock(return_value=False)
        session.get = MagicMock(return_value=cm)

        client = MarineTrafficClient(session)
        vessels = await client.get_vessels_in_box(60.0, 11.0, 59.0, 10.0)
        assert vessels == []

    @pytest.mark.asyncio
    async def test_http_error_reraises(self) -> None:
        """A non-200/non-429 HTTP error must propagate as ClientResponseError."""
        exc = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=503,
        )
        session = MagicMock()
        session.get = MagicMock(
            return_value=_make_raise_for_status_cm(503, exc)
        )
        client = MarineTrafficClient(session)
        with pytest.raises(aiohttp.ClientResponseError):
            await client.get_vessels_in_box(60.0, 11.0, 59.0, 10.0)

    @pytest.mark.asyncio
    async def test_404_endpoint_returns_empty_list(self) -> None:
        """A dead MarineTraffic endpoint should degrade to an empty result."""
        exc = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=404,
        )
        session = MagicMock()
        session.get = MagicMock(return_value=_make_raise_for_status_cm(404, exc))
        client = MarineTrafficClient(session)
        vessels = await client.get_vessels_in_box(60.0, 11.0, 59.0, 10.0)
        assert vessels == []

    @pytest.mark.asyncio
    async def test_network_error_reraises(self) -> None:
        """A network-level ClientError must propagate."""
        exc = aiohttp.ClientError("Connection reset")
        session = MagicMock()
        session.get = MagicMock(return_value=_make_error_response_cm(exc))
        client = MarineTrafficClient(session)
        with pytest.raises(aiohttp.ClientError):
            await client.get_vessels_in_box(60.0, 11.0, 59.0, 10.0)

    @pytest.mark.asyncio
    async def test_unexpected_exception_reraises(self) -> None:
        """Any unexpected exception during fetch must propagate."""
        exc = RuntimeError("Unexpected error")
        session = MagicMock()
        session.get = MagicMock(return_value=_make_error_response_cm(exc))
        client = MarineTrafficClient(session)
        with pytest.raises(RuntimeError):
            await client.get_vessels_in_box(60.0, 11.0, 59.0, 10.0)

    @pytest.mark.asyncio
    async def test_empty_rows_returns_empty_list(self) -> None:
        """An empty rows list in a valid response must return an empty list."""
        session = MagicMock()
        session.get = MagicMock(
            return_value=_make_response_cm(200, {"data": {"rows": []}})
        )
        client = MarineTrafficClient(session)
        vessels = await client.get_vessels_in_box(60.0, 11.0, 59.0, 10.0)
        assert vessels == []

    @pytest.mark.asyncio
    async def test_source_field_is_marinetraffic(self) -> None:
        """Vessels returned by MarineTrafficClient must have source='marinetraffic'."""
        session = MagicMock()
        session.get = MagicMock(
            return_value=_make_response_cm(
                200, {"data": {"rows": [_BASE_MT_ROW]}}
            )
        )
        client = MarineTrafficClient(session)
        vessels = await client.get_vessels_in_box(60.0, 11.0, 59.0, 10.0)
        assert vessels[0].source == "marinetraffic"


class TestMarineTrafficRadius:
    """Tests for MarineTrafficClient.get_vessels_in_radius."""

    @pytest.mark.asyncio
    async def test_get_vessels_in_radius_calls_get_vessels_in_box(self) -> None:
        """get_vessels_in_radius must delegate to get_vessels_in_box."""
        session = MagicMock()
        session.get = MagicMock(
            return_value=_make_response_cm(200, {"data": {"rows": []}})
        )
        client = MarineTrafficClient(session)
        await client.get_vessels_in_radius(59.9, 10.7, 50.0)
        session.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_haversine_filter_removes_corner_vessels(self) -> None:
        """Vessels outside the circle radius must be filtered out."""
        # Place one vessel at the centre (inside) and one far away (outside).
        inside_row = {**_BASE_MT_ROW, "LAT": 59.9, "LON": 10.7}  # exactly at centre
        outside_row = {
            **_BASE_MT_ROW,
            "MMSI": "999999999",
            "LAT": 62.0,  # far north — > 50 km from 59.9
            "LON": 10.7,
        }
        session = MagicMock()
        session.get = MagicMock(
            return_value=_make_response_cm(
                200, {"data": {"rows": [inside_row, outside_row]}}
            )
        )
        client = MarineTrafficClient(session)
        vessels = await client.get_vessels_in_radius(59.9, 10.7, 50.0)
        mmsis = {v.mmsi for v in vessels}
        assert "123456789" in mmsis, "Inside vessel must be included"
        assert "999999999" not in mmsis, "Outside vessel must be excluded"

    @pytest.mark.asyncio
    async def test_all_vessels_in_radius_returned(self) -> None:
        """All vessels within the radius must appear in the result."""
        row2 = {**_BASE_MT_ROW, "MMSI": "987654321", "LAT": 59.91, "LON": 10.71}
        session = MagicMock()
        session.get = MagicMock(
            return_value=_make_response_cm(
                200, {"data": {"rows": [_BASE_MT_ROW, row2]}}
            )
        )
        client = MarineTrafficClient(session)
        vessels = await client.get_vessels_in_radius(59.9, 10.7, 50.0)
        assert len(vessels) == 2


# ---------------------------------------------------------------------------
# AISHubClient — HTTP layer
# ---------------------------------------------------------------------------


class TestAISHubHTTP:
    """Tests for AISHubClient.get_vessels_in_box HTTP layer."""

    @pytest.mark.asyncio
    async def test_successful_response_returns_vessels(self) -> None:
        """A 200 response with valid AISHub JSON must return parsed vessels."""
        raw = [{"ERROR": False, "RECORDS": 1}, [_BASE_AISHUB_ROW]]
        session = MagicMock()
        session.get = MagicMock(return_value=_make_response_cm(200, raw))
        client = AISHubClient(session, api_key="TESTKEY")
        vessels = await client.get_vessels_in_box(60.0, 11.0, 59.0, 10.0)
        assert len(vessels) == 1
        assert vessels[0].mmsi == "123456789"

    @pytest.mark.asyncio
    async def test_http_error_reraises(self) -> None:
        """An HTTP error response must propagate."""
        exc = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=500,
        )
        session = MagicMock()
        session.get = MagicMock(
            return_value=_make_raise_for_status_cm(500, exc)
        )
        client = AISHubClient(session, api_key="TESTKEY")
        with pytest.raises(aiohttp.ClientResponseError):
            await client.get_vessels_in_box(60.0, 11.0, 59.0, 10.0)

    @pytest.mark.asyncio
    async def test_network_error_reraises(self) -> None:
        """A ClientError (network) must propagate."""
        exc = aiohttp.ClientError("Timeout")
        session = MagicMock()
        session.get = MagicMock(return_value=_make_error_response_cm(exc))
        client = AISHubClient(session, api_key="TESTKEY")
        with pytest.raises(aiohttp.ClientError):
            await client.get_vessels_in_box(60.0, 11.0, 59.0, 10.0)

    @pytest.mark.asyncio
    async def test_unexpected_exception_reraises(self) -> None:
        """Any unexpected exception must propagate."""
        exc = RuntimeError("Something unexpected")
        session = MagicMock()
        session.get = MagicMock(return_value=_make_error_response_cm(exc))
        client = AISHubClient(session, api_key="TESTKEY")
        with pytest.raises(RuntimeError):
            await client.get_vessels_in_box(60.0, 11.0, 59.0, 10.0)

    @pytest.mark.asyncio
    async def test_source_field_is_aishub(self) -> None:
        """Vessels returned by AISHubClient must have source='aishub'."""
        raw = [{"ERROR": False, "RECORDS": 1}, [_BASE_AISHUB_ROW]]
        session = MagicMock()
        session.get = MagicMock(return_value=_make_response_cm(200, raw))
        client = AISHubClient(session, api_key="KEY")
        vessels = await client.get_vessels_in_box(60.0, 11.0, 59.0, 10.0)
        assert vessels[0].source == "aishub"

    @pytest.mark.asyncio
    async def test_empty_vessel_list_returns_empty(self) -> None:
        """An empty vessel list in a valid AISHub response must return empty."""
        raw = [{"ERROR": False, "RECORDS": 0}, []]
        session = MagicMock()
        session.get = MagicMock(return_value=_make_response_cm(200, raw))
        client = AISHubClient(session, api_key="KEY")
        vessels = await client.get_vessels_in_box(60.0, 11.0, 59.0, 10.0)
        assert vessels == []


class TestAISHubRadius:
    """Tests for AISHubClient.get_vessels_in_radius."""

    @pytest.mark.asyncio
    async def test_delegates_to_get_vessels_in_box(self) -> None:
        """get_vessels_in_radius must call get_vessels_in_box once."""
        raw = [{"ERROR": False, "RECORDS": 1}, [_BASE_AISHUB_ROW]]
        session = MagicMock()
        session.get = MagicMock(return_value=_make_response_cm(200, raw))
        client = AISHubClient(session, api_key="KEY")
        await client.get_vessels_in_radius(59.9, 10.7, 50.0)
        session.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_haversine_filter_applied(self) -> None:
        """Vessels outside the given radius must be filtered out."""
        inside_row = {**_BASE_AISHUB_ROW, "LATITUDE": 59.9, "LONGITUDE": 10.7}
        outside_row = {
            **_BASE_AISHUB_ROW,
            "MMSI": 999999999,
            "LATITUDE": 65.0,  # far north
            "LONGITUDE": 10.7,
        }
        raw = [{"ERROR": False, "RECORDS": 2}, [inside_row, outside_row]]
        session = MagicMock()
        session.get = MagicMock(return_value=_make_response_cm(200, raw))
        client = AISHubClient(session, api_key="KEY")
        vessels = await client.get_vessels_in_radius(59.9, 10.7, 50.0)
        mmsis = {v.mmsi for v in vessels}
        assert "123456789" in mmsis
        assert "999999999" not in mmsis


# ---------------------------------------------------------------------------
# VesselFinderClient — HTTP layer
# ---------------------------------------------------------------------------


class TestVesselFinderHTTP:
    """Tests for VesselFinderClient.get_vessels_in_box HTTP layer."""

    @pytest.mark.asyncio
    async def test_successful_response_returns_vessels(self) -> None:
        """A 200 response with valid VesselFinder compact JSON must return vessels."""
        session = MagicMock()
        session.get = MagicMock(
            return_value=_make_response_cm(200, [_BASE_VF_ROW])
        )
        client = VesselFinderClient(session)
        vessels = await client.get_vessels_in_box(60.0, 11.0, 59.0, 10.0)
        assert len(vessels) == 1
        assert vessels[0].mmsi == "123456789"

    @pytest.mark.asyncio
    async def test_text_response_returns_vessels(self) -> None:
        """A text/tab-delimited map response must be parsed successfully."""
        session = MagicMock()
        session.get = MagicMock(
            return_value=_make_response_cm(
                200,
                aiohttp.ContentTypeError(MagicMock(), ()),
                text_data="35940000\t6420000\t910\t12.5\t90\t123456789\t0\tTEST VESSEL\n",
            )
        )
        client = VesselFinderClient(session)
        vessels = await client.get_vessels_in_box(60.0, 11.0, 59.0, 10.0)
        assert len(vessels) == 1
        assert vessels[0].mmsi == "123456789"
        assert vessels[0].latitude == pytest.approx(59.9)
        assert vessels[0].longitude == pytest.approx(10.7)

    @pytest.mark.asyncio
    async def test_429_response_returns_empty_list(self) -> None:
        """A 429 Too Many Requests must return an empty list (not raise)."""
        resp = MagicMock()
        resp.status = 429
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=resp)
        cm.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.get = MagicMock(return_value=cm)

        client = VesselFinderClient(session)
        vessels = await client.get_vessels_in_box(60.0, 11.0, 59.0, 10.0)
        assert vessels == []

    @pytest.mark.asyncio
    async def test_http_error_reraises(self) -> None:
        """An HTTP error must propagate as ClientResponseError."""
        exc = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=500,
        )
        session = MagicMock()
        session.get = MagicMock(
            return_value=_make_raise_for_status_cm(500, exc)
        )
        client = VesselFinderClient(session)
        with pytest.raises(aiohttp.ClientResponseError):
            await client.get_vessels_in_box(60.0, 11.0, 59.0, 10.0)

    @pytest.mark.asyncio
    async def test_404_endpoint_returns_empty_list(self) -> None:
        """A dead VesselFinder endpoint should degrade to an empty result."""
        exc = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=404,
        )
        session = MagicMock()
        session.get = MagicMock(return_value=_make_raise_for_status_cm(404, exc))
        client = VesselFinderClient(session)
        vessels = await client.get_vessels_in_box(60.0, 11.0, 59.0, 10.0)
        assert vessels == []

    @pytest.mark.asyncio
    async def test_network_error_reraises(self) -> None:
        """A ClientError must propagate."""
        exc = aiohttp.ClientError("DNS failure")
        session = MagicMock()
        session.get = MagicMock(return_value=_make_error_response_cm(exc))
        client = VesselFinderClient(session)
        with pytest.raises(aiohttp.ClientError):
            await client.get_vessels_in_box(60.0, 11.0, 59.0, 10.0)

    @pytest.mark.asyncio
    async def test_unexpected_exception_reraises(self) -> None:
        exc = ValueError("Unexpected parse error")
        session = MagicMock()
        session.get = MagicMock(return_value=_make_error_response_cm(exc))
        client = VesselFinderClient(session)
        with pytest.raises(ValueError):  # noqa: PT011
            await client.get_vessels_in_box(60.0, 11.0, 59.0, 10.0)

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self) -> None:
        """An empty array response must return an empty list."""
        session = MagicMock()
        session.get = MagicMock(return_value=_make_response_cm(200, []))
        client = VesselFinderClient(session)
        vessels = await client.get_vessels_in_box(60.0, 11.0, 59.0, 10.0)
        assert vessels == []

    @pytest.mark.asyncio
    async def test_source_field_is_vesselfinder(self) -> None:
        """Vessels returned by VesselFinderClient must have source='vesselfinder'."""
        session = MagicMock()
        session.get = MagicMock(return_value=_make_response_cm(200, [_BASE_VF_ROW]))
        client = VesselFinderClient(session)
        vessels = await client.get_vessels_in_box(60.0, 11.0, 59.0, 10.0)
        assert vessels[0].source == "vesselfinder"


class TestVesselFinderRadius:
    """Tests for VesselFinderClient.get_vessels_in_radius."""

    @pytest.mark.asyncio
    async def test_delegates_to_get_vessels_in_box(self) -> None:
        session = MagicMock()
        session.get = MagicMock(return_value=_make_response_cm(200, []))
        client = VesselFinderClient(session)
        await client.get_vessels_in_radius(59.9, 10.7, 50.0)
        session.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_haversine_filter_applied(self) -> None:
        """Vessels outside the radius must be excluded."""
        inside_row = list(_BASE_VF_ROW)  # lat=59.9, lon=10.7 — close to centre
        outside_row = [999999999, "FAR VESSEL", 65.0, 10.7, 0, 0, 511, 15, 0, "", 0, "", 0]
        session = MagicMock()
        session.get = MagicMock(
            return_value=_make_response_cm(200, [inside_row, outside_row])
        )
        client = VesselFinderClient(session)
        vessels = await client.get_vessels_in_radius(59.9, 10.7, 50.0)
        mmsis = {v.mmsi for v in vessels}
        assert "123456789" in mmsis
        assert "999999999" not in mmsis


# ---------------------------------------------------------------------------
# _haversine_km — direct unit tests
# ---------------------------------------------------------------------------


class TestHaversineKm:
    """Tests for the _haversine_km helper in client.py."""

    def test_same_point_returns_zero(self) -> None:
        """Distance from a point to itself must be 0."""
        assert _haversine_km(59.9, 10.7, 59.9, 10.7) == pytest.approx(0.0, abs=1e-6)

    def test_result_is_non_negative(self) -> None:
        """Distance must always be non-negative."""
        assert _haversine_km(0.0, 0.0, 10.0, 10.0) >= 0

    def test_symmetry(self) -> None:
        """Distance(A→B) must equal Distance(B→A)."""
        d1 = _haversine_km(59.9, 10.7, 51.5, -0.12)
        d2 = _haversine_km(51.5, -0.12, 59.9, 10.7)
        assert d1 == pytest.approx(d2, rel=1e-9)

    def test_oslo_to_london_approx(self) -> None:
        """Oslo (59.91°N, 10.75°E) to London (51.51°N, -0.13°E) ≈ 1155 km."""
        dist = _haversine_km(59.91, 10.75, 51.51, -0.13)
        assert 1100 < dist < 1250, f"Expected ~1155 km, got {dist:.1f}"

    def test_equatorial_degree_approx_111km(self) -> None:
        """One degree of longitude on the equator is approximately 111 km."""
        dist = _haversine_km(0.0, 0.0, 0.0, 1.0)
        assert 110 < dist < 113, f"Expected ~111 km, got {dist:.1f}"

    def test_one_degree_latitude_approx_111km(self) -> None:
        """One degree of latitude is approximately 111 km."""
        dist = _haversine_km(0.0, 0.0, 1.0, 0.0)
        assert 110 < dist < 112, f"Expected ~111 km, got {dist:.1f}"

    def test_large_distance_within_reason(self) -> None:
        """Antipodal points must be close to half Earth's circumference (~20015 km)."""
        dist = _haversine_km(0.0, 0.0, 0.0, 180.0)
        assert 19900 < dist < 20200, f"Expected ~20015 km, got {dist:.1f}"

    def test_small_distance_accuracy(self) -> None:
        """A ~1 km offset in latitude should return approximately 1 km."""
        # 0.009 degrees ≈ 1 km latitude
        dist = _haversine_km(59.9, 10.7, 59.909, 10.7)
        assert 0.9 < dist < 1.1, f"Expected ~1 km, got {dist:.3f}"


# ---------------------------------------------------------------------------
# VesselFinder _radius_to_zoom
# ---------------------------------------------------------------------------


class TestVesselFinderRadiusToZoom:
    """Tests for the _radius_to_zoom helper in vesselfinder_client.py.

    This is a duplicated function; we test it independently to ensure both
    copies behave correctly.
    """

    def test_zero_radius_returns_default(self) -> None:
        assert vf_radius_to_zoom(0) == 10

    def test_negative_radius_returns_default(self) -> None:
        assert vf_radius_to_zoom(-10) == 10

    def test_small_radius_gives_high_zoom(self) -> None:
        assert vf_radius_to_zoom(5) >= 10

    def test_large_radius_gives_low_zoom(self) -> None:
        assert vf_radius_to_zoom(200) <= 7

    def test_zoom_clamped_at_minimum_4(self) -> None:
        assert vf_radius_to_zoom(100_000) == 4

    def test_zoom_clamped_at_maximum_14(self) -> None:
        assert vf_radius_to_zoom(0.001) == 14

    def test_result_is_int(self) -> None:
        assert isinstance(vf_radius_to_zoom(50), int)

    def test_monotone_zoom_decreases_with_radius(self) -> None:
        """Larger radius must give same or lower zoom."""
        pairs = [(1, 10), (10, 50), (50, 100), (100, 200)]
        for smaller, larger in pairs:
            assert vf_radius_to_zoom(larger) <= vf_radius_to_zoom(smaller)
