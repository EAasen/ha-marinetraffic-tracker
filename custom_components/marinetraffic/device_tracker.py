"""Device tracker platform for the MarineTraffic Tracker integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.device_tracker import TrackerEntity
from homeassistant.components.device_tracker.const import SourceType
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up device tracker entities from a config entry."""
    coordinator: MarineTrafficCoordinator = hass.data[DOMAIN][entry.entry_id]
    known_mmsi: set[str] = set()

    @callback
    def _handle_coordinator_update() -> None:
        vessels: dict[str, Any] = coordinator.data.get("vessels", {})
        new_entities: list[MarineTrafficVesselTracker] = []
        for mmsi in vessels:
            if mmsi not in known_mmsi:
                known_mmsi.add(mmsi)
                new_entities.append(
                    MarineTrafficVesselTracker(coordinator, entry, mmsi)
                )
        if new_entities:
            async_add_entities(new_entities)

    coordinator.async_add_listener(_handle_coordinator_update)
    _handle_coordinator_update()


class MarineTrafficVesselTracker(
    CoordinatorEntity[MarineTrafficCoordinator], TrackerEntity
):
    """A device tracker entity representing a single AIS-tracked vessel."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:ferry"

    def __init__(
        self,
        coordinator: MarineTrafficCoordinator,
        entry: ConfigEntry,
        mmsi: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._mmsi = mmsi
        self._attr_unique_id = f"{entry.entry_id}_tracker_{mmsi}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="MarineTraffic",
            model="Live Vessel Tracker",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def _vessel(self) -> dict[str, Any] | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("vessels", {}).get(self._mmsi)

    # ------------------------------------------------------------------
    # TrackerEntity interface
    # ------------------------------------------------------------------

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        v = self._vessel
        return v.get("latitude") if v else None

    @property
    def longitude(self) -> float | None:
        v = self._vessel
        return v.get("longitude") if v else None

    @property
    def location_accuracy(self) -> int:
        """AIS Class A transponders have ~10 m accuracy."""
        return 10

    # ------------------------------------------------------------------
    # Entity interface
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        return self._vessel is not None

    @property
    def name(self) -> str:
        v = self._vessel
        if v:
            return v.get("name") or self._mmsi
        return self._mmsi

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
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
            "distance_km": v.get("distance_km"),
        }
