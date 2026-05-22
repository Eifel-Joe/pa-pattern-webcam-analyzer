"""Tests für die Pattern-Lokalisierung."""
from pathlib import Path

import numpy as np
import pytest

from pa_analyzer.image_loader import load_image
from pa_analyzer.pattern_locator import filament_mask, locate_quad

FIXTURES = Path(__file__).parent / "fixtures"


def test_filament_mask_ist_binaer():
    img = load_image(FIXTURES / "IMG_3843.HEIC")
    mask = filament_mask(img)
    assert mask.shape == img.shape[:2]
    assert mask.dtype == np.uint8
    assert set(np.unique(mask)).issubset({0, 255})


def test_filament_mask_erfasst_plausiblen_anteil():
    # Das Pattern füllt einen erkennbaren, aber nicht dominanten
    # Bildanteil — grobe Plausibilität gegen Totalausfall.
    img = load_image(FIXTURES / "IMG_3843.HEIC")
    anteil = filament_mask(img).mean() / 255
    assert 0.02 < anteil < 0.6


def test_locate_quad_liefert_vier_ecken():
    img = load_image(FIXTURES / "IMG_3843.HEIC")
    quad = locate_quad(filament_mask(img))
    assert quad.shape == (4, 2)


def test_locate_quad_umschliesst_patternregion_heic():
    # Aus dem Vision-Spike: die Druck-Region im Handy-Foto ist ein
    # rotiertes Rechteck mit Seitenverhältnis ~1.66 (Box+Balken
    # 98.5x59.4 mm). Die Quad-Fläche ist ein erheblicher Bildanteil.
    img = load_image(FIXTURES / "IMG_3843.HEIC")
    quad = locate_quad(filament_mask(img))
    seiten = [
        np.linalg.norm(quad[i] - quad[(i + 1) % 4]) for i in range(4)
    ]
    lang, kurz = max(seiten), min(seiten)
    assert 1.3 < lang / kurz < 2.1
    flaeche = lang * kurz
    bild = img.shape[0] * img.shape[1]
    assert 0.2 < flaeche / bild < 0.85
