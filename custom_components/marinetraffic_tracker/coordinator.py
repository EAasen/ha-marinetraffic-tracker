"""DataUpdateCoordinator for MarineTraffic Tracker.

The coordinator owns the vessel state dictionary and is responsible for:
- Periodic polling with randomised jitter to reduce rate-limit risk.
- Enforcing the minimum update interval (MIN_UPDATE_INTERVAL) at runtime so
  that even manually-edited config entries cannot poll faster than the safe
  floor.  If clamping occurs a warning is logged.
- Merging fresh API results into the running vessel set.
- Purging vessels that have not been observed within the stale timeout.
- Applying per-user vessel-type filtering before exposing state.
- Firing ``marinetraffic_vessel_entered`` / ``marinetraffic_vessel_exited``
  events on the HA event bus so automations can react to vessel lifecycle
  changes without polling coordinator data directly.
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
    MIN_UPDATE_INTERVAL,
    TRACKING_MODE_RADIUS,
)

_LOGGER = logging.getLogger(__name__)


class MarineTrafficCoordinator(DataUpdateCoordinator[dict[str, VesselData]]):
    """Coordinator that polls MarineTraffic and manages the vessel registry.

    ``data`` is a ``dict[mmsi, VesselData]`` representing all vessels
    currently considered active **and matching the user's type filter**
    (i.e. seen within the stale timeout and of an allowed vessel type).

    Events fired on the HA bus:
    - ``marinetraffic_vessel_entered``: when a vessel first appears in the
      filtered tracked set.
    - ``marinetraffic_vessel_exited``: when a vessel is removed from the
      tracked set (either purged as stale or filtered out after a type-filter
      change).
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
        # Contains ALL seen vessels (before filtering) so stale tracking works.
        self._vessels: dict[str, VesselData] = {}
        # Tracks the set of MMSIs currently exposed to HA (post-filter).
        # Used to detect entered/exited transitions without duplicates.
        self._active_mmsis: set[str] = set()

        raw_interval = int(
            entry.options.get(
                CONF_UPDATE_INTERVAL,
                entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            )
        )
        # Anti-ban: clamp the interval to the safe floor at runtime so that
        # manually-edited config entries cannot bypass the UI schema validation.
        if raw_interval < MIN_UPDATE_INTERVAL:
            _LOGGER.warning(
                "Configured update_interval (%ds) is below the safe minimum of %ds. "
                "Clamping to %ds to reduce MarineTraffic ban/rate-limit risk.",
                raw_interval,
                MIN_UPDATE_INTERVAL,
                MIN_UPDATE_INTERVAL,
            )
            raw_interval = MIN_UPDATE_INTERVAL

        update_interval = timedelta(seconds=raw_interval)

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

    @property
    def _filter_vessel_types(self) -> list[int]:
        """Return the list of allowed vessel type codes (empty = allow all)."""
        raw = self._entry.options.get(
            CONF_FILTER_VESSEL_TYPES,
            self._entry.data.get(CONF_FILTER_VESSEL_TYPES, []),
        )
        # Normalise to a list of ints regardless of how HA stored the value.
        if not raw:
            return []
        try:
            return [int(t) for t in raw]
        except (TypeError, ValueError):
            return []

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

        # Merge fresh observations into the registry
        for vessel in fresh:
            vessel.last_seen = now
            self._vessels[vessel.mmsi] = vessel

        # Remove vessels not seen within the stale timeout
        stale_cutoff = now - timedelta(seconds=self.stale_timeout_seconds)
        stale = [mmsi for mmsi, v in self._vessels.items() if v.last_seen < stale_cutoff]
        for mmsi in stale:
            _LOGGER.debug(
                "Removing stale vessel MMSI=%s (last seen >%ds ago)",
                mmsi,
                self.stale_timeout_seconds,
            )
            del self._vessels[mmsi]

        # Apply vessel type filter (empty filter = allow all).
        allowed_types = self._filter_vessel_types
        if allowed_types:
            filtered = {
                mmsi: v for mmsi, v in self._vessels.items() if v.vessel_type in allowed_types
            }
        else:
            filtered = dict(self._vessels)

        # Fire entered/exited events based on transitions in the filtered set.
        self._fire_lifecycle_events(filtered)

        _LOGGER.debug(
            "Poll complete: %d active vessel(s) (after filter), %d stale removed",
            len(filtered),
            len(stale),
        )
        return filtered

    # ------------------------------------------------------------------
    # Event helpers
    # ------------------------------------------------------------------

    def _fire_lifecycle_events(self, current: dict[str, VesselData]) -> None:
        """Emit entered/exited events for vessels that transitioned state.

        Entered = MMSI is in *current* but was not in the previous active set.
        Exited  = MMSI was in the previous active set but is not in *current*.

        Events are fired exactly once per transition; repeated polls with the
        same vessel in the active set do not re-fire ``entered``.
        """
        current_mmsis = set(current)
        entry_id = self._entry.entry_id

        # Newly visible vessels
        for mmsi in current_mmsis - self._active_mmsis:
            vessel = current[mmsi]
            self.hass.bus.async_fire(
                EVENT_VESSEL_ENTERED,
                _event_payload(vessel, entry_id),
            )
            _LOGGER.debug("Fired %s for MMSI=%s", EVENT_VESSEL_ENTERED, mmsi)

        # Vessels that have left the tracked/filtered set
        for mmsi in self._active_mmsis - current_mmsis:
            # The vessel may still be in self._vessels if it was filtered out
            # rather than purged as stale — use the last-known data.
            vessel = self._vessels.get(mmsi)
            payload = (
                _event_payload(vessel, entry_id) if vessel else {"mmsi": mmsi, "entry_id": entry_id}
            )
            self.hass.bus.async_fire(EVENT_VESSEL_EXITED, payload)
            _LOGGER.debug("Fired %s for MMSI=%s", EVENT_VESSEL_EXITED, mmsi)

        self._active_mmsis = current_mmsis


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event_payload(vessel: VesselData, entry_id: str) -> dict:
    """Build an event payload dict from a VesselData instance.

    All optional fields are included only when present so that
    automations can rely on the payload schema without risk of KeyError.
    Missing optional fields are included as ``None`` so the payload
    structure is stable across vessel types.
    """
    return {
        "mmsi": vessel.mmsi,
        "name": vessel.name,
        "vessel_type": vessel.vessel_type,
        "latitude": vessel.latitude,
        "longitude": vessel.longitude,
        "destination": vessel.destination,
        "eta": vessel.eta,
        "entry_id": entry_id,
    }
