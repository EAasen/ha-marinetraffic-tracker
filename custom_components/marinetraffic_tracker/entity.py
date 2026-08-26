"""Shared base entity for MarineTraffic Tracker.

All entities produced by this integration inherit from this class so that
they share a common virtual "device" (one per config entry) and follow the
same coordinator lifecycle.

Per-vessel entities (``MarineTrafficVesselSensor``,
``MarineTrafficVesselTracker``) are expected to:

- Implement an ``available`` property that returns ``False`` once the
  coordinator has purged the vessel as stale (not seen within the configured
  ``stale_timeout``).
- Expose a ``last_seen`` key in ``extra_state_attributes`` by reading
  ``VesselData.last_seen`` from the coordinator data dict.  This lets users
  build automations that react to vessels going silent.
"""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VESSEL_TYPE_MAP
from .coordinator import MarineTrafficCoordinator


class MarineTrafficEntity(CoordinatorEntity[MarineTrafficCoordinator]):
    """Base entity class for MarineTraffic Tracker.

    Entities are grouped under a single virtual device per config entry so
    they appear together in the Home Assistant device registry.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MarineTrafficCoordinator,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the shared virtual tracker device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="MarineTraffic Tracker",
            manufacturer="MarineTraffic",
            model="Live Map Tracker",
            configuration_url="https://www.marinetraffic.com/",
        )


class MarineTrafficVesselEntity(MarineTrafficEntity):
    """Base entity class for per-vessel entities.

    Each vessel gets its own device in the Home Assistant device registry so
    its sensor and device-tracker entities are grouped together and can be
    identified by vessel name, MMSI, and type.
    """

    def __init__(
        self,
        coordinator: MarineTrafficCoordinator,
        entry_id: str,
        mmsi: str,
    ) -> None:
        super().__init__(coordinator, entry_id)
        self._mmsi = mmsi

    @property
    def device_info(self) -> DeviceInfo:
        """Return per-vessel device info.

        The device identifier is unique per (integration entry, MMSI) pair so
        that the sensor and device-tracker for the same vessel are grouped
        under one device.  The device name and model are kept up-to-date with
        the latest coordinator data.
        """
        vessel = (self.coordinator.data or {}).get(self._mmsi)
        name = vessel.name if vessel else f"Vessel {self._mmsi}"
        model = (
            VESSEL_TYPE_MAP.get(vessel.vessel_type, f"Type {vessel.vessel_type}")
            if vessel
            else None
        )
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry_id}_{self._mmsi}")},
            name=name,
            manufacturer="MarineTraffic Tracker",
            model=model,
            via_device=(DOMAIN, self._entry_id),
        )
