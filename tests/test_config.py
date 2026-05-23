"""Tests für das Laden der Konfiguration."""
import json

from pa_analyzer.config import Config, load_config


def test_load_config_fehlende_datei_liefert_defaults(tmp_path):
    cfg = load_config(tmp_path / "gibt_es_nicht.json")
    assert cfg == Config()


def test_load_config_liest_werte(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({
        "webcam_url": "http://drucker/snapshot",
        "gcode_path": "/home/pi/pa.gcode",
        "report_path": "/home/pi/report.json",
    }), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.webcam_url == "http://drucker/snapshot"
    assert cfg.gcode_path == "/home/pi/pa.gcode"
    assert cfg.report_path == "/home/pi/report.json"


def test_load_config_ignoriert_unbekannte_schluessel(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({
        "webcam_url": "http://drucker/snapshot",
        "veraltete_option": 123,
    }), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.webcam_url == "http://drucker/snapshot"
    assert cfg.gcode_path == "pa_calibration.gcode"  # Default


def test_load_config_start_gcode_default_none(tmp_path):
    # Ohne Eintrag bleibt start_gcode None -> CLI nimmt den
    # GeneratorParams-Default. Keine Default-Duplikation zwischen
    # Config und GeneratorParams.
    cfg = load_config(tmp_path / "missing.json")
    assert cfg.start_gcode is None
    assert cfg.end_gcode is None
    assert cfg.analyze_gcode is None


def test_load_config_liest_start_gcode_override(tmp_path):
    # PRINT_START-Signaturen sind nicht genormt — der Override muss aus
    # der JSON gelesen werden.
    p = tmp_path / "config.json"
    p.write_text(json.dumps({
        "start_gcode": "PRINT_START HOTEND={temp} BED_TEMP={bed_temp} "
                       "MATERIAL=PLA",
    }), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.start_gcode == ("PRINT_START HOTEND={temp} BED_TEMP={bed_temp} "
                               "MATERIAL=PLA")
