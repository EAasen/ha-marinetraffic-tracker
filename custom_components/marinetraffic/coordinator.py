"""DataUpdateCoordinator for the MarineTraffic integration."""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import MarineTrafficClient
from .const import (
    DOMAIN,
    JITTER_MAX,
    JITTER_MIN,
    SCAN_INTERVAL,
    VESSEL_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


class MarineTrafficCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that polls MarineTraffic and manages vessel state."""

    def __init__(
        self,
        hass: HomeAssistant,
        latitude: float,
        longitude: float,
        radius_km: float,
    ) -> None:
        from datetime import timedelta

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.latitude = latitude
        self.longitude = longitude
        self.radius_km = radius_km

        # All vessels seen in the last VESSEL_TIMEOUT seconds.
        # Key: MMSI (str), Value: vessel dict with an added "_last_seen" key.
        self._vessels: dict[str, dict[str, Any]] = {}

        self._session: aiohttp.ClientSession | None = None
        self._client: MarineTrafficClient | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _async_setup(self) -> None:
        """Create an aiohttp session shared for the life of this entry."""
        self._session = aiohttp.ClientSession()
        self._client = MarineTrafficClient(self._session)

    async def async_shutdown(self) -> None:
        """Close the HTTP session when the integration is unloaded."""
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------
    # Core update
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch latest vessel data and merge with the tracked vessel state."""
        # Lazy initialisation of the HTTP session (runs once).
        if self._client is None:
            await self._async_setup()

        # Jitter to avoid looking like a bot.
        await asyncio.sleep(random.uniform(JITTER_MIN, JITTER_MAX))

        try:
            fresh_vessels = await self._client.get_vessels_in_radius(  # type: ignore[union-attr]
                self.latitude, self.longitude, self.radius_km
            )
        except Exception as exc:
            raise UpdateFailed(f"Error communicating with MarineTraffic: {exc}") from exc

        now = time.monotonic()

        # Update seen timestamps for vessels that are still in range.
        for vessel in fresh_vessels:
            mmsi = vessel["mmsi"]
            vessel["_last_seen"] = now
            self._vessels[mmsi] = vessel

        # Purge vessels that haven't been seen for VESSEL_TIMEOUT seconds.
        stale = [
            mmsi
            for mmsi, v in self._vessels.items()
            if now - v.get("_last_seen", 0) > VESSEL_TIMEOUT
        ]
        for mmsi in stale:
            _LOGGER.debug("Purging stale vessel %s", mmsi)
            del self._vessels[mmsi]

        return {
            "vessels": dict(self._vessels),  # shallow copy
            "count": len(self._vessels),
        }
