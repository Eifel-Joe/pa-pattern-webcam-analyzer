"""Tests für die perspektivische Entzerrung."""
from pathlib import Path

import numpy as np
import pytest

from pa_analyzer.gcode_parser import parse
from pa_analyzer.image_loader import load_image
from pa_analyzer.orientation import pick_orientation, warp_size
from pa_analyzer.pattern_locator import filament_mask, locate_quad
from pa_analyzer.rectifier import bett_to_warp, rectify

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def model():
    return parse((FIXTURES / "pa_pattern.gcode").read_text(
        encoding="utf-8", errors="replace"))


def test_bett_to_warp_eckpunkte(model):
    # Untere-linke content_bounds-Ecke -> (0, Höhe); obere-rechte -> (Breite, 0).
    lo, hi = model.content_bounds
    w, h = warp_size(model)
    p_ll = bett_to_warp(lo.x, lo.y, model)
    p_or = bett_to_warp(hi.x, hi.y, model)
    assert p_ll == pytest.approx([0.0, h], abs=1.0)
    assert p_or == pytest.approx([w, 0.0], abs=1.0)


def test_rectify_liefert_warp_groesse(model):
    img = load_image(FIXTURES / "IMG_3843.HEIC")
    mask = filament_mask(img)
    quad = locate_quad(mask)
    rot, _ = pick_orientation(mask, quad, model)
    warped = rectify(mask, quad, rot, model)
    w, h = warp_size(model)
    assert warped.shape == (h, w)
    assert warped.dtype == np.uint8


def test_rectify_fuellt_plausibel(model):
    # Nach der Entzerrung füllt das Pattern einen erheblichen Teil
    # des normierten Bildes (Maske enthält Filament-Pixel).
    img = load_image(FIXTURES / "IMG_3843.HEIC")
    mask = filament_mask(img)
    quad = locate_quad(mask)
    rot, _ = pick_orientation(mask, quad, model)
    warped = rectify(mask, quad, rot, model)
    assert 0.2 < (warped > 0).mean() < 0.95
