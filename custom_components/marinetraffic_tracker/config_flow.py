"""Config flow for Norwegian Maritime Tracker."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_BARENTSWATCH_CLIENT_ID,
    CONF_BARENTSWATCH_CLIENT_SECRET,
    CONF_DATA_SOURCE,
    CONF_EAST,
    CONF_EXCLUDE_ANCHORED,
    CONF_EXCLUDE_MOORED,
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
    DEFAULT_EXCLUDE_MOORED,
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
from .kystverket_client import InvalidAuthError, KystverketClient

_LOGGER = logging.getLogger(__name__)
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

_STEP_INTRO_SCHEMA = vol.Schema({})
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


def _default_coordinates(hass: HomeAssistant, defaults: dict[str, Any]) -> tuple[float, float]:
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


def _credentials_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build the credential step schema."""
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
        }
    )


def _radius_schema(hass: HomeAssistant, defaults: dict[str, Any]) -> vol.Schema:
    lat, lon = _default_coordinates(hass, defaults)
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


def _options_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build the shared non-authentication options schema."""
    try:
        raw_interval = int(defaults.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
    except (ValueError, TypeError):
        raw_interval = DEFAULT_UPDATE_INTERVAL

    return vol.Schema(
        {
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
            vol.Required(
                CONF_EXCLUDE_ANCHORED,
                default=defaults.get(CONF_EXCLUDE_ANCHORED, DEFAULT_EXCLUDE_ANCHORED),
            ): bool,
            vol.Required(
                CONF_EXCLUDE_MOORED,
                default=defaults.get(CONF_EXCLUDE_MOORED, DEFAULT_EXCLUDE_MOORED),
            ): bool,
        }
    )


async def _async_validate_credentials(
    hass: HomeAssistant,
    client_id: str,
    client_secret: str,
) -> str | None:
    """Validate BarentsWatch credentials against the live token endpoint."""
    client = KystverketClient(
        async_get_clientsession(hass),
        client_id=client_id,
        client_secret=client_secret,
    )
    try:
        await client.async_validate_credentials()
    except InvalidAuthError:
        return "invalid_auth"
    except (aiohttp.ClientError, TimeoutError):
        return "cannot_connect"
    return None


class MarineTrafficConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a UI config flow for Norwegian Maritime Tracker."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {CONF_DATA_SOURCE: DATA_SOURCE_KYSTVERKET}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Show setup instructions before collecting credentials."""
        if user_input is not None:
            return await self.async_step_credentials()

        return self.async_show_form(step_id="user", data_schema=_STEP_INTRO_SCHEMA)

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Collect and validate BarentsWatch credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            client_id = str(user_input.get(CONF_BARENTSWATCH_CLIENT_ID, "")).strip()
            client_secret = str(user_input.get(CONF_BARENTSWATCH_CLIENT_SECRET, "")).strip()

            if not client_id:
                errors[CONF_BARENTSWATCH_CLIENT_ID] = "barentswatch_client_id_required"
            if not client_secret:
                errors[CONF_BARENTSWATCH_CLIENT_SECRET] = "barentswatch_client_secret_required"

            if not errors:
                credential_error = await _async_validate_credentials(
                    self.hass, client_id, client_secret
                )
                if credential_error is None:
                    self._data[CONF_BARENTSWATCH_CLIENT_ID] = client_id
                    self._data[CONF_BARENTSWATCH_CLIENT_SECRET] = client_secret
                    return await self.async_step_mode()
                errors["base"] = credential_error

        return self.async_show_form(
            step_id="credentials",
            data_schema=_credentials_schema(self._data),
            errors=errors,
        )

    async def async_step_mode(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Choose the tracking mode."""
        if user_input is not None:
            self._data[CONF_TRACKING_MODE] = user_input[CONF_TRACKING_MODE]
            if user_input[CONF_TRACKING_MODE] == TRACKING_MODE_RADIUS:
                return await self.async_step_radius()
            return await self.async_step_box()

        return self.async_show_form(step_id="mode", data_schema=_STEP_MODE_SCHEMA)

    async def async_step_radius(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Collect center coordinates and radius."""
        if user_input is not None:
            loc = user_input[_CONF_LOCATION]
            self._data[CONF_LATITUDE] = loc["latitude"]
            self._data[CONF_LONGITUDE] = loc["longitude"]
            self._data[CONF_RADIUS_KM] = loc["radius"] / _METRES_PER_KM
            return await self.async_step_options()

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
                return await self.async_step_options()

        defaults = dict(self._data)
        lat, lon = _default_coordinates(self.hass, defaults)
        defaults.setdefault(CONF_LATITUDE, lat)
        defaults.setdefault(CONF_LONGITUDE, lon)
        return self.async_show_form(
            step_id="box",
            data_schema=_box_schema(defaults),
            errors=errors,
        )

    async def async_step_options(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Collect non-authentication options and create the entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                validated = _options_schema(self._data)(user_input)
            except vol.Invalid as err:
                _LOGGER.debug("Invalid config flow options submission: %s", err)
                errors["base"] = "invalid_options"
            else:
                self._data.update(validated)
                await self.async_set_unique_id(self._unique_id())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=self._make_title(), data=self._data)

        return self.async_show_form(
            step_id="options",
            data_schema=_options_schema(self._data),
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
    """Allow users to update non-authentication tracking options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the single-step options flow."""
        current = {**self._config_entry.data, **self._config_entry.options}
        current.setdefault(CONF_DATA_SOURCE, DATA_SOURCE_KYSTVERKET)
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                validated = _options_schema(current)(user_input)
            except vol.Invalid as err:
                _LOGGER.debug("Invalid options flow submission: %s", err)
                errors["base"] = "invalid_options"
            else:
                validated[CONF_DATA_SOURCE] = DATA_SOURCE_KYSTVERKET
                return self.async_create_entry(data=validated)

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(current),
            errors=errors,
        )
