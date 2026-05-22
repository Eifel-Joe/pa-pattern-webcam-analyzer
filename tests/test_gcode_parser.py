"""Tests für den GCode-Parser."""
import pytest

from pa_analyzer.gcode_parser import _Move, _tokenize, parse


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


def test_tokenize_ignoriert_achsenwerte_in_kommentaren():
    # Ein Kommentar mit achsen-aehnlichem Text darf keinen move-Token erzeugen
    assert list(_tokenize("G1 F6000 ; X123 im Kommentar\n")) == []


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


def test_parse_leerer_gcode_liefert_leeres_modell():
    model = parse("")
    assert model.groups == ()
    assert model.frame_box is None


def test_parse_gcode_ohne_pattern_liefert_keine_gruppen():
    # Bewegungen ohne SET_PRESSURE_ADVANCE und ohne Chevron-Struktur
    # ergeben ein leeres Modell statt eines Absturzes.
    model = parse("G90\nG1 X10 Y10 E1\nG1 X20 Y20 E1\n")
    assert model.groups == ()
    assert model.frame_box is None


def test_content_bounds_umschliesst_pattern(pa_pattern_gcode):
    # Bounding-Box aller extrudierten Pattern-Geometrie (Rahmen-Box +
    # Balken + Chevrons). Aus der GCode-Analyse: X ~100.7..199.3,
    # Y ~120.8..180.2.
    model = parse(pa_pattern_gcode)
    assert model.content_bounds is not None
    lo, hi = model.content_bounds
    assert lo.x == pytest.approx(100.731, abs=0.5)
    assert hi.x == pytest.approx(199.269, abs=0.5)
    assert lo.y == pytest.approx(120.787, abs=0.5)
    assert hi.y == pytest.approx(180.2, abs=1.0)


# ── Carry-over: G90/G91, M82/M83 (Etappe 3) ───────────────────────────

_BASIS = """\
G90
M83
SET_PRESSURE_ADVANCE ADVANCE=0.02
G1 X10 Y10 F1000
G1 X12 Y12 E0.5 F1000
G1 X10 Y14 E0.5 F1000
"""

_RELATIV_XY = """\
G91
M83
SET_PRESSURE_ADVANCE ADVANCE=0.02
G1 X10 Y10 F1000
G1 X2 Y2 E0.5 F1000
G1 X-2 Y2 E0.5 F1000
"""

_ABSOLUT_E = """\
G90
M82
SET_PRESSURE_ADVANCE ADVANCE=0.02
G1 X10 Y10 F1000
G1 X12 Y12 E0.5 F1000
G1 X10 Y14 E1.0 F1000
"""

_ABSOLUT_E_G92 = """\
G90
M82
SET_PRESSURE_ADVANCE ADVANCE=0.02
G1 X10 Y10 F1000
G1 X12 Y12 E0.5 F1000
G92 E0
G1 X10 Y14 E0.5 F1000
"""


def test_parse_g91_relativ_wie_g90_absolut():
    # Relative XY-Positionierung muss dasselbe Pattern ergeben wie die
    # absolute Variante mit identischer Geometrie.
    assert parse(_RELATIV_XY).groups == parse(_BASIS).groups


def test_parse_m82_absolut_e_wie_m83_relativ():
    # Bei M82 wird die Extrusion über das Delta zur vorigen E-Position
    # bestimmt — gleiches Pattern wie die relative M83-Variante.
    assert parse(_ABSOLUT_E).groups == parse(_BASIS).groups


def test_parse_m82_mit_g92_reset():
    # G92 E0 setzt den Extruder-Origin zurück; der folgende Move mit
    # E0.5 ist danach wieder eine Extrusion (Delta +0.5).
    assert parse(_ABSOLUT_E_G92).groups == parse(_BASIS).groups
