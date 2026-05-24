"""Bestimmt, welche der 4 Quad-Rotationen die korrekte Orientierung ist.

Das Pattern ist nahezu punktsymmetrisch. Eindeutiges Unterscheidungs-
merkmal: der Beschriftungs-Balken (Vollfüllung) liegt nur auf EINER
Seite. Die Rotation mit dem größten Dichte-Verhältnis Balken-Band /
Chevron-Band ist die richtige.

Dieses Modul beherbergt zudem die Warp-Geometrie-Primitive
(`PX_PER_MM`, `warp_size`, `homography`), da es das erste Pipeline-
Modul ist, das sie braucht; `rectifier` und `apex_analyzer` importieren
sie von hier.
"""
from __future__ import annotations

import cv2
import numpy as np

from .model import PatternModel

PX_PER_MM = 24.0


def warp_size(model: PatternModel) -> tuple[int, int]:
    """(Breite, Höhe) des entzerrten Bildes in Pixeln."""
    lo, hi = model.content_bounds
    w = int(round((hi.x - lo.x) * PX_PER_MM))
    h = int(round((hi.y - lo.y) * PX_PER_MM))
    return w, h


def homography(quad: np.ndarray, rot: int, w: int, h: int) -> np.ndarray:
    """Perspektiv-Transformation Bild-Quad → entzerrtes Rechteck (w×h).

    `rot` (0..3) rolliert die Quad-Ecken, um die Bild-Orientierung
    auszugleichen."""
    norm = np.array([[0, 0], [w, 0], [w, h], [0, h]], np.float32)
    src = np.roll(quad, -rot, axis=0).astype(np.float32)
    return cv2.getPerspectiveTransform(src, norm)


def pick_orientation(
    mask: np.ndarray, quad: np.ndarray, model: PatternModel
) -> tuple[int, float]:
    """Liefert (beste Rotation 0..3, Dichte-Verhältnis der besten).

    Das Balken-Band ist der Bildstreifen oberhalb der Chevron-Apex-
    Oberkante (= dort wo die Top-Bar liegt); das Chevron-Band der Rest.
    Höchstes Verhältnis gewinnt.

    Pipeline-Fix 2026-05-24: `chevron_band_top` aus dem Parser statt
    `frame_box.max_y` — letzteres ist bei v2-Geometrie identisch mit
    `content_bounds.hi.y` (oder sogar höher, wegen Marker-Plan-Wert),
    was zu `band <= 0` und falscher Rotation führte (siehe
    Pipeline-Diagnose).
    """
    w, h = warp_size(model)
    _, hi = model.content_bounds
    # Oberkante des Chevron-Bandes = Unterkante des Top-Bar-Bandes.
    # Bevorzugt: chevron_band_top vom Parser (max-y aller Apexe).
    # Fallback: frame_box.max_y für Backward-Compat mit OrcaSlicer-
    # Fixture (wo Top-Bar AUSSERHALB des Frames liegt → frame_top <
    # hi.y und band positiv).
    if model.chevron_band_top is not None:
        band_grenze = model.chevron_band_top
    else:
        band_grenze = max(p.y for p in model.frame_box.corners)
    band = int(round((hi.y - band_grenze) * PX_PER_MM))

    # Safety-Net: bei nicht-positivem band kann die Diskriminierung
    # nicht funktionieren (warped[:0] ist leer, warped[:negativ] wäre
    # zufällig). Konservativ rot=0 zurückgeben — Voraussetzung dafür
    # ist dass locate_quad das Pattern schon TL-kanonisch liefert.
    if band <= 0:
        return 0, 0.0

    best_rot, best_ratio = 0, -1.0
    for rot in range(4):
        hm = homography(quad, rot, w, h)
        warped = cv2.warpPerspective(mask, hm, (w, h))
        top = (warped[:band] > 0).mean()
        mid = (warped[band:] > 0).mean()
        ratio = top / mid if mid > 1e-3 else 0.0
        if ratio > best_ratio:
            best_rot, best_ratio = rot, ratio
    return best_rot, best_ratio
