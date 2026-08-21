"""Manifest validation tests for the marinetraffic_tracker integration."""

from __future__ import annotations

import json
import re
from pathlib import Path

MANIFEST_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "marinetraffic_tracker"
    / "manifest.json"
)

REQUIRED_FIELDS = {
    "domain",
    "name",
    "codeowners",
    "config_flow",
    "documentation",
    "homeassistant",
    "iot_class",
    "issue_tracker",
    "version",
}

VALID_IOT_CLASSES = {
    "assumed_state",
    "cloud_polling",
    "cloud_push",
    "local_polling",
    "local_push",
    "calculated",
}

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
HA_VERSION_RE = re.compile(r"^\d{4}\.\d+\.\d+$")


def load_manifest() -> dict:
    with MANIFEST_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def test_manifest_is_valid_json() -> None:
    """manifest.json must be parseable as JSON."""
    load_manifest()


def test_manifest_required_fields_present() -> None:
    """All required Home Assistant manifest fields must be present."""
    manifest = load_manifest()
    missing = REQUIRED_FIELDS - manifest.keys()
    assert not missing, f"Missing required fields: {missing}"


def test_manifest_version_is_semver() -> None:
    """version must follow semantic versioning (MAJOR.MINOR.PATCH)."""
    manifest = load_manifest()
    version = manifest.get("version", "")
    assert SEMVER_RE.match(version), f"version '{version}' is not valid semver (X.Y.Z)"


def test_manifest_domain() -> None:
    """domain must be a non-empty string."""
    manifest = load_manifest()
    assert isinstance(manifest.get("domain"), str)
    assert manifest["domain"]


def test_manifest_iot_class_is_valid() -> None:
    """iot_class must be one of the recognised Home Assistant values."""
    manifest = load_manifest()
    iot_class = manifest.get("iot_class", "")
    assert iot_class in VALID_IOT_CLASSES, (
        f"iot_class '{iot_class}' is not a valid HA iot_class. "
        f"Expected one of: {sorted(VALID_IOT_CLASSES)}"
    )


def test_manifest_codeowners_is_list() -> None:
    """codeowners must be a list of GitHub usernames."""
    manifest = load_manifest()
    codeowners = manifest.get("codeowners", None)
    assert isinstance(codeowners, list), "codeowners must be a list"
    for owner in codeowners:
        assert isinstance(owner, str) and owner.startswith("@"), (
            f"codeowners entry '{owner}' must be a string starting with '@'"
        )


def test_manifest_documentation_url() -> None:
    """documentation must be a non-empty URL string."""
    manifest = load_manifest()
    doc = manifest.get("documentation", "")
    assert isinstance(doc, str) and doc.startswith("http"), (
        f"documentation '{doc}' must be a URL"
    )


def test_manifest_issue_tracker_url() -> None:
    """issue_tracker must be a non-empty URL string."""
    manifest = load_manifest()
    tracker = manifest.get("issue_tracker", "")
    assert isinstance(tracker, str) and tracker.startswith("http"), (
        f"issue_tracker '{tracker}' must be a URL"
    )


def test_manifest_homeassistant_version_format() -> None:
    """homeassistant minimum version must be in YEAR.MONTH.PATCH format."""
    manifest = load_manifest()
    ha_version = manifest.get("homeassistant", "")
    assert HA_VERSION_RE.match(ha_version), (
        f"homeassistant '{ha_version}' must follow YEAR.MONTH.PATCH format (e.g. 2024.1.0)"
    )


def test_manifest_config_flow_is_bool() -> None:
    """config_flow must be a boolean."""
    manifest = load_manifest()
    assert isinstance(manifest.get("config_flow"), bool)
