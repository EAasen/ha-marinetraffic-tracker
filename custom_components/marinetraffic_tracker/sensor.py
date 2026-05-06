"""Sensor platform for MarineTraffic Tracker.

Provides:
- ``MarineTrafficCountSensor`` — global count of active vessels in the area.
- ``MarineTrafficVesselSensor`` — one entity per tracked vessel with full
  telemetry exposed as state attributes (suitable for map cards and
  automations).

New per-vessel sensors are registered dynamically via a coordinator listener
each time a previously-unseen vessel appears.  Vessels that age out of the
registry become unavailable but remain in the entity registry so history is
preserved.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import VesselData
from .const import (
    ATTR_BEAM,
    ATTR_BUSIEST_DAY,
    ATTR_BUSIEST_HOUR,
    ATTR_CALLSIGN,
    ATTR_COURSE,
    ATTR_DAILY_COUNTS,
    ATTR_DESTINATION,
    ATTR_DRAUGHT,
    ATTR_ETA,
    ATTR_FLAG,
    ATTR_HEADING,
    ATTR_HOURLY_COUNTS,
    ATTR_IMO,
    ATTR_LARGEST_VESSEL,
    ATTR_LAST_SEEN,
    ATTR_LENGTH,
    ATTR_LONGEST_RESIDENT,
    ATTR_MMSI,
    ATTR_MOST_FREQUENT_VISITOR,
    ATTR_ORIGIN,
    ATTR_POSITION_HISTORY,
    ATTR_RATE_OF_TURN,
    ATTR_SMALLEST_VESSEL,
    ATTR_SPEED,
    ATTR_SPEED_RECORD,
    ATTR_STATUS,
    ATTR_TOTAL_VESSELS_SEEN,
    ATTR_VESSEL_NAME,
    ATTR_VESSEL_TYPE,
    DEFAULT_VESSEL_ICON,
    DOMAIN,
    VESSEL_TYPE_ICONS,
    VESSEL_TYPE_MAP,
    vessel_photo_url,
)
from .coordinator import MarineTrafficCoordinator
from .entity import MarineTrafficEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities for a config entry."""
    coordinator: MarineTrafficCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Track which MMSIs we have already created entities for.
    known_mmsis: set[str] = set()

    # Always add the global count sensor and statistics sensor immediately.
    async_add_entities([
        MarineTrafficCountSensor(coordinator, entry.entry_id),
        MarineTrafficStatisticsSensor(coordinator, entry.entry_id),
    ])

    @callback
    def _handle_coordinator_update() -> None:
        """Register new per-vessel sensors for any newly-seen vessels."""
        vessels: dict[str, VesselData] = coordinator.data or {}
        new_mmsis = set(vessels) - known_mmsis
        if not new_mmsis:
            return
        new_entities = [
            MarineTrafficVesselSensor(coordinator, entry.entry_id, mmsi) for mmsi in new_mmsis
        ]
        known_mmsis.update(new_mmsis)
        async_add_entities(new_entities)

    # Register listener so future updates trigger dynamic entity creation.
    entry.async_on_unload(coordinator.async_add_listener(_handle_coordinator_update))

    # Process any vessels already present in coordinator data.
    _handle_coordinator_update()


# ---------------------------------------------------------------------------
# Global count sensor
# ---------------------------------------------------------------------------


class MarineTrafficCountSensor(MarineTrafficEntity, SensorEntity):
    """Sensor reporting the total number of vessels in the tracking area."""

    _attr_icon = "mdi:counter"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "vessels"
    _attr_translation_key = "vessel_count"

    def __init__(
        self,
        coordinator: MarineTrafficCoordinator,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_count"
        self._attr_name = "Vessel Count"

    @property
    def native_value(self) -> int:
        """Return the number of currently-active vessels."""
        return len(self.coordinator.data or {})

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the active vessel list for dashboard table and map cards.

        ``vessel_mmsis`` — sorted list of active MMSI strings (unchanged).
        ``vessels`` — structured list of vessel snapshots suitable for
        flex-table-card and similar Lovelace table cards.  Each entry
        contains the fields most useful for a vessel information table:
        name, MMSI, type, speed, status, position, heading, destination, and
        a MarineTraffic thumbnail URL.
        """
        vessels_data = self.coordinator.data or {}
        vessels_list = [
            {
                ATTR_MMSI: v.mmsi,
                ATTR_VESSEL_NAME: v.name,
                ATTR_VESSEL_TYPE: VESSEL_TYPE_MAP.get(v.vessel_type, f"Type {v.vessel_type}"),
                ATTR_SPEED: v.speed,
                ATTR_STATUS: v.status,
                ATTR_HEADING: v.heading,
                ATTR_DESTINATION: v.destination,
                "latitude": v.latitude,
                "longitude": v.longitude,
                "entity_picture": vessel_photo_url(v.mmsi),
            }
            for v in sorted(vessels_data.values(), key=lambda x: x.name)
        ]
        return {
            "vessel_mmsis": sorted(vessels_data.keys()),
            "vessels": vessels_list,
        }


# ---------------------------------------------------------------------------
# Per-vessel sensor
# ---------------------------------------------------------------------------


class MarineTrafficVesselSensor(MarineTrafficEntity, SensorEntity):
    """Sensor representing a single tracked vessel.

    State: current navigational status (e.g. "Under Way Using Engine").
    Attributes: full telemetry for use in map cards and automations.

    EXTENSION POINT: Add richer attributes here (e.g. draught, destination
    confidence) as the client parser is extended to provide them.

    Disabled by default to prevent entity-list explosion in busy ports or
    high-traffic areas.  Users can enable individual vessel entities manually
    via the Home Assistant entity registry.
    """

    # Disabled by default — prevents entity explosion in high-traffic areas.
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: MarineTrafficCoordinator,
        entry_id: str,
        mmsi: str,
    ) -> None:
        super().__init__(coordinator, entry_id)
        self._mmsi = mmsi
        self._attr_unique_id = f"{entry_id}_vessel_{mmsi}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _vessel(self) -> VesselData | None:
        """Return current vessel data, or None if the vessel has gone stale."""
        return (self.coordinator.data or {}).get(self._mmsi)

    # ------------------------------------------------------------------
    # Entity properties
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """Entity is unavailable once the vessel has been purged as stale."""
        return self.coordinator.last_update_success and self._vessel is not None

    @property
    def name(self) -> str:
        """Return the vessel name (falls back to MMSI if name is unknown)."""
        vessel = self._vessel
        return vessel.name if vessel else f"Vessel {self._mmsi}"

    @property
    def icon(self) -> str:
        """Return an MDI icon that reflects the vessel's AIS type code."""
        vessel = self._vessel
        if vessel is None:
            return DEFAULT_VESSEL_ICON
        return VESSEL_TYPE_ICONS.get(vessel.vessel_type, DEFAULT_VESSEL_ICON)

    @property
    def entity_picture(self) -> str | None:
        """Return a MarineTraffic thumbnail URL for this vessel, or None."""
        return vessel_photo_url(self._mmsi)

    @property
    def native_value(self) -> str | None:
        """Navigational status is used as the primary entity state."""
        vessel = self._vessel
        return vessel.status if vessel else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return full vessel telemetry as state attributes."""
        vessel = self._vessel
        if vessel is None:
            return {}
        return {
            ATTR_MMSI: vessel.mmsi,
            ATTR_VESSEL_NAME: vessel.name,
            ATTR_VESSEL_TYPE: VESSEL_TYPE_MAP.get(vessel.vessel_type, f"Type {vessel.vessel_type}"),
            "latitude": vessel.latitude,
            "longitude": vessel.longitude,
            ATTR_HEADING: vessel.heading,
            ATTR_COURSE: vessel.course,
            ATTR_SPEED: vessel.speed,
            ATTR_STATUS: vessel.status,
            ATTR_ORIGIN: vessel.origin,
            ATTR_DESTINATION: vessel.destination,
            ATTR_ETA: vessel.eta,
            ATTR_IMO: vessel.imo,
            ATTR_CALLSIGN: vessel.callsign,
            ATTR_LENGTH: vessel.length,
            ATTR_FLAG: vessel.flag,
            ATTR_DRAUGHT: vessel.draught,
            ATTR_RATE_OF_TURN: vessel.rate_of_turn,
            ATTR_BEAM: vessel.beam,
            ATTR_LAST_SEEN: vessel.last_seen.isoformat(),
            ATTR_POSITION_HISTORY: self.coordinator.get_position_history(self._mmsi),
        }


# ---------------------------------------------------------------------------
# Statistics / highscore sensor
# ---------------------------------------------------------------------------


class MarineTrafficStatisticsSensor(MarineTrafficEntity, SensorEntity):
    """Sensor exposing historical maritime statistics for the tracked area.

    State: total number of unique vessels ever seen in the tracking area.
    Attributes:
        most_frequent_visitor   — vessel with the highest entry count.
        longest_resident        — vessel with the most cumulative time in zone.
        speed_record            — highest speed ever recorded in the area.
        largest_vessel          — largest ship by length seen in the area.
        smallest_vessel         — smallest ship by length seen in the area.
        busiest_hour            — hour of the day (0–23) with most traffic.
        busiest_day             — weekday (0=Mon … 6=Sun) with most traffic.
        hourly_counts           — list of 24 observation counts, one per hour.
        daily_counts            — list of 7 observation counts, one per weekday.
        total_vessels_seen      — total unique vessels ever observed (= state).
    """

    _attr_icon = "mdi:trophy"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "vessels"

    def __init__(
        self,
        coordinator: MarineTrafficCoordinator,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_statistics"
        self._attr_name = "Maritime Statistics"

    @property
    def native_value(self) -> int:
        """Return the total number of unique vessels ever observed."""
        return len(self.coordinator.statistics.visit_counts)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return all historical statistics as a flat attribute dict."""
        stats_dict = self.coordinator.statistics.to_dict()
        return {
            ATTR_MOST_FREQUENT_VISITOR: stats_dict["most_frequent_visitor"],
            ATTR_LONGEST_RESIDENT: stats_dict["longest_resident"],
            ATTR_SPEED_RECORD: stats_dict["speed_record"],
            ATTR_LARGEST_VESSEL: stats_dict["largest_vessel"],
            ATTR_SMALLEST_VESSEL: stats_dict["smallest_vessel"],
            ATTR_BUSIEST_HOUR: stats_dict["busiest_hour"],
            ATTR_BUSIEST_DAY: stats_dict["busiest_day"],
            ATTR_HOURLY_COUNTS: stats_dict["hourly_counts"],
            ATTR_DAILY_COUNTS: stats_dict["daily_counts"],
            ATTR_TOTAL_VESSELS_SEEN: stats_dict["total_vessels_seen"],
        }
