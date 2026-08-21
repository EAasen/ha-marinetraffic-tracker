"""Integration tests for the Norwegian Maritime Tracker integration.

These tests exercise the full setup flow, data pipeline, entity creation, and
error-recovery paths using the Home Assistant test framework
(pytest-homeassistant-custom-component) together with mocked BarentsWatch/
Kystverket API responses.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.marinetraffic_tracker.client import VesselData
from custom_components.marinetraffic_tracker.const import (
    CONF_BARENTSWATCH_CLIENT_ID,
    CONF_BARENTSWATCH_CLIENT_SECRET,
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
    DEFAULT_STALE_TIMEOUT,
    DOMAIN,
    TRACKING_MODE_BOX,
    TRACKING_MODE_RADIUS,
)

# ---------------------------------------------------------------------------
# Enable custom integrations for every test in this module
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _auto_enable_custom(enable_custom_integrations: None) -> None:  # noqa: PT004
    """Ensure the marinetraffic_tracker custom component is loadable in all tests."""

# ---------------------------------------------------------------------------
# Shared sample vessels
# ---------------------------------------------------------------------------


def _make_vessel_a() -> VesselData:
    """Return a fresh VesselData for NORDIC STAR with the current timestamp."""
    return VesselData(
        mmsi="123456789",
        name="NORDIC STAR",
        vessel_type=70,
        latitude=60.4,
        longitude=5.3,
        heading=90,
        course=90,
        speed=10.0,
        status="Under Way Using Engine",
        origin="BERGEN",
        destination="STAVANGER",
        eta="2026-06-01 08:00:00",
        last_seen=datetime.now(UTC),
    )


def _make_vessel_b() -> VesselData:
    """Return a fresh VesselData for SEA EXPLORER with the current timestamp."""
    return VesselData(
        mmsi="987654321",
        name="SEA EXPLORER",
        vessel_type=80,
        latitude=60.5,
        longitude=5.4,
        heading=180,
        course=180,
        speed=5.0,
        status="At Anchor",
        origin="STAVANGER",
        destination=None,
        eta=None,
        last_seen=datetime.now(UTC),
    )


def _make_vessel_c() -> VesselData:
    """Return a fresh VesselData for FJORD RUNNER with the current timestamp."""
    return VesselData(
        mmsi="555111222",
        name="FJORD RUNNER",
        vessel_type=60,
        latitude=60.3,
        longitude=5.2,
        heading=270,
        course=270,
        speed=15.0,
        status="Under Way Using Engine",
        origin="OSLO",
        destination="BERGEN",
        eta=None,
        last_seen=datetime.now(UTC),
    )


_VESSEL_A = _make_vessel_a()
_VESSEL_B = _make_vessel_b()
_VESSEL_C = _make_vessel_c()

# ---------------------------------------------------------------------------
# Helper — build a MockConfigEntry for the integration
# ---------------------------------------------------------------------------

_BASE_ENTRY_DATA = {
    CONF_TRACKING_MODE: TRACKING_MODE_RADIUS,
    CONF_LATITUDE: 60.4,
    CONF_LONGITUDE: 5.3,
    CONF_RADIUS_KM: 50.0,
    CONF_UPDATE_INTERVAL: 60,
    CONF_STALE_TIMEOUT: DEFAULT_STALE_TIMEOUT,
    CONF_FILTER_VESSEL_TYPES: [],
    CONF_EXCLUDE_ANCHORED: False,
    CONF_BARENTSWATCH_CLIENT_ID: "test-client-id",
    CONF_BARENTSWATCH_CLIENT_SECRET: "test-client-secret",
    "data_source": DATA_SOURCE_KYSTVERKET,
}


def _make_entry(**overrides) -> MockConfigEntry:
    data = {**_BASE_ENTRY_DATA, **overrides}
    return MockConfigEntry(domain=DOMAIN, data=data, options={})


def _make_mock_client(vessels: list[VesselData] | None = None) -> MagicMock:
    """Return a mock VesselClient that returns *vessels* for any fetch call."""
    client = MagicMock()
    client.get_vessels_in_radius = AsyncMock(return_value=vessels or [])
    client.get_vessels_in_box = AsyncMock(return_value=vessels or [])
    return client


async def _setup_integration(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """Add the config entry to HA, injecting *mock_client* instead of a real one."""
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.marinetraffic_tracker._build_client",
            return_value=mock_client,
        ),
        patch("custom_components.marinetraffic_tracker.coordinator.asyncio.sleep"),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


# ===========================================================================
# Setup Flow Tests
# ===========================================================================


async def test_integration_loads_successfully(hass: HomeAssistant) -> None:
    """Complete config entry setup should load without errors."""
    entry = _make_entry()
    client = _make_mock_client()

    await _setup_integration(hass, entry, client)

    assert entry.state.value == "loaded"
    assert DOMAIN in hass.data
    assert entry.entry_id in hass.data[DOMAIN]


async def test_integration_unloads_cleanly(hass: HomeAssistant) -> None:
    """Unloading the entry should remove it from hass.data."""
    entry = _make_entry()
    client = _make_mock_client()

    await _setup_integration(hass, entry, client)
    assert entry.entry_id in hass.data[DOMAIN]

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.entry_id not in hass.data.get(DOMAIN, {})


async def test_integration_creates_coordinator(hass: HomeAssistant) -> None:
    """The coordinator should be stored in hass.data after setup."""
    from custom_components.marinetraffic_tracker.coordinator import MarineTrafficCoordinator

    entry = _make_entry()
    client = _make_mock_client()

    await _setup_integration(hass, entry, client)

    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert isinstance(coordinator, MarineTrafficCoordinator)


async def test_setup_with_bounding_box_mode(hass: HomeAssistant) -> None:
    """Setup should succeed for bounding-box tracking mode too."""
    entry = _make_entry(
        **{
            CONF_TRACKING_MODE: TRACKING_MODE_BOX,
            CONF_NORTH: 61.0,
            CONF_EAST: 6.0,
            CONF_SOUTH: 60.0,
            CONF_WEST: 5.0,
        },
    )
    client = _make_mock_client()

    await _setup_integration(hass, entry, client)

    assert entry.state.value == "loaded"


# ===========================================================================
# Data Flow Tests
# ===========================================================================


async def test_vessel_appears_creates_entities(hass: HomeAssistant) -> None:
    """When a vessel is returned by the API it should appear as an entity."""
    entry = _make_entry()
    client = _make_mock_client(vessels=[_VESSEL_A])

    await _setup_integration(hass, entry, client)

    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    vessel_entries = [
        e
        for e in registry.entities.values()
        if _VESSEL_A.mmsi in (e.unique_id or "")
    ]
    assert vessel_entries, "Expected at least one entity for vessel MMSI"


async def test_vessel_count_sensor_reflects_active_vessels(hass: HomeAssistant) -> None:
    """The count sensor state should equal the number of tracked vessels."""
    entry = _make_entry()
    client = _make_mock_client(vessels=[_VESSEL_A, _VESSEL_B])

    await _setup_integration(hass, entry, client)

    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    count_entry = next(
        (e for e in registry.entities.values() if e.unique_id == f"{entry.entry_id}_count"),
        None,
    )
    assert count_entry is not None, "Count sensor entity not found in registry"

    state = hass.states.get(count_entry.entity_id)
    assert state is not None
    assert state.state == "2"


async def test_vessel_count_zero_when_no_vessels(hass: HomeAssistant) -> None:
    """Count sensor should report 0 when no vessels are tracked."""
    entry = _make_entry()
    client = _make_mock_client(vessels=[])

    await _setup_integration(hass, entry, client)

    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    count_entry = next(
        (e for e in registry.entities.values() if e.unique_id == f"{entry.entry_id}_count"),
        None,
    )
    assert count_entry is not None

    state = hass.states.get(count_entry.entity_id)
    assert state is not None
    assert state.state == "0"


async def test_vessel_data_updates_on_refresh(hass: HomeAssistant) -> None:
    """After a coordinator refresh the vessel count should reflect new data."""
    entry = _make_entry()
    client = _make_mock_client(vessels=[_VESSEL_A])

    await _setup_integration(hass, entry, client)

    coordinator = hass.data[DOMAIN][entry.entry_id]

    # Update the mock to return two vessels and trigger a refresh
    client.get_vessels_in_radius.return_value = [_VESSEL_A, _VESSEL_B]
    client.get_vessels_in_box.return_value = [_VESSEL_A, _VESSEL_B]

    with patch("custom_components.marinetraffic_tracker.coordinator.asyncio.sleep"):
        await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(coordinator.data) == 2
    assert _VESSEL_A.mmsi in coordinator.data
    assert _VESSEL_B.mmsi in coordinator.data


async def test_vessel_leaves_boundary_removed_from_active(hass: HomeAssistant) -> None:
    """A vessel absent from the API response should be removed from active data."""
    # Use stale_timeout=0 so vessels absent from the next poll are removed immediately.
    entry = _make_entry(**{CONF_STALE_TIMEOUT: 0})
    client = _make_mock_client(vessels=[_VESSEL_A, _VESSEL_B])

    await _setup_integration(hass, entry, client)

    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert len(coordinator.data) == 2

    # Vessel B leaves — only Vessel A is returned
    client.get_vessels_in_radius.return_value = [_VESSEL_A]
    client.get_vessels_in_box.return_value = [_VESSEL_A]

    with patch("custom_components.marinetraffic_tracker.coordinator.asyncio.sleep"):
        await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert _VESSEL_A.mmsi in coordinator.data
    assert _VESSEL_B.mmsi not in coordinator.data


async def test_multiple_vessels_tracked_simultaneously(hass: HomeAssistant) -> None:
    """All vessels returned by the API should be tracked concurrently."""
    entry = _make_entry()
    vessels = [_VESSEL_A, _VESSEL_B, _VESSEL_C]
    client = _make_mock_client(vessels=vessels)

    await _setup_integration(hass, entry, client)

    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert len(coordinator.data) == 3
    for vessel in vessels:
        assert vessel.mmsi in coordinator.data


# ===========================================================================
# Entity Tests
# ===========================================================================


async def test_vessel_sensor_state_is_vessel_name(hass: HomeAssistant) -> None:
    """Per-vessel sensor entity should be registered with the vessel name as its name."""
    entry = _make_entry()
    client = _make_mock_client(vessels=[_VESSEL_A])

    await _setup_integration(hass, entry, client)

    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    vessel_entry = next(
        (
            e
            for e in registry.entities.values()
            if e.unique_id == f"{entry.entry_id}_vessel_{_VESSEL_A.mmsi}"
        ),
        None,
    )
    assert vessel_entry is not None

    # Per-vessel sensors are disabled by default; verify via coordinator data.
    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert _VESSEL_A.mmsi in coordinator.data
    assert coordinator.data[_VESSEL_A.mmsi].name == _VESSEL_A.name


async def test_vessel_sensor_exposes_speed_attribute(hass: HomeAssistant) -> None:
    """Coordinator data should expose the vessel speed for the sensor attribute."""
    entry = _make_entry()
    client = _make_mock_client(vessels=[_VESSEL_A])

    await _setup_integration(hass, entry, client)

    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert _VESSEL_A.mmsi in coordinator.data
    assert coordinator.data[_VESSEL_A.mmsi].speed == pytest.approx(_VESSEL_A.speed)


async def test_device_tracker_gps_coordinates(hass: HomeAssistant) -> None:
    """Device tracker entity should be registered with latitude/longitude in coordinator data."""
    entry = _make_entry()
    client = _make_mock_client(vessels=[_VESSEL_A])

    await _setup_integration(hass, entry, client)

    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    tracker_entry = next(
        (
            e
            for e in registry.entities.values()
            if e.domain == "device_tracker"
            and _VESSEL_A.mmsi in (e.unique_id or "")
        ),
        None,
    )
    assert tracker_entry is not None

    # Verify GPS coordinates in coordinator data (device trackers are disabled by default).
    coordinator = hass.data[DOMAIN][entry.entry_id]
    vessel = coordinator.data[_VESSEL_A.mmsi]
    assert vessel.latitude == pytest.approx(_VESSEL_A.latitude)
    assert vessel.longitude == pytest.approx(_VESSEL_A.longitude)


async def test_vessel_sensor_mmsi_attribute(hass: HomeAssistant) -> None:
    """Coordinator data should expose the MMSI that the sensor entity uses."""
    entry = _make_entry()
    client = _make_mock_client(vessels=[_VESSEL_A])

    await _setup_integration(hass, entry, client)

    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert _VESSEL_A.mmsi in coordinator.data
    assert coordinator.data[_VESSEL_A.mmsi].mmsi == _VESSEL_A.mmsi


# ===========================================================================
# Error Recovery Tests
# ===========================================================================


async def test_api_connection_loss_raises_update_failed(hass: HomeAssistant) -> None:
    """When the API is unreachable, the coordinator should mark the update as failed."""
    entry = _make_entry()
    client = _make_mock_client(vessels=[_VESSEL_A])

    await _setup_integration(hass, entry, client)

    coordinator = hass.data[DOMAIN][entry.entry_id]

    # Simulate a network outage
    client.get_vessels_in_radius.side_effect = Exception("connection refused")
    client.get_vessels_in_box.side_effect = Exception("connection refused")

    with patch("custom_components.marinetraffic_tracker.coordinator.asyncio.sleep"):
        await coordinator.async_refresh()

    assert coordinator.last_update_success is False
    assert coordinator.last_exception is not None


async def test_api_recovery_after_connection_loss(hass: HomeAssistant) -> None:
    """After an outage the coordinator should recover when the API comes back."""
    entry = _make_entry()
    client = _make_mock_client(vessels=[_VESSEL_A])

    await _setup_integration(hass, entry, client)

    coordinator = hass.data[DOMAIN][entry.entry_id]

    # Simulate outage
    client.get_vessels_in_radius.side_effect = Exception("network error")
    client.get_vessels_in_box.side_effect = Exception("network error")

    with patch("custom_components.marinetraffic_tracker.coordinator.asyncio.sleep"):
        await coordinator.async_refresh()

    assert coordinator.last_update_success is False

    # Restore the API
    client.get_vessels_in_radius.side_effect = None
    client.get_vessels_in_radius.return_value = [_VESSEL_A]
    client.get_vessels_in_box.side_effect = None
    client.get_vessels_in_box.return_value = [_VESSEL_A]

    with patch("custom_components.marinetraffic_tracker.coordinator.asyncio.sleep"):
        await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success is True
    assert _VESSEL_A.mmsi in coordinator.data


async def test_initial_fetch_failure_aborts_setup(hass: HomeAssistant) -> None:
    """If the very first API call fails, setup should abort gracefully."""
    from homeassistant.config_entries import ConfigEntryState

    entry = _make_entry()
    client = _make_mock_client()
    client.get_vessels_in_radius.side_effect = Exception("API unavailable")
    client.get_vessels_in_box.side_effect = Exception("API unavailable")

    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.marinetraffic_tracker._build_client",
            return_value=client,
        ),
        patch("custom_components.marinetraffic_tracker.coordinator.asyncio.sleep"),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state in (
        ConfigEntryState.SETUP_RETRY,
        ConfigEntryState.SETUP_ERROR,
    )


async def test_options_reload_resets_coordinator(hass: HomeAssistant) -> None:
    """Updating options should trigger a reload, creating a fresh coordinator."""
    entry = _make_entry()
    client = _make_mock_client(vessels=[_VESSEL_A])

    await _setup_integration(hass, entry, client)

    old_coordinator = hass.data[DOMAIN][entry.entry_id]

    with (
        patch(
            "custom_components.marinetraffic_tracker._build_client",
            return_value=_make_mock_client(vessels=[_VESSEL_A, _VESSEL_B]),
        ),
        patch("custom_components.marinetraffic_tracker.coordinator.asyncio.sleep"),
    ):
        hass.config_entries.async_update_entry(
            entry,
            options={CONF_UPDATE_INTERVAL: 120},
        )
        await hass.async_block_till_done()

    new_coordinator = hass.data[DOMAIN].get(entry.entry_id)
    # After reload a brand-new coordinator instance is stored.
    assert new_coordinator is not old_coordinator


# ===========================================================================
# Performance Tests
# ===========================================================================


async def test_update_speed_many_vessels(hass: HomeAssistant) -> None:
    """Coordinator refresh with 50 vessels should complete without error."""
    from dataclasses import replace

    many_vessels = [
        replace(
            _VESSEL_A,
            mmsi=str(100_000_000 + i),
            latitude=60.0 + i * 0.01,
            longitude=5.0 + i * 0.01,
        )
        for i in range(50)
    ]

    entry = _make_entry()
    client = _make_mock_client(vessels=many_vessels)

    await _setup_integration(hass, entry, client)

    coordinator = hass.data[DOMAIN][entry.entry_id]

    client.get_vessels_in_radius.return_value = many_vessels
    client.get_vessels_in_box.return_value = many_vessels

    with patch("custom_components.marinetraffic_tracker.coordinator.asyncio.sleep"):
        await coordinator.async_refresh()

    assert len(coordinator.data) == 50
    assert coordinator.last_update_success is True


async def test_coordinator_handles_empty_update_efficiently(hass: HomeAssistant) -> None:
    """A refresh with no vessels should complete without error and clear data."""
    # Use stale_timeout=0 so vessels absent from the next poll are removed immediately.
    entry = _make_entry(**{CONF_STALE_TIMEOUT: 0})
    client = _make_mock_client(vessels=[_VESSEL_A, _VESSEL_B])

    await _setup_integration(hass, entry, client)

    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert len(coordinator.data) == 2

    client.get_vessels_in_radius.return_value = []
    client.get_vessels_in_box.return_value = []

    with patch("custom_components.marinetraffic_tracker.coordinator.asyncio.sleep"):
        await coordinator.async_refresh()

    assert len(coordinator.data) == 0
