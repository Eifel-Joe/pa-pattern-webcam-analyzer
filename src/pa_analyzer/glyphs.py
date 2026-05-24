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
