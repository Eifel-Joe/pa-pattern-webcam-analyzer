# Etappe 4 — Teil A (drucker-unabhängig) — Implementierungsplan

> **Für agentische Umsetzung:** ERFORDERLICHES SUB-SKILL:
> `superpowers:subagent-driven-development`. Schritte nutzen Checkbox-
> Syntax (`- [ ]`).

**Ziel:** Den drucker-unabhängigen Teil von Etappe 4 umsetzen —
Generator-Trailer, Klipper-Macros als Repo-Dateien, `install.sh`,
`README.md`. Macht das Repo veröffentlichungsreif.

**Architektur:** Eine kleine TDD-Code-Änderung (Generator) plus drei
neue Repo-Artefakte (Klipper-Config, Installationsskript, Doku). Alles
auf Windows ohne Drucker abschließbar.

**Bezug:** Spec `docs/specs/2026-05-23-etappe4-hardware.md` (Teil A).

**Nicht in diesem Plan:** Teil B (V1–V5-Verifikation, Live-Druck-Test,
Kalibrierungs-Fallbacks) — drucker-gebunden, wird erst nach
ausdrücklicher Nutzer-Freigabe begonnen.

Test-Runner verbatim: `.venv/Scripts/python.exe -m pytest`.
Ausgangsstand: 101 Tests grün.

---

## Datei-Struktur

```
src/pa_analyzer/gcode_generator.py  # ändern: analyze_gcode-Trailer   [Task 1]
klipper/pa_calibrate.cfg            # NEU: Klipper-Macros             [Task 2]
install.sh                          # NEU: Einrichtungs-Skript        [Task 3]
README.md                           # NEU: Projekt-Doku               [Task 4]
tests/test_gcode_generator.py       # ergänzen                        [Task 1]
tests/test_klipper_macro.py         # NEU                             [Task 2]
tests/test_install_script.py        # NEU                             [Task 3]
```

---

## Task 1: A1 — Generator-Trailer

`generate()` hängt nach `end_gcode` die Analyse-Trigger-Zeile an. Die
letzte Zeile der gedruckten Datei stößt nach Druckende die Auswertung an.

**Files:**
- Modify: `src/pa_analyzer/gcode_generator.py`
- Test: `tests/test_gcode_generator.py` (ergänzen)

- [ ] **Schritt 1: Tests ans Ende von `tests/test_gcode_generator.py` anhängen**

```python
def test_generate_haengt_analyze_trigger_an():
    # Die letzte Zeile stößt nach Druckende die Auswertung an, direkt
    # nach dem end_gcode (PRINT_END).
    zeilen = generate(GeneratorParams()).strip().splitlines()
    assert zeilen[-1] == "RUN_SHELL_COMMAND CMD=pa_analyze"
    assert zeilen[-2] == "PRINT_END"


def test_generate_leeres_analyze_gcode_kein_trigger():
    # Leeres analyze_gcode -> kein Trigger (Generator bleibt für
    # Nicht-Klipper-Nutzung verwendbar).
    g = generate(GeneratorParams(analyze_gcode=""))
    assert "RUN_SHELL_COMMAND" not in g
    assert g.strip().splitlines()[-1] == "PRINT_END"
```

- [ ] **Schritt 2: Tests ausführen — RED**

Run: `.venv/Scripts/python.exe -m pytest tests/test_gcode_generator.py -k analyze -v`
Erwartet: FAIL — `analyze_gcode` ist kein `GeneratorParams`-Feld
(`TypeError`), und der Trigger fehlt im Output.

- [ ] **Schritt 3: `GeneratorParams` um `analyze_gcode` erweitern**

In `src/pa_analyzer/gcode_generator.py` die `GeneratorParams`-Dataclass
im Block `# Klipper-Hooks` ergänzen — nach `end_gcode`:

```python
    # Klipper-Hooks
    start_gcode: str = "PRINT_START"
    end_gcode: str = "PRINT_END"
    analyze_gcode: str = "RUN_SHELL_COMMAND CMD=pa_analyze"
```

- [ ] **Schritt 4: `generate()` den Trailer anhängen lassen**

In `generate()` die Zeile `out.append(p.end_gcode)` (kurz vor
`return "\n".join(out) + "\n"`) ersetzen durch:

```python
    out.append(p.end_gcode)
    # Letzte Zeile der gedruckten Datei: stößt nach Druckende die
    # Auswertung an (Spec §4 Phase 3). Leeres analyze_gcode -> kein Trailer.
    if p.analyze_gcode:
        out.append(p.analyze_gcode)
```

- [ ] **Schritt 5: Tests ausführen — GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/test_gcode_generator.py -v`
Erwartet: PASS — die 2 neuen Tests grün, alle bisherigen
Generator-Tests weiterhin grün.

- [ ] **Schritt 6: Gesamtsuite — keine Regression**

Run: `.venv/Scripts/python.exe -m pytest -q`
Erwartet: PASS (103 Tests: 101 bisher + 2 neu). Der Round-Trip-Test
bleibt grün — der Parser ignoriert die `RUN_SHELL_COMMAND`-Zeile (kein
G1/PA-Befehl).

- [ ] **Schritt 7: Commit**

```bash
git add src/pa_analyzer/gcode_generator.py tests/test_gcode_generator.py
git commit -m "gcode_generator: Analyse-Trigger als letzte Zeile anhaengen"
```

---

## Task 2: A2 — Klipper-Macros

Legt die Klipper-Anbindung als committete Repo-Datei an: ein
`[include]`-fähiges Config-Fragment mit den zwei `gcode_shell_command`-
Einträgen und dem `PA_CALIBRATE`-Macro.

**Files:**
- Create: `klipper/pa_calibrate.cfg`
- Test: `tests/test_klipper_macro.py`

- [ ] **Schritt 1: Test schreiben** — `tests/test_klipper_macro.py`

```python
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
```

- [ ] **Schritt 2: Test ausführen — RED**

Run: `.venv/Scripts/python.exe -m pytest tests/test_klipper_macro.py -v`
Erwartet: FAIL (`assert ... is_file()` — Datei fehlt).

- [ ] **Schritt 3: `klipper/pa_calibrate.cfg` anlegen**

Den Ordner `klipper/` anlegen und die Datei mit exakt diesem Inhalt
erstellen:

```ini
# PA-Analyzer — Klipper-Anbindung
# =====================================================================
# In die printer.cfg aufnehmen:   [include pa_calibrate.cfg]
#
# Voraussetzungen:
#   - gcode_shell_command (Klipper-Erweiterung) ist installiert
#   - PA-Analyzer ist per install.sh eingerichtet
#
# ANPASSEN: Die drei command:-Pfade unten gehen vom Standard-
# Installationsort /home/pi/pa-pattern-webcam-analyzer aus (so legt
# install.sh das Projekt ab). Wer woanders installiert, passt die Pfade
# an. pa_analyzer.json muss webcam_url sowie gcode_path (= der von
# SDCARD_PRINT_FILE genutzte Pfad) enthalten — siehe README.
# =====================================================================

[gcode_shell_command pa_generate]
command: /home/pi/pa-pattern-webcam-analyzer/.venv/bin/pa-analyzer --config /home/pi/pa-pattern-webcam-analyzer/pa_analyzer.json generate
timeout: 60.0
verbose: True

[gcode_shell_command pa_analyze]
command: /home/pi/pa-pattern-webcam-analyzer/.venv/bin/pa-analyzer --config /home/pi/pa-pattern-webcam-analyzer/pa_analyzer.json run
timeout: 120.0
verbose: True

[gcode_macro PA_CALIBRATE]
description: Druckt ein PA-Kalibrierungspattern und wertet es per Webcam aus
gcode:
    {% set pa_start = params.PA_START|default(0.0)|float %}
    {% set pa_end   = params.PA_END|default(0.08)|float %}
    {% set pa_step  = params.PA_STEP|default(0.005)|float %}
    RUN_SHELL_COMMAND CMD=pa_generate PARAMS="--pa-start {pa_start} --pa-end {pa_end} --pa-step {pa_step}"
    SDCARD_PRINT_FILE FILENAME=pa_calibration.gcode
```

> **Hinweis:** Die exakten Pfade, Timeouts und das Zusammenspiel mit
> `PRINT_END` werden in Teil B (V1/V2) am echten Drucker verifiziert.
> Diese Datei ist der drucker-unabhängige, konventionsbasierte Entwurf.

- [ ] **Schritt 4: Test ausführen — GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/test_klipper_macro.py -v`
Erwartet: PASS (2 Tests).

- [ ] **Schritt 5: Commit**

```bash
git add klipper/pa_calibrate.cfg tests/test_klipper_macro.py
git commit -m "klipper: PA_CALIBRATE-Macro und gcode_shell_command-Anbindung"
```

---

## Task 3: A3 — install.sh

Legt das Einrichtungsskript für den Raspberry Pi an: prüft Python,
richtet die virtuelle Umgebung ein, installiert das Paket, prüft
`gcode_shell_command`.

**Files:**
- Create: `install.sh`
- Test: `tests/test_install_script.py`

- [ ] **Schritt 1: Test schreiben** — `tests/test_install_script.py`

```python
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
```

- [ ] **Schritt 2: Test ausführen — RED**

Run: `.venv/Scripts/python.exe -m pytest tests/test_install_script.py -v`
Erwartet: FAIL (`assert ... is_file()` — Datei fehlt).

- [ ] **Schritt 3: `install.sh` im Repo-Root anlegen**

Datei mit exakt diesem Inhalt erstellen:

```bash
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
```

- [ ] **Schritt 4: Test ausführen — GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/test_install_script.py -v`
Erwartet: PASS (2 Tests).

- [ ] **Schritt 5: Commit**

```bash
git add install.sh tests/test_install_script.py
git commit -m "install: Einrichtungsskript fuer den Pi (Python-Pruefung, venv, Paket)"
```

---

## Task 4: A4 — README.md

Projekt-Dokumentation im Repo-Root. Reine Doku — kein automatisierter
Test (Korrektheit ist Ermessenssache, wird im Review geprüft).

**Files:**
- Create: `README.md`

- [ ] **Schritt 1: `README.md` im Repo-Root anlegen**

Datei mit exakt diesem Inhalt erstellen:

````markdown
# PA-Pattern-Webcam-Analyzer

Automatische Pressure-Advance-Kalibrierung für Klipper-3D-Drucker.

Das Werkzeug erzeugt ein Chevron-PA-Kalibrierungspattern als GCode,
druckt es über ein Klipper-Macro, fotografiert das Ergebnis per
Drucker-Webcam und ermittelt quantitativ den optimalen
Pressure-Advance-Wert. Der Wert wird **nur ausgegeben** — das Eintragen
in den Slicer bleibt dem Nutzer überlassen.

## Funktionsweise

1. **Erzeugen** — ein parametrischer Generator schreibt den
   Pattern-GCode (keine Slicer-Abhängigkeit).
2. **Drucken** — das Klipper-Macro `PA_CALIBRATE` startet den Druck.
3. **Auswerten** — nach Druckende holt der Analyzer einen Webcam-
   Snapshot, entzerrt die Pattern-Region perspektivisch und misst pro
   PA-Wert den Filament-Flächenanteil am Chevron-Apex.
4. **Ergebnis** — optimaler PA-Wert (interpoliert + nächster gedruckter
   Schritt) samt **Konfidenz**.

## Voraussetzungen

- Python ≥ 3.13
- Ein Klipper-Drucker mit Webcam und der Erweiterung
  `gcode_shell_command`
- Abhängigkeiten (von `install.sh` installiert): `opencv-python-headless`,
  `numpy`, `pillow-heif`

## Installation (Raspberry Pi / Klipper-Host)

```bash
git clone https://github.com/Eifel-Joe/pa-pattern-webcam-analyzer.git
cd pa-pattern-webcam-analyzer
./install.sh
```

`install.sh` prüft Python, legt eine virtuelle Umgebung an und
installiert das Paket.

## Konfiguration

Eine Datei `pa_analyzer.json` im Projektverzeichnis anlegen:

```json
{
  "webcam_url": "http://DRUCKER-IP/webcam/?action=snapshot",
  "gcode_path": "/home/pi/printer_data/gcodes/pa_calibration.gcode",
  "report_path": "/home/pi/printer_data/pa_report.json"
}
```

## Klipper-Einbindung

`klipper/pa_calibrate.cfg` in die `printer.cfg` aufnehmen:

```
[include pa_calibrate.cfg]
```

Danach in der Klipper-Konsole:

```
PA_CALIBRATE PA_START=0.0 PA_END=0.08 PA_STEP=0.005
```

## Nutzung der CLI (eigenständig)

```bash
# Pattern-GCode erzeugen
pa-analyzer generate -o pattern.gcode --pa-start 0.0 --pa-end 0.05 --pa-step 0.005

# Eine lokale Bilddatei auswerten
pa-analyzer analyze foto.jpg pattern.gcode --json report.json

# Webcam-Snapshot holen und auswerten
pa-analyzer run
```

## Genauigkeit

Die Messgenauigkeit ist **auflösungsgebunden**. Hochauflösende Fotos
treffen den optimalen PA-Wert auf ±1 Schritt; typische Webcam-Snapshots
sind gröber. Das Werkzeug gibt deshalb **immer eine Konfidenz** mit aus
und behauptet keine Scheingenauigkeit. Für ein genaueres Ergebnis
unterstützt es einen zweistufigen Workflow (`generate --refine-from`):
ein zweiter, feiner gestaffelter Lauf um den groben Wert herum.

## Entwicklung

```bash
python -m pytest
```

Alle Tests laufen ohne Drucker.

## Lizenz

Siehe Repository.
````

- [ ] **Schritt 2: Gesamtsuite ausführen — keine Regression**

Run: `.venv/Scripts/python.exe -m pytest -q`
Erwartet: PASS (107 Tests: 103 nach Task 1 + 2 aus Task 2 + 2 aus Task 3;
README fügt keine Tests hinzu).

- [ ] **Schritt 3: Commit**

```bash
git add README.md
git commit -m "docs: README mit Beschreibung, Installation und Nutzung"
```

---

## Abschluss Teil A

Nach Task 4 ist das Repo veröffentlichungsreif (Teil A):
- Generator stößt die Auswertung selbsttätig an.
- Klipper-Anbindung als committete `klipper/pa_calibrate.cfg`.
- `install.sh` richtet das Projekt auf dem Pi ein.
- `README.md` deckt Beschreibung, Installation und Nutzung ab.
- Gesamte Suite grün auf Windows ohne Drucker.

**Danach — Teil B, NUR nach ausdrücklicher Nutzer-Freigabe:**
V1–V5-Verifikation am Drucker, Deployment, Live-Druck-Test (A6),
Kalibrierungs-Fallbacks. Vor diesen Schritten wird angehalten.
