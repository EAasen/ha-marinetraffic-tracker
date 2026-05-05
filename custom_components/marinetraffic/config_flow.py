"""Config flow for the MarineTraffic Tracker integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_RADIUS
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult

from .const import DEFAULT_RADIUS, DOMAIN

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_schema(
    default_lat: float | None = None,
    default_lon: float | None = None,
    default_radius: float = DEFAULT_RADIUS,
) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_LATITUDE,
                default=default_lat,
            ): vol.All(vol.Coerce(float), vol.Range(min=-90, max=90)),
            vol.Required(
                CONF_LONGITUDE,
                default=default_lon,
            ): vol.All(vol.Coerce(float), vol.Range(min=-180, max=180)),
            vol.Required(
                CONF_RADIUS,
                default=default_radius,
            ): vol.All(vol.Coerce(float), vol.Range(min=1, max=500)),
        }
    )


# ---------------------------------------------------------------------------
# Config Flow
# ---------------------------------------------------------------------------


class MarineTrafficConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MarineTraffic Tracker."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial user-facing step."""
        errors: dict[str, str] = {}

        # Pre-fill with HA's configured home location when available.
        default_lat: float | None = self.hass.config.latitude or None
        default_lon: float | None = self.hass.config.longitude or None

        if user_input is not None:
            lat = user_input[CONF_LATITUDE]
            lon = user_input[CONF_LONGITUDE]
            radius = user_input[CONF_RADIUS]

            # Uniqueness: one entry per (lat, lon, radius) combination.
            await self.async_set_unique_id(f"{lat}_{lon}_{radius}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"MarineTraffic ({lat:.2f}, {lon:.2f}) r={radius} km",
                data=user_input,
            )

        schema = _build_schema(default_lat, default_lon, DEFAULT_RADIUS)
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Options flow (allows editing radius without removing the entry)
    # ------------------------------------------------------------------

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> MarineTrafficOptionsFlow:
        return MarineTrafficOptionsFlow(config_entry)


class MarineTrafficOptionsFlow(config_entries.OptionsFlow):
    """Handle options for MarineTraffic Tracker (edit radius)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_radius = self._config_entry.options.get(
            CONF_RADIUS,
            self._config_entry.data.get(CONF_RADIUS, DEFAULT_RADIUS),
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_RADIUS, default=current_radius): vol.All(
                    vol.Coerce(float), vol.Range(min=1, max=500)
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
