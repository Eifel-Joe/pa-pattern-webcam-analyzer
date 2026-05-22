#!/usr/bin/env bash
# install.sh — PA-Analyzer auf dem Raspberry Pi (Klipper-Host) einrichten.
#
# Idempotent: mehrfach ausführbar. Bricht bei fehlenden Muss-
# Voraussetzungen mit Exit-Code != 0 und klarer Meldung ab.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${REPO_DIR}/.venv"
MIN_PYTHON="3.13"

echo "PA-Analyzer-Installation in ${REPO_DIR}"

# 1. Python >= 3.13 prüfen (Muss-Kriterium)
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

# 3. gcode_shell_command prüfen (Soll-Kriterium, kein harter Abbruch)
if find "${HOME}" -maxdepth 4 -path "*klippy/extras*" -name "gcode_shell_command.py" 2>/dev/null | grep -q .; then
    echo "  gcode_shell_command — gefunden"
else
    echo "  HINWEIS: gcode_shell_command nicht gefunden — für die Klipper-" >&2
    echo "  Anbindung nachinstallieren (z.B. via KIAUH)." >&2
fi

# 4. Abschluss-Hinweis
cat <<'HINWEIS'

Installation abgeschlossen. Nächste Schritte:
  1. pa_analyzer.json anlegen/anpassen (webcam_url, gcode_path,
     report_path) — siehe README.md.
  2. In die printer.cfg aufnehmen:  [include pa_calibrate.cfg]
     (Datei aus dem klipper/-Ordner dieses Repos.)
  3. Pattern drucken und auswerten:  PA_CALIBRATE
HINWEIS
