"""Tests für die Zwei-Box-Apex-Messung."""
from pathlib import Path

import numpy as np
import pytest

from pa_analyzer.apex_analyzer import box_fill, measure_groups
from pa_analyzer.gcode_parser import parse
from pa_analyzer.image_loader import load_image
from pa_analyzer.orientation import pick_orientation
from pa_analyzer.pattern_locator import filament_mask, locate_quad
from pa_analyzer.rectifier import rectify

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def model():
    return parse((FIXTURES / "pa_pattern.gcode").read_text(
        encoding="utf-8", errors="replace"))


def test_box_fill_volle_maske():
    mask = np.full((100, 100), 255, np.uint8)
    f = box_fill(mask, np.array([50.0, 50.0]),
                 np.array([1.0, 0.0]), np.array([0.0, 1.0]), 10.0)
    assert f == pytest.approx(1.0)


def test_box_fill_leere_maske():
    mask = np.zeros((100, 100), np.uint8)
    f = box_fill(mask, np.array([50.0, 50.0]),
                 np.array([1.0, 0.0]), np.array([0.0, 1.0]), 10.0)
    assert f == pytest.approx(0.0)


def test_box_fill_halb_gefuellt():
    # Linke Hälfte gefüllt; Box mittig -> ~50 %.
    mask = np.zeros((100, 100), np.uint8)
    mask[:, :50] = 255
    f = box_fill(mask, np.array([50.0, 50.0]),
                 np.array([1.0, 0.0]), np.array([0.0, 1.0]), 10.0)
    assert 0.4 < f < 0.6


def test_measure_groups_liefert_eintrag_je_gruppe(model):
    img = load_image(FIXTURES / "IMG_3843.HEIC")
    mask = filament_mask(img)
    quad = locate_quad(mask)
    rot, _ = pick_orientation(mask, quad, model)
    warped = rectify(mask, quad, rot, model)
    measurements = measure_groups(warped, model)
    assert len(measurements) == 21
    for pa, fill_in, fill_out in measurements:
        assert 0.0 <= fill_in <= 1.0
        assert 0.0 <= fill_out <= 1.0
