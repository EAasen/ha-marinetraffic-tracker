"""DataUpdateCoordinator for MarineTraffic Tracker.

The coordinator owns the vessel state dictionary and is responsible for:
- Periodic polling with randomised jitter to reduce rate-limit risk.
- Merging fresh API results into the running vessel set.
- Purging vessels that have not been observed within the stale timeout.
- Maintaining historical statistics (visit counts, time-in-zone, speed/size
  records, and hourly/daily traffic patterns) that persist even after vessels
  are purged from the active registry.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any

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
    DEFAULT_HISTORY_SIZE,
    DEFAULT_JITTER_MAX,
    DEFAULT_RADIUS_KM,
    DEFAULT_STALE_TIMEOUT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MIN_UPDATE_INTERVAL,
    TRACKING_MODE_RADIUS,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Statistics data model
# ---------------------------------------------------------------------------

@dataclass
class VesselRecord:
    """A snapshot of a vessel used for record-keeping in statistics."""

    mmsi: str
    name: str
    value: float
    recorded_at: str  # ISO-8601 timestamp


@dataclass
class AreaStatistics:
    """Aggregate statistics for the tracked area.

    All fields persist across coordinator refresh cycles so that records
    survive even after a vessel is purged from the active registry.
    """

    # visit_counts[mmsi] = total number of times the vessel entered the zone.
    visit_counts: dict[str, int] = field(default_factory=dict)
    # total_time_seconds[mmsi] = cumulative seconds the vessel spent in zone.
    total_time_seconds: dict[str, float] = field(default_factory=dict)
    # vessel_names[mmsi] = most recently observed name for the MMSI.
    vessel_names: dict[str, str] = field(default_factory=dict)

    # Global records — None until at least one observation has been recorded.
    speed_record: VesselRecord | None = None
    largest_vessel: VesselRecord | None = None
    smallest_vessel: VesselRecord | None = None

    # Traffic pattern counters — 24 hourly and 7 daily buckets.
    # Each observation of a vessel in a poll increments the current bucket.
    hourly_counts: list[int] = field(default_factory=lambda: [0] * 24)
    daily_counts: list[int] = field(default_factory=lambda: [0] * 7)

    def to_dict(self) -> dict[str, Any]:
        """Serialise statistics to a plain dict for sensor attributes."""
        # Most frequent visitor
        most_frequent: dict | None = None
        if self.visit_counts:
            top_mmsi = max(self.visit_counts, key=lambda m: self.visit_counts[m])
            most_frequent = {
                "mmsi": top_mmsi,
                "name": self.vessel_names.get(top_mmsi, top_mmsi),
                "visit_count": self.visit_counts[top_mmsi],
            }

        # Longest resident (by cumulative seconds in zone)
        longest_resident: dict | None = None
        if self.total_time_seconds:
            top_mmsi = max(self.total_time_seconds, key=lambda m: self.total_time_seconds[m])
            longest_resident = {
                "mmsi": top_mmsi,
                "name": self.vessel_names.get(top_mmsi, top_mmsi),
                "total_time_seconds": round(self.total_time_seconds[top_mmsi]),
            }

        # Busiest hour / day
        busiest_hour = self.hourly_counts.index(max(self.hourly_counts)) if any(self.hourly_counts) else None
        busiest_day = self.daily_counts.index(max(self.daily_counts)) if any(self.daily_counts) else None

        return {
            "most_frequent_visitor": most_frequent,
            "longest_resident": longest_resident,
            "speed_record": (
                {
                    "mmsi": self.speed_record.mmsi,
                    "name": self.speed_record.name,
                    "speed_knots": self.speed_record.value,
                    "recorded_at": self.speed_record.recorded_at,
                }
                if self.speed_record
                else None
            ),
            "largest_vessel": (
                {
                    "mmsi": self.largest_vessel.mmsi,
                    "name": self.largest_vessel.name,
                    "length_m": self.largest_vessel.value,
                    "recorded_at": self.largest_vessel.recorded_at,
                }
                if self.largest_vessel
                else None
            ),
            "smallest_vessel": (
                {
                    "mmsi": self.smallest_vessel.mmsi,
                    "name": self.smallest_vessel.name,
                    "length_m": self.smallest_vessel.value,
                    "recorded_at": self.smallest_vessel.recorded_at,
                }
                if self.smallest_vessel
                else None
            ),
            "busiest_hour": busiest_hour,
            "busiest_day": busiest_day,
            "hourly_counts": list(self.hourly_counts),
            "daily_counts": list(self.daily_counts),
            "total_vessels_seen": len(self.visit_counts),
        }


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
        # Per-vessel position history — stores recent (lat, lon, timestamp) tuples.
        self._position_history: dict[str, list[dict]] = {}
        # Historical statistics — persists even after vessels leave the active registry.
        self._statistics: AreaStatistics = AreaStatistics()
        # Entry timestamps — records when each vessel entered the zone this session.
        self._entry_times: dict[str, datetime] = {}

        # Anti-ban safety compliance: clamp the update interval to the hard floor
        # to protect the user's IP address from MarineTraffic rate limiting.
        try:
            raw_interval = int(
                entry.options.get(
                    CONF_UPDATE_INTERVAL,
                    entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                )
            )
        except (ValueError, TypeError):
            raw_interval = DEFAULT_UPDATE_INTERVAL
        safe_interval = max(raw_interval, MIN_UPDATE_INTERVAL)
        if safe_interval != raw_interval:
            _LOGGER.warning(
                "Update interval %ds is below the safe threshold of %ds. "
                "Overriding to %ds to prevent MarineTraffic IP ban.",
                raw_interval,
                MIN_UPDATE_INTERVAL,
                MIN_UPDATE_INTERVAL,
            )
        update_interval = timedelta(seconds=safe_interval)

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
    # Public helpers
    # ------------------------------------------------------------------

    def get_position_history(self, mmsi: str) -> list[dict]:
        """Return the stored position history for a vessel (oldest first).

        Each entry is a dict with keys ``latitude``, ``longitude``, and
        ``timestamp`` (ISO-8601 string).  Returns an empty list when no
        history has been recorded for the given MMSI.
        """
        return list(self._position_history.get(mmsi, []))

    @property
    def statistics(self) -> AreaStatistics:
        """Return the current historical statistics for the tracked area."""
        return self._statistics

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

        # Apply vessel type filter if configured.
        # Stored values may be strings (from the SelectSelector) or ints; normalise to int.
        raw_filter = config.get(CONF_FILTER_VESSEL_TYPES, [])
        allowed_types: list[int] = [int(t) for t in raw_filter] if raw_filter else []
        if allowed_types:
            before = len(fresh)
            fresh = [v for v in fresh if v.vessel_type in allowed_types]
            _LOGGER.debug(
                "Vessel type filter applied: %d → %d vessel(s) (allowed types: %s)",
                before,
                len(fresh),
                allowed_types,
            )

        now = datetime.now(UTC)

        # Snapshot of MMSIs tracked before this update cycle.
        previous_mmsis: set[str] = set(self._vessels.keys())

        # Merge fresh observations into the registry
        for vessel in fresh:
            updated = replace(vessel, last_seen=now)
            self._vessels[updated.mmsi] = updated

        # Record position history for each observed vessel.
        for vessel in fresh:
            pos_entry = {
                "latitude": vessel.latitude,
                "longitude": vessel.longitude,
                "timestamp": now.isoformat(),
            }
            history = self._position_history.setdefault(vessel.mmsi, [])
            history.append(pos_entry)
            if len(history) > DEFAULT_HISTORY_SIZE:
                self._position_history[vessel.mmsi] = history[-DEFAULT_HISTORY_SIZE:]

        # Update statistics for each observed vessel.
        self._update_statistics(fresh, now)

        # Fire entered events for vessels that are new this cycle.
        for vessel in fresh:
            if vessel.mmsi not in previous_mmsis:
                _LOGGER.debug("Vessel entered: MMSI=%s name=%s", vessel.mmsi, vessel.name)
                self.hass.bus.async_fire(
                    "marinetraffic_vessel_entered",
                    self._vessel_event_payload(vessel),
                )

        # Remove vessels not seen within the stale timeout
        stale_cutoff = now - timedelta(seconds=self.stale_timeout_seconds)
        stale = [mmsi for mmsi, v in self._vessels.items() if v.last_seen < stale_cutoff]
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
            # Accumulate time-in-zone when the vessel exits.
            self._accumulate_time_in_zone(mmsi, now)
            del self._vessels[mmsi]
            self._position_history.pop(mmsi, None)

        _LOGGER.debug(
            "Poll complete: %d active vessel(s), %d stale removed",
            len(self._vessels),
            len(stale),
        )
        return dict(self._vessels)

    # ------------------------------------------------------------------
    # Statistics helpers
    # ------------------------------------------------------------------

    def _update_statistics(self, vessels: list[VesselData], now: datetime) -> None:
        """Update all historical statistics for the current set of observed vessels."""
        stats = self._statistics
        hour = now.hour
        day = now.weekday()  # 0 = Monday, 6 = Sunday

        for vessel in vessels:
            mmsi = vessel.mmsi

            # Always keep the latest name.
            stats.vessel_names[mmsi] = vessel.name

            # Record the entry time if this is the vessel's first appearance
            # (so we can later compute time-in-zone when it departs).
            if mmsi not in self._entry_times:
                self._entry_times[mmsi] = now
                # Increment visit count on each new entry.
                stats.visit_counts[mmsi] = stats.visit_counts.get(mmsi, 0) + 1

            # Traffic pattern: count each vessel-observation per bucket.
            stats.hourly_counts[hour] += 1
            stats.daily_counts[day] += 1

            # Speed record.
            if vessel.speed is not None:
                if stats.speed_record is None or vessel.speed > stats.speed_record.value:
                    stats.speed_record = VesselRecord(
                        mmsi=mmsi,
                        name=vessel.name,
                        value=vessel.speed,
                        recorded_at=now.isoformat(),
                    )

            # Size records (only vessels with a valid positive length).
            if vessel.length is not None and vessel.length > 0:
                length = float(vessel.length)
                if stats.largest_vessel is None or length > stats.largest_vessel.value:
                    stats.largest_vessel = VesselRecord(
                        mmsi=mmsi,
                        name=vessel.name,
                        value=length,
                        recorded_at=now.isoformat(),
                    )
                if stats.smallest_vessel is None or length < stats.smallest_vessel.value:
                    stats.smallest_vessel = VesselRecord(
                        mmsi=mmsi,
                        name=vessel.name,
                        value=length,
                        recorded_at=now.isoformat(),
                    )

    def _accumulate_time_in_zone(self, mmsi: str, now: datetime) -> None:
        """Add the elapsed time for a departing vessel to the cumulative total."""
        entry_time = self._entry_times.pop(mmsi, None)
        if entry_time is None:
            return
        elapsed = (now - entry_time).total_seconds()
        self._statistics.total_time_seconds[mmsi] = (
            self._statistics.total_time_seconds.get(mmsi, 0.0) + elapsed
        )
