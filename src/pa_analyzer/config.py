"""Lädt die Werkzeug-Konfiguration aus einer INI-Datei.

Die Konfiguration ist eine **pro-Drucker-Einstellungsvoraussetzung**:
Sie enthält Webcam-URL, Datei-Pfade und — entscheidend — die nicht
genormten PRINT_START/PRINT_END-Macro-Aufrufe. Jede Klipper-Installation
hat eine eigene Variante; der Generator baut den vollständigen GCode
genau um diese Aufrufe herum, damit das Tool auf jedem Drucker
funktioniert.

Format (siehe `pa_analyzer.example.conf` als Vorlage):

    [webcam]
    url = http://drucker.local/webcam/?action=snapshot

    [paths]
    gcode_path = /home/pi/printer_data/gcodes/pa_calibration.gcode
    report_path = /home/pi/printer_data/pa_report.json

    [macros]
    start_gcode =
        PRINT_START EXTRUDER={temp} BED={bed_temp}
    end_gcode =
        PRINT_END

Platzhalter `{temp}` und `{bed_temp}` werden vom Generator substituiert.
"""
from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """Laufzeit-Konfiguration. Fehlende Datei → reine Defaults.

    Die `*_gcode`-Felder überschreiben die `GeneratorParams`-Defaults
    (None = nicht überschreiben). `start_gcode` ist für `generate`
    Pflicht; die CLI bricht ohne Konfiguration klar ab.
    """

    webcam_url: str = ""
    gcode_path: str = "pa_calibration.gcode"
    report_path: str = "pa_report.json"
    start_gcode: str | None = None
    end_gcode: str | None = None
    analyze_gcode: str | None = None
    # True, wenn das start_gcode-Macro bereits eine Purge-Linie zieht
    # (z.B. ADAPTIVE_PURGE in KAMP-/Kiauh-Setups). Dann unterdrueckt
    # der Generator seine eigene Purge — sonst doppelte Purge-Linie.
    purge_in_start_macro: bool = False
    # True, wenn das end_gcode-Macro Hotend/Bett/Luefter selbst abschaltet.
    # Dann laesst der Generator M104 S0 / M140 S0 / M107 weg.
    cooldown_in_end_macro: bool = False


def _stripped_or_none(value: str | None) -> str | None:
    """Whitespace-Werte werden als None behandelt (== Schlüssel nicht gesetzt)."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def load_config(path: str | Path) -> Config:
    """Lädt die INI-Konfiguration. Fehlende Datei → reine Defaults.

    `interpolation=None` schaltet configparsers `%(name)s`-Magie ab —
    wichtig, weil PRINT_START-Aufrufe `%`-Zeichen enthalten können
    (z.B. in Klipper-Jinja2-Werten).
    """
    path = Path(path)
    if not path.is_file():
        return Config()
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(path.read_text(encoding="utf-8"))
    except configparser.Error as exc:
        # configparser.Error gehört nicht zu (OSError, ValueError) —
        # in ValueError umpacken, damit das zentrale CLI-Catch greift.
        raise ValueError(
            f"Konfiguration unlesbar: {path} ({exc})") from exc

    def get(section: str, option: str, default: str) -> str:
        return parser.get(section, option, fallback=default)

    return Config(
        webcam_url=get("webcam", "url", ""),
        gcode_path=get("paths", "gcode_path", "pa_calibration.gcode"),
        report_path=get("paths", "report_path", "pa_report.json"),
        start_gcode=_stripped_or_none(parser.get(
            "macros", "start_gcode", fallback=None)),
        end_gcode=_stripped_or_none(parser.get(
            "macros", "end_gcode", fallback=None)),
        analyze_gcode=_stripped_or_none(parser.get(
            "macros", "analyze_gcode", fallback=None)),
        purge_in_start_macro=parser.getboolean(
            "macros", "purge_in_start_macro", fallback=False),
        cooldown_in_end_macro=parser.getboolean(
            "macros", "cooldown_in_end_macro", fallback=False),
    )
