"""VesselFinder live-map HTTP client.

VesselFinder (https://www.vesselfinder.com/) provides a public live map
that can be used as a fallback when MarineTraffic is unavailable.  Like
MarineTraffic, this integration observes the internal endpoint used by the
VesselFinder web application and is therefore subject to change without
notice.

Use this as a fallback/secondary source, not as the primary source when
reliability is critical.  VesselFinder's geographic coverage and rate-
limiting policies differ from MarineTraffic, which makes it a useful
complement.

SCHEMA NOTE:
  The live-map endpoint observed at::

    GET https://www.vesselfinder.com/vesselsonmap
        ?bbox={west},{south},{east},{north}
        &zoom={zoom}
        &mmsi=0
        &show_names=1
        &filters=0

  Response envelope (compact list encoding)::

    Each vessel is a list::

      [
        mmsi,       # int — MMSI number
        name,       # str — vessel name
        lat,        # float — latitude
        lon,        # float — longitude
        speed,      # float — speed over ground (knots)
        course,     # float — course over ground (degrees)
        heading,    # int — true heading (degrees; 511 = not available)
        status,     # int — AIS navigational status code (0–15)
        type,       # int — AIS ship type code
        flag,       # str — ISO 3166-1 alpha-2 flag code
        imo,        # int — IMO number (0 when unknown)
        callsign,   # str — radio callsign
        length,     # int — vessel length in metres (0 when unknown)
        ...         # additional fields may be present and are ignored
      ]

  Update ``_parse_row`` if VesselFinder changes their response format.
"""

from __future__ import annotations

import logging
import math
import secrets
from json import JSONDecodeError, loads
from typing import Any

import aiohttp

from .client import VesselData, _haversine_km, _nav_status_to_str

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
_GRID_URLS: tuple[str, ...] = (
    (
        "https://www.vesselfinder.com/vesselsonmap"
        "?bbox={west},{south},{east},{north}"
        "&zoom={zoom}&mmsi=0&show_names=1&filters=0&pv=6"
    ),
    (
        "https://www.vesselfinder.com/vesselsonmap"
        "?pv=6&lat1={south}&lat2={north}&lon1={west}&lon2={east}&zoom={zoom}"
    ),
)

# ---------------------------------------------------------------------------
# Browser impersonation — rotate through realistic User-Agent strings.
# ---------------------------------------------------------------------------
_USER_AGENTS: list[str] = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    ("Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"),
]

_BASE_HEADERS: dict[str, str] = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Referer": "https://www.vesselfinder.com/",
    "Origin": "https://www.vesselfinder.com",
    "X-Requested-With": "XMLHttpRequest",
    "Connection": "keep-alive",
}

_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)
_EMPTY_RESULT_HTTP_STATUSES: frozenset[int] = frozenset({403, 404, 410})

# AIS heading sentinel — 511 means "not available".
_HEADING_NOT_AVAILABLE = 511

# Response field indices (compact list format).
_IDX_MMSI = 0
_IDX_NAME = 1
_IDX_LAT = 2
_IDX_LON = 3
_IDX_SPEED = 4
_IDX_COURSE = 5
_IDX_HEADING = 6
_IDX_STATUS = 7
_IDX_TYPE = 8
_IDX_FLAG = 9
_IDX_IMO = 10
_IDX_CALLSIGN = 11
_IDX_LENGTH = 12


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class VesselFinderClient:
    """Async HTTP client for the VesselFinder live-map data endpoint.

    Usage::

        async with aiohttp.ClientSession() as session:
            client = VesselFinderClient(session)
            vessels = await client.get_vessels_in_radius(59.9, 10.7, 50)
    """

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_vessels_in_radius(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
    ) -> list[VesselData]:
        """Return vessels within *radius_km* of (*latitude*, *longitude*).

        Converts the circle to a bounding box for the API query, then
        applies a Haversine post-filter for precise circle accuracy.
        """
        _LOGGER.debug(
            "VesselFinder: fetching vessels within %.1f km of tracking centre",
            radius_km,
        )

        delta_lat = radius_km / 111.0
        cos_lat = math.cos(math.radians(latitude))
        delta_lon = radius_km / (111.0 * max(cos_lat, 0.01))

        zoom = _radius_to_zoom(radius_km)
        all_vessels = await self.get_vessels_in_box(
            north=latitude + delta_lat,
            east=longitude + delta_lon,
            south=latitude - delta_lat,
            west=longitude - delta_lon,
            zoom=zoom,
        )

        in_radius = [
            v
            for v in all_vessels
            if _haversine_km(latitude, longitude, v.latitude, v.longitude) <= radius_km
        ]
        _LOGGER.debug(
            "VesselFinder Haversine filter: %d → %d vessels within %.1f km",
            len(all_vessels),
            len(in_radius),
            radius_km,
        )
        return in_radius

    async def get_vessels_in_box(
        self,
        north: float,
        east: float,
        south: float,
        west: float,
        zoom: int = 10,
    ) -> list[VesselData]:
        """Return vessels within the given geographic bounding box."""
        user_agent = secrets.choice(_USER_AGENTS)
        headers = {**_BASE_HEADERS, "User-Agent": user_agent}
        urls = [
            template.format(
                north=round(north, 4),
                east=round(east, 4),
                south=round(south, 4),
                west=round(west, 4),
                zoom=zoom,
            )
            for template in _GRID_URLS
        ]

        last_http_error: aiohttp.ClientResponseError | None = None
        for idx, url in enumerate(urls):
            _LOGGER.debug("GET VesselFinder %s", url)
            try:
                async with self._session.get(
                    url,
                    headers=headers,
                    timeout=_REQUEST_TIMEOUT,
                ) as resp:
                    _LOGGER.debug("VesselFinder responded with HTTP %s", resp.status)
                    if resp.status == 429:
                        _LOGGER.warning(
                            "VesselFinder returned 429 Too Many Requests — "
                            "consider increasing CONF_UPDATE_INTERVAL"
                        )
                        return []
                    if resp.status in _EMPTY_RESULT_HTTP_STATUSES:
                        _LOGGER.warning(
                            "VesselFinder endpoint returned HTTP %s for %s",
                            resp.status,
                            url,
                        )
                        if idx < len(urls) - 1:
                            continue
                        return []

                    resp.raise_for_status()
                    return self._parse_response(await _read_json_or_text(resp))
            except aiohttp.ClientResponseError as exc:
                last_http_error = exc
                _LOGGER.error("VesselFinder returned HTTP %s for %s", exc.status, url)
                if exc.status in _EMPTY_RESULT_HTTP_STATUSES and idx < len(urls) - 1:
                    continue
                if exc.status in _EMPTY_RESULT_HTTP_STATUSES:
                    return []
                raise
            except aiohttp.ClientError as exc:
                _LOGGER.error("Network error fetching VesselFinder data: %s", exc)
                raise
            except Exception as exc:  # noqa: BLE001
                _LOGGER.error("Unexpected error during VesselFinder fetch: %s", exc)
                raise

        if last_http_error is not None:
            raise last_http_error
        return []

    # ------------------------------------------------------------------
    # EXTENSION POINT — parser
    # Update ``_parse_response`` / ``_parse_row`` when VesselFinder changes
    # their response format.
    # ------------------------------------------------------------------

    def _parse_response(self, raw: Any) -> list[VesselData]:
        """Parse the raw VesselFinder response into a list of :class:`VesselData`.

        VesselFinder returns a list of compact vessel arrays.  Returns an empty
        list when the response format is unexpected or the area is empty.
        """
        if isinstance(raw, str):
            return self._parse_text_response(raw)

        vessels: list[VesselData] = []

        if not isinstance(raw, list):
            _LOGGER.debug(
                "Unexpected VesselFinder response type: %s (expected list)",
                type(raw).__name__,
            )
            return vessels

        if not raw:
            _LOGGER.debug("VesselFinder returned an empty vessel list (empty area)")
            return vessels

        _LOGGER.debug("Parsing %d VesselFinder vessel row(s)", len(raw))

        for row in raw:
            try:
                vessel = self._parse_row(row)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug("Failed to parse VesselFinder vessel row %s: %s", row, exc)
                continue
            if vessel is not None:
                vessels.append(vessel)

        _LOGGER.debug("Parsed %d vessel(s) from VesselFinder response", len(vessels))
        return vessels

    def _parse_text_response(self, raw: str) -> list[VesselData]:
        """Parse text/tab-delimited VesselFinder map responses."""
        vessels: list[VesselData] = []
        for line in raw.splitlines():
            row = line.strip()
            if not row:
                continue

            columns = row.split("\t")
            vessel = self._parse_tab_row(columns)
            if vessel is not None:
                vessels.append(vessel)

        _LOGGER.debug("Parsed %d vessel(s) from VesselFinder text response", len(vessels))
        return vessels

    def _parse_tab_row(self, row: list[str]) -> VesselData | None:
        """Parse a tab-delimited VesselFinder row."""
        if len(row) < 6:
            return None

        try:
            lat = float(row[0]) / 600000.0
            lon = float(row[1]) / 600000.0
        except (TypeError, ValueError):
            lat = None
            lon = None

        if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
            try:
                mmsi = str(int(row[5])).strip()
            except (TypeError, ValueError):
                return None

            if not mmsi or mmsi == "0":
                return None

            course: int | None = None
            try:
                course = int(float(row[2])) if len(row) > 2 and row[2] else None
            except (TypeError, ValueError):
                course = None

            speed: float | None = None
            try:
                speed = float(row[3]) if len(row) > 3 and row[3] else None
            except (TypeError, ValueError):
                speed = None

            heading: int | None = None
            try:
                if len(row) > 4 and row[4]:
                    heading_raw = int(float(row[4]))
                    heading = None if heading_raw == _HEADING_NOT_AVAILABLE else heading_raw
            except (TypeError, ValueError):
                heading = None

            name = str(row[7]).strip() if len(row) > 7 and row[7].strip() else f"Vessel {mmsi}"

            return VesselData(
                mmsi=mmsi,
                name=name,
                vessel_type=0,
                latitude=lat,
                longitude=lon,
                heading=heading,
                course=course,
                speed=speed,
                status=None,
                origin=None,
                destination=None,
                eta=None,
                source="vesselfinder",
            )

        first_column = row[0].strip()
        if first_column.isdigit() and len(first_column) >= 7:
            return self._parse_row(row)

        return None

    def _parse_row(self, row: Any) -> VesselData | None:
        """Parse a single VesselFinder vessel list into a :class:`VesselData`.

        Returns ``None`` when the row is missing the mandatory MMSI field or
        is not in the expected list format.
        """
        if not isinstance(row, list) or len(row) < 2:
            _LOGGER.debug("VesselFinder row is not a non-empty list: %s", row)
            return None

        mmsi = str(row[_IDX_MMSI]).strip() if len(row) > _IDX_MMSI else ""
        if not mmsi or mmsi == "0":
            return None

        raw_name = str(row[_IDX_NAME]).strip() if len(row) > _IDX_NAME else ""
        name = raw_name or f"Vessel {mmsi}"

        lat = float(row[_IDX_LAT]) if len(row) > _IDX_LAT else 0.0
        lon = float(row[_IDX_LON]) if len(row) > _IDX_LON else 0.0

        raw_speed = row[_IDX_SPEED] if len(row) > _IDX_SPEED else None
        speed: float | None = None
        try:
            speed = float(raw_speed) if raw_speed is not None else None
        except (ValueError, TypeError):
            speed = None

        raw_course = row[_IDX_COURSE] if len(row) > _IDX_COURSE else None
        course: int | None = None
        try:
            course = int(float(raw_course)) if raw_course is not None else None
        except (ValueError, TypeError):
            course = None

        raw_heading = row[_IDX_HEADING] if len(row) > _IDX_HEADING else None
        heading: int | None = None
        try:
            if raw_heading is not None:
                h = int(raw_heading)
                heading = None if h == _HEADING_NOT_AVAILABLE else h
        except (ValueError, TypeError):
            heading = None

        raw_status = row[_IDX_STATUS] if len(row) > _IDX_STATUS else None
        status = _nav_status_to_str(raw_status)

        vessel_type = 0
        try:
            vessel_type = int(row[_IDX_TYPE]) if len(row) > _IDX_TYPE else 0
        except (ValueError, TypeError):
            vessel_type = 0

        flag: str | None = None
        if len(row) > _IDX_FLAG:
            raw_flag = str(row[_IDX_FLAG]).strip()
            flag = raw_flag if raw_flag else None

        imo: str | None = None
        if len(row) > _IDX_IMO:
            try:
                imo_int = int(row[_IDX_IMO])
                imo = str(imo_int) if imo_int > 0 else None
            except (ValueError, TypeError):
                imo = None

        callsign: str | None = None
        if len(row) > _IDX_CALLSIGN:
            raw_cs = str(row[_IDX_CALLSIGN]).strip()
            callsign = raw_cs if raw_cs else None

        length: int | None = None
        if len(row) > _IDX_LENGTH:
            try:
                length_int = int(row[_IDX_LENGTH])
                length = length_int if length_int > 0 else None
            except (ValueError, TypeError):
                length = None

        return VesselData(
            mmsi=mmsi,
            name=name,
            vessel_type=vessel_type,
            latitude=lat,
            longitude=lon,
            heading=heading,
            course=course,
            speed=speed,
            status=status,
            origin=None,  # VesselFinder compact format does not include last port
            destination=None,  # destination not available in compact format
            eta=None,  # ETA not available in compact format
            imo=imo,
            flag=flag,
            callsign=callsign,
            length=length,
            source="vesselfinder",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _radius_to_zoom(radius_km: float) -> int:
    """Return a map zoom level appropriate for *radius_km* (clamped 4–14)."""
    if radius_km <= 0:
        return 10
    zoom = round(14.0 - math.log2(radius_km))
    return max(4, min(14, zoom))


async def _read_json_or_text(resp: aiohttp.ClientResponse) -> Any:
    """Return JSON-decoded content, falling back to raw text."""
    try:
        return await resp.json(content_type=None)
    except (JSONDecodeError, aiohttp.ContentTypeError):
        text = await resp.text()
        try:
            return loads(text)
        except JSONDecodeError:
            return text
