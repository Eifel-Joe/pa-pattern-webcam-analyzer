"""Tests für das Laden der INI-Konfiguration."""
import pytest

from pa_analyzer.config import Config, load_config


def test_load_config_fehlende_datei_liefert_defaults(tmp_path):
    # Ohne Datei: reine Defaults. Validierung (start_gcode Pflicht)
    # passiert nicht hier, sondern im CLI-Subkommando.
    cfg = load_config(tmp_path / "gibt_es_nicht.conf")
    assert cfg == Config()


def test_load_config_liest_alle_sektionen(tmp_path):
    p = tmp_path / "pa_analyzer.conf"
    p.write_text(
        "[webcam]\n"
        "url = http://drucker/snapshot\n"
        "\n"
        "[paths]\n"
        "gcode_path = /home/pi/pa.gcode\n"
        "report_path = /home/pi/report.json\n"
        "\n"
        "[macros]\n"
        "start_gcode =\n"
        "    PRINT_START EXTRUDER={temp} BED={bed_temp}\n"
        "end_gcode =\n"
        "    PRINT_END\n"
        "analyze_gcode = RUN_SHELL_COMMAND CMD=mein_analyze\n",
        encoding="utf-8")
    cfg = load_config(p)
    assert cfg.webcam_url == "http://drucker/snapshot"
    assert cfg.gcode_path == "/home/pi/pa.gcode"
    assert cfg.report_path == "/home/pi/report.json"
    assert cfg.start_gcode == "PRINT_START EXTRUDER={temp} BED={bed_temp}"
    assert cfg.end_gcode == "PRINT_END"
    assert cfg.analyze_gcode == "RUN_SHELL_COMMAND CMD=mein_analyze"


def test_load_config_multiline_macro(tmp_path):
    # Multi-line: Folgezeilen einrücken; configparser strippt den Einzug
    # und verbindet mit Newlines.
    p = tmp_path / "pa_analyzer.conf"
    p.write_text(
        "[macros]\n"
        "start_gcode =\n"
        "    M117 PA Calibration\n"
        "    PRINT_START EXTRUDER={temp} BED={bed_temp}\n",
        encoding="utf-8")
    cfg = load_config(p)
    assert cfg.start_gcode == (
        "M117 PA Calibration\nPRINT_START EXTRUDER={temp} BED={bed_temp}")


def test_load_config_fehlende_macros_sektion_liefert_none(tmp_path):
    # Ohne [macros]-Sektion bleiben start_gcode etc. None — _cmd_generate
    # erkennt das und bricht klar ab.
    p = tmp_path / "pa_analyzer.conf"
    p.write_text("[webcam]\nurl = http://drucker/snap\n", encoding="utf-8")
    cfg = load_config(p)
    assert cfg.webcam_url == "http://drucker/snap"
    assert cfg.start_gcode is None
    assert cfg.end_gcode is None


def test_load_config_leerer_macro_wert_ist_none(tmp_path):
    # Ein leerer / nur-whitespace Wert zaehlt nicht als gesetzt.
    p = tmp_path / "pa_analyzer.conf"
    p.write_text("[macros]\nstart_gcode =   \n", encoding="utf-8")
    cfg = load_config(p)
    assert cfg.start_gcode is None


def test_load_config_kaputte_ini_wirft_valueerror(tmp_path):
    # configparser.Error wird in ValueError umverpackt, damit das
    # zentrale CLI-Catch (OSError, ValueError) greift.
    p = tmp_path / "pa_analyzer.conf"
    p.write_text("kein_section_header = nope\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(p)


def test_load_config_prozent_zeichen_im_macro_bleibt_erhalten(tmp_path):
    # interpolation=None: %-Zeichen werden NICHT als %()s-Interpolation
    # interpretiert (wichtig fuer Klipper-Jinja2-Werte).
    p = tmp_path / "pa_analyzer.conf"
    p.write_text(
        "[macros]\n"
        "start_gcode = PRINT_START EXTRA=50%%\n",
        encoding="utf-8")
    cfg = load_config(p)
    assert cfg.start_gcode == "PRINT_START EXTRA=50%%"
