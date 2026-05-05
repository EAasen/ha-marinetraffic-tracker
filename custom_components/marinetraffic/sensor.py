"""Sensor platform for the MarineTraffic Tracker integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_CALLSIGN,
    ATTR_COURSE,
    ATTR_DESTINATION,
    ATTR_ETA,
    ATTR_FLAG,
    ATTR_HEADING,
    ATTR_IMO,
    ATTR_LENGTH,
    ATTR_MMSI,
    ATTR_SPEED,
    ATTR_STATUS,
    ATTR_VESSEL_NAME,
    ATTR_VESSEL_TYPE,
    DOMAIN,
    NAV_STATUS_MAP,
    VESSEL_TYPE_MAP,
)
from .coordinator import MarineTrafficCoordinator

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Platform setup
# ---------------------------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities from a config entry."""
    coordinator: MarineTrafficCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Track which vessel sensors have already been created.
    known_mmsi: set[str] = set()

    # The aggregated count sensor is static — create it once.
    count_sensor = MarineTrafficCountSensor(coordinator, entry)
    async_add_entities([count_sensor])

    @callback
    def _handle_coordinator_update() -> None:
        """Add new vessel sensors when new vessels appear."""
        vessels: dict[str, Any] = coordinator.data.get("vessels", {})
        new_entities: list[MarineTrafficVesselSensor] = []
        for mmsi, vessel in vessels.items():
            if mmsi not in known_mmsi:
                known_mmsi.add(mmsi)
                new_entities.append(
                    MarineTrafficVesselSensor(coordinator, entry, mmsi)
                )
        if new_entities:
            async_add_entities(new_entities)

    # Register the callback and fire it once so we handle the initial data.
    coordinator.async_add_listener(_handle_coordinator_update)
    _handle_coordinator_update()


# ---------------------------------------------------------------------------
# Count sensor
# ---------------------------------------------------------------------------


class MarineTrafficCountSensor(CoordinatorEntity[MarineTrafficCoordinator], SensorEntity):
    """Total number of vessels currently tracked within the boundary."""

    _attr_icon = "mdi:ferry"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "vessels"
    _attr_has_entity_name = True
    _attr_name = "Vessel Count"

    def __init__(
        self,
        coordinator: MarineTrafficCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_count"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="MarineTraffic",
            model="Live Vessel Tracker",
        )

    @property
    def native_value(self) -> int:
        """Return the number of tracked vessels."""
        if self.coordinator.data is None:
            return 0
        return self.coordinator.data.get("count", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra info about the tracked area."""
        return {
            "latitude": self.coordinator.latitude,
            "longitude": self.coordinator.longitude,
            "radius_km": self.coordinator.radius_km,
        }


# ---------------------------------------------------------------------------
# Per-vessel sensor
# ---------------------------------------------------------------------------


class MarineTrafficVesselSensor(CoordinatorEntity[MarineTrafficCoordinator], SensorEntity):
    """Sensor representing an individual tracked vessel."""

    _attr_icon = "mdi:ferry"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "kn"
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MarineTrafficCoordinator,
        entry: ConfigEntry,
        mmsi: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._mmsi = mmsi
        self._attr_unique_id = f"{entry.entry_id}_vessel_{mmsi}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="MarineTraffic",
            model="Live Vessel Tracker",
        )

    @property
    def _vessel(self) -> dict[str, Any] | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("vessels", {}).get(self._mmsi)

    @property
    def available(self) -> bool:
        """Mark unavailable when the vessel has left the boundary."""
        return self._vessel is not None

    @property
    def name(self) -> str:
        """Return the vessel name (or MMSI fallback)."""
        v = self._vessel
        if v:
            return v.get("name") or self._mmsi
        return self._mmsi

    @property
    def native_value(self) -> float | None:
        """Return the vessel's speed in knots as the sensor state."""
        v = self._vessel
        return v.get("speed_knots") if v else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return full vessel telemetry as attributes."""
        v = self._vessel
        if not v:
            return {}
        ship_type_code = v.get("ship_type", 0)
        nav_status_code = v.get("nav_status", 15)
        return {
            ATTR_MMSI: v.get("mmsi"),
            ATTR_VESSEL_NAME: v.get("name"),
            ATTR_VESSEL_TYPE: VESSEL_TYPE_MAP.get(ship_type_code, f"Type {ship_type_code}"),
            ATTR_STATUS: NAV_STATUS_MAP.get(nav_status_code, "Undefined"),
            ATTR_SPEED: v.get("speed_knots"),
            ATTR_HEADING: v.get("heading"),
            ATTR_COURSE: v.get("course"),
            ATTR_DESTINATION: v.get("destination"),
            ATTR_ETA: v.get("eta"),
            ATTR_FLAG: v.get("flag"),
            ATTR_IMO: v.get("imo"),
            ATTR_CALLSIGN: v.get("callsign"),
            ATTR_LENGTH: v.get("length"),
            "latitude": v.get("latitude"),
            "longitude": v.get("longitude"),
            "distance_km": v.get("distance_km"),
        }
