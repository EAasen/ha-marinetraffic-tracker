"""Kystverket / BarentsWatch AIS client for Norwegian vessel data."""

from __future__ import annotations

import json
import logging
import math
from datetime import UTC, datetime, timedelta
from json import JSONDecodeError
from typing import Any

import aiohttp

from .client import VesselData, _haversine_km, _nav_status_to_str

_LOGGER = logging.getLogger(__name__)

_TOKEN_URL = "https://id.barentswatch.no/connect/token"
_VESSELS_URL = "https://live.ais.barentswatch.no/v1/combined"
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=60)
_TOKEN_REFRESH_BUFFER = 60
_HEADING_NOT_AVAILABLE = 511


class KystverketClient:
    """Async client for Kystverket live AIS data via BarentsWatch."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        client_id: str,
        client_secret: str,
    ) -> None:
        self._session = session
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token: str | None = None
        self._token_expiry: datetime | None = None

    async def get_vessels_in_radius(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
    ) -> list[VesselData]:
        """Return vessels within *radius_km* of (*latitude*, *longitude*)."""
        delta_lat = radius_km / 111.0
        cos_lat = math.cos(math.radians(latitude))
        delta_lon = radius_km / (111.0 * max(cos_lat, 0.01))

        all_vessels = await self.get_vessels_in_box(
            north=latitude + delta_lat,
            east=longitude + delta_lon,
            south=latitude - delta_lat,
            west=longitude - delta_lon,
        )

        return [
            vessel
            for vessel in all_vessels
            if _haversine_km(latitude, longitude, vessel.latitude, vessel.longitude) <= radius_km
        ]

    async def get_vessels_in_box(
        self,
        north: float,
        east: float,
        south: float,
        west: float,
        zoom: int = 10,  # kept for interface compatibility; unused
    ) -> list[VesselData]:
        """Return vessels within the given geographic bounding box."""
        del zoom

        token = await self._get_access_token()
        raw = await self._fetch_payload(token, north, east, south, west)
        if raw is None:
            self._access_token = None
            self._token_expiry = None
            token = await self._get_access_token()
            raw = await self._fetch_payload(token, north, east, south, west, retry=False)
        return self._parse_response(raw)

    async def _get_access_token(self) -> str:
        now = datetime.now(UTC)
        if (
            self._access_token is not None
            and self._token_expiry is not None
            and now < self._token_expiry
        ):
            return self._access_token

        data = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": "ais",
            "grant_type": "client_credentials",
        }

        async with self._session.post(
            _TOKEN_URL,
            data=data,
            timeout=_REQUEST_TIMEOUT,
        ) as resp:
            resp.raise_for_status()
            payload = await resp.json(content_type=None)

        self._access_token = str(payload["access_token"])
        expires_in = int(payload.get("expires_in", 3600))
        self._token_expiry = now + timedelta(
            seconds=max(expires_in - _TOKEN_REFRESH_BUFFER, 0)
        )
        return self._access_token

    async def _fetch_payload(
        self,
        token: str,
        north: float,
        east: float,
        south: float,
        west: float,
        *,
        retry: bool = True,
    ) -> Any | None:
        params = {
            "Xmin": round(west, 4),
            "Ymin": round(south, 4),
            "Xmax": round(east, 4),
            "Ymax": round(north, 4),
            "modelType": "Full",
            "modelFormat": "Json",
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        async with self._session.get(
            _VESSELS_URL,
            headers=headers,
            params=params,
            timeout=_REQUEST_TIMEOUT,
        ) as resp:
            if resp.status == 401 and retry:
                return None
            resp.raise_for_status()
            try:
                return await resp.json(content_type=None)
            except (JSONDecodeError, aiohttp.ContentTypeError):
                return self._parse_ndjson(await resp.text())

    def _parse_ndjson(self, text: str) -> list[dict[str, Any]]:
        """Parse newline-delimited JSON payloads."""
        rows: list[dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows

    def _parse_response(self, raw: Any) -> list[VesselData]:
        """Parse a Kystverket / BarentsWatch response payload."""
        if isinstance(raw, list):
            rows = raw
        elif isinstance(raw, dict) and isinstance(raw.get("features"), list):
            rows = raw["features"]
        else:
            _LOGGER.debug(
                "Unexpected Kystverket response type: %s",
                type(raw).__name__,
            )
            return []

        vessels: list[VesselData] = []
        for row in rows:
            vessel = self._parse_row(row)
            if vessel is not None:
                vessels.append(vessel)
        return vessels

    def _parse_row(self, row: dict[str, Any]) -> VesselData | None:
        """Parse one vessel row into a :class:`VesselData`."""
        if "properties" in row and isinstance(row["properties"], dict):
            props = dict(row["properties"])
            geometry = row.get("geometry")
            coords = geometry.get("coordinates") if isinstance(geometry, dict) else None
            if isinstance(coords, list) and len(coords) >= 2:
                props.setdefault("longitude", coords[0])
                props.setdefault("latitude", coords[1])
            row = props

        mmsi = str(row.get("mmsi") or "").strip()
        if not mmsi:
            return None

        lat = row.get("latitude")
        lon = row.get("longitude")
        if lat is None or lon is None:
            return None

        name = str(row.get("name") or "").strip() or f"Vessel {mmsi}"

        heading = _safe_int(row.get("trueHeading"))
        if heading == _HEADING_NOT_AVAILABLE:
            heading = None
        rate_of_turn = _safe_int(row.get("rateOfTurn"))
        if rate_of_turn == -128:
            rate_of_turn = None

        last_seen = _parse_timestamp(row.get("msgtime"))

        return VesselData(
            mmsi=mmsi,
            name=name,
            vessel_type=_safe_int(row.get("shipType")) or 0,
            latitude=float(lat),
            longitude=float(lon),
            heading=heading,
            course=_safe_int(row.get("courseOverGround")),
            speed=_safe_float(row.get("speedOverGround")),
            status=_nav_status_to_str(row.get("navigationalStatus")),
            origin=None,
            destination=_safe_str(row.get("destination")),
            eta=None,
            imo=_safe_str(row.get("imoNumber")),
            flag=None,
            callsign=_safe_str(row.get("callsign")),
            length=_safe_int(row.get("shipLength")),
            draught=_safe_float(row.get("draught")),
            rate_of_turn=rate_of_turn,
            beam=_safe_int(row.get("shipBreadth")),
            last_seen=last_seen or datetime.now(UTC),
            source="kystverket",
        )


def _safe_int(value: Any) -> int | None:
    try:
        return int(float(value)) if value is not None else None
    except (ValueError, TypeError):
        return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (ValueError, TypeError):
        return None


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
