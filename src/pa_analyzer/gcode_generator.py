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
    analyze_gcode: str = "RUN_SHELL_COMMAND CMD=pa_analyze"


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


def _fmt(v: float) -> str:
    """Koordinate/PA-Wert mit bis zu 4 Nachkommastellen, ohne überflüssige
    Nullen. Für den Wertebereich dieses Generators (Koordinaten 1–300,
    PA 0–0.5) erzeugt :g keine wissenschaftliche Notation."""
    return f"{round(v, 4):g}"


def _fmt_e(v: float) -> str:
    """Extrusionswert mit bis zu 5 Nachkommastellen."""
    return f"{round(v, 5):g}"


def generate(params: GeneratorParams) -> str:
    """Erzeugt den vollständigen PA-Pattern-GCode als String."""
    p = params
    lw = _line_width(p)
    dx, dy = _chevron_deltas(p)
    wall_off = _wall_x_offset(p)
    adv = _group_advance(p)
    pa_values = _pa_values(p)
    e_arm = _extrusion(
        p.wall_side_length, lw, p.layer_height, p.filament_diameter,
        p.extrusion_multiplier,
    )
    print_f = round(p.speed_print * 60)
    travel_f = round(p.speed_travel * 60)

    # Pattern-Abmessungen und Bett-Zentrierung
    pattern_w = (
        (len(pa_values) - 1) * adv + (p.wall_count - 1) * wall_off + dx
    )
    pattern_h = 2 * dy
    margin = 4.0
    bx0 = p.bed_x / 2 - (pattern_w + 2 * margin) / 2
    by0 = p.bed_y / 2 - (pattern_h + 2 * margin) / 2
    bx1 = bx0 + pattern_w + 2 * margin
    by1 = by0 + pattern_h + 2 * margin
    px0 = bx0 + margin  # Start-X des ersten Chevrons
    py0 = by0 + margin  # Start-Y (untere Arm-Enden)

    out: list[str] = [
        "; PA-Pattern erzeugt von pa_analyzer (Etappe 1)",
        f"; pa_start={p.pa_start} pa_end={p.pa_end} pa_step={p.pa_step}",
        f"; wall_count={p.wall_count} num_layers={p.num_layers}",
        f"; temp={p.temp} extrusion_multiplier={p.extrusion_multiplier}",
        "G90",
        "M83",
        p.start_gcode,
        f"M109 S{_fmt(p.temp)}",
    ]

    # Rahmen-Box auf erster Layer-Höhe (4 achsenparallele extrudierende Moves)
    e_h = _extrusion(bx1 - bx0, lw, p.layer_height, p.filament_diameter,
                     p.extrusion_multiplier)
    e_v = _extrusion(by1 - by0, lw, p.layer_height, p.filament_diameter,
                     p.extrusion_multiplier)
    out.append(f"G1 Z{_fmt(p.layer_height)} F{travel_f}")
    out.append(f"G1 X{_fmt(bx0)} Y{_fmt(by0)} F{travel_f}")
    out.append(f"G1 X{_fmt(bx0)} Y{_fmt(by1)} E{_fmt_e(e_v)} F{print_f}")
    out.append(f"G1 X{_fmt(bx1)} Y{_fmt(by1)} E{_fmt_e(e_h)} F{print_f}")
    out.append(f"G1 X{_fmt(bx1)} Y{_fmt(by0)} E{_fmt_e(e_v)} F{print_f}")
    out.append(f"G1 X{_fmt(bx0)} Y{_fmt(by0)} E{_fmt_e(e_h)} F{print_f}")

    # Pattern, num_layers mal gestapelt
    for layer in range(p.num_layers):
        z = (layer + 1) * p.layer_height
        out.append(f"G1 Z{_fmt(z)} F{travel_f}")
        for j, pa in enumerate(pa_values):
            out.append(f"SET_PRESSURE_ADVANCE ADVANCE={_fmt(pa)}")
            gx = px0 + j * adv
            for k in range(p.wall_count):
                sx = gx + k * wall_off
                # Travel zum Chevron-Start (trennt die Chevron-Runs)
                out.append(f"G1 X{_fmt(sx)} Y{_fmt(py0)} F{travel_f}")
                # Arm 1: Start -> Apex
                out.append(
                    f"G1 X{_fmt(sx + dx)} Y{_fmt(py0 + dy)} "
                    f"E{_fmt_e(e_arm)} F{print_f}"
                )
                # Arm 2: Apex -> End
                out.append(
                    f"G1 X{_fmt(sx)} Y{_fmt(py0 + 2 * dy)} "
                    f"E{_fmt_e(e_arm)} F{print_f}"
                )

    out.append(p.end_gcode)
    # Letzte Zeile der gedruckten Datei: stößt nach Druckende die
    # Auswertung an (Spec §4 Phase 3). Leeres analyze_gcode -> kein Trailer.
    if p.analyze_gcode:
        out.append(p.analyze_gcode)
    return "\n".join(out) + "\n"
