"""Device tracker platform for the MarineTraffic Tracker integration.

Provides one :class:`MarineTrafficVesselTracker` entity per AIS vessel
currently tracked by the coordinator.  Entities are created dynamically
the first time a vessel's MMSI is observed and become unavailable (but
remain in the entity registry) once the vessel ages out of the coordinator's
active vessel dict.

Map integration
---------------
``TrackerEntity`` exposes ``latitude``/``longitude`` so HA's built-in Map
card and the device-tracker integration display each vessel as a pin on the
map automatically.  No additional lovelace configuration is required.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.device_tracker import TrackerEntity
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import VesselData
from .const import (
    ATTR_CALLSIGN,
    ATTR_COURSE,
    ATTR_DESTINATION,
    ATTR_ETA,
    ATTR_FLAG,
    ATTR_HEADING,
    ATTR_IMO,
    ATTR_LAST_SEEN,
    ATTR_LENGTH,
    ATTR_MMSI,
    ATTR_ORIGIN,
    ATTR_SPEED,
    ATTR_STATUS,
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
    """Set up device tracker entities from a config entry."""
    coordinator: MarineTrafficCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Keep track of which MMSIs already have a tracker entity so we don't
    # create duplicates on subsequent coordinator updates.
    known_mmsis: set[str] = set()

    @callback
    def _handle_coordinator_update() -> None:
        """Register new vessel tracker entities for any newly-seen vessels."""
        vessels: dict[str, VesselData] = coordinator.data or {}
        new_mmsis = set(vessels) - known_mmsis
        if not new_mmsis:
            _LOGGER.debug("No new vessels to register as device trackers")
            return

        new_entities = [
            MarineTrafficVesselTracker(coordinator, entry.entry_id, mmsi)
            for mmsi in new_mmsis
        ]
        known_mmsis.update(new_mmsis)
        _LOGGER.debug(
            "Adding %d new vessel tracker entity/entities: %s",
            len(new_entities),
            sorted(new_mmsis),
        )
        async_add_entities(new_entities)

    # Register the listener so future updates trigger dynamic entity creation.
    entry.async_on_unload(coordinator.async_add_listener(_handle_coordinator_update))

    # Process vessels already present in the coordinator on initial setup.
    _handle_coordinator_update()


class MarineTrafficVesselTracker(MarineTrafficEntity, TrackerEntity):
    """A device tracker entity representing a single AIS-tracked vessel.

    The entity becomes *unavailable* once the coordinator has purged it from
    the active vessel registry (i.e. it has not been observed within the
    configured stale timeout, default 10 minutes).  The entity remains in the
    entity registry so that its history is preserved.

    AIS data fields exposed as state attributes
    -------------------------------------------
    All PRD-required attributes are present:
    mmsi, vessel_name, vessel_type, speed_knots, heading, course, status,
    origin, destination, eta, latitude, longitude, imo, callsign, length,
    flag, last_seen.

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
        """Initialise the tracker entity for the given MMSI."""
        super().__init__(coordinator, entry_id)
        self._mmsi = mmsi
        self._attr_unique_id = f"{entry_id}_tracker_{mmsi}"

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    @property
    def _vessel(self) -> VesselData | None:
        """Return current :class:`VesselData` or ``None`` if vessel is stale."""
        return (self.coordinator.data or {}).get(self._mmsi)

    # ------------------------------------------------------------------
    # TrackerEntity interface (required for map placement)
    # ------------------------------------------------------------------

    @property
    def source_type(self) -> SourceType:
        """AIS is satellite/GPS-based positioning."""
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """Return the vessel's current latitude."""
        vessel = self._vessel
        return vessel.latitude if vessel else None

    @property
    def longitude(self) -> float | None:
        """Return the vessel's current longitude."""
        vessel = self._vessel
        return vessel.longitude if vessel else None

    @property
    def location_accuracy(self) -> int:
        """AIS Class A transponders report position to within ~10 metres."""
        return 10

    # ------------------------------------------------------------------
    # Entity interface
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """Return True while the vessel is in the coordinator's active registry."""
        return self.coordinator.last_update_success and self._vessel is not None

    @property
    def name(self) -> str:
        """Return the vessel name, falling back to the MMSI when unknown."""
        vessel = self._vessel
        return vessel.name if vessel else f"Vessel {self._mmsi}"

    @property
    def icon(self) -> str:
        """Return an MDI icon appropriate for the vessel's AIS type code."""
        vessel = self._vessel
        if vessel is None:
            return DEFAULT_VESSEL_ICON
        return VESSEL_TYPE_ICONS.get(vessel.vessel_type, DEFAULT_VESSEL_ICON)

    @property
    def entity_picture(self) -> str | None:
        """Return a MarineTraffic thumbnail URL for this vessel, or None."""
        return vessel_photo_url(self._mmsi)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return full AIS telemetry as HA state attributes.

        All PRD-required fields are present.  Fields that the current parser
        stub has not yet populated will appear as ``None``.
        """
        vessel = self._vessel
        if vessel is None:
            return {}

        _LOGGER.debug(
            "Returning attributes for vessel MMSI=%s name=%s",
            vessel.mmsi,
            vessel.name,
        )

        return {
            ATTR_MMSI: vessel.mmsi,
            ATTR_VESSEL_NAME: vessel.name,
            ATTR_VESSEL_TYPE: VESSEL_TYPE_MAP.get(vessel.vessel_type, f"Type {vessel.vessel_type}"),
            ATTR_SPEED: vessel.speed,
            ATTR_HEADING: vessel.heading,
            ATTR_COURSE: vessel.course,
            ATTR_STATUS: vessel.status,
            ATTR_ORIGIN: vessel.origin,
            ATTR_DESTINATION: vessel.destination,
            ATTR_ETA: vessel.eta,
            ATTR_IMO: vessel.imo,
            ATTR_CALLSIGN: vessel.callsign,
            ATTR_LENGTH: vessel.length,
            ATTR_FLAG: vessel.flag,
            ATTR_LAST_SEEN: vessel.last_seen.isoformat(),
        }
