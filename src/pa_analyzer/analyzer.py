"""Pipeline-Integration: Bild + GCode → optimaler PA-Wert."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .apex_analyzer import measure_groups
from .gcode_parser import parse
from .image_loader import load_image
from .model import AnalysisResult
from .orientation import pick_orientation
from .pa_estimator import estimate_pa
from .pattern_locator import filament_mask, locate_quad
from .rectifier import rectify


def analyze_image(image: np.ndarray, gcode_text: str) -> AnalysisResult:
    """Ermittelt den optimalen PA-Wert aus einem bereits geladenen Bild
    (BGR-Array) und dem zugehörigen GCode.

    Pipeline: GCode parsen → Filament-Maske → Eckpunkte → Orientierung →
    entzerren → Apex-Messung → PA-Schätzung.
    """
    model = parse(gcode_text)
    # Zentrale Boundary-Validierung: für GCode ohne auswertbares Pattern
    # liefert parse() leere groups bzw. None-Felder. An der Systemgrenze
    # abfangen — sonst kryptischer Fehler tief in der Vision-Pipeline.
    if (not model.groups or model.frame_box is None
            or model.content_bounds is None):
        raise ValueError(
            "GCode enthält kein auswertbares PA-Pattern "
            "(keine PA-Gruppen, Rahmen-Box oder Druck-Geometrie).")
    mask = filament_mask(image)
    quad = locate_quad(mask)
    rotation, _ratio = pick_orientation(mask, quad, model)
    warped = rectify(mask, quad, rotation, model)
    measurements = measure_groups(warped, model)
    return estimate_pa(measurements)


def analyze(image_path: str | Path, gcode_text: str) -> AnalysisResult:
    """Ermittelt den optimalen PA-Wert aus einem Foto des gedruckten
    Patterns (Datei-Pfad) und dem zugehörigen GCode.

    Pipeline: Bild laden → `analyze_image`.
    """
    return analyze_image(load_image(image_path), gcode_text)
