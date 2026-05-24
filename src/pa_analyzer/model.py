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
    """Geparstes PA-Pattern: alle PA-Gruppen, die Rahmen-Box und die
    Bounding-Box der gesamten Druck-Geometrie.

    `chevron_band_top` ist die obere Y-Grenze der Chevron-Apexe (= unterer
    Rand der Top-Bar in v2-Geometrie). Wird von `orientation.py` als
    band-Berechnungs-Grenze genutzt, weil `frame_box.max_y` bei v2 die
    THEORETISCHE Frame-Outline meint (Marker `by1`) und nicht die echte
    extrudierte Pattern-Grenze — was zu negativem `band` führen würde.
    """

    groups: tuple[PaGroup, ...]
    frame_box: FrameBox | None = None
    content_bounds: tuple[Point, Point] | None = None
    chevron_band_top: float | None = None


@dataclass(frozen=True)
class AnalysisResult:
    """Ergebnis der Bild-Auswertung."""

    best_pa: float                          # interpoliertes Optimum
    nearest_step: float                     # nächster gedruckter PA-Wert
    confidence: float                       # 0..1
    scores: tuple[tuple[float, float], ...]  # (pa_value, score) je Gruppe
