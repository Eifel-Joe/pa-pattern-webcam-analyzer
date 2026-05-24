"""Stroke-Font für Pattern-Labels (PA-Werte, Speed/Accel-Header).

Glyphen sind als Liste von Strokes definiert; jeder Stroke ist eine
Polyline aus (x, y)-Punkten in normierten Koordinaten [0, 1].
Mehrere Strokes = Pen-Up dazwischen (im GCode: Retract + Travel +
De-Retract).

Skalierung auf reale Maße passiert in `render_label_gcode` über
glyph_width / glyph_height. Die Glyphen sind so designed, dass sie
auch bei kleinen Maßen (~0.7 mm Höhe) gedruckt lesbar bleiben.
"""
from __future__ import annotations
import math

# Glyph-Definitionen. Y-Achse zeigt nach oben (0 = unten, 1 = oben),
# X-Achse nach rechts. Das wird im Renderer auf Druckbett-Koordinaten
# umgesetzt (Y nach oben = positives Y in mm).

GLYPHS: dict[str, list[list[tuple[float, float]]]] = {
    "0": [[(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]],
    "1": [[(0.5, 0), (0.5, 1)]],
    "2": [[(0, 1), (1, 1), (1, 0.5), (0, 0.5), (0, 0), (1, 0)]],
    "3": [[(0, 1), (1, 1), (1, 0), (0, 0)],
          [(0, 0.5), (1, 0.5)]],
    "4": [[(0, 1), (0, 0.5), (1, 0.5)],
          [(1, 1), (1, 0)]],
    "5": [[(1, 1), (0, 1), (0, 0.5), (1, 0.5), (1, 0), (0, 0)]],
    "6": [[(1, 1), (0, 1), (0, 0), (1, 0), (1, 0.5), (0, 0.5)]],
    "7": [[(0, 1), (1, 1), (1, 0)]],
    "8": [[(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)],
          [(0, 0.5), (1, 0.5)]],
    "9": [[(0, 0), (1, 0), (1, 1), (0, 1), (0, 0.5), (1, 0.5)]],
    ".": [[(0.4, 0), (0.6, 0)]],
}


def _extrusion_for_segment(
    length: float, line_width: float, layer_height: float,
    filament_diameter: float, extrusion_multiplier: float,
) -> float:
    """E-Wert für eine extrudierende Bewegung (Stadion-Querschnitt).

    Identisch zur Formel in gcode_generator._extrusion — hier dupliziert,
    weil glyphs.py keine Abhängigkeit auf gcode_generator haben soll
    (umgekehrt würde Generator glyphs importieren).
    """
    ext_area = ((line_width - layer_height) * layer_height
                + math.pi * (layer_height / 2) ** 2)
    fil_area = math.pi * (filament_diameter / 2) ** 2
    return round(length * ext_area / fil_area * extrusion_multiplier, 5)


def _fmt(v: float) -> str:
    """Koordinate mit bis zu 4 Nachkommastellen, keine überflüssigen Nullen."""
    return f"{round(v, 4):g}"


def _fmt_e(v: float) -> str:
    """E-Wert mit bis zu 5 Nachkommastellen."""
    return f"{round(v, 5):g}"


def render_label_gcode(
    text: str, x: float, y: float,
    glyph_height: float, glyph_width: float, glyph_gap: float,
    line_width: float, layer_height: float,
    filament_diameter: float, extrusion_multiplier: float,
    print_speed: float, travel_speed: float,
    rotation: int = 0,
) -> list[str]:
    """Rendert `text` als GCode-Zeilen (G1-Bewegungen).

    Position (`x`, `y`) ist die linke untere Ecke der ersten Glyphe in
    mm (Druckbett-Koordinaten). Bei `rotation=0` läuft der Text nach
    rechts; bei `rotation=90` läuft er nach unten (siehe Task 3).

    Zwischen Strokes innerhalb einer Glyphe wird Travel ohne Extrusion
    gemacht (Pen-Up). Retract wird in dieser Funktion bewusst nicht
    emittiert, weil die Aufrufer-Seite (Generator) ihren eigenen
    Retract-Block hat und doppeltes Retract Stringing nicht zusätzlich
    verhindert. Falls in der Praxis Stringing auftritt: Retract-Logik
    via TODO einbauen.
    """
    if rotation not in (0, 90):
        raise ValueError(
            f"rotation={rotation} nicht unterstützt (nur 0 oder 90).")
    out: list[str] = []
    print_f = round(print_speed * 60)
    travel_f = round(travel_speed * 60)
    # Cursor: linke untere Ecke der aktuellen Glyphe in mm.
    cursor_x = x
    cursor_y = y
    for ziffer in text:
        if ziffer not in GLYPHS:
            raise ValueError(f"Glyph '{ziffer}' nicht in GLYPHS.")
        for stroke in GLYPHS[ziffer]:
            # Stroke-Punkte auf Druckbett-Koordinaten skalieren und
            # ggf. um 90° im Uhrzeigersinn rotieren (Lese-Richtung
            # von oben nach unten).
            if rotation == 0:
                punkte = [
                    (cursor_x + px * glyph_width,
                     cursor_y + py * glyph_height)
                    for (px, py) in stroke
                ]
            else:  # rotation == 90
                # (x_g, y_g) → (x_g_neu, y_g_neu) = (y_g, -x_g)
                # Anschließend Skalierung: Original x_g läuft bis
                # glyph_width, Original y_g bis glyph_height. Nach
                # Rotation: x läuft jetzt bis glyph_height, y nach
                # unten bis -glyph_width.
                punkte = [
                    (cursor_x + py * glyph_height,
                     cursor_y - px * glyph_width)
                    for (px, py) in stroke
                ]
            # Travel zum Stroke-Anfang (ohne E).
            sx, sy = punkte[0]
            out.append(f"G1 X{_fmt(sx)} Y{_fmt(sy)} F{travel_f}")
            # Extrudierte Moves zu allen weiteren Punkten.
            prev_x, prev_y = sx, sy
            for (px, py) in punkte[1:]:
                length = math.hypot(px - prev_x, py - prev_y)
                e = _extrusion_for_segment(
                    length, line_width, layer_height,
                    filament_diameter, extrusion_multiplier)
                out.append(
                    f"G1 X{_fmt(px)} Y{_fmt(py)} "
                    f"E{_fmt_e(e)} F{print_f}")
                prev_x, prev_y = px, py
        # Cursor um glyph_width + glyph_gap weiter:
        # bei rotation=0 nach rechts (+X), bei rotation=90 nach unten (-Y).
        if rotation == 0:
            cursor_x += glyph_width + glyph_gap
        else:
            cursor_y -= glyph_width + glyph_gap
    return out
