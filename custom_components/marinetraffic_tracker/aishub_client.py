"""AISHub API client for vessel data.

AISHub (https://www.aishub.net/) operates on a data-sharing model: users
who contribute AIS data to the network receive a free API key that allows
them to query the aggregated AIS dataset.

The key advantage over web-scraping is:
- Official, stable JSON API — no IP-ban risk.
- Faster polling is safe (down to 5 s; the platform encourages sharing).
- Global coverage aggregated from many shore-based and satellite receivers.

API endpoint::

    GET https://data.aishub.net/ws.php
        ?username={api_key}
        &format=1
        &output=json
        &compress=0
        &latmin={south}
        &latmax={north}
        &lonmin={west}
        &lonmax={east}

Response envelope (format=1, output=json)::

    [
      {"ERROR": false, "USERNAME": "...", "FORMAT": 1, "RECORDS": N},
      [
        {
          "MMSI": 123456789,
          "TIME": "2024-01-15 08:00:00 UTC",
          "LONGITUDE": 10.7,
          "LATITUDE": 59.9,
          "COG": 182.0,      # Course Over Ground (degrees)
          "SOG": 12.5,       # Speed Over Ground (knots)
          "HEADING": 180,    # True heading (degrees; 511 = not available)
          "ROT": 5,          # Rate Of Turn (degrees/min; -128 = not available)
          "NAVSTAT": 0,      # AIS Navigational Status code (0–15)
          "IMO": 9876543,
          "NAME": "MY VESSEL",
          "CALLSIGN": "ABCD",
          "TYPE": 70,        # AIS ship type code
          "A": 100,          # Bow-to-antenna offset (m)
          "B": 80,           # Stern-to-antenna offset (m)
          "C": 12,           # Port-to-antenna offset (m) → half of beam
          "D": 8,            # Starboard-to-antenna offset (m) → half of beam
          "DRAUGHT": 62,     # Draught in decimetres (as reported via AIS)
          "DEST": "OSLO",    # Destination
          "ETA": "01/15 14:00"
        },
        ...
      ]
    ]

Update ``_parse_row`` if AISHub changes field names.
"""

from __future__ import annotations

import logging
import math
from typing import Any

import aiohttp

from .client import VesselData, _haversine_km, _nav_status_to_str

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
_AISHUB_URL = (
    "https://data.aishub.net/ws.php"
    "?username={api_key}&format=1&output=json&compress=0"
    "&latmin={south}&latmax={north}&lonmin={west}&lonmax={east}"
)

_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)

# AIS heading sentinel — 511 means "not available".
_HEADING_NOT_AVAILABLE = 511


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class AISHubClient:
    """Async HTTP client for the AISHub vessel data API.

    Usage::

        async with aiohttp.ClientSession() as session:
            client = AISHubClient(session, api_key="YOUR_AISHUB_USERNAME")
            vessels = await client.get_vessels_in_radius(59.9, 10.7, 50)
    """

    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key

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
            "AISHub: fetching vessels within %.1f km of tracking centre",
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

        in_radius = [
            v
            for v in all_vessels
            if _haversine_km(latitude, longitude, v.latitude, v.longitude) <= radius_km
        ]
        _LOGGER.debug(
            "AISHub Haversine filter: %d → %d vessels within %.1f km",
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
        zoom: int = 10,  # kept for interface compatibility; unused by AISHub API
    ) -> list[VesselData]:
        """Return vessels within the given geographic bounding box."""
        url = _AISHUB_URL.format(
            api_key=self._api_key,
            north=round(north, 4),
            east=round(east, 4),
            south=round(south, 4),
            west=round(west, 4),
        )

        # Build a log-safe URL (with the API key masked) independently, so that
        # no tainted data flows into the log statement.
        log_url = _AISHUB_URL.format(
            api_key="***",
            north=round(north, 4),
            east=round(east, 4),
            south=round(south, 4),
            west=round(west, 4),
        )
        _LOGGER.debug("GET AISHub %s", log_url)

        try:
            async with self._session.get(url, timeout=_REQUEST_TIMEOUT) as resp:
                _LOGGER.debug("AISHub responded with HTTP %s", resp.status)
                resp.raise_for_status()
                raw = await resp.json(content_type=None)
        except aiohttp.ClientResponseError as exc:
            _LOGGER.error("AISHub returned HTTP %s", exc.status)
            raise
        except aiohttp.ClientError as exc:
            _LOGGER.error("Network error fetching AISHub data: %s", exc)
            raise
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("Unexpected error during AISHub fetch: %s", exc)
            raise

        return self._parse_response(raw)

    # ------------------------------------------------------------------
    # EXTENSION POINT — parser
    # Update ``_parse_response`` / ``_parse_row`` when the API format changes.
    # ------------------------------------------------------------------

    def _parse_response(self, raw: Any) -> list[VesselData]:
        """Parse the raw AISHub JSON response into a list of :class:`VesselData`.

        The response is a two-element list: a header dict and a list of vessel
        dicts.  Returns an empty list on error or when no vessels are found.
        """
        vessels: list[VesselData] = []

        if not isinstance(raw, list) or len(raw) < 2:
            _LOGGER.debug(
                "Unexpected AISHub response format: %s (expected 2-element list)",
                type(raw).__name__,
            )
            return vessels

        # First element is the response header.
        header = raw[0]
        if isinstance(header, dict) and header.get("ERROR"):
            _LOGGER.error(
                "AISHub returned an error response: %s",
                header.get("ERROR_MESSAGE", header),
            )
            return vessels

        rows = raw[1]
        if not isinstance(rows, list):
            _LOGGER.debug(
                "AISHub vessel list is not a list: %s", type(rows).__name__
            )
            return vessels

        _LOGGER.debug("Parsing %d AISHub vessel row(s)", len(rows))

        for row in rows:
            try:
                vessel = self._parse_row(row)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug("Failed to parse AISHub vessel row %s: %s", row, exc)
                continue
            if vessel is not None:
                vessels.append(vessel)

        _LOGGER.debug("Parsed %d vessel(s) from AISHub response", len(vessels))
        return vessels

    def _parse_row(self, row: dict[str, Any]) -> VesselData | None:
        """Parse a single AISHub vessel dict into a :class:`VesselData`.

        Returns ``None`` when the row is missing the mandatory MMSI field.
        """
        mmsi = str(row.get("MMSI", "")).strip()
        if not mmsi:
            return None

        raw_name = str(row.get("NAME", "")).strip()
        name = raw_name or f"Vessel {mmsi}"

        # Rate of turn — AIS sentinel –128 means "no information available".
        raw_rot = row.get("ROT")
        rate_of_turn: int | None = None
        try:
            if raw_rot is not None:
                rot_int = int(raw_rot)
                rate_of_turn = None if rot_int == -128 else rot_int
        except (ValueError, TypeError):
            rate_of_turn = None

        # Beam derived from port/starboard antenna offsets (C + D), same as MarineTraffic.
        beam: int | None = None
        try:
            raw_c = row.get("C")
            raw_d = row.get("D")
            if raw_c is not None and raw_d is not None:
                beam = int(raw_c) + int(raw_d)
        except (ValueError, TypeError):
            beam = None

        raw_draught = row.get("DRAUGHT")
        draught: float | None = None
        try:
            draught = float(raw_draught) if raw_draught is not None else None
        except (ValueError, TypeError):
            draught = None

        # IMO — AISHub returns 0 when unknown; treat 0 as absent.
        raw_imo = row.get("IMO")
        imo: str | None = None
        if raw_imo is not None:
            try:
                imo_int = int(raw_imo)
                imo = str(imo_int) if imo_int > 0 else None
            except (ValueError, TypeError):
                imo = None

        # AISHub uses COG (Course Over Ground) and SOG (Speed Over Ground).
        raw_cog = row.get("COG")
        course: int | None = None
        try:
            course = int(float(raw_cog)) if raw_cog is not None else None
        except (ValueError, TypeError):
            course = None

        # Heading — 511 is the AIS "not available" sentinel.
        raw_heading = row.get("HEADING")
        heading: int | None = None
        try:
            if raw_heading is not None:
                h = int(raw_heading)
                heading = None if h == _HEADING_NOT_AVAILABLE else h
        except (ValueError, TypeError):
            heading = None

        raw_speed = row.get("SOG")
        speed: float | None = None
        try:
            speed = float(raw_speed) if raw_speed is not None else None
        except (ValueError, TypeError):
            speed = None

        raw_dest = row.get("DEST")
        destination: str | None = None
        if raw_dest is not None:
            dest_str = str(raw_dest).strip()
            destination = dest_str if dest_str else None

        raw_eta = row.get("ETA")
        eta: str | None = str(raw_eta).strip() or None if raw_eta is not None else None

        raw_cs = row.get("CALLSIGN")
        callsign: str | None = str(raw_cs).strip() or None if raw_cs is not None else None

        return VesselData(
            mmsi=mmsi,
            name=name,
            vessel_type=int(row.get("TYPE", 0)),
            latitude=float(row.get("LATITUDE", 0.0)),
            longitude=float(row.get("LONGITUDE", 0.0)),
            heading=heading,
            course=course,
            speed=speed,
            status=_nav_status_to_str(row.get("NAVSTAT")),
            origin=None,  # AISHub does not provide last-port information
            destination=destination,
            eta=eta,
            imo=imo,
            flag=None,  # AISHub does not expose flag/country in the free API
            callsign=callsign,
            rate_of_turn=rate_of_turn,
            beam=beam,
            draught=draught,
            source="aishub",
        )
