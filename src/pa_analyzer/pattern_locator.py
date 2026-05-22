"""Lokalisiert die gedruckte Pattern-Region im Bild.

Farbunabhängig: die dominante Filamentfarbe wird aus den gesättigten
Bildpixeln ermittelt, dann darauf maskiert. Die 4 Eckpunkte kommen aus
`cv2.minAreaRect` der größten zusammenhängenden Komponente.
"""
from __future__ import annotations

import cv2
import numpy as np


def _dominant_hue(hue: np.ndarray, mask: np.ndarray) -> int:
    """Häufigster Hue unter den maskierten Pixeln, zirkulär geglättet."""
    hist = np.bincount(hue[mask].ravel(), minlength=180).astype(float)
    tiled = np.r_[hist, hist, hist]
    smooth = np.convolve(tiled, np.ones(11) / 11, mode="same")[180:360]
    return int(np.argmax(smooth))


def filament_mask(img: np.ndarray) -> np.ndarray:
    """Binäre Maske (0/255) der gedruckten Filament-Pixel."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    sat_thr = max(60, int(cv2.threshold(sat, 0, 255, cv2.THRESH_OTSU)[0]))
    rough = (sat > sat_thr) & (val > 40) & (val < 250)
    h0 = _dominant_hue(hue, rough)
    dh = np.abs(hue.astype(int) - h0)
    dh = np.minimum(dh, 180 - dh)
    mask = ((dh < 18) & (sat > sat_thr) & (val > 40)).astype(np.uint8) * 255
    return mask


def locate_quad(mask: np.ndarray) -> np.ndarray:
    """4 Eckpunkte der größten zusammenhängenden Filament-Region.

    Reihenfolge: im Uhrzeigersinn ab der Ecke mit der kleinsten
    Koordinatensumme. Über `minAreaRect` — robust gegen die
    Chevron-Einkerbungen der Box-Kante (anders als convexHull).
    """
    opened = cv2.morphologyEx(
        mask, cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(opened)
    if n > 1:
        biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        opened = (lbl == biggest).astype(np.uint8) * 255
    ks = max(7, mask.shape[1] // 120) | 1
    closed = cv2.morphologyEx(
        opened, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ks, ks)))
    cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL,
                               cv2.CHAIN_APPROX_SIMPLE)
    big = max(cnts, key=cv2.contourArea)
    pts = cv2.boxPoints(cv2.minAreaRect(big)).astype(np.float64)
    center = pts.mean(axis=0)
    order = np.argsort(np.arctan2(pts[:, 1] - center[1],
                                  pts[:, 0] - center[0]))
    pts = pts[order]
    start = int(np.argmin(pts.sum(axis=1)))
    return np.roll(pts, -start, axis=0).astype(np.float32)
