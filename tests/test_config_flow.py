"""Tests for MarineTraffic Tracker config flow and options flow.

Covers:
- Schema helper functions: _timing_schema, _source_schema, _box_schema
- Validation errors: south >= north, west >= east, AISHub key missing,
  fallback == primary
- Step transitions in the config flow (user → radius/box → source → timing)
- Entry title generation via _make_title
- Options flow: source validation and timing step
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol

from custom_components.marinetraffic_tracker.config_flow import (
    MarineTrafficConfigFlow,
    MarineTrafficOptionsFlow,
    _box_schema,
    _source_schema,
    _timing_schema,
)
from custom_components.marinetraffic_tracker.const import (
    CONF_AISHUB_API_KEY,
    CONF_DATA_SOURCE,
    CONF_EAST,
    CONF_EXCLUDE_ANCHORED,
    CONF_EXTRA_SOURCES,
    CONF_FALLBACK_SOURCE,
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
    DATA_SOURCE_AISHUB,
    DATA_SOURCE_MARINETRAFFIC,
    DATA_SOURCE_VESSELFINDER,
    DEFAULT_DATA_SOURCE,
    DEFAULT_FALLBACK_SOURCE,
    DEFAULT_RADIUS_KM,
    DEFAULT_STALE_TIMEOUT,
    DEFAULT_UPDATE_INTERVAL,
    FALLBACK_SOURCE_NONE,
    MIN_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL_API,
    TRACKING_MODE_BOX,
    TRACKING_MODE_RADIUS,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config_flow() -> MarineTrafficConfigFlow:
    """Create a MarineTrafficConfigFlow with mocked HA base-class internals."""
    flow = MarineTrafficConfigFlow.__new__(MarineTrafficConfigFlow)
    flow._data = {}
    flow.hass = MagicMock()
    flow.hass.config.latitude = 59.9
    flow.hass.config.longitude = 10.7
    # Replace FlowHandler base-class methods with simple stubs.
    flow.async_show_form = MagicMock(side_effect=lambda **kw: {"type": "form", **kw})
    flow.async_create_entry = MagicMock(side_effect=lambda **kw: {"type": "create_entry", **kw})
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()
    return flow


def _make_options_flow() -> MarineTrafficOptionsFlow:
    """Create a MarineTrafficOptionsFlow with mocked HA internals."""
    config_entry = MagicMock()
    config_entry.data = {
        CONF_DATA_SOURCE: DATA_SOURCE_MARINETRAFFIC,
        CONF_UPDATE_INTERVAL: 60,
        CONF_STALE_TIMEOUT: DEFAULT_STALE_TIMEOUT,
        CONF_EXTRA_SOURCES: [],
        CONF_AISHUB_API_KEY: "",
        CONF_FALLBACK_SOURCE: FALLBACK_SOURCE_NONE,
    }
    config_entry.options = {}

    flow = MarineTrafficOptionsFlow.__new__(MarineTrafficOptionsFlow)
    flow._config_entry = config_entry
    flow._options = {}
    flow.hass = MagicMock()
    flow.async_show_form = MagicMock(side_effect=lambda **kw: {"type": "form", **kw})
    flow.async_create_entry = MagicMock(side_effect=lambda **kw: {"type": "create_entry", **kw})
    return flow


# ---------------------------------------------------------------------------
# _timing_schema — interval floor enforcement
# ---------------------------------------------------------------------------


class TestTimingSchema:
    """Tests for the _timing_schema helper."""

    def test_marinetraffic_source_enforces_scraper_floor(self) -> None:
        """Intervals below MIN_UPDATE_INTERVAL must be clamped to the floor."""
        schema = _timing_schema({CONF_DATA_SOURCE: DATA_SOURCE_MARINETRAFFIC})
        with pytest.raises(vol.Invalid):
            schema(
                {
                    CONF_UPDATE_INTERVAL: MIN_UPDATE_INTERVAL - 1,
                    CONF_STALE_TIMEOUT: DEFAULT_STALE_TIMEOUT,
                    CONF_FILTER_VESSEL_TYPES: [],
                    CONF_EXCLUDE_ANCHORED: False,
                }
            )

    def test_aishub_source_enforces_api_floor(self) -> None:
        """When data source is AISHub the floor drops to MIN_UPDATE_INTERVAL_API."""
        schema = _timing_schema({CONF_DATA_SOURCE: DATA_SOURCE_AISHUB})
        # MIN_UPDATE_INTERVAL_API (5s) must be accepted, whereas MIN_UPDATE_INTERVAL (30s)
        # would also be accepted. Verify the API floor is at least as permissive.
        result = schema(
            {
                CONF_UPDATE_INTERVAL: MIN_UPDATE_INTERVAL_API,
                CONF_STALE_TIMEOUT: DEFAULT_STALE_TIMEOUT,
                CONF_FILTER_VESSEL_TYPES: [],
                CONF_EXCLUDE_ANCHORED: False,
            }
        )
        assert result[CONF_UPDATE_INTERVAL] == MIN_UPDATE_INTERVAL_API

    def test_valid_interval_accepted(self) -> None:
        """An interval at or above the floor is accepted unchanged."""
        schema = _timing_schema({CONF_DATA_SOURCE: DATA_SOURCE_MARINETRAFFIC})
        result = schema(
            {
                CONF_UPDATE_INTERVAL: MIN_UPDATE_INTERVAL,
                CONF_STALE_TIMEOUT: DEFAULT_STALE_TIMEOUT,
                CONF_FILTER_VESSEL_TYPES: [],
                CONF_EXCLUDE_ANCHORED: False,
            }
        )
        assert result[CONF_UPDATE_INTERVAL] == MIN_UPDATE_INTERVAL

    def test_stale_timeout_below_60_rejected(self) -> None:
        """stale_timeout must be at least 60 seconds."""
        schema = _timing_schema({CONF_DATA_SOURCE: DATA_SOURCE_MARINETRAFFIC})
        with pytest.raises(vol.Invalid):
            schema(
                {
                    CONF_UPDATE_INTERVAL: MIN_UPDATE_INTERVAL,
                    CONF_STALE_TIMEOUT: 30,
                    CONF_FILTER_VESSEL_TYPES: [],
                    CONF_EXCLUDE_ANCHORED: False,
                }
            )

    def test_stale_timeout_above_86400_rejected(self) -> None:
        """stale_timeout must not exceed 86400 seconds (1 day)."""
        schema = _timing_schema({CONF_DATA_SOURCE: DATA_SOURCE_MARINETRAFFIC})
        with pytest.raises(vol.Invalid):
            schema(
                {
                    CONF_UPDATE_INTERVAL: MIN_UPDATE_INTERVAL,
                    CONF_STALE_TIMEOUT: 86401,
                    CONF_FILTER_VESSEL_TYPES: [],
                    CONF_EXCLUDE_ANCHORED: False,
                }
            )

    def test_aishub_in_extra_sources_uses_api_floor(self) -> None:
        """AISHub as an extra source should also lower the floor."""
        schema = _timing_schema(
            {
                CONF_DATA_SOURCE: DATA_SOURCE_MARINETRAFFIC,
                CONF_EXTRA_SOURCES: [DATA_SOURCE_AISHUB],
            }
        )
        # Should accept MIN_UPDATE_INTERVAL_API
        result = schema(
            {
                CONF_UPDATE_INTERVAL: MIN_UPDATE_INTERVAL_API,
                CONF_STALE_TIMEOUT: DEFAULT_STALE_TIMEOUT,
                CONF_FILTER_VESSEL_TYPES: [],
                CONF_EXCLUDE_ANCHORED: False,
            }
        )
        assert result[CONF_UPDATE_INTERVAL] == MIN_UPDATE_INTERVAL_API

    def test_low_raw_interval_is_clamped_to_floor_in_defaults(self) -> None:
        """When an existing value is below floor, defaults are clamped, not rejected."""
        # _timing_schema clamps the default; the schema min ensures rejection below floor.
        schema = _timing_schema(
            {
                CONF_DATA_SOURCE: DATA_SOURCE_MARINETRAFFIC,
                CONF_UPDATE_INTERVAL: 1,  # below floor — default will be clamped
            }
        )
        # Attempting to pass the raw value via schema should be rejected.
        with pytest.raises(vol.Invalid):
            schema(
                {
                    CONF_UPDATE_INTERVAL: 1,
                    CONF_STALE_TIMEOUT: DEFAULT_STALE_TIMEOUT,
                    CONF_FILTER_VESSEL_TYPES: [],
                    CONF_EXCLUDE_ANCHORED: False,
                }
            )


# ---------------------------------------------------------------------------
# _box_schema — bounding box coordinate schema
# ---------------------------------------------------------------------------


class TestBoxSchema:
    """Tests for the _box_schema helper."""

    def test_schema_accepts_valid_coordinates(self) -> None:
        """Schema must accept valid bounding box coordinates."""
        schema = _box_schema({})
        result = schema(
            {
                CONF_NORTH: 60.0,
                CONF_EAST: 11.0,
                CONF_SOUTH: 59.0,
                CONF_WEST: 10.0,
            }
        )
        assert result[CONF_NORTH] == 60.0
        assert result[CONF_SOUTH] == 59.0

    def test_schema_rejects_latitude_above_90(self) -> None:
        schema = _box_schema({})
        with pytest.raises(vol.Invalid):
            schema(
                {
                    CONF_NORTH: 91.0,
                    CONF_EAST: 11.0,
                    CONF_SOUTH: 59.0,
                    CONF_WEST: 10.0,
                }
            )

    def test_schema_rejects_longitude_above_180(self) -> None:
        schema = _box_schema({})
        with pytest.raises(vol.Invalid):
            schema(
                {
                    CONF_NORTH: 60.0,
                    CONF_EAST: 181.0,
                    CONF_SOUTH: 59.0,
                    CONF_WEST: 10.0,
                }
            )

    def test_schema_rejects_latitude_below_minus_90(self) -> None:
        schema = _box_schema({})
        with pytest.raises(vol.Invalid):
            schema(
                {
                    CONF_NORTH: 60.0,
                    CONF_EAST: 11.0,
                    CONF_SOUTH: -91.0,
                    CONF_WEST: 10.0,
                }
            )

    def test_defaults_are_applied_from_existing_data(self) -> None:
        """Defaults from existing data must pre-populate the schema."""
        schema = _box_schema(
            {
                CONF_NORTH: 61.0,
                CONF_SOUTH: 58.0,
                CONF_EAST: 12.0,
                CONF_WEST: 9.0,
            }
        )
        # Calling the schema with the same values should succeed.
        result = schema(
            {CONF_NORTH: 61.0, CONF_EAST: 12.0, CONF_SOUTH: 58.0, CONF_WEST: 9.0}
        )
        assert result[CONF_NORTH] == 61.0


# ---------------------------------------------------------------------------
# _source_schema — data source selection schema
# ---------------------------------------------------------------------------


class TestSourceSchema:
    """Tests for the _source_schema helper."""

    def test_schema_accepts_valid_marinetraffic_source(self) -> None:
        schema = _source_schema({})
        result = schema(
            {
                CONF_DATA_SOURCE: DATA_SOURCE_MARINETRAFFIC,
                CONF_FALLBACK_SOURCE: FALLBACK_SOURCE_NONE,
                CONF_AISHUB_API_KEY: "",
                CONF_EXTRA_SOURCES: [],
            }
        )
        assert result[CONF_DATA_SOURCE] == DATA_SOURCE_MARINETRAFFIC

    def test_schema_accepts_aishub_source_with_key(self) -> None:
        schema = _source_schema({})
        result = schema(
            {
                CONF_DATA_SOURCE: DATA_SOURCE_AISHUB,
                CONF_FALLBACK_SOURCE: FALLBACK_SOURCE_NONE,
                CONF_AISHUB_API_KEY: "MYAPIKEY",
                CONF_EXTRA_SOURCES: [],
            }
        )
        assert result[CONF_DATA_SOURCE] == DATA_SOURCE_AISHUB

    def test_schema_rejects_unknown_data_source(self) -> None:
        schema = _source_schema({})
        with pytest.raises(vol.Invalid):
            schema(
                {
                    CONF_DATA_SOURCE: "unknown_source",
                    CONF_FALLBACK_SOURCE: FALLBACK_SOURCE_NONE,
                    CONF_AISHUB_API_KEY: "",
                    CONF_EXTRA_SOURCES: [],
                }
            )

    def test_schema_rejects_unknown_fallback_source(self) -> None:
        schema = _source_schema({})
        with pytest.raises(vol.Invalid):
            schema(
                {
                    CONF_DATA_SOURCE: DATA_SOURCE_MARINETRAFFIC,
                    CONF_FALLBACK_SOURCE: "bad_fallback",
                    CONF_AISHUB_API_KEY: "",
                    CONF_EXTRA_SOURCES: [],
                }
            )


# ---------------------------------------------------------------------------
# _make_title — entry title generation
# ---------------------------------------------------------------------------


class TestMakeTitle:
    """Tests for the _make_title helper method."""

    def test_radius_mode_title(self) -> None:
        """Radius mode title includes coordinates and radius."""
        flow = _make_config_flow()
        flow._data = {
            CONF_TRACKING_MODE: TRACKING_MODE_RADIUS,
            CONF_LATITUDE: 59.9,
            CONF_LONGITUDE: 10.7,
            CONF_RADIUS_KM: 50.0,
        }
        title = flow._make_title()
        assert "59.9000" in title
        assert "10.7000" in title
        assert "50" in title
        assert "MarineTraffic" in title

    def test_box_mode_title(self) -> None:
        """Box mode title includes bounding box coordinates."""
        flow = _make_config_flow()
        flow._data = {
            CONF_TRACKING_MODE: TRACKING_MODE_BOX,
            CONF_NORTH: 61.0,
            CONF_EAST: 11.5,
            CONF_SOUTH: 59.5,
            CONF_WEST: 9.0,
        }
        title = flow._make_title()
        assert "61.00" in title
        assert "11.50" in title
        assert "59.50" in title
        assert "9.00" in title
        assert "MarineTraffic" in title

    def test_radius_title_uses_default_radius_when_absent(self) -> None:
        """When radius is not set, the default radius appears in the title."""
        flow = _make_config_flow()
        flow._data = {
            CONF_TRACKING_MODE: TRACKING_MODE_RADIUS,
            CONF_LATITUDE: 0.0,
            CONF_LONGITUDE: 0.0,
        }
        title = flow._make_title()
        assert str(int(DEFAULT_RADIUS_KM)) in title

    def test_title_defaults_to_radius_mode_when_mode_absent(self) -> None:
        """When tracking mode is absent, radius format is used (safe default)."""
        flow = _make_config_flow()
        flow._data = {CONF_LATITUDE: 48.85, CONF_LONGITUDE: 2.35, CONF_RADIUS_KM: 25.0}
        title = flow._make_title()
        assert "48.8500" in title
        assert "2.3500" in title


# ---------------------------------------------------------------------------
# Config flow step: async_step_user
# ---------------------------------------------------------------------------


class TestConfigFlowStepUser:
    """Tests for MarineTrafficConfigFlow.async_step_user."""

    @pytest.mark.asyncio
    async def test_no_input_shows_user_form(self) -> None:
        """When no user_input is provided, the mode-selection form is shown."""
        flow = _make_config_flow()
        result = await flow.async_step_user(None)
        assert result["type"] == "form"
        call_kwargs = flow.async_show_form.call_args[1]
        assert call_kwargs["step_id"] == "user"

    @pytest.mark.asyncio
    async def test_radius_mode_navigates_to_radius_step(self) -> None:
        """Selecting radius tracking mode must navigate to the radius step."""
        flow = _make_config_flow()
        result = await flow.async_step_user({CONF_TRACKING_MODE: TRACKING_MODE_RADIUS})
        # The flow calls async_step_radius (no input) which shows a form.
        assert result["type"] == "form"
        assert flow._data[CONF_TRACKING_MODE] == TRACKING_MODE_RADIUS

    @pytest.mark.asyncio
    async def test_box_mode_navigates_to_box_step(self) -> None:
        """Selecting bounding-box mode must navigate to the box step."""
        flow = _make_config_flow()
        result = await flow.async_step_user({CONF_TRACKING_MODE: TRACKING_MODE_BOX})
        # async_step_box (no input) shows a form.
        assert result["type"] == "form"
        assert flow._data[CONF_TRACKING_MODE] == TRACKING_MODE_BOX


# ---------------------------------------------------------------------------
# Config flow step: async_step_box validation
# ---------------------------------------------------------------------------


class TestConfigFlowStepBox:
    """Tests for async_step_box geographic validation."""

    @pytest.mark.asyncio
    async def test_no_input_shows_box_form(self) -> None:
        """Without user_input, the box coordinate form is shown."""
        flow = _make_config_flow()
        result = await flow.async_step_box(None)
        assert result["type"] == "form"
        call_kwargs = flow.async_show_form.call_args[1]
        assert call_kwargs["step_id"] == "box"

    @pytest.mark.asyncio
    async def test_south_gte_north_returns_error(self) -> None:
        """When south >= north, the 'south_gte_north' error must be returned."""
        flow = _make_config_flow()
        result = await flow.async_step_box(
            {
                CONF_NORTH: 59.0,
                CONF_SOUTH: 60.0,  # south > north — invalid
                CONF_EAST: 11.0,
                CONF_WEST: 10.0,
            }
        )
        assert result["type"] == "form"
        errors = flow.async_show_form.call_args[1].get("errors", {})
        assert errors.get("base") == "south_gte_north"

    @pytest.mark.asyncio
    async def test_south_equal_to_north_returns_error(self) -> None:
        """When south == north, the same error must be returned."""
        flow = _make_config_flow()
        await flow.async_step_box(
            {
                CONF_NORTH: 60.0,
                CONF_SOUTH: 60.0,  # equal — invalid
                CONF_EAST: 11.0,
                CONF_WEST: 10.0,
            }
        )
        errors = flow.async_show_form.call_args[1].get("errors", {})
        assert errors.get("base") == "south_gte_north"

    @pytest.mark.asyncio
    async def test_west_gte_east_returns_error(self) -> None:
        """When west >= east, the 'west_gte_east' error must be returned."""
        flow = _make_config_flow()
        await flow.async_step_box(
            {
                CONF_NORTH: 61.0,
                CONF_SOUTH: 59.0,
                CONF_EAST: 10.0,
                CONF_WEST: 11.0,  # west > east — invalid
            }
        )
        errors = flow.async_show_form.call_args[1].get("errors", {})
        assert errors.get("base") == "west_gte_east"

    @pytest.mark.asyncio
    async def test_valid_box_advances_to_source_step(self) -> None:
        """A valid bounding box must advance to the data source step."""
        flow = _make_config_flow()
        result = await flow.async_step_box(
            {
                CONF_NORTH: 61.0,
                CONF_SOUTH: 59.0,
                CONF_EAST: 11.0,
                CONF_WEST: 9.0,
            }
        )
        # async_step_source with no input shows a form.
        assert result["type"] == "form"
        assert flow._data[CONF_NORTH] == 61.0
        assert flow._data[CONF_SOUTH] == 59.0


# ---------------------------------------------------------------------------
# Config flow step: async_step_source validation
# ---------------------------------------------------------------------------


class TestConfigFlowStepSource:
    """Tests for async_step_source validation logic."""

    @pytest.mark.asyncio
    async def test_no_input_shows_source_form(self) -> None:
        """Without user_input, the source selection form is shown."""
        flow = _make_config_flow()
        result = await flow.async_step_source(None)
        assert result["type"] == "form"
        assert flow.async_show_form.call_args[1]["step_id"] == "source"

    @pytest.mark.asyncio
    async def test_aishub_primary_without_key_returns_error(self) -> None:
        """Selecting AISHub as primary without an API key must fail."""
        flow = _make_config_flow()
        await flow.async_step_source(
            {
                CONF_DATA_SOURCE: DATA_SOURCE_AISHUB,
                CONF_FALLBACK_SOURCE: FALLBACK_SOURCE_NONE,
                CONF_AISHUB_API_KEY: "",
                CONF_EXTRA_SOURCES: [],
            }
        )
        errors = flow.async_show_form.call_args[1].get("errors", {})
        assert CONF_AISHUB_API_KEY in errors

    @pytest.mark.asyncio
    async def test_aishub_fallback_without_key_returns_error(self) -> None:
        """AISHub as fallback without an API key must also fail."""
        flow = _make_config_flow()
        await flow.async_step_source(
            {
                CONF_DATA_SOURCE: DATA_SOURCE_MARINETRAFFIC,
                CONF_FALLBACK_SOURCE: DATA_SOURCE_AISHUB,
                CONF_AISHUB_API_KEY: "",
                CONF_EXTRA_SOURCES: [],
            }
        )
        errors = flow.async_show_form.call_args[1].get("errors", {})
        assert CONF_AISHUB_API_KEY in errors

    @pytest.mark.asyncio
    async def test_aishub_extra_source_without_key_returns_error(self) -> None:
        """AISHub in extra_sources without a key must fail."""
        flow = _make_config_flow()
        await flow.async_step_source(
            {
                CONF_DATA_SOURCE: DATA_SOURCE_MARINETRAFFIC,
                CONF_FALLBACK_SOURCE: FALLBACK_SOURCE_NONE,
                CONF_AISHUB_API_KEY: "",
                CONF_EXTRA_SOURCES: [DATA_SOURCE_AISHUB],
            }
        )
        errors = flow.async_show_form.call_args[1].get("errors", {})
        assert CONF_AISHUB_API_KEY in errors

    @pytest.mark.asyncio
    async def test_fallback_same_as_primary_returns_error(self) -> None:
        """Fallback source equal to primary must be rejected."""
        flow = _make_config_flow()
        await flow.async_step_source(
            {
                CONF_DATA_SOURCE: DATA_SOURCE_MARINETRAFFIC,
                CONF_FALLBACK_SOURCE: DATA_SOURCE_MARINETRAFFIC,
                CONF_AISHUB_API_KEY: "",
                CONF_EXTRA_SOURCES: [],
            }
        )
        errors = flow.async_show_form.call_args[1].get("errors", {})
        assert CONF_FALLBACK_SOURCE in errors

    @pytest.mark.asyncio
    async def test_valid_marinetraffic_source_advances(self) -> None:
        """MarineTraffic as primary with no AISHub dependency must advance."""
        flow = _make_config_flow()
        result = await flow.async_step_source(
            {
                CONF_DATA_SOURCE: DATA_SOURCE_MARINETRAFFIC,
                CONF_FALLBACK_SOURCE: FALLBACK_SOURCE_NONE,
                CONF_AISHUB_API_KEY: "",
                CONF_EXTRA_SOURCES: [],
            }
        )
        # Advances to timing step (which shows a form with no input).
        assert result["type"] == "form"
        assert flow._data[CONF_DATA_SOURCE] == DATA_SOURCE_MARINETRAFFIC

    @pytest.mark.asyncio
    async def test_valid_aishub_with_key_advances(self) -> None:
        """AISHub as primary with a valid key must advance."""
        flow = _make_config_flow()
        flow._data[CONF_TRACKING_MODE] = TRACKING_MODE_RADIUS
        flow._data[CONF_LATITUDE] = 59.9
        flow._data[CONF_LONGITUDE] = 10.7
        flow._data[CONF_RADIUS_KM] = 50.0
        result = await flow.async_step_source(
            {
                CONF_DATA_SOURCE: DATA_SOURCE_AISHUB,
                CONF_FALLBACK_SOURCE: FALLBACK_SOURCE_NONE,
                CONF_AISHUB_API_KEY: "VALIDKEY",
                CONF_EXTRA_SOURCES: [],
            }
        )
        assert result["type"] == "form"
        assert flow._data[CONF_AISHUB_API_KEY] == "VALIDKEY"

    @pytest.mark.asyncio
    async def test_aishub_key_is_stripped_of_whitespace(self) -> None:
        """Leading/trailing whitespace in the API key must be stripped."""
        flow = _make_config_flow()
        await flow.async_step_source(
            {
                CONF_DATA_SOURCE: DATA_SOURCE_AISHUB,
                CONF_FALLBACK_SOURCE: FALLBACK_SOURCE_NONE,
                CONF_AISHUB_API_KEY: "  MYKEY  ",
                CONF_EXTRA_SOURCES: [],
            }
        )
        assert flow._data.get(CONF_AISHUB_API_KEY) == "MYKEY"

    @pytest.mark.asyncio
    async def test_extra_sources_stored_as_list(self) -> None:
        """Extra sources must be stored as a list regardless of input type."""
        flow = _make_config_flow()
        await flow.async_step_source(
            {
                CONF_DATA_SOURCE: DATA_SOURCE_MARINETRAFFIC,
                CONF_FALLBACK_SOURCE: FALLBACK_SOURCE_NONE,
                CONF_AISHUB_API_KEY: "",
                CONF_EXTRA_SOURCES: [DATA_SOURCE_VESSELFINDER],
            }
        )
        assert isinstance(flow._data.get(CONF_EXTRA_SOURCES), list)


# ---------------------------------------------------------------------------
# Config flow step: async_step_timing — creates the entry
# ---------------------------------------------------------------------------


class TestConfigFlowStepTiming:
    """Tests for async_step_timing and final entry creation."""

    @pytest.mark.asyncio
    async def test_no_input_shows_timing_form(self) -> None:
        flow = _make_config_flow()
        flow._data[CONF_DATA_SOURCE] = DATA_SOURCE_MARINETRAFFIC
        flow._data[CONF_EXTRA_SOURCES] = []
        result = await flow.async_step_timing(None)
        assert result["type"] == "form"
        assert flow.async_show_form.call_args[1]["step_id"] == "timing"

    @pytest.mark.asyncio
    async def test_valid_timing_creates_entry_radius_mode(self) -> None:
        """Valid timing data with radius mode must create a config entry."""
        flow = _make_config_flow()
        flow._data = {
            CONF_TRACKING_MODE: TRACKING_MODE_RADIUS,
            CONF_LATITUDE: 59.9,
            CONF_LONGITUDE: 10.7,
            CONF_RADIUS_KM: 50.0,
            CONF_DATA_SOURCE: DATA_SOURCE_MARINETRAFFIC,
            CONF_EXTRA_SOURCES: [],
        }
        result = await flow.async_step_timing(
            {
                CONF_UPDATE_INTERVAL: 60,
                CONF_STALE_TIMEOUT: DEFAULT_STALE_TIMEOUT,
                CONF_FILTER_VESSEL_TYPES: [],
                CONF_EXCLUDE_ANCHORED: False,
            }
        )
        assert result["type"] == "create_entry"
        flow.async_set_unique_id.assert_called_once()

    @pytest.mark.asyncio
    async def test_valid_timing_creates_entry_box_mode(self) -> None:
        """Valid timing data with box mode must create a config entry."""
        flow = _make_config_flow()
        flow._data = {
            CONF_TRACKING_MODE: TRACKING_MODE_BOX,
            CONF_NORTH: 61.0,
            CONF_EAST: 11.0,
            CONF_SOUTH: 59.0,
            CONF_WEST: 9.0,
            CONF_DATA_SOURCE: DATA_SOURCE_MARINETRAFFIC,
            CONF_EXTRA_SOURCES: [],
        }
        result = await flow.async_step_timing(
            {
                CONF_UPDATE_INTERVAL: 60,
                CONF_STALE_TIMEOUT: DEFAULT_STALE_TIMEOUT,
                CONF_FILTER_VESSEL_TYPES: [],
                CONF_EXCLUDE_ANCHORED: False,
            }
        )
        assert result["type"] == "create_entry"
        flow.async_set_unique_id.assert_called_once()

    @pytest.mark.asyncio
    async def test_unique_id_contains_coordinates_radius_mode(self) -> None:
        """Unique ID for radius mode must encode lat/lon/radius."""
        flow = _make_config_flow()
        flow._data = {
            CONF_TRACKING_MODE: TRACKING_MODE_RADIUS,
            CONF_LATITUDE: 48.85,
            CONF_LONGITUDE: 2.35,
            CONF_RADIUS_KM: 25.0,
            CONF_DATA_SOURCE: DATA_SOURCE_MARINETRAFFIC,
            CONF_EXTRA_SOURCES: [],
        }
        await flow.async_step_timing(
            {
                CONF_UPDATE_INTERVAL: 60,
                CONF_STALE_TIMEOUT: DEFAULT_STALE_TIMEOUT,
                CONF_FILTER_VESSEL_TYPES: [],
                CONF_EXCLUDE_ANCHORED: False,
            }
        )
        uid = flow.async_set_unique_id.call_args[0][0]
        assert "48.85" in uid
        assert "2.35" in uid

    @pytest.mark.asyncio
    async def test_unique_id_contains_coordinates_box_mode(self) -> None:
        """Unique ID for box mode must encode N/E/S/W."""
        flow = _make_config_flow()
        flow._data = {
            CONF_TRACKING_MODE: TRACKING_MODE_BOX,
            CONF_NORTH: 61.0,
            CONF_EAST: 11.5,
            CONF_SOUTH: 59.0,
            CONF_WEST: 9.0,
            CONF_DATA_SOURCE: DATA_SOURCE_MARINETRAFFIC,
            CONF_EXTRA_SOURCES: [],
        }
        await flow.async_step_timing(
            {
                CONF_UPDATE_INTERVAL: 60,
                CONF_STALE_TIMEOUT: DEFAULT_STALE_TIMEOUT,
                CONF_FILTER_VESSEL_TYPES: [],
                CONF_EXCLUDE_ANCHORED: False,
            }
        )
        uid = flow.async_set_unique_id.call_args[0][0]
        assert "61.0" in uid
        assert "11.5" in uid


# ---------------------------------------------------------------------------
# Config flow: complete happy-path flow
# ---------------------------------------------------------------------------


class TestConfigFlowHappyPath:
    """End-to-end flow tests: user → [radius|box] → source → timing → entry."""

    @pytest.mark.asyncio
    async def test_radius_flow_end_to_end(self) -> None:
        """Full radius mode flow must end with a config entry creation."""
        flow = _make_config_flow()

        # Step 1: choose mode
        await flow.async_step_user({CONF_TRACKING_MODE: TRACKING_MODE_RADIUS})

        # Step 2: enter radius (simulating location selector output)
        await flow.async_step_radius(
            {"location": {"latitude": 59.9, "longitude": 10.7, "radius": 50_000}}
        )

        # Step 3: choose source
        await flow.async_step_source(
            {
                CONF_DATA_SOURCE: DATA_SOURCE_MARINETRAFFIC,
                CONF_FALLBACK_SOURCE: FALLBACK_SOURCE_NONE,
                CONF_AISHUB_API_KEY: "",
                CONF_EXTRA_SOURCES: [],
            }
        )

        # Step 4: enter timing
        result = await flow.async_step_timing(
            {
                CONF_UPDATE_INTERVAL: 60,
                CONF_STALE_TIMEOUT: DEFAULT_STALE_TIMEOUT,
                CONF_FILTER_VESSEL_TYPES: [],
                CONF_EXCLUDE_ANCHORED: False,
            }
        )

        assert result["type"] == "create_entry"
        assert flow._data[CONF_LATITUDE] == 59.9
        assert flow._data[CONF_LONGITUDE] == 10.7
        assert flow._data[CONF_RADIUS_KM] == 50.0  # converted from metres

    @pytest.mark.asyncio
    async def test_box_flow_end_to_end(self) -> None:
        """Full bounding-box mode flow must end with a config entry creation."""
        flow = _make_config_flow()

        await flow.async_step_user({CONF_TRACKING_MODE: TRACKING_MODE_BOX})
        await flow.async_step_box(
            {CONF_NORTH: 61.0, CONF_EAST: 11.0, CONF_SOUTH: 59.0, CONF_WEST: 9.0}
        )
        await flow.async_step_source(
            {
                CONF_DATA_SOURCE: DATA_SOURCE_MARINETRAFFIC,
                CONF_FALLBACK_SOURCE: FALLBACK_SOURCE_NONE,
                CONF_AISHUB_API_KEY: "",
                CONF_EXTRA_SOURCES: [],
            }
        )
        result = await flow.async_step_timing(
            {
                CONF_UPDATE_INTERVAL: 60,
                CONF_STALE_TIMEOUT: DEFAULT_STALE_TIMEOUT,
                CONF_FILTER_VESSEL_TYPES: [],
                CONF_EXCLUDE_ANCHORED: False,
            }
        )

        assert result["type"] == "create_entry"
        assert flow._data[CONF_NORTH] == 61.0
        assert flow._data[CONF_DATA_SOURCE] == DATA_SOURCE_MARINETRAFFIC


# ---------------------------------------------------------------------------
# Options flow
# ---------------------------------------------------------------------------


class TestOptionsFlow:
    """Tests for MarineTrafficOptionsFlow."""

    @pytest.mark.asyncio
    async def test_no_input_shows_source_form(self) -> None:
        """Without input, the options init step shows the source form."""
        flow = _make_options_flow()
        result = await flow.async_step_init(None)
        assert result["type"] == "form"
        assert flow.async_show_form.call_args[1]["step_id"] == "init"

    @pytest.mark.asyncio
    async def test_aishub_without_key_returns_error(self) -> None:
        """Options flow must reject AISHub without an API key."""
        flow = _make_options_flow()
        await flow.async_step_init(
            {
                CONF_DATA_SOURCE: DATA_SOURCE_AISHUB,
                CONF_FALLBACK_SOURCE: FALLBACK_SOURCE_NONE,
                CONF_AISHUB_API_KEY: "",
                CONF_EXTRA_SOURCES: [],
            }
        )
        errors = flow.async_show_form.call_args[1].get("errors", {})
        assert CONF_AISHUB_API_KEY in errors

    @pytest.mark.asyncio
    async def test_fallback_same_as_primary_returns_error(self) -> None:
        """Options flow must reject fallback equal to primary."""
        flow = _make_options_flow()
        await flow.async_step_init(
            {
                CONF_DATA_SOURCE: DATA_SOURCE_MARINETRAFFIC,
                CONF_FALLBACK_SOURCE: DATA_SOURCE_MARINETRAFFIC,
                CONF_AISHUB_API_KEY: "",
                CONF_EXTRA_SOURCES: [],
            }
        )
        errors = flow.async_show_form.call_args[1].get("errors", {})
        assert CONF_FALLBACK_SOURCE in errors

    @pytest.mark.asyncio
    async def test_valid_source_advances_to_timing_step(self) -> None:
        """Valid source options must advance to the timing step."""
        flow = _make_options_flow()
        result = await flow.async_step_init(
            {
                CONF_DATA_SOURCE: DATA_SOURCE_MARINETRAFFIC,
                CONF_FALLBACK_SOURCE: FALLBACK_SOURCE_NONE,
                CONF_AISHUB_API_KEY: "",
                CONF_EXTRA_SOURCES: [],
            }
        )
        # Should show timing form (no input yet).
        assert result["type"] == "form"
        assert flow.async_show_form.call_args[1]["step_id"] == "timing"

    @pytest.mark.asyncio
    async def test_timing_step_creates_options_entry(self) -> None:
        """Completing timing in options flow must create an options entry."""
        flow = _make_options_flow()
        flow._options = {
            CONF_DATA_SOURCE: DATA_SOURCE_MARINETRAFFIC,
            CONF_EXTRA_SOURCES: [],
        }
        result = await flow.async_step_timing(
            {
                CONF_UPDATE_INTERVAL: 120,
                CONF_STALE_TIMEOUT: DEFAULT_STALE_TIMEOUT,
                CONF_FILTER_VESSEL_TYPES: [],
                CONF_EXCLUDE_ANCHORED: False,
            }
        )
        assert result["type"] == "create_entry"
        assert flow._options[CONF_UPDATE_INTERVAL] == 120

    @pytest.mark.asyncio
    async def test_options_aishub_key_stripped(self) -> None:
        """Options flow must strip whitespace from the AISHub API key."""
        flow = _make_options_flow()
        await flow.async_step_init(
            {
                CONF_DATA_SOURCE: DATA_SOURCE_AISHUB,
                CONF_FALLBACK_SOURCE: FALLBACK_SOURCE_NONE,
                CONF_AISHUB_API_KEY: "  TRIMMEDKEY  ",
                CONF_EXTRA_SOURCES: [],
            }
        )
        assert flow._options.get(CONF_AISHUB_API_KEY) == "TRIMMEDKEY"

    @pytest.mark.asyncio
    async def test_options_timing_no_input_shows_form(self) -> None:
        """Without user_input the options timing step shows a form."""
        flow = _make_options_flow()
        flow._options = {
            CONF_DATA_SOURCE: DATA_SOURCE_MARINETRAFFIC,
            CONF_EXTRA_SOURCES: [],
        }
        result = await flow.async_step_timing(None)
        assert result["type"] == "form"
        assert flow.async_show_form.call_args[1]["step_id"] == "timing"
