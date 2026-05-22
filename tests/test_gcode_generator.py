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
