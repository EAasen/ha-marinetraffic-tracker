"""DataUpdateCoordinator for MarineTraffic Tracker.

The coordinator owns the vessel state dictionary and is responsible for:
- Periodic polling with randomised jitter to reduce rate-limit risk.
- Merging fresh API results into the running vessel set.
- Purging vessels that have not been observed within the stale timeout.
- Applying vessel-type filtering before state exposure and event emission.
- Firing ``marinetraffic_vessel_entered`` / ``marinetraffic_vessel_exited``
  events on the Home Assistant event bus for automation support.
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import UTC, datetime, timedelta

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
    DEFAULT_FILTER_VESSEL_TYPES,
    DEFAULT_JITTER_MAX,
    DEFAULT_RADIUS_KM,
    DEFAULT_STALE_TIMEOUT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    EVENT_VESSEL_ENTERED,
    EVENT_VESSEL_EXITED,
    MIN_UPDATE_INTERVAL,
    TRACKING_MODE_RADIUS,
)

_LOGGER = logging.getLogger(__name__)


class MarineTrafficCoordinator(DataUpdateCoordinator[dict[str, VesselData]]):
    """Coordinator that polls MarineTraffic and manages the vessel registry.

    ``data`` is a ``dict[mmsi, VesselData]`` representing all vessels
    currently considered active (i.e. seen within the stale timeout) and
    matching the configured vessel-type filter.
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
        # Track previous poll's MMSIs to compute entered/exited deltas.
        self._prev_mmsis: set[str] = set()

        configured_interval = int(
            entry.options.get(
                CONF_UPDATE_INTERVAL,
                entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            )
        )
        if configured_interval < MIN_UPDATE_INTERVAL:
            _LOGGER.warning(
                "Configured update_interval %ds is below the minimum %ds. "
                "Clamping to %ds to reduce MarineTraffic ban/rate-limit risk.",
                configured_interval,
                MIN_UPDATE_INTERVAL,
                MIN_UPDATE_INTERVAL,
            )
            configured_interval = MIN_UPDATE_INTERVAL

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=configured_interval),
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

    @property
    def _filter_vessel_types(self) -> set[int]:
        """Return the set of allowed vessel type codes; empty = allow all."""
        raw: list[str] = self._entry.options.get(
            CONF_FILTER_VESSEL_TYPES,
            self._entry.data.get(CONF_FILTER_VESSEL_TYPES, DEFAULT_FILTER_VESSEL_TYPES),
        )
        return {int(t) for t in raw} if raw else set()

    # ------------------------------------------------------------------
    # Core update logic
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, VesselData]:
        """Fetch fresh vessel data, merge into registry, purge stale entries.

        A random jitter of up to ``DEFAULT_JITTER_MAX`` seconds is applied
        before each request to spread load and avoid predictable polling
        patterns that could trigger MarineTraffic's rate limiting.
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

        # Apply vessel-type filter before state exposure and event emission.
        # An empty filter set means "allow all vessel types".
        filter_types = self._filter_vessel_types
        if filter_types:
            fresh = [v for v in fresh if v.vessel_type in filter_types]

        now = datetime.now(UTC)

        # Snapshot the previous state for entered/exited delta calculation.
        prev_mmsis = set(self._prev_mmsis)
        prev_vessel_data = dict(self._vessels)

        # Merge fresh observations into the registry.
        for vessel in fresh:
            vessel.last_seen = now
            self._vessels[vessel.mmsi] = vessel

        # Remove vessels not seen within the stale timeout.
        stale_cutoff = now - timedelta(seconds=self.stale_timeout_seconds)
        stale = [mmsi for mmsi, v in self._vessels.items() if v.last_seen < stale_cutoff]
        for mmsi in stale:
            _LOGGER.debug(
                "Removing stale vessel MMSI=%s (last seen >%ds ago)",
                mmsi,
                self.stale_timeout_seconds,
            )
            del self._vessels[mmsi]

        current_mmsis = set(self._vessels.keys())
        entered_mmsis = current_mmsis - prev_mmsis
        exited_mmsis = prev_mmsis - current_mmsis

        # Fire entered events for vessels newly in the tracked set.
        for mmsi in entered_mmsis:
            vessel = self._vessels[mmsi]
            self.hass.bus.async_fire(
                EVENT_VESSEL_ENTERED,
                {
                    "mmsi": vessel.mmsi,
                    "name": vessel.name,
                    "vessel_type": vessel.vessel_type,
                    "latitude": vessel.latitude,
                    "longitude": vessel.longitude,
                    "destination": vessel.destination,
                    "eta": vessel.eta,
                    "entry_id": self._entry.entry_id,
                },
            )

        # Fire exited events for vessels no longer in the tracked set.
        for mmsi in exited_mmsis:
            vessel = prev_vessel_data.get(mmsi)
            if vessel is not None:
                self.hass.bus.async_fire(
                    EVENT_VESSEL_EXITED,
                    {
                        "mmsi": vessel.mmsi,
                        "name": vessel.name,
                        "vessel_type": vessel.vessel_type,
                        "latitude": vessel.latitude,
                        "longitude": vessel.longitude,
                        "destination": vessel.destination,
                        "eta": vessel.eta,
                        "entry_id": self._entry.entry_id,
                    },
                )

        self._prev_mmsis = current_mmsis

        _LOGGER.debug(
            "Poll complete: %d active vessel(s), %d stale removed, %d entered, %d exited",
            len(self._vessels),
            len(stale),
            len(entered_mmsis),
            len(exited_mmsis),
        )
        return dict(self._vessels)
