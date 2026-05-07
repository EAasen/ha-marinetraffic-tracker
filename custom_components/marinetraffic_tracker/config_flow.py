"""Config flow for MarineTraffic Tracker.

The flow is split into three steps so the UI remains focused:

1. ``user``   — choose tracking mode (radius or bounding box).
2. ``radius`` / ``box`` — enter the geographic parameters for the chosen mode.
3. ``timing`` — configure the update interval and stale vessel timeout.

An options flow (``MarineTrafficOptionsFlow``) allows users to adjust the
timing parameters after the integration has been set up without needing to
remove and re-add it.  Geographic parameters require a re-setup.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector

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
    DEFAULT_RADIUS_KM,
    DEFAULT_STALE_TIMEOUT,
    DEFAULT_TRACKING_MODE,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MIN_UPDATE_INTERVAL,
    TRACKING_MODE_RADIUS,
    TRACKING_MODES,
    VESSEL_TYPE_LABELS,
)

_LOGGER = logging.getLogger(__name__)

# Internal key for the location selector composite field (lat + lon + radius).
# This is unpacked into CONF_LATITUDE / CONF_LONGITUDE / CONF_RADIUS_KM before
# the data is stored, so it never appears in the config entry.
_CONF_LOCATION = "location"

# The LocationSelector returns radius in metres; we store it in kilometres.
_METRES_PER_KM = 1000.0

# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

_STEP_MODE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TRACKING_MODE, default=DEFAULT_TRACKING_MODE): vol.In(TRACKING_MODES),
    }
)


def _radius_schema(defaults: dict[str, Any]) -> vol.Schema:
    # Callers must pre-populate CONF_LATITUDE / CONF_LONGITUDE with HA home
    # coordinates (see async_step_radius), so the 0.0 fallback here is only
    # a safety net for misconfigured HA instances where home location is unset.
    lat = defaults.get(CONF_LATITUDE, 0.0)
    lon = defaults.get(CONF_LONGITUDE, 0.0)
    radius_m = defaults.get(CONF_RADIUS_KM, DEFAULT_RADIUS_KM) * _METRES_PER_KM
    return vol.Schema(
        {
            vol.Required(
                _CONF_LOCATION,
                default={"latitude": lat, "longitude": lon, "radius": radius_m},
            ): selector.LocationSelector(
                selector.LocationSelectorConfig(radius=True, icon="mdi:ship")
            ),
        }
    )


def _box_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_NORTH, default=defaults.get(CONF_NORTH, 0.0)): vol.All(
                vol.Coerce(float), vol.Range(min=-90, max=90)
            ),
            vol.Required(CONF_EAST, default=defaults.get(CONF_EAST, 0.0)): vol.All(
                vol.Coerce(float), vol.Range(min=-180, max=180)
            ),
            vol.Required(CONF_SOUTH, default=defaults.get(CONF_SOUTH, 0.0)): vol.All(
                vol.Coerce(float), vol.Range(min=-90, max=90)
            ),
            vol.Required(CONF_WEST, default=defaults.get(CONF_WEST, 0.0)): vol.All(
                vol.Coerce(float), vol.Range(min=-180, max=180)
            ),
        }
    )


def _timing_schema(defaults: dict[str, Any]) -> vol.Schema:
    # Anti-ban safety compliance: clamp any stored interval below the hard floor
    # so it never gets persisted or shown as a default below MIN_UPDATE_INTERVAL.
    try:
        raw_interval = int(defaults.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
    except (ValueError, TypeError):
        raw_interval = DEFAULT_UPDATE_INTERVAL
    safe_interval = max(raw_interval, MIN_UPDATE_INTERVAL)
    if safe_interval != raw_interval:
        _LOGGER.warning(
            "Update interval %ds is below the %ds hard floor (anti-ban rate limiting). "
            "Overriding to %ds.",
            raw_interval,
            MIN_UPDATE_INTERVAL,
            MIN_UPDATE_INTERVAL,
        )
    return vol.Schema(
        {
            vol.Required(
                CONF_UPDATE_INTERVAL,
                default=safe_interval,
            ): vol.All(int, vol.Range(min=MIN_UPDATE_INTERVAL, max=3600)),
            vol.Required(
                CONF_STALE_TIMEOUT,
                default=defaults.get(CONF_STALE_TIMEOUT, DEFAULT_STALE_TIMEOUT),
            ): vol.All(int, vol.Range(min=60, max=86400)),
            vol.Optional(
                CONF_FILTER_VESSEL_TYPES,
                default=defaults.get(CONF_FILTER_VESSEL_TYPES, []),
            ): cv.multi_select(VESSEL_TYPE_LABELS),
        }
    )


# ---------------------------------------------------------------------------
# Config flow
# ---------------------------------------------------------------------------


class MarineTrafficConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a UI config flow for MarineTraffic Tracker."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Step 1: choose mode
    # ------------------------------------------------------------------

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Present the tracking mode selector."""
        if user_input is not None:
            self._data[CONF_TRACKING_MODE] = user_input[CONF_TRACKING_MODE]
            if user_input[CONF_TRACKING_MODE] == TRACKING_MODE_RADIUS:
                return await self.async_step_radius()
            return await self.async_step_box()

        return self.async_show_form(
            step_id="user",
            data_schema=_STEP_MODE_SCHEMA,
        )

    # ------------------------------------------------------------------
    # Step 2a: radius parameters
    # ------------------------------------------------------------------

    async def async_step_radius(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Collect center coordinates and radius using a map-based location selector."""
        if user_input is not None:
            loc = user_input[_CONF_LOCATION]
            self._data[CONF_LATITUDE] = loc["latitude"]
            self._data[CONF_LONGITUDE] = loc["longitude"]
            # LocationSelector(radius=True) always includes "radius" in metres.
            self._data[CONF_RADIUS_KM] = loc["radius"] / _METRES_PER_KM
            return await self.async_step_timing()

        # Pre-populate with HA home coordinates so the map opens at a sensible
        # location rather than (0, 0).
        defaults = {**self._data}
        if CONF_LATITUDE not in defaults:
            defaults[CONF_LATITUDE] = self.hass.config.latitude
        if CONF_LONGITUDE not in defaults:
            defaults[CONF_LONGITUDE] = self.hass.config.longitude

        return self.async_show_form(
            step_id="radius",
            data_schema=_radius_schema(defaults),
        )

    # ------------------------------------------------------------------
    # Step 2b: bounding box parameters
    # ------------------------------------------------------------------

    async def async_step_box(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Collect bounding box coordinates."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input[CONF_SOUTH] >= user_input[CONF_NORTH]:
                errors["base"] = "south_gte_north"
            elif user_input[CONF_WEST] >= user_input[CONF_EAST]:
                errors["base"] = "west_gte_east"
            else:
                self._data.update(user_input)
                return await self.async_step_timing()

        return self.async_show_form(
            step_id="box",
            data_schema=_box_schema(self._data),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 3: timing / polling parameters
    # ------------------------------------------------------------------

    async def async_step_timing(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Collect update interval and stale vessel timeout."""
        if user_input is not None:
            self._data.update(user_input)

            # Build a unique ID from the geographic parameters so that the
            # same tracking area cannot be configured twice.
            mode = self._data.get(CONF_TRACKING_MODE, TRACKING_MODE_RADIUS)
            if mode == TRACKING_MODE_RADIUS:
                unique_id = (
                    f"{self._data[CONF_LATITUDE]}"
                    f"_{self._data[CONF_LONGITUDE]}"
                    f"_{self._data[CONF_RADIUS_KM]}"
                )
            else:
                unique_id = (
                    f"{self._data[CONF_NORTH]}_{self._data[CONF_EAST]}"
                    f"_{self._data[CONF_SOUTH]}_{self._data[CONF_WEST]}"
                )

            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=self._make_title(),
                data=self._data,
            )

        return self.async_show_form(
            step_id="timing",
            data_schema=_timing_schema(self._data),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_title(self) -> str:
        """Generate a human-readable config entry title."""
        mode = self._data.get(CONF_TRACKING_MODE, TRACKING_MODE_RADIUS)
        if mode == TRACKING_MODE_RADIUS:
            lat = self._data.get(CONF_LATITUDE, 0)
            lon = self._data.get(CONF_LONGITUDE, 0)
            r = self._data.get(CONF_RADIUS_KM, DEFAULT_RADIUS_KM)
            return f"MarineTraffic ({lat:.4f}, {lon:.4f}) r={r}km"
        n = self._data.get(CONF_NORTH, 0)
        e = self._data.get(CONF_EAST, 0)
        s = self._data.get(CONF_SOUTH, 0)
        w = self._data.get(CONF_WEST, 0)
        return f"MarineTraffic [{s:.2f},{w:.2f}]–[{n:.2f},{e:.2f}]"

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> MarineTrafficOptionsFlow:
        """Return the options flow handler for an existing entry."""
        return MarineTrafficOptionsFlow(config_entry)


# ---------------------------------------------------------------------------
# Options flow
# ---------------------------------------------------------------------------


class MarineTrafficOptionsFlow(OptionsFlow):
    """Allow users to adjust timing settings without removing the integration.

    Geographic parameters (coordinates, radius, box boundaries) are not
    editable via options because changing them effectively creates a different
    tracking area.  Users should remove and re-add the integration for that.
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the options form."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = {**self._config_entry.data, **self._config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=_timing_schema(current),
        )
