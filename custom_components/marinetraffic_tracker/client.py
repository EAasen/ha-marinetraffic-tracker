"""MarineTraffic live-map HTTP client and vessel data model.

This module is the sole integration point with the external MarineTraffic
website.  All network I/O and JSON parsing lives here so that upstream
format changes only require updates to ``_parse_response`` / ``_parse_row``
without touching the coordinator or entity layers.

SCHEMA NOTE:
  The live-map endpoint is observed at:
    GET /map/getData/shipData/zoom:7/minlat:{s}/maxlat:{n}/minlon:{w}/maxlon:{e}/...
  Response envelope (dict-format rows are the currently observed schema):
    { "data": { "rows": [ {"MMSI": ..., "LAT": ..., ...}, ... ] } }
  Update ``_parse_row`` if MarineTraffic changes the field names.
"""

from __future__ import annotations

import logging
import math
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
# NOTE: This URL is derived from observing MarineTraffic's public web app.
# It is not an official API and may change without notice.  Adjust the URL
# and ``_parse_response`` together when the format changes.
_GRID_URL = (
    "https://www.marinetraffic.com/map/getData/shipData"
    "/zoom:7/minlat:{south}/maxlat:{north}/minlon:{west}/maxlon:{east}"
    "/land:1/fleet:0/mmsi:0/ext:1"
)

# ---------------------------------------------------------------------------
# Browser impersonation — rotate through realistic User-Agent strings to
# reduce fingerprinting risk and the chance of being rate-limited.
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
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0"),
]

_BASE_HEADERS: dict[str, str] = {
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

_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)


# ---------------------------------------------------------------------------
# Vessel data model
# ---------------------------------------------------------------------------
@dataclass
class VesselData:
    """Immutable snapshot of a single vessel's state.

    Fields map directly to what MarineTraffic exposes on its live map.
    Optional fields default to ``None`` when the source does not include them.
    """

    mmsi: str
    name: str
    vessel_type: int
    latitude: float
    longitude: float
    heading: int | None
    course: int | None
    speed: float | None
    status: str | None
    origin: str | None
    destination: str | None
    eta: str | None
    imo: str | None = None
    flag: str | None = None
    callsign: str | None = None
    length: int | None = None
    # Timestamp of last successful observation — updated by the coordinator.
    last_seen: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def unique_id(self) -> str:
        """Stable identifier for this vessel (MMSI is globally unique)."""
        return self.mmsi


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class MarineTrafficClient:
    """Async HTTP client for the MarineTraffic live-map data endpoint.

    Usage::

        async with aiohttp.ClientSession() as session:
            client = MarineTrafficClient(session)
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

        Steps:
        1. Convert the circle to a bounding box for the API query (fast).
        2. Fetch all vessels in that box.
        3. Post-filter with the Haversine formula for strict circle accuracy,
           eliminating vessels in the box corners that are outside the circle.
        """
        _LOGGER.debug(
            "Fetching vessels within %.1f km of configured tracking centre",
            radius_km,
        )

        delta_lat = radius_km / 111.0
        cos_lat = math.cos(math.radians(latitude))
        delta_lon = radius_km / (111.0 * max(cos_lat, 0.01))

        all_vessels = await self.get_vessels_in_box(
            north=latitude + delta_lat,
            east=longitude + delta_lon,
            south=latitude - delta_lat,
            west=longitude - delta_lon,
        )

        # Strict Haversine filter — removes corner vessels outside the circle.
        in_radius = [
            v
            for v in all_vessels
            if _haversine_km(latitude, longitude, v.latitude, v.longitude) <= radius_km
        ]

        _LOGGER.debug(
            "Haversine filter: %d → %d vessels within %.1f km radius",
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
    ) -> list[VesselData]:
        """Return vessels within the given geographic bounding box."""
        url = _GRID_URL.format(
            north=round(north, 4),
            east=round(east, 4),
            south=round(south, 4),
            west=round(west, 4),
        )

        # Rotate User-Agent on every request to reduce fingerprinting.
        user_agent = secrets.choice(_USER_AGENTS)
        headers = {**_BASE_HEADERS, "User-Agent": user_agent}
        _LOGGER.debug("GET %s", url)

        try:
            async with self._session.get(
                url,
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            ) as resp:
                _LOGGER.debug("MarineTraffic responded with HTTP %s", resp.status)
                if resp.status == 429:
                    _LOGGER.warning(
                        "MarineTraffic returned 429 Too Many Requests — "
                        "consider increasing CONF_UPDATE_INTERVAL"
                    )
                    return []
                resp.raise_for_status()
                raw = await resp.json(content_type=None)
        except aiohttp.ClientResponseError as exc:
            _LOGGER.error("MarineTraffic returned HTTP %s for %s", exc.status, url)
            raise
        except aiohttp.ClientError as exc:
            _LOGGER.error("Network error fetching MarineTraffic data: %s", exc)
            raise
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("Unexpected error during MarineTraffic fetch: %s", exc)
            raise

        return self._parse_response(raw)

    # ------------------------------------------------------------------
    # EXTENSION POINT — parser
    # Update ``_parse_response`` and ``_parse_row`` when the endpoint
    # format changes.  Nothing outside this module depends on field names.
    # ------------------------------------------------------------------

    def _parse_response(self, raw: Any) -> list[VesselData]:
        """Parse the raw API response into a list of :class:`VesselData`.

        Expected response envelope (placeholder — verify against live data)::

            {
                "data": {
                    "rows": [
                        {
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
                            "IMO": "9876543"
                        }
                    ]
                }
            }

        Returns an empty list when the area is genuinely empty **or** when
        the response format does not match — a debug log is emitted in the
        latter case so the discrepancy is visible without flooding the log.
        """
        vessels: list[VesselData] = []

        if not isinstance(raw, dict):
            _LOGGER.debug(
                "Unexpected MarineTraffic response type: %s (expected dict)",
                type(raw).__name__,
            )
            return vessels

        # Support several common envelope patterns
        rows: list | None = None
        if "data" in raw and isinstance(raw["data"], dict):
            rows = raw["data"].get("rows")
        elif "rows" in raw:
            rows = raw["rows"]

        if not rows:
            _LOGGER.debug(
                "No vessel rows in MarineTraffic response (empty area or changed response format)"
            )
            return vessels

        _LOGGER.debug("Parsing %d raw vessel row(s)", len(rows))

        for row in rows:
            try:
                vessel = self._parse_row(row)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug("Failed to parse vessel row %s: %s", row, exc)
                continue
            if vessel is not None:
                vessels.append(vessel)

        _LOGGER.debug("Parsed %d vessel(s) from MarineTraffic response", len(vessels))
        return vessels

    def _parse_row(self, row: dict[str, Any]) -> VesselData | None:
        """Parse a single vessel dict into a :class:`VesselData`.

        Returns ``None`` when the row is missing the mandatory MMSI field.
        """
        mmsi = str(row.get("MMSI", "")).strip()
        if not mmsi:
            return None

        raw_name = str(row.get("SHIPNAME", "")).strip()
        name = raw_name or f"Vessel {mmsi}"

        raw_length = row.get("LENGTH")
        length: int | None = None
        try:
            length = int(raw_length) if raw_length is not None else None
        except (ValueError, TypeError):
            length = None

        return VesselData(
            mmsi=mmsi,
            name=name,
            vessel_type=int(row.get("SHIPTYPE", 0)),
            latitude=float(row.get("LAT", 0.0)),
            longitude=float(row.get("LON", 0.0)),
            heading=int(row["HEADING"]) if row.get("HEADING") is not None else None,
            course=int(row["COURSE"]) if row.get("COURSE") is not None else None,
            speed=float(row["SPEED"]) if row.get("SPEED") is not None else None,
            status=_nav_status_to_str(row.get("NAVSTAT")),
            origin=row.get("LASTPORT") or None,
            destination=row.get("DESTINATION") or None,
            eta=str(row["ETA_CALC"]) if row.get("ETA_CALC") else None,
            imo=str(row["IMO"]) if row.get("IMO") else None,
            flag=str(row["FLAG"]).strip() or None if row.get("FLAG") else None,
            callsign=str(row["CALLSIGN"]).strip() or None if row.get("CALLSIGN") else None,
            length=length,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in kilometres between two points."""
    earth_radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lat_rad = phi2 - phi1
    delta_lon_rad = math.radians(lon2) - math.radians(lon1)
    a = (
        math.sin(delta_lat_rad / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lon_rad / 2) ** 2
    )
    return earth_radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _nav_status_to_str(code: Any) -> str | None:
    """Convert an AIS navigational status code to a human-readable string."""
    _STATUS_MAP: dict[int, str] = {
        0: "Under Way Using Engine",
        1: "At Anchor",
        2: "Not Under Command",
        3: "Restricted Manoeuvrability",
        4: "Constrained By Draught",
        5: "Moored",
        6: "Aground",
        7: "Engaged In Fishing",
        8: "Under Way Sailing",
        9: "Reserved for High Speed Craft",
        10: "Reserved for Wing in Ground",
        11: "Reserved",
        12: "Reserved",
        13: "Reserved",
        14: "AIS-SART / MOB-AIS / EPIRB-AIS",
        15: "Undefined",
    }
    if code is None:
        return None
    try:
        return _STATUS_MAP.get(int(code))
    except (ValueError, TypeError):
        return None
