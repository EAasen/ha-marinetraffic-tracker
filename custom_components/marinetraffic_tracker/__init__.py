"""MarineTraffic Tracker — Home Assistant custom integration.

Domain: marinetraffic_tracker

Entry point for integration setup and teardown.  The coordinator is created
here so all platforms share one polling instance per config entry.
"""

from __future__ import annotations

import logging

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .aishub_client import AISHubClient
from .client import MarineTrafficClient
from .const import (
    CONF_AISHUB_API_KEY,
    CONF_DATA_SOURCE,
    CONF_EXTRA_SOURCES,
    CONF_FALLBACK_SOURCE,
    DATA_SOURCE_AISHUB,
    DATA_SOURCE_VESSELFINDER,
    DEFAULT_DATA_SOURCE,
    DEFAULT_FALLBACK_SOURCE,
    DOMAIN,
    FALLBACK_SOURCE_NONE,
)
from .coordinator import MarineTrafficCoordinator, VesselClient
from .vesselfinder_client import VesselFinderClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.DEVICE_TRACKER]


def _build_client(
    source: str,
    session: aiohttp.ClientSession,
    api_key: str,
) -> VesselClient:
    """Instantiate the appropriate vessel data client for *source*."""
    if source == DATA_SOURCE_AISHUB:
        return AISHubClient(session, api_key=api_key)
    if source == DATA_SOURCE_VESSELFINDER:
        return VesselFinderClient(session)
    # Default / DATA_SOURCE_MARINETRAFFIC
    return MarineTrafficClient(session)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MarineTraffic Tracker from a config entry."""
    session = async_get_clientsession(hass)

    config: dict = {**entry.data, **entry.options}
    primary_source: str = config.get(CONF_DATA_SOURCE, DEFAULT_DATA_SOURCE)
    fallback_source: str = config.get(CONF_FALLBACK_SOURCE, DEFAULT_FALLBACK_SOURCE)
    extra_sources: list[str] = list(config.get(CONF_EXTRA_SOURCES, []))
    aishub_api_key: str = str(config.get(CONF_AISHUB_API_KEY, "")).strip()

    client = _build_client(primary_source, session, aishub_api_key)
    _LOGGER.debug("Primary data source: %s", primary_source)

    # Build extra clients for simultaneous multi-source polling.
    extra_clients: list[VesselClient] = []
    for source in extra_sources:
        if source and source != primary_source:
            extra_clients.append(_build_client(source, session, aishub_api_key))
            _LOGGER.debug("Extra data source: %s", source)

    fallback_client = None
    if fallback_source and fallback_source != FALLBACK_SOURCE_NONE:
        # Only build a fallback if it isn't already in the extra clients list.
        if fallback_source not in extra_sources and fallback_source != primary_source:
            fallback_client = _build_client(fallback_source, session, aishub_api_key)
            _LOGGER.debug("Fallback data source: %s", fallback_source)

    coordinator = MarineTrafficCoordinator(
        hass, entry, client, fallback_client=fallback_client, extra_clients=extra_clients
    )

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
