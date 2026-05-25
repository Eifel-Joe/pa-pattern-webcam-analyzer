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
    pa_end: float = 0.04
    pa_step: float = 0.005
    wall_count: int = 3
    # v4 (2026-05-25): wall_side_length 8→30, pattern_spacing 6→18, pa_step
    # → 0.005 in 0..0.04-Range (9 Werte). v3 (wall_side=8) konnte den
    # Drucker bei realer Druckgeschwindigkeit (180 mm/s + 3000 mm/s²)
    # nicht auf volle Geschwindigkeit beschleunigen — Beschleunigungs-
    # Distanz 180²/3000=10.8mm > halbe Arm-Länge 4mm → PA-Effekt nicht
    # messbar. v4 hat wieder lange Arme (30 mm wie v2) damit der Drucker
    # die volle Druckgeschwindigkeit erreicht, aber weiteren Apex-Abstand
    # (~20 mm group_advance) und kleinere PA-Range (0..0.04, typischer
    # Direct-Drive-Bereich). pa_end via CLI/Macro überschreibbar.
    # Pattern-Größe ~182×54 mm, passt auf Bett >= 200 mm. Orca-Stil
    # PA-Pattern mit klar getrennten Chevrons.
    wall_side_length: float = 30.0
    corner_angle: float = 90.0
    pattern_spacing: float = 18.0
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
    # Pattern-Markierungen (v2: deutlich größer für Webcam-Lesbarkeit)
    top_bar_height: float = 12.0        # mm Vollfüllung-Höhe (v2: 4 → 12)
    chevron_band_gap: float = 0.0       # mm Trennzone Top-Bar/Chevrons (v2: 1 → 0, berührt Chevrons)
    anchor_marker_width: float = 2.0    # mm horizontal
    anchor_marker_height: float = 8.0   # mm vertikal
    label_glyph_height: float = 2.5     # mm PA-Label-Glyph (v2: 0.7 → 2.5)
    label_glyph_width: float = 1.5      # mm (v2: 0.5 → 1.5)
    label_glyph_gap: float = 0.2        # mm zwischen Glyphen
    label_stride: int = 2               # nur jeden N-ten PA-Wert beschriften
                                        # (v2.1: 1 → 2; Zwischenwerte ergeben
                                        # sich kontextual, mehr Platz pro Label)
    header_glyph_height: float = 4.0    # mm Speed/Accel-Header (v2: 1.0 → 4.0)
    header_glyph_width: float = 2.5     # mm (v2: 0.7 → 2.5)
    header_column_spacing: float = 4.0  # mm zwischen Speed- und Accel-Spalte
    header_to_labels_gap: float = 3.0   # mm Header-Trennung zu PA-Labels

    # Beschleunigung (neu)
    accel: float = 2000.0               # mm/s² (0 = nicht emittieren)
    # Sicherheits-Reduzierung für die erste Layer — bessere Bett-Haftung.
    # Wird für Frame, Top-Bar, Anker und Chevrons in Layer 1 (= layer==0)
    # angewendet; ab Layer 2 (= layer==1) gelten speed_print/accel.
    # 0 = keine Reduzierung (Drucker-Default bzw. speed_print/accel).
    first_layer_speed: float = 50.0     # mm/s
    first_layer_accel: float = 500.0    # mm/s²

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


def _draw_box(
    p: GeneratorParams,
    x0: float, y0: float, width: float, height: float,
    n_perimeters: int,
    is_filled: bool,
    travel_to_fn,
    print_f: int,
) -> list[str]:
    """Zeichnet eine Box mit n_perimeters umlaufenden Wandlinien
    (optional + 45°-Infill innen). Reproduziert Orca's draw_box-
    Funktion (siehe reference/orca_calib.cpp Linie 261).

    Perimeter-Reihenfolge pro Wand: up → right → down → left.
    Zwischen Perimetern: Travel-Move "step inwards" um line_spacing.

    NOT-TO-DO: Statt Step-inwards die nächste Perimeter zu starten
    mit Off-by-one in Y. Orca's Logik ist klar — wir halten uns
    streng daran (line_spacing in BEIDE Achsen je Perimeter).
    """
    lw = _line_width(p)
    # line_spacing = lw - h*(1 - π/4) — übernommen aus Orca (Linie 270)
    line_spacing = lw - p.layer_height * (1 - math.pi / 4)

    out: list[str] = []
    out.extend(travel_to_fn(x0, y0))

    x, y = x0, y0
    for i in range(n_perimeters):
        if i > 0:
            x += line_spacing
            y += line_spacing
            # Step-inwards als Travel (kein E)
            out.append(f"G1 X{_fmt(x)} Y{_fmt(y)} F7200")
        # Aktuelle Box-Größe für diesen Perimeter
        cur_w = width - 2 * i * line_spacing
        cur_h = height - 2 * i * line_spacing
        e_v = _extrusion(cur_h, lw, p.layer_height,
                         p.filament_diameter, p.extrusion_multiplier)
        e_h = _extrusion(cur_w, lw, p.layer_height,
                         p.filament_diameter, p.extrusion_multiplier)
        # up: Y +cur_h
        y += cur_h
        out.append(f"G1 X{_fmt(x)} Y{_fmt(y)} E{_fmt_e(e_v)} F{print_f}")
        # right: X +cur_w
        x += cur_w
        out.append(f"G1 X{_fmt(x)} Y{_fmt(y)} E{_fmt_e(e_h)} F{print_f}")
        # down: Y -cur_h
        y -= cur_h
        out.append(f"G1 X{_fmt(x)} Y{_fmt(y)} E{_fmt_e(e_v)} F{print_f}")
        # left: X -cur_w
        x -= cur_w
        out.append(f"G1 X{_fmt(x)} Y{_fmt(y)} E{_fmt_e(e_h)} F{print_f}")

    if not is_filled:
        return out

    # 45°-Infill — direkte Übersetzung von Orca's draw_box Linie 316-460.
    # spacing_45 = line_spacing / sin(45°): Infill-Linien-Abstand entlang
    # der Diagonale. m_encroachment = 0.45 (aus Orca-Default), wie weit
    # Infill in die innerste Perimeter hineinläuft.
    m_encroachment = 0.45
    spacing_45 = line_spacing / math.sin(math.pi / 4)
    bound_modifier = (line_spacing * (n_perimeters - 1)
                      + lw * (1 - m_encroachment))
    x_min = x0 + bound_modifier
    x_max = x0 + width - bound_modifier
    y_min = y0 + bound_modifier
    y_max = y0 + height - bound_modifier
    x_count = int(math.floor((x_max - x_min) / spacing_45))
    y_count = int(math.floor((y_max - y_min) / spacing_45))
    x_remainder = (x_max - x_min) % spacing_45
    y_remainder = (y_max - y_min) % spacing_45

    x, y = x_min, y_min
    # Fill-Start (Travel)
    out.append(f"G1 X{_fmt(x)} Y{_fmt(y)} F7200  ; Fill: Move to fill start")

    n_iter = x_count + y_count + (
        1 if x_remainder + y_remainder >= spacing_45 else 0)
    for i in range(n_iter):
        if i < min(x_count, y_count):
            # Diagonalen die nicht den oberen/rechten Rand erreichen
            if i % 2 == 0:
                x += spacing_45
                y = y_min
                out.append(f"G1 X{_fmt(x)} Y{_fmt(y)} F7200  ; Fill: Step right")
                # Print up/left zu (x_min, y + (x - x_min))
                new_y = y + (x - x_min)
                new_x = x_min
                e = _extrusion(
                    math.hypot(new_x - x, new_y - y), lw, p.layer_height,
                    p.filament_diameter, p.extrusion_multiplier)
                x, y = new_x, new_y
                out.append(f"G1 X{_fmt(x)} Y{_fmt(y)} E{_fmt_e(e)} "
                           f"F{print_f}  ; Fill: Print up/left")
            else:
                y += spacing_45
                x = x_min
                out.append(f"G1 X{_fmt(x)} Y{_fmt(y)} F7200  ; Fill: Step up")
                # Print down/right zu (x + (y - y_min), y_min)
                new_x = x + (y - y_min)
                new_y = y_min
                e = _extrusion(
                    math.hypot(new_x - x, new_y - y), lw, p.layer_height,
                    p.filament_diameter, p.extrusion_multiplier)
                x, y = new_x, new_y
                out.append(f"G1 X{_fmt(x)} Y{_fmt(y)} E{_fmt_e(e)} "
                           f"F{print_f}  ; Fill: Print down/right")
        elif i < max(x_count, y_count):
            # Boxes wider than tall OR taller than wide — Diagonalen
            # die einen Rand erreichen aber nicht den anderen
            if x_count > y_count:
                if i % 2 == 0:
                    x += spacing_45
                    y = y_min
                    out.append(f"G1 X{_fmt(x)} Y{_fmt(y)} F7200  ; Fill: Step right")
                    new_x = x - (y_max - y_min)
                    new_y = y_max
                    e = _extrusion(
                        math.hypot(new_x - x, new_y - y), lw, p.layer_height,
                        p.filament_diameter, p.extrusion_multiplier)
                    x, y = new_x, new_y
                    out.append(f"G1 X{_fmt(x)} Y{_fmt(y)} E{_fmt_e(e)} "
                               f"F{print_f}  ; Fill: Print up/left")
                else:
                    if i == y_count:
                        x += spacing_45 - y_remainder
                        y_remainder = 0
                    else:
                        x += spacing_45
                    y = y_max
                    out.append(f"G1 X{_fmt(x)} Y{_fmt(y)} F7200  ; Fill: Step right")
                    new_x = x + (y_max - y_min)
                    new_y = y_min
                    e = _extrusion(
                        math.hypot(new_x - x, new_y - y), lw, p.layer_height,
                        p.filament_diameter, p.extrusion_multiplier)
                    x, y = new_x, new_y
                    out.append(f"G1 X{_fmt(x)} Y{_fmt(y)} E{_fmt_e(e)} "
                               f"F{print_f}  ; Fill: Print down/right")
            else:
                # box taller than wide — analog spiegelverkehrt
                # (in unserem Use-Case Top-Bar ist x_count > y_count
                # weil 84 mm × 13 mm; daher kein concrete Fall — aber
                # für draw_box-Vollständigkeit drin)
                if i % 2 == 0:
                    y += spacing_45
                    x = x_min
                    out.append(f"G1 X{_fmt(x)} Y{_fmt(y)} F7200  ; Fill: Step up")
                    new_y = y - (x_max - x_min)
                    new_x = x_max
                    e = _extrusion(
                        math.hypot(new_x - x, new_y - y), lw, p.layer_height,
                        p.filament_diameter, p.extrusion_multiplier)
                    x, y = new_x, new_y
                    out.append(f"G1 X{_fmt(x)} Y{_fmt(y)} E{_fmt_e(e)} "
                               f"F{print_f}  ; Fill: Print down/right")
                else:
                    if i == x_count:
                        y += spacing_45 - x_remainder
                        x_remainder = 0
                    else:
                        y += spacing_45
                    x = x_max
                    out.append(f"G1 X{_fmt(x)} Y{_fmt(y)} F7200  ; Fill: Step up")
                    new_y = y + (x_max - x_min)
                    new_x = x_min
                    e = _extrusion(
                        math.hypot(new_x - x, new_y - y), lw, p.layer_height,
                        p.filament_diameter, p.extrusion_multiplier)
                    x, y = new_x, new_y
                    out.append(f"G1 X{_fmt(x)} Y{_fmt(y)} E{_fmt_e(e)} "
                               f"F{print_f}  ; Fill: Print up/left")
        else:
            # Letzte Iteration für x_remainder + y_remainder >= spacing_45
            # (kleine Eck-Diagonale) — vereinfacht: skip wenn beide 0
            if x_remainder == 0 and y_remainder == 0:
                continue
            # Wir lassen diese Edge-Case-Diagonale weg — minimaler
            # Footprint-Unterschied, kein Druck-Defekt.

    return out


# _top_bar_block entfernt 2026-05-25 — ersetzt durch _draw_box(is_filled=True) (Task 5)


# _anchor_marker_block entfernt 2026-05-25 — Orca-Stil verwendet keinen
# separaten Asymmetrie-Anker; die Top-Bar oben reicht für orientation.py (Task 8)


def _pa_labels_block(
    p: GeneratorParams, pa_values: list[float], px0: float,
    label_y_top: float, group_advance: float,
    print_speed: float | None = None,
) -> list[str]:
    """Hochkant rotierte PA-Labels auf der Top-Bar.

    Position pro Label: Label-Start-X = Chevron-Wall-Cluster-Mitte
    minus halbe Glyph-Höhe (= Orca's glyph_start_x-Logik, siehe
    reference/orca_calib.cpp Linie 821-844). Damit sitzt das Label
    über dem Anker-Punkt am Frame, NICHT über der weiter nach
    rechts ausladenden Chevron-Spitze.

    NOT-TO-DO: Label über Chevron-Tip-Mitte zentrieren (= alte
    Implementation mit `+ dx` im Offset). User-Anforderung
    2026-05-25 explizit: "an den Ankerpunkt am Frame, damit man
    es überhaupt zuordnen könnte". Mittellage über Tip führte
    dazu dass die visuelle Zuordnung Label↔Chevron unklar war
    (Labels überlappten teilweise mit Nachbar-Chevrons).
    """
    out: list[str] = []
    wall_off = _wall_x_offset(p)
    speed = print_speed if print_speed is not None else p.speed_print
    for j, pa in enumerate(pa_values):
        if j % p.label_stride != 0:
            continue
        # glyph_start_x(j) = px0 + j*group_advance
        #   + (wall_count-1)*wall_off/2 - glyph_len_x/2
        # Entspricht Orca's Logik: Label über Wall-Cluster-Mitte,
        # nicht über der Chevron-Tip-Mitte (die um dx/2 weiter rechts
        # läge). Siehe reference/orca_calib.cpp Linie 821-844.
        x_start = (px0 + j * group_advance
                   + (p.wall_count - 1) * wall_off / 2
                   - p.label_glyph_height / 2)
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
            print_speed=speed,
            travel_speed=p.speed_travel,
            rotation=90,
        ))
    return out


# _header_labels_block entfernt 2026-05-25 — ersetzt durch inline Flow/Accel-Slots in generate() Layer 1 (Task 7)


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
    first_layer_print_f = round(p.first_layer_speed * 60)
    travel_f = round(p.speed_travel * 60)
    purge_f = round(p.purge_speed * 60)
    retract = _retract_block(p)
    unretract = _unretract_block(p)

    # Pattern-Abmessungen und Bett-Zentrierung (v2: margin=0 + left_padding)
    chevron_h = 2 * dy
    pattern_w = (
        (len(pa_values) - 1) * adv + (p.wall_count - 1) * wall_off + dx
    )
    pattern_h = p.top_bar_height + p.chevron_band_gap + chevron_h
    margin = 0.0  # Frame berührt Pattern direkt (kein Luftspalt)
    # pattern_shift: X-Versatz vom Frame-Links-Rand bis zum ersten
    # Chevron-Arm-Start. Macht Platz für die Frame-Perimeter-Wandstärke
    # (wall_count-1) * line_spacing) PLUS Nozzle-Linienbreite PLUS
    # horizontales Padding (~0.5 mm) für saubere Label-Ausrichtung.
    # Reproduziert Orca's pattern_shift() (orca_calib.cpp Linie 893).
    line_spacing = lw - p.layer_height * (1 - math.pi / 4)
    glyph_padding_horizontal = 0.5
    pattern_shift = ((p.wall_count - 1) * line_spacing
                     + lw + glyph_padding_horizontal)
    # Settings-Extent: tight spacing für Flow (+ optional Accel) rechts
    # nach den PA-Labels. Frame muss so weit reichen, dass die Settings
    # AUF der Top-Bar liegen, nicht in leeres Bett-Areal.
    # Bug (Task 9 Render): glyph_start_x(num_patterns + 2/+4) mit
    # group_advance ~18mm schiebt Settings ~70mm rechts vom Frame.
    # Fix: settings nutzen label_glyph_height + 1.5mm tight spacing,
    # Frame total_w wird um settings_extent erweitert.
    settings_gap = 5.0  # mm Abstand letztes PA-Label → erstes Settings-Label
    settings_spacing = p.label_glyph_height + 1.5
    n_settings = 2 if p.accel > 0 else 1
    settings_extent = settings_gap + n_settings * settings_spacing + 1.0
    total_w = pattern_w + pattern_shift + settings_extent
    bx0 = p.bed_x / 2 - (total_w + 2 * margin) / 2
    by0 = p.bed_y / 2 - (pattern_h + 2 * margin) / 2
    bx1 = bx0 + total_w + 2 * margin
    by1 = by0 + pattern_h + 2 * margin
    px0 = bx0 + margin + pattern_shift      # Chevron-Start nach Frame-Wand-Padding
    py0 = by0 + margin                     # Chevron-Bottom
    # Top-Bar-Y-Bereich (y_high wird nicht mehr separat berechnet —
    # tb_height wird in der Layer-Schleife aus top_bar_height - line_spacing ermittelt):
    top_bar_y_low = by1 - margin - p.top_bar_height

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

    # First-Layer-Sicherheit: reduzierte Beschleunigung für bessere
    # Bett-Haftung. Wird in Layer 1 (= layer==0) für Frame, Top-Bar,
    # Anker und Chevrons verwendet. Ab Layer 2 (= layer==1) switcht
    # SET_VELOCITY_LIMIT zurück auf p.accel.
    # first_layer_accel=0 → kein Set, Drucker-Default für Layer 1.
    if p.first_layer_accel > 0:
        out.append(
            f"SET_VELOCITY_LIMIT ACCEL={_fmt(p.first_layer_accel)} "
            f"ACCEL_TO_DECEL={_fmt(p.first_layer_accel / 2)}")

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

    # Frame-Box-Marker als Kommentar — Parser nutzt diese, da auch ein
    # 3-Perimeter-Frame im GCode als viele Linien erscheint.
    out.append(
        f"; PA_ANALYZER_FRAME X0={_fmt(bx0)} Y0={_fmt(by0)} "
        f"X1={_fmt(bx1)} Y1={_fmt(by1)}")
    # Frame als 3-Perimeter umlaufender Rahmen (Orca-Stil), ohne Infill.
    # Höhe = nur bis Top-Bar-Bottom; Top-Bar wird separat als zweite
    # Box gezeichnet (Task 5). Wird in Layer 0 mit first_layer_print_f
    # gedruckt für Bett-Haftung.
    out.extend(_draw_box(
        p, bx0, by0,
        width=bx1 - bx0, height=top_bar_y_low - by0,
        n_perimeters=p.wall_count, is_filled=False,
        travel_to_fn=travel_to, print_f=first_layer_print_f,
    ))

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
        # Layer-spezifische Druck-Geschwindigkeit:
        # Layer 0 (= erste Layer): first_layer_print_f (Bett-Haftung).
        # Layer >=1: print_f (normale Test-Geschwindigkeit).
        layer_print_f = first_layer_print_f if layer == 0 else print_f
        # Nach Layer 0: Beschleunigung von first_layer_accel auf p.accel
        # umstellen (sofern p.accel > 0; sonst bleibt first_layer_accel
        # bzw. der Drucker-Default).
        if layer == 1 and p.accel > 0:
            out.append(
                f"SET_VELOCITY_LIMIT ACCEL={_fmt(p.accel)} "
                f"ACCEL_TO_DECEL={_fmt(p.accel / 2)}")
        # Lüfter nach Layer 1 auf den normalen Wert umschalten
        if layer == 1 and p.fan_speed != p.fan_speed_layer1:
            out.append(f"M106 S{round(p.fan_speed * 255)}")
        # Top-Bar NUR in Layer 0 (Orca-Stil): 3 Perimeter + 45°-Infill,
        # mit ~0.5 mm Lücke (=line_spacing) zwischen Frame-Top (=
        # top_bar_y_low) und Top-Bar-Bottom — das verhindert
        # Verschmelzung der Wände beider Boxen im Slicer-Output.
        if layer == 0:
            line_spacing = (
                _line_width(p) - p.layer_height * (1 - math.pi / 4))
            tb_y0_gapped = top_bar_y_low + line_spacing
            tb_height = p.top_bar_height - line_spacing
            out.extend(_draw_box(
                p, bx0, tb_y0_gapped,
                width=bx1 - bx0, height=tb_height,
                n_perimeters=p.wall_count, is_filled=True,
                travel_to_fn=travel_to, print_f=layer_print_f,
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
                    f"E{_fmt_e(e_arm)} F{layer_print_f}"
                )
                # Arm 2: Apex -> End
                out.append(
                    f"G1 X{_fmt(sx)} Y{_fmt(py0 + 2 * dy)} "
                    f"E{_fmt_e(e_arm)} F{layer_print_f}"
                )

        # Labels in Layer 1 (Orca-Stil): Relief auf der einlagigen
        # Top-Bar. PA=0 explizit setzen, mit first_layer_speed drucken.
        # Settings (Flow, Accel) folgen NACH den PA-Labels — auf
        # zusätzlichen Glyph-Slots auf der gleichen Top-Bar.
        if layer == 1:
            out.append(f"{set_pa_prefix}0")
            label_y_top = (by1 - margin) - 0.5  # 0.5 mm Padding oben
            label_speed = p.first_layer_speed
            # 1) PA-Labels (über jedem Chevron-Anker)
            out.extend(_pa_labels_block(
                p, pa_values, px0, label_y_top, adv,
                print_speed=label_speed,
            ))
            # 2) Settings (Flow + Accel) NACH den PA-Labels —
            #    tight spacing statt Orca's glyph_start_x(num_patterns + 2/+4).
            #    Orca's Slot-Formel skaliert nicht mit unserer wide group_advance
            #    (~18mm) → Settings landen ~70mm rechts vom Frame (Task 9 Bug).
            #    Fix: settings_gap=5mm nach letztem PA-Label, dann tight spacing
            #    label_glyph_height + 1.5mm. Frame total_w wurde bereits
            #    um settings_extent erweitert (siehe pattern_shift-Block oben).
            num_patterns = len(pa_values)
            settings_gap_local = 5.0
            settings_spacing_local = p.label_glyph_height + 1.5
            flow_x = px0 + num_patterns * adv + settings_gap_local
            accel_x = flow_x + settings_spacing_local
            flow_value = p.extrusion_multiplier * 100  # als Prozent
            out.extend(render_label_gcode(
                text=_fmt(flow_value),
                x=flow_x, y=label_y_top,
                glyph_height=p.label_glyph_height,
                glyph_width=p.label_glyph_width,
                glyph_gap=p.label_glyph_gap,
                line_width=_line_width(p),
                layer_height=p.layer_height,
                filament_diameter=p.filament_diameter,
                extrusion_multiplier=p.extrusion_multiplier,
                print_speed=label_speed,
                travel_speed=p.speed_travel,
                rotation=90,
            ))
            if p.accel > 0:
                out.extend(render_label_gcode(
                    text=_fmt(p.accel),
                    x=accel_x, y=label_y_top,
                    glyph_height=p.label_glyph_height,
                    glyph_width=p.label_glyph_width,
                    glyph_gap=p.label_glyph_gap,
                    line_width=_line_width(p),
                    layer_height=p.layer_height,
                    filament_diameter=p.filament_diameter,
                    extrusion_multiplier=p.extrusion_multiplier,
                    print_speed=label_speed,
                    travel_speed=p.speed_travel,
                    rotation=90,
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
