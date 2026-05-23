"""Erzeugt druckbaren Chevron-PA-Pattern-GCode aus Parametern.

Algorithmus abgeleitet aus Andrew Ellis' Pressure_Linear_Advance_Tool
(Flow-Mathematik mit Stadion-Querschnitt, Chevron-Geometrie). Erzeugt
">"-Chevrons, die der gcode_parser dieses Projekts verlustfrei
zurücklesen kann (siehe Round-Trip-Tests).

Klipper-spezifischer Output (Marlin/RepRap-Befehle wie G21, M900, M572
werden bewusst NICHT emittiert): PRINT_START erhält EXTRUDER/BED als
Parameter (statt eigenständigem M190/M109), Retract/De-Retract um jeden
Travel, Purge-Linie vor dem Pattern, M117 PA-Status, M106 für den
Lüfter, abschließendes M104/M140/M107 als Cooldown-Sicherheitsnetz.
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
    bed_temp: float = 60.0
    extrusion_multiplier: float = 1.0
    speed_print: float = 60.0
    speed_travel: float = 120.0
    # Retract um jeden Travel (Ellis-Stil; 0 = aus)
    retract_distance: float = 0.5    # mm
    retract_speed: float = 35.0      # mm/s
    unretract_speed: float = 35.0    # mm/s
    # Purge-Linie am linken Bettrand vor dem Pattern (0 = keine)
    purge_length: float = 80.0       # mm
    purge_x_margin: float = 10.0     # mm Abstand vom linken Bettrand
    purge_speed: float = 25.0        # mm/s (langsam für sauberes Priming)
    # Lüfter (0..1; PLA: Layer-1 aus, danach voll. PETG/ABS niedriger.)
    fan_speed: float = 1.0
    fan_speed_layer1: float = 0.0
    # Klipper-Hooks (start_gcode unterstützt {temp} und {bed_temp})
    extruder_name: str = ""          # leer = SET_PRESSURE_ADVANCE ohne EXTRUDER=
    z_raise_end: float = 5.0         # mm Z-Raise vor Cooldown
    cooldown_at_end: bool = True     # False: PRINT_END kühlt selbst
    start_gcode: str = "PRINT_START EXTRUDER={temp} BED={bed_temp}"
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


def _retract_block(p: GeneratorParams) -> list[str]:
    """Retract-Sequenz (leer wenn retract_distance == 0)."""
    if p.retract_distance <= 0:
        return []
    return [f"G1 E-{_fmt_e(p.retract_distance)} "
            f"F{round(p.retract_speed * 60)}"]


def _unretract_block(p: GeneratorParams) -> list[str]:
    """De-Retract-Sequenz."""
    if p.retract_distance <= 0:
        return []
    return [f"G1 E{_fmt_e(p.retract_distance)} "
            f"F{round(p.unretract_speed * 60)}"]


def _format_start(p: GeneratorParams) -> str:
    """Substituiert {temp} und {bed_temp} im start_gcode.

    Nutzt str.replace statt str.format, damit unbekannte {Platzhalter}
    (z.B. in user-eigenen Macro-Calls) keinen KeyError werfen, sondern
    unverändert durchgereicht werden.
    """
    return (p.start_gcode
            .replace("{temp}", _fmt(p.temp))
            .replace("{bed_temp}", _fmt(p.bed_temp)))


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
    purge_f = round(p.purge_speed * 60)
    retract = _retract_block(p)
    unretract = _unretract_block(p)

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

    def travel_to(x: float, y: float) -> list[str]:
        """Travel mit Retract+De-Retract (Ellis-Stil)."""
        return [*retract,
                f"G1 X{_fmt(x)} Y{_fmt(y)} F{travel_f}",
                *unretract]

    out: list[str] = [
        "; PA-Pattern erzeugt von pa_analyzer",
        f"; pa_start={p.pa_start} pa_end={p.pa_end} pa_step={p.pa_step}",
        f"; wall_count={p.wall_count} num_layers={p.num_layers}",
        f"; temp={p.temp} bed_temp={p.bed_temp} "
        f"extrusion_multiplier={p.extrusion_multiplier}",
        f"; retract_distance={p.retract_distance} "
        f"purge_length={p.purge_length}",
        # Klipper-PRINT_START erhaelt die Temperaturen als Parameter und
        # uebernimmt das Heizen (Bett-Pre-Heat waehrend Homing/QGL etc.).
        _format_start(p),
        "G90",
        "M83",
        "G92 E0",
    ]

    # Lüfter für die erste Layer (PLA: 0; PETG/ABS: konfigurierbar)
    if p.fan_speed_layer1 > 0:
        out.append(f"M106 S{round(p.fan_speed_layer1 * 255)}")

    # Z auf erste Layer-Höhe
    out.append(f"G1 Z{_fmt(p.layer_height)} F{travel_f}")

    # Purge-Linie am linken Bettrand (sauberer Düsen-Start)
    if p.purge_length > 0:
        purge_y = p.bed_y / 2
        e_purge = _extrusion(
            p.purge_length, lw, p.layer_height, p.filament_diameter,
            p.extrusion_multiplier)
        out.extend(travel_to(p.purge_x_margin, purge_y))
        out.append(
            f"G1 X{_fmt(p.purge_x_margin + p.purge_length)} "
            f"Y{_fmt(purge_y)} E{_fmt_e(e_purge)} F{purge_f}")

    # Rahmen-Box (Travel hin, dann 4 extrudierende Moves)
    e_h = _extrusion(bx1 - bx0, lw, p.layer_height, p.filament_diameter,
                     p.extrusion_multiplier)
    e_v = _extrusion(by1 - by0, lw, p.layer_height, p.filament_diameter,
                     p.extrusion_multiplier)
    out.extend(travel_to(bx0, by0))
    out.append(f"G1 X{_fmt(bx0)} Y{_fmt(by1)} E{_fmt_e(e_v)} F{print_f}")
    out.append(f"G1 X{_fmt(bx1)} Y{_fmt(by1)} E{_fmt_e(e_h)} F{print_f}")
    out.append(f"G1 X{_fmt(bx1)} Y{_fmt(by0)} E{_fmt_e(e_v)} F{print_f}")
    out.append(f"G1 X{_fmt(bx0)} Y{_fmt(by0)} E{_fmt_e(e_h)} F{print_f}")

    # SET_PRESSURE_ADVANCE-Präfix vorbereiten (optional mit EXTRUDER=)
    set_pa_prefix = (
        f"SET_PRESSURE_ADVANCE EXTRUDER={p.extruder_name} ADVANCE="
        if p.extruder_name
        else "SET_PRESSURE_ADVANCE ADVANCE=")

    # Pattern, num_layers mal gestapelt
    z = p.layer_height  # initialisieren falls num_layers == 0 (Edge-Case)
    for layer in range(p.num_layers):
        z = (layer + 1) * p.layer_height
        out.append(f"G1 Z{_fmt(z)} F{travel_f}")
        # Lüfter nach Layer 1 auf den normalen Wert umschalten
        if layer == 1 and p.fan_speed != p.fan_speed_layer1:
            out.append(f"M106 S{round(p.fan_speed * 255)}")
        for j, pa in enumerate(pa_values):
            out.append(f"M117 PA {_fmt(pa)}")
            out.append(f"{set_pa_prefix}{_fmt(pa)}")
            gx = px0 + j * adv
            for k in range(p.wall_count):
                sx = gx + k * wall_off
                out.extend(travel_to(sx, py0))
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

    # End-Sequenz: Retract, Z-Raise, optionaler Cooldown (Sicherheits-
    # netz; viele PRINT_END-Macros machen das selbst — dann
    # cooldown_at_end=False setzen).
    out.extend(retract)
    out.append(f"G1 Z{_fmt(z + p.z_raise_end)} F{travel_f}")
    if p.cooldown_at_end:
        out.append("M104 S0")
        out.append("M140 S0")
        out.append("M107")
    out.append(p.end_gcode)
    # Letzte Zeile der gedruckten Datei: stößt nach Druckende die
    # Auswertung an (Spec §4 Phase 3). Leeres analyze_gcode -> kein Trailer.
    if p.analyze_gcode:
        out.append(p.analyze_gcode)
    return "\n".join(out) + "\n"
