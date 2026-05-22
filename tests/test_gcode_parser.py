"""Tests für den GCode-Parser."""
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


def test_tokenize_ignoriert_achsenwerte_in_kommentaren():
    # Ein Kommentar mit achsen-aehnlichem Text darf keinen move-Token erzeugen
    assert list(_tokenize("G1 F6000 ; X123 im Kommentar\n")) == []
