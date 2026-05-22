"""Tests für die Report-Ausgabe."""
import json

from pa_analyzer.model import AnalysisResult
from pa_analyzer.report import format_result, read_json, write_json

_RESULT = AnalysisResult(
    best_pa=0.0285,
    nearest_step=0.028,
    confidence=0.7,
    scores=((0.024, 1.2), (0.026, 0.9), (0.028, 0.4)),
)


def test_format_result_enthaelt_kernwerte():
    text = format_result(_RESULT)
    assert "0.0285" in text
    assert "0.0280" in text
    assert "70 %" in text


def test_write_json_ist_round_trip_faehig(tmp_path):
    p = tmp_path / "report.json"
    write_json(_RESULT, p)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["best_pa"] == 0.0285
    assert data["nearest_step"] == 0.028
    assert data["confidence"] == 0.7
    assert data["scores"] == [[0.024, 1.2], [0.026, 0.9], [0.028, 0.4]]


def test_read_json_rekonstruiert_analysisresult(tmp_path):
    p = tmp_path / "report.json"
    write_json(_RESULT, p)
    wieder = read_json(p)
    assert wieder == _RESULT
