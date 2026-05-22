"""Entzerrt die maskierte Pattern-Region perspektivisch in den
normierten Bett-Koordinaten-Raum (siehe Vision-Spike)."""
from __future__ import annotations

import cv2
import numpy as np

from .model import PatternModel
from .orientation import PX_PER_MM, homography, warp_size


def bett_to_warp(x: float, y: float, model: PatternModel) -> np.ndarray:
    """GCode-Bett-Koordinate (mm) → (px, py) im entzerrten Bild.

    Die GCode-Y-Achse zeigt nach oben, die Bild-Y-Achse nach unten —
    daher wird Y an der Oberkante gespiegelt.
    """
    lo, hi = model.content_bounds
    return np.array([(x - lo.x) * PX_PER_MM, (hi.y - y) * PX_PER_MM])


def rectify(
    mask: np.ndarray, quad: np.ndarray, rot: int, model: PatternModel
) -> np.ndarray:
    """Entzerrt die Filament-Maske in den normierten Pattern-Raum.

    Ein abschließendes morphologisches Schließen (3×3) glättet die durch
    die Perspektiv-Transformation entstandenen Treppen-Artefakte.
    """
    w, h = warp_size(model)
    hm = homography(quad, rot, w, h)
    warped = cv2.warpPerspective(mask, hm, (w, h))
    return cv2.morphologyEx(
        warped, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
