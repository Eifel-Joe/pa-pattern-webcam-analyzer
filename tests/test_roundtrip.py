"""Round-Trip-Tests: Generator-Ausgabe muss vom Parser verlustfrei lesbar sein."""
import pytest

from pa_analyzer.gcode_generator import GeneratorParams, generate
from pa_analyzer.gcode_parser import parse


def test_roundtrip_anzahl_gruppen():
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
