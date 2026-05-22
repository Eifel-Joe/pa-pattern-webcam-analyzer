"""Gemeinsame pytest-Fixtures."""
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def pa_pattern_gcode() -> str:
    """Roher Text des Beispiel-GCodes (OrcaSlicer-PA-Pattern, 4 Layer)."""
    return (FIXTURES_DIR / "pa_pattern.gcode").read_text(
        encoding="utf-8", errors="replace"
    )
