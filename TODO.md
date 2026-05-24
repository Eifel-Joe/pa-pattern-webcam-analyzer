# TODO

Offene Punkte und Erweiterungs-Ideen für den PA-Pattern-Webcam-Analyzer.
Geordnet nach Bereich + grobe Priorität. Jeweils mit Begründung und
Hinweis auf den Zeitpunkt der Umsetzung.

> Status-Kürzel: **[demnächst]** = nach dem ersten Live-Test sinnvoll,
> **[mittel]** = Komfort/Aufräumarbeit, **[später]** = nice-to-have oder
> Fallback, der erst bei konkretem Bedarf gebaut wird (YAGNI),
> **[erledigt]** = abgeschlossen (Commit-SHA als Beleg dazu).
>
> **Pflege:** Living Document — neue Punkte werden hier ergänzt, sobald
> sie aufkommen; abgearbeitete bleiben mit `[erledigt]`-Marker stehen
> (nicht entfernen), idealerweise mit Commit-SHA. So bildet die Datei
> nebenbei ein Mini-Changelog der nicht-feature-zentralen Arbeit.

---

## Generator

### [erledigt] Druck-Geschwindigkeit und Beschleunigung als Parameter

Behoben in Commit `4829bf1` (CLI), `ce3b0d3` (Macro), `1ac781c` (Config)
auf Branch `feature/pattern-markierungen-speed-accel` (24.05.2026).
Speed (`--speed` / `SPEED=`) und Accel (`--accel` / `ACCEL=`) sind
jetzt CLI-, Macro- und Config-Parameter. Accel wird als
`SET_VELOCITY_LIMIT ACCEL=<n> ACCEL_TO_DECEL=<n/2>` vor dem Pattern
emittiert. Beide Werte werden zusätzlich als hochkant rotierte Labels
auf der Top-Bar mitgedruckt (Reproduzierbarkeit). Defaults konservativ:
100 mm/s und 2000 mm/s². Override-Hierarchie:
CLI > Macro > `[generator]`-Sektion in `pa_analyzer.conf` > Code-Default.

### [mittel] Rahmen berührt Chevrons (3-Linien-Frame statt geschlossenem Rechteck)

Aktuell zieht der Generator einen geschlossenen 4-seitigen Rahmen um
das Chevron-Pattern mit etwas Abstand. Resultat beim ersten Live-Test:
Rahmen und Chevrons sind beim Ablösen vom Bett **getrennte
Einzelteile** — fummelig zu entfernen.

**Vorschlag:** Rahmen als 3-Linien-"["-Form (oder "U") drucken, sodass
die Chevron-Arm-Enden den Rahmen **berühren**. Der ganze Druck wird
damit ein zusammenhängendes Teil und lässt sich in einem Stück
abnehmen.

**Umsetzung:** In `gcode_generator.py` die `_frame_block()`-Geometrie
auf 3 Seiten + passende Chevron-Position-Berechnung anpassen, damit
die Spitzen genau am Rahmen ansetzen. Tests für Rahmen-Form + Kontakt-
Punkt-Koordinaten ergänzen.

Vom User am 2026-05-24 nach dem ersten Live-Test gewünscht ("Lässt
sich dann besser vom Druckbett entfernen").

### [mittel] Generator-Defaults aus der `pa_analyzer.conf` ziehen

Aktuell sind `speed_*`, `retract_distance`, `purge_length`, `bed_x/y`
etc. nur GeneratorParams-Defaults. Wer nicht-Standard fährt, müsste sie
bei jedem `PA_CALIBRATE`-Aufruf mitgeben — was das Macro nicht macht.

**Umsetzung:** Neue `[generator]`-Sektion in `pa_analyzer.conf` mit
beliebigen GeneratorParams-Feldern. CLI-Argumente überschreiben Config,
Config überschreibt GeneratorParams-Defaults. Synergie mit dem
Speed/Accel-TODO oben.

**Update 24.05.2026 (Commit `1ac781c`):** Die `[generator]`-Sektion
existiert jetzt als Extension-Point, mit `speed_print` und `accel`
als ersten freigegebenen Feldern. Weitere `GeneratorParams`-Felder
können nach demselben Schema (`_get_float`-Helper in `load_config`)
nachgezogen werden, wenn Bedarf entsteht.

---

## CLI / Auswertung

### [demnächst] Fortschrittsanzeige in der Analyse

Während `pa-analyzer run` / `analyze` läuft (~5–15 s auf dem Pi), gibt
das Tool keine Statusausgabe — der User sieht in der Klipper-Konsole
nichts bis zum fertigen Ergebnis. Wirkt wie Hänger.

**Umsetzung:** Je Pipeline-Stufe (`filament_mask` → `locate_quad` →
`pick_orientation` → `rectify` → `measure_groups` → `estimate_pa`) ein
`print()`-Statuszeile mit fortlaufender Prozentzahl
(z.B. `[3/6] Orientierung bestimmen ...`). Output geht via
`gcode_shell_command verbose: True` automatisch an die Klipper-Konsole.

Vom User am 2026-05-24 explizit gewünscht ("Können wir nach dem ersten
Test machen").

### [mittel] Effektive Webcam-Auflösung beim ersten Snapshot loggen

V3-Check ist nicht eindeutig — die Moonraker-API gibt nur den Endpoint
zurück, nicht die Pixel-Auflösung. Bei `pa-analyzer run` ist die Info
nach `fetch_snapshot` als `img.shape` verfügbar. Kurz mitausgeben
(passt gut zur Fortschrittsanzeige-Stufe 1) — damit ist V3 erledigt.

---

## Hardware-Etappe (drucker-gebunden, Teil B)

### [später] Kalibrierungs-Fallbacks (Haupt-Spec §10.1)

Wenn die automatische Lokalisierung am realen Webcam-Bild versagt
(Rahmen-Box nicht erkannt), Fallback-Kette:
1. Gespeicherte Homographie aus der Config.
2. Manuelle 4-Ecken-Eingabe.

**YAGNI bis erwiesen nötig** — der Vision-Spike hat die Auto-Erkennung
auf allen drei Beispielfotos validiert. Erst bauen wenn Live-Tests
zeigen, dass die Auto-Lokalisierung in der Praxis versagt.

### [später] Zweistufiger Mess-Workflow im Klipper-Macro

`refine_bounds()` als Funktion ist da, CLI-Integration via
`generate --refine-from report.json` auch — aber das Klipper-Macro
orchestriert noch keinen automatischen 2. Lauf.

**Vorschlag:** Neues `PA_CALIBRATE_REFINE`-Macro, das nach dem ersten
Lauf das verfeinerte Pattern erzeugt und druckt. Oder optionaler
`REFINE=1`-Param an `PA_CALIBRATE`.

Spec-Verweis: Vision-Spike §6.

### [später] Optional ermittelten PA-Wert direkt setzen

Aktuell: Tool gibt PA-Wert nur aus, User trägt selbst in den Slicer
oder die `printer.cfg` ein (Haupt-Spec §2 Nicht-Ziel). Optionaler
Komfort: `APPLY=1`-Param, der nach Ermittlung
`SET_PRESSURE_ADVANCE ADVANCE=<best_pa>` direkt absetzt. Default
bleibt "ausgeben".

---

## Bugs / Aufräumarbeit

### [erledigt] install.sh: SAVE_CONFIG-Marker-Detection beim `[include]`-Anhängen

Behoben in Commit `a73b3c4` (24.05.2026). Ursprünglicher Bug: Append
ans Datei-Ende landete nach Klippers SAVE_CONFIG-Block, was den
Autosave-Merge brach (`[heater_bed]` verlor `control = pid`).

### [erledigt] install.sh: find-Pipefail bei gcode_shell_command-Detection

Behoben in Commit `a73b3c4`. Direkter `[ -f ... ]`-Pfad-Check statt
`find ... | grep -q .` (das brach bei Permission-Denied auf
`~/.cache/...` durch `pipefail`).
