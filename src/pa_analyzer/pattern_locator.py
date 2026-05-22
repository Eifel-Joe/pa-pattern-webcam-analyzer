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
    # Dreifach gekachelt, damit das Glätten über die Hue-Grenze 0/180
    # wrappt (rotes Filament liegt genau dort). Fenster 11 (~22°) ist
    # breiter als die Hue-Toleranz von filament_mask — kein gespaltener Peak.
    tiled = np.r_[hist, hist, hist]
    smooth = np.convolve(tiled, np.ones(11) / 11, mode="same")[180:360]
    return int(np.argmax(smooth))


def filament_mask(img: np.ndarray) -> np.ndarray:
    """Binäre Maske (0/255) der gedruckten Filament-Pixel.

    Drei Stufen (Konstanten im Vision-Spike validiert):
    1. Sättigungs-Schwelle ``max(60, Otsu(S))`` — die Untergrenze 60
       verhindert, dass flau gefärbtes Bett als "gesättigt" gilt.
    2. Grob-Maske ``S > sat_thr und 40 < V < 250`` — schließt zu dunkle
       und ausgebrannte (Glanzlicht-) Pixel aus.
    3. Dominanter Filament-Hue, dann zirkuläre Hue-Distanz < 18 — so wird
       farbunabhängig auf die tatsächliche Filamentfarbe gefiltert.
    """
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
    # Close-Kernel skaliert mit der Bildbreite (Spike: Breite/120);
    # `| 1` erzwingt eine ungerade Größe (von morphologyEx verlangt).
    ks = max(7, mask.shape[1] // 120) | 1
    closed = cv2.morphologyEx(
        opened, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ks, ks)))
    cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL,
                               cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        raise ValueError(
            "locate_quad: keine Filament-Region gefunden — Bild zu "
            "dunkel oder Filamentfarbe nicht erkennbar?")
    big = max(cnts, key=cv2.contourArea)
    pts = cv2.boxPoints(cv2.minAreaRect(big)).astype(np.float64)
    center = pts.mean(axis=0)
    order = np.argsort(np.arctan2(pts[:, 1] - center[1],
                                  pts[:, 0] - center[0]))
    pts = pts[order]
    start = int(np.argmin(pts.sum(axis=1)))
    return np.roll(pts, -start, axis=0).astype(np.float32)
