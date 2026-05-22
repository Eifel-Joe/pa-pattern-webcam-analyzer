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


# ── Geometrie-Toleranzen ──────────────────────────────────────────────
_EPS = 1e-4          # Punkt-Gleichheit (Koordinaten haben max. 4 Nachkommast.)
_X_RETURN_TOL = 1.0  # max. X-Differenz zwischen Chevron-Arm-Enden (mm)


def _close(p: Point, q: Point) -> bool:
    return abs(p.x - q.x) < _EPS and abs(p.y - q.y) < _EPS


def _chevron_from_run(
    seg1: tuple[Point, Point], seg2: tuple[Point, Point]
) -> Chevron | None:
    """Bildet aus zwei aufeinanderfolgenden Segmenten ein ">"-Chevron.

    Gibt None zurück, wenn die Segmente kein gültiges Chevron bilden
    (so werden Rahmen-Box-Linien und Füll-Striche aussortiert). Kriterien:
    Segment 2 setzt am Ende von Segment 1 an; der gemeinsame Punkt (Apex)
    hat das größte X; die äußeren Enden liegen auf gleicher X-Spalte.
    """
    a, b = seg1
    b2, c = seg2
    if not _close(b, b2):
        return None
    apex = b
    if not (apex.x > a.x and apex.x > c.x):
        return None
    if abs(a.x - c.x) > _X_RETURN_TOL:
        return None
    return Chevron(start=a, apex=apex, end=c)


def _parse_groups(gcode_text: str) -> list[tuple[float, tuple[Chevron, ...]]]:
    """Liefert (pa_wert, chevrons) je echter Gruppe, in Datei-Reihenfolge.

    Ein "Run" ist eine Folge konsekutiver extrudierender Moves; ein
    Travel-Move beendet ihn. Genau ein Run der Länge 2, der das
    Chevron-Kriterium erfüllt, ergibt einen Chevron.
    """
    raw: list[tuple[float, tuple[Chevron, ...]]] = []
    cur_pa: float | None = None
    chevrons: list[Chevron] = []
    run: list[tuple[Point, Point]] = []
    pos = Point(0.0, 0.0)

    def finish_run() -> None:
        if len(run) == 2:
            ch = _chevron_from_run(run[0], run[1])
            if ch is not None:
                chevrons.append(ch)
        run.clear()

    def finish_group() -> None:
        if cur_pa is not None and chevrons:
            raw.append((cur_pa, tuple(chevrons)))
        chevrons.clear()

    for kind, val in _tokenize(gcode_text):
        if kind == "pa":
            finish_run()
            finish_group()
            cur_pa = val  # type: ignore[assignment]
            continue
        move: _Move = val  # type: ignore[assignment]
        start, end = pos, Point(move.x, move.y)
        pos = end
        if move.extruding:
            run.append((start, end))
        else:
            finish_run()
    finish_run()
    finish_group()
    return raw


def _dedupe_by_pa(
    raw: list[tuple[float, tuple[Chevron, ...]]],
) -> list[PaGroup]:
    """Behält je PA-Wert die erste Begegnung (= erster Layer) und
    sortiert die Gruppen aufsteigend nach PA-Wert."""
    seen: dict[float, PaGroup] = {}
    for pa, chevrons in raw:
        key = round(pa, 6)
        if key not in seen:
            seen[key] = PaGroup(pa_value=pa, chevrons=chevrons)
    return [seen[k] for k in sorted(seen)]


def parse(gcode_text: str) -> PatternModel:
    """Parst PA-Pattern-GCode in ein PatternModel."""
    groups = _dedupe_by_pa(_parse_groups(gcode_text))
    return PatternModel(groups=tuple(groups), frame_box=None)
