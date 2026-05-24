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
