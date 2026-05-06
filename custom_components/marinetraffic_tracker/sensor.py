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
from .const import DEFAULT_VESSEL_ICON, DOMAIN, VESSEL_TYPE_ICONS, VESSEL_TYPE_MAP, vessel_photo_url
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

    # Always add the global count sensor immediately.
    async_add_entities([MarineTrafficCountSensor(coordinator, entry.entry_id)])

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
        """Expose the list of active MMSIs for easy dashboard filtering."""
        return {"vessel_mmsis": sorted((self.coordinator.data or {}).keys())}


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
            "mmsi": vessel.mmsi,
            "imo": vessel.imo,
            "vessel_type": VESSEL_TYPE_MAP.get(vessel.vessel_type, f"Type {vessel.vessel_type}"),
            "latitude": vessel.latitude,
            "longitude": vessel.longitude,
            "heading": vessel.heading,
            "course": vessel.course,
            "speed_knots": vessel.speed,
            "status": vessel.status,
            "origin": vessel.origin,
            "destination": vessel.destination,
            "eta": vessel.eta,
            "last_seen": vessel.last_seen.isoformat(),
        }
