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

    Modus-bewusst: G90/G91 schalten zwischen absoluter und relativer
    XY-Positionierung, M82/M83 zwischen absoluter und relativer Extrusion;
    `G92 E<wert>` setzt den Extruder-Origin. Defaults sind G90/M83 — der
    von diesem Projekt erzeugte GCode nutzt genau diese Modi, daher bleibt
    sein Parsing unverändert.

    Zeilen ohne XY-Änderung (Retract, reine F-Zeilen) erzeugen kein
    move-Token.
    """
    cur_x = 0.0
    cur_y = 0.0
    prev_e = 0.0
    abs_xy = True   # G90
    abs_e = False   # M83
    for raw in gcode_text.splitlines():
        # GCode-Kommentar entfernen, damit Achsen-Regexes keine Werte
        # aus Kommentartext aufgreifen (z.B. "; X123" wäre sonst ein Treffer).
        line = raw.split(";", 1)[0].strip()
        if not line:
            continue
        word = line.split()[0].upper()
        if word == "G90":
            abs_xy = True
            continue
        if word == "G91":
            abs_xy = False
            continue
        if word == "M82":
            abs_e = True
            continue
        if word == "M83":
            abs_e = False
            continue
        if word == "G92":
            me = _AXIS_RE["e"].search(line)
            if me:
                prev_e = float(me.group(1))
            continue
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
            val = float(mx.group(1))
            cur_x = val if abs_xy else cur_x + val
        if my:
            val = float(my.group(1))
            cur_y = val if abs_xy else cur_y + val
        extruding = False
        if me:
            e_val = float(me.group(1))
            if abs_e:
                # Absolute Extrusion: nur ein positives Delta zur vorigen
                # E-Position ist echte Extrusion (ein Retract hat E < prev).
                extruding = (e_val - prev_e) > 0
                prev_e = e_val
            else:
                extruding = e_val > 0
        if mx or my:
            yield ("move", _Move(cur_x, cur_y, extruding))


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
        # Ein Chevron besteht aus genau 2 Segmenten; kürzere oder längere
        # Runs (z.B. die Rahmen-Box mit 4 Segmenten) sind keine Chevrons.
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


def _axis_parallel(seg: tuple[Point, Point]) -> bool:
    s, e = seg
    return abs(s.x - e.x) < _EPS or abs(s.y - e.y) < _EPS


def _rectangle_from_run(run: list[tuple[Point, Point]]) -> FrameBox | None:
    """Prüft, ob ein Run aus genau 4 Segmenten ein geschlossenes,
    achsenparalleles Rechteck bildet.

    Verlangt exakt 4 Segmente — so wird ein zufällig rechteckiges
    4er-Fenster aus einer langen Extrusion (z.B. Skirt) nicht als
    Rahmen-Box fehlerkannt.
    """
    if len(run) != 4:
        return None
    segs = run
    if not all(_axis_parallel(s) for s in segs):
        return None
    if not _close(segs[-1][1], segs[0][0]):  # geschlossen?
        return None
    corners = (segs[0][0], segs[1][0], segs[2][0], segs[3][0])
    xs = {round(c.x, 3) for c in corners}
    ys = {round(c.y, 3) for c in corners}
    if len(xs) != 2 or len(ys) != 2:  # echtes Rechteck mit Fläche?
        return None
    return FrameBox(corners=corners)


def _find_frame_box(gcode_text: str) -> FrameBox | None:
    """Findet die äußere Rahmen-Box: das erste geschlossene,
    achsenparallele Rechteck aus 4 konsekutiven extrudierenden Moves."""
    pos = Point(0.0, 0.0)
    run: list[tuple[Point, Point]] = []
    for kind, val in _tokenize(gcode_text):
        if kind == "pa":
            run.clear()
            continue
        move: _Move = val  # type: ignore[assignment]
        start, end = pos, Point(move.x, move.y)
        pos = end
        if move.extruding:
            run.append((start, end))
            box = _rectangle_from_run(run)
            if box is not None:
                return box
        else:
            run.clear()
    return None


def _content_bounds(gcode_text: str) -> tuple[Point, Point] | None:
    """Bounding-Box aller extrudierenden Move-Endpunkte (Rahmen-Box,
    Balken und Chevrons des Patterns)."""
    xs: list[float] = []
    ys: list[float] = []
    for kind, val in _tokenize(gcode_text):
        if kind == "move":
            move: _Move = val  # type: ignore[assignment]
            if move.extruding:
                xs.append(move.x)
                ys.append(move.y)
    if not xs:
        return None
    return Point(min(xs), min(ys)), Point(max(xs), max(ys))


def parse(gcode_text: str) -> PatternModel:
    """Parst PA-Pattern-GCode in ein PatternModel."""
    groups = _dedupe_by_pa(_parse_groups(gcode_text))
    frame_box = _find_frame_box(gcode_text)
    content_bounds = _content_bounds(gcode_text)
    return PatternModel(
        groups=tuple(groups),
        frame_box=frame_box,
        content_bounds=content_bounds,
    )
