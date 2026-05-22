"""Tests für die Lauf-2-Grenzen-Ableitung (zweistufiger Workflow)."""
import pytest

from pa_analyzer.model import AnalysisResult
from pa_analyzer.two_stage import refine_bounds


def _result(best_pa):
    """Lauf-1-Ergebnis mit 21 PA-Werten 0.010..0.050, Schritt 0.002."""
    scores = tuple((round(0.010 + i * 0.002, 3), 1.0) for i in range(21))
    return AnalysisResult(
        best_pa=best_pa, nearest_step=round(best_pa, 3),
        confidence=0.5, scores=scores)


def test_refine_bounds_umschliesst_best_pa():
    start, end, _ = refine_bounds(_result(best_pa=0.028))
    assert start < 0.028 < end


def test_refine_bounds_schrittweite_feiner():
    _, _, step = refine_bounds(_result(best_pa=0.028))
    # Original-Schritt 0.002 -> halbiert 0.001.
    assert step == pytest.approx(0.001)


def test_refine_bounds_fenster_drei_schritte():
    start, end, _ = refine_bounds(_result(best_pa=0.028))
    # +/- 3 * 0.002 = +/- 0.006 um best_pa.
    assert start == pytest.approx(0.022)
    assert end == pytest.approx(0.034)


def test_refine_bounds_klemmt_start_auf_null():
    # best_pa nahe 0 -> start darf nicht negativ werden.
    start, _, _ = refine_bounds(_result(best_pa=0.004))
    assert start == 0.0
