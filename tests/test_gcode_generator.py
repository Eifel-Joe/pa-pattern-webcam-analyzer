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
