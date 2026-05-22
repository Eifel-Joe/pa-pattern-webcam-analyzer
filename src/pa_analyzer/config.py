"""Lädt die Werkzeug-Konfiguration aus einer JSON-Datei.

Enthält die nicht-pattern-bezogenen Laufzeit-Einstellungen: Webcam-URL und
Datei-Pfade. Pattern-Parameter gehören dagegen zu GeneratorParams.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """Laufzeit-Konfiguration. Alle Felder haben Defaults, sodass das
    Werkzeug auch ohne Konfigurationsdatei läuft."""

    webcam_url: str = ""
    gcode_path: str = "pa_calibration.gcode"
    report_path: str = "pa_report.json"


def load_config(path: str | Path) -> Config:
    """Lädt die Konfiguration aus einer JSON-Datei.

    Fehlt die Datei, werden reine Default-Werte zurückgegeben. Unbekannte
    Schlüssel in der Datei werden ignoriert (vorwärtskompatibel).
    """
    path = Path(path)
    if not path.is_file():
        return Config()
    data = json.loads(path.read_text(encoding="utf-8"))
    known = {f.name for f in fields(Config)}
    return Config(**{k: v for k, v in data.items() if k in known})
