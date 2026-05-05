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

from .const import DOMAIN, VESSEL_PHOTO_URL
from .coordinator import MarineTrafficCoordinator


def vessel_photo_url(mmsi: str | None) -> str | None:
    """Return a MarineTraffic photo URL for the given MMSI, or None.

    A valid MMSI is exactly 9 ASCII digits.  Any other value (None, empty
    string, wrong length, non-numeric) returns ``None`` so callers can safely
    use the result as ``entity_picture`` without additional guards.
    """
    if not mmsi or not mmsi.isdigit() or len(mmsi) != 9:
        return None
    return VESSEL_PHOTO_URL.format(mmsi=mmsi)


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
