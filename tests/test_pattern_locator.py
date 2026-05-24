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
    """Realistisches Webcam-Szenario: Top-Bar als ein Block und
    Chevrons als VIELE kleine Components (300-600 px je, jeder
    unter MIN_AREA). Top-Bar ist nur ~55 % aller weißen Pixel —
    die Fragmentierungs-Heuristik in locate_quad muss erkennen,
    dass das Pattern stark zerfallen ist, und kräftiges Closing
    anwenden, damit der Quad ALLE Pattern-Teile erfasst."""
    # Breite 1320 → kräftiger Close-Kernel ks=11
    mask = np.zeros((400, 1320), np.uint8)
    # Top-Bar (~21000 px = ~54 % des Total, wie reales Webcam-Bild)
    mask[50:80, 250:950] = 255   # 30×700 = 21000 px
    # 30 einzelne Chevron-Reste (600 px je, alle unter MIN_AREA=528)
    # Lücke y=80..86 (6 px) zum Top-Bar — vom Closing schließbar
    for x in range(150, 1150, 33):
        mask[86:116, x:x + 20] = 255  # 30×20 = 600 px je
    # Total: 21000 + 30*600 = 39000; Top-Bar/Total ≈ 54 % → density < 75 %
    quad = locate_quad(mask)
    y_min = float(quad[:, 1].min())
    y_max = float(quad[:, 1].max())
    assert y_min < 70, (
        f"Quad-Y-min={y_min:.0f} — Top-Bar (y=50..80) nicht erfasst")
    assert y_max > 105, (
        f"Quad-Y-max={y_max:.0f} — Chevron-Reste bei y=86..116 nicht "
        "erfasst (Closing greift nicht oder Density-Heuristik falsch?)")


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


# ============================================================================
# Stabilitäts-Diagnose 2026-05-24 (Live-Test 4, 3 Webcam-Snapshots stab_a/b/c):
# Im echten Webcam-Bild zerfallen Chevrons in viele kleine Components
# (300-500 px je), die ALLE unter der MIN_AREA-Schwelle (~1200 px) liegen.
# Die "Combine-Qualifying-Components"-Logik wirft sie alle raus und behält
# nur den Top-Bar → Quad nur 76-122 px hoch statt ~185 px, mit ~50%
# Höhen-Schwankung weil zufällige Stringing-Pixel mal Top-Bar mit Chevron
# verschmelzen mal nicht. Fix: Closing VOR connectedComponents, sodass
# Top-Bar + alle Chevrons zu EINER stabilen Mega-Komponente werden
# (verifiziert mit reference/diag_close_first.py: 184/184/183 px statt
# 81/122/76 px Höhe).
# ============================================================================

def test_locate_quad_verschmilzt_chevron_reste_unter_min_area():
    """Reale Webcam-Anatomie: Top-Bar als ein Block + VIELE einzelne
    Chevron-Reste (300-600 px je, alle unter MIN_AREA). Top-Bar ist
    deutlich unter 75 % aller weißen Pixel — die Fragmentierungs-
    Heuristik muss kräftiges Closing wählen, damit Chevron-Reste
    nicht alle vom MIN_AREA-Filter weggeworfen werden."""
    mask = np.zeros((400, 1320), np.uint8)
    mask[50:80, 250:950] = 255  # Top-Bar 21000 px
    for x in range(150, 1150, 33):
        mask[86:116, x:x + 20] = 255  # 30 Chevron-Reste à 600 px
    quad = locate_quad(mask)
    y_max = float(quad[:, 1].max())
    assert y_max > 105, (
        f"Quad-Y-max={y_max:.0f} — Chevron-Reste bei y=86..116 nicht "
        "erfasst (Closing greift nicht vor connectedComponents?)")


def test_locate_quad_stabil_bei_pixel_bruecke():
    """Stabilitäts-Eigenschaft: Eine 1-Pixel-Brücke zwischen Top-Bar
    und Chevron-Region (zufälliges Stringing-Pixel) darf den Quad
    NICHT um >5 % ändern. Vor dem Fix variierte der Quad um ~50 %
    je nach Zufalls-Brücke."""
    h, w = 400, 1320
    def _mask(mit_bruecke: bool) -> np.ndarray:
        m = np.zeros((h, w), np.uint8)
        m[50:80, 250:950] = 255  # Top-Bar 21000 px
        for x in range(150, 1150, 33):
            m[86:116, x:x + 20] = 255  # 30 Chevron-Reste
        if mit_bruecke:
            # 1-Pixel-Brücke verbindet Top-Bar mit einem Chevron
            m[80:86, 600:601] = 255
        return m
    q_ohne = locate_quad(_mask(False))
    q_mit = locate_quad(_mask(True))
    span_ohne = float(q_ohne[:, 1].max() - q_ohne[:, 1].min())
    span_mit = float(q_mit[:, 1].max() - q_mit[:, 1].min())
    # Toleranz 5 % auf die größere Spanne
    tol = 0.05 * max(span_ohne, span_mit)
    assert abs(span_ohne - span_mit) <= tol, (
        f"Quad instabil: ohne-Brücke y_span={span_ohne:.0f}, "
        f"mit-Brücke y_span={span_mit:.0f}")
