"""Pipeline-Integration: Bilddatei + GCode → optimaler PA-Wert."""
from __future__ import annotations

from pathlib import Path

from .apex_analyzer import measure_groups
from .gcode_parser import parse
from .image_loader import load_image
from .model import AnalysisResult
from .orientation import pick_orientation
from .pa_estimator import estimate_pa
from .pattern_locator import filament_mask, locate_quad
from .rectifier import rectify


def analyze(image_path: str | Path, gcode_text: str) -> AnalysisResult:
    """Ermittelt den optimalen PA-Wert aus einem Foto des gedruckten
    Patterns und dem zugehörigen GCode.

    Pipeline: GCode parsen → Bild laden → Filament-Maske → Eckpunkte →
    Orientierung → entzerren → Apex-Messung → PA-Schätzung.
    """
    model = parse(gcode_text)
    # Zentrale Boundary-Validierung: für GCode ohne auswertbares Pattern
    # liefert parse() leere groups bzw. None-Felder. An der Systemgrenze
    # abfangen — sonst kryptischer Fehler tief in der Vision-Pipeline.
    if (not model.groups or model.frame_box is None
            or model.content_bounds is None):
        raise ValueError(
            "analyze: GCode enthält kein auswertbares PA-Pattern "
            "(keine PA-Gruppen, Rahmen-Box oder Druck-Geometrie).")
    image = load_image(image_path)
    mask = filament_mask(image)
    quad = locate_quad(mask)
    rotation, _ratio = pick_orientation(mask, quad, model)
    warped = rectify(mask, quad, rotation, model)
    measurements = measure_groups(warped, model)
    return estimate_pa(measurements)
