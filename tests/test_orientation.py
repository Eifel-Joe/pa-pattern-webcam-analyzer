"""Tests für die Orientierungs-Bestimmung."""
from pathlib import Path

import pytest

from pa_analyzer.gcode_parser import parse
from pa_analyzer.image_loader import load_image
from pa_analyzer.orientation import pick_orientation
from pa_analyzer.pattern_locator import filament_mask, locate_quad

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def model():
    return parse((FIXTURES / "pa_pattern.gcode").read_text(
        encoding="utf-8", errors="replace"))


@pytest.mark.parametrize("name", ["IMG_3843.HEIC", "pa_snap.jpg",
                                  "pa_snap2.jpg"])
def test_pick_orientation_liefert_gueltige_rotation(name, model):
    img = load_image(FIXTURES / name)
    mask = filament_mask(img)
    quad = locate_quad(mask)
    rot, ratio = pick_orientation(mask, quad, model)
    assert rot in (0, 1, 2, 3)
    # Korrekte Orientierung hat ein deutliches Balken/Chevron-
    # Dichte-Verhältnis (Spike: >= 1.5 korrekt, <= 0.9 falsch).
    assert ratio > 1.3
