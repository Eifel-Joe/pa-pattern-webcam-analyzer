"""Tests für die PA-Wert-Schätzung."""
import pytest

from pa_analyzer.model import AnalysisResult
from pa_analyzer.pa_estimator import estimate_pa


def _kurve(best_index):
    """Konstruiert 21 (pa, fill_in, fill_out)-Tripel mit V-förmigem
    Score und Minimum bei best_index.

    Physikalische Semantik:
    - PA zu niedrig (i < best_index): fill_out > 0 (Wulst außen), fill_in = 1.0
    - PA optimal (i == best_index): fill_in = 1.0, fill_out = 0.0 → score = 0
    - PA zu hoch (i > best_index): fill_out = 0.0, fill_in < 1.0 (Lücke innen)
    score = (1 − fill_in) + fill_out hat sein Minimum bei best_index.
    """
    out = []
    for i in range(21):
        pa = round(0.010 + i * 0.002, 3)
        if i < best_index:
            fill_in = 1.0
            fill_out = 0.12 * (best_index - i)  # Wulst außen
        elif i == best_index:
            fill_in = 1.0
            fill_out = 0.0
        else:
            fill_in = max(0.0, 1.0 - 0.1 * (i - best_index))  # Lücke innen
            fill_out = 0.0
        out.append((pa, fill_in, fill_out))
    return out


def test_estimate_pa_findet_minimum():
    result = estimate_pa(_kurve(best_index=9))  # PA 0.028
    assert isinstance(result, AnalysisResult)
    assert result.nearest_step == pytest.approx(0.028)
    assert abs(result.best_pa - 0.028) <= 0.003


def test_estimate_pa_scores_vollstaendig():
    result = estimate_pa(_kurve(best_index=9))
    assert len(result.scores) == 21


def test_estimate_pa_konfidenz_im_bereich():
    result = estimate_pa(_kurve(best_index=9))
    assert 0.0 <= result.confidence <= 1.0


def test_estimate_pa_flache_kurve_niedrige_konfidenz():
    # Konstante Messwerte -> flacher Score -> niedrige Konfidenz.
    flach = [(round(0.010 + i * 0.002, 3), 0.8, 0.3) for i in range(21)]
    result = estimate_pa(flach)
    assert result.confidence < 0.2
