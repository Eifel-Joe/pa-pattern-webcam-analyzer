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


def test_macro_uebergibt_filament_parameter():
    # PA_CALIBRATE MUSS TEMP, BED_TEMP, FLOW und FAN als Macro-Parameter
    # annehmen und an pa_generate weiterreichen (Spec §5 Entscheidung 2:
    # filament-spezifische Werte werden in den GCode eingebacken).
    text = _CFG.read_text(encoding="utf-8")
    assert "params.TEMP" in text
    assert "params.BED_TEMP" in text
    assert "params.FLOW" in text
    assert "params.FAN" in text
    assert "--temp" in text
    assert "--bed-temp" in text
    assert "--flow" in text
    assert "--fan" in text


def test_macro_uebergibt_speed_und_accel():
    # PA_CALIBRATE muss SPEED= und ACCEL= optional annehmen und an
    # pa_generate weiterreichen. Leere Defaults verhindern, dass eine
    # leere Klammer-Substitution dem CLI-Parser eine ungültige Zahl
    # zuschickt.
    text = _CFG.read_text(encoding="utf-8")
    assert "params.SPEED" in text
    assert "params.ACCEL" in text
    assert "--speed" in text
    assert "--accel" in text


def test_macro_uebergibt_walls():
    # PA_CALIBRATE muss WALLS= optional annehmen und an pa_generate
    # weiterreichen. Leerer Default wie SPEED/ACCEL.
    text = _CFG.read_text(encoding="utf-8")
    assert "params.WALLS" in text
    assert "--walls" in text
