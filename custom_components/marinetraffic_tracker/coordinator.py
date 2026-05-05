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
    MIN_UPDATE_INTERVAL,
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

        raw_interval = entry.options.get(
            CONF_UPDATE_INTERVAL,
            entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )
        try:
            interval_seconds = int(raw_interval)
        except (TypeError, ValueError):
            interval_seconds = DEFAULT_UPDATE_INTERVAL

        if interval_seconds < MIN_UPDATE_INTERVAL:
            _LOGGER.warning(
                "Configured update_interval %d s is below the minimum %d s — clamping.",
                interval_seconds,
                MIN_UPDATE_INTERVAL,
            )
            interval_seconds = MIN_UPDATE_INTERVAL

        update_interval = timedelta(seconds=interval_seconds)

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
    # Internal helpers
    # ------------------------------------------------------------------

    def _vessel_event_payload(self, vessel: VesselData) -> dict:
        """Build a consistent, automation-friendly event payload for a vessel."""
        return {
            "mmsi": vessel.mmsi,
            "name": vessel.name,
            "vessel_type": vessel.vessel_type,
            "latitude": vessel.latitude,
            "longitude": vessel.longitude,
            "destination": vessel.destination,
            "eta": vessel.eta,
            "entry_id": self._entry.entry_id,
        }

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

        now = datetime.now(UTC)

        # Snapshot of MMSIs tracked before this update cycle.
        previous_mmsis: set[str] = set(self._vessels.keys())

        # Vessel type filter — empty set means no filtering (all types allowed).
        filter_types: set[str] = set(
            config.get(CONF_FILTER_VESSEL_TYPES, DEFAULT_FILTER_VESSEL_TYPES)
        )

        # Merge fresh observations into the registry
        for vessel in fresh:
            if filter_types and str(vessel.vessel_type) not in filter_types:
                _LOGGER.debug(
                    "Skipping vessel MMSI=%s type=%d (filtered out)",
                    vessel.mmsi,
                    vessel.vessel_type,
                )
                continue
            vessel.last_seen = now
            self._vessels[vessel.mmsi] = vessel

        # Fire entered events only for vessels that passed the filter and are new.
        for vessel in fresh:
            if vessel.mmsi in self._vessels and vessel.mmsi not in previous_mmsis:
                _LOGGER.debug("Vessel entered: MMSI=%s name=%s", vessel.mmsi, vessel.name)
                self.hass.bus.async_fire(
                    "marinetraffic_vessel_entered",
                    self._vessel_event_payload(vessel),
                )

        # Remove vessels not seen within the stale timeout
        stale_cutoff = now - timedelta(seconds=self.stale_timeout_seconds)
        stale = [
            mmsi for mmsi, v in self._vessels.items() if v.last_seen < stale_cutoff
        ]
        for mmsi in stale:
            departed = self._vessels[mmsi]
            _LOGGER.debug(
                "Removing stale vessel MMSI=%s (last seen >%ds ago)",
                mmsi,
                self.stale_timeout_seconds,
            )
            self.hass.bus.async_fire(
                "marinetraffic_vessel_exited",
                self._vessel_event_payload(departed),
            )
            del self._vessels[mmsi]

        _LOGGER.debug(
            "Poll complete: %d active vessel(s), %d stale removed",
            len(self._vessels),
            len(stale),
        )
        return dict(self._vessels)
