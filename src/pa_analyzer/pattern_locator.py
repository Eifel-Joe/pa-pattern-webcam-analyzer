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
    """4 Eckpunkte um ALLE Filament-Regionen des Patterns.

    Reihenfolge: im Uhrzeigersinn ab der Ecke mit der kleinsten
    Koordinatensumme. Über `minAreaRect` — robust gegen die
    Chevron-Einkerbungen der Box-Kante (anders als convexHull).

    Stabilitäts-Diagnose 2026-05-24 (Live-Test 4, Snapshots
    stab_a/b/c): bei v2-Pattern und Webcam-Auflösung 1280×960
    zerfallen Chevrons in der Maske in viele einzelne Components
    von 300-500 px je (deutlich unter MIN_AREA 1228 px). Würde
    `connectedComponentsWithStats` direkt nach OPEN laufen,
    blieben nur Top-Bar + ggf. zufällig durch Stringing-Pixel
    angeheftete Chevrons übrig — die Quad-Höhe schwankte um
    ~50 % je nach Zufalls-Brücke (76/122/76 px auf 3 Snapshots
    im 30-s-Abstand). Fix: CLOSE vor connectedComponents. Der
    Closing-Kernel (Breite/120 ≈ 11 px) verschmilzt Top-Bar +
    alle Chevrons zu EINER stabilen Mega-Komponente (~32500 px
    auf allen 3 Snapshots, Höhe 183-184 px statt 76-122).
    Bett-Reflexionen (>>10 px entfernt) bleiben separate Mini-
    Komponenten und werden vom MIN_AREA-Filter weggeworfen.
    Siehe tests/test_pattern_locator.py::
    test_locate_quad_verschmilzt_chevron_reste_unter_min_area.
    """
    opened = cv2.morphologyEx(
        mask, cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    # VERTIKALES Closing-Strukturelement (3 × 21 RECT) statt ELLIPSE.
    # Hintergrund Live-Test 5 (v3-Pattern): in der filament_mask zerfällt
    # das Pattern in Top-Bar (kompakte Komponente) + viele kleine
    # Chevron-Spitzen-Components (50-100 px je, alle unter MIN_AREA).
    # Ein symmetrisches ELLIPSE(11) Closing schließt die ~3-5 px vertikale
    # Lücke zwischen Top-Bar-Unterkante und Chevron-Spitzen nicht
    # zuverlässig. Ein vertikales RECT(3, 21) schließt die Lücke
    # sicher (vertikale Reichweite 10 px in jede Richtung), expandiert
    # aber horizontal kaum (1 px) — verbindet Top-Bar+Chevrons OHNE
    # benachbarte Hintergrund-Strukturen (HEIC) einzuziehen.
    # NOT-TO-DO: ELLIPSE oder größeres symmetrisches Strukturelement —
    # bei großen Bildern (HEIC, 4032 px breit) zieht das Pattern mit
    # benachbartem Material zusammen und ruiniert das Aspect-Ratio.
    # NOT-TO-DO: density-adaptives ks (frühere Iteration): bei dense
    # Pattern wurde sanftes ks=3 gewählt, was die Chevron-Spitzen-Lücken
    # nicht schloss — Pipeline misst dann Müll, weil der Quad nur den
    # Top-Bar erfasst.
    closed = cv2.morphologyEx(
        opened, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, 21)))
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(closed)
    # Mindest-Fläche für "ernsthafte" Komponente: 0.1 % der Bildfläche,
    # mindestens 200 px. Schützt davor, bei extrem dunklen Bildern
    # zufälligen Pixel-Rauschen-Cluster als Pattern auszuwählen.
    min_area = max(200, mask.size // 1000)
    # Nur die GRÖSSTE Komponente nehmen — nach dem Closing-Vorher
    # ist das echte Pattern zu einer Mega-Komponente verschmolzen.
    # NOT-TO-DO: Alle qualifying Components kombinieren — Bei
    # hochauflösenden Fotos (HEIC, Hintergrund-Strukturen) gibt es
    # qualifying Side-Components abseits des Patterns; deren
    # Inklusion ruiniert das Aspect-Ratio (Validierung im Test
    # test_locate_quad_umschliesst_patternregion_heic).
    candidates = [(int(stats[i, cv2.CC_STAT_AREA]), i)
                  for i in range(1, n)
                  if stats[i, cv2.CC_STAT_AREA] >= min_area]
    if not candidates:
        raise ValueError(
            "locate_quad: keine Filament-Region gefunden — Bild zu "
            "dunkel oder Filamentfarbe nicht erkennbar?")
    _, biggest = max(candidates)
    selected = (lbl == biggest).astype(np.uint8) * 255
    # Direkt minAreaRect über alle Pixel der gewählten Komponente.
    ys, xs = np.where(selected > 0)
    pts = np.column_stack([xs, ys]).astype(np.float32)
    box = cv2.boxPoints(cv2.minAreaRect(pts)).astype(np.float64)
    center = box.mean(axis=0)
    order = np.argsort(np.arctan2(box[:, 1] - center[1],
                                  box[:, 0] - center[0]))
    box = box[order]
    start = int(np.argmin(box.sum(axis=1)))
    return np.roll(box, -start, axis=0).astype(np.float32)
