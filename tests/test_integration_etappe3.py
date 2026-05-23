"""End-zu-End-Test der Etappe-3-Integration (CLI-Kette)."""
from pathlib import Path

from pa_analyzer.cli import main
from pa_analyzer.gcode_parser import parse
from pa_analyzer.report import read_json

FIXTURES = Path(__file__).parent / "fixtures"


def test_generate_analyze_refine_kette(tmp_path, minimal_conf):
    # 1. Lauf-1-Pattern erzeugen.
    gcode1 = tmp_path / "lauf1.gcode"
    assert main(["--config", str(minimal_conf), "generate", "-o", str(gcode1),
                 "--pa-start", "0.0", "--pa-end", "0.05",
                 "--pa-step", "0.005"]) == 0
    assert len(parse(gcode1.read_text(encoding="utf-8")).groups) == 11

    # 2. Echtes Foto auswerten, Report als JSON schreiben (E3-A2).
    report = tmp_path / "report.json"
    assert main(["analyze", str(FIXTURES / "IMG_3843.HEIC"),
                 str(FIXTURES / "pa_pattern.gcode"),
                 "--json", str(report)]) == 0
    result = read_json(report)
    assert 0.026 <= result.best_pa <= 0.030

    # 3. Lauf-2-Pattern aus dem Report verfeinern.
    gcode2 = tmp_path / "lauf2.gcode"
    assert main(["--config", str(minimal_conf), "generate", "-o", str(gcode2),
                 "--refine-from", str(report)]) == 0
    pa2 = [g.pa_value for g in parse(
        gcode2.read_text(encoding="utf-8")).groups]
    # Lauf 2 ist enger als der volle Lauf-1-Bereich und nicht-negativ.
    assert min(pa2) >= 0.0
    assert 0.0 < max(pa2) - min(pa2) < 0.05
