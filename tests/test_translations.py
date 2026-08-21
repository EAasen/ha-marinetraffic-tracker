"""Translation file regression tests."""

from __future__ import annotations

import json
from pathlib import Path


def test_english_translation_matches_strings_template() -> None:
    """The shipped English translation should stay aligned with the current flow text."""
    integration_dir = (
        Path(__file__).resolve().parents[1] / "custom_components" / "marinetraffic_tracker"
    )

    with (integration_dir / "strings.json").open(encoding="utf-8") as strings_file:
        strings = json.load(strings_file)

    with (integration_dir / "translations" / "en.json").open(encoding="utf-8") as en_file:
        english = json.load(en_file)

    assert english == strings
