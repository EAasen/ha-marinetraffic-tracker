"""MarineTraffic live-map HTTP client and vessel data model.

This module is the sole integration point with the external MarineTraffic
website.  All network I/O and JSON parsing lives here so that upstream
format changes only require updates to ``_parse_response`` / ``_parse_row``
without touching the coordinator or entity layers.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
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

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.marinetraffic.com/",
    "X-Requested-With": "XMLHttpRequest",
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
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

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

        Internally converts the circle to an approximate bounding box for
        the API query.  Callers that need strict circle filtering can post-
        filter by haversine distance — this is left for a future iteration.
        """
        # 1 degree latitude ≈ 111 km; longitude varies with cosine of lat.
        import math

        delta_lat = radius_km / 111.0
        cos_lat = math.cos(math.radians(latitude))
        delta_lon = radius_km / (111.0 * max(cos_lat, 0.01))

        return await self.get_vessels_in_box(
            north=latitude + delta_lat,
            east=longitude + delta_lon,
            south=latitude - delta_lat,
            west=longitude - delta_lon,
        )

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

        try:
            async with self._session.get(
                url,
                headers=_DEFAULT_HEADERS,
                timeout=_REQUEST_TIMEOUT,
            ) as resp:
                resp.raise_for_status()
                raw = await resp.json(content_type=None)
        except aiohttp.ClientResponseError as exc:
            _LOGGER.error(
                "MarineTraffic returned HTTP %s for %s", exc.status, url
            )
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

        **This is a stub implementation.**  The actual MarineTraffic live-map
        JSON schema must be confirmed by inspecting browser network traffic
        and then mapping the real field names below.

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
                "No vessel rows in MarineTraffic response "
                "(empty area or changed response format)"
            )
            return vessels

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
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    }
    if code is None:
        return None
    try:
        return _STATUS_MAP.get(int(code))
    except (ValueError, TypeError):
        return None
