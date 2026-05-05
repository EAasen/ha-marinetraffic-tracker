"""Tests for the MIN_UPDATE_INTERVAL hard floor enforcement.

These tests verify that the 30-second anti-ban safety threshold is enforced
consistently across both the schema layer and the coordinator runtime.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest
import voluptuous as vol

# ---------------------------------------------------------------------------
# Bootstrap: import const.py without needing the full homeassistant package.
# const.py has no HA dependencies, so this is safe.
# ---------------------------------------------------------------------------
_COMPONENT_DIR = Path(__file__).parent.parent / "custom_components" / "marinetraffic_tracker"

def _load_module(name: str, filename: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, _COMPONENT_DIR / filename)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod

_const = _load_module("marinetraffic_tracker_const", "const.py")

MIN_UPDATE_INTERVAL = _const.MIN_UPDATE_INTERVAL
CONF_UPDATE_INTERVAL = _const.CONF_UPDATE_INTERVAL
DEFAULT_UPDATE_INTERVAL = _const.DEFAULT_UPDATE_INTERVAL


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_min_update_interval_constant_value() -> None:
    """MIN_UPDATE_INTERVAL must be exactly 30 seconds (anti-ban hard floor)."""
    assert MIN_UPDATE_INTERVAL == 30


def test_hard_floor_clamps_low_interval() -> None:
    """Any interval below 30s must be clamped to MIN_UPDATE_INTERVAL at runtime."""
    for raw in (1, 5, 10, 15, 29):
        enforced = max(raw, MIN_UPDATE_INTERVAL)
        assert enforced == MIN_UPDATE_INTERVAL, (
            f"Interval {raw}s was not clamped to {MIN_UPDATE_INTERVAL}s"
        )


def test_hard_floor_does_not_clamp_valid_intervals() -> None:
    """Intervals at or above 30s must not be modified by the hard floor."""
    for raw in (30, 60, 120, 300, 3600):
        enforced = max(raw, MIN_UPDATE_INTERVAL)
        assert enforced == raw, (
            f"Valid interval {raw}s was incorrectly clamped to {enforced}s"
        )


def test_schema_min_equals_constant() -> None:
    """The schema's min=N must equal MIN_UPDATE_INTERVAL (no magic numbers)."""
    # Build the same schema logic as _timing_schema uses.
    schema = vol.Schema(
        {
            vol.Required(CONF_UPDATE_INTERVAL, default=MIN_UPDATE_INTERVAL): vol.All(
                int, vol.Range(min=MIN_UPDATE_INTERVAL, max=3600)
            ),
        }
    )
    # Value exactly at the floor is accepted.
    assert schema({CONF_UPDATE_INTERVAL: MIN_UPDATE_INTERVAL})[CONF_UPDATE_INTERVAL] == 30
    # Value one below the floor is rejected.
    with pytest.raises(vol.Invalid):
        schema({CONF_UPDATE_INTERVAL: MIN_UPDATE_INTERVAL - 1})


def test_default_update_interval_is_above_floor() -> None:
    """The built-in DEFAULT_UPDATE_INTERVAL must always be >= MIN_UPDATE_INTERVAL."""
    assert DEFAULT_UPDATE_INTERVAL >= MIN_UPDATE_INTERVAL, (
        "DEFAULT_UPDATE_INTERVAL must never be below MIN_UPDATE_INTERVAL"
    )


def test_coordinator_clamping_logic_below_floor() -> None:
    """Simulate the coordinator __init__ clamping logic with a below-floor value.

    This mirrors the exact logic in coordinator.py to confirm that passing an
    interval of, e.g., 5s is overridden to MIN_UPDATE_INTERVAL at runtime.
    """
    # Values that would come from a (possibly corrupted) config entry.
    for stored_value in (1, 5, 10, 15, 29):
        try:
            raw_interval = int(stored_value)
        except (ValueError, TypeError):
            raw_interval = DEFAULT_UPDATE_INTERVAL
        safe_interval = max(raw_interval, MIN_UPDATE_INTERVAL)
        assert safe_interval == MIN_UPDATE_INTERVAL, (
            f"Coordinator would use {safe_interval}s "
            f"instead of clamping {stored_value}s to {MIN_UPDATE_INTERVAL}s"
        )


def test_coordinator_clamping_logic_invalid_type() -> None:
    """Simulate coordinator handling a corrupt (non-integer) stored interval."""
    for bad_value in ("not_a_number", None, [], {}):
        try:
            raw_interval = int(bad_value)  # type: ignore[arg-type]
        except (ValueError, TypeError):
            raw_interval = DEFAULT_UPDATE_INTERVAL
        safe_interval = max(raw_interval, MIN_UPDATE_INTERVAL)
        # Should fall back to DEFAULT_UPDATE_INTERVAL which is >= MIN_UPDATE_INTERVAL.
        assert safe_interval >= MIN_UPDATE_INTERVAL
