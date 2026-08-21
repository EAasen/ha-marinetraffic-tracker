"""Tests for the Norwegian Maritime Tracker config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
import voluptuous as vol
from homeassistant.helpers import selector

from custom_components.marinetraffic_tracker import config_flow
from custom_components.marinetraffic_tracker.config_flow import (
    _CONF_LOCATION,
    _STEP_INTRO_SCHEMA,
    _STEP_MODE_SCHEMA,
    MarineTrafficConfigFlow,
    MarineTrafficOptionsFlow,
    _box_schema,
    _credentials_schema,
    _options_schema,
)
from custom_components.marinetraffic_tracker.const import (
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
    DEFAULT_STALE_TIMEOUT,
    MIN_UPDATE_INTERVAL_API,
    TRACKING_MODE_BOX,
    TRACKING_MODE_RADIUS,
)


def _make_config_flow(*, home_lat: float = 59.9, home_lon: float = 10.7) -> MarineTrafficConfigFlow:
    """Create a flow with mocked Home Assistant internals."""
    flow = MarineTrafficConfigFlow.__new__(MarineTrafficConfigFlow)
    flow._data = {CONF_DATA_SOURCE: DATA_SOURCE_KYSTVERKET}
    flow.hass = MagicMock()
    flow.hass.config.latitude = home_lat
    flow.hass.config.longitude = home_lon
    flow.async_show_form = MagicMock(side_effect=lambda **kw: {"type": "form", **kw})
    flow.async_create_entry = MagicMock(side_effect=lambda **kw: {"type": "create_entry", **kw})
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()
    return flow


def _make_options_flow() -> MarineTrafficOptionsFlow:
    """Create an options flow with mocked internals."""
    entry = MagicMock()
    entry.data = {
        CONF_DATA_SOURCE: DATA_SOURCE_KYSTVERKET,
        CONF_BARENTSWATCH_CLIENT_ID: "client-id",
        CONF_BARENTSWATCH_CLIENT_SECRET: "client-secret",
        CONF_UPDATE_INTERVAL: 15,
        CONF_STALE_TIMEOUT: DEFAULT_STALE_TIMEOUT,
        CONF_FILTER_VESSEL_TYPES: [],
        CONF_EXCLUDE_ANCHORED: DEFAULT_EXCLUDE_ANCHORED,
        CONF_EXCLUDE_MOORED: DEFAULT_EXCLUDE_MOORED,
    }
    entry.options = {}

    flow = MarineTrafficOptionsFlow.__new__(MarineTrafficOptionsFlow)
    flow._config_entry = entry
    flow.async_show_form = MagicMock(side_effect=lambda **kw: {"type": "form", **kw})
    flow.async_create_entry = MagicMock(side_effect=lambda **kw: {"type": "create_entry", **kw})
    return flow


def test_intro_schema_has_no_fields() -> None:
    """The intro step should only display instructions."""
    assert _STEP_INTRO_SCHEMA.schema == {}


def test_mode_schema_exposes_tracking_mode_selector() -> None:
    """The mode step should offer radius vs bounding box."""
    assert isinstance(_STEP_MODE_SCHEMA.schema[CONF_TRACKING_MODE], selector.SelectSelector)


def test_credentials_schema_collects_barentswatch_credentials() -> None:
    """The credentials step should request BarentsWatch secrets."""
    schema = _credentials_schema({})
    assert isinstance(schema.schema[CONF_BARENTSWATCH_CLIENT_ID], selector.TextSelector)
    assert isinstance(schema.schema[CONF_BARENTSWATCH_CLIENT_SECRET], selector.TextSelector)


def test_options_schema_uses_api_floor_and_split_exclusion_toggles() -> None:
    """The options step should enforce the API floor and expose both toggles."""
    schema = _options_schema({})
    assert CONF_BARENTSWATCH_CLIENT_ID not in schema.schema
    assert CONF_BARENTSWATCH_CLIENT_SECRET not in schema.schema
    assert schema.schema[CONF_EXCLUDE_ANCHORED] is bool
    assert schema.schema[CONF_EXCLUDE_MOORED] is bool

    with pytest.raises(vol.Invalid):
        schema(
            {
                CONF_UPDATE_INTERVAL: MIN_UPDATE_INTERVAL_API - 1,
                CONF_STALE_TIMEOUT: DEFAULT_STALE_TIMEOUT,
                CONF_FILTER_VESSEL_TYPES: [],
                CONF_EXCLUDE_ANCHORED: False,
                CONF_EXCLUDE_MOORED: False,
            }
        )


def test_box_schema_rejects_invalid_coordinates() -> None:
    """Bounding box validation should still reject inverted bounds."""
    schema = _box_schema(
        {
            CONF_LATITUDE: 60.0,
            CONF_LONGITUDE: 5.0,
        }
    )
    with pytest.raises(vol.Invalid):
        schema(
            {
                CONF_NORTH: 91.0,
                CONF_EAST: 10.0,
                CONF_SOUTH: 59.0,
                CONF_WEST: 4.0,
            }
        )


@pytest.mark.asyncio
async def test_user_step_moves_to_credentials() -> None:
    """Submitting the intro step should move to credentials."""
    flow = _make_config_flow()

    result = await flow.async_step_user({})

    assert result["type"] == "form"
    assert result["step_id"] == "credentials"


@pytest.mark.asyncio
async def test_credentials_step_requires_barentswatch_credentials() -> None:
    """Blank credentials should return field-specific errors."""
    flow = _make_config_flow()

    result = await flow.async_step_credentials(
        {
            CONF_BARENTSWATCH_CLIENT_ID: " ",
            CONF_BARENTSWATCH_CLIENT_SECRET: "",
        }
    )

    assert result["type"] == "form"
    assert result["errors"][CONF_BARENTSWATCH_CLIENT_ID] == "barentswatch_client_id_required"
    assert (
        result["errors"][CONF_BARENTSWATCH_CLIENT_SECRET]
        == "barentswatch_client_secret_required"
    )


@pytest.mark.asyncio
async def test_credentials_step_reports_invalid_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Credential validation errors should stay on the credentials step."""
    flow = _make_config_flow()
    monkeypatch.setattr(
        config_flow,
        "_async_validate_credentials",
        AsyncMock(return_value="invalid_auth"),
    )

    result = await flow.async_step_credentials(
        {
            CONF_BARENTSWATCH_CLIENT_ID: "client-id",
            CONF_BARENTSWATCH_CLIENT_SECRET: "client-secret",
        }
    )

    assert result["type"] == "form"
    assert result["step_id"] == "credentials"
    assert result["errors"]["base"] == "invalid_auth"


@pytest.mark.asyncio
async def test_credentials_step_trims_credentials_and_moves_to_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful credential validation should normalize secrets and continue."""
    flow = _make_config_flow()
    monkeypatch.setattr(config_flow, "_async_validate_credentials", AsyncMock(return_value=None))

    result = await flow.async_step_credentials(
        {
            CONF_BARENTSWATCH_CLIENT_ID: " client-id ",
            CONF_BARENTSWATCH_CLIENT_SECRET: " secret ",
        }
    )

    assert result["type"] == "form"
    assert result["step_id"] == "mode"
    assert flow._data[CONF_BARENTSWATCH_CLIENT_ID] == "client-id"
    assert flow._data[CONF_BARENTSWATCH_CLIENT_SECRET] == "secret"


@pytest.mark.asyncio
async def test_radius_step_uses_norway_default_when_home_outside_norway() -> None:
    """The location selector should fall back to Norwegian coordinates."""
    flow = _make_config_flow(home_lat=40.0, home_lon=-74.0)

    result = await flow.async_step_radius()
    assert result["type"] == "form"

    location_key = next(key for key in result["data_schema"].schema if key.schema == _CONF_LOCATION)
    default = location_key.default()
    assert default["latitude"] == pytest.approx(60.4720)
    assert default["longitude"] == pytest.approx(8.4689)


@pytest.mark.asyncio
async def test_radius_step_moves_directly_to_options() -> None:
    """Radius selection should move directly to non-authentication options."""
    flow = _make_config_flow()
    result = await flow.async_step_radius(
        {_CONF_LOCATION: {"latitude": 60.4, "longitude": 5.3, "radius": 15000.0}}
    )

    assert result["type"] == "form"
    assert result["step_id"] == "options"
    assert flow._data[CONF_LATITUDE] == 60.4
    assert flow._data[CONF_LONGITUDE] == 5.3
    assert flow._data[CONF_RADIUS_KM] == 15.0
    assert flow._data[CONF_DATA_SOURCE] == DATA_SOURCE_KYSTVERKET


@pytest.mark.asyncio
async def test_options_step_creates_entry_without_reauth() -> None:
    """Successful setup should create the entry from non-authentication options."""
    flow = _make_config_flow()
    flow._data.update(
        {
            CONF_BARENTSWATCH_CLIENT_ID: "client-id",
            CONF_BARENTSWATCH_CLIENT_SECRET: "secret",
            CONF_TRACKING_MODE: TRACKING_MODE_RADIUS,
            CONF_LATITUDE: 60.4,
            CONF_LONGITUDE: 5.3,
            CONF_RADIUS_KM: 15.0,
        }
    )

    result = await flow.async_step_options(
        {
            CONF_UPDATE_INTERVAL: 15,
            CONF_STALE_TIMEOUT: DEFAULT_STALE_TIMEOUT,
            CONF_FILTER_VESSEL_TYPES: ["70"],
            CONF_EXCLUDE_ANCHORED: True,
            CONF_EXCLUDE_MOORED: False,
        }
    )

    assert result["type"] == "create_entry"
    assert result["data"][CONF_BARENTSWATCH_CLIENT_ID] == "client-id"
    assert result["data"][CONF_EXCLUDE_ANCHORED] is True
    assert result["data"][CONF_EXCLUDE_MOORED] is False
    flow.async_set_unique_id.assert_awaited_once_with("60.4_5.3_15.0_kystverket")


@pytest.mark.asyncio
async def test_options_step_handles_invalid_values() -> None:
    """Invalid options submissions should stay on the options step."""
    flow = _make_config_flow()
    flow._data.update(
        {
            CONF_BARENTSWATCH_CLIENT_ID: "client-id",
            CONF_BARENTSWATCH_CLIENT_SECRET: "secret",
            CONF_TRACKING_MODE: TRACKING_MODE_RADIUS,
            CONF_LATITUDE: 60.4,
            CONF_LONGITUDE: 5.3,
            CONF_RADIUS_KM: 15.0,
        }
    )

    result = await flow.async_step_options(
        {
            CONF_UPDATE_INTERVAL: MIN_UPDATE_INTERVAL_API - 1,
            CONF_STALE_TIMEOUT: DEFAULT_STALE_TIMEOUT,
            CONF_FILTER_VESSEL_TYPES: [],
            CONF_EXCLUDE_ANCHORED: False,
            CONF_EXCLUDE_MOORED: False,
        }
    )

    assert result["type"] == "form"
    assert result["step_id"] == "options"
    assert result["errors"]["base"] == "invalid_options"


@pytest.mark.asyncio
async def test_box_flow_validates_bounds_before_options() -> None:
    """Invalid bounding boxes should stay on the box step."""
    flow = _make_config_flow()
    result = await flow.async_step_box(
        {
            CONF_NORTH: 60.0,
            CONF_EAST: 10.0,
            CONF_SOUTH: 60.0,
            CONF_WEST: 4.0,
        }
    )

    assert result["type"] == "form"
    assert result["step_id"] == "box"
    assert result["errors"]["base"] == "south_gte_north"


@pytest.mark.asyncio
async def test_options_flow_uses_non_authentication_schema() -> None:
    """Options flow should not require credentials again."""
    flow = _make_options_flow()

    result = await flow.async_step_init()

    assert result["type"] == "form"
    assert CONF_BARENTSWATCH_CLIENT_ID not in result["data_schema"].schema
    assert CONF_BARENTSWATCH_CLIENT_SECRET not in result["data_schema"].schema


@pytest.mark.asyncio
async def test_options_flow_persists_kystverket_source() -> None:
    """Options changes should keep the Kystverket source active."""
    flow = _make_options_flow()
    result = await flow.async_step_init(
        {
            CONF_UPDATE_INTERVAL: 20,
            CONF_STALE_TIMEOUT: DEFAULT_STALE_TIMEOUT,
            CONF_FILTER_VESSEL_TYPES: [],
            CONF_EXCLUDE_ANCHORED: True,
            CONF_EXCLUDE_MOORED: True,
        }
    )

    assert result["type"] == "create_entry"
    assert result["data"][CONF_DATA_SOURCE] == DATA_SOURCE_KYSTVERKET


@pytest.mark.asyncio
async def test_options_flow_handles_invalid_values() -> None:
    """Invalid direct options submissions should stay on the options form."""
    flow = _make_options_flow()

    result = await flow.async_step_init(
        {
            CONF_UPDATE_INTERVAL: MIN_UPDATE_INTERVAL_API - 1,
            CONF_STALE_TIMEOUT: DEFAULT_STALE_TIMEOUT,
            CONF_FILTER_VESSEL_TYPES: [],
            CONF_EXCLUDE_ANCHORED: False,
            CONF_EXCLUDE_MOORED: False,
        }
    )

    assert result["type"] == "form"
    assert result["step_id"] == "init"
    assert result["errors"]["base"] == "invalid_options"


def test_make_title_uses_new_branding() -> None:
    """The entry title should reflect the Norwegian focus."""
    flow = _make_config_flow()
    flow._data.update(
        {
            CONF_TRACKING_MODE: TRACKING_MODE_BOX,
            CONF_NORTH: 61.0,
            CONF_EAST: 6.0,
            CONF_SOUTH: 60.0,
            CONF_WEST: 5.0,
        }
    )
    assert flow._make_title() == "Norwegian Maritime Tracker [60.00,5.00]–[61.00,6.00]"
