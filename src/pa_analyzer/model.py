"""Datenmodell für das PA-Pattern.

Wird von gcode_parser (Erzeuger) und – ab Etappe 2 – vom Analyzer
(Verbraucher) geteilt. Alle Koordinaten in Bett-Millimetern.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    """Ein Punkt in Bett-Koordinaten (mm)."""

    x: float
    y: float


@dataclass(frozen=True)
class Chevron:
    """Ein einzelner Chevron in ">"-Form.

    Zwei Arme treffen sich am Apex (rechte Spitze). `start` und `end`
    sind die äußeren Arm-Enden, sie liegen auf gleicher X-Spalte.
    """

    start: Point
    apex: Point
    end: Point


@dataclass(frozen=True)
class PaGroup:
    """Eine PA-Gruppe: ein Pressure-Advance-Wert mit mehreren Chevrons."""

    pa_value: float
    chevrons: tuple[Chevron, ...]

    @property
    def apex(self) -> Point:
        """Mittlerer Apex über alle Chevrons der Gruppe."""
        n = len(self.chevrons)
        return Point(
            sum(c.apex.x for c in self.chevrons) / n,
            sum(c.apex.y for c in self.chevrons) / n,
        )


@dataclass(frozen=True)
class FrameBox:
    """Rechteckige Rahmen-Box um das Pattern, 4 Ecken in Bett-mm."""

    corners: tuple[Point, Point, Point, Point]


@dataclass(frozen=True)
class PatternModel:
    """Geparstes PA-Pattern: alle PA-Gruppen und (optional) die Rahmen-Box."""

    groups: tuple[PaGroup, ...]
    frame_box: FrameBox | None = None
