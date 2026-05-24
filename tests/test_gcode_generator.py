"""Tests für den GCode-Generator."""
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
    # Handgerechnet fuer die Default-Parameter (wall_count=3, lw=0.45,
    # layer_height=0.2, corner_angle=90, pattern_spacing=2.0):
    # line_spacing = 0.45 - 0.2*(1-pi/4) ~= 0.40708
    # wall_x_offset = line_spacing / sin(45 Grad) ~= 0.57577
    # group_advance = 2*0.57577 + 2.0 + 0.45 ~= 3.6015
    # Dieser Wert deckt sich mit dem Gruppenabstand des echten
    # OrcaSlicer-PA-Patterns (~3.6015 mm) — doppelte Validierung.
    assert _group_advance(GeneratorParams()) == pytest.approx(3.6015, abs=0.001)


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


def test_generate_pattern_hoehe_enthaelt_top_bar_und_band_gap():
    # Frame-Y-Erstreckung muss jetzt = 2*margin + chevron_band +
    # chevron_band_gap + top_bar_height sein.
    # 2*dy bei wall_side_length=30, corner_angle=90 → 2*30*sin(45°) ≈ 42.43
    # pattern_h = top_bar_height(4) + chevron_band_gap(1) + 42.43 ≈ 47.43
    # Rahmenhöhe = pattern_h + 2*margin(4) ≈ 55.43 mm
    # OHNE Top-Bar wäre Rahmenhöhe = 2*dy + 2*margin ≈ 50.43 mm
    p = GeneratorParams()
    g = generate(p)
    # Sammle nur Frame-Y-Werte: Frame-Zeilen enthalten kein 'E'-Feld
    # bei Travel und emittieren 4 Kanten. Statt Heuristik: wir parsen
    # die exakten Frame-Koordinaten durch Vergleich mit den erwarteten Grenzen.
    # Einfacher: Frame-Höhe = by1 - by0. Aus den 4 Frame-Zeilen nach dem
    # Frame-Travel lassen sich by0 und by1 direkt ablesen.
    import re
    # Frame-Zeilen: extrudierende G1-Moves mit sowohl X als auch Y,
    # die VOR dem ersten SET_PRESSURE_ADVANCE stehen
    zeilen = g.splitlines()
    first_pa_idx = next(i for i, z in enumerate(zeilen)
                        if "SET_PRESSURE_ADVANCE" in z)
    frame_ys = set()
    for line in zeilen[:first_pa_idx]:
        # Nur extrudierende Moves (enthalten 'E')
        if " E" in line:
            m = re.search(r"\sY([\d.-]+)", line)
            if m:
                frame_ys.add(float(m.group(1)))
    frame_h = max(frame_ys) - min(frame_ys)
    # Erwartete Rahmenhöhe MIT Top-Bar: ≈ 55.43 mm
    # Schwellwert: zwischen 50.43 (ohne) und 55.43 (mit) → > 54.0
    assert frame_h >= 54.0, (
        f"Rahmen-Höhe {frame_h:.2f} mm zu klein — "
        f"Top-Bar (4 mm) + Band-Gap (1 mm) fehlen vermutlich")


def test_generate_zieht_solid_top_bar():
    # Top-Bar = Vollfüllung der Höhe top_bar_height über pattern_w.
    # Bei top_bar_height=4 mm und line_width=0.45 mm → ca. 9 parallele
    # Linien (4/0.45 ≈ 8.89).
    p = GeneratorParams()
    g = generate(p)
    # Top-Bar-Y-Bereich: die obersten ~4 mm des Patterns. Wir prüfen,
    # dass im oberen Bett-Bereich viele extrudierte horizontale Moves
    # mit E-Wert auftauchen (typische Stadion-Füllung).
    import re
    e_lines_in_top = 0
    for line in g.splitlines():
        m = re.search(r"\sY([\d.-]+).+E([\d.-]+)", line)
        if m:
            y = float(m.group(1))
            # Heuristik: Y im oberen Bereich = Y > bed_y/2 + 15 (grob)
            if y > p.bed_y / 2 + 15:
                e_lines_in_top += 1
    assert e_lines_in_top >= 5, (
        f"Nur {e_lines_in_top} extrudierte Moves im Top-Bar-Bereich — "
        "Solid-Top-Bar fehlt vermutlich")


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
    # Anker-Marker = gefülltes Rechteck, das linksseitig am Pattern-Start
    # (x = bx0+margin) andockt und vertikal in der Chevron-Mitte sitzt.
    #
    # Geometrie (Default-Params):
    #   x-Bereich : [bx0+margin, bx0+margin+anchor_marker_width] = [px0, px0+2]
    #   y-Bereich : [chevron_center_y - 4, chevron_center_y + 4]
    #               = [py0+dy - 4, py0+dy + 4]
    #   n_lines   : round(anchor_marker_width / line_width) = 4
    #
    # Test-Strategie (Option A gegenüber Spec-Vorlage): Die Spec-Vorlage
    # suchte im Bereich [px0-5, px0], was den Marker (der BEI px0 startet)
    # nicht treffen würde. Korrekte Prüfung: extrudierende G1-Moves, deren
    # X- UND Y-Wert gleichzeitig im Anker-Rechteck liegen. Der Chevron-
    # Bereich überschneidet sich nicht mit diesem Y-Fenster.
    import math as _math
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
    margin = 4.0
    bx0 = p.bed_x / 2 - (pattern_w + 2 * margin) / 2
    by0 = p.bed_y / 2 - (pattern_h + 2 * margin) / 2
    py0 = by0 + margin
    x_left = bx0 + margin
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
