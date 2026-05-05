"""DataUpdateCoordinator for MarineTraffic Tracker.

The coordinator owns the vessel state dictionary and is responsible for:
- Periodic polling with randomised jitter to reduce rate-limit risk.
- Merging fresh API results into the running vessel set.
- Purging vessels that have not been observed within the stale timeout.
"""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import MarineTrafficClient, VesselData
from .const import (
    CONF_EAST,
    CONF_FILTER_VESSEL_TYPES,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NORTH,
    CONF_RADIUS_KM,
    CONF_SOUTH,
    CONF_STALE_TIMEOUT,
    CONF_TRACKING_MODE,
    CONF_UPDATE_INTERVAL,
    CONF_WEST,
    DEFAULT_JITTER_MAX,
    DEFAULT_RADIUS_KM,
    DEFAULT_STALE_TIMEOUT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    EVENT_VESSEL_ENTERED,
    EVENT_VESSEL_EXITED,
    TRACKING_MODE_RADIUS,
)

_LOGGER = logging.getLogger(__name__)


class MarineTrafficCoordinator(DataUpdateCoordinator[dict[str, VesselData]]):
    """Coordinator that polls MarineTraffic and manages the vessel registry.

    ``data`` is a ``dict[mmsi, VesselData]`` representing all vessels
    currently considered active (i.e. seen within the stale timeout).
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: MarineTrafficClient,
    ) -> None:
        self._client = client
        self._entry = entry
        # Running vessel registry — persists across updates.
        self._vessels: dict[str, VesselData] = {}

        update_interval = timedelta(
            seconds=entry.options.get(
                CONF_UPDATE_INTERVAL,
                entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            )
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def stale_timeout_seconds(self) -> int:
        """Configurable age (seconds) beyond which a vessel is removed."""
        return int(
            self._entry.options.get(
                CONF_STALE_TIMEOUT,
                self._entry.data.get(CONF_STALE_TIMEOUT, DEFAULT_STALE_TIMEOUT),
            )
        )

    # ------------------------------------------------------------------
    # Core update logic
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, VesselData]:
        """Fetch fresh vessel data, merge into registry, purge stale entries.

        A random jitter of up to ``DEFAULT_JITTER_MAX`` seconds is applied
        before each request to spread load and avoid predictable polling
        patterns that could trigger MarineTraffic's rate limiting.

        EXTENSION POINT: If Home Assistant ever provides a native jitter
        mechanism in DataUpdateCoordinator, the ``asyncio.sleep`` below can
        be replaced with the framework equivalent.
        """
        jitter = random.uniform(0, DEFAULT_JITTER_MAX)  # noqa: S311
        _LOGGER.debug("Waiting %.1f s jitter before polling", jitter)
        await asyncio.sleep(jitter)

        config: dict = {**self._entry.data, **self._entry.options}
        tracking_mode = config.get(CONF_TRACKING_MODE, TRACKING_MODE_RADIUS)

        try:
            if tracking_mode == TRACKING_MODE_RADIUS:
                fresh = await self._client.get_vessels_in_radius(
                    latitude=float(config[CONF_LATITUDE]),
                    longitude=float(config[CONF_LONGITUDE]),
                    radius_km=float(config.get(CONF_RADIUS_KM, DEFAULT_RADIUS_KM)),
                )
            else:
                fresh = await self._client.get_vessels_in_box(
                    north=float(config[CONF_NORTH]),
                    east=float(config[CONF_EAST]),
                    south=float(config[CONF_SOUTH]),
                    west=float(config[CONF_WEST]),
                )
        except Exception as exc:
            raise UpdateFailed(f"Error communicating with MarineTraffic: {exc}") from exc

        now = datetime.now(timezone.utc)

        # Determine which MMSIs are genuinely new (not yet tracked).
        previously_tracked: set[str] = set(self._vessels)

        # Merge fresh observations into the registry
        for vessel in fresh:
            vessel.last_seen = now
            self._vessels[vessel.mmsi] = vessel

        # Apply optional vessel-type filter
        filter_types: list[int] = list(
            self._entry.options.get(
                CONF_FILTER_VESSEL_TYPES,
                self._entry.data.get(CONF_FILTER_VESSEL_TYPES, []),
            )
        )
        if filter_types:
            excluded = [
                mmsi
                for mmsi, v in self._vessels.items()
                if v.vessel_type not in filter_types
            ]
            for mmsi in excluded:
                del self._vessels[mmsi]

        # Remove vessels not seen within the stale timeout
        stale_cutoff = now - timedelta(seconds=self.stale_timeout_seconds)
        stale = [
            mmsi for mmsi, v in self._vessels.items() if v.last_seen < stale_cutoff
        ]
        for mmsi in stale:
            _LOGGER.debug("Removing stale vessel MMSI=%s (last seen >%ds ago)", mmsi, self.stale_timeout_seconds)
            exited_vessel = self._vessels.pop(mmsi)
            self.hass.bus.async_fire(
                EVENT_VESSEL_EXITED,
                {
                    "mmsi": mmsi,
                    "name": exited_vessel.name,
                    "vessel_type": exited_vessel.vessel_type,
                },
            )

        # Fire entered events for vessels that are new this cycle.
        for mmsi, vessel in self._vessels.items():
            if mmsi not in previously_tracked:
                self.hass.bus.async_fire(
                    EVENT_VESSEL_ENTERED,
                    {
                        "mmsi": mmsi,
                        "name": vessel.name,
                        "vessel_type": vessel.vessel_type,
                    },
                )

        _LOGGER.debug(
            "Poll complete: %d active vessel(s), %d stale removed",
            len(self._vessels),
            len(stale),
        )
        return dict(self._vessels)