"""Leitet aus einem Lauf-1-Ergebnis die PA-Grenzen für einen feineren
zweiten Mess-Lauf ab (zweistufiger Workflow, siehe Vision-Spike §6).

Wirkprinzip: Der dominante Webcam-Fehler ist die räumliche
Lokalisierungs-Ungenauigkeit — sie ist pattern-relativ. Ein feiner
gestaffelter zweiter Lauf übersetzt denselben räumlichen Fehler in einen
kleineren absoluten PA-Fehler.
"""
from __future__ import annotations

from .model import AnalysisResult

_WINDOW_STEPS = 3   # halbe Fensterbreite in Original-Schrittweiten
_STEP_DIVISOR = 2   # Verfeinerungsfaktor der Schrittweite


def refine_bounds(result: AnalysisResult) -> tuple[float, float, float]:
    """Liefert (pa_start, pa_end, pa_step) für den zweiten Lauf.

    Das Fenster umspannt `best_pa ± 3 × Original-Schrittweite` (deckt die
    Lauf-1-Unsicherheit ab), die Schrittweite wird halbiert. `pa_start`
    wird auf >= 0 geklemmt. Die Original-Schrittweite stammt aus den
    PA-Werten von `result.scores` — kein Hardcoding.
    """
    pa_values = [pa for pa, _ in result.scores]
    orig_step = pa_values[1] - pa_values[0]
    new_step = round(orig_step / _STEP_DIVISOR, 6)
    half_window = _WINDOW_STEPS * orig_step
    start = max(0.0, round(result.best_pa - half_window, 6))
    end = round(result.best_pa + half_window, 6)
    return (start, end, new_step)
