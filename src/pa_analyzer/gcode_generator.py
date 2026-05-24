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

from .glyphs import render_label_gcode


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
    speed_print: float = 100.0
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
    # Pattern-Markierungen (neu, siehe docs/specs/2026-05-24-pattern-markierungen-und-speed-accel.md)
    top_bar_height: float = 4.0         # mm Vollfüllung-Höhe
    chevron_band_gap: float = 1.0       # mm Trennzone Top-Bar/Chevrons
    anchor_marker_width: float = 2.0    # mm horizontal
    anchor_marker_height: float = 8.0   # mm vertikal
    label_glyph_height: float = 0.7     # mm PA-Label-Glyph
    label_glyph_width: float = 0.5      # mm
    label_glyph_gap: float = 0.2        # mm zwischen Glyphen
    header_glyph_height: float = 1.0    # mm Speed/Accel-Header etwas größer
    header_glyph_width: float = 0.7
    header_column_spacing: float = 4.0  # mm zwischen Speed- und Accel-Spalte
    header_to_labels_gap: float = 3.0   # mm Header-Trennung zu PA-Labels

    # Beschleunigung (neu)
    accel: float = 2000.0               # mm/s² (0 = nicht emittieren)

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


def _top_bar_block(
    p: GeneratorParams, x0: float, x1: float,
    y_low: float, y_high: float,
    travel_to_fn, print_f: int,
) -> list[str]:
    """Vollfüllung der Top-Bar als Linien-Stadion.

    Zieht horizontale Linien Y=y_low bis Y=y_high im Abstand
    `line_width`, abwechselnd in X-Richtung (Boustrophedon = Pflüge
    drehen ohne Travel).
    """
    lw = _line_width(p)
    e_h = _extrusion(x1 - x0, lw, p.layer_height,
                     p.filament_diameter, p.extrusion_multiplier)
    out: list[str] = []
    n_lines = max(1, int(round((y_high - y_low) / lw)))
    # Travel zum Start
    out.extend(travel_to_fn(x0, y_low))
    rechts = True
    for i in range(n_lines):
        y = y_low + i * lw
        if rechts:
            out.append(f"G1 X{_fmt(x1)} Y{_fmt(y)} "
                       f"E{_fmt_e(e_h)} F{print_f}")
        else:
            out.append(f"G1 X{_fmt(x0)} Y{_fmt(y)} "
                       f"E{_fmt_e(e_h)} F{print_f}")
        rechts = not rechts
    return out


def _anchor_marker_block(
    p: GeneratorParams, x_left: float, y_center: float,
    travel_to_fn, print_f: int,
) -> list[str]:
    """Gefülltes Rechteck links neben dem Pattern (Asymmetrie-Anker).

    x_left = linke Außenkante des Rechtecks (Frame-Innenkante = bx0+margin).
    y_center = vertikale Mitte des Rechtecks (Chevron-Reihenmitte = py0+dy).

    Der Marker besteht aus n_lines vertikalen Linien im Abstand line_width,
    abwechselnd nach oben / nach unten gezeichnet (Boustrophedon). Jede Linie
    hat die Länge anchor_marker_height.
    """
    lw = _line_width(p)
    y_low = y_center - p.anchor_marker_height / 2
    y_high = y_center + p.anchor_marker_height / 2
    e_v = _extrusion(p.anchor_marker_height, lw, p.layer_height,
                     p.filament_diameter, p.extrusion_multiplier)
    out: list[str] = []
    n_lines = max(1, int(round(p.anchor_marker_width / lw)))
    out.extend(travel_to_fn(x_left, y_low))
    nach_oben = True
    for i in range(n_lines):
        x = x_left + i * lw
        if nach_oben:
            out.append(f"G1 X{_fmt(x)} Y{_fmt(y_high)} "
                       f"E{_fmt_e(e_v)} F{print_f}")
        else:
            out.append(f"G1 X{_fmt(x)} Y{_fmt(y_low)} "
                       f"E{_fmt_e(e_v)} F{print_f}")
        nach_oben = not nach_oben
    return out


def _pa_labels_block(
    p: GeneratorParams, pa_values: list[float], px0: float,
    label_y_top: float, group_advance: float,
) -> list[str]:
    """Hochkant rotierte PA-Labels auf der Top-Bar.

    Ein Label pro Chevron-Gruppe. Position: über dem Chevron, label_y_top
    ist die Y-Koordinate der oberen Glyph-Kante (label läuft nach unten,
    weil rotation=90).
    """
    out: list[str] = []
    for j, pa in enumerate(pa_values):
        # X-Mitte der Chevron-Gruppe j.
        gx_center = px0 + j * group_advance + (
            (p.wall_count - 1) * _wall_x_offset(p) + _chevron_deltas(p)[0]
        ) / 2
        # Bei rotation=90 ist der Cursor-Anker die linke obere Ecke
        # der ersten Glyphe. Wir möchten das Label horizontal an der
        # Chevron-Mitte zentriert — die rotierte Glyph-Höhe wird nach
        # rechts in X gerendert, also Start x = gx_center -
        # label_glyph_height/2.
        x_start = gx_center - p.label_glyph_height / 2
        out.extend(render_label_gcode(
            text=_fmt(pa),
            x=x_start, y=label_y_top,
            glyph_height=p.label_glyph_height,
            glyph_width=p.label_glyph_width,
            glyph_gap=p.label_glyph_gap,
            line_width=_line_width(p),
            layer_height=p.layer_height,
            filament_diameter=p.filament_diameter,
            extrusion_multiplier=p.extrusion_multiplier,
            print_speed=p.speed_print,
            travel_speed=p.speed_travel,
            rotation=90,
        ))
    return out


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
    chevron_h = 2 * dy
    # pattern_h umfasst: Top-Bar + Trennzone + Chevron-Band
    # (Vorbereitung für Top-Bar-Emit in Task 6)
    pattern_h = p.top_bar_height + p.chevron_band_gap + chevron_h
    margin = 4.0
    bx0 = p.bed_x / 2 - (pattern_w + 2 * margin) / 2
    by0 = p.bed_y / 2 - (pattern_h + 2 * margin) / 2
    bx1 = bx0 + pattern_w + 2 * margin
    by1 = by0 + pattern_h + 2 * margin
    px0 = bx0 + margin            # Start-X des ersten Chevrons
    py0 = by0 + margin            # untere Arm-Enden, wie bisher
    # Top-Bar-Y-Bereich (für späteren Helper in Task 6):
    top_bar_y_low = by1 - margin - p.top_bar_height
    top_bar_y_high = by1 - margin

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
        f"; speed_print={p.speed_print} accel={p.accel}",
        # Klipper-PRINT_START erhaelt die Temperaturen als Parameter und
        # uebernimmt das Heizen (Bett-Pre-Heat waehrend Homing/QGL etc.).
        _format_start(p),
        "G90",
        "M83",
        "G92 E0",
    ]

    # Beschleunigung als Test-Parameter setzen (Klipper-Idiom).
    # Mit accel=0 wird das übersprungen — dann gilt der Drucker-Default
    # bzw. was PRINT_START gesetzt hat.
    if p.accel > 0:
        out.append(
            f"SET_VELOCITY_LIMIT ACCEL={_fmt(p.accel)} "
            f"ACCEL_TO_DECEL={_fmt(p.accel / 2)}")

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
        # Top-Bar in jedem Layer (CV-Anker für orientation.py).
        out.extend(_top_bar_block(
            p, bx0 + margin, bx1 - margin,
            top_bar_y_low, top_bar_y_high,
            travel_to, print_f,
        ))
        # Anker-Marker links neben dem ersten Chevron.
        # x_left = Frame-Innenkante (bx0 + margin); y_center =
        # Chevron-Mitte (zwischen py0 und py0 + 2*dy).
        chevron_center_y = py0 + dy
        out.extend(_anchor_marker_block(
            p, bx0 + margin, chevron_center_y,
            travel_to, print_f,
        ))
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

        # Labels nur in oberster Layer (sitzen als Relief auf der Top-Bar).
        if layer == p.num_layers - 1:
            # Label-Y-Top = obere Top-Bar-Innenkante (oben in der Bar,
            # Labels laufen nach unten in die Bar hinein).
            label_y_top = top_bar_y_high - 0.5  # 0.5 mm Padding zum oberen Rand
            out.extend(_pa_labels_block(
                p, pa_values, px0, label_y_top, adv,
            ))

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
