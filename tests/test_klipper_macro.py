"""Smoke-Test für die committete Klipper-Macro-Datei."""
from pathlib import Path

_CFG = Path(__file__).parent.parent / "klipper" / "pa_calibrate.cfg"


def test_macro_datei_existiert():
    assert _CFG.is_file()


def test_macro_enthaelt_alle_sektionen():
    text = _CFG.read_text(encoding="utf-8")
    assert "[gcode_shell_command pa_generate]" in text
    assert "[gcode_shell_command pa_analyze]" in text
    assert "[gcode_macro PA_CALIBRATE]" in text
