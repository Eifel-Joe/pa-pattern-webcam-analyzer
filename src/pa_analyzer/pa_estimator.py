"""Ermittelt aus den Apex-Messungen den optimalen Pressure-Advance-Wert.

score = (1 − fill_in) + fill_out — bestraft Lücke (zu hoher PA) und
Wulst (zu niedriger PA). Das Minimum der geglätteten Score-Kurve ist
der optimale PA; ein Parabel-Fit um das Minimum liefert den
interpolierten Wert.
"""
from __future__ import annotations

import numpy as np

from .model import AnalysisResult


def estimate_pa(
    measurements: list[tuple[float, float, float]],
) -> AnalysisResult:
    """`measurements`: Liste von (pa_value, fill_in, fill_out)."""
    pa = np.array([m[0] for m in measurements], dtype=float)
    fill_in = np.array([m[1] for m in measurements], dtype=float)
    fill_out = np.array([m[2] for m in measurements], dtype=float)
    score = (1.0 - fill_in) + fill_out

    # Leichtes Glätten gegen Einzelausreißer (Ränder unverändert lassen).
    smooth = np.convolve(score, np.ones(3) / 3, mode="same")
    smooth[0], smooth[-1] = score[0], score[-1]

    k = int(np.argmin(smooth))
    best = float(pa[k])

    # Parabel-Fit ±3 Punkte um das diskrete Minimum für Sub-Schritt-Wert.
    lo, hi = max(0, k - 3), min(len(pa), k + 4)
    if hi - lo >= 3:
        coef = np.polyfit(pa[lo:hi], smooth[lo:hi], 2)
        if coef[0] > 0:
            vertex = -coef[1] / (2.0 * coef[0])
            if pa[0] <= vertex <= pa[-1]:
                best = float(vertex)

    # Konfidenz: Ausprägung des Minimums relativ zum Kurven-Mittel.
    span = float(smooth.mean() - smooth.min())
    confidence = float(np.clip(span / (smooth.mean() + 1e-6), 0.0, 1.0))

    return AnalysisResult(
        best_pa=best,
        nearest_step=float(pa[k]),
        confidence=confidence,
        scores=tuple((float(p), float(s)) for p, s in zip(pa, score)),
    )
