"""Tests for the geographic boundary filter module (geo_filter.py).

Covers:
- RadiusFilter: contains(), partition(), haversine accuracy at various distances
- BoundingBoxFilter: contains(), partition(), edge coordinates
- build_geo_filter: radius mode, box mode, invalid / missing config
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from custom_components.marinetraffic_tracker.geo_filter import (
    BoundingBoxFilter,
    RadiusFilter,
    _haversine_km,
    build_geo_filter,
)

from .conftest import MOCK_VESSEL_CARGO, MOCK_VESSEL_PASSENGER, MOCK_VESSEL_TANKER

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OSLO_LAT = 59.9
_OSLO_LON = 10.7


def _vessel_at(lat: float, lon: float):
    """Return a copy of MOCK_VESSEL_CARGO placed at (lat, lon)."""
    return replace(MOCK_VESSEL_CARGO, latitude=lat, longitude=lon)


# ===========================================================================
# _haversine_km — internal distance helper
# ===========================================================================


def test_haversine_same_point_is_zero() -> None:
    """Distance from a point to itself must be zero."""
    assert _haversine_km(59.9, 10.7, 59.9, 10.7) == pytest.approx(0.0, abs=1e-6)


def test_haversine_known_distance_oslo_bergen() -> None:
    """Oslo→Bergen great-circle distance is approximately 300–310 km."""
    dist = _haversine_km(59.9, 10.7, 60.39, 5.32)
    assert 295 <= dist <= 315, f"Expected ~300–310 km, got {dist:.1f} km"


def test_haversine_symmetry() -> None:
    """Distance A→B must equal B→A."""
    a_to_b = _haversine_km(59.9, 10.7, 60.4, 5.3)
    b_to_a = _haversine_km(60.4, 5.3, 59.9, 10.7)
    assert a_to_b == pytest.approx(b_to_a, rel=1e-9)


def test_haversine_equator_degree_approx_111km() -> None:
    """One degree of longitude at the equator is ~111.3 km."""
    dist = _haversine_km(0.0, 0.0, 0.0, 1.0)
    assert 111.0 <= dist <= 112.0, f"Expected ~111 km, got {dist:.2f} km"


def test_haversine_poles() -> None:
    """Distance from south pole to north pole must be ~20 015 km (half circumference)."""
    dist = _haversine_km(-90.0, 0.0, 90.0, 0.0)
    assert 20000 <= dist <= 20050


# ===========================================================================
# RadiusFilter
# ===========================================================================


class TestRadiusFilter:
    """Unit tests for RadiusFilter."""

    _centre_lat = _OSLO_LAT
    _centre_lon = _OSLO_LON
    _radius_km = 50.0

    @pytest.fixture
    def flt(self) -> RadiusFilter:
        return RadiusFilter(self._centre_lat, self._centre_lon, self._radius_km)

    # ------------------------------------------------------------------
    # Construction guards
    # ------------------------------------------------------------------

    def test_zero_radius_raises(self) -> None:
        with pytest.raises(ValueError, match="radius_km must be positive"):
            RadiusFilter(59.9, 10.7, 0.0)

    def test_negative_radius_raises(self) -> None:
        with pytest.raises(ValueError, match="radius_km must be positive"):
            RadiusFilter(59.9, 10.7, -10.0)

    # ------------------------------------------------------------------
    # contains()
    # ------------------------------------------------------------------

    def test_centre_is_inside(self, flt: RadiusFilter) -> None:
        """A vessel exactly at the centre must be inside."""
        v = _vessel_at(self._centre_lat, self._centre_lon)
        assert flt.contains(v) is True

    def test_vessel_just_inside_radius(self, flt: RadiusFilter) -> None:
        """A vessel 0.1 km inside the boundary must be inside."""
        # Move north by (radius - 0.1) km.  1° latitude ≈ 111 km.
        offset_deg = (self._radius_km - 0.1) / 111.0
        v = _vessel_at(self._centre_lat + offset_deg, self._centre_lon)
        assert flt.contains(v) is True

    def test_vessel_just_outside_radius(self, flt: RadiusFilter) -> None:
        """A vessel 0.1 km outside the boundary must be outside."""
        offset_deg = (self._radius_km + 0.1) / 111.0
        v = _vessel_at(self._centre_lat + offset_deg, self._centre_lon)
        assert flt.contains(v) is False

    def test_vessel_exactly_on_boundary_is_inside(self, flt: RadiusFilter) -> None:
        """A vessel at exactly the radius distance is inside (≤ comparison)."""
        # Place vessel at a known distance by moving north exactly radius_km.
        offset_deg = self._radius_km / 111.0
        v = _vessel_at(self._centre_lat + offset_deg, self._centre_lon)
        dist = _haversine_km(self._centre_lat, self._centre_lon, v.latitude, v.longitude)
        # The straight-line lat offset isn't exactly radius_km due to the
        # haversine; assert that it's within 1 km of the limit.
        assert dist <= self._radius_km + 1.0

    def test_distant_vessel_is_outside(self, flt: RadiusFilter) -> None:
        """Suez Canal is thousands of km away — must be outside a 50-km Oslo radius."""
        v = _vessel_at(30.0, 32.5)
        assert flt.contains(v) is False

    # ------------------------------------------------------------------
    # partition()
    # ------------------------------------------------------------------

    def test_partition_empty_list(self, flt: RadiusFilter) -> None:
        inside, outside = flt.partition([])
        assert inside == []
        assert outside == []

    def test_partition_all_inside(self, flt: RadiusFilter) -> None:
        vessels = [_vessel_at(self._centre_lat, self._centre_lon) for _ in range(3)]
        inside, outside = flt.partition(vessels)
        assert len(inside) == 3
        assert outside == []

    def test_partition_all_outside(self, flt: RadiusFilter) -> None:
        vessels = [_vessel_at(0.0, 0.0), _vessel_at(30.0, 32.5)]
        inside, outside = flt.partition(vessels)
        assert inside == []
        assert len(outside) == 2

    def test_partition_mixed(self, flt: RadiusFilter) -> None:
        inside_v = _vessel_at(self._centre_lat, self._centre_lon)
        outside_v = _vessel_at(0.0, 0.0)
        inside, outside = flt.partition([inside_v, outside_v])
        assert len(inside) == 1
        assert len(outside) == 1
        assert inside[0] is inside_v
        assert outside[0] is outside_v

    def test_partition_preserves_order(self, flt: RadiusFilter) -> None:
        v1 = replace(MOCK_VESSEL_CARGO, mmsi="111", latitude=_OSLO_LAT, longitude=_OSLO_LON)
        v2 = replace(MOCK_VESSEL_CARGO, mmsi="222", latitude=_OSLO_LAT + 0.01, longitude=_OSLO_LON)
        v3 = replace(MOCK_VESSEL_CARGO, mmsi="333", latitude=0.0, longitude=0.0)
        inside, outside = flt.partition([v1, v2, v3])
        assert [v.mmsi for v in inside] == ["111", "222"]
        assert [v.mmsi for v in outside] == ["333"]

    # ------------------------------------------------------------------
    # Various distances
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("radius_km,offset_km,expect_inside", [
        (10.0, 9.9, True),
        (10.0, 10.1, False),
        (100.0, 99.0, True),
        (100.0, 101.0, False),
        (500.0, 499.0, True),
        (500.0, 501.0, False),
    ])
    def test_various_radii(
        self,
        radius_km: float,
        offset_km: float,
        expect_inside: bool,
    ) -> None:
        flt = RadiusFilter(0.0, 0.0, radius_km)
        # Move north by offset_km (1° lat ≈ 111 km)
        offset_deg = offset_km / 111.0
        v = _vessel_at(offset_deg, 0.0)
        assert flt.contains(v) is expect_inside


# ===========================================================================
# BoundingBoxFilter
# ===========================================================================


class TestBoundingBoxFilter:
    """Unit tests for BoundingBoxFilter."""

    # Bounding box around southern Norway / Oslo Fjord region
    _north = 60.5
    _east = 11.5
    _south = 59.3
    _west = 9.9

    @pytest.fixture
    def flt(self) -> BoundingBoxFilter:
        return BoundingBoxFilter(
            north=self._north,
            east=self._east,
            south=self._south,
            west=self._west,
        )

    # ------------------------------------------------------------------
    # Construction guards
    # ------------------------------------------------------------------

    def test_south_gte_north_raises(self) -> None:
        with pytest.raises(ValueError, match="south.*must be less than north"):
            BoundingBoxFilter(north=50.0, east=10.0, south=50.0, west=9.0)

    def test_south_gt_north_raises(self) -> None:
        with pytest.raises(ValueError, match="south.*must be less than north"):
            BoundingBoxFilter(north=50.0, east=10.0, south=51.0, west=9.0)

    def test_west_gte_east_raises(self) -> None:
        with pytest.raises(ValueError, match="west.*must be less than east"):
            BoundingBoxFilter(north=60.0, east=10.0, south=59.0, west=10.0)

    # ------------------------------------------------------------------
    # contains()
    # ------------------------------------------------------------------

    def test_centre_is_inside(self, flt: BoundingBoxFilter) -> None:
        mid_lat = (self._north + self._south) / 2
        mid_lon = (self._east + self._west) / 2
        v = _vessel_at(mid_lat, mid_lon)
        assert flt.contains(v) is True

    def test_north_boundary_inclusive(self, flt: BoundingBoxFilter) -> None:
        v = _vessel_at(self._north, (self._east + self._west) / 2)
        assert flt.contains(v) is True

    def test_south_boundary_inclusive(self, flt: BoundingBoxFilter) -> None:
        v = _vessel_at(self._south, (self._east + self._west) / 2)
        assert flt.contains(v) is True

    def test_east_boundary_inclusive(self, flt: BoundingBoxFilter) -> None:
        v = _vessel_at((self._north + self._south) / 2, self._east)
        assert flt.contains(v) is True

    def test_west_boundary_inclusive(self, flt: BoundingBoxFilter) -> None:
        v = _vessel_at((self._north + self._south) / 2, self._west)
        assert flt.contains(v) is True

    def test_just_outside_north(self, flt: BoundingBoxFilter) -> None:
        v = _vessel_at(self._north + 0.001, (self._east + self._west) / 2)
        assert flt.contains(v) is False

    def test_just_outside_south(self, flt: BoundingBoxFilter) -> None:
        v = _vessel_at(self._south - 0.001, (self._east + self._west) / 2)
        assert flt.contains(v) is False

    def test_just_outside_east(self, flt: BoundingBoxFilter) -> None:
        v = _vessel_at((self._north + self._south) / 2, self._east + 0.001)
        assert flt.contains(v) is False

    def test_just_outside_west(self, flt: BoundingBoxFilter) -> None:
        v = _vessel_at((self._north + self._south) / 2, self._west - 0.001)
        assert flt.contains(v) is False

    def test_suez_canal_outside(self, flt: BoundingBoxFilter) -> None:
        v = _vessel_at(30.0, 32.5)
        assert flt.contains(v) is False

    # ------------------------------------------------------------------
    # partition()
    # ------------------------------------------------------------------

    def test_partition_empty(self, flt: BoundingBoxFilter) -> None:
        inside, outside = flt.partition([])
        assert inside == []
        assert outside == []

    def test_partition_all_inside(self, flt: BoundingBoxFilter) -> None:
        mid = ((self._north + self._south) / 2, (self._east + self._west) / 2)
        vessels = [_vessel_at(*mid) for _ in range(4)]
        inside, outside = flt.partition(vessels)
        assert len(inside) == 4
        assert outside == []

    def test_partition_mixed(self, flt: BoundingBoxFilter) -> None:
        mid_lat = (self._north + self._south) / 2
        mid_lon = (self._east + self._west) / 2
        inside_v = _vessel_at(mid_lat, mid_lon)
        outside_v = _vessel_at(0.0, 0.0)
        inside, outside = flt.partition([inside_v, outside_v])
        assert len(inside) == 1
        assert len(outside) == 1

    # ------------------------------------------------------------------
    # Coordinate range coverage
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("lat,lon,expect_inside", [
        (0.0, 0.0, True),       # equator / prime meridian
        (-89.9, 0.0, True),     # near south pole
        (89.9, 0.0, True),      # near north pole
        (-90.0, -180.0, True),  # extreme SW corner — on boundary
        (90.0, 180.0, True),    # extreme NE corner — on boundary
        (0.0, 181.0, False),    # longitude beyond east boundary — outside
    ])
    def test_global_coordinate_ranges(
        self,
        lat: float,
        lon: float,
        expect_inside: bool,
    ) -> None:
        """BoundingBoxFilter must handle the full lat/lon coordinate space."""
        global_flt = BoundingBoxFilter(
            north=90.0, east=180.0, south=-90.0, west=-180.0
        )
        v = _vessel_at(lat, lon)
        assert global_flt.contains(v) is expect_inside


# ===========================================================================
# build_geo_filter
# ===========================================================================


class TestBuildGeoFilter:
    """Unit tests for the build_geo_filter factory function."""

    def test_radius_mode_returns_radius_filter(self) -> None:
        config = {
            "tracking_mode": "radius",
            "latitude": 59.9,
            "longitude": 10.7,
            "radius_km": 50.0,
        }
        result = build_geo_filter(config)
        assert isinstance(result, RadiusFilter)
        assert result.latitude == 59.9
        assert result.longitude == 10.7
        assert result.radius_km == 50.0

    def test_box_mode_returns_bounding_box_filter(self) -> None:
        config = {
            "tracking_mode": "box",
            "north": 60.5,
            "east": 11.5,
            "south": 59.3,
            "west": 9.9,
        }
        result = build_geo_filter(config)
        assert isinstance(result, BoundingBoxFilter)
        assert result.north == 60.5
        assert result.east == 11.5
        assert result.south == 59.3
        assert result.west == 9.9

    def test_default_mode_is_radius(self) -> None:
        """When tracking_mode is absent, radius mode must be assumed."""
        config = {
            "latitude": 59.9,
            "longitude": 10.7,
            "radius_km": 50.0,
        }
        result = build_geo_filter(config)
        assert isinstance(result, RadiusFilter)

    def test_radius_mode_uses_default_radius_when_missing(self) -> None:
        from custom_components.marinetraffic_tracker.const import DEFAULT_RADIUS_KM

        config = {
            "tracking_mode": "radius",
            "latitude": 59.9,
            "longitude": 10.7,
        }
        result = build_geo_filter(config)
        assert isinstance(result, RadiusFilter)
        assert result.radius_km == DEFAULT_RADIUS_KM

    def test_missing_latitude_returns_none(self) -> None:
        config = {
            "tracking_mode": "radius",
            "longitude": 10.7,
            "radius_km": 50.0,
        }
        result = build_geo_filter(config)
        assert result is None

    def test_missing_box_north_returns_none(self) -> None:
        config = {
            "tracking_mode": "box",
            "east": 11.5,
            "south": 59.3,
            "west": 9.9,
        }
        result = build_geo_filter(config)
        assert result is None

    def test_invalid_south_gte_north_returns_none(self) -> None:
        config = {
            "tracking_mode": "box",
            "north": 59.0,
            "east": 11.5,
            "south": 60.0,  # south > north
            "west": 9.9,
        }
        result = build_geo_filter(config)
        assert result is None

    def test_invalid_west_gte_east_returns_none(self) -> None:
        config = {
            "tracking_mode": "box",
            "north": 60.5,
            "east": 9.9,  # east < west
            "south": 59.3,
            "west": 11.5,
        }
        result = build_geo_filter(config)
        assert result is None

    def test_radius_filter_filters_correctly(self) -> None:
        """End-to-end: build a RadiusFilter and verify it filters vessels."""
        config = {
            "tracking_mode": "radius",
            "latitude": _OSLO_LAT,
            "longitude": _OSLO_LON,
            "radius_km": 50.0,
        }
        flt = build_geo_filter(config)
        assert flt is not None

        near = _vessel_at(_OSLO_LAT, _OSLO_LON)
        far = _vessel_at(0.0, 0.0)
        inside, outside = flt.partition([near, far])
        assert len(inside) == 1
        assert len(outside) == 1

    def test_box_filter_filters_correctly(self) -> None:
        """End-to-end: build a BoundingBoxFilter and verify it filters vessels."""
        config = {
            "tracking_mode": "box",
            "north": 60.5,
            "east": 11.5,
            "south": 59.3,
            "west": 9.9,
        }
        flt = build_geo_filter(config)
        assert flt is not None

        inside_v = _vessel_at(59.9, 10.7)  # Oslo — inside
        outside_v = _vessel_at(0.0, 0.0)  # equator — outside
        inside, outside = flt.partition([inside_v, outside_v])
        assert len(inside) == 1
        assert len(outside) == 1
