# Etappe 1 — Grundgerüst, GCode-Parser & GCode-Generator — Implementierungsplan

> **Für agentische Umsetzung:** ERFORDERLICHES SUB-SKILL: `superpowers:subagent-driven-development` (empfohlen) oder `superpowers:executing-plans`, um diesen Plan Task für Task umzusetzen. Schritte nutzen Checkbox-Syntax (`- [ ]`) zur Fortschritts-Verfolgung.

**Ziel:** Die zwei reinen Logik-Module des PA-Pattern-Webcam-Analyzers bauen — `gcode_parser` (beliebiger PA-Pattern-GCode → `PatternModel`) und `gcode_generator` (Parameter → druckbarer Chevron-PA-Pattern-GCode) — plus Projekt-Grundgerüst.

**Architektur:** Reine Python-Logik ohne externe Abhängigkeiten (Spec §N4), damit trivial unit-testbar. Beide Module teilen das Datenmodell `model.py`. Der Parser ist die „niemals hardcoden"-Instanz (Spec §9): PA-Werte, Chevron-Anzahl und Geometrie kommen ausschließlich aus dem GCode. Generator und Parser werden gegeneinander per Round-Trip-Test validiert.

**Tech Stack:** Python 3.13, Standardbibliothek (`re`, `math`, `dataclasses`), `pytest`. Keine weiteren Abhängigkeiten in dieser Etappe.

**Referenz-Fakten** (aus der Analyse von `tests/fixtures/pa_pattern.gcode` und Ellis' `Pressure_Linear_Advance_Tool`):
- Die Fixture hat 4 Layer, 21 PA-Werte 0.010–0.050 (Schritt 0.002), je 3 Chevrons pro PA-Wert.
- Ein Chevron (`>`-Form) = 2 aufeinanderfolgende extrudierende `G1`-Moves; der Apex ist der gemeinsame Punkt mit dem größten X; die Arm-Enden (`start`, `end`) liegen auf gleicher X-Spalte.
- Echte Pattern-Gruppen werden von Setup-`SET_PRESSURE_ADVANCE`-Befehlen (Filament-Default, Rahmen-Box) dadurch unterschieden, dass ihnen ein gültiges Chevron-Muster folgt.
- Flow-Formel (Stadion-Querschnitt): `ext_area = (line_width − height)·height + π·(height/2)²`; `E = length · ext_area / fil_area · ext_mult`.

---

## Datei-Struktur

```
pa-pattern-webcam-analyzer/
├── pyproject.toml                  # Paket-Metadaten + pytest-Konfiguration   [Task 1]
├── src/
│   └── pa_analyzer/
│       ├── __init__.py             # leer (Paket-Marker)                       [Task 1]
│       ├── model.py                # Point, Chevron, PaGroup, FrameBox,        [Task 2]
│       │                           #   PatternModel
│       ├── gcode_parser.py         # parse(gcode_text) -> PatternModel    [Task 3,4,5]
│       └── gcode_generator.py      # generate(params) -> str              [Task 6,7,8]
├── tests/
│   ├── __init__.py                 # leer                                      [Task 1]
│   ├── conftest.py                 # Fixture-Pfad-Helfer                       [Task 1]
│   ├── fixtures/                   # existiert bereits (committed)
│   ├── test_smoke.py               # Grundgerüst-Smoke-Test                    [Task 1]
│   ├── test_model.py               # Datenmodell-Tests                         [Task 2]
│   ├── test_gcode_parser.py        # Parser-Tests                         [Task 3,4,5]
│   ├── test_gcode_generator.py     # Generator-Tests                      [Task 6,7,8]
│   └── test_roundtrip.py           # Generator→Parser-Konsistenz               [Task 9]
```

Jede Datei hat eine Verantwortung. `model.py` ist abhängigkeitsfrei und wird von beiden Logik-Modulen importiert. `gcode_parser.py` und `gcode_generator.py` kennen einander nicht — ihre Kopplung wird nur im Round-Trip-Test (Task 9) geprüft.

---

## Task 1: Projekt-Grundgerüst

**Files:**
- Create: `pyproject.toml`
- Create: `src/pa_analyzer/__init__.py` (leer)
- Create: `tests/__init__.py` (leer)
- Create: `tests/conftest.py`
- Test: `tests/test_smoke.py`

- [ ] **Schritt 1: `pyproject.toml` anlegen**

```toml
[project]
name = "pa-analyzer"
version = "0.1.0"
description = "Automatische Pressure-Advance-Kalibrierung eines Klipper-3D-Druckers per Webcam-Auswertung"
requires-python = ">=3.13"

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

Über `pythonpath = ["src"]` findet pytest das Paket ohne Installation (`pip install -e` nicht nötig).

- [ ] **Schritt 2: Leere Paket-/Test-Marker anlegen**

`src/pa_analyzer/__init__.py` — leere Datei.
`tests/__init__.py` — leere Datei.

- [ ] **Schritt 3: `tests/conftest.py` anlegen**

```python
"""Gemeinsame pytest-Fixtures."""
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def pa_pattern_gcode() -> str:
    """Roher Text des Beispiel-GCodes (OrcaSlicer-PA-Pattern, 4 Layer)."""
    return (FIXTURES_DIR / "pa_pattern.gcode").read_text(
        encoding="utf-8", errors="replace"
    )
```

- [ ] **Schritt 4: Smoke-Test schreiben** — `tests/test_smoke.py`

```python
def test_paket_importierbar():
    import pa_analyzer

    assert pa_analyzer is not None
```

- [ ] **Schritt 5: Test ausführen — muss zunächst grün sein (Grundgerüst-Check)**

Run: `python -m pytest tests/test_smoke.py -v`
Erwartet: PASS (1 Test). Falls FAIL: `pythonpath`/Paketstruktur prüfen.

- [ ] **Schritt 6: Commit**

```bash
git add pyproject.toml src/pa_analyzer/__init__.py tests/__init__.py tests/conftest.py tests/test_smoke.py
git commit -m "Projekt-Grundgeruest: pyproject, Paketstruktur, pytest-Setup"
```

---

## Task 2: Datenmodell (`model.py`)

**Files:**
- Create: `src/pa_analyzer/model.py`
- Test: `tests/test_model.py`

- [ ] **Schritt 1: Tests schreiben** — `tests/test_model.py`

```python
import pytest

from pa_analyzer.model import Chevron, FrameBox, PaGroup, PatternModel, Point


def test_point_ist_unveraenderlich():
    p = Point(1.0, 2.0)
    assert (p.x, p.y) == (1.0, 2.0)
    with pytest.raises(Exception):
        p.x = 9.0  # frozen dataclass


def test_chevron_haelt_drei_punkte():
    ch = Chevron(start=Point(0, 0), apex=Point(5, 5), end=Point(0, 10))
    assert ch.apex == Point(5, 5)


def test_pagroup_apex_ist_mittel_der_chevron_apexe():
    g = PaGroup(
        pa_value=0.02,
        chevrons=(
            Chevron(Point(0, 0), Point(10, 5), Point(0, 10)),
            Chevron(Point(0, 0), Point(12, 5), Point(0, 10)),
            Chevron(Point(0, 0), Point(14, 5), Point(0, 10)),
        ),
    )
    assert g.apex.x == pytest.approx(12.0)
    assert g.apex.y == pytest.approx(5.0)


def test_patternmodel_default_ohne_rahmenbox():
    m = PatternModel(groups=())
    assert m.groups == ()
    assert m.frame_box is None


def test_framebox_haelt_vier_ecken():
    ecken = (Point(0, 0), Point(0, 1), Point(1, 1), Point(1, 0))
    box = FrameBox(corners=ecken)
    assert len(box.corners) == 4
```

- [ ] **Schritt 2: Tests ausführen — RED**

Run: `python -m pytest tests/test_model.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'pa_analyzer.model'`.

- [ ] **Schritt 3: `model.py` implementieren**

```python
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
```

- [ ] **Schritt 4: Tests ausführen — GREEN**

Run: `python -m pytest tests/test_model.py -v`
Erwartet: PASS (5 Tests).

- [ ] **Schritt 5: Commit**

```bash
git add src/pa_analyzer/model.py tests/test_model.py
git commit -m "Datenmodell: Point, Chevron, PaGroup, FrameBox, PatternModel"
```

---

## Task 3: Parser — GCode-Tokenizer

Zerlegt rohen GCode in einen Strom aus Bewegungen (mit absolut getrackter Position) und `SET_PRESSURE_ADVANCE`-Befehlen. Grundlage für Task 4 und 5.

**Files:**
- Create: `src/pa_analyzer/gcode_parser.py`
- Test: `tests/test_gcode_parser.py`

- [ ] **Schritt 1: Tests schreiben** — `tests/test_gcode_parser.py`

```python
import pytest

from pa_analyzer.gcode_parser import _Move, _tokenize


def test_tokenize_erkennt_pa_befehl():
    tokens = list(_tokenize("SET_PRESSURE_ADVANCE ADVANCE=0.025\n"))
    assert tokens == [("pa", 0.025)]


def test_tokenize_pa_mit_kommentar_und_extruder():
    gcode = "SET_PRESSURE_ADVANCE EXTRUDER=extruder ADVANCE=.018 ; comment\n"
    assert list(_tokenize(gcode)) == [("pa", 0.018)]


def test_tokenize_extrudierende_bewegung():
    tokens = list(_tokenize("G1 X10 Y20 E0.5\n"))
    assert tokens == [("move", _Move(10.0, 20.0, extruding=True))]


def test_tokenize_travel_ist_nicht_extrudierend():
    tokens = list(_tokenize("G1 X10 Y20 F30000\n"))
    assert tokens == [("move", _Move(10.0, 20.0, extruding=False))]


def test_tokenize_trackt_position_absolut():
    gcode = "G1 X10 Y20 E1\nG1 X15 E1\n"  # zweite Zeile ohne Y
    tokens = list(_tokenize(gcode))
    assert tokens[1] == ("move", _Move(15.0, 20.0, extruding=True))


def test_tokenize_ueberspringt_reine_e_moves():
    # Retract/De-Retract (kein X/Y) erzeugen kein move-Token
    assert list(_tokenize("G1 E-0.8 F1500\n")) == []


def test_tokenize_fuehrende_null_optional():
    # OrcaSlicer schreibt E-Werte oft ohne fuehrende Null
    tokens = list(_tokenize("G1 X.5 Y-.25 E.88741\n"))
    assert tokens == [("move", _Move(0.5, -0.25, extruding=True))]
```

- [ ] **Schritt 2: Tests ausführen — RED**

Run: `python -m pytest tests/test_gcode_parser.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'pa_analyzer.gcode_parser'`.

- [ ] **Schritt 3: Tokenizer implementieren** — `src/pa_analyzer/gcode_parser.py`

```python
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
```

- [ ] **Schritt 4: Tests ausführen — GREEN**

Run: `python -m pytest tests/test_gcode_parser.py -v`
Erwartet: PASS (7 Tests).

- [ ] **Schritt 5: Commit**

```bash
git add src/pa_analyzer/gcode_parser.py tests/test_gcode_parser.py
git commit -m "Parser: GCode-Tokenizer mit absolutem Positions-Tracking"
```

---

## Task 4: Parser — PA-Gruppen & Chevron-Erkennung

Die Kern-Logik: aus dem Token-Strom echte Chevron-Gruppen erkennen, Setup-Befehle ignorieren, über Layer deduplizieren. Getestet gegen die echte Fixture.

**Files:**
- Modify: `src/pa_analyzer/gcode_parser.py` (Funktionen ergänzen)
- Test: `tests/test_gcode_parser.py` (Tests ergänzen)

- [ ] **Schritt 1: Tests ergänzen** — ans Ende von `tests/test_gcode_parser.py`

```python
from pa_analyzer.gcode_parser import parse  # oben zu den Imports nehmen


def test_parst_genau_21_pa_gruppen(pa_pattern_gcode):
    model = parse(pa_pattern_gcode)
    assert len(model.groups) == 21


def test_pa_werte_aufsteigend_und_korrekt(pa_pattern_gcode):
    model = parse(pa_pattern_gcode)
    werte = [g.pa_value for g in model.groups]
    erwartet = [round(0.010 + i * 0.002, 3) for i in range(21)]
    assert werte == pytest.approx(erwartet, abs=1e-9)


def test_drei_chevrons_pro_gruppe(pa_pattern_gcode):
    model = parse(pa_pattern_gcode)
    assert all(len(g.chevrons) == 3 for g in model.groups)


def test_erste_gruppe_ist_echtes_pattern_nicht_rahmenbox(pa_pattern_gcode):
    # Die SET_PRESSURE_ADVANCE bei GCode-Zeile 108 gehoert zur Rahmen-Box
    # und darf NICHT als Gruppe auftauchen. Die echte erste Gruppe (PA 0.01)
    # hat ihren Apex bei X~124.5.
    model = parse(pa_pattern_gcode)
    g = model.groups[0]
    assert g.pa_value == pytest.approx(0.01)
    ch = g.chevrons[0]
    assert ch.apex.x == pytest.approx(124.538, abs=0.01)
    assert ch.apex.y == pytest.approx(142.0, abs=0.01)
    assert ch.apex.x > ch.start.x  # Apex liegt rechts


def test_apex_x_letzte_gruppe(pa_pattern_gcode):
    model = parse(pa_pattern_gcode)
    assert model.groups[-1].pa_value == pytest.approx(0.05)
    assert model.groups[-1].chevrons[0].apex.x == pytest.approx(196.566, abs=0.01)


def test_chevron_arme_kehren_in_x_zurueck(pa_pattern_gcode):
    # start.x und end.x eines Chevrons liegen auf gleicher Spalte
    model = parse(pa_pattern_gcode)
    for g in model.groups:
        for ch in g.chevrons:
            assert ch.start.x == pytest.approx(ch.end.x, abs=0.5)
```

- [ ] **Schritt 2: Tests ausführen — RED**

Run: `python -m pytest tests/test_gcode_parser.py -k "gruppe or chevron or apex or pattern" -v`
Erwartet: FAIL mit `ImportError: cannot import name 'parse'`.

- [ ] **Schritt 3: Chevron-/Gruppen-Logik implementieren** — an `gcode_parser.py` anhängen

```python
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
```

- [ ] **Schritt 4: Tests ausführen — GREEN**

Run: `python -m pytest tests/test_gcode_parser.py -v`
Erwartet: PASS (alle Tests aus Task 3 + 6 neue). Falls eine Apex-X-Erwartung knapp danebenliegt: Toleranz prüfen, nicht den Erwartungswert raten — die Werte stammen aus der verifizierten GCode-Analyse.

- [ ] **Schritt 5: Commit**

```bash
git add src/pa_analyzer/gcode_parser.py tests/test_gcode_parser.py
git commit -m "Parser: Chevron- und PA-Gruppen-Erkennung mit Layer-Deduplizierung"
```

---

## Task 5: Parser — Rahmen-Box

Findet die äußere Rahmen-Box (4 Ecken) für die spätere Homographie (Etappe 2).

**Files:**
- Modify: `src/pa_analyzer/gcode_parser.py`
- Test: `tests/test_gcode_parser.py`

- [ ] **Schritt 1: Tests ergänzen** — ans Ende von `tests/test_gcode_parser.py`

```python
def test_rahmenbox_vier_ecken(pa_pattern_gcode):
    model = parse(pa_pattern_gcode)
    assert model.frame_box is not None
    assert len(model.frame_box.corners) == 4


def test_rahmenbox_korrekte_ausdehnung(pa_pattern_gcode):
    # Aus der GCode-Analyse: aeussere Box X 100.731..199.269,
    # Y 120.787..163.213.
    model = parse(pa_pattern_gcode)
    xs = sorted({round(c.x, 3) for c in model.frame_box.corners})
    ys = sorted({round(c.y, 3) for c in model.frame_box.corners})
    assert xs == pytest.approx([100.731, 199.269], abs=0.01)
    assert ys == pytest.approx([120.787, 163.213], abs=0.01)
```

- [ ] **Schritt 2: Tests ausführen — RED**

Run: `python -m pytest tests/test_gcode_parser.py -k "rahmenbox" -v`
Erwartet: FAIL — `model.frame_box` ist `None`, `len(None.corners)` wirft `AttributeError`.

- [ ] **Schritt 3: Rahmen-Box-Erkennung implementieren** — an `gcode_parser.py` anhängen, und `parse()` anpassen

```python
def _axis_parallel(seg: tuple[Point, Point]) -> bool:
    s, e = seg
    return abs(s.x - e.x) < _EPS or abs(s.y - e.y) < _EPS


def _rectangle_from_run(run: list[tuple[Point, Point]]) -> FrameBox | None:
    """Prüft, ob die letzten 4 Segmente eines Runs ein geschlossenes,
    achsenparalleles Rechteck bilden."""
    if len(run) < 4:
        return None
    segs = run[-4:]
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
```

Dann `parse()` ersetzen:

```python
def parse(gcode_text: str) -> PatternModel:
    """Parst PA-Pattern-GCode in ein PatternModel."""
    groups = _dedupe_by_pa(_parse_groups(gcode_text))
    frame_box = _find_frame_box(gcode_text)
    return PatternModel(groups=tuple(groups), frame_box=frame_box)
```

- [ ] **Schritt 4: Tests ausführen — GREEN**

Run: `python -m pytest tests/test_gcode_parser.py -v`
Erwartet: PASS (alle Parser-Tests).

- [ ] **Schritt 5: Commit**

```bash
git add src/pa_analyzer/gcode_parser.py tests/test_gcode_parser.py
git commit -m "Parser: Rahmen-Box-Erkennung, parse() vollstaendig"
```

---

## Task 6: Generator — Parameter & Mathematik

Die Eingabe-Parameter und alle abgeleiteten Größen: Flow-Formel, Linienbreite, PA-Werte, Chevron-Geometrie.

**Files:**
- Create: `src/pa_analyzer/gcode_generator.py`
- Test: `tests/test_gcode_generator.py`

- [ ] **Schritt 1: Tests schreiben** — `tests/test_gcode_generator.py`

```python
import math

import pytest

from pa_analyzer.gcode_generator import (
    GeneratorParams,
    _chevron_deltas,
    _extrusion,
    _group_advance,
    _line_width,
    _num_patterns,
    _pa_values,
    _wall_x_offset,
)


def test_line_width_aus_duese_und_ratio():
    p = GeneratorParams(nozzle_diameter=0.4, line_ratio=112.5)
    assert _line_width(p) == pytest.approx(0.45)


def test_num_patterns():
    p = GeneratorParams(pa_start=0.0, pa_end=0.05, pa_step=0.005)
    assert _num_patterns(p) == 11


def test_pa_values_liste():
    p = GeneratorParams(pa_start=0.0, pa_end=0.02, pa_step=0.005)
    assert _pa_values(p) == pytest.approx([0.0, 0.005, 0.01, 0.015, 0.02])


def test_extrusion_entspricht_stadion_formel():
    # Unabhaengige Nachrechnung der dokumentierten Flow-Formel.
    lw, h, fd, mult, length = 0.45, 0.2, 1.75, 1.0, 12.0
    ext_area = (lw - h) * h + math.pi * (h / 2) ** 2
    fil_area = math.pi * (fd / 2) ** 2
    erwartet = round(length * ext_area / fil_area * mult, 5)
    assert _extrusion(length, lw, h, fd, mult) == pytest.approx(erwartet)


def test_extrusion_proportional_zur_laenge():
    args = (0.45, 0.2, 1.75, 1.0)
    assert _extrusion(20, *args) == pytest.approx(2 * _extrusion(10, *args), rel=1e-3)


def test_extrusion_skaliert_mit_multiplikator():
    e1 = _extrusion(10, 0.45, 0.2, 1.75, 1.0)
    e2 = _extrusion(10, 0.45, 0.2, 1.75, 1.2)
    assert e2 == pytest.approx(e1 * 1.2, rel=1e-3)


def test_chevron_deltas_bei_90_grad():
    # Halbwinkel 45 Grad: dx == dy == side_length * cos(45 Grad)
    p = GeneratorParams(corner_angle=90.0, wall_side_length=30.0)
    dx, dy = _chevron_deltas(p)
    assert dx == pytest.approx(dy)
    assert dx == pytest.approx(30.0 * math.cos(math.radians(45)))


def test_group_advance_positiv():
    assert _group_advance(GeneratorParams()) > 0
```

- [ ] **Schritt 2: Tests ausführen — RED**

Run: `python -m pytest tests/test_gcode_generator.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'pa_analyzer.gcode_generator'`.

- [ ] **Schritt 3: Parameter & Mathematik implementieren** — `src/pa_analyzer/gcode_generator.py`

```python
"""Erzeugt druckbaren Chevron-PA-Pattern-GCode aus Parametern.

Algorithmus abgeleitet aus Ellis' Pressure_Linear_Advance_Tool
(Flow-Mathematik mit Stadion-Querschnitt, Chevron-Geometrie). Erzeugt
">"-Chevrons, die der gcode_parser dieses Projekts verlustfrei
zurücklesen kann (siehe Round-Trip-Test, Task 8).
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
    extrusion_multiplier: float = 1.0
    speed_print: float = 60.0
    speed_travel: float = 120.0
    # Klipper-Hooks
    start_gcode: str = "PRINT_START"
    end_gcode: str = "PRINT_END"


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
```

- [ ] **Schritt 4: Tests ausführen — GREEN**

Run: `python -m pytest tests/test_gcode_generator.py -v`
Erwartet: PASS (8 Tests).

- [ ] **Schritt 5: Commit**

```bash
git add src/pa_analyzer/gcode_generator.py tests/test_gcode_generator.py
git commit -m "Generator: Parameter, Flow-Mathematik und Geometrie-Groessen"
```

---

## Task 7: Generator — `generate()`

Setzt aus den Parametern den vollständigen GCode-Text zusammen: Header, Rahmen-Box, Chevron-Gruppen über alle Layer.

**Files:**
- Modify: `src/pa_analyzer/gcode_generator.py`
- Test: `tests/test_gcode_generator.py`

- [ ] **Schritt 1: Tests ergänzen** — ans Ende von `tests/test_gcode_generator.py`

```python
from pa_analyzer.gcode_generator import generate  # oben zu den Imports


def test_generate_enthaelt_geruest():
    g = generate(GeneratorParams())
    for marker in ("G90", "M83", "PRINT_START", "PRINT_END"):
        assert marker in g


def test_generate_pa_zeilen_anzahl():
    # num_patterns × num_layers SET_PRESSURE_ADVANCE-Zeilen
    p = GeneratorParams(pa_start=0.0, pa_end=0.05, pa_step=0.005, num_layers=3)
    assert generate(p).count("SET_PRESSURE_ADVANCE") == 11 * 3


def test_generate_endet_mit_newline():
    assert generate(GeneratorParams()).endswith("\n")


def test_generate_temp_eingebacken():
    assert "235" in generate(GeneratorParams(temp=235))


def test_generate_eigener_start_end_gcode():
    p = GeneratorParams(start_gcode="MEIN_START", end_gcode="MEIN_ENDE")
    g = generate(p)
    assert "MEIN_START" in g and "MEIN_ENDE" in g
```

- [ ] **Schritt 2: Tests ausführen — RED**

Run: `python -m pytest tests/test_gcode_generator.py -k generate -v`
Erwartet: FAIL mit `ImportError: cannot import name 'generate'`.

- [ ] **Schritt 3: `generate()` implementieren** — an `gcode_generator.py` anhängen

```python
def _fmt(v: float) -> str:
    """Koordinate/PA-Wert mit bis zu 4 Nachkommastellen, ohne überflüssige
    Nullen. Für den Wertebereich dieses Generators (Koordinaten 1–300,
    PA 0–0.5) erzeugt :g keine wissenschaftliche Notation."""
    return f"{round(v, 4):g}"


def _fmt_e(v: float) -> str:
    """Extrusionswert mit bis zu 5 Nachkommastellen."""
    return f"{round(v, 5):g}"


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

    out: list[str] = [
        "; PA-Pattern erzeugt von pa_analyzer (Etappe 1)",
        f"; pa_start={p.pa_start} pa_end={p.pa_end} pa_step={p.pa_step}",
        f"; wall_count={p.wall_count} num_layers={p.num_layers}",
        f"; temp={p.temp} extrusion_multiplier={p.extrusion_multiplier}",
        "G90",
        "M83",
        p.start_gcode,
        f"M109 S{_fmt(p.temp)}",
    ]

    # Rahmen-Box auf erster Layer-Höhe (4 achsenparallele extrudierende Moves)
    e_h = _extrusion(bx1 - bx0, lw, p.layer_height, p.filament_diameter,
                     p.extrusion_multiplier)
    e_v = _extrusion(by1 - by0, lw, p.layer_height, p.filament_diameter,
                     p.extrusion_multiplier)
    out.append(f"G1 Z{_fmt(p.layer_height)} F{travel_f}")
    out.append(f"G1 X{_fmt(bx0)} Y{_fmt(by0)} F{travel_f}")
    out.append(f"G1 X{_fmt(bx0)} Y{_fmt(by1)} E{_fmt_e(e_v)} F{print_f}")
    out.append(f"G1 X{_fmt(bx1)} Y{_fmt(by1)} E{_fmt_e(e_h)} F{print_f}")
    out.append(f"G1 X{_fmt(bx1)} Y{_fmt(by0)} E{_fmt_e(e_v)} F{print_f}")
    out.append(f"G1 X{_fmt(bx0)} Y{_fmt(by0)} E{_fmt_e(e_h)} F{print_f}")

    # Pattern, num_layers mal gestapelt
    for layer in range(p.num_layers):
        z = (layer + 1) * p.layer_height
        out.append(f"G1 Z{_fmt(z)} F{travel_f}")
        for j, pa in enumerate(pa_values):
            out.append(f"SET_PRESSURE_ADVANCE ADVANCE={_fmt(pa)}")
            gx = px0 + j * adv
            for k in range(p.wall_count):
                sx = gx + k * wall_off
                # Travel zum Chevron-Start (trennt die Chevron-Runs)
                out.append(f"G1 X{_fmt(sx)} Y{_fmt(py0)} F{travel_f}")
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

    out.append(p.end_gcode)
    return "\n".join(out) + "\n"
```

- [ ] **Schritt 4: Tests ausführen — GREEN**

Run: `python -m pytest tests/test_gcode_generator.py -v`
Erwartet: PASS (13 Tests).

- [ ] **Schritt 5: Commit**

```bash
git add src/pa_analyzer/gcode_generator.py tests/test_gcode_generator.py
git commit -m "Generator: generate() erzeugt vollstaendigen Pattern-GCode"
```

---

## Task 8: Integration — Round-Trip Generator → Parser

Beweist, dass der Parser den vom Generator erzeugten GCode verlustfrei zurücklesen kann (Spec, Akzeptanzkriterium A2).

**Files:**
- Test: `tests/test_roundtrip.py`

- [ ] **Schritt 1: Tests schreiben** — `tests/test_roundtrip.py`

```python
import pytest

from pa_analyzer.gcode_generator import GeneratorParams, generate
from pa_analyzer.gcode_parser import parse


def test_roundtrip_anzahl_gruppen():
    p = GeneratorParams(pa_start=0.0, pa_end=0.05, pa_step=0.005, num_layers=2)
    model = parse(generate(p))
    assert len(model.groups) == 11


def test_roundtrip_pa_werte_konsistent():
    p = GeneratorParams(pa_start=0.0, pa_end=0.05, pa_step=0.005)
    model = parse(generate(p))
    werte = [g.pa_value for g in model.groups]
    assert werte == pytest.approx([round(i * 0.005, 4) for i in range(11)])


def test_roundtrip_chevron_anzahl():
    p = GeneratorParams(wall_count=3, pa_start=0.0, pa_end=0.02, pa_step=0.005)
    model = parse(generate(p))
    assert all(len(g.chevrons) == 3 for g in model.groups)


def test_roundtrip_andere_wandzahl():
    p = GeneratorParams(wall_count=5, pa_start=0.0, pa_end=0.01, pa_step=0.005)
    model = parse(generate(p))
    assert all(len(g.chevrons) == 5 for g in model.groups)


def test_roundtrip_apex_streng_monoton_steigend():
    p = GeneratorParams(pa_start=0.0, pa_end=0.04, pa_step=0.005)
    model = parse(generate(p))
    apex_xs = [g.apex.x for g in model.groups]
    assert apex_xs == sorted(apex_xs)
    assert len(set(apex_xs)) == len(apex_xs)  # alle verschieden


def test_roundtrip_rahmenbox_erkannt():
    model = parse(generate(GeneratorParams()))
    assert model.frame_box is not None
```

- [ ] **Schritt 2: Tests ausführen — RED→GREEN prüfen**

Run: `python -m pytest tests/test_roundtrip.py -v`
Erwartet: PASS (6 Tests). `parse` und `generate` existieren bereits — dieser Task hat keine eigene Implementierung, er ist der Integrations-Nachweis. Falls ein Test FAIL: Es liegt ein echter Konsistenz-Bug zwischen Generator und Parser vor — diesen mit `superpowers:systematic-debugging` untersuchen, **nicht** den Test aufweichen.

- [ ] **Schritt 3: Gesamte Test-Suite ausführen**

Run: `python -m pytest -v`
Erwartet: PASS (alle Tests aus Task 1–8, keine Regressionen).

- [ ] **Schritt 4: Commit**

```bash
git add tests/test_roundtrip.py
git commit -m "Integration: Round-Trip-Test Generator->Parser"
```

---

## Abschluss Etappe 1

Nach Task 8 ist der Stand:
- Lauffähige, getestete Software: PA-Pattern-GCode erzeugen und parsen.
- `PatternModel` als feste Schnittstelle für Etappe 2 (Bildverarbeitung).
- Akzeptanzkriterien A1 (Parser gegen Fixture), A2 (Round-Trip), A5 (Suite grün auf Windows) erfüllt.

**Bewusst auf spätere Etappen verschoben (YAGNI):** Nummern-Glyphen im erzeugten Pattern (Ablesbarkeit, nicht kalibrierungsrelevant), Pattern-Rotation, `meta`-Felder im `PatternModel`, der Analyse-Trigger im End-GCode (`RUN_SHELL_COMMAND` — gehört zur Klipper-Integration in Etappe 3).

