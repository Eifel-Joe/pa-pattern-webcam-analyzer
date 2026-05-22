"""Parst PA-Pattern-GCode in ein PatternModel.

PA-Werte, Chevron-Anzahl und Geometrie werden ausschließlich aus dem
GCode gelesen — niemals hartcodiert (Spec §9). Funktioniert mit
generiertem wie mit extern (z.B. OrcaSlicer) erzeugtem GCode.
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from .model import Chevron, FrameBox, PaGroup, PatternModel, Point

# Zahl-Token: deckt "142", "124.538", ".88741", "-.8" ab.
_NUM = r"-?\d*\.?\d+"
_G1_RE = re.compile(r"^G1(?=\s)")
_AXIS_RE = {
    axis: re.compile(rf"(?:^|\s){axis.upper()}({_NUM})")
    for axis in ("x", "y", "e")
}
_PA_RE = re.compile(rf"^SET_PRESSURE_ADVANCE\b.*?\bADVANCE=({_NUM})")


@dataclass(frozen=True)
class _Move:
    """Eine G1-Bewegung mit absoluter End-Position."""

    x: float
    y: float
    extruding: bool  # True, wenn die Bewegung Material extrudiert (E > 0)


def _tokenize(gcode_text: str) -> Iterator[tuple[str, object]]:
    """Yieldet ('pa', wert: float) und ('move', _Move) in Datei-Reihenfolge.

    Der Pattern-GCode nutzt absolute XY-Koordinaten (G90); die Position
    wird über alle Zeilen hinweg fortgeschrieben. Zeilen ohne XY-Änderung
    (Retract, reine F-Zeilen) erzeugen kein move-Token.
    """
    cur_x = 0.0
    cur_y = 0.0
    for raw in gcode_text.splitlines():
        line = raw.strip()
        # GCode-Kommentar entfernen, damit Achsen-Regexes keine Werte
        # aus Kommentartext aufgreifen (z.B. "; X123" wäre sonst ein Treffer).
        line = line.split(";", 1)[0]
        pa = _PA_RE.match(line)
        if pa:
            yield ("pa", float(pa.group(1)))
            continue
        if not _G1_RE.match(line):
            continue
        mx = _AXIS_RE["x"].search(line)
        my = _AXIS_RE["y"].search(line)
        me = _AXIS_RE["e"].search(line)
        if mx:
            cur_x = float(mx.group(1))
        if my:
            cur_y = float(my.group(1))
        if mx or my:
            e_val = float(me.group(1)) if me else 0.0
            yield ("move", _Move(cur_x, cur_y, extruding=e_val > 0))
