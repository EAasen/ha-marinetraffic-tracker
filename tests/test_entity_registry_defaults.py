"""Tests for entity_registry_enabled_default on per-vessel entities.

Verifies that:
- Per-vessel sensor and device_tracker entities are disabled by default in
  the entity registry (to prevent entity explosion in high-traffic areas).
- The global count sensor remains enabled by default.

Home Assistant's ``CachedProperties`` metaclass converts a class-level
``_attr_entity_registry_enabled_default = <value>`` assignment into a
property descriptor backed by a ``__attr_entity_registry_enabled_default``
class attribute.  We therefore inspect ``cls.__dict__`` to check the stored
value directly.
"""
from __future__ import annotations

from custom_components.marinetraffic_tracker.device_tracker import (
    MarineTrafficVesselTracker,
)
from custom_components.marinetraffic_tracker.sensor import (
    MarineTrafficCountSensor,
    MarineTrafficVesselSensor,
)

# The backing attribute name created by HA's CachedProperties metaclass when
# _attr_entity_registry_enabled_default is assigned at class level.
_BACKING_ATTR = "__attr_entity_registry_enabled_default"


def test_vessel_sensor_disabled_by_default() -> None:
    """Per-vessel sensor must be disabled by default in the entity registry."""
    assert MarineTrafficVesselSensor.__dict__.get(_BACKING_ATTR) is False


def test_vessel_tracker_disabled_by_default() -> None:
    """Per-vessel device_tracker must be disabled by default in the entity registry."""
    assert MarineTrafficVesselTracker.__dict__.get(_BACKING_ATTR) is False


def test_count_sensor_enabled_by_default() -> None:
    """Global count sensor must remain enabled by default in the entity registry.

    The count sensor must NOT have a False override — it should be absent from
    its own ``__dict__`` (HA's Entity class defaults the value to True).
    """
    assert MarineTrafficCountSensor.__dict__.get(_BACKING_ATTR, True) is True
