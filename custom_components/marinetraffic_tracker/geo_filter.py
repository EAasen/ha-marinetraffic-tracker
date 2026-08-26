"""Geographic boundary filters for the MarineTraffic Tracker integration.

This module provides two filter strategies that can be applied at the
coordinator level to enforce vessel inclusion rules independently of the
upstream client implementation:

- :class:`RadiusFilter` — great-circle distance check using the Haversine
  formula.  Caches the centre coordinates and radius so they are not
  re-extracted from the config dict on every invocation.
- :class:`BoundingBoxFilter` — simple latitude/longitude rectangle check.
  Caches the four boundary coordinates for the same reason.

Both classes expose the same interface::

    filter_obj = RadiusFilter(lat, lon, radius_km)
    inside, outside = filter_obj.partition(vessels)

The ``partition`` method returns a tuple of *(inside, outside)* lists so
callers can log the excluded vessels without a second pass.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import VesselData

_LOGGER = logging.getLogger(__name__)

_EARTH_RADIUS_KM = 6371.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in kilometres between two lat/lon points.

    Uses the Haversine formula which is accurate to within 0.5% for distances
    up to several thousand kilometres — well within the precision needed for
    vessel tracking.

    Args:
        lat1: Latitude of the first point in decimal degrees.
        lon1: Longitude of the first point in decimal degrees.
        lat2: Latitude of the second point in decimal degrees.
        lon2: Longitude of the second point in decimal degrees.

    Returns:
        Distance in kilometres.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return _EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@dataclass(frozen=True)
class RadiusFilter:
    """Filter vessels that lie within a circular geographic area.

    The centre point and radius are cached on construction so repeated calls
    to :meth:`partition` do not re-parse the configuration dictionary.

    Args:
        latitude:  Centre latitude in decimal degrees.
        longitude: Centre longitude in decimal degrees.
        radius_km: Radius in kilometres.  Must be a positive number.
    """

    latitude: float
    longitude: float
    radius_km: float

    def __post_init__(self) -> None:
        if self.radius_km <= 0:
            raise ValueError(f"radius_km must be positive, got {self.radius_km}")

    def contains(self, vessel: VesselData) -> bool:
        """Return ``True`` when *vessel* is within the configured radius."""
        return (
            _haversine_km(
                self.latitude, self.longitude, vessel.latitude, vessel.longitude
            )
            <= self.radius_km
        )

    def partition(
        self, vessels: list[VesselData]
    ) -> tuple[list[VesselData], list[VesselData]]:
        """Split *vessels* into *(inside, outside)* lists.

        Vessels inside the radius are in the first list; those outside are in
        the second.  Both lists preserve the original order.  Filtered-out
        vessels are logged at DEBUG level so operators can diagnose boundary
        issues without enabling verbose tracing.

        The distance is only computed in full when the vessel falls outside the
        radius so that the exact figure can be included in the debug message;
        the membership test itself reuses the same calculation.

        Args:
            vessels: Flat list of vessel observations to partition.

        Returns:
            A 2-tuple ``(inside, outside)``.
        """
        inside: list[VesselData] = []
        outside: list[VesselData] = []
        for vessel in vessels:
            dist = _haversine_km(
                self.latitude, self.longitude, vessel.latitude, vessel.longitude
            )
            if dist <= self.radius_km:
                inside.append(vessel)
            else:
                outside.append(vessel)
                _LOGGER.debug(
                    "Vessel MMSI=%s (%s) excluded by radius filter: "
                    "%.2f km from centre (limit %.2f km)",
                    vessel.mmsi,
                    vessel.name,
                    dist,
                    self.radius_km,
                )
        return inside, outside


@dataclass(frozen=True)
class BoundingBoxFilter:
    """Filter vessels that lie within a rectangular geographic area.

    The boundary coordinates are cached on construction.  The filter uses
    simple inclusive comparisons (``south <= lat <= north`` and
    ``west <= lon <= east``).  This does **not** handle anti-meridian
    crossing (bounding boxes that wrap around ±180°); the config flow
    already rejects boxes where ``west >= east``.

    Args:
        north: Maximum (northern) latitude in decimal degrees (−90 to 90).
        east:  Maximum (eastern) longitude in decimal degrees (−180 to 180).
        south: Minimum (southern) latitude in decimal degrees (−90 to 90).
        west:  Minimum (western) longitude in decimal degrees (−180 to 180).
    """

    north: float
    east: float
    south: float
    west: float

    def __post_init__(self) -> None:
        if self.south >= self.north:
            raise ValueError(
                f"south ({self.south}) must be less than north ({self.north})"
            )
        if self.west >= self.east:
            raise ValueError(
                f"west ({self.west}) must be less than east ({self.east})"
            )

    def contains(self, vessel: VesselData) -> bool:
        """Return ``True`` when *vessel* lies within the bounding box."""
        return (
            self.south <= vessel.latitude <= self.north
            and self.west <= vessel.longitude <= self.east
        )

    def partition(
        self, vessels: list[VesselData]
    ) -> tuple[list[VesselData], list[VesselData]]:
        """Split *vessels* into *(inside, outside)* lists.

        Filtered-out vessels are logged at DEBUG level.

        Args:
            vessels: Flat list of vessel observations to partition.

        Returns:
            A 2-tuple ``(inside, outside)``.
        """
        inside: list[VesselData] = []
        outside: list[VesselData] = []
        for vessel in vessels:
            if self.contains(vessel):
                inside.append(vessel)
            else:
                outside.append(vessel)
                _LOGGER.debug(
                    "Vessel MMSI=%s (%s) excluded by bounding box filter "
                    "(box S=%.4f W=%.4f N=%.4f E=%.4f)",
                    vessel.mmsi,
                    vessel.name,
                    self.south,
                    self.west,
                    self.north,
                    self.east,
                )
        return inside, outside


def build_geo_filter(config: dict) -> RadiusFilter | BoundingBoxFilter | None:
    """Construct the appropriate geographic filter from a config dict.

    Reads ``tracking_mode``, ``latitude``/``longitude``/``radius_km`` (radius
    mode), or ``north``/``east``/``south``/``west`` (box mode) from *config*.

    Returns ``None`` when the configuration is incomplete or invalid so that
    callers can skip filtering rather than raising.

    Args:
        config: Merged ``entry.data | entry.options`` dictionary.

    Returns:
        A :class:`RadiusFilter`, :class:`BoundingBoxFilter`, or ``None``.
    """
    from .const import (  # noqa: PLC0415 — local import to avoid circular deps at module level
        CONF_EAST,
        CONF_LATITUDE,
        CONF_LONGITUDE,
        CONF_NORTH,
        CONF_RADIUS_KM,
        CONF_SOUTH,
        CONF_TRACKING_MODE,
        CONF_WEST,
        DEFAULT_RADIUS_KM,
        TRACKING_MODE_RADIUS,
    )

    mode = config.get(CONF_TRACKING_MODE, TRACKING_MODE_RADIUS)

    try:
        if mode == TRACKING_MODE_RADIUS:
            return RadiusFilter(
                latitude=float(config[CONF_LATITUDE]),
                longitude=float(config[CONF_LONGITUDE]),
                radius_km=float(config.get(CONF_RADIUS_KM, DEFAULT_RADIUS_KM)),
            )
        return BoundingBoxFilter(
            north=float(config[CONF_NORTH]),
            east=float(config[CONF_EAST]),
            south=float(config[CONF_SOUTH]),
            west=float(config[CONF_WEST]),
        )
    except (KeyError, ValueError, TypeError) as exc:
        _LOGGER.warning("Could not build geographic filter from config: %s", exc)
        return None
