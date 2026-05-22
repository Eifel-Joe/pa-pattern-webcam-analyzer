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

    Das Balken-Band ist der Bildstreifen oberhalb der Rahmen-Box-
    Oberkante; das Chevron-Band der Rest. Höchstes Verhältnis gewinnt.
    """
    w, h = warp_size(model)
    _, hi = model.content_bounds  # nur hi.y für die Bandgrenze gebraucht
    # Oberkante der Rahmen-Box = Unterkante des Balkens.
    frame_top = max(p.y for p in model.frame_box.corners)
    band = int(round((hi.y - frame_top) * PX_PER_MM))

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
