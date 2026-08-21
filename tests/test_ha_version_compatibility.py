"""Tests for Home Assistant version compatibility checks."""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from custom_components.marinetraffic_tracker import MIN_HA_VERSION, _check_ha_version


class TestMinHaVersion:
    """Tests for the MIN_HA_VERSION constant."""

    def test_min_ha_version_is_string(self) -> None:
        """MIN_HA_VERSION should be a non-empty version string."""
        assert isinstance(MIN_HA_VERSION, str)
        assert MIN_HA_VERSION

    def test_min_ha_version_format(self) -> None:
        """MIN_HA_VERSION should follow YYYY.M.PATCH format."""
        parts = MIN_HA_VERSION.split(".")
        assert len(parts) >= 2, "Expected at least YYYY.M"
        assert all(p.isdigit() for p in parts), "All parts should be numeric"

    def test_min_ha_version_is_2023_or_later(self) -> None:
        """Minimum supported HA version should be 2023.1.0 or later."""
        year = int(MIN_HA_VERSION.split(".")[0])
        assert year >= 2023, f"Expected year >= 2023, got {year}"


class TestCheckHaVersion:
    """Tests for the _check_ha_version helper."""

    def test_no_warning_when_version_meets_minimum(self, caplog: pytest.LogCaptureFixture) -> None:
        """No warning should be emitted when the running HA version meets the minimum."""
        with (
            patch(
                "custom_components.marinetraffic_tracker.HA_VERSION",
                "2024.6.0",
            ),
            caplog.at_level(logging.WARNING, logger="custom_components.marinetraffic_tracker"),
        ):
            _check_ha_version()

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert not warnings, f"Unexpected warnings: {[r.message for r in warnings]}"

    def test_no_warning_on_minimum_version(self, caplog: pytest.LogCaptureFixture) -> None:
        """No warning should be emitted when running exactly on the minimum version."""
        with (
            patch(
                "custom_components.marinetraffic_tracker.HA_VERSION",
                MIN_HA_VERSION,
            ),
            caplog.at_level(logging.WARNING, logger="custom_components.marinetraffic_tracker"),
        ):
            _check_ha_version()

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert not warnings, f"Unexpected warnings: {[r.message for r in warnings]}"

    def test_warning_when_version_too_old(self, caplog: pytest.LogCaptureFixture) -> None:
        """A warning should be emitted when the running HA version is below the minimum."""
        with (
            patch(
                "custom_components.marinetraffic_tracker.HA_VERSION",
                "2022.12.0",
            ),
            caplog.at_level(logging.WARNING, logger="custom_components.marinetraffic_tracker"),
        ):
            _check_ha_version()

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warnings, "Expected a deprecation warning for old HA version"
        assert "2022.12.0" in warnings[0].getMessage()
        assert MIN_HA_VERSION in warnings[0].getMessage()

    def test_info_log_always_emitted(self, caplog: pytest.LogCaptureFixture) -> None:
        """An info log with the running version should always be emitted."""
        with (
            patch(
                "custom_components.marinetraffic_tracker.HA_VERSION",
                "2025.1.0",
            ),
            caplog.at_level(logging.INFO, logger="custom_components.marinetraffic_tracker"),
        ):
            _check_ha_version()

        info_logs = [r for r in caplog.records if r.levelno == logging.INFO]
        assert info_logs, "Expected at least one INFO log from _check_ha_version"
        assert any("2025.1.0" in r.getMessage() for r in info_logs)

    def test_no_exception_on_unexpected_version_format(self) -> None:
        """_check_ha_version should not raise for non-standard version strings."""
        with patch(
            "custom_components.marinetraffic_tracker.HA_VERSION",
            "dev",
        ):
            # Parsing "dev" will raise ValueError — ensure the helper does not propagate it.
            try:
                _check_ha_version()
            except (ValueError, IndexError):
                pytest.fail("_check_ha_version raised an exception for a non-standard version")
