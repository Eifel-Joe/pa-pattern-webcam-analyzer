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


def test_locate_quad_wirft_bei_leerer_maske():
    # Eine komplett leere Maske (kein Filament erkannt) darf nicht mit
    # einer kryptischen Exception abstürzen, sondern klar melden.
    leer = np.zeros((200, 200), np.uint8)
    with pytest.raises(ValueError):
        locate_quad(leer)


# ============================================================================
# Robustheits-Tests für locate_quad (Pipeline-Diagnose 2026-05-24):
# Bei v2-Pattern (dünne Chevron-Linien) trennt sich Top-Bar in der Maske
# häufig von den Chevrons in eigene Connected-Components. Die alte
# "nur größte Component"-Logik nahm dann nur den Top-Bar als Quad —
# Chevrons komplett außerhalb → Pipeline-Output Müll. Fix: alle
# Components > MIN_AREA kombinieren.
# ============================================================================

def test_locate_quad_umfasst_alle_pattern_komponenten():
    """Wenn Maske mehrere getrennte Filament-Regionen enthält
    (Top-Bar getrennt von Chevrons-Region), muss der Quad ALLE
    erfassen, nicht nur die größte."""
    mask = np.zeros((400, 600), np.uint8)
    # Top-Bar: dicker Block oben
    mask[50:100, 100:500] = 255   # 50px × 400px = 20000 px (große Komponente)
    # Chevron-Region: dünnere getrennte Region darunter
    # NICHT verbunden mit Top-Bar (Lücke bei y=100..150)
    mask[150:300, 120:480] = 255  # 150px × 360px = 54000 px

    # Mit der alten Logik (nur größte Komponente) wäre der Quad nur die
    # 54000-px-Region. Mit Fix muss der Quad BEIDE Regionen umfassen.
    quad = locate_quad(mask)
    # Min/Max-Y des Quads müssen die Spanne 50..300 abdecken (mit
    # kleiner Toleranz für Closing/Rotation).
    y_min = float(quad[:, 1].min())
    y_max = float(quad[:, 1].max())
    assert y_min < 80, (
        f"Quad-Y-min={y_min:.0f} — Top-Bar (y=50..100) nicht erfasst")
    assert y_max > 290, (
        f"Quad-Y-max={y_max:.0f} — Chevron-Region (y=150..300) "
        "nicht voll erfasst")


def test_locate_quad_ignoriert_kleine_rausch_pixel():
    """Vereinzelte Rausch-Pixel (z.B. Bett-Reflexionen unten links im
    Webcam-Bild — siehe diag_02_mask_with_quad.jpg) dürfen die
    Bounding-Box NICHT verzerren."""
    mask = np.zeros((400, 600), np.uint8)
    # Hauptpattern in der Mitte
    mask[150:250, 200:400] = 255  # 100×200 = 20000 px
    # Kleine Rauschen unten-links (z.B. Bett-Glitter-Artefakt)
    mask[380:390, 10:20] = 255   # 10×10 = 100 px (sehr klein)

    quad = locate_quad(mask)
    # Quad sollte NUR das Hauptpattern umfassen, nicht den
    # weit-entfernten Rauschen-Bereich
    x_min = float(quad[:, 0].min())
    y_max = float(quad[:, 1].max())
    assert x_min > 100, (
        f"Quad-X-min={x_min:.0f} — Rauschen bei x=10 fälschlich erfasst")
    assert y_max < 320, (
        f"Quad-Y-max={y_max:.0f} — Rauschen bei y=380 fälschlich erfasst")
