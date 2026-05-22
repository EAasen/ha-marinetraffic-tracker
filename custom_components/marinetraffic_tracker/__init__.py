"""Norwegian Maritime Tracker — Home Assistant custom integration.

Domain: marinetraffic_tracker

Entry point for integration setup and teardown.  The coordinator is created
here so all platforms share one polling instance per config entry.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_BARENTSWATCH_CLIENT_ID,
    CONF_BARENTSWATCH_CLIENT_SECRET,
    DOMAIN,
)
from .coordinator import MarineTrafficCoordinator, VesselClient
from .kystverket_client import KystverketClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.DEVICE_TRACKER]


def _build_client(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> VesselClient:
    """Instantiate the active Kystverket client."""
    config: dict = {**entry.data, **entry.options}
    return KystverketClient(
        async_get_clientsession(hass),
        client_id=str(config.get(CONF_BARENTSWATCH_CLIENT_ID, "")).strip(),
        client_secret=str(config.get(CONF_BARENTSWATCH_CLIENT_SECRET, "")).strip(),
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Norwegian Maritime Tracker from a config entry."""
    client = _build_client(hass, entry)
    coordinator = MarineTrafficCoordinator(hass, entry, client)

    # Perform the first refresh so entities are available immediately.
    # If the initial fetch fails, the setup is aborted and HA will retry.
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload the entry when options are changed so the new interval takes effect.
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry and clean up resources."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)
