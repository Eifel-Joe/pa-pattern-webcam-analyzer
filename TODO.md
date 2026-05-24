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

### [demnächst] Druck-Geschwindigkeit und Beschleunigung als Parameter

Aktuell hardcoded in `GeneratorParams`:
- `speed_print = 60 mm/s` (`F3600`)
- `speed_travel = 120 mm/s` (`F7200`)
- `speed_purge = 25 mm/s` (`F1500`)
- **Beschleunigung wird gar nicht emittiert** — der Drucker nutzt
  `printer.cfg`-Default oder was `PRINT_START` setzt.

Problem: Pressure-Advance reagiert primär auf Beschleunigungs-Änderungen.
Der bei 60 mm/s ermittelte Wert ist nicht 1:1 auf reale Drucke bei z.B.
200 mm/s übertragbar. OrcaSlicer-PA-Tool und Andrew Ellis' Tool erlauben
beides pro Lauf zu setzen.

**Umsetzung:**
- `--speed` / `SPEED=` im Macro (Druck-Geschwindigkeit, Default 60).
- Optional `--accel` / `ACCEL=` — emittiert `M204 S<accel>` oder
  `SET_VELOCITY_LIMIT ACCEL=<n>` im Header.
- Defaults überschreibbar via `[generator]`-Sektion in `pa_analyzer.conf`
  (siehe nächster Punkt).

### [mittel] Generator-Defaults aus der `pa_analyzer.conf` ziehen

Aktuell sind `speed_*`, `retract_distance`, `purge_length`, `bed_x/y`
etc. nur GeneratorParams-Defaults. Wer nicht-Standard fährt, müsste sie
bei jedem `PA_CALIBRATE`-Aufruf mitgeben — was das Macro nicht macht.

**Umsetzung:** Neue `[generator]`-Sektion in `pa_analyzer.conf` mit
beliebigen GeneratorParams-Feldern. CLI-Argumente überschreiben Config,
Config überschreibt GeneratorParams-Defaults. Synergie mit dem
Speed/Accel-TODO oben.

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
