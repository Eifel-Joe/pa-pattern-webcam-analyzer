"""Round-Trip-Tests: Generator-Ausgabe muss vom Parser verlustfrei lesbar sein."""
import pytest

from pa_analyzer.gcode_generator import GeneratorParams, generate
from pa_analyzer.gcode_parser import parse


def test_roundtrip_anzahl_gruppen():
    # num_layers=2 belegt die Layer-Deduplizierung: Layer vervielfachen
    # die Gruppen-Anzahl nicht.
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


def test_roundtrip_rahmenbox_geometrie_zentriert():
    # Die Rahmen-Box muss ein echtes Rechteck sein (genau 2 X- und 2
    # Y-Werte) und das Pattern auf dem Bett zentrieren.
    p = GeneratorParams(pa_start=0.0, pa_end=0.01, pa_step=0.005)
    model = parse(generate(p))
    assert model.frame_box is not None
    xs = sorted({c.x for c in model.frame_box.corners})
    ys = sorted({c.y for c in model.frame_box.corners})
    assert len(xs) == 2
    assert len(ys) == 2
    assert (xs[0] + xs[1]) / 2 == pytest.approx(p.bed_x / 2, abs=0.1)
    assert (ys[0] + ys[1]) / 2 == pytest.approx(p.bed_y / 2, abs=0.1)


def test_roundtrip_chevron_arme_symmetrisch():
    # start.x und end.x jedes Chevrons liegen auf gleicher X-Spalte
    p = GeneratorParams(wall_count=3, pa_start=0.0, pa_end=0.01, pa_step=0.005)
    model = parse(generate(p))
    for g in model.groups:
        for ch in g.chevrons:
            assert ch.start.x == pytest.approx(ch.end.x, abs=0.001)


def test_roundtrip_apex_y_konstant():
    # Alle Chevron-Spitzen liegen auf derselben Y-Hoehe
    p = GeneratorParams(pa_start=0.0, pa_end=0.01, pa_step=0.005)
    model = parse(generate(p))
    apex_ys = {round(g.apex.y, 3) for g in model.groups}
    assert len(apex_ys) == 1
