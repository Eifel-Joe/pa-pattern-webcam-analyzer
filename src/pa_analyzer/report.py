"""Formatiert ein AnalysisResult für Konsole und JSON-Report."""
from __future__ import annotations

import json
from pathlib import Path

from .model import AnalysisResult


def format_result(result: AnalysisResult) -> str:
    """Erzeugt eine mehrzeilige, menschenlesbare Ergebnis-Zusammenfassung."""
    return "\n".join([
        "PA-Analyse-Ergebnis",
        f"  Optimaler PA-Wert:     {result.best_pa:.4f}  (interpoliert)",
        f"  Nächster Druckschritt: {result.nearest_step:.4f}",
        f"  Konfidenz:             {result.confidence * 100:.0f} %",
    ])


def write_json(result: AnalysisResult, path: str | Path) -> None:
    """Schreibt das Ergebnis als JSON-Datei (UTF-8, eingerückt)."""
    payload = {
        "best_pa": result.best_pa,
        "nearest_step": result.nearest_step,
        "confidence": result.confidence,
        "scores": [[pa, score] for pa, score in result.scores],
    }
    Path(path).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")


def read_json(path: str | Path) -> AnalysisResult:
    """Liest einen zuvor mit `write_json` geschriebenen Report zurück."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return AnalysisResult(
        best_pa=data["best_pa"],
        nearest_step=data["nearest_step"],
        confidence=data["confidence"],
        scores=tuple((pa, score) for pa, score in data["scores"]),
    )
