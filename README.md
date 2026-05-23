# PA-Pattern-Webcam-Analyzer

> [!WARNING]
> **Experimentell — frühe Entwicklungsphase.** Dieses Werkzeug steht
> ganz am Anfang seiner Entwicklung. Die Bildverarbeitungs-Pipeline
> wurde an Beispielfotos validiert, **aber der Live-Test am echten
> Drucker steht noch aus** — die Klipper-Anbindung
> (`klipper/pa_calibrate.cfg`) ist konventionsbasiert entworfen und in
> der Praxis nicht verifiziert.
>
> Vor dem ersten Aufruf von `PA_CALIBRATE` unbedingt:
> - Den Macro-Inhalt lesen und Pfade an die eigene Installation
>   anpassen.
> - Während des ersten Drucks bereit sein, den Drucker per Not-Aus
>   anzuhalten.
> - Die Konfidenz-Angabe des Analyzers ernst nehmen — niedrige
>   Konfidenz heißt: dem Ergebnis nicht trauen.
>
> Nutzung auf eigene Gefahr.

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

**Einstellungsvoraussetzung:** Die Vorlage `pa_analyzer.example.conf`
nach `pa_analyzer.conf` kopieren und an die eigene Klipper-Installation
anpassen. Ohne diese Datei (genauer: ohne `start_gcode` darin) bricht
`pa-analyzer generate` mit einer klaren Meldung ab — PRINT_START-
Aufrufe sind nicht genormt, und der Generator muss exakt deinen Aufruf
in den GCode einbauen.

```bash
cp pa_analyzer.example.conf pa_analyzer.conf
$EDITOR pa_analyzer.conf
```

Aufbau (INI-Format):

```ini
[webcam]
url = http://DRUCKER-IP/webcam/?action=snapshot

[paths]
gcode_path = /home/pi/printer_data/gcodes/pa_calibration.gcode
report_path = /home/pi/printer_data/pa_report.json

[macros]
# Multi-line: Folgezeilen einrücken. {temp}/{bed_temp} substituiert
# der Generator mit den Werten aus PA_CALIBRATE TEMP=.../BED_TEMP=...
start_gcode =
    PRINT_START EXTRUDER={temp} BED={bed_temp}
end_gcode =
    PRINT_END
```

Häufige PRINT_START-Signaturen als Anhaltspunkt:

| PRINT_START-Variante | start_gcode-Eintrag |
|---|---|
| Klipper-Standard | `PRINT_START EXTRUDER={temp} BED={bed_temp}` |
| Klippain / mancher Kiauh-Setup | `PRINT_START HOTEND={temp} BED_TEMP={bed_temp}` |
| Mit Material-Hinweis | `PRINT_START EXTRUDER={temp} BED={bed_temp} MATERIAL=PLA` |
| Kurzform | `PRINT_START T={temp} B={bed_temp}` |

Platzhalter `{temp}` und `{bed_temp}` werden eingesetzt; andere
`{Platzhalter}` bleiben unverändert. Optional steht `analyze_gcode`
unter `[macros]` zur Verfügung (Default `RUN_SHELL_COMMAND CMD=pa_analyze`).

**Wenn dein `PRINT_START` weitere Parameter erwartet** (z.B. `MATERIAL`,
`PRINT_AREA_START`/`_END`, `SOAKTIME`, …), trage sie im `start_gcode`
direkt mit konkreten Werten ein. Das Tool reicht nur die für die
PA-Kalibrierung relevanten Werte (Hotend-/Bett-Temperatur,
Extrusionsfaktor, Lüfter) durch — alles übrige Drucker-Setup ist Sache
der Konfiguration:

```ini
start_gcode =
    PRINT_START EXTRUDER_TEMP={temp} BED_TEMP={bed_temp} MATERIAL=0 PRINT_AREA_START=25,25 PRINT_AREA_END=275,275
```

## Klipper-Einbindung

`klipper/pa_calibrate.cfg` in die `printer.cfg` aufnehmen:

```
[include pa_calibrate.cfg]
```

Danach in der Klipper-Konsole — `TEMP` (Hotend), `BED_TEMP` (Bett),
`FLOW` (Extrusionsfaktor) und `FAN` (Lüfter ab Layer 2, 0..1) an das
gedruckte Filament anpassen (werden in den GCode eingebacken):

```
# PLA-typisch:
PA_CALIBRATE PA_START=0.0 PA_END=0.08 PA_STEP=0.005 TEMP=215 BED_TEMP=60 FLOW=1.0 FAN=1.0

# PETG/ABS-typisch (Lüfter aus oder niedrig):
PA_CALIBRATE PA_START=0.0 PA_END=0.08 PA_STEP=0.005 TEMP=240 BED_TEMP=80 FLOW=1.0 FAN=0.3
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

Dieses Projekt steht unter der MIT-Lizenz — siehe [LICENSE](LICENSE).

## Danksagung

Der Pattern-Generator dieses Werkzeugs leitet seine Geometrie- und
Flow-Mathematik aus Andrew Ellis' offen verfügbarem
[Pressure_Linear_Advance_Tool](https://github.com/AndrewEllis93/Pressure_Linear_Advance_Tool)
ab — Teil seines umfassenden
[Print Tuning Guide](https://ellis3dp.com/Print-Tuning-Guide/). Vielen
Dank für die ausgezeichnete Vorarbeit.
