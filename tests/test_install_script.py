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
