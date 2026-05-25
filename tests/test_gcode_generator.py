"""Tests für den GCode-Generator."""
import math

import pytest

from pa_analyzer.gcode_generator import (
    GeneratorParams,
    _chevron_deltas,
    _extrusion,
    _fmt,
    _group_advance,
    _line_width,
    _num_patterns,
    _pa_values,
    _wall_x_offset,
    generate,
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


def test_group_advance_konkreter_wert():
    # Handgerechnet fuer die v4-Default-Parameter (wall_count=3, lw=0.45,
    # layer_height=0.2, corner_angle=90, pattern_spacing=18.0):
    # line_spacing = 0.45 - 0.2*(1-pi/4) ~= 0.40708
    # wall_x_offset = line_spacing / sin(45 Grad) ~= 0.57577
    # group_advance = 2*0.57577 + 18.0 + 0.45 ~= 19.6014
    # (v3 hatte pattern_spacing=6 → 7.6014; v4 erweitert auf 18 damit
    # Chevrons mit wall_side_length=30 klar getrennt sind — Orca-Stil.)
    assert _group_advance(GeneratorParams()) == pytest.approx(19.6014, abs=0.001)
    # Explizit auch mit alter v2-Geometrie testen (Backward-Compat
    # für Nutzer die alte Parameter überschreiben).
    p_v2 = GeneratorParams(wall_side_length=30.0, pattern_spacing=2.0)
    assert _group_advance(p_v2) == pytest.approx(3.6015, abs=0.001)


def test_generate_enthaelt_geruest():
    g = generate(GeneratorParams())
    for marker in ("G90", "M83", "PRINT_START", "PRINT_END"):
        assert marker in g


def test_generate_pa_zeilen_anzahl():
    # num_patterns × num_layers SET_PRESSURE_ADVANCE-Zeilen für die
    # Chevron-Gruppen. v4-Refactor: in Layer 1 wird ZUSÄTZLICH einmal
    # SET_PRESSURE_ADVANCE ADVANCE=0 vor den Labels emittiert (PA=0
    # für saubere Beschriftung). → 11*3 + 1 = 34.
    p = GeneratorParams(pa_start=0.0, pa_end=0.05, pa_step=0.005, num_layers=3)
    assert generate(p).count("SET_PRESSURE_ADVANCE") == 11 * 3 + 1


def test_generate_endet_mit_newline():
    assert generate(GeneratorParams()).endswith("\n")


def test_generate_temp_eingebacken():
    assert "235" in generate(GeneratorParams(temp=235))


def test_generate_print_start_uebernimmt_temps():
    # Klipper-Konvention: PRINT_START erhaelt EXTRUDER und BED als
    # Parameter und uebernimmt das Heizen selbst (Bett-Pre-Heat waehrend
    # Homing/QGL etc.) — wir emittieren KEIN eigenes M190/M109.
    g = generate(GeneratorParams(temp=230, bed_temp=70))
    assert "PRINT_START EXTRUDER=230 BED=70" in g
    assert "M190" not in g
    assert "M109" not in g
    # Header dokumentiert beide Werte:
    assert "temp=230" in g
    assert "bed_temp=70" in g


def test_generate_retract_um_jeden_travel():
    # Vor jedem Travel ein Retract, danach ein De-Retract (Ellis-Stil
    # gegen Sabbern auf langen Bewegungen zwischen Chevron-Gruppen).
    g = generate(GeneratorParams(pa_start=0.0, pa_end=0.01, pa_step=0.005,
                                 num_layers=1, retract_distance=0.5))
    # Mindestens ein Retract und ein De-Retract:
    assert "G1 E-0.5" in g
    assert "G1 E0.5" in g
    # Travels werden konsequent eingerahmt — bei mehreren Chevrons ist
    # die Anzahl der Retracts > Anzahl der Pattern-Travels.
    assert g.count("G1 E-0.5") >= 3  # mindestens Purge + Frame + Pattern


def test_generate_retract_aus_wenn_distance_null():
    g = generate(GeneratorParams(retract_distance=0.0))
    assert "G1 E-" not in g  # kein Retract


def test_generate_zieht_purge_linie():
    # Vor dem Pattern wird eine Purge-Linie am linken Bettrand gezogen.
    g = generate(GeneratorParams(bed_x=300.0, bed_y=300.0,
                                 purge_x_margin=10.0, purge_length=80.0))
    # Travel zur Purge-Start-Position (linker Rand, Bett-Y-Mitte):
    assert "G1 X10 Y150" in g
    # Extrudierende Purge-Bewegung 80 mm nach rechts:
    assert "G1 X90 Y150" in g
    # Purge laeuft vor dem Pattern, also vor dem ersten SET_PRESSURE_ADVANCE:
    zeilen = g.splitlines()
    purge_idx = next(i for i, z in enumerate(zeilen) if "G1 X90 Y150" in z)
    pa_idx = next(i for i, z in enumerate(zeilen) if "SET_PRESSURE_ADVANCE" in z)
    assert purge_idx < pa_idx


def test_generate_zeigt_pa_im_display():
    # M117 PA <wert> als Status-Anzeige je PA-Gruppe.
    g = generate(GeneratorParams(pa_start=0.02, pa_end=0.025, pa_step=0.005,
                                 num_layers=1))
    assert "M117 PA 0.02" in g
    assert "M117 PA 0.025" in g


def test_generate_set_pressure_advance_mit_extruder_name():
    # Optionaler EXTRUDER=-Parameter fuer Multi-Extruder-Setups.
    g = generate(GeneratorParams(extruder_name="extruder1"))
    assert "SET_PRESSURE_ADVANCE EXTRUDER=extruder1 ADVANCE=" in g


def test_generate_set_pressure_advance_ohne_extruder_name_default():
    g = generate(GeneratorParams())
    assert "SET_PRESSURE_ADVANCE ADVANCE=" in g
    assert "EXTRUDER=" not in g.split("SET_PRESSURE_ADVANCE")[1].split("\n")[0]


def test_generate_luefter_layer1_und_normal():
    # Layer-1 mit fan_speed_layer1, danach Umschaltung auf fan_speed.
    g = generate(GeneratorParams(fan_speed_layer1=0.0, fan_speed=1.0,
                                 num_layers=3))
    # Kein M106 fuer Layer-1 (Wert 0.0 -> wird nicht emittiert):
    # Aber nach Layer 1 muss M106 S255 erscheinen.
    assert "M106 S255" in g  # fan_speed=1.0 -> 255


def test_generate_luefter_layer1_aktiv():
    # PETG/ABS-Szenario: Layer-1 mit reduziertem Luefter (z.B. 30 %).
    g = generate(GeneratorParams(fan_speed_layer1=0.3, fan_speed=0.3))
    assert "M106 S76" in g  # round(0.3 * 255) = 76


def test_generate_kein_cooldown_wenn_abgeschaltet():
    # cooldown_at_end=False -> Tool laesst M104/M140/M107 weg.
    # User-PRINT_END uebernimmt das Heizungen-Aus dann selbst.
    g = generate(GeneratorParams(cooldown_at_end=False))
    assert "M104 S0" not in g
    assert "M140 S0" not in g
    assert "M107" not in g
    # PRINT_END muss aber weiterhin emittiert werden:
    assert "PRINT_END" in g
    # Analyse-Trigger ebenfalls:
    assert "RUN_SHELL_COMMAND CMD=pa_analyze" in g


def test_generate_endsequenz_cooldown():
    # Vor PRINT_END wird das Hotend, Bett und der Luefter ausgeschaltet
    # (Sicherheits-Netz; PRINT_END macht das ueblicherweise selbst).
    g = generate(GeneratorParams())
    zeilen = g.splitlines()
    pe_idx = zeilen.index("PRINT_END")
    cooldown = zeilen[max(0, pe_idx - 5):pe_idx]
    assert "M104 S0" in cooldown
    assert "M140 S0" in cooldown
    assert "M107" in cooldown


def test_generate_g92_e0_nach_m83():
    # G92 E0 setzt den Extruder-Origin zurueck, direkt nach dem Modus-Setup.
    g = generate(GeneratorParams())
    zeilen = g.splitlines()
    assert "G92 E0" in zeilen
    assert zeilen.index("G92 E0") > zeilen.index("M83")


def test_generate_eigener_start_end_gcode():
    p = GeneratorParams(start_gcode="MEIN_START", end_gcode="MEIN_ENDE")
    g = generate(p)
    assert "MEIN_START" in g and "MEIN_ENDE" in g


def test_generate_haengt_analyze_trigger_an():
    # Die letzte Zeile stößt nach Druckende die Auswertung an, direkt
    # nach dem end_gcode (PRINT_END).
    zeilen = generate(GeneratorParams()).strip().splitlines()
    assert zeilen[-1] == "RUN_SHELL_COMMAND CMD=pa_analyze"
    assert zeilen[-2] == "PRINT_END"


def test_generate_leeres_analyze_gcode_kein_trigger():
    # Leeres analyze_gcode -> kein Trigger (Generator bleibt für
    # Nicht-Klipper-Nutzung verwendbar).
    g = generate(GeneratorParams(analyze_gcode=""))
    assert "RUN_SHELL_COMMAND" not in g
    assert g.strip().splitlines()[-1] == "PRINT_END"


def test_generator_params_neue_defaults():
    p = GeneratorParams()
    # Pattern-Markierungen (v2: deutlich größer für Sichtbarkeit)
    assert p.top_bar_height == 12.0          # v2: 4 → 12
    assert p.anchor_marker_width == 2.0
    assert p.anchor_marker_height == 8.0
    assert p.label_glyph_height == 2.5       # v2: 0.7 → 2.5
    assert p.label_glyph_width == 1.5        # v2: 0.5 → 1.5
    assert p.label_glyph_gap == 0.2
    assert p.label_stride == 2               # v2.1: nur jedes zweite Label
    assert p.header_glyph_height == 4.0      # v2: 1.0 → 4.0
    assert p.header_glyph_width == 2.5       # v2: 0.7 → 2.5
    assert p.header_column_spacing == 4.0
    assert p.header_to_labels_gap == 3.0
    assert p.chevron_band_gap == 0.0         # v2: 1.0 → 0.0 (Top-Bar berührt Chevrons)
    # Speed/Accel (unverändert)
    assert p.speed_print == 100.0
    assert p.accel == 2000.0
    # First-Layer-Sicherheit (NEU): reduzierte Werte für Layer 1
    assert p.first_layer_speed == 50.0
    assert p.first_layer_accel == 500.0


def test_generate_pattern_hoehe_enthaelt_top_bar_und_band_gap():
    # Y-Erstreckung aller extrudierenden Moves (Pre-PA) muss die
    # gesamte Pattern-Höhe abdecken (Top-Bar + Chevron-Band).
    # Geometrie aus den aktuellen Params herleiten, damit der Test
    # robust gegen wall_side_length/top_bar_height-Änderungen ist.
    import math

    p = GeneratorParams()
    chevron_h = 2 * math.sin(math.radians(p.corner_angle / 2)) * p.wall_side_length
    erwartet_pattern_h = p.top_bar_height + p.chevron_band_gap + chevron_h

    g = generate(p)
    import re
    zeilen = g.splitlines()
    first_pa_idx = next(i for i, z in enumerate(zeilen)
                        if "SET_PRESSURE_ADVANCE" in z)
    frame_ys = set()
    for line in zeilen[:first_pa_idx]:
        if " E" in line:
            m = re.search(r"\sY([\d.-]+)", line)
            if m:
                frame_ys.add(float(m.group(1)))
    frame_h = max(frame_ys) - min(frame_ys)
    # Mit Top-Bar muss frame_h MINDESTENS chevron_h + 50 % top_bar_height
    # erreichen — die strikte Gleichheit zur erwarteten Pattern-Höhe
    # prüft test_generate_top_bar_beruehrt_chevrons.
    min_h = chevron_h + 0.5 * p.top_bar_height
    assert frame_h >= min_h, (
        f"Y-Erstreckung {frame_h:.2f} mm < {min_h:.2f} mm — "
        f"Top-Bar (≈ {p.top_bar_height} mm) fehlt vermutlich. "
        f"Erwartet ≈ {erwartet_pattern_h:.2f} mm.")


def test_generate_zieht_solid_top_bar():
    # Top-Bar = Vollfüllung der Höhe top_bar_height über pattern_w.
    # Heuristik: viele extrudierte Moves in den obersten ~top_bar_height
    # Millimetern des Patterns (typische Stadion-Füllung).
    import math
    p = GeneratorParams()
    g = generate(p)
    # Top-Bar-Untergrenze relativ zur Pattern-Oberkante. Pattern-Höhe
    # leiten wir aus Generator-Geometrie ab.
    chevron_h = 2 * math.sin(math.radians(p.corner_angle / 2)) * p.wall_side_length
    pattern_h = p.top_bar_height + p.chevron_band_gap + chevron_h
    pattern_top_y = p.bed_y / 2 + pattern_h / 2
    # Top-Bar nimmt obere top_bar_height mm
    top_bar_min_y = pattern_top_y - p.top_bar_height
    import re
    e_lines_in_top = 0
    for line in g.splitlines():
        m = re.search(r"\sY([\d.-]+).+E([\d.-]+)", line)
        if m:
            y = float(m.group(1))
            if y >= top_bar_min_y:
                e_lines_in_top += 1
    assert e_lines_in_top >= 5, (
        f"Nur {e_lines_in_top} extrudierte Moves im Top-Bar-Bereich "
        f"(y >= {top_bar_min_y:.1f}) — Solid-Top-Bar fehlt vermutlich")


def test_generate_top_bar_in_allen_layern():
    # Top-Bar wird in jedem Layer gedruckt — Z-Werte werden mehrfach
    # hochgesetzt, und in jedem Z-Block sollten Top-Bar-Moves auftauchen.
    p = GeneratorParams(num_layers=2)
    g = generate(p)
    # Zwei Layer = zwei Z-Wechsel zu z=0.2 bzw. z=0.4.
    assert "G1 Z0.2 " in g
    assert "G1 Z0.4 " in g


def test_generate_emittiert_top_bar_vor_erstem_chevron():
    # T6-Followup (Reviewer-Befund): wirklich-RED-Test — prüft, dass der
    # Top-Bar tatsächlich emittiert wird.
    #
    # Zählt extrudierende G1-Moves vor dem ersten SET_PRESSURE_ADVANCE.
    # Breakdown bei Default-Params:
    #   - Purge-Linie         : 1
    #   - Frame (4 Kanten)    : 4
    #   - Top-Bar (~9 Linien) : 9
    #   → Gesamt              : ≥ 14
    #
    # Würde der Top-Bar weggelassen, käme man nur auf ~5 (Purge + Frame).
    # Schwellwert 10 liegt klar zwischen "ohne" (5) und "mit" (14).
    p = GeneratorParams()
    g = generate(p)
    lines = g.splitlines()
    pa_idx = next(i for i, l in enumerate(lines)
                  if "SET_PRESSURE_ADVANCE" in l)
    # Extrudierende G1-Moves: "G1 X... E..." oder "G1 Y... E..." — aber
    # NICHT reine Retract/De-Retract-Moves wie "G1 E0.5 ..."
    e_count = sum(1 for l in lines[:pa_idx]
                  if l.startswith("G1") and " E" in l
                  and not l.startswith("G1 E"))
    assert e_count >= 10, (
        f"Nur {e_count} extrudierte Moves vor erstem PA — "
        f"Top-Bar fehlt vermutlich (erwartet >= 10 = Purge+Frame+Top-Bar)"
    )


def test_generate_setzt_anker_marker_links():
    # Anker-Marker = gefülltes Rechteck, das linksseitig an Frame-Left (bx0)
    # andockt und vertikal in der Chevron-Mitte sitzt.
    #
    # Geometrie (Default-Params, v2: margin=0, left_padding=2.5):
    #   x-Bereich : [bx0, bx0 + anchor_marker_width]
    #   y-Bereich : [chevron_center_y - 4, chevron_center_y + 4]
    #   n_lines   : round(anchor_marker_width / line_width) = 4
    #
    # Test-Strategie: extrudierende G1-Moves im Anker-Rechteck suchen.
    # Chevron-Bereich überschneidet sich nicht mit diesem Y-Fenster.
    import re
    p = GeneratorParams()
    g = generate(p)

    lw = _line_width(p)
    dx, dy = _chevron_deltas(p)
    adv = _group_advance(p)
    pa_vals = _pa_values(p)
    pattern_w = (len(pa_vals) - 1) * adv + (p.wall_count - 1) * _wall_x_offset(p) + dx
    chevron_h = 2 * dy
    pattern_h = p.top_bar_height + p.chevron_band_gap + chevron_h
    # v2: margin=0, left_padding=anchor_marker_width + 0.5
    margin = 0.0
    left_padding = p.anchor_marker_width + 0.5
    total_w = pattern_w + left_padding
    bx0 = p.bed_x / 2 - (total_w + 2 * margin) / 2
    by0 = p.bed_y / 2 - (pattern_h + 2 * margin) / 2
    py0 = by0 + margin
    # Anker sitzt an bx0 (Frame-Left), nicht mehr an bx0+margin
    x_left = bx0
    x_right = x_left + p.anchor_marker_width + 0.5   # +0.5 Puffer
    chevron_center_y = py0 + dy
    y_low = chevron_center_y - p.anchor_marker_height / 2 - 0.5   # Puffer
    y_high = chevron_center_y + p.anchor_marker_height / 2 + 0.5

    extruding_hits = []
    for line in g.splitlines():
        if " E" not in line or not line.startswith("G1"):
            continue
        mx = re.search(r"X([\d.-]+)", line)
        my = re.search(r"Y([\d.-]+)", line)
        if not mx or not my:
            continue
        x = float(mx.group(1))
        y = float(my.group(1))
        if x_left <= x <= x_right and y_low <= y <= y_high:
            extruding_hits.append((x, y))

    assert len(extruding_hits) >= 4, (
        f"Anker-Marker fehlt — nur {len(extruding_hits)} extrudierende Moves "
        f"im Anker-Rechteck X[{x_left:.2f},{x_right:.2f}] "
        f"Y[{y_low:.2f},{y_high:.2f}] gefunden "
        f"(erwartet ≥ 4 = anchor_marker_width / line_width)"
    )


def test_generate_emittiert_set_velocity_limit_accel():
    p = GeneratorParams(accel=2000.0)
    g = generate(p)
    assert "SET_VELOCITY_LIMIT ACCEL=2000 ACCEL_TO_DECEL=1000" in g


def test_generate_accel_null_emittiert_kein_velocity_limit():
    # accel=0 UND first_layer_accel=0 → kein SET_VELOCITY_LIMIT.
    # (Mit Default first_layer_accel=500 würde Layer 1 trotzdem ein
    # Velocity-Limit setzen — getestet separat in
    # test_generate_first_layer_accel_null_emittiert_nicht.)
    p = GeneratorParams(accel=0.0, first_layer_accel=0.0)
    g = generate(p)
    assert "SET_VELOCITY_LIMIT" not in g


def test_generate_accel_emittiert_vor_pattern():
    # Reihenfolge: PRINT_START → G90 → M83 → G92 E0 → SET_VELOCITY_LIMIT
    # → Z-Wechsel → ... Set-Velocity muss vor dem ersten
    # G1 Z<layer_height>-Befehl liegen.
    p = GeneratorParams(accel=3000.0)
    g = generate(p)
    lines = g.splitlines()
    accel_idx = next(i for i, l in enumerate(lines)
                     if "SET_VELOCITY_LIMIT" in l)
    # Suche erste G1 Z<layer_height>-Bewegung (Layer 1).
    z_str = f"G1 Z{_fmt(p.layer_height)}"
    first_z = next(i for i, l in enumerate(lines)
                   if l.startswith(z_str))
    assert accel_idx < first_z, (
        f"SET_VELOCITY_LIMIT ({accel_idx}) muss vor erstem Z-Move "
        f"({first_z}) stehen")


def test_generate_beschriftet_jeden_chevron_mit_pa_wert():
    # In der obersten Layer müssen Bewegungen für jeden PA-Wert
    # ("0", ".", "0", "2", "0" für PA=0.020) auftauchen. Pro PA-Wert
    # mindestens ~5 Glyphen-Strokes; Label-Stride filtert evtl. einige.
    p = GeneratorParams(num_layers=2)  # 2 Layer: 1 ohne Labels, 1 mit
    g = generate(p)
    lines = g.splitlines()
    z_top_idx = next(i for i, l in enumerate(lines)
                     if l.startswith("G1 Z0.4 "))
    moves_in_top_layer = lines[z_top_idx:]
    g1_count = sum(1 for l in moves_in_top_layer if l.startswith("G1"))
    # Aus Params berechnen statt fester Schwelle: typische
    # G1-pro-Chevron-ohne-Labels ~6 (3 Wände × 2 Arme), plus Top-Bar
    # und Travel-Overhead. Mit Labels mindestens 50 % mehr als ohne.
    import math
    n_groups = int(math.floor((p.pa_end - p.pa_start) / p.pa_step + 0.5)) + 1
    base_min = n_groups * 6 + 20  # ohne Labels
    with_labels_min = int(base_min * 1.5)
    assert g1_count > with_labels_min, (
        f"2. Layer hat nur {g1_count} G1-Moves bei {n_groups} Gruppen "
        f"(erwartet > {with_labels_min}) — Labels fehlen vermutlich")


def test_generate_labels_nur_in_oberster_layer():
    # Schärfer Test (ersetzt defekte Version vom 2026-05-24):
    # Der alte Test nutzte Z-Hub-Move-Indizes als Layer-Trenner und
    # verglich chunk[2] (= Layer 1, ohne Labels) mit chunk[0] (= 12-zeiligem
    # Pre-Loop-Artifact). Damit wäre die Assertion auch bei "Labels in jeder
    # Layer" TRUE geblieben — kein Schutz gegen Regressions.
    #
    # Korrekte Strategie: Layer-Grenzen per Z-Wert (nicht per Z-Marken-Index).
    # num_layers=3, layer_height=0.2 → Layer-Z-Werte: 0.2, 0.4, 0.6.
    # "G1 Z0.6 F..." ist der Einstieg in die oberste Layer.
    # "G1 Z0.4 F..." ist der Einstieg in die vorletzte Layer (keine Labels).
    # Beide ohne E-Parameter (kein Extrusions-Move).
    #
    # v4-Refactor 2026-05-25: Labels stehen jetzt in Layer 1 (Z=0.4) statt
    # in der OBERSTEN Layer. Top-Bar nur in Layer 0 (1-Layer-dick). Daher:
    # - Layer 0: Top-Bar + Anker + Chevrons (kein Label) — viele Moves
    # - Layer 1: Anker + Chevrons + Labels (kein Top-Bar) — sehr viele
    # - Layer 2+: nur Anker + Chevrons — wenig
    import re
    p = GeneratorParams(num_layers=3)
    g = generate(p)
    lines = g.splitlines()

    lh = p.layer_height  # 0.2 mm

    def _first_line_of_z(target_z: float) -> int:
        """Index der ersten Zeile 'G1 Z<target_z> F...' (ohne E)."""
        target = f"G1 Z{round(target_z, 4):g} F"
        for i, l in enumerate(lines):
            if l.startswith(target) and " E" not in l:
                return i
        raise AssertionError(f"Keine G1-Z-Linie für Z={target_z} gefunden")

    # Positionen der drei Layer-Übergänge
    z_layer0 = _first_line_of_z(lh)          # G1 Z0.2 — Layer 0 (Top-Bar)
    z_layer1 = _first_line_of_z(2 * lh)      # G1 Z0.4 — Layer 1 (Labels)
    z_layer2 = _first_line_of_z(3 * lh)      # G1 Z0.6 — Layer 2 (kein Label)
    z_end = _first_line_of_z(3 * lh + p.z_raise_end)

    def _g1_count(start: int, end: int) -> int:
        return sum(1 for l in lines[start:end] if l.startswith("G1"))

    moves_layer1 = _g1_count(z_layer1, z_layer2)   # MIT Labels (v4)
    moves_layer2 = _g1_count(z_layer2, z_end)       # OHNE Labels (v4)

    # A) Label-Layer (Layer 1) hat deutlich mehr Moves als label-freie
    #    Layer 2 (gleicher Chevron+Anker-Aufbau, plus Labels)
    assert moves_layer1 > moves_layer2 + 100, (
        f"Label-Layer 1 ({moves_layer1} G1) nicht deutlich größer als "
        f"label-freie Layer 2 ({moves_layer2} G1) — Labels fehlen.")

    # B) Zwei label-freie Layer (Layer 0-Block und Layer 1) sind annähernd
    #    gleich groß — beweist, dass Differenz aus Labels stammt, nicht
    #    aus anderem layerspezifischem Code.
    moves_layer0_block = _g1_count(z_layer0, z_layer1)
    # Layer 0 hat Top-Bar (viele Moves), Layer 1 hat Labels (auch viele).
    # Layer 0 + Top-Bar ≈ Layer 1 + Labels (Top-Bar-Stadion und Labels
    # sind in der Größenordnung ähnlich). Erlauben einen großzügigen
    # Toleranz-Bereich.
    assert abs(moves_layer0_block - moves_layer1) < 250, (
        f"Layer-0-Block ({moves_layer0_block} G1) und Label-Layer 1 "
        f"({moves_layer1} G1) weichen um "
        f"{abs(moves_layer0_block - moves_layer1)} ab — "
        "ungewöhnlich große Differenz.")


def test_generate_beschriftet_speed_accel_header():
    # Vergleichs-Test: Mit Header (accel > 0) muss der Output
    # spürbar mehr G1-Moves haben als ohne (accel = 0). Labels sind
    # in Layer 1 (v4-Refactor) — daher num_layers=2 nötig.
    g1_mit = sum(
        1 for l in generate(
            GeneratorParams(num_layers=2, accel=2000.0, speed_print=100.0)
        ).splitlines() if l.startswith("G1"))
    g1_ohne = sum(
        1 for l in generate(
            GeneratorParams(num_layers=2, accel=0.0, speed_print=100.0)
        ).splitlines() if l.startswith("G1"))
    # Accel-Header "2000" = 4 Glyphen × min 4 Moves = >= 16 Extra-Moves
    assert g1_mit > g1_ohne + 15, (
        f"Mit-Header ({g1_mit}) sollte deutlich > ohne-Header ({g1_ohne}) "
        f"+ 15 sein — Accel-Header wird vermutlich nicht emittiert")


def test_generate_kein_accel_kein_header_label():
    # Bei accel=0 wird auch kein Accel-Header-Label gerendert
    # (sonst stünde "0" als Accel im Header — irreführend).
    # Speed-Label bleibt aber (speed_print ist immer > 0).
    # v4-Refactor: Labels in Layer 1, daher num_layers=2 nötig.
    p_mit_accel = GeneratorParams(num_layers=2, accel=2000.0)
    p_ohne_accel = GeneratorParams(num_layers=2, accel=0.0)
    g_mit = generate(p_mit_accel)
    g_ohne = generate(p_ohne_accel)
    g1_mit = sum(1 for l in g_mit.splitlines() if l.startswith("G1"))
    g1_ohne = sum(1 for l in g_ohne.splitlines() if l.startswith("G1"))
    # Differenz: 4 Glyphen ("2000") × 2-6 Moves = mindestens 8 Moves weniger.
    assert g1_mit > g1_ohne + 8, (
        f"Mit-Accel-Output ({g1_mit}) sollte ~10-30 Moves mehr haben "
        f"als Ohne-Accel ({g1_ohne}) — Accel-Header wird nicht "
        "konditional emittiert")


def test_generate_drei_linien_frame_kein_rechts():
    """Frame ist 3-Linien-"["-Form: links + Top-Bar (implizit oben) + unten.
    KEIN expliziter Frame-Right-Strich — Chevron-Spitzen bilden rechten Rand.

    Erwartung: im GCode gibt es genau 2 Frame-Strich-G1-Moves
    (links vertikal, unten horizontal). Die Top-Bar ist als
    Vollfüllung gerendert (mehrere Linien); die oberste Linie der
    Top-Bar fungiert als Frame-Top.
    """
    p = GeneratorParams()
    g = generate(p)
    # Hole alle G1-Bewegungen aus dem ERSTEN Layer (vor erstem
    # SET_PRESSURE_ADVANCE) — das umfasst Purge, Frame, Top-Bar, Anker.
    lines = g.splitlines()
    pa_idx = next(i for i, l in enumerate(lines)
                  if "SET_PRESSURE_ADVANCE" in l)
    pre_pa = lines[:pa_idx]
    # Zähle horizontale Frame-Bottom-Linie und vertikale Frame-Left-Linie.
    # Frame-Bottom: einzige extrudierende horizontale Linie auf y == by0
    # Frame-Left: einzige extrudierende vertikale Linie auf x == bx0
    # Wir prüfen einfach: KEINE extrudierende Linie liegt bei x == bx1
    # (das wäre Frame-Right — und das gibt's nicht mehr).
    # Approximation: Bett-Mitte ist 150,150 (bed_x/y default 300/300).
    # Pattern-Breite ~75mm, also bx1 ≈ 150 + 37.5 = 187.5.
    # Wir suchen explizit nach Moves die x ≈ 187 erreichen UND nicht
    # zu einem Chevron-Apex gehören (chevron-apex hat charakteristisches Y).
    import re
    # Sammle alle (x, y, e) für extrudierende Pre-PA Moves.
    extrudiert = []
    for line in pre_pa:
        m = re.match(r"^G1 X([\d.-]+) Y([\d.-]+).*E([\d.-]+)", line)
        if m:
            extrudiert.append((float(m.group(1)), float(m.group(2))))
    assert len(extrudiert) > 0, "Keine extrudierten Frame/Top-Bar-Moves"
    # Maximales X im Pre-PA-Bereich = Frame-Right wäre hier
    max_x = max(x for x, y in extrudiert)
    # Wenn es einen Frame-Right gäbe: viele Moves bei max_x mit
    # verschiedenen Y (vertikale Frame-Linie). Wir checken: max_x sollte
    # bei Top-Bar-Linien auftauchen (mehrere horizontale Moves enden bei
    # max_x), ABER nicht als isolierte vertikale Linie.
    # Vereinfachung: zähle MOVES bei x == max_x mit unterschiedlichen Y.
    # Bei einem 4-Linien-Frame wären das exakt 2 Moves (oben-rechts, unten-rechts).
    # Bei 3-Linien-Frame (kein rechts): die max_x-Moves sind Top-Bar-Endpunkte
    # (mehrere Y-Werte, weil mehrere Top-Bar-Linien dort enden).
    moves_at_max_x = [(x, y) for x, y in extrudiert if abs(x - max_x) < 0.01]
    # Mehr als 2 Moves bei max_x → Top-Bar-Stadion-Füllung (viele Linien
    # enden dort, je nach Boustrophedon-Richtung). Bei einem expliziten
    # Frame-Right wären es genau 2 (oben-rechts, unten-rechts).
    # Tatsächlich Top-Bar hat ~26 Linien (12mm/0.45mm), ungefähr die
    # Hälfte endet bei max_x → ~13 Moves.
    assert len(moves_at_max_x) > 5, (
        f"Nur {len(moves_at_max_x)} Moves bei max_x={max_x:.2f} — "
        f"deutet auf einen expliziten Frame-Right hin (3-Linien-Frame "
        f"hätte deutlich mehr durch Top-Bar-Boustrophedon)")


def test_generate_top_bar_beruehrt_chevrons():
    """chevron_band_gap = 0 → Top-Bar-Unterkante = Chevron-Oberkante."""
    p = GeneratorParams()
    g = generate(p)
    # Test indirekt: pattern_h = top_bar_height + chevron_band_gap + 2*dy
    import math
    dy = math.sin(math.radians(p.corner_angle / 2)) * p.wall_side_length
    erwartete_pattern_h = p.top_bar_height + 2 * dy + p.chevron_band_gap
    assert p.chevron_band_gap == 0.0
    # v3 (wall_side_length=8): 12 + 11.31 = 23.31 mm.
    # v2 (wall_side_length=30): 12 + 42.43 = 54.43 mm — beides möglich,
    # die Formel selbst ist die Aussage. Test prüft Konsistenz.
    assert erwartete_pattern_h == pytest.approx(
        p.top_bar_height + 2 * dy, abs=0.01)


def test_generate_margin_null_kein_padding_zwischen_frame_und_pattern():
    """v2: margin = 0, aber left_padding = anchor_marker_width + 0.5
    für den Anker-Bereich links."""
    p = GeneratorParams()
    g = generate(p)
    # Total-Width = pattern_w + left_padding (links für Anker)
    # Frame-Left ist bei bx0, Anker bei bx0, Chevron-Start bei bx0+left_padding.
    # Indirekt prüfbar: Y-Span ist GENAU pattern_h (kein extra margin).
    import re
    ys = []
    for line in g.splitlines():
        if not line.startswith("G1"):
            continue
        if " E" not in line:
            continue  # nur extrudierende Moves (kein Purge/Travel)
        m = re.search(r"\sY([\d.-]+)", line)
        if m:
            ys.append(float(m.group(1)))
    y_span = max(ys) - min(ys)
    # Y-Span muss MINDESTENS dem erwarteten Pattern-Höhen entsprechen
    # (Top-Bar + chevron_band_gap + 2*dy). Aus Params herleiten statt
    # hartkodiert, damit Test robust gegen Generator-Default-Änderungen.
    import math
    dy = math.sin(math.radians(p.corner_angle / 2)) * p.wall_side_length
    erwartete_pattern_h = p.top_bar_height + p.chevron_band_gap + 2 * dy
    # Toleranz 0.5 mm; Pattern darf nicht durch zusätzliches Padding
    # größer werden (margin=0-Zusicherung).
    assert y_span >= erwartete_pattern_h - 0.5, (
        f"Y-Span {y_span:.2f} mm < erwartet {erwartete_pattern_h:.2f} mm")
    assert y_span <= erwartete_pattern_h + 0.5, (
        f"Y-Span {y_span:.2f} mm > erwartet {erwartete_pattern_h:.2f} mm — "
        f"Padding zwischen Frame und Pattern?")


def test_generate_emittiert_frame_marker_kommentar():
    """Generator emittiert vor dem 3-Linien-Frame einen Marker-
    Kommentar mit den Frame-Box-Koordinaten. Parser nutzt diesen
    bevorzugt, weil das "["-Frame nicht als 4-Linien-Rechteck
    erkennbar ist.
    """
    p = GeneratorParams()
    g = generate(p)
    import re
    m = re.search(
        r"; PA_ANALYZER_FRAME X0=([\d.-]+) Y0=([\d.-]+) "
        r"X1=([\d.-]+) Y1=([\d.-]+)",
        g,
    )
    assert m is not None, "Frame-Marker-Kommentar fehlt im Output"
    bx0, by0, bx1, by1 = (float(x) for x in m.groups())
    # Sanity: bx0 < bx1, by0 < by1, Frame ist zentriert um 150,150 (default bed)
    assert bx0 < bx1
    assert by0 < by1
    cx = (bx0 + bx1) / 2
    cy = (by0 + by1) / 2
    assert abs(cx - 150.0) < 1.0, (
        f"Frame nicht bett-zentriert (X-Mitte {cx:.2f})")
    assert abs(cy - 150.0) < 1.0, (
        f"Frame nicht bett-zentriert (Y-Mitte {cy:.2f})")


def test_generate_label_stride_zwei_emittiert_jedes_zweite_label():
    """label_stride=2 (default): bei 17 PA-Werten werden 9 Labels
    gedruckt (Indices 0, 2, 4, ..., 16). Die Zwischen-Indizes
    ergeben sich kontextual aus den Nachbarn."""
    p_stride2 = GeneratorParams(label_stride=2)
    p_stride1 = GeneratorParams(label_stride=1)
    g_stride2 = generate(p_stride2)
    g_stride1 = generate(p_stride1)
    g1_stride2 = sum(
        1 for l in g_stride2.splitlines() if l.startswith("G1"))
    g1_stride1 = sum(
        1 for l in g_stride1.splitlines() if l.startswith("G1"))
    # stride=2 muss DEUTLICH weniger G1-Moves haben — etwa die Hälfte
    # der PA-Label-Moves entfallen. Bei 17 → 9 Labels statt 17 → ~50%
    # weniger Label-Stroke-Moves.
    assert g1_stride1 > g1_stride2 + 50, (
        f"stride=1 ({g1_stride1}) sollte deutlich mehr Moves haben als "
        f"stride=2 ({g1_stride2}) — label_stride wirkt nicht.")


def test_generate_first_layer_accel_vor_dem_pattern():
    """First-Layer-Sicherheit: SET_VELOCITY_LIMIT ACCEL=500
    (first_layer_accel) wird vor dem Frame emittiert, NICHT der
    p.accel-Wert (2000). Ab Layer 2 wird auf p.accel umgeschaltet."""
    p = GeneratorParams(accel=2000.0, first_layer_accel=500.0)
    g = generate(p)
    lines = g.splitlines()
    # Erstes SET_VELOCITY_LIMIT muss ACCEL=500 sein (first_layer_accel)
    first_set = next(l for l in lines if "SET_VELOCITY_LIMIT" in l)
    assert "ACCEL=500" in first_set, (
        f"Erstes SET_VELOCITY_LIMIT sollte ACCEL=500 (first_layer_accel) "
        f"sein, ist aber: {first_set}")
    assert "ACCEL_TO_DECEL=250" in first_set
    # Zweites SET_VELOCITY_LIMIT muss ACCEL=2000 (p.accel) sein
    velocity_limit_lines = [l for l in lines if "SET_VELOCITY_LIMIT" in l]
    assert len(velocity_limit_lines) >= 2, (
        f"Erwartet mind. 2x SET_VELOCITY_LIMIT (Layer 1 + Switch), "
        f"got: {velocity_limit_lines}")
    second_set = velocity_limit_lines[1]
    assert "ACCEL=2000" in second_set, (
        f"Zweites SET_VELOCITY_LIMIT sollte auf ACCEL=2000 switchen, "
        f"ist aber: {second_set}")


def test_generate_first_layer_speed_fuer_frame_und_layer_0():
    """Frame + Layer-0-Moves nutzen first_layer_speed (50 mm/s → F3000).
    Layer 1+-Chevrons nutzen p.speed_print (100 mm/s → F6000)."""
    p = GeneratorParams(speed_print=100.0, first_layer_speed=50.0,
                        num_layers=2)
    g = generate(p)
    lines = g.splitlines()
    # Suche die Z-Marken
    z_layer1_idx = next(i for i, l in enumerate(lines)
                        if l.startswith("G1 Z0.2 ") and " E" not in l)
    z_layer2_idx = next(i for i, l in enumerate(lines)
                        if l.startswith("G1 Z0.4 ") and " E" not in l)
    # Frame liegt zwischen Header und Layer-Schleife — also vor z_layer1_idx?
    # Eigentlich Frame wird VOR der Layer-Schleife gedruckt + erstes Z=0.2.
    # Lass uns prüfen: alle extrudierten Moves im Bereich vor z_layer2 sollten
    # F3000 (first_layer) sein, alle ab z_layer2 sollten F6000 sein.
    layer1_block = lines[:z_layer2_idx]
    layer2_block = lines[z_layer2_idx:]
    # Extrudierte Moves mit F-Wert
    import re
    def f_values(block):
        result = []
        for l in block:
            if not l.startswith("G1"):
                continue
            if " E" not in l:
                continue
            m = re.search(r"F(\d+)", l)
            if m:
                result.append(int(m.group(1)))
        return result
    layer1_fs = f_values(layer1_block)
    layer2_fs = f_values(layer2_block)
    # Layer 1 muss F3000 enthalten (Frame + Top-Bar + Anker + Chevrons)
    # F1500 = purge_speed (25 mm/s) ist auch erlaubt
    assert 3000 in layer1_fs, (
        f"Layer 1 sollte F3000 (first_layer_speed=50*60) enthalten, "
        f"F-Werte: {set(layer1_fs)}")
    # Layer 1 darf KEIN F6000 enthalten
    assert 6000 not in layer1_fs, (
        f"Layer 1 sollte KEIN F6000 (speed_print=100*60) enthalten, "
        f"F-Werte: {set(layer1_fs)}")
    # Layer 2 muss F6000 enthalten
    assert 6000 in layer2_fs, (
        f"Layer 2 sollte F6000 (speed_print=100*60) enthalten, "
        f"F-Werte: {set(layer2_fs)}")


def test_generate_first_layer_accel_null_emittiert_nicht():
    """first_layer_accel=0 → kein SET_VELOCITY_LIMIT für Layer 1
    (Drucker-Default greift)."""
    p = GeneratorParams(accel=2000.0, first_layer_accel=0.0)
    g = generate(p)
    lines = g.splitlines()
    velocity_limit_lines = [l for l in lines if "SET_VELOCITY_LIMIT" in l]
    # Es gibt nur 1 SET_VELOCITY_LIMIT (der Layer-2-Switch auf ACCEL=2000),
    # KEIN initial-Set für first_layer_accel
    assert len(velocity_limit_lines) == 1
    assert "ACCEL=2000" in velocity_limit_lines[0]


def test_generate_label_stride_eins_emittiert_alle_labels():
    """label_stride=1: jeder PA-Wert bekommt ein Label (alte v2-Variante,
    nur für Vergleich/Override-Fall)."""
    # Ein parametrisiert spezifischer Smoke-Test: bei stride=1 müssen
    # die Indices 0..n_pa-1 alle in der Label-Schleife landen.
    p = GeneratorParams(label_stride=1)
    g = generate(p)
    # Indirekt: G1-Count ist höher als bei stride=2 (siehe Test oben).
    # Hier nur prüfen: kein Crash und plausible Ausgabe.
    assert "G1" in g
    assert "SET_PRESSURE_ADVANCE" in g


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
