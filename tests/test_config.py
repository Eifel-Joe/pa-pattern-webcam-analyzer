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
