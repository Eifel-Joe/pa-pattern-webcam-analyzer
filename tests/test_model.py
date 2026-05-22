"""Tests für das PA-Pattern-Datenmodell."""
import pytest

from pa_analyzer.model import Chevron, FrameBox, PaGroup, PatternModel, Point


def test_point_ist_unveraenderlich():
    p = Point(1.0, 2.0)
    assert (p.x, p.y) == (1.0, 2.0)
    with pytest.raises(Exception):
        p.x = 9.0  # frozen dataclass


def test_chevron_haelt_drei_punkte():
    ch = Chevron(start=Point(0, 0), apex=Point(5, 5), end=Point(0, 10))
    assert ch.apex == Point(5, 5)


def test_pagroup_apex_ist_mittel_der_chevron_apexe():
    g = PaGroup(
        pa_value=0.02,
        chevrons=(
            Chevron(Point(0, 0), Point(10, 5), Point(0, 10)),
            Chevron(Point(0, 0), Point(12, 5), Point(0, 10)),
            Chevron(Point(0, 0), Point(14, 5), Point(0, 10)),
        ),
    )
    assert g.apex.x == pytest.approx(12.0)
    assert g.apex.y == pytest.approx(5.0)


def test_patternmodel_default_ohne_rahmenbox():
    m = PatternModel(groups=())
    assert m.groups == ()
    assert m.frame_box is None


def test_framebox_haelt_vier_ecken():
    ecken = (Point(0, 0), Point(0, 1), Point(1, 1), Point(1, 0))
    box = FrameBox(corners=ecken)
    assert len(box.corners) == 4


from pa_analyzer.model import AnalysisResult


def test_analysisresult_haelt_ergebnisfelder():
    r = AnalysisResult(
        best_pa=0.0285,
        nearest_step=0.028,
        confidence=0.7,
        scores=((0.01, 1.2), (0.012, 0.9)),
    )
    assert r.best_pa == pytest.approx(0.0285)
    assert r.nearest_step == pytest.approx(0.028)
    assert r.confidence == pytest.approx(0.7)
    assert len(r.scores) == 2
