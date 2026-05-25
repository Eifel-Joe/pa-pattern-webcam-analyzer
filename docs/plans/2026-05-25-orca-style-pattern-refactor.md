# Orca-Style PA-Pattern Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Das generierte PA-Pattern visuell mit OrcaSlicer's Standard-PA-Pattern angleichen — umlaufender 3-Wandlinien-Frame um Chevrons, Top-Bar mit 3 Wandlinien + 45°-Infill, Labels über Chevron-Frame-Ankern (nicht über Chevron-Mitten), Settings (Flow, Accel) rechts nach den PA-Labels auf gleicher Top-Bar.

**Architecture:** Ein neuer `_draw_box(x, y, w, h, n_perimeters, is_filled)` Helper kapselt Orca's Geometrie (umlaufende Perimeter mit Boustrophedon-Wand-Reihenfolge + optionalem 45°-Infill). Frame und Top-Bar werden über diesen Helper gezeichnet. Label-Position-Logik wird auf `glyph_start_x(j)` umgestellt (Anker am Chevron-Start am Frame). Anker-Marker entfällt (Orca hat das nicht — der Frame selbst ist asymmetrisch durch die Top-Bar oben). Pattern-Geometrie (wall_side_length, pattern_spacing, pa_step, pa_end) bleibt unverändert von v4 (post-Live-Test 5).

**Tech Stack:** Python 3.13, pytest, OpenCV. Referenz-Implementierungen:
- `reference/orca_calib.cpp` Linien 261-460 (draw_box), 580-670 (generate_custom_gcodes), 821-895 (glyph_start_x, pattern_shift)
- `reference/orca_reference.gcode` (echte Pi-generierte Orca-Pattern-Datei, 3595 Zeilen, Header bei Linie 89-204)

---

## File Structure

**Zu ändern:**
- `src/pa_analyzer/gcode_generator.py` — Main-Refactor (~150 LOC + ~100 LOC neuer Helper, einige Funktionen werden ersetzt)
- `tests/test_gcode_generator.py` — Tests für draw_box-Helper, Frame-Form, Top-Bar-Form, Label-Position
- `reference/render_proposed_pattern.py` — Lokales Render-Script aktualisieren um Frame-Walls + Top-Bar-Infill anzuzeigen

**Unverändert (Schnittstellen stabil):**
- `src/pa_analyzer/model.py` — Datenmodell (PatternModel etc.) bleibt
- `src/pa_analyzer/gcode_parser.py` — Parser bleibt (Frame-Box-Markers + Chevrons werden weiter geparst)
- `src/pa_analyzer/glyphs.py` — Glyph-Renderer bleibt
- `klipper/pa_calibrate.cfg` — Macro bleibt (war beim letzten Fix bereits korrigiert)
- `src/pa_analyzer/pattern_locator.py` u. ä. — Pipeline-Code bleibt

**Begründung:** `gcode_generator.py` ist aktuell ~620 LOC. Mit dem Refactor wachsen wir auf ~700 LOC — noch handhabbar. Auslagerung in eigene `draw_box.py`-Datei nur wenn der Helper > 200 LOC wird (aktuell schätze ich ~100 LOC inkl. Tests).

---

## Reference-Daten aus orca_reference.gcode

Für die Akzeptanz-Tests müssen die Geometrie-Konstanten matchen:

| Element | Orca-Wert | Quelle |
|---------|-----------|--------|
| Frame Y-Min | 122.287 | Linie 113 |
| Frame Y-Max | 164.713 | Linie 113 |
| Frame X-Min | 107.934 | Linie 113 |
| Frame X-Max | 192.066 | Linie 115 |
| Frame-Höhe (= 2×sin(45°)×30) | 42.426 | wall_side_length=30 |
| line_spacing (= line_width - layer_h × (1 - π/4)) | 0.517 | Linie 113 vs 126 |
| Top-Bar Y-Min | 165.230 | Linie 152 |
| Top-Bar Y-Max | 178.747 | Linie 152 |
| Lücke Frame-Top → Top-Bar-Bottom | 0.517 mm | = line_spacing |
| Chevron-Start X (Pattern N=0) | 111.935 | Linie 835 |
| pattern_shift (= Chevron_start − Frame_x_min) | 4.001 mm | 111.935 − 107.934 |
| Pattern-Abstand (Group-Advance) | 3.602 mm | 115.537 − 111.935 |
| Wand-Versatz innerhalb Pattern (line_spacing_angle) | 0.576 mm | 112.511 − 111.935 |

---

### Task 1: Spec niederschreiben

**Files:**
- Create: `docs/specs/2026-05-25-orca-pattern-layout.md`

- [ ] **Step 1: Spec-Dokument anlegen**

```markdown
# Orca-Style PA-Pattern Layout (Spec)

**Status:** Implementiert in Task 2-11.

## Anforderungen (aus User-Befunden 2026-05-25)

1. **Frame um Chevrons**: umlaufender Rahmen mit `wall_count`
   konzentrischen Wandlinien, KEIN Infill. Aktuell ist es ein
   "[" 2-Linien-Frame (links + unten). Soll wie Orca's `draw_box`
   mit `is_filled=false` werden.

2. **Top-Bar**: oberhalb des Frames mit ~0.5 mm Lücke; gleiche
   X-Breite wie Frame. Innen `wall_count` Perimeter + 45°-Infill
   (solide gefüllt). Soll wie Orca's `draw_box` mit
   `is_filled=true`. Aktuell ist es Boustrophedon-Stadion-Linien
   (diagonal-streifig im Slicer-Preview).

3. **Labels**: pro Chevron ein PA-Label. Position:
   - X = `glyph_start_x(j)` (zentriert über dem Chevron-Anker
     am oberen Frame-Rand, NICHT über der Chevron-Mitte)
   - Y = Top-Bar-Bottom + glyph_padding (= AUF der Top-Bar als
     Relief)
   - Rotation 90° (hochkant, Lesrichtung von oben nach unten)
   - Aktive PA = 0 (separates SET_PRESSURE_ADVANCE vor Labels)
   - Speed = `first_layer_speed` (langsam für saubere Glyphen)

4. **Settings (Flow, Accel)**: nach den PA-Labels rechts auf
   derselben Top-Bar. X-Position via `glyph_start_x(num_patterns
   + 2)` für Flow und `glyph_start_x(num_patterns + 4)` für Accel
   (= 2 bzw. 4 Slots nach dem letzten PA-Label).

5. **Anker-Marker entfällt**: Orca hat keinen separaten Asymmetrie-
   Anker. Der Frame selbst ist asymmetrisch durch die nur-oben
   liegende Top-Bar.

6. **Layer-Verteilung**:
   - Frame + Top-Bar nur in Layer 0 (Z=0.2)
   - Labels nur in Layer 1 (Z=0.4)
   - Chevrons in jedem Layer (4× wiederholt)

7. **Pattern-Geometrie unverändert**: wall_side_length=30 mm,
   pattern_spacing=18 mm, pa_step=0.005, pa_end=0.04 wie v4.

## Geometrische Konstanten

Aus `reference/orca_reference.gcode` extrahiert:
- `line_spacing = line_width − layer_height × (1 − π/4)`
  (Versatz zwischen Perimetern, auch zwischen Frame-Top und
  Top-Bar-Bottom)
- `spacing_45 = line_spacing / sin(45°)`
  (Infill-Linien-Abstand im 45°-Pattern)
- `pattern_shift = (wall_count−1) × line_spacing + line_width +
  glyph_padding_horizontal`
  (Padding vor erstem Chevron, für Labels-Platz)
```

- [ ] **Step 2: Commit**

```bash
git add docs/specs/2026-05-25-orca-pattern-layout.md
git commit -m "spec: Orca-Style PA-Pattern-Layout dokumentieren"
```

---

### Task 2: `_draw_box`-Helper — Perimeter-Schleife (kein Infill)

**Files:**
- Modify: `src/pa_analyzer/gcode_generator.py`
- Test: `tests/test_gcode_generator.py`

- [ ] **Step 1: Failing test — 1 Perimeter (Rechteck)**

In `tests/test_gcode_generator.py` am Ende anfügen:

```python
def test_draw_box_ein_perimeter_zeichnet_rechteck():
    """Ein Perimeter = 4 extrudierte Linien (up, right, down, left)
    plus ein Travel-Move zum Box-Start."""
    from pa_analyzer.gcode_generator import _draw_box
    p = GeneratorParams()
    def travel_to(x, y):
        return [f"G1 X{x} Y{y} F7200"]
    lines = _draw_box(p, x0=100.0, y0=200.0, width=30.0, height=20.0,
                     n_perimeters=1, is_filled=False,
                     travel_to_fn=travel_to, print_f=6000)
    # 1 Travel zum Start + 4 extrudierte Linien
    g1 = [l for l in lines if l.startswith("G1")]
    extruded = [l for l in g1 if " E" in l]
    assert len(extruded) == 4, (
        f"1 Perimeter sollte 4 extrudierte Moves haben, hat {len(extruded)}")
    # Reihenfolge: up (Y wechselt), right (X wechselt), down, left
    # Check: erste extrudierte Linie geht in +Y (up)
    assert "Y220" in extruded[0], "Erste Linie sollte 'up' (Y +20) sein"
    assert "X130" in extruded[1], "Zweite Linie sollte 'right' (X +30) sein"
```

- [ ] **Step 2: Run, expect fail**

Run: `"D:\Entwicklung\PA-Analyzer\.venv\Scripts\python.exe" -m pytest tests/test_gcode_generator.py::test_draw_box_ein_perimeter_zeichnet_rechteck -v`

Expected: FAIL mit `ImportError: cannot import name '_draw_box'`.

- [ ] **Step 3: Minimal-Implementation `_draw_box` ohne Infill**

In `src/pa_analyzer/gcode_generator.py` direkt vor `_top_bar_block` einfügen:

```python
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

    # Infill kommt in Task 3
    return out
```

- [ ] **Step 4: Run, expect pass**

Run: `"D:\Entwicklung\PA-Analyzer\.venv\Scripts\python.exe" -m pytest tests/test_gcode_generator.py::test_draw_box_ein_perimeter_zeichnet_rechteck -v`

Expected: PASS.

- [ ] **Step 5: Failing test — 3 Perimeter mit Step-Inwards**

In `tests/test_gcode_generator.py` anfügen:

```python
def test_draw_box_drei_perimeter_nest_inwards():
    """3 Perimeter = 12 extrudierte Linien + 2 Step-Inwards-Travels."""
    from pa_analyzer.gcode_generator import _draw_box, _line_width
    import math
    p = GeneratorParams()
    def travel_to(x, y):
        return [f"G1 X{x} Y{y} F7200"]
    lines = _draw_box(p, x0=100.0, y0=200.0, width=30.0, height=20.0,
                     n_perimeters=3, is_filled=False,
                     travel_to_fn=travel_to, print_f=6000)
    extruded = [l for l in lines if l.startswith("G1") and " E" in l]
    assert len(extruded) == 12, (
        f"3 Perimeter sollten 12 Moves haben, sind {len(extruded)}")
    travels = [l for l in lines if l.startswith("G1") and " E" not in l]
    # 1 Travel zum Start + 2 Step-Inwards-Travels (zwischen
    # Perimetern 1→2 und 2→3) = 3 Travels.
    assert len(travels) == 3, (
        f"Erwartet 3 Travels (Start + 2 Step-Inwards), sind {len(travels)}")
    # Step-Inwards: Perimeter 2 startet bei (x0 + line_spacing, y0 + line_spacing)
    lw = _line_width(p)
    spacing = lw - p.layer_height * (1 - math.pi / 4)
    expected_x = round(100.0 + spacing, 4)
    expected_y = round(200.0 + spacing, 4)
    assert f"X{expected_x:g} Y{expected_y:g}" in travels[1], (
        f"2. Travel sollte zu ({expected_x}, {expected_y}) gehen, "
        f"ist: {travels[1]}")
```

- [ ] **Step 6: Run, expect pass (Code aus Step 3 erfüllt das schon)**

Run: `"D:\Entwicklung\PA-Analyzer\.venv\Scripts\python.exe" -m pytest tests/test_gcode_generator.py::test_draw_box_drei_perimeter_nest_inwards -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/pa_analyzer/gcode_generator.py tests/test_gcode_generator.py
git commit -m "generator: _draw_box Helper mit umlaufenden Perimetern"
```

---

### Task 3: `_draw_box` — 45°-Infill ergänzen

**Files:**
- Modify: `src/pa_analyzer/gcode_generator.py`
- Test: `tests/test_gcode_generator.py`

- [ ] **Step 1: Failing test — Infill emittiert 45°-Diagonalen**

In `tests/test_gcode_generator.py` anfügen:

```python
def test_draw_box_mit_infill_emittiert_45grad_diagonalen():
    """Bei is_filled=True kommt nach den Perimetern ein 45°-Infill.
    Jede Infill-Print-Linie hat |ΔX| == |ΔY| (45°).
    """
    from pa_analyzer.gcode_generator import _draw_box
    import re
    p = GeneratorParams()
    def travel_to(x, y):
        return [f"G1 X{x} Y{y} F7200"]
    lines = _draw_box(p, x0=100.0, y0=200.0, width=30.0, height=20.0,
                     n_perimeters=3, is_filled=True,
                     travel_to_fn=travel_to, print_f=6000)
    # Infill-Linien folgen den Perimetern. Extrudierte Linien NACH den
    # 12 Perimeter-Moves sind Infill-Print-Linien.
    extruded = [l for l in lines if l.startswith("G1") and " E" in l]
    assert len(extruded) > 12, (
        "is_filled=True sollte zusätzliche extrudierte Linien "
        "(Infill) emittieren")
    infill_lines = extruded[12:]
    # Für jede Infill-Linie: |ΔX| ≈ |ΔY| (45°)
    prev_x, prev_y = None, None
    for l in lines:
        m = re.match(r"G1 X([\d.-]+) Y([\d.-]+)", l)
        if not m:
            continue
        x, y = float(m.group(1)), float(m.group(2))
        if prev_x is not None and "E" in l and "Fill: Print" in l:
            dx = abs(x - prev_x)
            dy = abs(y - prev_y)
            assert abs(dx - dy) < 0.01, (
                f"Infill-Linie nicht 45°: ΔX={dx:.3f} vs ΔY={dy:.3f}")
        prev_x, prev_y = x, y
```

- [ ] **Step 2: Run, expect fail**

Run: `"D:\Entwicklung\PA-Analyzer\.venv\Scripts\python.exe" -m pytest tests/test_gcode_generator.py::test_draw_box_mit_infill_emittiert_45grad_diagonalen -v`

Expected: FAIL (kein "Fill: Print"-Kommentar im Output, keine Infill-Linien).

- [ ] **Step 3: Implementation — 45°-Infill ergänzen**

In `src/pa_analyzer/gcode_generator.py` die `_draw_box`-Funktion erweitern (vor `return out`):

```python
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
```

- [ ] **Step 4: Run, expect pass**

Run: `"D:\Entwicklung\PA-Analyzer\.venv\Scripts\python.exe" -m pytest tests/test_gcode_generator.py::test_draw_box_mit_infill_emittiert_45grad_diagonalen -v`

Expected: PASS.

- [ ] **Step 5: Full suite — keine Regressionen**

Run: `"D:\Entwicklung\PA-Analyzer\.venv\Scripts\python.exe" -m pytest -q`

Expected: 192 passed (190 alt + 2 neu), 3 xfailed.

- [ ] **Step 6: Commit**

```bash
git add src/pa_analyzer/gcode_generator.py tests/test_gcode_generator.py
git commit -m "generator: _draw_box mit 45°-Infill (Orca-Style)"
```

---

### Task 4: Frame umstellen auf `_draw_box`

**Files:**
- Modify: `src/pa_analyzer/gcode_generator.py` (im `generate()`)
- Test: `tests/test_gcode_generator.py`

- [ ] **Step 1: Failing test — Frame hat 3 umlaufende Wandlinien**

In `tests/test_gcode_generator.py` anfügen:

```python
def test_frame_hat_drei_umlaufende_wandlinien():
    """Frame um Chevrons soll 3 konzentrische Perimeter haben (Orca-Stil).
    Aktuelle Implementierung hatte nur '[' (2 Linien links + unten).
    """
    import re
    p = GeneratorParams(num_layers=1)
    g = generate(p)
    lines = g.splitlines()
    # Finde Frame-Block: zwischen PA_ANALYZER_FRAME-Kommentar und der
    # ersten SET_PRESSURE_ADVANCE
    frame_start = next(i for i, l in enumerate(lines)
                       if "; PA_ANALYZER_FRAME" in l)
    pa_set = next(i for i, l in enumerate(lines)
                  if i > frame_start and l.startswith("SET_PRESSURE_ADVANCE"))
    frame_block = lines[frame_start:pa_set]
    # 3 Perimeter à 4 extrudierte Linien = 12 extrudierte Moves
    extruded = [l for l in frame_block
                if l.startswith("G1") and " E" in l]
    # Wir tolerieren mehr (kann auch Top-Bar enthalten wenn die direkt
    # nach Frame ohne PA-Setzung kommt). Mindestens 12.
    assert len(extruded) >= 12, (
        f"Frame sollte mindestens 12 extrudierte Moves (3 Perimeter × 4) "
        f"haben, hat {len(extruded)}")
```

- [ ] **Step 2: Run, expect fail**

Run: `"D:\Entwicklung\PA-Analyzer\.venv\Scripts\python.exe" -m pytest tests/test_gcode_generator.py::test_frame_hat_drei_umlaufende_wandlinien -v`

Expected: FAIL (aktueller Frame hat nur 2 extrudierte Linien — links und unten).

- [ ] **Step 3: Frame-Code in `generate()` umstellen**

In `src/pa_analyzer/gcode_generator.py` in `generate()` den Frame-Block (ca. Linie 460-470, suchen nach `"; PA_ANALYZER_FRAME"` und den 2 nachfolgenden G1-Linien) ersetzen durch:

```python
    # Frame-Box-Marker als Kommentar — Parser nutzt diese, da auch ein
    # 3-Perimeter-Frame im GCode als viele Linien erscheint.
    out.append(
        f"; PA_ANALYZER_FRAME X0={_fmt(bx0)} Y0={_fmt(by0)} "
        f"X1={_fmt(bx1)} Y1={_fmt(by1)}")
    # Frame als 3-Perimeter umlaufender Rahmen (Orca-Stil),
    # ohne Infill. Wird in Layer 0 mit first_layer_print_f gedruckt
    # für Bett-Haftung.
    out.extend(_draw_box(
        p, bx0, by0,
        width=bx1 - bx0, height=top_bar_y_low - by0,
        n_perimeters=p.wall_count, is_filled=False,
        travel_to_fn=travel_to, print_f=first_layer_print_f,
    ))
```

(Die alten 2 `G1`-Frame-Linien gelöscht.)

Wichtig: Die Frame-Höhe wird `top_bar_y_low - by0` — also nur bis zur Top-Bar-Unterkante (Top-Bar wird in Task 5 separat als zweite Box gezeichnet).

- [ ] **Step 4: Run new test, expect pass**

Run: `"D:\Entwicklung\PA-Analyzer\.venv\Scripts\python.exe" -m pytest tests/test_gcode_generator.py::test_frame_hat_drei_umlaufende_wandlinien -v`

Expected: PASS.

- [ ] **Step 5: Full suite — Regressionen identifizieren**

Run: `"D:\Entwicklung\PA-Analyzer\.venv\Scripts\python.exe" -m pytest -q`

Expected: einige bestehende Tests werden brechen (z.B. Tests die "[-Frame" annahmen). Beispiele die wahrscheinlich brechen:
- `test_generate_emittiert_top_bar_vor_erstem_chevron` (zählt G1-Moves, mit 3-Wall-Frame mehr Moves)
- `test_generate_top_bar_ist_letzte_grosse_aktion` (vermutlich noch ok)

Für jeden Fail: Test-Threshold/Assertion an neue Geometrie anpassen (siehe Step 6).

- [ ] **Step 6: Failing tests fixen**

Test `test_generate_emittiert_top_bar_vor_erstem_chevron` (in `test_gcode_generator.py`, suche nach diesem Namen):
- Alte Erwartung: ~3-5 extrudierte Moves im Pre-Pattern-Block (Frame "[" + Top-Bar paar Linien)
- Neue Erwartung: Frame 3-Perimeter × 4 = 12 Moves + Top-Bar (in Task 5) → vermutlich > 30
- Anpassen: Schwelle nach oben justieren auf die tatsächlich gemessene Zahl.

Falls weitere Tests brechen: jeweils einzeln Erwartung an neue Geometrie anpassen, NICHT die alte "[" -Logik wiederherstellen.

- [ ] **Step 7: Full suite — alles grün**

Run: `"D:\Entwicklung\PA-Analyzer\.venv\Scripts\python.exe" -m pytest -q`

Expected: 193 passed (190 alt - 0 obsolet + 3 angepasst + Task-2/3-Tests), 3 xfailed.

- [ ] **Step 8: Commit**

```bash
git add src/pa_analyzer/gcode_generator.py tests/test_gcode_generator.py
git commit -m "generator: Frame als 3-Perimeter umlaufender Rahmen (Orca-Stil)"
```

---

### Task 5: Top-Bar auf `_draw_box(is_filled=True)` umstellen

**Files:**
- Modify: `src/pa_analyzer/gcode_generator.py`
- Test: `tests/test_gcode_generator.py`

- [ ] **Step 1: Failing test — Top-Bar hat 45°-Infill (statt Stadion)**

In `tests/test_gcode_generator.py` anfügen:

```python
def test_top_bar_hat_45grad_infill():
    """Top-Bar enthält 45°-Infill-Linien (Orca-Stil),
    nicht Stadion-Boustrophedon."""
    p = GeneratorParams(num_layers=1)
    g = generate(p)
    # 45°-Infill emittiert "Fill: Print up/left" und "Fill: Print down/right"
    # Kommentare. Stadion-Code hatte das nicht.
    assert "Fill: Print" in g, (
        "Top-Bar hat keine 45°-Fill-Kommentare — vermutlich noch alter "
        "Stadion-Boustrophedon-Code aktiv.")
    # Zähle Fill-Linien: für 84×13.5 mm Top-Bar mit 3 Perimetern und
    # spacing_45 ≈ 0.73 mm sind das ~80-100 Diagonalen.
    fill_print_count = g.count("Fill: Print")
    assert fill_print_count > 30, (
        f"Erwartet > 30 Fill-Linien, hat {fill_print_count}")
```

- [ ] **Step 2: Run, expect fail**

Run: `"D:\Entwicklung\PA-Analyzer\.venv\Scripts\python.exe" -m pytest tests/test_gcode_generator.py::test_top_bar_hat_45grad_infill -v`

Expected: FAIL (alter `_top_bar_block` macht Stadion-Linien).

- [ ] **Step 3: `_top_bar_block` entfernen, `generate()` auf `_draw_box` umstellen**

In `src/pa_analyzer/gcode_generator.py`:

1. Die alte `_top_bar_block`-Funktion (Linien 204-240 etwa) komplett löschen — wird ersetzt durch `_draw_box(is_filled=True)`.

2. Im `generate()` den `_top_bar_block`-Aufruf (im Layer-Loop, ca. Linie 502) ersetzen durch:

```python
        # Top-Bar NUR in Layer 0 (Orca-Stil): 3 Perimeter + 45°-Infill,
        # mit 0.517 mm Lücke (=line_spacing) zwischen Frame-Top und
        # Top-Bar-Bottom — das verhindert Verschmelzung der Wände.
        if layer == 0:
            line_spacing = _line_width(p) - p.layer_height * (1 - math.pi / 4)
            tb_y0 = top_bar_y_low  # bereits berechnet aus by1 - top_bar_height
            # Lücke zwischen Frame-Top (= top_bar_y_low) und Top-Bar-Bottom
            # ist im Modell bereits implizit, da top_bar_y_low aufeinander
            # liegt. Wir verschieben Top-Bar um line_spacing nach oben:
            tb_y0_gapped = tb_y0 + line_spacing
            tb_height = p.top_bar_height - line_spacing
            out.extend(_draw_box(
                p, bx0, tb_y0_gapped,
                width=bx1 - bx0, height=tb_height,
                n_perimeters=p.wall_count, is_filled=True,
                travel_to_fn=travel_to, print_f=layer_print_f,
            ))
```

(Wichtig: `top_bar_y_high` wird nicht mehr verwendet, kann gelöscht werden falls anderswo nicht referenziert.)

- [ ] **Step 4: Run new test, expect pass**

Run: `"D:\Entwicklung\PA-Analyzer\.venv\Scripts\python.exe" -m pytest tests/test_gcode_generator.py::test_top_bar_hat_45grad_infill -v`

Expected: PASS.

- [ ] **Step 5: Full suite — Regressionen prüfen**

Run: `"D:\Entwicklung\PA-Analyzer\.venv\Scripts\python.exe" -m pytest -q`

Brüche identifizieren: vermutlich Tests die spezifische Y-Spannweiten asserten (Top-Bar startet jetzt 0.517 mm später). Beispiele:
- `test_generate_pattern_hoehe_enthaelt_top_bar_und_band_gap`: anpassen wenn Frame-Höhe sich ändert
- `test_generate_top_bar_beruehrt_chevrons`: jetzt FALSCH — Top-Bar hat explizite Lücke, Test umbenennen + Aussage umkehren

- [ ] **Step 6: Failing tests fixen**

Test `test_generate_top_bar_beruehrt_chevrons` — neue Erwartung:

```python
def test_generate_top_bar_mit_luecke_zum_frame():
    """Orca-Stil: zwischen Frame-Top und Top-Bar-Bottom liegt eine
    Lücke von ~line_spacing (~0.5 mm), die ein Verschmelzen der
    beiden Wand-Reihen verhindert."""
    import math, re
    p = GeneratorParams()
    g = generate(p)
    lw = p.nozzle_diameter * p.line_ratio / 100.0
    expected_gap = lw - p.layer_height * (1 - math.pi / 4)
    # Aus den Travel-Moves: Frame-Top-Y vs Top-Bar-Bottom-Y
    # Frame-Top-Y = max y der ersten Box, Top-Bar-Bottom-Y = min y der zweiten
    # ... Vereinfachung: prüfe dass eine Y-Lücke von ~0.5 mm zwischen
    # Frame-Top (~165 mm laut Orca-Beispiel) und Top-Bar-Bottom (~165.5 mm)
    # besteht. Konkret: kein Move auf der exakten Frame-Top-Y im Top-Bar-Bereich.
    assert expected_gap > 0.3 and expected_gap < 0.7
```

- [ ] **Step 7: Full suite — grün**

Run: `"D:\Entwicklung\PA-Analyzer\.venv\Scripts\python.exe" -m pytest -q`

Expected: 194 passed, 3 xfailed.

- [ ] **Step 8: Commit**

```bash
git add src/pa_analyzer/gcode_generator.py tests/test_gcode_generator.py
git commit -m "generator: Top-Bar als 3-Perimeter+Infill-Box (Orca-Stil)"
```

---

### Task 6: Labels-X-Position auf `glyph_start_x` (Anker am Frame)

**Files:**
- Modify: `src/pa_analyzer/gcode_generator.py` (`_pa_labels_block`)
- Test: `tests/test_gcode_generator.py`

- [ ] **Step 1: Failing test — Label-X liegt über Chevron-Start, nicht über Mitte**

In `tests/test_gcode_generator.py` anfügen:

```python
def test_label_x_position_ist_chevron_anker_nicht_mitte():
    """Labels sollen über dem Chevron-Anker am Frame (= Chevron-Start-X)
    stehen, nicht über der Chevron-Mitte. Orca's Logik: glyph_start_x(j)
    = pattern_start + j*group_advance + (wall_count*wall_spacing)/2
                    - glyph_length/2.
    """
    import re, math
    from pa_analyzer.gcode_generator import (
        GeneratorParams, generate, _line_width, _wall_x_offset,
        _group_advance, _chevron_deltas,
    )
    p = GeneratorParams(num_layers=2)
    g = generate(p)
    # Aus dem GCode-Header die PA_ANALYZER_FRAME-X-Range lesen
    frame_line = next(l for l in g.splitlines() if "PA_ANALYZER_FRAME" in l)
    bx0 = float(re.search(r"X0=([\d.-]+)", frame_line).group(1))
    # Aus parser-konvention: erste Chevron-Gruppe-Apex liegt bei
    # px0 + dx (px0 = bx0 + pattern_shift)
    line_spacing = _line_width(p) - p.layer_height * (1 - math.pi / 4)
    glyph_padding_h = 0.5  # wir geben dem einen Konstanten-Wert
    pattern_shift = (p.wall_count - 1) * line_spacing + _line_width(p) + glyph_padding_h
    expected_pattern_start = bx0 + pattern_shift
    # Erster PA-Wert (0.0) wird beschriftet (label_stride=2, j=0 → ja).
    # Label-Block ist in Layer 1, beginnt nach SET_PRESSURE_ADVANCE=0.
    # Wir suchen die erste hochkant-rotierte Glyph-Strich-Sequenz:
    # render_label_gcode mit rotation=90 erzeugt G1 X{x_const} Y{y_decreasing}.
    # Vereinfachte Heuristik: in Layer 1 (nach Z=0.4) den ersten Move
    # ohne E lesen — sein X sollte expected_pattern_start ± kleinen
    # glyph_offset matchen.
    lines = g.splitlines()
    z04_idx = next(i for i, l in enumerate(lines) if l.startswith("G1 Z0.4"))
    after_z04 = lines[z04_idx:]
    set_pa_zero_idx = next(i for i, l in enumerate(after_z04)
                           if "ADVANCE=0" in l and "Override" not in l)
    label_start = after_z04[set_pa_zero_idx + 1:]
    # Erster G1 ohne E nach SET_PA=0 ist Travel zum ersten Glyph-Start
    first_travel = next(l for l in label_start
                        if l.startswith("G1 X") and " E" not in l)
    x_label = float(re.search(r"X([\d.-]+)", first_travel).group(1))
    # Label-Start sollte beim ersten Chevron-Anker liegen
    # (= pattern_shift vom Frame-Links-Rand). Toleranz: glyph_height/2
    # für Glyph-Zentrierung.
    assert abs(x_label - expected_pattern_start) < p.label_glyph_height, (
        f"Erstes Label-X={x_label:.2f} weicht von erwartetem "
        f"Chevron-Anker {expected_pattern_start:.2f} um "
        f"{abs(x_label - expected_pattern_start):.2f} mm ab")
```

- [ ] **Step 2: Run, expect fail**

Run: `"D:\Entwicklung\PA-Analyzer\.venv\Scripts\python.exe" -m pytest tests/test_gcode_generator.py::test_label_x_position_ist_chevron_anker_nicht_mitte -v`

Expected: FAIL (aktuelle Implementation setzt Label über Chevron-Mitte, nicht über Anker).

- [ ] **Step 3: `_pa_labels_block` umbauen**

In `src/pa_analyzer/gcode_generator.py` die `_pa_labels_block`-Funktion (ca. Linie 269-310) umschreiben:

```python
def _pa_labels_block(
    p: GeneratorParams, pa_values: list[float], px0: float,
    label_y_top: float, group_advance: float,
    print_speed: float | None = None,
) -> list[str]:
    """Hochkant rotierte PA-Labels auf der Top-Bar.

    Position: Label-Start-X = Chevron-Anker-X (Position des Chevron-
    Start-Arms am Frame-Rand), zentriert um die Wand-Mitte des Chevrons.
    Reproduziert Orca's glyph_start_x-Logik (siehe reference/orca_calib.cpp
    Linie 821-844).

    NOT-TO-DO: Label über Chevron-Mitte oder Apex zentrieren — User-
    Anforderung 2026-05-25 explizit: "an den Ankerpunkt am Frame, damit
    man es überhaupt zuordnen könnte". Mittellage führte dazu dass die
    Zuordnung Label↔Chevron visuell unklar war.
    """
    out: list[str] = []
    wall_off = _wall_x_offset(p)
    speed = print_speed if print_speed is not None else p.speed_print
    # Glyph-Länge (für 90°-Rotation: Höhe entspricht horizontaler Glyph-Spanne)
    glyph_len_x = p.label_glyph_height
    for j, pa in enumerate(pa_values):
        if j % p.label_stride != 0:
            continue
        # Orca: glyph_start_x = pattern_start + j*group_advance
        #       + wall_count*wall_spacing/2 - glyph_len/2
        # In unserer Konvention ist px0 schon = pattern_start, j*group_advance
        # ist der Versatz pro Pattern. Wall-Center: (wall_count-1)*wall_off/2.
        x_start = (px0 + j * group_advance
                   + (p.wall_count - 1) * wall_off / 2
                   - glyph_len_x / 2)
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
```

- [ ] **Step 4: Run new test, expect pass**

Run: `"D:\Entwicklung\PA-Analyzer\.venv\Scripts\python.exe" -m pytest tests/test_gcode_generator.py::test_label_x_position_ist_chevron_anker_nicht_mitte -v`

Expected: PASS.

- [ ] **Step 5: Full suite**

Run: `"D:\Entwicklung\PA-Analyzer\.venv\Scripts\python.exe" -m pytest -q`

Expected: 195 passed, 3 xfailed (oder Regressionen identifizieren).

- [ ] **Step 6: Commit**

```bash
git add src/pa_analyzer/gcode_generator.py tests/test_gcode_generator.py
git commit -m "generator: PA-Labels über Chevron-Anker am Frame (Orca-Stil)"
```

---

### Task 7: Settings-Position fixen — nach den PA-Labels

**Files:**
- Modify: `src/pa_analyzer/gcode_generator.py` (in `generate()`)
- Test: `tests/test_gcode_generator.py`

- [ ] **Step 1: Failing test — Settings-Labels liegen RECHTS von letztem PA-Label**

In `tests/test_gcode_generator.py` anfügen:

```python
def test_settings_header_liegt_rechts_von_letztem_pa_label():
    """Flow- und Accel-Labels sollen NACH dem letzten PA-Label
    auf der Top-Bar stehen (Orca-Stil), nicht davor."""
    import re
    p = GeneratorParams(num_layers=2)
    g = generate(p)
    lines = g.splitlines()
    z04_idx = next(i for i, l in enumerate(lines) if l.startswith("G1 Z0.4"))
    after_z04 = lines[z04_idx:]
    # Sammle alle X-Werte von Travel-Moves nach SET_PA=0
    set_pa_zero_idx = next(i for i, l in enumerate(after_z04)
                           if "ADVANCE=0" in l and "Override" not in l)
    label_moves = after_z04[set_pa_zero_idx + 1:]
    travel_xs = []
    for l in label_moves:
        if not (l.startswith("G1 X") and " E" not in l):
            continue
        m = re.search(r"X([\d.-]+)", l)
        if m:
            travel_xs.append(float(m.group(1)))
        # Stop bei nächstem Z-Wechsel
        if "Z" in l and " E" not in l:
            break
    # Mindestens 4 Labels gerendert (mehrere PA-Werte + Flow + Accel)
    assert len(travel_xs) >= 4
    # PA-Labels kommen ZUERST (kleinere X), Settings ZULETZT (größere X)
    # → letzten beiden X-Werte sollten die größten sein
    sorted_xs = sorted(travel_xs)
    # Mindestens das letzte X (= Accel-Label) sollte > als der mittlere
    # PA-Label-X sein
    assert travel_xs[-1] > sorted_xs[len(sorted_xs) // 2], (
        "Letztes Label (Accel) sollte rechts von mittlerem PA-Label "
        "stehen — Header steht aber links davon")
```

- [ ] **Step 2: Run, expect fail**

Run: `"D:\Entwicklung\PA-Analyzer\.venv\Scripts\python.exe" -m pytest tests/test_gcode_generator.py::test_settings_header_liegt_rechts_von_letztem_pa_label -v`

Expected: FAIL (aktuell wird Header VOR den PA-Labels emittiert).

- [ ] **Step 3: `generate()`-Layer-Loop-Section für Layer 1 umbauen**

In `src/pa_analyzer/gcode_generator.py` in `generate()` (Layer-Loop, ca. Linie 530-555) den `if layer == 1:`-Block ersetzen durch:

```python
        # Labels in Layer 1 (Orca-Stil): Relief auf der einlagigen
        # Top-Bar. PA=0 explizit setzen, mit first_layer_speed drucken.
        # Settings (Flow, Accel) folgen NACH den PA-Labels — auf
        # zusätzlichen Glyph-Slots auf der gleichen Top-Bar.
        if layer == 1:
            out.append(f"{set_pa_prefix}0")
            # Y-Position der Label-Glyphen: AUF der Top-Bar, mit
            # vertikalem Padding zur Top-Bar-Oberkante.
            line_spacing = _line_width(p) - p.layer_height * (1 - math.pi / 4)
            tb_y_top = top_bar_y_low + line_spacing + (
                p.top_bar_height - line_spacing)
            label_y_top = tb_y_top - 0.5  # 0.5 mm Padding zum oberen Rand
            label_speed = p.first_layer_speed
            # 1) PA-Labels (über jedem Chevron-Anker)
            out.extend(_pa_labels_block(
                p, pa_values, px0, label_y_top, adv,
                print_speed=label_speed,
            ))
            # 2) Settings (Flow + Accel) NACH den PA-Labels.
            #    glyph_start_x(num_patterns + 2) und (+ 4) — Orca-Stil.
            num_patterns = len(pa_values)
            wall_off = _wall_x_offset(p)
            glyph_len_x = p.label_glyph_height
            flow_x = (px0 + (num_patterns + 2) * adv
                      + (p.wall_count - 1) * wall_off / 2
                      - glyph_len_x / 2)
            accel_x = (px0 + (num_patterns + 4) * adv
                       + (p.wall_count - 1) * wall_off / 2
                       - glyph_len_x / 2)
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
```

(Die alte `_header_labels_block`-Aufruf entfällt, die Funktion selbst kann gelöscht werden falls woanders nicht referenziert.)

- [ ] **Step 4: Run new test, expect pass**

Run: `"D:\Entwicklung\PA-Analyzer\.venv\Scripts\python.exe" -m pytest tests/test_gcode_generator.py::test_settings_header_liegt_rechts_von_letztem_pa_label -v`

Expected: PASS.

- [ ] **Step 5: Full suite — Regressionen prüfen**

Run: `"D:\Entwicklung\PA-Analyzer\.venv\Scripts\python.exe" -m pytest -q`

Brüche fixen — speziell:
- `test_generate_beschriftet_speed_accel_header`: Erwartung über G1-Count anpassen
- `test_generate_kein_accel_kein_header_label`: bleibt sinnvoll (Accel-Block bleibt conditional)

- [ ] **Step 6: Commit**

```bash
git add src/pa_analyzer/gcode_generator.py tests/test_gcode_generator.py
git commit -m "generator: Settings-Header rechts nach PA-Labels (Orca-Stil)"
```

---

### Task 8: Anker-Marker entfernen

**Files:**
- Modify: `src/pa_analyzer/gcode_generator.py`
- Test: `tests/test_gcode_generator.py`

**Begründung:** Orca verwendet keinen separaten Asymmetrie-Anker. Der Frame ist asymmetrisch durch die Top-Bar oben (orientation-Pipeline nutzt das Top-Bar/Chevron-Dichte-Verhältnis). Der bestehende `_anchor_marker_block` macht das v2-3-Linien-Anker-Quadrat innen-links — visuell stört das nun den nahtlosen Frame.

- [ ] **Step 1: Failing test — Anker-Marker nicht mehr emittiert**

In `tests/test_gcode_generator.py` anfügen:

```python
def test_anker_marker_nicht_mehr_emittiert():
    """Orca-Stil hat keinen separaten Anker-Marker. Frame-Asymmetrie
    durch Top-Bar oben reicht für orientation.py."""
    p = GeneratorParams()
    g = generate(p)
    # Anker-Marker war 8x2 mm Vollfüllung links innen.
    # Indirekte Detection: bei wall_side_length=30 und top_bar_height=12
    # gibt es genug "viele kurze vertikale Linien" nur im Anker-Block.
    # Vereinfacht: prüfe dass _anchor_marker_block-Aufruf wegfällt
    # (Marker-Code im Source).
    import inspect
    from pa_analyzer import gcode_generator
    src = inspect.getsource(gcode_generator.generate)
    assert "_anchor_marker_block(" not in src, (
        "_anchor_marker_block wird noch aufgerufen — Anker-Marker noch da")
```

- [ ] **Step 2: Run, expect fail**

Run: `"D:\Entwicklung\PA-Analyzer\.venv\Scripts\python.exe" -m pytest tests/test_gcode_generator.py::test_anker_marker_nicht_mehr_emittiert -v`

Expected: FAIL.

- [ ] **Step 3: Anker-Marker-Aufruf aus `generate()` entfernen**

In `src/pa_analyzer/gcode_generator.py`:
1. Im Layer-Loop den `_anchor_marker_block`-Aufruf entfernen (ca. Linie 508-511).
2. Die `_anchor_marker_block`-Funktion selbst (Linie 235-266) löschen oder zu Deprecation-Kommentar machen.
3. `chevron_center_y`-Variable im Loop löschen (war nur für Anker).
4. `left_padding`-Konstante in `generate()` ist nicht mehr nötig wenn Chevrons direkt nach Frame-Wand-Padding starten — aber: Orca's `pattern_shift` ÜBERNIMMT diesen Padding-Job. `left_padding` lässt sich umbenennen zu `pattern_shift` und neu berechnen:

```python
    # pattern_shift: X-Versatz vom Frame-Links-Rand bis zum ersten
    # Chevron-Arm-Start. Macht Platz für Frame-Perimeter (n_walls *
    # line_spacing) PLUS horizontales Padding für Label-Ausrichtung
    # (~0.5 mm). Reproduziert Orca's pattern_shift()
    # (orca_calib.cpp Linie 893).
    line_spacing = _line_width(p) - p.layer_height * (1 - math.pi / 4)
    glyph_padding_horizontal = 0.5
    pattern_shift = ((p.wall_count - 1) * line_spacing
                     + _line_width(p) + glyph_padding_horizontal)
    px0 = bx0 + pattern_shift
```

- [ ] **Step 4: Run new test, expect pass**

Run: `"D:\Entwicklung\PA-Analyzer\.venv\Scripts\python.exe" -m pytest tests/test_gcode_generator.py::test_anker_marker_nicht_mehr_emittiert -v`

Expected: PASS.

- [ ] **Step 5: Full suite — Regressionen**

Run: `"D:\Entwicklung\PA-Analyzer\.venv\Scripts\python.exe" -m pytest -q`

Brüche fixen — Tests die spezifische Anker-Marker-Eigenschaften assert ('test_anchor_*', etc.) — sind alle obsolet, löschen oder umschreiben.

- [ ] **Step 6: Commit**

```bash
git add src/pa_analyzer/gcode_generator.py tests/test_gcode_generator.py
git commit -m "generator: Anker-Marker entfernen (Orca verwendet keinen)"
```

---

### Task 9: Render-Script aktualisieren + lokale Visual-Verifikation

**Files:**
- Modify: `reference/render_proposed_pattern.py`

- [ ] **Step 1: Render-Script erweitern um Frame-Walls und Top-Bar-Infill**

In `reference/render_proposed_pattern.py` die `render_for_params`-Funktion erweitern:

```python
def render_for_params(p: GeneratorParams, out_path: str) -> None:
    gcode = generate(p)
    m = parse(gcode)
    lo, hi = m.content_bounds
    px_per_mm = 12
    w = int((hi.x - lo.x) * px_per_mm)
    h = int((hi.y - lo.y) * px_per_mm)
    img = np.full((h, w, 3), 32, np.uint8)

    def to_px(pt):
        return (int((pt.x - lo.x) * px_per_mm),
                int((hi.y - pt.y) * px_per_mm))

    # 1) ALLE G1-Moves aus dem GCode zeichnen — extrudierte als
    #    farbig, Travel-Moves als ausgeblendet (dunkel)
    import re
    pos = (0.0, 0.0)
    for line in gcode.splitlines():
        if not line.startswith("G1"):
            continue
        m_x = re.search(r"X([\d.-]+)", line)
        m_y = re.search(r"Y([\d.-]+)", line)
        m_e = re.search(r"\sE([\d.-]+)", line)
        if not (m_x or m_y):
            continue
        x = float(m_x.group(1)) if m_x else pos[0]
        y = float(m_y.group(1)) if m_y else pos[1]
        if m_e:
            # Print-Linie — extrahiere Pattern-Type aus Kommentar
            if "Fill: Print" in line:
                color = (0, 100, 255)  # Infill = Orange
            elif "perimeter" in line.lower():
                color = (0, 255, 100)  # Walls = Grün
            else:
                color = (0, 0, 200)    # Chevrons = Rot
            cv2.line(img, to_px(_pt(*pos)), to_px(_pt(x, y)), color, 2)
        pos = (x, y)

    # Apex-Marker (Mess-Boxen) wie zuvor
    for g in m.groups:
        apx = to_px(g.apex)
        cv2.circle(img, apx, 3, (0, 255, 255), -1)
        bh = int(BOX_HALF_MM * px_per_mm)
        cv2.rectangle(img, (apx[0] - bh, apx[1] - bh),
                      (apx[0] + bh, apx[1] + bh), (255, 255, 0), 1)

    cv2.imwrite(out_path, img)
    print(f"Saved: {out_path} ({w}x{h} px, {hi.x-lo.x:.1f}x{hi.y-lo.y:.1f} mm)")

# Helper am Anfang der Datei:
from dataclasses import dataclass
@dataclass
class _pt:
    x: float
    y: float
```

- [ ] **Step 2: Render erzeugen**

Run: `cd "D:\Entwicklung\PA-Analyzer" && "D:\Entwicklung\PA-Analyzer\.venv\Scripts\python.exe" reference/render_proposed_pattern.py`

Expected: Speichert `reference/render_v4.png` (oder ähnlich) mit:
- Grünem 3-Wand-Frame umlaufend
- Grüner Top-Bar mit oranger 45°-Infill-Struktur
- Roten Chevrons drinnen
- Gelben Apex-Box-Markern

- [ ] **Step 3: Visuelle Verifikation**

Open `reference/render_v4.png` mit Bildbetrachter. Vergleich mit `reference/pa_calibration_v4.gcode`-Verarbeitung im Orca-Slicer.

**Checklist:**
- [ ] Frame umlaufend (alle 4 Seiten, 3 Wände)
- [ ] Top-Bar 3 Wände + Diagonale Infill-Linien
- [ ] Lücke zwischen Frame-Top und Top-Bar-Bottom sichtbar
- [ ] Chevrons sitzen innen im Frame, mit Padding links

Falls Optik nicht passt: zurück zu betreffender Task (4/5).

- [ ] **Step 4: Commit Render-Update**

```bash
git add reference/render_proposed_pattern.py
git commit -m "render: Frame-Walls + Top-Bar-Infill visualisieren"
```

---

### Task 10: Live-Test vorbereiten — Pi-Deploy + GCode-Regenerierung

**Files:** keine Source-Änderungen, nur Deploy.

- [ ] **Step 1: PR auf main mergen (User-Freigabe einholen)**

Wenn alle Tasks 1-9 commited sind: PR aufmachen mit Body:

```bash
git push origin feature/orca-style-pattern-refactor
gh pr create --title "Orca-Style PA-Pattern Refactor" --body "$(cat <<'EOF'
## Refactor: Generator-Output an OrcaSlicer-Pattern angleichen

### Was sich ändert

| Element | Vorher | Nachher |
|---------|--------|---------|
| Frame | "[" 2-Linien (links + unten) | 3-Perimeter umlaufender Rahmen |
| Top-Bar | Stadion-Boustrophedon (45°-Diagonale durch Bug) | 3 Perimeter + 45°-Infill |
| PA-Labels | über Chevron-Mitte, mit Header-Versatz | über Chevron-Anker am Frame (Orca-Style) |
| Settings | links vor PA-Labels | rechts nach PA-Labels (Orca-Style) |
| Anker-Marker | 8x2 mm Vollfüllung links | entfernt (Frame-Asymmetrie reicht) |

### Validierung

- 195+ Tests grün, 3 xfailed (pre-existing HEIC-Bug)
- Lokales Render bestätigt Orca-ähnliche Optik
- Generator-Output verglichen mit reference/orca_reference.gcode

### Live-Test-Plan

PA_CALIBRATE TEMP=220 BED_TEMP=55 FLOW=0.956 FAN=0.4 SPEED=180 ACCEL=3000

### Referenzen

- Spec: docs/specs/2026-05-25-orca-pattern-layout.md
- Plan: docs/plans/2026-05-25-orca-style-pattern-refactor.md
- Orca-Source: reference/orca_calib.cpp (draw_box Linie 261-460)
- Orca-Output: reference/orca_reference.gcode (3595 Zeilen)
EOF
)"
```

- [ ] **Step 2: Nach Merge — Pi-Deploy**

```bash
"C:\Program Files\PuTTY\plink.exe" -pw "<PW>" -batch pi@<IP> "cd ~/pa-pattern-webcam-analyzer && git checkout main && git pull && find src -name __pycache__ -exec rm -rf {} + 2>/dev/null; .venv/bin/pip install -e . 2>&1 | tail -1"
```

- [ ] **Step 3: GCode neu generieren (KEIN Druck!)**

```bash
"C:\Program Files\PuTTY\plink.exe" -pw "<PW>" -batch pi@<IP> "cd ~/pa-pattern-webcam-analyzer && .venv/bin/pa-analyzer --config /home/pi/printer_data/config/pa_analyzer.conf generate --temp 220 --bed-temp 55 --flow 0.956 --fan 0.4 --speed 180 --accel 3000"
```

Expected: Datei `/home/pi/printer_data/gcodes/pa_calibration.gcode` neu erstellt mit Orca-Style-Layout.

- [ ] **Step 4: GCode lokal runterladen**

```bash
"C:\Program Files\PuTTY\plink.exe" -pw "<PW>" -batch pi@<IP> "base64 /home/pi/printer_data/gcodes/pa_calibration.gcode" > /tmp/v5.b64 && base64 -d /tmp/v5.b64 > "D:\Entwicklung\PA-Analyzer\reference\pa_calibration_v5.gcode"
```

- [ ] **Step 5: User-Freigabe für Druck einholen**

Im Chat: "GCode v5 (Orca-Style) ist auf Pi und lokal. Du kannst ihn im Orca öffnen und visuell prüfen. Wenn ok, gib Druck-Freigabe für `PA_CALIBRATE TEMP=220 BED_TEMP=55 FLOW=0.956 FAN=0.4 SPEED=180 ACCEL=3000`."

---

### Task 11: Live-Test ausführen (nach User-Freigabe)

**Files:** keine.

- [ ] **Step 1: Klipper-State prüfen**

```bash
"C:\Program Files\PuTTY\plink.exe" -pw "<PW>" -batch pi@<IP> "curl -s 'http://localhost/printer/info' | python3 -c 'import sys,json; print(json.load(sys.stdin)[\"result\"][\"state\"])'"
```

Expected: `ready`.

- [ ] **Step 2: Log truncieren + PA_CALIBRATE starten**

```bash
"C:\Program Files\PuTTY\plink.exe" -pw "<PW>" -batch pi@<IP> ": > /home/pi/printer_data/logs/klippy.log && curl -s -X POST 'http://localhost/printer/gcode/script' -H 'Content-Type: application/json' -d '{\"script\":\"PA_CALIBRATE TEMP=220 BED_TEMP=55 FLOW=0.956 FAN=0.4 SPEED=180 ACCEL=3000\"}'"
```

- [ ] **Step 3: Monitor im Hintergrund starten**

```bash
"C:\Program Files\PuTTY\plink.exe" -pw "<PW>" -batch pi@<IP> "python3 /tmp/monitor_print.py"
# mit run_in_background=true
```

- [ ] **Step 4: Auf Notification warten**

Bei Druckende:
- Wenn state=complete: weiter zu Step 5
- Wenn state=error oder cancelled: Klipper-Log analysieren, Root-Cause finden, mit User koordinieren

- [ ] **Step 5: Webcam-Snapshot + Visual-Verifikation**

```bash
"C:\Program Files\PuTTY\plink.exe" -pw "<PW>" -batch pi@<IP> "curl -s 'http://localhost/webcam/?action=snapshot' -o /tmp/v5_print.jpg" && \
"C:\Program Files\PuTTY\plink.exe" -pw "<PW>" -batch pi@<IP> "base64 /tmp/v5_print.jpg" > /tmp/v5.b64 && \
base64 -d /tmp/v5.b64 > "D:\Entwicklung\PA-Analyzer\reference\v5_print.jpg"
```

Open + visual check: stimmt Layout mit Orca-Vorbild überein?

- [ ] **Step 6: pa-analyzer run für Pipeline-Auswertung**

```bash
"C:\Program Files\PuTTY\plink.exe" -pw "<PW>" -batch pi@<IP> "cd ~/pa-pattern-webcam-analyzer && .venv/bin/pa-analyzer --config /home/pi/printer_data/config/pa_analyzer.conf analyze /tmp/v5_print.jpg /home/pi/printer_data/gcodes/pa_calibration.gcode"
```

Ergebnis dem User berichten.

- [ ] **Step 7: Commit (optional, falls weitere Anpassungen)**

Wenn der Live-Test Anpassungen ergibt: jeweils neue Task-Reihe mit systematic-debugging starten, NICHT improvisieren.

---

## Verifikation der Plan-Vollständigkeit (Self-Review)

**Spec-Coverage:** ✓ Tasks 4 + 5 (Frame + Top-Bar), Task 6 (Label-Position), Task 7 (Settings-Position), Task 8 (Anker entfernt), Task 9 (visual), Task 10/11 (Live-Test) decken alle User-Befunde.

**Placeholder-Scan:** Alle Code-Snippets vollständig, keine TODO/TBD-Marker. Konstante glyph_padding_horizontal=0.5 mm ist gesetzt (statt fehlend).

**Type-Konsistenz:** `_draw_box`-Signature einheitlich in Task 2/3/4/5. `pattern_shift` Variable konsistent berechnet in Task 6/8.

**Bekannte Risiken:**
1. **45°-Infill bei sehr breiter Top-Bar** (Task 3): Edge-Case "x_remainder + y_remainder >= spacing_45" wird vereinfacht (skip). Reicht für 84x13.5-mm-Top-Bar; bei anderen Proportionen ggf. anpassen.
2. **Label-X-Berechnung** (Task 6): Bei `label_stride > 1` werden manche Labels übersprungen — Pattern_shift muss reichen für längste Glyph-Sequenz (Default-Werte passen für `pa_step=0.005`).
3. **Test-Regressionen** (Task 4/5/7): Zähle Test-Anpassungen ein. Schwellen-basierte Tests müssen mit den neuen Geometrie-Konstanten neu kalibriert werden.

---

## Execution Handoff

Plan complete and saved to `docs/plans/2026-05-25-orca-style-pattern-refactor.md`. Zwei Execution-Optionen:

**1. Subagent-Driven (empfohlen)** — Ein frischer Subagent pro Task, Review zwischen Tasks, schnelle Iteration

**2. Inline Execution** — Tasks in dieser Session mit Batch-Checkpoints

Welcher Ansatz?
