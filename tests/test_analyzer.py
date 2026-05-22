"""End-zu-End-Tests der Bild→PA-Pipeline."""
from pathlib import Path

import pytest

from pa_analyzer.analyzer import analyze
from pa_analyzer.model import AnalysisResult

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def gcode():
    return (FIXTURES / "pa_pattern.gcode").read_text(
        encoding="utf-8", errors="replace")


def test_analyze_handyfoto_trifft_referenzwert(gcode):
    # Akzeptanzkriterium A3: das hochauflösende Handy-Foto muss den
    # Referenz-PA 0.028 im Band 0.026-0.030 treffen.
    result = analyze(FIXTURES / "IMG_3843.HEIC", gcode)
    assert isinstance(result, AnalysisResult)
    assert 0.026 <= result.best_pa <= 0.030


def test_analyze_webcam_snapshot_laeuft_durch(gcode):
    # Akzeptanzkriterium A4: Webcam-Snapshots sind auflösungslimitiert —
    # geprüft wird nur, dass die Pipeline durchläuft und ein Ergebnis im
    # weiten Plausibilitätsbereich liefert (KEINE enge PA-Erwartung).
    for name in ("pa_snap.jpg", "pa_snap2.jpg"):
        result = analyze(FIXTURES / name, gcode)
        assert isinstance(result, AnalysisResult)
        assert 0.010 <= result.best_pa <= 0.050


def test_analyze_liefert_konfidenz_und_scores(gcode):
    result = analyze(FIXTURES / "IMG_3843.HEIC", gcode)
    assert 0.0 <= result.confidence <= 1.0
    assert len(result.scores) == 21


def test_analyze_wirft_bei_unbrauchbarem_gcode():
    # Zentrale Boundary-Validierung: GCode ohne auswertbares Pattern
    # (hier nur Homing) muss klar abgewiesen werden — kein kryptischer
    # Absturz tief in der Vision-Pipeline.
    with pytest.raises(ValueError):
        analyze(FIXTURES / "IMG_3843.HEIC", "G28\nG1 Z5 F300\n")
