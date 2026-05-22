"""Misst pro PA-Gruppe den Filament-Flächenanteil in zwei kleinen Boxen
am Chevron-Apex (Zwei-Box-Methode, validiert im Vision-Spike).

fill_in:  Box zentriert auf dem Soll-Apex — fällt, wenn bei zu hohem PA
          eine Lücke entsteht.
fill_out: dieselbe Box nach außen versetzt — hoch, wenn bei zu niedrigem
          PA Material über die Spitze quillt (Wulst).
"""
from __future__ import annotations

import cv2
import numpy as np

from .model import PatternModel
from .orientation import PX_PER_MM
from .rectifier import bett_to_warp

BOX_HALF_MM = 0.6     # halbe Kantenlänge der Mess-Box
OUT_OFFSET_MM = 0.75  # Versatz der Außen-Box entlang der Apex-Richtung


def box_fill(
    mask: np.ndarray,
    center: np.ndarray,
    axis_u: np.ndarray,
    axis_v: np.ndarray,
    half_px: float,
) -> float:
    """Filament-Anteil (0..1) in einem achsen-rotierten Quadrat.

    Das Quadrat wird per `cv2.remap` aus der Maske abgetastet — Achsen
    `axis_u`/`axis_v`, Mittelpunkt `center`, halbe Kante `half_px`.
    """
    grid = np.arange(-half_px, half_px + 1, 1.0)
    uu, vv = np.meshgrid(grid, grid)
    xs = (center[0] + axis_u[0] * uu + axis_v[0] * vv).astype(np.float32)
    ys = (center[1] + axis_u[1] * uu + axis_v[1] * vv).astype(np.float32)
    sampled = cv2.remap(mask, xs, ys, cv2.INTER_NEAREST, borderValue=0)
    return float((sampled > 0).mean())


def measure_groups(
    warped_mask: np.ndarray, model: PatternModel
) -> list[tuple[float, float, float]]:
    """Liefert je PA-Gruppe (pa_value, fill_in, fill_out).

    Pro Gruppe wird der Median über ihre Chevrons gebildet.
    """
    half = BOX_HALF_MM * PX_PER_MM
    offset = OUT_OFFSET_MM * PX_PER_MM
    result: list[tuple[float, float, float]] = []
    for group in model.groups:
        inner, outer = [], []
        for chevron in group.chevrons:
            s = bett_to_warp(chevron.start.x, chevron.start.y, model)
            a = bett_to_warp(chevron.apex.x, chevron.apex.y, model)
            e = bett_to_warp(chevron.end.x, chevron.end.y, model)
            u1 = (a - s) / np.linalg.norm(a - s)
            u2 = (a - e) / np.linalg.norm(a - e)
            out = u1 + u2
            out /= np.linalg.norm(out)
            tang = np.array([-out[1], out[0]])
            inner.append(box_fill(warped_mask, a, out, tang, half))
            outer.append(
                box_fill(warped_mask, a + out * offset, out, tang, half))
        result.append((group.pa_value, float(np.median(inner)),
                       float(np.median(outer))))
    return result
