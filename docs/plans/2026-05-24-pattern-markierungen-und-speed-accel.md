# Pattern-Markierungen + Speed/Accel-Parameter — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (empfohlen) oder
> superpowers:executing-plans, um diesen Plan Task für Task umzusetzen.
> Steps verwenden Checkbox-Syntax (`- [ ]`) für Tracking.

**Ziel:** Generator emittiert Solid-Top-Bar + Anker-Marker + hochkant
PA-Labels + Speed/Accel-Header; Speed und Accel werden konfigurierbar
(CLI/Macro/Config); orientation.py funktioniert dadurch erstmals
zuverlässig.

**Architektur:** Neues `glyphs.py`-Modul liefert eine Stroke-Font + eine
`render_label_gcode`-Funktion (pure Logik, keine Abhängigkeiten). Der
Generator emittiert in *allen* Layern Top-Bar + Anker; in der *obersten*
Layer zusätzlich die hochkant rotierten Labels als 0.2-mm-Relief.
Speed/Accel werden über `[generator]`-Sektion in `pa_analyzer.conf`
konfiguriert (Override-Hierarchie: CLI > Macro > Config > Default).

**Tech-Stack:** Python 3.13 · pytest · configparser · keine neuen
externen Abhängigkeiten · TDD strict (RED → GREEN → Commit).

**Spec:** `docs/specs/2026-05-24-pattern-markierungen-und-speed-accel.md`
**Layout-SVG:** `docs/specs/2026-05-24-pattern-markierungen-layout.svg`

---

## Datei-Struktur

**Neu:**
- `src/pa_analyzer/glyphs.py` — Stroke-Font (0-9 + ".") +
  `render_label_gcode(text, x, y, glyph_height, glyph_width,
  glyph_gap, line_width, layer_height, filament_diameter,
  extrusion_multiplier, print_speed, travel_speed, rotation) → list[str]`
- `tests/test_glyphs.py` — Unit-Tests fürs Glyphen-Modul

**Geändert:**
- `src/pa_analyzer/gcode_generator.py` — neue `GeneratorParams`-Felder
  (top_bar_height, anchor_marker_*, label_*, header_*, accel,
  chevron_band_gap); Helper `_top_bar_block`, `_anchor_marker_block`,
  `_label_block_top_layer`; Anpassung `generate()` für neue Geometrie
  und `SET_VELOCITY_LIMIT`-Emit; `speed_print`-Default 60 → 100
- `src/pa_analyzer/config.py` — neue Config-Felder `speed_print: float
  | None`, `accel: float | None`; `[generator]`-Sektion in
  `load_config()` parsen
- `src/pa_analyzer/cli.py` — neue argparse-Args `--speed`, `--accel`
  (Default `None` = sentinel); gen_overrides um Speed/Accel-Mapping aus
  CLI/Config erweitern
- `klipper/pa_calibrate.cfg` — `SPEED=` und `ACCEL=` als Macro-Parameter
  (leerer Default → an `pa_generate` weitergereicht, leer wird im CLI
  ignoriert)
- `pa_analyzer.example.conf` — neue `[generator]`-Sektion mit
  ausführlichen Kommentaren
- `tests/test_gcode_generator.py` — neue Tests für alle neuen Generator-
  Outputs
- `tests/test_config.py` — neue Tests für `[generator]`-Sektion
- `tests/test_cli.py` — neue Tests für `--speed`/`--accel`-Hierarchie
- `tests/test_orientation.py` — Integrations-Test mit Generator-Output
- `tests/test_klipper_macro.py` — Smoke-Test für SPEED/ACCEL im Macro

**Unverändert (aber verifizieren):**
- `tests/test_roundtrip.py` — muss grün bleiben (Round-Trip mit
  bestehender OrcaSlicer-Fixture)
- `src/pa_analyzer/gcode_parser.py` — vermutlich keine Änderung nötig
  (Frame-Box-Erkennung bleibt äußere Hülle); falls Round-Trip rot wird,
  Marker-Kommentar-Filter einbauen

---

## Test-Konventionen im Projekt

- Alle Tests in `tests/test_*.py`, ausgeführt mit `python -m pytest -q`
- Fixtures kommen aus `tests/conftest.py`
- Float-Vergleiche mit `pytest.approx(x)` oder `pytest.approx(x, abs=0.001)`
- GCode-Inhalts-Checks mit `assert "MARKER" in gcode_text`
- Test-Funktionen auf Deutsch benannt (z.B. `test_generate_zieht_solid_top_bar`)
- Reine Logik-Module ohne externe Abhängigkeiten halten (siehe `CLAUDE.md`)

---

## Aufwand-Schätzung

17 Tasks, je 5 Steps (Test, RED, Implement, GREEN, Commit), ~3-6
Stunden Gesamtaufwand. Tasks 1-13 sind reine Software-Arbeit (Windows
oder Pi). Task 14-15 sind Datei-Edits. Task 16 ist
Integrations-Validierung. Task 17 ist Doku. Task 18 ist Pi-Deploy +
User-Live-Test (Hardware-Freigabe durch User nötig).

---

## Task 1: Glyphen — GLYPHS-Lookup-Tabelle

**Files:**
- Create: `src/pa_analyzer/glyphs.py`
- Test: `tests/test_glyphs.py`

- [ ] **Step 1: Failing-Tests schreiben**

```python
# tests/test_glyphs.py
"""Unit-Tests für das Glyphen-Modul (Stroke-Font für Pattern-Labels)."""
import pytest

from pa_analyzer.glyphs import GLYPHS


def test_glyphs_enthaelt_alle_ziffern_und_punkt():
    erwartet = set("0123456789.")
    assert set(GLYPHS.keys()) == erwartet


def test_jeder_glyph_ist_liste_von_strokes():
    for zeichen, strokes in GLYPHS.items():
        assert isinstance(strokes, list), f"{zeichen} keine Liste"
        assert len(strokes) >= 1, f"{zeichen} hat keinen Stroke"
        for stroke in strokes:
            assert len(stroke) >= 2, (
                f"{zeichen}: Stroke mit weniger als 2 Punkten")


def test_glyph_koordinaten_in_einheitsquadrat():
    # Alle (x, y)-Punkte müssen in [0, 1] liegen — normierte Koordinaten,
    # die später auf glyph_width/glyph_height skaliert werden.
    for zeichen, strokes in GLYPHS.items():
        for stroke in strokes:
            for x, y in stroke:
                assert 0.0 <= x <= 1.0, f"{zeichen}: x={x} außerhalb [0,1]"
                assert 0.0 <= y <= 1.0, f"{zeichen}: y={y} außerhalb [0,1]"


def test_glyph_0_ist_rechteck():
    # "0" = ein geschlossenes Rechteck = 1 Stroke mit 5 Punkten
    # (Anfang == Ende für geschlossene Form).
    strokes = GLYPHS["0"]
    assert len(strokes) == 1
    assert strokes[0][0] == strokes[0][-1], "0 nicht geschlossen"


def test_glyph_8_hat_zwei_strokes():
    # "8" = Rechteck + horizontale Mittellinie = 2 Strokes
    # (Pen-Up zwischen den Strokes).
    assert len(GLYPHS["8"]) == 2


def test_glyph_punkt_ist_kurze_linie():
    # "." = kurze horizontale Linie am unteren Rand
    strokes = GLYPHS["."]
    assert len(strokes) == 1
    assert len(strokes[0]) == 2
    # Beide Punkte am unteren Rand (y == 0)
    assert strokes[0][0][1] == 0.0
    assert strokes[0][1][1] == 0.0
```

- [ ] **Step 2: Tests laufen lassen — müssen RED sein**

```bash
python -m pytest tests/test_glyphs.py -v
```

Erwartet: `ModuleNotFoundError: No module named 'pa_analyzer.glyphs'`

- [ ] **Step 3: Glyphen-Modul anlegen**

```python
# src/pa_analyzer/glyphs.py
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
```

- [ ] **Step 4: Tests laufen lassen — müssen GREEN sein**

```bash
python -m pytest tests/test_glyphs.py -v
```

Erwartet: alle 6 Tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pa_analyzer/glyphs.py tests/test_glyphs.py
git commit -m "$(cat <<'EOF'
glyphs: Stroke-Font-Lookup für Pattern-Labels

Ziffern 0-9 und Punkt als Vektor-Strokes in normierten Koordinaten
[0, 1]. Jeder Glyph = Liste von Strokes; jeder Stroke = Polyline.
Mehrere Strokes = Pen-Up dazwischen (späteres Retract im GCode).
Reine Logik, keine externen Abhängigkeiten (CLAUDE.md-Regel).

Spec: docs/specs/2026-05-24-pattern-markierungen-und-speed-accel.md §Glyphen-Engine
EOF
)"
```

---

## Task 2: Glyphen — render_label_gcode (rotation=0)

**Files:**
- Modify: `src/pa_analyzer/glyphs.py`
- Modify: `tests/test_glyphs.py`

- [ ] **Step 1: Failing-Tests anhängen**

```python
# Am Ende von tests/test_glyphs.py anhängen:

from pa_analyzer.glyphs import render_label_gcode


def _druck_args() -> dict:
    """Sammelt typische Druckwerte für die Tests."""
    return dict(
        glyph_height=0.7, glyph_width=0.5, glyph_gap=0.2,
        line_width=0.45, layer_height=0.2,
        filament_diameter=1.75, extrusion_multiplier=1.0,
        print_speed=60.0, travel_speed=120.0,
    )


def test_render_label_einzelne_ziffer_horizontal():
    lines = render_label_gcode("1", x=10.0, y=20.0, rotation=0,
                                **_druck_args())
    # "1" ist 1 Stroke (vertikal), 2 Punkte — Travel zum Start +
    # extrudierter Move zum Endpunkt = mindestens 2 G1-Zeilen.
    assert any("G1 X10.25 Y20" in z for z in lines), (
        f"Travel zum Start (X10.25 = 10.0 + 0.5*0.5) fehlt: {lines}")
    assert any("G1 X10.25 Y20.7" in z for z in lines), (
        f"Extrudierter Move zum Endpunkt (Y=20+0.7) fehlt: {lines}")


def test_render_label_mehrziffern_x_offset():
    # "12" — Ziffer "1" bei x=0, dann "2" bei x = glyph_width + glyph_gap
    # = 0.5 + 0.2 = 0.7 (relativ zum Label-Start).
    lines = render_label_gcode("12", x=0.0, y=0.0, rotation=0,
                                **_druck_args())
    # "1" beginnt bei x=0+0.25=0.25
    assert any("X0.25" in z for z in lines)
    # "2" beginnt bei x=0.7+0=0.7 (erster Punkt von "2" ist (0, 1))
    assert any("X0.7" in z for z in lines)


def test_render_label_extrudierter_move_hat_e_wert():
    lines = render_label_gcode("1", x=0.0, y=0.0, rotation=0,
                                **_druck_args())
    # Der extrudierte Move (kein Travel) muss einen E-Wert enthalten.
    extrudiert = [z for z in lines if z.startswith("G1")
                  and " E" in z]
    assert len(extrudiert) >= 1, (
        f"kein extrudierter Move mit E-Wert: {lines}")
```

- [ ] **Step 2: Tests laufen lassen — müssen RED sein**

```bash
python -m pytest tests/test_glyphs.py::test_render_label_einzelne_ziffer_horizontal -v
```

Erwartet: `ImportError: cannot import name 'render_label_gcode'`

- [ ] **Step 3: render_label_gcode (rotation=0) implementieren**

Anhängen an `src/pa_analyzer/glyphs.py`:

```python
import math


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
    """Koordinate mit bis zu 4 Nachkommastellen, keine überflüssige Nullen."""
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
            # Stroke-Punkte auf Druckbett-Koordinaten skalieren.
            punkte = [
                (cursor_x + px * glyph_width,
                 cursor_y + py * glyph_height)
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
        # Nach Glyphe: Cursor um glyph_width + glyph_gap nach rechts.
        cursor_x += glyph_width + glyph_gap
    return out
```

- [ ] **Step 4: Tests laufen lassen — müssen GREEN sein**

```bash
python -m pytest tests/test_glyphs.py -v
```

Erwartet: alle 9 Tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pa_analyzer/glyphs.py tests/test_glyphs.py
git commit -m "$(cat <<'EOF'
glyphs: render_label_gcode für horizontale Labels (rotation=0)

Skaliert Stroke-Koordinaten auf glyph_width/glyph_height, emittiert
Travel zum Stroke-Start und extrudierte Moves entlang der Polyline.
Mehrere Glyphen werden mit glyph_gap-Abstand nebeneinander gerendert.
Extrusions-Formel dupliziert (kein Import auf gcode_generator), damit
glyphs.py reine Logik bleibt.
EOF
)"
```

---

## Task 3: Glyphen — render_label_gcode (rotation=90)

**Files:**
- Modify: `src/pa_analyzer/glyphs.py`
- Modify: `tests/test_glyphs.py`

- [ ] **Step 1: Failing-Test anhängen**

```python
# Am Ende von tests/test_glyphs.py anhängen:

def test_render_label_rotation_90_dreht_koordinaten():
    # Bei rotation=90 dreht sich die Glyphe 90° im Uhrzeigersinn:
    # Original (x_g, y_g) im Einheitsquadrat → gedruckt bei
    # (x + y_g * glyph_height, y - x_g * glyph_width).
    # Die Glyphe "1" hat Stroke [(0.5, 0), (0.5, 1)].
    # Bei rotation=0, x=0, y=0:
    #   Start  = (0+0.5*0.5, 0+0*0.7)   = (0.25, 0)
    #   Ende   = (0+0.5*0.5, 0+1*0.7)   = (0.25, 0.7)
    # Bei rotation=90, x=0, y=0:
    #   Start  = (0+0*0.7,   0-0.5*0.5) = (0, -0.25)
    #   Ende   = (0+1*0.7,   0-0.5*0.5) = (0.7, -0.25)
    lines = render_label_gcode("1", x=0.0, y=0.0, rotation=90,
                                **_druck_args())
    assert any("X0 Y-0.25" in z for z in lines), (
        f"Rotierter Start (0, -0.25) fehlt: {lines}")
    assert any("X0.7 Y-0.25" in z for z in lines), (
        f"Rotiertes Ende (0.7, -0.25) fehlt: {lines}")


def test_render_label_rotation_90_text_laeuft_nach_unten():
    # "12" bei rotation=90 — "2" muss UNTER "1" stehen (Cursor läuft
    # nach Glyphe um glyph_width + glyph_gap = 0.7 nach UNTEN bei rot=90).
    lines = render_label_gcode("12", x=0.0, y=0.0, rotation=90,
                                **_druck_args())
    # "1": stroke endet bei Y=-0.25
    # "2": Cursor ist jetzt y = 0 - 0.7 = -0.7. "2"-Stroke beginnt
    # bei (0, 1) im Original. Rotation:
    # Start (0+1*0.7, -0.7-0*0.5) = (0.7, -0.7)
    assert any("X0.7 Y-0.7" in z for z in lines), (
        f"Cursor läuft nicht nach unten: {lines}")


def test_render_label_rotation_invalid_wirft_value_error():
    with pytest.raises(ValueError):
        render_label_gcode("1", x=0.0, y=0.0, rotation=45,
                            **_druck_args())
```

- [ ] **Step 2: Tests laufen lassen — müssen RED sein**

```bash
python -m pytest tests/test_glyphs.py::test_render_label_rotation_90_dreht_koordinaten -v
```

Erwartet: FAIL (Rotation noch nicht implementiert; ValueError-Test
PASS, aber die Rotations-Geometrie-Tests müssen FAIL sein).

- [ ] **Step 3: Rotation in render_label_gcode einbauen**

Ersetze in `src/pa_analyzer/glyphs.py` den Block `# Stroke-Punkte auf
Druckbett-Koordinaten skalieren.` bis `cursor_x += glyph_width +
glyph_gap`:

```python
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
```

- [ ] **Step 4: Tests laufen lassen — müssen GREEN sein**

```bash
python -m pytest tests/test_glyphs.py -v
```

Erwartet: alle 12 Tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pa_analyzer/glyphs.py tests/test_glyphs.py
git commit -m "$(cat <<'EOF'
glyphs: rotation=90 für hochkante Labels auf der Top-Bar

Bei rotation=90 wird jeder Stroke-Punkt (x_g, y_g) → (y_g, -x_g)
gedreht (Clockwise 90°). Cursor läuft nach jeder Glyphe nach unten
statt nach rechts. Lese-Richtung: von oben nach unten (intuitiv
beim Betrachten des Druckbetts).
EOF
)"
```

---

## Task 4: Generator — neue GeneratorParams-Felder

**Files:**
- Modify: `src/pa_analyzer/gcode_generator.py`
- Modify: `tests/test_gcode_generator.py`

- [ ] **Step 1: Failing-Tests anhängen**

```python
# Am Ende von tests/test_gcode_generator.py anhängen:

def test_generator_params_neue_defaults():
    p = GeneratorParams()
    # Pattern-Markierungen
    assert p.top_bar_height == 4.0
    assert p.anchor_marker_width == 2.0
    assert p.anchor_marker_height == 8.0
    assert p.label_glyph_height == 0.7
    assert p.label_glyph_width == 0.5
    assert p.label_glyph_gap == 0.2
    assert p.header_glyph_height == 1.0
    assert p.header_glyph_width == 0.7
    assert p.header_column_spacing == 4.0
    assert p.header_to_labels_gap == 3.0
    assert p.chevron_band_gap == 1.0
    # Speed/Accel
    assert p.speed_print == 100.0    # geändert von 60
    assert p.accel == 2000.0         # neu
```

- [ ] **Step 2: Tests laufen lassen — müssen RED sein**

```bash
python -m pytest tests/test_gcode_generator.py::test_generator_params_neue_defaults -v
```

Erwartet: `AttributeError: 'GeneratorParams' object has no attribute
'top_bar_height'`.

- [ ] **Step 3: GeneratorParams erweitern**

In `src/pa_analyzer/gcode_generator.py` im `@dataclass(frozen=True)
class GeneratorParams:` direkt vor der `start_gcode`-Zeile einfügen
und `speed_print = 60.0` auf `100.0` ändern:

```python
    # ... bestehende Felder ...
    speed_print: float = 100.0        # geändert von 60
    speed_travel: float = 120.0
    # ... bestehende Felder bis 'analyze_gcode' ...

    # Pattern-Markierungen (neu, siehe docs/specs/2026-05-24-...)
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
```

Das Feld `start_gcode` bleibt als letztes nach dem neuen Block; in der
aktuellen Reihenfolge nach `analyze_gcode`.

- [ ] **Step 4: Tests laufen lassen — müssen GREEN sein**

```bash
python -m pytest tests/test_gcode_generator.py -v
```

Erwartet: alle bestehenden Tests + der neue PASS. **Vorsicht:** bei
existierenden Tests, die `speed_print == 60.0` hartcodiert prüfen,
müssten diese auf 100.0 angepasst werden. Bestehender Test
`test_generate_enthaelt_geruest` und andere prüfen nur Marker-Strings
und sollten unverändert grün bleiben.

- [ ] **Step 5: Commit**

```bash
git add src/pa_analyzer/gcode_generator.py tests/test_gcode_generator.py
git commit -m "$(cat <<'EOF'
gcode_generator: neue Params für Markierungen + Speed/Accel

Felder für Top-Bar, Anker-Marker, Labels (PA und Header), Accel.
Default speed_print von 60 auf 100 mm/s erhöht (konservativer
realer Druck-Default), accel = 2000 mm/s² als neues Feld
(0 = nicht emittieren). Werte noch ungenutzt — Generator-Logik
kommt in den Folge-Tasks.
EOF
)"
```

---

## Task 5: Generator — Pattern-Geometrie mit Top-Bar

**Files:**
- Modify: `src/pa_analyzer/gcode_generator.py`
- Modify: `tests/test_gcode_generator.py`

- [ ] **Step 1: Failing-Test anhängen**

```python
def test_generate_pattern_hoehe_enthaelt_top_bar_und_band_gap():
    # Frame-Y-Erstreckung muss jetzt = 2*margin + chevron_band +
    # chevron_band_gap + top_bar_height sein.
    p = GeneratorParams()
    g = generate(p)
    # Parse alle Y-Werte aus G1-Zeilen
    import re
    ys = []
    for line in g.splitlines():
        m = re.search(r"\sY([\d.-]+)", line)
        if m:
            ys.append(float(m.group(1)))
    y_span = max(ys) - min(ys)
    # Erwartet: pattern_h = top_bar_height + chevron_band_gap + 2*dy
    # 2*dy bei wall_side_length=30, corner_angle=90 → 2*30*sin(45°) ≈ 42.43
    # pattern_h ≈ 4 + 1 + 42.43 = 47.43 mm
    # Plus 2*margin (4 mm) = 55.43 mm bzw. Differenz im Y-Span
    assert y_span >= 47.0, (
        f"Y-Span {y_span} mm zu klein — Top-Bar fehlt vermutlich")
```

- [ ] **Step 2: Tests laufen lassen — müssen RED sein**

```bash
python -m pytest tests/test_gcode_generator.py::test_generate_pattern_hoehe_enthaelt_top_bar_und_band_gap -v
```

Erwartet: FAIL (Y-Span ist noch ~50.43 = 42.43 + 8 margin, deckt aber
gerade nicht 47 ab; je nachdem wie genau).

Hinweis: Falls schon GREEN, dann ist der Test zu schwach — Schwelle
auf z.B. 46.0 oder einen exakten `pytest.approx` setzen.

- [ ] **Step 3: pattern_h-Berechnung anpassen**

In `src/pa_analyzer/gcode_generator.py` in der `generate()`-Funktion
ersetzen:

```python
    # Pattern-Abmessungen und Bett-Zentrierung
    chevron_h = 2 * dy
    pattern_w = (
        (len(pa_values) - 1) * adv + (p.wall_count - 1) * wall_off + dx
    )
    pattern_h = p.top_bar_height + p.chevron_band_gap + chevron_h
    margin = 4.0
    bx0 = p.bed_x / 2 - (pattern_w + 2 * margin) / 2
    by0 = p.bed_y / 2 - (pattern_h + 2 * margin) / 2
    bx1 = bx0 + pattern_w + 2 * margin
    by1 = by0 + pattern_h + 2 * margin
    px0 = bx0 + margin            # Start-X des ersten Chevrons
    # Chevron-Y-Start: über dem Frame-Unterrand, UNTER der Top-Bar.
    # Top-Bar liegt im oberen Frame-Innenbereich (Höhe top_bar_height
    # unterhalb der Frame-Oberkante). Chevrons starten chevron_band_gap
    # darunter.
    py0 = by0 + margin            # untere Arm-Enden, wie bisher
    # Top-Bar-Y-Bereich (für späteren Helper):
    top_bar_y_low = by1 - margin - p.top_bar_height
    top_bar_y_high = by1 - margin
```

(`top_bar_y_low`/`top_bar_y_high` werden in Task 6 verwendet.)

- [ ] **Step 4: Tests laufen lassen — müssen GREEN sein**

```bash
python -m pytest tests/test_gcode_generator.py -v
```

Erwartet: neuer Test PASS, alle bestehenden bleiben grün (Frame-Box
verschiebt sich, aber Marker-Strings unverändert).

- [ ] **Step 5: Commit**

```bash
git add src/pa_analyzer/gcode_generator.py tests/test_gcode_generator.py
git commit -m "$(cat <<'EOF'
gcode_generator: pattern_h berücksichtigt Top-Bar + Band-Gap

Pattern-Höhe = top_bar_height + chevron_band_gap + Chevron-Höhe.
Bett-Zentrierung passt sich automatisch an. Vorbereitung für den
Top-Bar-Emit in der nächsten Task — die Top-Bar-Y-Koordinaten
werden als lokale Variablen für den späteren Helper bereitgestellt.
EOF
)"
```

---

## Task 6: Generator — Solid-Top-Bar emittieren

**Files:**
- Modify: `src/pa_analyzer/gcode_generator.py`
- Modify: `tests/test_gcode_generator.py`

- [ ] **Step 1: Failing-Tests anhängen**

```python
def test_generate_zieht_solid_top_bar():
    # Top-Bar = Vollfüllung der Höhe top_bar_height über pattern_w.
    # Bei top_bar_height=4 mm und line_width=0.45 mm → ca. 9 parallele
    # Linien (4/0.45 ≈ 8.89).
    p = GeneratorParams()
    g = generate(p)
    # Top-Bar-Y-Bereich (siehe Berechnung in generate)
    import re
    # Wir prüfen, dass im obersten Bereich (Y > by1 - margin -
    # top_bar_height) viele horizontale Moves mit E-Wert auftauchen
    # (typische Stadion-Füllung).
    e_lines_in_top = 0
    for line in g.splitlines():
        m = re.search(r"\sY([\d.-]+).+E([\d.-]+)", line)
        if m:
            y = float(m.group(1))
            # by1 = bed_y/2 + (pattern_h + 8) / 2; margin=4
            # Vereinfacht: Y im oberen Bereich = Y > bed_y/2 + 15 (grob)
            if y > p.bed_y / 2 + 15:
                e_lines_in_top += 1
    assert e_lines_in_top >= 5, (
        f"Nur {e_lines_in_top} extrudierte Moves im Top-Bar-Bereich — "
        "Solid-Top-Bar fehlt vermutlich")


def test_generate_top_bar_in_allen_layern():
    # Top-Bar wird in jedem Layer gedruckt (gleiche Füll-Anzahl).
    # Indirekt: Z-Werte werden mehrfach hochgesetzt, und in jedem
    # Z-Block sollten Top-Bar-Moves auftauchen.
    p = GeneratorParams(num_layers=2)
    g = generate(p)
    # Zwei Layer = zwei Z-Wechsel zu z=0.2 bzw. z=0.4.
    assert "G1 Z0.2 " in g
    assert "G1 Z0.4 " in g
```

- [ ] **Step 2: Tests laufen lassen — müssen RED sein**

```bash
python -m pytest tests/test_gcode_generator.py::test_generate_zieht_solid_top_bar -v
```

Erwartet: FAIL (im Top-Bar-Bereich sind aktuell nur Chevrons, keine
Stadion-Füllung).

- [ ] **Step 3: Top-Bar-Helper + Integration in generate()**

In `src/pa_analyzer/gcode_generator.py` als neuen Helper VOR `def
generate(...)` einfügen:

```python
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
```

Dann in `generate()`, INNERHALB der `for layer in range(p.num_layers):`-
Schleife, NACH dem Z-Wechsel (`out.append(f"G1 Z{_fmt(z)} F{travel_f}")`)
und VOR dem `for j, pa in enumerate(pa_values):`-Block einfügen:

```python
        # Top-Bar in jedem Layer (CV-Anker für orientation.py).
        out.extend(_top_bar_block(
            p, bx0 + margin, bx1 - margin,
            top_bar_y_low, top_bar_y_high,
            travel_to, print_f,
        ))
```

(Frame-Box wird weiterhin außerhalb der Schleife vor dem ersten Layer
gedruckt — bleibt unverändert.)

- [ ] **Step 4: Tests laufen lassen — müssen GREEN sein**

```bash
python -m pytest tests/test_gcode_generator.py -v
```

Erwartet: neuer Top-Bar-Test + bestehende PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pa_analyzer/gcode_generator.py tests/test_gcode_generator.py
git commit -m "$(cat <<'EOF'
gcode_generator: Solid-Top-Bar als Vollfüllung in jedem Layer

Linien-Stadion (Boustrophedon) zwischen den vertikalen Frame-
Kanten; Höhe top_bar_height, in allen num_layers Layern.

Adressiert die Wurzel des 16-%-Konfidenz-Live-Tests: orientation.py
erwartet einen Solid-Top-Bar (Dichte-Anker), den unser Generator
bisher nicht emittiert hat (Mismatch seit Etappe 2). Beim Spike
fiel es nicht auf, weil OrcaSlicer-Output mit Bar validiert wurde.

Spec: docs/specs/2026-05-24-pattern-markierungen-und-speed-accel.md §Layout
EOF
)"
```

---

## Task 7: Generator — Anker-Marker emittieren

**Files:**
- Modify: `src/pa_analyzer/gcode_generator.py`
- Modify: `tests/test_gcode_generator.py`

- [ ] **Step 1: Failing-Test anhängen**

```python
def test_generate_setzt_anker_marker_links():
    # Anker-Marker = gefülltes Rechteck links angedockt am Frame.
    # Position: x in [bx0+margin, bx0+margin+anchor_width], y vertikal
    # mittig zur Chevron-Reihe.
    p = GeneratorParams()
    g = generate(p)
    # Heuristik: irgendwo links vom ersten Chevron muss ein klar
    # erkennbares Rechteck mit anchor_marker_width × anchor_marker_height
    # auftauchen. Da unser Marker als parallele Linien gefüllt wird
    # (analog Top-Bar), zählen wir die X-Werte im Anker-Bereich.
    import re
    px0 = p.bed_x / 2 - (
        (len(_pa_values(p)) - 1) * _group_advance(p)
        + (p.wall_count - 1) * _wall_x_offset(p) + _chevron_deltas(p)[0]
        + 8.0) / 2 + 4.0  # ≈ Pattern-Start-X
    anchor_xs = []
    for line in g.splitlines():
        m = re.search(r"G1 X([\d.-]+)", line)
        if m:
            x = float(m.group(1))
            # Anker-Bereich = unmittelbar vor px0 (Pattern-Start)
            if px0 - 5.0 < x < px0:
                anchor_xs.append(x)
    assert len(anchor_xs) >= 4, (
        f"Anker-Marker fehlt — nur {len(anchor_xs)} X-Werte links vom "
        f"Pattern-Start gefunden")
```

- [ ] **Step 2: Tests laufen lassen — müssen RED sein**

```bash
python -m pytest tests/test_gcode_generator.py::test_generate_setzt_anker_marker_links -v
```

Erwartet: FAIL.

- [ ] **Step 3: Anker-Marker-Helper + Integration**

In `src/pa_analyzer/gcode_generator.py` als zweiten Helper:

```python
def _anchor_marker_block(
    p: GeneratorParams, x_left: float, y_center: float,
    travel_to_fn, print_f: int,
) -> list[str]:
    """Gefülltes Rechteck links neben dem Pattern (Asymmetrie-Anker).

    x_left = linke Außenkante des Rechtecks (Frame-Innenkante).
    y_center = vertikale Mitte des Rechtecks (in der Chevron-Reihe).
    """
    lw = _line_width(p)
    x_right = x_left + p.anchor_marker_width
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
```

Im `generate()` direkt nach dem Top-Bar-Block (siehe Task 6):

```python
        # Anker-Marker links neben dem ersten Chevron.
        # x_left = Frame-Innenkante (bx0 + margin); y_center =
        # Chevron-Mitte (zwischen py0 und py0 + 2*dy).
        chevron_center_y = py0 + dy
        out.extend(_anchor_marker_block(
            p, bx0 + margin, chevron_center_y,
            travel_to, print_f,
        ))
```

- [ ] **Step 4: Tests laufen lassen — müssen GREEN sein**

```bash
python -m pytest tests/test_gcode_generator.py -v
```

Erwartet: alle PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pa_analyzer/gcode_generator.py tests/test_gcode_generator.py
git commit -m "$(cat <<'EOF'
gcode_generator: Anker-Marker links als Asymmetrie-Backup

Gefülltes 2×8 mm Rechteck links neben dem ersten Chevron, in allen
Layern. Macht "links" eindeutig identifizierbar — falls die Top-Bar-
Dichte für orientation knapp wird, ist der Marker das Backup-Signal.

Spec: docs/specs/2026-05-24-pattern-markierungen-und-speed-accel.md §Layout
EOF
)"
```

---

## Task 8: Generator — SET_VELOCITY_LIMIT-Accel-Emit

**Files:**
- Modify: `src/pa_analyzer/gcode_generator.py`
- Modify: `tests/test_gcode_generator.py`

- [ ] **Step 1: Failing-Tests anhängen**

```python
def test_generate_emittiert_set_velocity_limit_accel():
    p = GeneratorParams(accel=2000.0)
    g = generate(p)
    assert "SET_VELOCITY_LIMIT ACCEL=2000 ACCEL_TO_DECEL=1000" in g


def test_generate_accel_null_emittiert_kein_velocity_limit():
    p = GeneratorParams(accel=0.0)
    g = generate(p)
    assert "SET_VELOCITY_LIMIT" not in g


def test_generate_accel_emittiert_vor_pattern():
    # Reihenfolge: PRINT_START → G90 → M83 → G92 E0 → SET_VELOCITY_LIMIT
    # → Z-Wechsel → Top-Bar → ... Set-Velocity muss vor dem ersten
    # G1 Z<layer_height>-Befehl liegen.
    p = GeneratorParams(accel=3000.0)
    g = generate(p)
    lines = g.splitlines()
    accel_idx = next(i for i, l in enumerate(lines)
                     if "SET_VELOCITY_LIMIT" in l)
    first_z = next(i for i, l in enumerate(lines)
                   if l.startswith(f"G1 Z{_fmt(p.layer_height)}"))
    assert accel_idx < first_z, (
        f"SET_VELOCITY_LIMIT ({accel_idx}) muss vor erstem Z-Move "
        f"({first_z}) stehen")
```

(`_fmt` wird oben aus `pa_analyzer.gcode_generator` importiert — falls
nicht schon, ergänze: `from pa_analyzer.gcode_generator import _fmt`.)

- [ ] **Step 2: Tests laufen lassen — müssen RED sein**

```bash
python -m pytest tests/test_gcode_generator.py::test_generate_emittiert_set_velocity_limit_accel -v
```

Erwartet: FAIL (SET_VELOCITY_LIMIT noch nicht emittiert).

- [ ] **Step 3: SET_VELOCITY_LIMIT in generate() einfügen**

In `src/pa_analyzer/gcode_generator.py` in `generate()` nach der
`out: list[str] = [...]`-Initialisierung (also nach den Header-
Kommentaren und vor `out.append("G90")` falls dort schon
abgeschlossen — oder im richtigen Block: NACH PRINT_START / G90 / M83
/ G92 E0, VOR dem ersten Z-Move):

Ersetze den Initialisierungs-Block:

```python
    out: list[str] = [
        "; PA-Pattern erzeugt von pa_analyzer",
        f"; pa_start={p.pa_start} pa_end={p.pa_end} pa_step={p.pa_step}",
        f"; wall_count={p.wall_count} num_layers={p.num_layers}",
        f"; temp={p.temp} bed_temp={p.bed_temp} "
        f"extrusion_multiplier={p.extrusion_multiplier}",
        f"; retract_distance={p.retract_distance} "
        f"purge_length={p.purge_length}",
        f"; speed_print={p.speed_print} accel={p.accel}",
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
```

- [ ] **Step 4: Tests laufen lassen — müssen GREEN sein**

```bash
python -m pytest tests/test_gcode_generator.py -v
```

Erwartet: alle PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pa_analyzer/gcode_generator.py tests/test_gcode_generator.py
git commit -m "$(cat <<'EOF'
gcode_generator: SET_VELOCITY_LIMIT für accel-Test-Parameter

Klipper-natives SET_VELOCITY_LIMIT ACCEL=<n> ACCEL_TO_DECEL=<n/2>
direkt nach PRINT_START. accel=0 deaktiviert den Emit (Drucker-
Default bleibt).

Pressure-Advance reagiert primär auf Beschleunigungs-Änderungen —
ohne diesen Set-Befehl wird der PA-Wert bei einer anderen Accel-
Konfiguration im echten Druck nicht reproduzieren.
EOF
)"
```

---

## Task 9: Generator — PA-Labels in oberster Layer

**Files:**
- Modify: `src/pa_analyzer/gcode_generator.py`
- Modify: `tests/test_gcode_generator.py`

- [ ] **Step 1: Failing-Tests anhängen**

```python
def test_generate_beschriftet_jeden_chevron_mit_pa_wert():
    # In der obersten Layer müssen Bewegungen für jeden PA-Wert
    # ("0", ".", "0", "2", "0" für PA=0.020) auftauchen. Wir prüfen
    # auf "0.020"-Glyphen-Sequenz indirekt: für 17 PA-Werte und je
    # 5 Glyphen = mindestens 17*5 = 85 Stroke-Travel-Moves zusätzlich
    # (in der obersten Layer).
    p = GeneratorParams(num_layers=2)  # 2 Layer: 1 ohne Labels, 1 mit
    g = generate(p)
    # Wir suchen nach Y-Werten oberhalb der Top-Bar-Oberkante (also
    # auf der Top-Bar, in einem schmalen Y-Streifen) UND mit dem
    # Z=0.4 (=2. Layer)-Marker davor.
    lines = g.splitlines()
    z_top_idx = next(i for i, l in enumerate(lines)
                     if l.startswith("G1 Z0.4 "))
    moves_in_top_layer = lines[z_top_idx:]
    # Eine grobe Heuristik: zähle G1-Moves im 2. Layer
    # (Erwartung: deutlich mehr als nur Top-Bar + Chevrons)
    g1_count = sum(1 for l in moves_in_top_layer if l.startswith("G1"))
    # 2. Layer ohne Labels hätte ~Top-Bar (~9 Linien) + Anker (~5) +
    # 17 Chevrons à 3 Wände à 2 Arme à 1 Move = 102 + 14 + 51 ≈ 167.
    # Mit Labels (~85 Strokes) sollte deutlich mehr stehen.
    assert g1_count > 200, (
        f"2. Layer hat nur {g1_count} G1-Moves — Labels fehlen")


def test_generate_labels_nur_in_oberster_layer():
    # Bei num_layers=3 zählen wir die G1-Move-Anzahl pro Layer.
    # Layer 1 + 2 sollten gleich viele haben (nur Top-Bar + Anker +
    # Chevrons). Layer 3 (oberste) hat zusätzlich Labels → deutlich mehr.
    p = GeneratorParams(num_layers=3)
    g = generate(p)
    import re
    lines = g.splitlines()
    z_marks = [(i, float(re.search(r"Z([\d.-]+)", l).group(1)))
               for i, l in enumerate(lines)
               if l.startswith("G1 Z")
               and "F" in l
               and "E" not in l]
    # z_marks = Liste der (index, z)-Tupel für die Z-Hub-Moves zwischen
    # Layern (3 Stück bei num_layers=3).
    assert len(z_marks) >= 3
    layer_chunks = []
    for k in range(len(z_marks)):
        start = z_marks[k][0]
        end = z_marks[k+1][0] if k+1 < len(z_marks) else len(lines)
        layer_chunks.append([l for l in lines[start:end]
                              if l.startswith("G1")])
    # layer_chunks[0] = Layer 1, layer_chunks[1] = Layer 2,
    # layer_chunks[2] = Layer 3 (oberste, mit Labels).
    assert len(layer_chunks[2]) > len(layer_chunks[0]) + 50, (
        f"Oberste Layer ({len(layer_chunks[2])} G1) nicht deutlich "
        f"größer als Layer 1 ({len(layer_chunks[0])} G1) — Labels "
        "stehen wohl in jeder Layer (sollen aber nur in oberster).")
```

- [ ] **Step 2: Tests laufen lassen — müssen RED sein**

```bash
python -m pytest tests/test_gcode_generator.py::test_generate_beschriftet_jeden_chevron_mit_pa_wert -v
```

Erwartet: FAIL (Labels noch nicht implementiert).

- [ ] **Step 3: Label-Block-Helper + Integration**

In `src/pa_analyzer/gcode_generator.py` ganz oben:

```python
from .glyphs import render_label_gcode
```

Als neuer Helper:

```python
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
```

In `generate()`, im `for layer in range(p.num_layers):`-Block, NACH
der Chevron-Reihe, **nur** wenn `layer == p.num_layers - 1`:

```python
        # Labels nur in oberster Layer (sitzen als Relief auf der Top-Bar).
        if layer == p.num_layers - 1:
            # Label-Y-Top = obere Top-Bar-Innenkante (oben in der Bar,
            # Labels laufen nach unten in die Bar hinein).
            label_y_top = top_bar_y_high - 0.5  # 0.5 mm Padding zum oberen Rand
            out.extend(_pa_labels_block(
                p, pa_values, px0, label_y_top, adv,
            ))
```

- [ ] **Step 4: Tests laufen lassen — müssen GREEN sein**

```bash
python -m pytest tests/test_gcode_generator.py -v
```

Erwartet: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pa_analyzer/gcode_generator.py tests/test_gcode_generator.py
git commit -m "$(cat <<'EOF'
gcode_generator: PA-Labels auf der Top-Bar (nur oberste Layer)

Jede Chevron-Gruppe bekommt in der obersten Layer ein hochkant
rotiertes PA-Label (z.B. "0.020"). Renderer via glyphs.render_label_gcode
mit rotation=90. Bei Webcam-Auflösung verschmilzt das 0.2 mm Relief
optisch mit dem Top-Bar → CV-Anker bleibt sauber. Bei Nahfoto/Handy
sind die Werte als Relief lesbar.
EOF
)"
```

---

## Task 10: Generator — Speed/Accel-Header in oberster Layer

**Files:**
- Modify: `src/pa_analyzer/gcode_generator.py`
- Modify: `tests/test_gcode_generator.py`

- [ ] **Step 1: Failing-Tests anhängen**

```python
def test_generate_beschriftet_speed_accel_header():
    # Speed/Accel-Header in oberster Layer: 2 Spalten ("100", "2000")
    # mit größerer Glyph-Höhe als die PA-Labels.
    p = GeneratorParams(num_layers=1, accel=2000.0, speed_print=100.0)
    g = generate(p)
    # Indirekter Test: zähle G1-Moves im einzigen Layer; Header fügt
    # 3 Glyphen ("1", "0", "0") + 4 Glyphen ("2", "0", "0", "0") =
    # 7 Glyphen extra hinzu (= mindestens 7 Stroke-Travel + Strokes).
    g1_lines = [l for l in g.splitlines() if l.startswith("G1")]
    # Ohne Header: ~85 Label-Moves + ~167 Pattern-Moves = ~252
    # Mit Header: ~252 + 30 = ~282
    assert len(g1_lines) > 280, (
        f"Nur {len(g1_lines)} G1-Moves — Speed/Accel-Header fehlt?")


def test_generate_kein_accel_kein_header_label():
    # Bei accel=0 wird auch kein Accel-Header-Label gerendert
    # (sonst stünde "0" als Accel im Header — irreführend).
    p = GeneratorParams(num_layers=1, accel=0.0)
    g = generate(p)
    # Speed-Label aber schon: "speed_print" ist immer > 0
    g1_lines = [l for l in g.splitlines() if l.startswith("G1")]
    # Differenz zum Test mit accel: weniger Header-Glyphen
    # Schwelle locker, weil exakte Zählung schwierig
    assert len(g1_lines) > 230
```

- [ ] **Step 2: Tests laufen lassen — müssen RED sein**

```bash
python -m pytest tests/test_gcode_generator.py::test_generate_beschriftet_speed_accel_header -v
```

Erwartet: FAIL.

- [ ] **Step 3: Header-Helper + Integration**

In `src/pa_analyzer/gcode_generator.py`:

```python
def _header_labels_block(
    p: GeneratorParams, x_start: float, y_top: float,
) -> list[str]:
    """Speed/Accel-Header: 2 hochkant rotierte Spalten links der PA-Labels."""
    out: list[str] = []
    # Spalte 1: Speed
    out.extend(render_label_gcode(
        text=_fmt(p.speed_print),
        x=x_start, y=y_top,
        glyph_height=p.header_glyph_height,
        glyph_width=p.header_glyph_width,
        glyph_gap=p.label_glyph_gap,
        line_width=_line_width(p),
        layer_height=p.layer_height,
        filament_diameter=p.filament_diameter,
        extrusion_multiplier=p.extrusion_multiplier,
        print_speed=p.speed_print,
        travel_speed=p.speed_travel,
        rotation=90,
    ))
    # Spalte 2: Accel (nur wenn > 0)
    if p.accel > 0:
        x_col2 = x_start + p.header_glyph_height + p.header_column_spacing
        out.extend(render_label_gcode(
            text=_fmt(p.accel),
            x=x_col2, y=y_top,
            glyph_height=p.header_glyph_height,
            glyph_width=p.header_glyph_width,
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
```

In `generate()`, im `if layer == p.num_layers - 1:`-Block VOR dem
`_pa_labels_block`-Aufruf:

```python
            # Speed/Accel-Header VOR den PA-Labels (links auf der Top-Bar).
            header_x_start = bx0 + margin + 0.5  # 0.5 mm Padding zum Anker
            out.extend(_header_labels_block(
                p, header_x_start, label_y_top,
            ))
            # PA-Labels beginnen nach den Header-Spalten + Trenn-Lücke.
            pa_labels_x_offset = (
                2 * p.header_glyph_height + p.header_column_spacing
                + p.header_to_labels_gap
            )
            # Übergebe verschobene px0 an die PA-Labels:
            out.extend(_pa_labels_block(
                p, pa_values, px0 + pa_labels_x_offset, label_y_top, adv,
            ))
```

**Achtung:** die letzte Zeile ersetzt den `_pa_labels_block`-Aufruf aus
Task 9. Also den vorherigen Aufruf entfernen — Header und Labels
werden jetzt zusammen aufgerufen.

- [ ] **Step 4: Tests laufen lassen — müssen GREEN sein**

```bash
python -m pytest tests/test_gcode_generator.py -v
```

Erwartet: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pa_analyzer/gcode_generator.py tests/test_gcode_generator.py
git commit -m "$(cat <<'EOF'
gcode_generator: Speed/Accel-Header in oberster Layer

Zwei hochkant rotierte Header-Spalten (Speed, Accel) ganz links auf
der Top-Bar, vor den PA-Labels. Größere Glyph-Höhe (1 mm vs. 0.7 mm)
für Header-Effekt. accel=0 → Accel-Spalte entfällt (sonst stünde "0"
als irreführender Wert).

Damit dokumentiert sich der Druck selbst: aus dem Foto kann man die
Test-Bedingungen ablesen (Reproduzierbarkeit).
EOF
)"
```

---

## Task 11: Config — [generator]-Sektion

**Files:**
- Modify: `src/pa_analyzer/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Failing-Tests anhängen**

```python
# Am Ende von tests/test_config.py anhängen:

def test_load_config_parst_generator_sektion(tmp_path):
    cfg_path = tmp_path / "test.conf"
    cfg_path.write_text(
        "[macros]\n"
        "start_gcode = PRINT_START\n"
        "[generator]\n"
        "speed_print = 180\n"
        "accel = 3000\n",
        encoding="utf-8")
    cfg = load_config(cfg_path)
    assert cfg.speed_print == 180.0
    assert cfg.accel == 3000.0


def test_load_config_generator_sektion_optional(tmp_path):
    cfg_path = tmp_path / "test.conf"
    cfg_path.write_text(
        "[macros]\n"
        "start_gcode = PRINT_START\n",
        encoding="utf-8")
    cfg = load_config(cfg_path)
    assert cfg.speed_print is None
    assert cfg.accel is None


def test_load_config_generator_kaputte_zahl_wirft_value_error(tmp_path):
    cfg_path = tmp_path / "test.conf"
    cfg_path.write_text(
        "[macros]\n"
        "start_gcode = PRINT_START\n"
        "[generator]\n"
        "speed_print = nicht-eine-zahl\n",
        encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(cfg_path)


def test_load_config_generator_teilweise(tmp_path):
    # speed_print gesetzt, accel weggelassen
    cfg_path = tmp_path / "test.conf"
    cfg_path.write_text(
        "[macros]\n"
        "start_gcode = PRINT_START\n"
        "[generator]\n"
        "speed_print = 150\n",
        encoding="utf-8")
    cfg = load_config(cfg_path)
    assert cfg.speed_print == 150.0
    assert cfg.accel is None
```

(`from pa_analyzer.config import load_config` und `import pytest` sind
in test_config.py vermutlich schon importiert; falls nicht, ergänzen.)

- [ ] **Step 2: Tests laufen lassen — müssen RED sein**

```bash
python -m pytest tests/test_config.py::test_load_config_parst_generator_sektion -v
```

Erwartet: FAIL (`AttributeError: 'Config' object has no attribute 'speed_print'`).

- [ ] **Step 3: Config + load_config erweitern**

In `src/pa_analyzer/config.py`, im `@dataclass(frozen=True) class
Config:` ergänzen (nach dem `cooldown_in_end_macro`-Feld):

```python
    # Generator-Overrides (None = GeneratorParams-Default greift)
    speed_print: float | None = None
    accel: float | None = None
```

In `load_config()`, vor dem `return Config(...)` einfügen:

```python
    def _get_float(section: str, option: str) -> float | None:
        """Liest ein optionales Float-Feld. Fehlt es / ist leer → None.
        Ungültige Werte → ValueError (wrap durch das zentrale Try-Catch)."""
        raw = parser.get(section, option, fallback=None)
        if raw is None or not raw.strip():
            return None
        try:
            return float(raw.strip())
        except ValueError as exc:
            raise ValueError(
                f"Konfiguration unlesbar: {path} "
                f"([{section}] {option} = {raw!r} ist keine Zahl)") from exc
```

Im `return Config(...)`-Block zwei Felder ergänzen:

```python
        speed_print=_get_float("generator", "speed_print"),
        accel=_get_float("generator", "accel"),
```

- [ ] **Step 4: Tests laufen lassen — müssen GREEN sein**

```bash
python -m pytest tests/test_config.py -v
```

Erwartet: alle 4 neuen + bestehende PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pa_analyzer/config.py tests/test_config.py
git commit -m "$(cat <<'EOF'
config: [generator]-Sektion mit speed_print + accel

Optionale Felder. None = nicht gesetzt → GeneratorParams-Default
greift. Kaputte Zahlen werfen ValueError mit klarer Pfad-Angabe.
Extension-Point für weitere Generator-Defaults (TODO [mittel]
"Generator-Defaults aus pa_analyzer.conf"): kann Feld für Feld
nachgezogen werden, ohne dass die Sektion sich strukturell ändert.
EOF
)"
```

---

## Task 12: CLI — --speed und --accel mit Override-Hierarchie

**Files:**
- Modify: `src/pa_analyzer/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Failing-Tests anhängen**

```python
# Am Ende von tests/test_cli.py anhängen:

def test_generate_honoriert_cli_speed_und_accel(tmp_path, minimal_conf,
                                                  capsys):
    gcode_path = tmp_path / "out.gcode"
    from pa_analyzer.cli import main
    main([
        "--config", str(minimal_conf),
        "generate", "-o", str(gcode_path),
        "--speed", "150",
        "--accel", "2500",
    ])
    gc = gcode_path.read_text(encoding="utf-8")
    # speed_print=150 → F-Werte im G1-Print mit F9000 (150*60)
    assert " F9000" in gc, "CLI --speed kommt nicht im GCode an"
    # accel=2500 → SET_VELOCITY_LIMIT ACCEL=2500
    assert "SET_VELOCITY_LIMIT ACCEL=2500" in gc


def test_generate_zieht_speed_accel_aus_config(tmp_path, capsys):
    cfg = tmp_path / "test.conf"
    cfg.write_text(
        "[macros]\nstart_gcode = PRINT_START\n"
        "[generator]\nspeed_print = 80\naccel = 1500\n",
        encoding="utf-8")
    gcode_path = tmp_path / "out.gcode"
    from pa_analyzer.cli import main
    main(["--config", str(cfg), "generate", "-o", str(gcode_path)])
    gc = gcode_path.read_text(encoding="utf-8")
    assert " F4800" in gc  # 80 * 60
    assert "SET_VELOCITY_LIMIT ACCEL=1500" in gc


def test_generate_cli_ueberschreibt_config(tmp_path, capsys):
    cfg = tmp_path / "test.conf"
    cfg.write_text(
        "[macros]\nstart_gcode = PRINT_START\n"
        "[generator]\nspeed_print = 80\naccel = 1500\n",
        encoding="utf-8")
    gcode_path = tmp_path / "out.gcode"
    from pa_analyzer.cli import main
    main([
        "--config", str(cfg), "generate", "-o", str(gcode_path),
        "--speed", "200",  # überschreibt Config-80
    ])
    gc = gcode_path.read_text(encoding="utf-8")
    assert " F12000" in gc       # 200*60, CLI hat gewonnen
    assert "SET_VELOCITY_LIMIT ACCEL=1500" in gc  # Accel kam aus Config
```

- [ ] **Step 2: Tests laufen lassen — müssen RED sein**

```bash
python -m pytest tests/test_cli.py::test_generate_honoriert_cli_speed_und_accel -v
```

Erwartet: FAIL (`unrecognized arguments: --speed 150`).

- [ ] **Step 3: argparse-Args + gen_overrides erweitern**

In `src/pa_analyzer/cli.py`, im `_build_parser()` im
`g`-Sub-Parser-Block (vor `g.set_defaults(func=_cmd_generate)`):

```python
    g.add_argument("--speed", type=float, default=None,
                   help="Druck-Geschwindigkeit in mm/s (Default: aus "
                        "pa_analyzer.conf [generator], sonst 100)")
    g.add_argument("--accel", type=float, default=None,
                   help="Beschleunigung in mm/s² (Default: aus "
                        "pa_analyzer.conf [generator], sonst 2000; "
                        "0 = nicht emittieren)")
```

In `_cmd_generate()`, im `gen_overrides`-Block:

```python
    # CLI > Config > GeneratorParams-Default.
    if args.speed is not None:
        gen_overrides["speed_print"] = args.speed
    elif cfg.speed_print is not None:
        gen_overrides["speed_print"] = cfg.speed_print

    if args.accel is not None:
        gen_overrides["accel"] = args.accel
    elif cfg.accel is not None:
        gen_overrides["accel"] = cfg.accel
```

- [ ] **Step 4: Tests laufen lassen — müssen GREEN sein**

```bash
python -m pytest tests/test_cli.py -v
```

Erwartet: alle PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pa_analyzer/cli.py tests/test_cli.py
git commit -m "$(cat <<'EOF'
cli: --speed und --accel mit Override-Hierarchie CLI > Config > Default

CLI-Args mit Default=None (Sentinel) erlauben Trennung "User hat
explizit gesetzt" vs. "Default greift". Wenn CLI None und Config-
Feld nicht None → Config-Wert. Sonst GeneratorParams-Default.
EOF
)"
```

---

## Task 13: Klipper-Macro — SPEED= und ACCEL= Parameter

**Files:**
- Modify: `klipper/pa_calibrate.cfg`
- Modify: `tests/test_klipper_macro.py`

- [ ] **Step 1: Failing-Tests anhängen**

```python
# Am Ende von tests/test_klipper_macro.py anhängen:

def test_macro_uebergibt_speed_und_accel():
    # PA_CALIBRATE muss SPEED= und ACCEL= optional annehmen und an
    # pa_generate weiterreichen. Leere Defaults verhindern, dass eine
    # leere Klammer-Substitution dem CLI-Parser eine ungültige Zahl
    # zuschickt.
    text = _CFG.read_text(encoding="utf-8")
    assert "params.SPEED" in text
    assert "params.ACCEL" in text
    assert "--speed" in text
    assert "--accel" in text
```

- [ ] **Step 2: Tests laufen lassen — müssen RED sein**

```bash
python -m pytest tests/test_klipper_macro.py::test_macro_uebergibt_speed_und_accel -v
```

Erwartet: FAIL.

- [ ] **Step 3: Macro erweitern**

In `klipper/pa_calibrate.cfg` den `gcode:`-Block der `PA_CALIBRATE`-
Sektion ersetzen:

```ini
gcode:
    {% set pa_start = params.PA_START|default(0.0)|float %}
    {% set pa_end   = params.PA_END|default(0.08)|float %}
    {% set pa_step  = params.PA_STEP|default(0.005)|float %}
    {% set temp     = params.TEMP|default(240.0)|float %}
    {% set bed_temp = params.BED_TEMP|default(60.0)|float %}
    {% set flow     = params.FLOW|default(1.0)|float %}
    {% set fan      = params.FAN|default(1.0)|float %}
    {% set speed    = params.SPEED|default("") %}
    {% set accel    = params.ACCEL|default("") %}
    {% set speed_arg = " --speed " ~ speed if speed != "" else "" %}
    {% set accel_arg = " --accel " ~ accel if accel != "" else "" %}
    RUN_SHELL_COMMAND CMD=pa_generate PARAMS="--pa-start {pa_start} --pa-end {pa_end} --pa-step {pa_step} --temp {temp} --bed-temp {bed_temp} --flow {flow} --fan {fan}{speed_arg}{accel_arg}"
    # FILENAME muss zum Basename von gcode_path in pa_analyzer.json passen.
    SDCARD_PRINT_FILE FILENAME=pa_calibration.gcode
```

Begründung für die Default-Logik: Leerer String + nur dann
`--speed VALUE` anhängen, wenn nicht-leer. So kann der User
`PA_CALIBRATE SPEED=180` rufen, OHNE dass bei leerem Aufruf
`--speed ` (leerer Wert) den CLI-Parser bricht.

- [ ] **Step 4: Tests laufen lassen — müssen GREEN sein**

```bash
python -m pytest tests/test_klipper_macro.py -v
```

Erwartet: PASS.

- [ ] **Step 5: Commit**

```bash
git add klipper/pa_calibrate.cfg tests/test_klipper_macro.py
git commit -m "$(cat <<'EOF'
klipper: SPEED= und ACCEL= als PA_CALIBRATE-Parameter

Beide optional (leerer Default). Werden nur an pa_generate
durchgereicht, wenn nicht-leer — sonst greift Config bzw.
GeneratorParams-Default. Verhindert, dass leere Substitution
dem CLI-Parser eine ungültige Zahl zuschickt.
EOF
)"
```

---

## Task 14: example.conf — [generator]-Sektion + Kommentare

**Files:**
- Modify: `pa_analyzer.example.conf`

(Kein neuer Test — diese Datei wird von `install.sh` als Template
kopiert, ihre Korrektheit prüft `test_install_script.py` nur per
Inhalts-Substring. Bei Bedarf kann man einen Smoke-Test ergänzen,
aber YAGNI.)

- [ ] **Step 1: Sektion an `pa_analyzer.example.conf` anhängen**

Am Ende von `pa_analyzer.example.conf` ergänzen:

```ini

# =============================================================================
# Optional: Generator-Test-Parameter überschreiben
# =============================================================================
# Defaults aus dem Code: speed_print = 100 mm/s, accel = 2000 mm/s²
# (konservativ, funktioniert auf der breiten Hobby-Drucker-Basis).
#
# Werden überschrieben durch SPEED=/ACCEL= im PA_CALIBRATE-Aufruf
# bzw. --speed/--accel auf der Kommandozeile. Override-Hierarchie:
#   CLI  >  Macro-Parameter  >  diese .conf  >  Code-Default
#
# Wer mit Input-Shaping schneller druckt (z.B. 180 mm/s @ 3000 mm/s²),
# trägt hier seine Standard-Test-Werte ein — dann reicht
# PA_CALIBRATE (ohne SPEED=/ACCEL=) im Klipper-Terminal.
#
# Beispiel-Override für einen schnelleren Drucker:
# [generator]
# speed_print = 180
# accel = 3000
```

- [ ] **Step 2: Commit**

```bash
git add pa_analyzer.example.conf
git commit -m "$(cat <<'EOF'
example.conf: [generator]-Sektion mit Speed/Accel-Override dokumentiert

Optionaler Block mit kommentiertem Beispiel-Override (180/3000 für
schnellere Drucker). Defaults 100/2000 bleiben aus dem Code-Default,
wenn die Sektion fehlt.
EOF
)"
```

---

## Task 15: Integration — orientation.py-Test mit Generator-Output

**Files:**
- Modify: `tests/test_orientation.py`

- [ ] **Step 1: Failing-Test anhängen**

```python
# Am Ende von tests/test_orientation.py anhängen:

def test_orientation_funktioniert_mit_generator_output_synthetisch():
    """Generiert einen Pattern-GCode, rendert ihn als binäre Bitmap,
    und prüft, dass pick_orientation eine eindeutige Rotation findet
    (best_ratio > 1.5 = klares Top-Bar-Signal über Chevron-Band)."""
    import numpy as np

    from pa_analyzer.gcode_generator import GeneratorParams, generate
    from pa_analyzer.gcode_parser import parse
    from pa_analyzer.orientation import pick_orientation

    gcode = generate(GeneratorParams())
    model = parse(gcode)

    # Synthetisches Bild rendern: 800x600, Pattern-Bewegungen als
    # weiße Pixel auf schwarzem Hintergrund. Skalierung so, dass
    # Pattern ins Bild passt.
    img_w, img_h = 800, 600
    mask = np.zeros((img_h, img_w), dtype=np.uint8)
    # Pattern-Bounding-Box aus dem Modell
    lo, hi = model.content_bounds
    scale = min(img_w / (hi.x - lo.x), img_h / (hi.y - lo.y)) * 0.8
    cx, cy = img_w // 2, img_h // 2
    pcx, pcy = (lo.x + hi.x) / 2, (lo.y + hi.y) / 2

    def to_px(x: float, y: float) -> tuple[int, int]:
        return (int(cx + (x - pcx) * scale),
                int(cy - (y - pcy) * scale))  # Y invertiert (Bild oben)

    # Wir parsen den GCode noch einmal, um alle extrudierenden Moves
    # als Linien ins mask zu zeichnen.
    import re
    import cv2
    pos = (0.0, 0.0)
    for line in gcode.splitlines():
        if not line.startswith("G1"):
            continue
        x_match = re.search(r"X([\d.-]+)", line)
        y_match = re.search(r"Y([\d.-]+)", line)
        e_match = re.search(r"\sE([\d.-]+)", line)
        x = float(x_match.group(1)) if x_match else pos[0]
        y = float(y_match.group(1)) if y_match else pos[1]
        if e_match and (x_match or y_match):
            p1 = to_px(*pos)
            p2 = to_px(x, y)
            cv2.line(mask, p1, p2, 255, thickness=2)
        pos = (x, y)

    # Quad-Detection: einfaches Bounding-Rect der weißen Pixel.
    ys, xs = np.where(mask > 0)
    quad = np.array([
        [xs.min(), ys.min()],
        [xs.max(), ys.min()],
        [xs.max(), ys.max()],
        [xs.min(), ys.max()],
    ], dtype=np.float32)

    best_rot, best_ratio = pick_orientation(mask, quad, model)

    # Erwartung: Top-Bar liefert klares Dichte-Signal.
    assert best_ratio > 1.5, (
        f"best_ratio={best_ratio:.2f} — Top-Bar wirkt nicht als "
        "Dichte-Anker (Top/Mid-Verhältnis zu schwach).")
```

- [ ] **Step 2: Test laufen lassen — sollte GREEN sein**

```bash
python -m pytest tests/test_orientation.py::test_orientation_funktioniert_mit_generator_output_synthetisch -v
```

Erwartet: PASS (Top-Bar ist jetzt im Generator-Output, also liefert
das Dichte-Verhältnis ein klares Signal).

**Falls FAIL:** Das wäre eine echte Erkenntnis — entweder ist die
Top-Bar-Dichte doch zu schwach (dann: Top-Bar-Höhe erhöhen, oder
mehrere Layer dicker drucken), oder der Render-Helper hat einen
Geometrie-Bug. Im Plan-Sinne: ist der Test rot, ist der Plan rot —
nicht weitermachen, sondern debuggen.

- [ ] **Step 3: Commit**

```bash
git add tests/test_orientation.py
git commit -m "$(cat <<'EOF'
test_orientation: Integrations-Test mit echtem Generator-Output

Generiert einen Pattern-GCode, rendert die extrudierenden Moves
als Binär-Maske, und prüft, dass orientation.pick_orientation
ein eindeutiges Dichte-Verhältnis (> 1.5) findet. Schließt damit
den Mismatch, der beim Live-Test 1 die schlechte Konfidenz
verursacht hat (Generator hatte keinen Top-Bar, orientation
erwartete einen).

Spec: docs/specs/2026-05-24-pattern-markierungen-und-speed-accel.md §CV-Pipeline-Auswirkungen
EOF
)"
```

---

## Task 16: Round-Trip-Test verifizieren

**Files:**
- Verify: `tests/test_roundtrip.py`
- Optional: `src/pa_analyzer/gcode_generator.py` (Marker-Kommentar)
- Optional: `src/pa_analyzer/gcode_parser.py` (Marker-Filter)

- [ ] **Step 1: Bestehenden Round-Trip-Test laufen lassen**

```bash
python -m pytest tests/test_roundtrip.py -v
```

Erwartet: PASS.

Falls PASS → direkt zu Step 5 (kein Commit nötig, nichts geändert).

- [ ] **Step 2: Bei FAIL — Marker-Kommentar in Generator**

Falls der Parser die neuen Geometrien als zusätzliche PA-Gruppen oder
Frame-Boxes interpretiert: in `src/pa_analyzer/gcode_generator.py`
vor jedem Label-/Top-Bar-/Anker-Block einen Marker-Kommentar
emittieren:

```python
        out.append("; PA_ANALYZER_INTERNAL_GEOMETRY")
        out.extend(_top_bar_block(...))
        out.append("; PA_ANALYZER_INTERNAL_GEOMETRY_END")
```

(Analog für Anker und Labels.)

- [ ] **Step 3: Bei FAIL — Marker-Filter im Parser**

In `src/pa_analyzer/gcode_parser.py` einen Filter ergänzen, der
G1-Bewegungen zwischen `PA_ANALYZER_INTERNAL_GEOMETRY`-Markern
überspringt (Detail: Implementierung hängt von der konkreten
Parser-Architektur ab — siehe `gcode_parser.py`-Modul).

- [ ] **Step 4: Bei Änderungen — Tests laufen lassen + Commit**

```bash
python -m pytest -q
```

Erwartet: alle PASS, inkl. Round-Trip.

```bash
git add src/pa_analyzer/gcode_generator.py src/pa_analyzer/gcode_parser.py
git commit -m "$(cat <<'EOF'
parser: interne Generator-Geometrien filtern (Marker-Kommentar)

Top-Bar, Anker, Labels werden nach den Marker-Kommentaren
PA_ANALYZER_INTERNAL_GEOMETRY[_END] im Generator gekapselt.
Parser überspringt G1-Moves innerhalb dieser Marker, sodass die
PA-Gruppen-Detektion und Frame-Box-Erkennung weiterhin nur die
"echten" Pattern-Elemente sehen. Round-Trip-Test bleibt grün.
EOF
)"
```

- [ ] **Step 5: Wenn ohne Änderung GREEN → Erkenntnis notieren**

Wenn der bestehende Round-Trip-Test direkt PASS war: kurzer
Hinweis-Kommentar im PR/Commit oder in `TODO.md`, dass die
Hypothese aus der Spec (Parser bleibt unverändert) bestätigt
wurde. Keine Code-Änderung nötig.

---

## Task 17: TODO.md + README erweitern

**Files:**
- Modify: `TODO.md`
- Modify: `README.md`

- [ ] **Step 1: TODO.md aktualisieren**

In `TODO.md` den Eintrag `### [demnächst] Druck-Geschwindigkeit und
Beschleunigung als Parameter` auf `[erledigt]` umstellen:

```markdown
### [erledigt] Druck-Geschwindigkeit und Beschleunigung als Parameter

Behoben in Commit `<SHA>` (24.05.2026). Speed (`--speed`/`SPEED=`)
und Accel (`--accel`/`ACCEL=`) sind CLI-, Macro- und Config-Parameter.
Accel wird als `SET_VELOCITY_LIMIT ACCEL=<n> ACCEL_TO_DECEL=<n/2>`
vor dem Pattern emittiert. Beide Werte werden auf der Top-Bar
mitgedruckt (Reproduzierbarkeit). Defaults konservativ: 100 mm/s
und 2000 mm/s². Override via `[generator]`-Sektion in der `.conf`.
```

Den Eintrag `### [mittel] Generator-Defaults aus der pa_analyzer.conf
ziehen` um einen Hinweis ergänzen:

```markdown
### [mittel] Generator-Defaults aus der `pa_analyzer.conf` ziehen

(unverändert)

**Update 24.05.2026 (Commit `<SHA>`):** Die `[generator]`-Sektion
existiert jetzt als Extension-Point, mit `speed_print` und `accel`
als ersten freigegebenen Feldern. Weitere `GeneratorParams`-Felder
können nach demselben Schema (CLI > Macro > Config > Default)
nachgezogen werden, wenn Bedarf entsteht.
```

`<SHA>` wird beim Commit gefüllt — siehe Step 3.

- [ ] **Step 2: README erweitern**

In `README.md` das Klipper-Macro-Beispiel um die neuen Parameter
erweitern (suche nach `PA_CALIBRATE` im README):

```markdown
**Optional: Test-Parameter überschreiben**

```
PA_CALIBRATE SPEED=180 ACCEL=3000
```

Speed und Accel werden zusätzlich oben auf das Pattern aufgedruckt
(Reproduzierbarkeit). Defaults: 100 mm/s @ 2000 mm/s² (konservativ).
Für dauerhafte Override-Werte siehe die `[generator]`-Sektion in
`pa_analyzer.example.conf`.
```

- [ ] **Step 3: Commit (mit nachträglich eingefügtem SHA)**

```bash
git add TODO.md README.md
git commit -m "docs: TODO als [erledigt] markieren + README mit Speed/Accel-Beispiel"
# Den frischen SHA in TODO.md nachtragen:
SHA=$(git rev-parse HEAD)
sed -i "s/<SHA>/$SHA/g" TODO.md
git add TODO.md
git commit --amend --no-edit
```

(Alternativ: SHA-Platzhalter im ersten Commit lassen und in einem
Follow-up-Commit ergänzen — der amend-Pfad oben ist nur eine
Bequemlichkeit.)

---

## Task 18: Live-Test auf dem Pi (Hardware, User-Freigabe)

**Files:** keine im Repo — Hardware-Validierung.

**Vorbedingung:** Tasks 1-17 alle grün, `python -m pytest -q` liefert
exit 0.

- [ ] **Step 1: Push auf GitHub**

```bash
git push origin main
```

- [ ] **Step 2: Pi-Update**

Auf dem Pi (via plink — siehe `MEMORY.md` für Connection-Details):

```bash
cd /home/pi/pa-pattern-webcam-analyzer
git pull
./install.sh
```

Erwartet: `install.sh` aktualisiert die `.cfg`-Datei und die
`pa_analyzer.example.conf` im Klipper-Config-Ordner (idempotent,
ohne `pa_analyzer.conf` zu überschreiben).

- [ ] **Step 3: User-eigene .conf um [generator]-Sektion ergänzen**

User soll `pa_analyzer.conf` (im Klipper-Config-Ordner) editieren
und anhängen:

```ini
[generator]
speed_print = 180
accel = 3000
```

(Die Werte sind die für seinen Drucker realistischen.)

- [ ] **Step 4: Klipper restarten**

`FIRMWARE_RESTART` in Mainsail/Fluidd oder via `plink`:

```bash
curl -X POST http://localhost:7125/printer/restart
```

- [ ] **Step 5: User-Freigabe für Drucktest einholen**

**WICHTIG:** Vor dem Druck den User explizit fragen ("Bett frei?
Wir drucken jetzt das neue Pattern."). Iron Law aus der globalen
`CLAUDE.md` zu Hardware-Tests.

- [ ] **Step 6: PA_CALIBRATE im Klipper-Terminal**

```
PA_CALIBRATE
```

(Ohne SPEED/ACCEL — User hat sie in der Config hinterlegt.)

Erwartet:
- Pattern wird gedruckt (~10 min)
- Sieht aus wie in `docs/specs/2026-05-24-pattern-markierungen-layout.svg`
  (Solid-Top-Bar mit hochkant rotierten "180", "3000" und PA-Werten)
- Tool wertet automatisch aus
- JSON-Report unter `/home/pi/printer_data/pa_report.json`

- [ ] **Step 7: Konfidenz vergleichen**

Vorher (Live-Test 1, 23.05.2026): `confidence = 0.16` (16 %).

Jetzt erwartet: deutlich höher (Hypothese: > 50 %). Falls weiterhin
unter 30 %: das ist ein neuer Erkenntnis-Punkt — entweder Webcam-
Auflösung ist der tatsächliche Engpass (siehe Spec §Out-of-Scope
„Effektive Webcam-Auflösung loggen"), oder ein anderes Problem.
In dem Fall: zurück zur `systematic-debugging`-Skill.

- [ ] **Step 8: Foto des gedruckten Patterns ablegen**

Falls erfolgreich: das Foto in `reference/` ablegen (analog zu
`pa_snap.jpg`) als neue Referenz für künftige Tests. Optional:
`reference/README.md` um den neuen Snapshot ergänzen.

```bash
# Pfad-Vorschlag: reference/pa_snap_v2_with_markers.jpg
# (Im git commit als "test: neuer Referenz-Snapshot mit Markierungen")
```

---

## Self-Review

### 1. Spec-Coverage

Spec-Abschnitt → Plan-Task:

| Spec | Plan |
|---|---|
| Glyphen-Engine `GLYPHS`-Dict | Task 1 |
| Glyphen-Engine `render_label_gcode` rotation=0 | Task 2 |
| Glyphen-Engine `render_label_gcode` rotation=90 | Task 3 |
| Neue `GeneratorParams`-Felder | Task 4 |
| Pattern-Geometrie mit Top-Bar | Task 5 |
| Solid-Top-Bar in allen Layern | Task 6 |
| Anker-Marker an Frame-Linkskante | Task 7 |
| `SET_VELOCITY_LIMIT` + accel=0 Edge-Case | Task 8 |
| PA-Labels in oberster Layer | Task 9 |
| Speed/Accel-Header in oberster Layer | Task 10 |
| Config `[generator]`-Sektion | Task 11 |
| CLI `--speed`/`--accel` mit Hierarchie | Task 12 |
| Klipper-Macro `SPEED=`/`ACCEL=` | Task 13 |
| `example.conf` mit `[generator]`-Sektion | Task 14 |
| orientation.py-Integrations-Test | Task 15 |
| Round-Trip-Test bleibt grün (oder Marker-Filter) | Task 16 |
| TODO.md + README aktualisieren | Task 17 |
| Live-Test auf dem Pi | Task 18 |

**Spec-Coverage:** vollständig.

### 2. Placeholder-Scan

- "TBD", "TODO", "fill in" — keine
- "Add appropriate error handling" — keine
- "Write tests for the above" — alle Tests sind konkret geschrieben
- "Similar to Task N" — keine (Code ist überall ausgeschrieben)
- "Implement later" — Task 16 hat einen "Optional bei FAIL"-Pfad, der
  bewusst zwei Wege beschreibt — kein Placeholder.

### 3. Type-/Method-Konsistenz

- `render_label_gcode(text, x, y, glyph_height, glyph_width, glyph_gap,
  line_width, layer_height, filament_diameter, extrusion_multiplier,
  print_speed, travel_speed, rotation)` — Signature konsistent in
  Tasks 2, 3, 9, 10.
- `GeneratorParams`-Felder konsistent benannt: `label_glyph_height`,
  `label_glyph_width`, `label_glyph_gap` (Task 4, 9), `header_glyph_height`,
  `header_glyph_width` (Task 4, 10), `accel` (Task 4, 8, 10, 11, 12).
- `Config.speed_print: float | None` (Task 11), `Config.accel: float | None`
  (Task 11), gleicher Default-Pfad in CLI Task 12.
- `SET_VELOCITY_LIMIT ACCEL=<n> ACCEL_TO_DECEL=<n/2>` — gleiche
  String-Form in Spec, Task 8, Task 12.

**Konsistenz:** OK.

### 4. Spec-Detail-Lücken

Eine Stelle in der Spec war locker formuliert: die genaue Position
der Labels auf der Top-Bar (innerhalb vs. außerhalb). Im Plan ist
das jetzt präzisiert (Task 9, `label_y_top = top_bar_y_high - 0.5`
— d.h. Labels stehen 0.5 mm unterhalb der oberen Top-Bar-Kante und
laufen nach unten in die Bar hinein).

---

## Plan-Übergabe

Plan komplett und gespeichert unter
`docs/plans/2026-05-24-pattern-markierungen-und-speed-accel.md`.

Zwei Execution-Optionen:

1. **Subagent-Driven (empfohlen)** — frischer Subagent pro Task,
   zweistufiges Review (Spec-Compliance + Code-Qualität) zwischen
   den Tasks, schnelle Iteration.

2. **Inline-Execution** — Tasks in dieser Session via
   `superpowers:executing-plans` ausführen, Batch-Execution mit
   Checkpoints.

**Welcher Ansatz?**
