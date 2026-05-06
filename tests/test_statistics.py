"""Tests for the maritime statistics/highscore feature.

Covers:
- AreaStatistics.to_dict() — all fields when empty and when populated.
- Coordinator._update_statistics() — visit counts, speed record, size records,
  hourly/daily traffic pattern buckets.
- Coordinator._accumulate_time_in_zone() — cumulative time tracking.
- Visit counting: entering once vs. multiple times (re-entry after departure).
- MarineTrafficStatisticsSensor — native_value and extra_state_attributes.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.marinetraffic_tracker.const import (
    ATTR_BUSIEST_DAY,
    ATTR_BUSIEST_HOUR,
    ATTR_DAILY_COUNTS,
    ATTR_HOURLY_COUNTS,
    ATTR_LARGEST_VESSEL,
    ATTR_LONGEST_RESIDENT,
    ATTR_MOST_FREQUENT_VISITOR,
    ATTR_SMALLEST_VESSEL,
    ATTR_SPEED_RECORD,
    ATTR_TOTAL_VESSELS_SEEN,
    CONF_STALE_TIMEOUT,
    CONF_UPDATE_INTERVAL,
)
from custom_components.marinetraffic_tracker.coordinator import (
    AreaStatistics,
    MarineTrafficCoordinator,
    VesselRecord,
)

from .conftest import MOCK_VESSEL_CARGO, MOCK_VESSEL_PASSENGER, MOCK_VESSEL_TANKER

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CARGO = MOCK_VESSEL_CARGO
_TANKER = MOCK_VESSEL_TANKER
_PASSENGER = MOCK_VESSEL_PASSENGER


def _make_entry(
    stale_timeout: int = 600,
    update_interval: int = 60,
) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "test_stats_entry"
    entry.data = {
        CONF_UPDATE_INTERVAL: update_interval,
        CONF_STALE_TIMEOUT: stale_timeout,
        "tracking_mode": "radius",
        "latitude": 59.9,
        "longitude": 10.7,
        "radius_km": 50.0,
    }
    entry.options = {}
    return entry


def _make_coordinator(
    hass: MagicMock,
    client: AsyncMock,
    stale_timeout: int = 600,
) -> MarineTrafficCoordinator:
    return MarineTrafficCoordinator(hass, _make_entry(stale_timeout=stale_timeout), client)


async def _refresh(coordinator: MarineTrafficCoordinator) -> None:
    with patch("custom_components.marinetraffic_tracker.coordinator.asyncio.sleep"):
        await coordinator.async_refresh()


# ---------------------------------------------------------------------------
# AreaStatistics.to_dict() — empty state
# ---------------------------------------------------------------------------


def test_area_statistics_empty() -> None:
    """to_dict() on a fresh AreaStatistics must return safe None/zero values."""
    stats = AreaStatistics()
    d = stats.to_dict()

    assert d["most_frequent_visitor"] is None
    assert d["longest_resident"] is None
    assert d["speed_record"] is None
    assert d["largest_vessel"] is None
    assert d["smallest_vessel"] is None
    assert d["busiest_hour"] is None
    assert d["busiest_day"] is None
    assert d["hourly_counts"] == [0] * 24
    assert d["daily_counts"] == [0] * 7
    assert d["total_vessels_seen"] == 0


# ---------------------------------------------------------------------------
# AreaStatistics.to_dict() — populated state
# ---------------------------------------------------------------------------


def test_area_statistics_most_frequent_visitor() -> None:
    """most_frequent_visitor must return the MMSI with the highest visit count."""
    stats = AreaStatistics()
    stats.visit_counts = {"AAA": 5, "BBB": 2, "CCC": 8}
    stats.vessel_names = {"AAA": "Alpha", "BBB": "Beta", "CCC": "Charlie"}

    d = stats.to_dict()
    mfv = d["most_frequent_visitor"]
    assert mfv is not None
    assert mfv["mmsi"] == "CCC"
    assert mfv["name"] == "Charlie"
    assert mfv["visit_count"] == 8


def test_area_statistics_longest_resident() -> None:
    """longest_resident must return the MMSI with the most cumulative seconds."""
    stats = AreaStatistics()
    stats.total_time_seconds = {"X": 100.0, "Y": 9999.5, "Z": 500.0}
    stats.vessel_names = {"X": "X-Ship", "Y": "Y-Ship", "Z": "Z-Ship"}

    d = stats.to_dict()
    lr = d["longest_resident"]
    assert lr is not None
    assert lr["mmsi"] == "Y"
    assert lr["name"] == "Y-Ship"
    assert lr["total_time_seconds"] == 10000  # rounded


def test_area_statistics_speed_record() -> None:
    """speed_record must contain mmsi, name, speed_knots, and recorded_at."""
    stats = AreaStatistics()
    ts = "2026-01-01T12:00:00+00:00"
    stats.speed_record = VesselRecord(mmsi="111", name="Fast Ferry", value=42.5, recorded_at=ts)

    d = stats.to_dict()
    sr = d["speed_record"]
    assert sr is not None
    assert sr["mmsi"] == "111"
    assert sr["name"] == "Fast Ferry"
    assert sr["speed_knots"] == 42.5
    assert sr["recorded_at"] == ts


def test_area_statistics_size_records() -> None:
    """largest_vessel and smallest_vessel must contain length_m."""
    stats = AreaStatistics()
    ts = "2026-01-01T12:00:00+00:00"
    stats.largest_vessel = VesselRecord(mmsi="222", name="Giant Cargo", value=400.0, recorded_at=ts)
    stats.smallest_vessel = VesselRecord(mmsi="333", name="Tiny Boat", value=5.0, recorded_at=ts)

    d = stats.to_dict()
    assert d["largest_vessel"]["length_m"] == 400.0
    assert d["largest_vessel"]["name"] == "Giant Cargo"
    assert d["smallest_vessel"]["length_m"] == 5.0
    assert d["smallest_vessel"]["name"] == "Tiny Boat"


def test_area_statistics_busiest_hour_and_day() -> None:
    """busiest_hour and busiest_day must return the index of the max bucket."""
    stats = AreaStatistics()
    stats.hourly_counts[14] = 50
    stats.daily_counts[2] = 30  # Wednesday

    d = stats.to_dict()
    assert d["busiest_hour"] == 14
    assert d["busiest_day"] == 2


# ---------------------------------------------------------------------------
# Coordinator statistics via _async_update_data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_visit_count_increments_on_new_vessel() -> None:
    """Each new vessel entering must increment its visit count to 1."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()

    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[_CARGO])
    coordinator = _make_coordinator(hass, client)

    await _refresh(coordinator)

    stats = coordinator.statistics
    assert stats.visit_counts.get(_CARGO.mmsi) == 1
    assert stats.vessel_names.get(_CARGO.mmsi) == _CARGO.name


@pytest.mark.asyncio
async def test_visit_count_does_not_double_count_same_visit() -> None:
    """A vessel present in two consecutive polls must still have visit_count=1."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()

    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[_CARGO])
    coordinator = _make_coordinator(hass, client)

    await _refresh(coordinator)
    await _refresh(coordinator)

    assert coordinator.statistics.visit_counts[_CARGO.mmsi] == 1


@pytest.mark.asyncio
async def test_visit_count_increments_on_reentry() -> None:
    """A vessel that departs and re-enters must have visit_count=2."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()

    # Short stale timeout so the vessel is purged quickly.
    client = AsyncMock()
    coordinator = _make_coordinator(hass, client, stale_timeout=30)

    # First visit: vessel is present.
    client.get_vessels_in_radius = AsyncMock(return_value=[_CARGO])
    await _refresh(coordinator)
    assert coordinator.statistics.visit_counts[_CARGO.mmsi] == 1

    # Vessel departs: next poll returns no vessels; coordinator purges it.
    client.get_vessels_in_radius = AsyncMock(return_value=[])
    # Manually advance last_seen to force stale purge.
    old_vessel = coordinator._vessels[_CARGO.mmsi]
    coordinator._vessels[_CARGO.mmsi] = replace(
        old_vessel, last_seen=datetime.now(UTC) - timedelta(seconds=60)
    )
    await _refresh(coordinator)
    assert _CARGO.mmsi not in coordinator.data

    # Second visit: vessel reappears.
    client.get_vessels_in_radius = AsyncMock(return_value=[_CARGO])
    await _refresh(coordinator)
    assert coordinator.statistics.visit_counts[_CARGO.mmsi] == 2


@pytest.mark.asyncio
async def test_speed_record_updated() -> None:
    """Speed record must track the highest speed seen across all vessels."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()

    fast_vessel = replace(_CARGO, speed=35.0)
    slow_vessel = replace(_TANKER, speed=5.0)

    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[fast_vessel, slow_vessel])
    coordinator = _make_coordinator(hass, client)
    await _refresh(coordinator)

    sr = coordinator.statistics.speed_record
    assert sr is not None
    assert sr.mmsi == fast_vessel.mmsi
    assert sr.value == 35.0


@pytest.mark.asyncio
async def test_speed_record_none_speed_skipped() -> None:
    """A vessel with speed=None must not overwrite a valid speed record."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()

    vessel_with_speed = replace(_CARGO, speed=20.0)
    vessel_no_speed = replace(_TANKER, speed=None)

    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[vessel_with_speed])
    coordinator = _make_coordinator(hass, client)
    await _refresh(coordinator)

    client.get_vessels_in_radius = AsyncMock(return_value=[vessel_no_speed])
    await _refresh(coordinator)

    assert coordinator.statistics.speed_record is not None
    assert coordinator.statistics.speed_record.value == 20.0


@pytest.mark.asyncio
async def test_size_records_updated() -> None:
    """largest_vessel and smallest_vessel must reflect the observed extremes."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()

    big = replace(_CARGO, length=400)
    small = replace(_TANKER, length=15)

    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[big, small])
    coordinator = _make_coordinator(hass, client)
    await _refresh(coordinator)

    stats = coordinator.statistics
    assert stats.largest_vessel is not None
    assert stats.largest_vessel.value == 400.0
    assert stats.smallest_vessel is not None
    assert stats.smallest_vessel.value == 15.0


@pytest.mark.asyncio
async def test_size_record_zero_length_skipped() -> None:
    """Vessels with length=0 must not be recorded as size extremes."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()

    zero_length = replace(_CARGO, length=0)

    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[zero_length])
    coordinator = _make_coordinator(hass, client)
    await _refresh(coordinator)

    assert coordinator.statistics.largest_vessel is None
    assert coordinator.statistics.smallest_vessel is None


@pytest.mark.asyncio
async def test_hourly_and_daily_counts_incremented() -> None:
    """Each vessel observation must increment the correct hourly and daily buckets."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()

    client = AsyncMock()
    client.get_vessels_in_radius = AsyncMock(return_value=[_CARGO, _TANKER])
    coordinator = _make_coordinator(hass, client)

    fixed_now = datetime(2026, 5, 6, 14, 0, 0, tzinfo=UTC)  # Wednesday, hour 14
    with patch("custom_components.marinetraffic_tracker.coordinator.asyncio.sleep"):
        with patch(
            "custom_components.marinetraffic_tracker.coordinator.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = fixed_now
            await coordinator.async_refresh()

    stats = coordinator.statistics
    # Two vessels observed at hour 14 on Wednesday (weekday 2).
    assert stats.hourly_counts[14] == 2
    assert stats.daily_counts[2] == 2  # Wednesday


@pytest.mark.asyncio
async def test_time_in_zone_accumulated_on_departure() -> None:
    """Cumulative time in zone must be recorded when a vessel is purged as stale."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()

    client = AsyncMock()
    coordinator = _make_coordinator(hass, client, stale_timeout=30)

    # Vessel appears.
    client.get_vessels_in_radius = AsyncMock(return_value=[_CARGO])
    await _refresh(coordinator)

    # Force the vessel to appear stale.
    coordinator._vessels[_CARGO.mmsi] = replace(
        coordinator._vessels[_CARGO.mmsi],
        last_seen=datetime.now(UTC) - timedelta(seconds=60),
    )

    # Advance entry time so we get a measurable duration (~60 s).
    coordinator._entry_times[_CARGO.mmsi] = datetime.now(UTC) - timedelta(seconds=60)

    client.get_vessels_in_radius = AsyncMock(return_value=[])
    await _refresh(coordinator)

    elapsed = coordinator.statistics.total_time_seconds.get(_CARGO.mmsi, 0)
    assert elapsed > 0, "Time-in-zone should be positive after vessel departed"


# ---------------------------------------------------------------------------
# MarineTrafficStatisticsSensor
# ---------------------------------------------------------------------------


def _make_statistics_sensor():
    """Build a MarineTrafficStatisticsSensor with a mocked coordinator."""
    from custom_components.marinetraffic_tracker.sensor import MarineTrafficStatisticsSensor

    coordinator = MagicMock()
    coordinator.data = {}
    coordinator.last_update_success = True

    stats = AreaStatistics()
    stats.visit_counts = {"AAA": 3, "BBB": 1}
    stats.vessel_names = {"AAA": "Alpha", "BBB": "Beta"}
    stats.total_time_seconds = {"AAA": 3600.0}
    ts = "2026-01-01T12:00:00+00:00"
    stats.speed_record = VesselRecord(mmsi="AAA", name="Alpha", value=28.5, recorded_at=ts)
    stats.largest_vessel = VesselRecord(mmsi="AAA", name="Alpha", value=200.0, recorded_at=ts)
    stats.smallest_vessel = VesselRecord(mmsi="BBB", name="Beta", value=30.0, recorded_at=ts)
    stats.hourly_counts[10] = 5
    stats.daily_counts[0] = 3

    coordinator.statistics = stats

    sensor = MarineTrafficStatisticsSensor(coordinator, "test_entry")
    return sensor


def test_statistics_sensor_native_value() -> None:
    """native_value must equal the number of unique vessels ever seen."""
    sensor = _make_statistics_sensor()
    assert sensor.native_value == 2


def test_statistics_sensor_attributes_structure() -> None:
    """extra_state_attributes must contain all expected keys with correct values."""
    sensor = _make_statistics_sensor()
    attrs = sensor.extra_state_attributes

    assert ATTR_MOST_FREQUENT_VISITOR in attrs
    assert attrs[ATTR_MOST_FREQUENT_VISITOR]["mmsi"] == "AAA"
    assert attrs[ATTR_MOST_FREQUENT_VISITOR]["visit_count"] == 3

    assert ATTR_LONGEST_RESIDENT in attrs
    assert attrs[ATTR_LONGEST_RESIDENT]["mmsi"] == "AAA"

    assert ATTR_SPEED_RECORD in attrs
    assert attrs[ATTR_SPEED_RECORD]["speed_knots"] == 28.5

    assert ATTR_LARGEST_VESSEL in attrs
    assert attrs[ATTR_LARGEST_VESSEL]["length_m"] == 200.0

    assert ATTR_SMALLEST_VESSEL in attrs
    assert attrs[ATTR_SMALLEST_VESSEL]["length_m"] == 30.0

    assert ATTR_BUSIEST_HOUR in attrs
    assert attrs[ATTR_BUSIEST_HOUR] == 10

    assert ATTR_BUSIEST_DAY in attrs
    assert attrs[ATTR_BUSIEST_DAY] == 0

    assert ATTR_HOURLY_COUNTS in attrs
    assert len(attrs[ATTR_HOURLY_COUNTS]) == 24

    assert ATTR_DAILY_COUNTS in attrs
    assert len(attrs[ATTR_DAILY_COUNTS]) == 7

    assert ATTR_TOTAL_VESSELS_SEEN in attrs
    assert attrs[ATTR_TOTAL_VESSELS_SEEN] == 2
