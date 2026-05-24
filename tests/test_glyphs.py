"""Unit-Tests für das Glyphen-Modul (Stroke-Font für Pattern-Labels)."""
import pytest

from pa_analyzer.glyphs import GLYPHS, render_label_gcode


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


def test_render_label_rotation_90_zwei_strokes_vollstaendig():
    # "8" hat 2 Strokes (Rechteck + Mittellinie). Beide müssen bei
    # rotation=90 rotiert werden — die for-stroke-Schleife darf nicht
    # vergessen, die Rotation auch im 2. Stroke anzuwenden.
    # Erwartung: 2 Travel-Moves (einer je Stroke-Anfang) im Output.
    lines = render_label_gcode("8", x=0.0, y=0.0, rotation=90,
                                **_druck_args())
    travel_moves = [z for z in lines
                    if z.startswith("G1") and " E" not in z]
    assert len(travel_moves) >= 2, (
        f"Erwartet >= 2 Travel-Moves für 2 Strokes, got: {travel_moves}")
    # Zusätzlich: alle X-Werte sollten >= 0 sein (Glyphe wird nach
    # rechts aufgebaut bei rotation=90), keine negative X.
    import re
    for line in lines:
        m = re.search(r"X([\d.-]+)", line)
        if m:
            x = float(m.group(1))
            assert x >= 0, (
                f"Negativer X bei rotation=90 in '{line}' — Rotation "
                f"des 2. Strokes ist evtl. ausgelassen")
