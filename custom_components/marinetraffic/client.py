"""Async HTTP client for MarineTraffic public live-map data."""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

import aiohttp

from .const import MAP_ZOOM, REQUEST_TIMEOUT, USER_AGENT

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tile coordinate helpers
# ---------------------------------------------------------------------------


def _lat_lon_to_tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    """Convert a WGS-84 coordinate to OSM tile (x, y) at *zoom*."""
    lat_rad = math.radians(lat)
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int(
        (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    )
    return x, y


def _radius_to_bbox(
    lat: float, lon: float, radius_km: float
) -> tuple[float, float, float, float]:
    """Return (min_lat, min_lon, max_lat, max_lon) for *radius_km* around *lat/lon*."""
    # Approximate degree offsets
    delta_lat = radius_km / 111.0  # 1° latitude ≈ 111 km
    delta_lon = radius_km / (111.0 * math.cos(math.radians(lat)))
    return (
        lat - delta_lat,
        lon - delta_lon,
        lat + delta_lat,
        lon + delta_lon,
    )


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in kilometres."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_vessel(raw: list[Any]) -> dict[str, Any] | None:
    """Parse a single vessel row from MarineTraffic tile JSON.

    The public tile endpoint returns a list of lists.  The field order that
    has been observed in the wild is:

        [0]  MMSI
        [1]  Longitude  (×10⁻⁵ degrees, integer)
        [2]  Latitude   (×10⁻⁵ degrees, integer)
        [3]  Course     (degrees)
        [4]  Speed      (×10 knots, integer — divide by 10)
        [5]  Timestamp  (Unix UTC)
        [6]  Ship type  (AIS numeric)
        [7]  Navigation status (AIS numeric)
        [8]  Ship name
        [9]  Destination
        [10] ETA        (string, may be empty)
        [11] Callsign
        [12] IMO
        [13] Flag       (ISO 2-letter)
        [14] Heading    (degrees, 511 = unavailable)
        [15] Draught    (m)
        [16] Ship length (m)
        [17] Ship width  (m)

    MarineTraffic occasionally ships different column orders across endpoints
    and zones; we handle missing columns gracefully.
    """
    if not isinstance(raw, list) or len(raw) < 5:
        return None

    try:
        mmsi = str(raw[0])
        lon = float(raw[1]) / 100000.0
        lat = float(raw[2]) / 100000.0
        course = _safe_float(raw[3])
        speed = _safe_float(raw[4], divisor=10)
        ship_type = _safe_int(raw[6]) if len(raw) > 6 else 0
        nav_status = _safe_int(raw[7]) if len(raw) > 7 else 15
        name = str(raw[8]).strip() if len(raw) > 8 else ""
        destination = str(raw[9]).strip() if len(raw) > 9 else ""
        eta = str(raw[10]).strip() if len(raw) > 10 else ""
        callsign = str(raw[11]).strip() if len(raw) > 11 else ""
        imo = str(raw[12]).strip() if len(raw) > 12 else ""
        flag = str(raw[13]).strip() if len(raw) > 13 else ""
        heading = _safe_float(raw[14]) if len(raw) > 14 else None
        length = _safe_float(raw[16]) if len(raw) > 16 else None
    except (TypeError, ValueError, IndexError) as exc:
        _LOGGER.debug("Could not parse vessel row %s: %s", raw, exc)
        return None

    return {
        "mmsi": mmsi,
        "latitude": lat,
        "longitude": lon,
        "course": course,
        "speed_knots": speed,
        "ship_type": ship_type,
        "nav_status": nav_status,
        "name": name or mmsi,
        "destination": destination,
        "eta": eta,
        "callsign": callsign,
        "imo": imo,
        "flag": flag,
        "heading": heading if heading is not None and heading != 511 else None,
        "length": length,
    }


def _safe_float(value: Any, divisor: float = 1.0) -> float | None:
    try:
        return float(value) / divisor
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

# Headers that mimic a real Chrome browser visiting MarineTraffic.
_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.marinetraffic.com/",
    "Origin": "https://www.marinetraffic.com",
    "X-Requested-With": "XMLHttpRequest",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


class MarineTrafficClient:
    """Async client for MarineTraffic public live-map data."""

    # Base URL for the tile JSON endpoint.
    _TILE_URL = (
        "https://www.marinetraffic.com/getData/get_data_json_4"
        "/z:{zoom}/X:{x}/Y:{y}/station:0"
    )

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def get_vessels_in_radius(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
    ) -> list[dict[str, Any]]:
        """Return vessels within *radius_km* of (*latitude*, *longitude*)."""
        min_lat, min_lon, max_lat, max_lon = _radius_to_bbox(
            latitude, longitude, radius_km
        )

        # Determine which OSM tiles cover the bounding box.
        zoom = MAP_ZOOM
        x_min, y_max = _lat_lon_to_tile(min_lat, min_lon, zoom)
        x_max, y_min = _lat_lon_to_tile(max_lat, max_lon, zoom)

        # Clamp tile ranges (sanity guard against crossing ±180° antimeridian).
        x_min, x_max = sorted([x_min, x_max])
        y_min, y_max = sorted([y_min, y_max])

        # Build the list of tiles to fetch (cap at a reasonable number).
        tiles: list[tuple[int, int]] = []
        for tx in range(x_min, x_max + 1):
            for ty in range(y_min, y_max + 1):
                tiles.append((tx, ty))

        if not tiles:
            _LOGGER.warning("No tiles derived for the given area")
            return []

        # Fetch tiles concurrently.
        tasks = [self._fetch_tile(zoom, tx, ty) for tx, ty in tiles]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        seen_mmsi: set[str] = set()
        vessels: list[dict[str, Any]] = []

        for result in results:
            if isinstance(result, Exception):
                _LOGGER.debug("Tile fetch error: %s", result)
                continue
            for vessel in result:
                mmsi = vessel.get("mmsi", "")
                if mmsi in seen_mmsi:
                    continue
                seen_mmsi.add(mmsi)

                dist = _haversine_km(
                    latitude, longitude,
                    vessel["latitude"], vessel["longitude"],
                )
                if dist <= radius_km:
                    vessel["distance_km"] = round(dist, 2)
                    vessels.append(vessel)

        _LOGGER.debug(
            "Found %d unique vessels within %.1f km (tiles fetched: %d)",
            len(vessels),
            radius_km,
            len(tiles),
        )
        return vessels

    async def _fetch_tile(
        self, zoom: int, x: int, y: int
    ) -> list[dict[str, Any]]:
        """Fetch a single map tile and return parsed vessel list."""
        url = self._TILE_URL.format(zoom=zoom, x=x, y=y)
        try:
            async with self._session.get(
                url,
                headers=_HEADERS,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                ssl=False,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        except aiohttp.ClientResponseError as exc:
            _LOGGER.debug("HTTP %s fetching tile z%s/%s/%s", exc.status, zoom, x, y)
            return []
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            _LOGGER.debug("Network error fetching tile z%s/%s/%s: %s", zoom, x, y, exc)
            return []

        return self._parse_tile_response(data)

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_tile_response(data: Any) -> list[dict[str, Any]]:
        """Extract vessels from a raw tile JSON response.

        MarineTraffic returns either:
        - {"data": [[...], ...]}                (most common)
        - {"data": {"rows": [[...], ...]}}      (some regions / versions)
        - A direct list [[...], ...]
        """
        rows: list[Any] = []

        if isinstance(data, dict):
            inner = data.get("data", data)
            if isinstance(inner, dict):
                rows = inner.get("rows", [])
            elif isinstance(inner, list):
                rows = inner
        elif isinstance(data, list):
            rows = data

        vessels: list[dict[str, Any]] = []
        for row in rows:
            parsed = _parse_vessel(row)
            if parsed:
                vessels.append(parsed)
        return vessels
