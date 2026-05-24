#!/usr/bin/env bash
# install.sh — PA-Analyzer auf dem Raspberry Pi (Klipper-Host) einrichten.
#
# Idempotent: mehrfach ausführbar. Bricht bei fehlenden Muss-
# Voraussetzungen mit Exit-Code != 0 und klarer Meldung ab.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${REPO_DIR}/.venv"
MIN_PYTHON="3.11"

echo "PA-Analyzer-Installation in ${REPO_DIR}"

# 1. Python >= 3.11 prüfen (Muss-Kriterium)
if ! command -v python3 >/dev/null 2>&1; then
    echo "FEHLER: python3 nicht gefunden. Python >= ${MIN_PYTHON} installieren." >&2
    exit 1
fi
PY_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [ "$(printf '%s\n%s\n' "${MIN_PYTHON}" "${PY_VERSION}" | sort -V | head -n1)" != "${MIN_PYTHON}" ]; then
    echo "FEHLER: Python ${PY_VERSION} gefunden, benötigt >= ${MIN_PYTHON}." >&2
    exit 1
fi
echo "  Python ${PY_VERSION} — OK"

# 2. Virtuelle Umgebung anlegen (idempotent) und Projekt installieren
if [ ! -d "${VENV_DIR}" ]; then
    python3 -m venv "${VENV_DIR}"
    echo "  venv angelegt: ${VENV_DIR}"
else
    echo "  venv vorhanden: ${VENV_DIR}"
fi
"${VENV_DIR}/bin/pip" install --upgrade pip >/dev/null
"${VENV_DIR}/bin/pip" install "${REPO_DIR}"
echo "  Abhängigkeiten installiert (opencv-python-headless, numpy, pillow-heif)"

# 3. gcode_shell_command prüfen (Soll-Kriterium, kein harter Abbruch).
# Standard-Pfad: ~/klipper/klippy/extras/gcode_shell_command.py — vom
# $HOME aus auf Tiefe 5. maxdepth 5 deckt das ab; weniger erzeugt
# falsch-positive "nicht gefunden"-Meldungen.
if find "${HOME}" -maxdepth 5 -path "*klippy/extras*" -name "gcode_shell_command.py" 2>/dev/null | grep -q .; then
    echo "  gcode_shell_command — gefunden"
else
    echo "  HINWEIS: gcode_shell_command nicht gefunden — für die Klipper-" >&2
    echo "  Anbindung nachinstallieren (z.B. via KIAUH)." >&2
fi

# 4. Klipper-Config-Verzeichnis erkennen und Macro-Dateien installieren.
# Standard ist ~/printer_data/config (Mainsail/Fluidd); historischer
# Fallback ~/klipper_config. Beides ohne Treffer -> manueller Schritt.
KLIPPER_CFG_DIR=""
if [ -d "${HOME}/printer_data/config" ]; then
    KLIPPER_CFG_DIR="${HOME}/printer_data/config"
elif [ -d "${HOME}/klipper_config" ]; then
    KLIPPER_CFG_DIR="${HOME}/klipper_config"
fi

if [ -n "${KLIPPER_CFG_DIR}" ]; then
    echo "  Klipper-Config-Verzeichnis: ${KLIPPER_CFG_DIR}"
    cp "${REPO_DIR}/klipper/pa_calibrate.cfg" "${KLIPPER_CFG_DIR}/"
    echo "    pa_calibrate.cfg → ${KLIPPER_CFG_DIR}/"
    cp "${REPO_DIR}/pa_analyzer.example.conf" "${KLIPPER_CFG_DIR}/"
    echo "    pa_analyzer.example.conf → ${KLIPPER_CFG_DIR}/"

    PRINTER_CFG="${KLIPPER_CFG_DIR}/printer.cfg"
    if [ -f "${PRINTER_CFG}" ]; then
        if grep -q '^\[include pa_calibrate.cfg\]' "${PRINTER_CFG}"; then
            echo "    [include pa_calibrate.cfg] schon in printer.cfg"
        else
            printf '\n[include pa_calibrate.cfg]\n' >> "${PRINTER_CFG}"
            echo "    [include pa_calibrate.cfg] zu printer.cfg hinzugefügt"
        fi
    else
        echo "    HINWEIS: ${PRINTER_CFG} nicht gefunden — bitte selbst" >&2
        echo "    [include pa_calibrate.cfg] in deine printer.cfg eintragen." >&2
    fi
else
    echo "  HINWEIS: Klipper-Config-Verzeichnis nicht gefunden" >&2
    echo "  (weder ~/printer_data/config noch ~/klipper_config)." >&2
    echo "  Bitte ${REPO_DIR}/klipper/pa_calibrate.cfg und" >&2
    echo "  ${REPO_DIR}/pa_analyzer.example.conf manuell ins" >&2
    echo "  Klipper-Config-Verzeichnis kopieren und in printer.cfg" >&2
    echo "  einbinden." >&2
fi

# 5. Abschluss-Hinweis (kontext-sensitiv)
echo
echo "Installation abgeschlossen. Nächste Schritte:"
if [ -n "${KLIPPER_CFG_DIR}" ]; then
    echo "  1. cp ${KLIPPER_CFG_DIR}/pa_analyzer.example.conf \\"
    echo "        ${KLIPPER_CFG_DIR}/pa_analyzer.conf"
    echo "     und an die PRINT_START/PRINT_END-Aufrufe deiner"
    echo "     Klipper-Installation anpassen (siehe README)."
    echo "  2. Klipper neu starten (Mainsail/Fluidd: \"Firmware Restart\"."
    echo "     oder: curl -X POST http://localhost:7125/printer/restart)"
    echo "  3. Pattern drucken und auswerten:  PA_CALIBRATE"
else
    echo "  1. pa_calibrate.cfg und pa_analyzer.example.conf manuell ins"
    echo "     Klipper-Config-Verzeichnis kopieren."
    echo "  2. pa_analyzer.example.conf nach pa_analyzer.conf umbenennen"
    echo "     und an deine PRINT_START/PRINT_END-Aufrufe anpassen."
    echo "  3. [include pa_calibrate.cfg] in printer.cfg eintragen."
    echo "  4. Klipper neu starten und PA_CALIBRATE ausführen."
fi
