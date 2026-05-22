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

- Python ≥ 3.11 (Raspberry Pi OS Bookworm bringt 3.11 mit; auf Bullseye
  muss eine neuere Python-Version installiert werden, z.B. via pyenv)
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

# Zweiter, feinerer Lauf um den groben Wert herum
pa-analyzer generate -o pattern2.gcode --refine-from report.json
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
