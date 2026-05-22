"""Erzeugt druckbaren Chevron-PA-Pattern-GCode aus Parametern.

Algorithmus abgeleitet aus Ellis' Pressure_Linear_Advance_Tool
(Flow-Mathematik mit Stadion-Querschnitt, Chevron-Geometrie). Erzeugt
">"-Chevrons, die der gcode_parser dieses Projekts verlustfrei
zurücklesen kann (siehe Round-Trip-Test, Task 8).
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class GeneratorParams:
    """Eingabe-Parameter. Längen in mm, Winkel in Grad,
    Geschwindigkeiten in mm/s, Temperatur in Grad Celsius."""

    # Pattern
    pa_start: float = 0.0
    pa_end: float = 0.08
    pa_step: float = 0.005
    wall_count: int = 3
    wall_side_length: float = 30.0
    corner_angle: float = 90.0
    pattern_spacing: float = 2.0
    num_layers: int = 4
    # Drucker / Material
    bed_x: float = 300.0
    bed_y: float = 300.0
    nozzle_diameter: float = 0.4
    filament_diameter: float = 1.75
    line_ratio: float = 112.5  # Linienbreite in % des Düsendurchmessers
    layer_height: float = 0.2
    # Prozess
    temp: float = 240.0
    extrusion_multiplier: float = 1.0
    speed_print: float = 60.0
    speed_travel: float = 120.0
    # Klipper-Hooks
    start_gcode: str = "PRINT_START"
    end_gcode: str = "PRINT_END"


def _line_width(p: GeneratorParams) -> float:
    """Linienbreite = Düsendurchmesser × line_ratio %."""
    return p.nozzle_diameter * p.line_ratio / 100.0


def _num_patterns(p: GeneratorParams) -> int:
    """Anzahl PA-Werte. floor(x + 0.5) bildet JS-Math.round nach
    (Python round() nutzt Banker's Rounding — hier unerwünscht)."""
    return int(math.floor((p.pa_end - p.pa_start) / p.pa_step + 0.5)) + 1


def _pa_values(p: GeneratorParams) -> list[float]:
    return [round(p.pa_start + i * p.pa_step, 4) for i in range(_num_patterns(p))]


def _extrusion(
    length: float,
    line_width: float,
    layer_height: float,
    filament_diameter: float,
    ext_mult: float,
) -> float:
    """E-Wert für eine extrudierende Bewegung (Stadion-Querschnitt:
    Rechteck-Mittelteil + zwei Halbkreis-Enden)."""
    ext_area = (line_width - layer_height) * layer_height + math.pi * (
        layer_height / 2
    ) ** 2
    fil_area = math.pi * (filament_diameter / 2) ** 2
    return round(length * ext_area / fil_area * ext_mult, 5)


def _half_angle_rad(p: GeneratorParams) -> float:
    return math.radians(p.corner_angle / 2.0)


def _chevron_deltas(p: GeneratorParams) -> tuple[float, float]:
    """(dx, dy) eines Chevron-Arms der Länge wall_side_length."""
    half = _half_angle_rad(p)
    return (
        math.cos(half) * p.wall_side_length,
        math.sin(half) * p.wall_side_length,
    )


def _wall_x_offset(p: GeneratorParams) -> float:
    """X-Versatz zwischen genesteten Chevron-Wänden einer Gruppe."""
    line_spacing = _line_width(p) - p.layer_height * (1 - math.pi / 4)
    return line_spacing / math.sin(_half_angle_rad(p))


def _group_advance(p: GeneratorParams) -> float:
    """X-Abstand von Gruppen-Start zu Gruppen-Start."""
    return (
        (p.wall_count - 1) * _wall_x_offset(p)
        + p.pattern_spacing
        + _line_width(p)
    )
