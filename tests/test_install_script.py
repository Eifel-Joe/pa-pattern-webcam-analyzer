"""Smoke-Test für install.sh (auf Windows nicht ausführbar — Inhalt)."""
from pathlib import Path

_SCRIPT = Path(__file__).parent.parent / "install.sh"


def test_install_sh_existiert_mit_shebang():
    assert _SCRIPT.is_file()
    assert _SCRIPT.read_text(encoding="utf-8").startswith("#!")


def test_install_sh_prueft_python_und_installiert():
    text = _SCRIPT.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text
    assert "python3" in text
    assert "pip" in text and "install" in text
    assert "gcode_shell_command" in text


def test_install_sh_kopiert_macro_und_aktualisiert_printer_cfg():
    # install.sh erkennt das Klipper-Config-Verzeichnis (standard:
    # ~/printer_data/config, Fallback ~/klipper_config), kopiert
    # pa_calibrate.cfg + pa_analyzer.example.conf dorthin und ergaenzt
    # [include pa_calibrate.cfg] idempotent in der printer.cfg.
    text = _SCRIPT.read_text(encoding="utf-8")
    # Config-Verzeichnis-Detection:
    assert "printer_data/config" in text
    assert "klipper_config" in text  # Fallback
    # Datei-Kopien:
    assert "pa_calibrate.cfg" in text
    assert "pa_analyzer.example.conf" in text
    # Idempotente printer.cfg-Edit:
    assert "[include pa_calibrate.cfg]" in text
    assert "grep" in text  # Idempotenz-Check


def test_install_sh_gcode_shell_command_find_maxdepth_korrekt():
    # Standard-Pfad /home/pi/klipper/klippy/extras/gcode_shell_command.py
    # liegt auf Tiefe 5 ab $HOME. maxdepth muss >= 5 sein, sonst
    # falsch-positive "nicht gefunden"-Meldung trotz Standard-Install.
    text = _SCRIPT.read_text(encoding="utf-8")
    assert "maxdepth 5" in text
