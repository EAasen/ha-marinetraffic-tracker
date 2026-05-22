"""Config flow for Norwegian Maritime Tracker."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_BARENTSWATCH_CLIENT_ID,
    CONF_BARENTSWATCH_CLIENT_SECRET,
    CONF_DATA_SOURCE,
    CONF_EAST,
    CONF_EXCLUDE_ANCHORED,
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
    DATA_SOURCE_KYSTVERKET,
    DEFAULT_EXCLUDE_ANCHORED,
    DEFAULT_RADIUS_KM,
    DEFAULT_STALE_TIMEOUT,
    DEFAULT_TRACKING_MODE,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MIN_UPDATE_INTERVAL_API,
    TRACKING_MODE_BOX,
    TRACKING_MODE_RADIUS,
    VESSEL_TYPE_LABELS,
)

_CONF_LOCATION = "location"
_METRES_PER_KM = 1000.0
_NORWAY_LATITUDE = 60.4720
_NORWAY_LONGITUDE = 8.4689
_NORWAY_BOUNDS = {
    "north": 71.5,
    "south": 57.0,
    "east": 32.0,
    "west": 4.0,
}

_TRACKING_MODE_OPTIONS: list[selector.SelectOptionDict] = [
    selector.SelectOptionDict(value=TRACKING_MODE_RADIUS, label="Radius (map selector)"),
    selector.SelectOptionDict(value=TRACKING_MODE_BOX, label="Bounding box"),
]

_VESSEL_TYPE_OPTIONS: list[selector.SelectOptionDict] = [
    selector.SelectOptionDict(value=value, label=label)
    for value, label in VESSEL_TYPE_LABELS.items()
]

_STEP_MODE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TRACKING_MODE, default=DEFAULT_TRACKING_MODE): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=_TRACKING_MODE_OPTIONS,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
    }
)


def _is_within_norway(latitude: float | None, longitude: float | None) -> bool:
    """Return whether coordinates fall within a broad Norwegian bounding box."""
    if latitude is None or longitude is None:
        return False
    return (
        _NORWAY_BOUNDS["south"] <= latitude <= _NORWAY_BOUNDS["north"]
        and _NORWAY_BOUNDS["west"] <= longitude <= _NORWAY_BOUNDS["east"]
    )


def _source_defaults(hass: Any, defaults: dict[str, Any]) -> tuple[float, float]:
    """Return sensible Norwegian coordinates for the selector default."""
    lat = defaults.get(CONF_LATITUDE)
    lon = defaults.get(CONF_LONGITUDE)
    if _is_within_norway(lat, lon):
        return float(lat), float(lon)

    hass_lat = getattr(hass.config, "latitude", None)
    hass_lon = getattr(hass.config, "longitude", None)
    if _is_within_norway(hass_lat, hass_lon):
        return float(hass_lat), float(hass_lon)

    return _NORWAY_LATITUDE, _NORWAY_LONGITUDE


def _radius_schema(hass: Any, defaults: dict[str, Any]) -> vol.Schema:
    lat, lon = _source_defaults(hass, defaults)
    radius_m = defaults.get(CONF_RADIUS_KM, DEFAULT_RADIUS_KM) * _METRES_PER_KM
    return vol.Schema(
        {
            vol.Required(
                _CONF_LOCATION,
                default={"latitude": lat, "longitude": lon, "radius": radius_m},
            ): selector.LocationSelector(
                selector.LocationSelectorConfig(radius=True, icon="mdi:ferry")
            ),
        }
    )


def _box_schema(defaults: dict[str, Any]) -> vol.Schema:
    suggested_lat = float(defaults.get(CONF_LATITUDE, _NORWAY_LATITUDE))
    suggested_lon = float(defaults.get(CONF_LONGITUDE, _NORWAY_LONGITUDE))
    north = defaults.get(CONF_NORTH, round(suggested_lat + 0.4, 4))
    south = defaults.get(CONF_SOUTH, round(suggested_lat - 0.4, 4))
    east = defaults.get(CONF_EAST, round(suggested_lon + 0.8, 4))
    west = defaults.get(CONF_WEST, round(suggested_lon - 0.8, 4))
    return vol.Schema(
        {
            vol.Required(CONF_NORTH, default=north): vol.All(
                vol.Coerce(float),
                vol.Range(min=-90, max=90),
            ),
            vol.Required(CONF_EAST, default=east): vol.All(
                vol.Coerce(float),
                vol.Range(min=-180, max=180),
            ),
            vol.Required(CONF_SOUTH, default=south): vol.All(
                vol.Coerce(float),
                vol.Range(min=-90, max=90),
            ),
            vol.Required(CONF_WEST, default=west): vol.All(
                vol.Coerce(float),
                vol.Range(min=-180, max=180),
            ),
        }
    )


def _timing_schema(defaults: dict[str, Any]) -> vol.Schema:
    try:
        raw_interval = int(defaults.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
    except (ValueError, TypeError):
        raw_interval = DEFAULT_UPDATE_INTERVAL

    return vol.Schema(
        {
            vol.Required(
                CONF_BARENTSWATCH_CLIENT_ID,
                default=defaults.get(CONF_BARENTSWATCH_CLIENT_ID, ""),
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Required(
                CONF_BARENTSWATCH_CLIENT_SECRET,
                default=defaults.get(CONF_BARENTSWATCH_CLIENT_SECRET, ""),
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(
                CONF_UPDATE_INTERVAL,
                default=max(raw_interval, MIN_UPDATE_INTERVAL_API),
            ): vol.All(int, vol.Range(min=MIN_UPDATE_INTERVAL_API, max=3600)),
            vol.Required(
                CONF_STALE_TIMEOUT,
                default=defaults.get(CONF_STALE_TIMEOUT, DEFAULT_STALE_TIMEOUT),
            ): vol.All(int, vol.Range(min=60, max=86400)),
            vol.Optional(
                CONF_FILTER_VESSEL_TYPES,
                default=defaults.get(CONF_FILTER_VESSEL_TYPES, []),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=_VESSEL_TYPE_OPTIONS,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_EXCLUDE_ANCHORED,
                default=defaults.get(CONF_EXCLUDE_ANCHORED, DEFAULT_EXCLUDE_ANCHORED),
            ): bool,
        }
    )


class MarineTrafficConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a UI config flow for Norwegian Maritime Tracker."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {CONF_DATA_SOURCE: DATA_SOURCE_KYSTVERKET}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Choose the tracking mode."""
        if user_input is not None:
            self._data[CONF_TRACKING_MODE] = user_input[CONF_TRACKING_MODE]
            if user_input[CONF_TRACKING_MODE] == TRACKING_MODE_RADIUS:
                return await self.async_step_radius()
            return await self.async_step_box()

        return self.async_show_form(step_id="user", data_schema=_STEP_MODE_SCHEMA)

    async def async_step_radius(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Collect center coordinates and radius."""
        if user_input is not None:
            loc = user_input[_CONF_LOCATION]
            self._data[CONF_LATITUDE] = loc["latitude"]
            self._data[CONF_LONGITUDE] = loc["longitude"]
            self._data[CONF_RADIUS_KM] = loc["radius"] / _METRES_PER_KM
            return await self.async_step_timing()

        return self.async_show_form(
            step_id="radius",
            data_schema=_radius_schema(self.hass, self._data),
        )

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

        defaults = dict(self._data)
        lat, lon = _source_defaults(self.hass, defaults)
        defaults.setdefault(CONF_LATITUDE, lat)
        defaults.setdefault(CONF_LONGITUDE, lon)
        return self.async_show_form(
            step_id="box",
            data_schema=_box_schema(defaults),
            errors=errors,
        )

    async def async_step_timing(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Collect Kystverket credentials and polling settings."""
        errors: dict[str, str] = {}
        if user_input is not None:
            client_id = str(user_input.get(CONF_BARENTSWATCH_CLIENT_ID, "")).strip()
            client_secret = str(user_input.get(CONF_BARENTSWATCH_CLIENT_SECRET, "")).strip()

            if not client_id:
                errors[CONF_BARENTSWATCH_CLIENT_ID] = "barentswatch_client_id_required"
            if not client_secret:
                errors[CONF_BARENTSWATCH_CLIENT_SECRET] = "barentswatch_client_secret_required"

            if not errors:
                self._data.update(user_input)
                self._data[CONF_BARENTSWATCH_CLIENT_ID] = client_id
                self._data[CONF_BARENTSWATCH_CLIENT_SECRET] = client_secret
                await self.async_set_unique_id(self._unique_id())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=self._make_title(), data=self._data)

        return self.async_show_form(
            step_id="timing",
            data_schema=_timing_schema(self._data),
            errors=errors,
        )

    def _unique_id(self) -> str:
        """Build a stable unique ID for the tracking area."""
        mode = self._data.get(CONF_TRACKING_MODE, TRACKING_MODE_RADIUS)
        if mode == TRACKING_MODE_RADIUS:
            return (
                f"{self._data[CONF_LATITUDE]}_{self._data[CONF_LONGITUDE]}"
                f"_{self._data[CONF_RADIUS_KM]}_kystverket"
            )
        return (
            f"{self._data[CONF_NORTH]}_{self._data[CONF_EAST]}"
            f"_{self._data[CONF_SOUTH]}_{self._data[CONF_WEST]}_kystverket"
        )

    def _make_title(self) -> str:
        """Generate a human-readable config entry title."""
        mode = self._data.get(CONF_TRACKING_MODE, TRACKING_MODE_RADIUS)
        if mode == TRACKING_MODE_RADIUS:
            lat = self._data.get(CONF_LATITUDE, _NORWAY_LATITUDE)
            lon = self._data.get(CONF_LONGITUDE, _NORWAY_LONGITUDE)
            radius = self._data.get(CONF_RADIUS_KM, DEFAULT_RADIUS_KM)
            return f"Norwegian Maritime Tracker ({lat:.4f}, {lon:.4f}) r={radius}km"
        north = self._data.get(CONF_NORTH, 0)
        east = self._data.get(CONF_EAST, 0)
        south = self._data.get(CONF_SOUTH, 0)
        west = self._data.get(CONF_WEST, 0)
        return f"Norwegian Maritime Tracker [{south:.2f},{west:.2f}]–[{north:.2f},{east:.2f}]"

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> MarineTrafficOptionsFlow:
        """Return the options flow handler for an existing entry."""
        return MarineTrafficOptionsFlow(config_entry)


class MarineTrafficOptionsFlow(OptionsFlow):
    """Allow users to update Kystverket credentials and polling settings."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the single-step options flow."""
        errors: dict[str, str] = {}
        if user_input is not None:
            client_id = str(user_input.get(CONF_BARENTSWATCH_CLIENT_ID, "")).strip()
            client_secret = str(user_input.get(CONF_BARENTSWATCH_CLIENT_SECRET, "")).strip()

            if not client_id:
                errors[CONF_BARENTSWATCH_CLIENT_ID] = "barentswatch_client_id_required"
            if not client_secret:
                errors[CONF_BARENTSWATCH_CLIENT_SECRET] = "barentswatch_client_secret_required"

            if not errors:
                user_input[CONF_BARENTSWATCH_CLIENT_ID] = client_id
                user_input[CONF_BARENTSWATCH_CLIENT_SECRET] = client_secret
                user_input[CONF_DATA_SOURCE] = DATA_SOURCE_KYSTVERKET
                return self.async_create_entry(data=user_input)

        current = {**self._config_entry.data, **self._config_entry.options}
        current.setdefault(CONF_DATA_SOURCE, DATA_SOURCE_KYSTVERKET)
        return self.async_show_form(
            step_id="init",
            data_schema=_timing_schema(current),
            errors=errors,
        )
