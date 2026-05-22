# Spec: PA-Pattern-Webcam-Analyzer

- **Datum:** 2026-05-22
- **Status:** Entwurf zur Freigabe
- **Autor:** Brainstorming-Session (Claude + Nutzer)

---

## 1. Problem

Die Kalibrierung des Pressure-Advance-Werts (PA) eines Klipper-3D-Druckers
erfolgt heute manuell: Man druckt ein PA-Kalibrier-Pattern (genestete
Chevron-Linien, jede mit anderem PA-Wert), begutachtet die Apex-Ecken per
Augenmaß und liest den optimalen Wert ab. Das ist subjektiv, fehleranfällig
und nicht reproduzierbar.

Ziel ist ein Werkzeug, das diesen Vorgang **deterministisch automatisiert**:
Pattern erzeugen, drucken, per Drucker-Webcam fotografieren, quantitativ
auswerten und den optimalen PA-Wert ausgeben.

## 2. Ziele und Nicht-Ziele

### Ziele

- Parametrische Erzeugung eines Chevron-PA-Pattern-GCodes (portierbar auf
  beliebige Druckergrößen).
- Drucken des Patterns über ein Klipper-Macro.
- Automatische Auswertung eines Webcam-Fotos nach Druckende.
- Ausgabe des optimalen PA-Werts samt Konfidenz.
- Voll test-getriebene Entwicklung (TDD) auf Windows; Betrieb auf dem Pi.

### Nicht-Ziele

- **Kein** automatisches Setzen des PA-Werts im Drucker oder Slicer — das
  Tool gibt den Wert nur aus, der Nutzer trägt ihn selbst ein.
- **Kein** Dauerdienst/Daemon — die Auswertung läuft als One-Shot, getriggert
  vom Druck-Ende.
- **Kein** OrcaSlicer-CLI-Aufruf zur Laufzeit.
- **Keine** GUI — Konsolen-/Datei-Ausgabe genügt.

## 3. Anforderungen

### Funktional

- **F1** — Generator erzeugt aus Parametern einen gültigen, druckbaren
  Chevron-PA-Pattern-GCode.
- **F2** — Parser liest aus *beliebigem* PA-Pattern-GCode (generiert oder
  extern, z.B. OrcaSlicer) Anzahl, Werte, Reihenfolge der PA-Werte sowie die
  Geometrie (Apex-Positionen, Chevron-Arme, Rahmen-Box). PA-Parameter werden
  **niemals** hartcodiert.
- **F3** — Webcam-Snapshot wird per HTTP geholt; alternativ wird eine lokale
  Bilddatei geladen (für Tests und manuelle Auswertung).
- **F4** — Perspektivkorrektur: Abbildung GCode-Koordinaten ↔ Bild-Pixel über
  eine Homographie.
- **F5** — Quantitative Auswertung: pro PA-Wert ein Linienbreiten-Metrik-Score;
  bester PA = minimale Apex-Breiten-Abweichung.
- **F6** — Ausgabe: optimaler PA-Wert (interpoliert + nächster gedruckter
  Schritt) + Konfidenz, nach `M118` in die Klipper-Konsole und in eine
  JSON-Report-Datei.
- **F7** — Klipper-Macro `PA_CALIBRATE` als Einstiegspunkt, Parameter werden
  durchgereicht.

### Nicht-funktional

- **N1** — Sprache Python 3.13; Bildverarbeitung mit OpenCV
  (`opencv-python-headless`).
- **N2** — Entwicklung und alle Tests laufen auf Windows ohne Drucker.
- **N3** — Betrieb auf dem Raspberry Pi (Klipper-Host).
- **N4** — Reine Logik-Module (`gcode_generator`, `gcode_parser`) ohne
  externe Abhängigkeiten, damit trivial unit-testbar.
- **N5** — Robuste Fehlerbehandlung: ein Generierungsfehler darf **nie** zu
  einem Fehldruck führen.

## 4. Architektur-Überblick

Der Ablauf zerfällt in **drei kurze, klar getrennte Phasen**. Zwischen den
Phasen blockiert nichts langfristig.

```
Nutzer am Drucker:
  PA_CALIBRATE TEMP=240 FLOW=1.0 PA_START=0.0 PA_END=0.05 PA_STEP=0.0025

Phase 1 — Generierung (Drucker idle, Sekunden, blockierend)
  PA_CALIBRATE-Macro
    -> RUN_SHELL_COMMAND CMD=pa_generate ...      (gcode_shell_command, synchron)
       -> Python: gcode_generator schreibt pa_calibration.gcode (atomar)
    -> SDCARD_PRINT_FILE FILENAME=pa_calibration.gcode

Phase 2 — Druck (virtual_sdcard, Minuten, nichts blockiert)
  ... Chevron-Pattern wird gedruckt ...
  ... am Dateiende: PRINT_END  (parkt Kopf aus dem Kamerabereich) ...

Phase 3 — Auswertung (Drucker idle, Sekunden, blockierend)
  letzte Zeile der generierten Datei:
    -> RUN_SHELL_COMMAND CMD=pa_analyze ...        (gcode_shell_command, synchron)
       -> Python: Snapshot holen -> parsen -> lokalisieren -> messen
       -> Ergebnis: M118 in Konsole + JSON-Report-Datei
```

**Race-Sicherheit:** `gcode_shell_command` ist synchron/blockierend. Das
Macro fährt erst mit `SDCARD_PRINT_FILE` fort, wenn der Generator-Prozess
beendet ist (Datei vollständig geschrieben und geschlossen). Es gibt daher
keine Race zwischen Generierung und Druckstart.

## 5. Architektur-Entscheidungen (geklärte Optionen)

| # | Frage | Entscheidung | Verworfen / Begründung |
|---|---|---|---|
| 1 | GCode-Quelle | Parametrischer Python-Generator | Festes Template (nicht portierbar); Jinja-Macro-Generator (kaum TDD-bar). Python: portierbar, voll testbar. |
| 2 | Temp/Flow | Direkt in den GCode einbacken | Flow-1.0-Indirektion unnötig, da ohnehin jeder Lauf neu generiert. Macro-Parameter = Generator-Parameter. |
| 3 | Einstiegspunkt / Brücke | Klipper-Macro + Python auf dem Pi, Brücke via `gcode_shell_command` | Reine Python-CLI (kein Drucker-Einstieg gewünscht); `klippy/extras`-Modul (OpenCV würde den Echtzeit-klippy-Prozess blockieren → MCU-Timeouts, `klippy-env`-Verschmutzung). |
| 4 | Perspektiv-Kalibrierung | Hybrid: Auto-Erkennung der Rahmen-Box (farbunabhängig) → gespeicherte Kalibrierung → manuelle 4 Ecken | Reine Auto-Erkennung (scheitert bei schlechtem Snapshot); reine gespeicherte Kalibrierung (bricht bei Kamerabewegung). |
| 5 | Bildquelle | Webcam-only produktiv; intern bilddatei-fähig (Tests, manuelle Auswertung) | — |
| 6 | Ergebnis | Nur ausgeben (`M118` + JSON-Report) | Auto-Setzen im Drucker/Slicer (nicht gewünscht). |
| 7 | Laufmodus | One-Shot, getriggert vom Druck-Ende | Dauerdienst/Daemon (nicht gewünscht). |

## 6. Komponenten

Python-Paket `pa_analyzer`. Jedes Modul hat eine klar umrissene Aufgabe und
ist isoliert testbar.

| Modul | Aufgabe | Schnittstelle (grob) | Abhängigkeiten |
|---|---|---|---|
| `gcode_generator` | Parameter → Pattern-GCode | `generate(params: GeneratorParams) -> str` | keine |
| `gcode_parser` | GCode → `PatternModel` | `parse(gcode_text: str) -> PatternModel` | keine |
| `webcam` | Snapshot holen / Bild laden | `fetch_snapshot(url) -> ndarray`, `load_image(path) -> ndarray` | requests, opencv, pillow-heif |
| `localizer` | Bild + Modell → Homographie | `localize(image, model, calibration?, color_hint?) -> LocalizationResult` | opencv, numpy |
| `analyzer` | entzerrtes Bild + Modell → Ergebnis | `analyze(image, model, homography) -> AnalysisResult` | opencv, numpy |
| `report` | Ergebnis formatieren/schreiben | `format(result) -> str`, `write_json(result, path)` | keine |
| `cli` | Subkommandos `generate`/`analyze`/`run` | argparse-Einstieg | die obigen |
| `config` | Drucker-Host, Webcam-URL, Kalibrierungsdaten | Laden/Speichern (TOML/JSON) | keine |

`gcode_generator` und `analyzer` sind **vollständig entkoppelt**: Der Analyzer
parst stets den tatsächlich gedruckten GCode, funktioniert also auch mit
extern erzeugten Patterns.

## 7. Datenmodell

`PatternModel` (Ergebnis des Parsers, Eingabe für Localizer/Analyzer):

- `frame_box`: 4 Eckkoordinaten der Rahmen-Box in Bett-mm.
- `groups`: geordnete Liste von `PaGroup`, sortiert nach PA-Wert.
  - `PaGroup.pa_value: float`
  - `PaGroup.apex: (x, y)` in Bett-mm
  - `PaGroup.chevrons`: Liste von Chevron-Geometrien (Arm-Endpunkte je
    Chevron — typischerweise 3 pro Gruppe)
- `meta`: aus dem GCode ableitbare Kennwerte (Linienbreite, Schichthöhe,
  Schichtanzahl), soweit vorhanden.

## 8. Generator — Detail

Algorithmus abgeleitet aus Ellis' Open-Source-Tool
([AndrewEllis93/Pressure_Linear_Advance_Tool](https://github.com/AndrewEllis93/Pressure_Linear_Advance_Tool),
JavaScript, Prusa-/Orca-Flow-Mathematik) und dem konkreten
Beispiel-GCode `tests/fixtures/pa_pattern.gcode` als ausgearbeitetem Beispiel.

**Parameter (`GeneratorParams`):** Bett-Ursprung + Größe, `pa_start`,
`pa_end`, `pa_step`, Linienbreite, Schichthöhe, Schichtanzahl,
Druckgeschwindigkeit, Beschleunigung, `temp`, `extrusion_multiplier`
(Default 1.0), Filamentdurchmesser.

> **Benennung:** `extrusion_multiplier` entspricht dem Macro-Parameter
> `FLOW` und dem "Flow Ratio" (OrcaSlicer) bzw. "Extrusion Multiplier"
> (PrusaSlicer) — durchgängig dasselbe Konzept, ein Faktor um 1.0.

**Ausgabe-Struktur:** Start-Sequenz (Homing, Heizen — mit eingebackener
`temp`), Priming-Linie, Rahmen-Box, Chevron-Gruppen (jede Gruppe direkt mit
vorangehendem `SET_PRESSURE_ADVANCE ADVANCE=<wert>`), `PRINT_END`-Aufruf,
abschließend `RUN_SHELL_COMMAND CMD=pa_analyze ...`.

**Schreibweise:** atomar — erst in temporäre Datei schreiben, am Schluss
umbenennen. Frischer Dateiname pro Lauf bzw. alte Datei zuvor löschen, damit
nie ein veraltetes Pattern gedruckt werden kann.

## 9. Parser — Detail

Der Parser ist die "niemals hardcoden"-Instanz. Anforderungen, die sich aus
`reference/pa_pattern.gcode` ergeben:

- **Setup-/Prime-Befehle ignorieren:** Vor dem eigentlichen Pattern stehen
  `SET_PRESSURE_ADVANCE`-Befehle (im Sample Zeilen 89, 108), die zur
  Drucker-Vorbereitung gehören. Echte Pattern-Gruppen werden daran erkannt,
  dass ihnen eine Chevron-Bewegung folgt (zwei diagonale Segmente mit
  gemeinsamem Apex) bzw. dass sie innerhalb der Rahmen-Box liegen.
- **Layer-Deduplizierung:** Das Pattern hat mehrere Layer (im Sample 4); die
  Sequenz der 21 PA-Werte wiederholt sich pro Layer. Der Parser sammelt die
  *eindeutigen* PA-Werte und ihre (über alle Layer konsistente) Apex-X-Position.
- **Apex-Bestimmung:** Die erste Bewegung nach `SET_PRESSURE_ADVANCE` führt
  zum Apex; das ist der rechte Scheitelpunkt des `>`-Chevrons.
- **Rahmen-Box:** Eckkoordinaten der gedruckten Box aus den entsprechenden
  Bewegungen ableiten.

**Verifikations-Fixture:** `tests/fixtures/pa_pattern.gcode` → 21 PA-Werte
0.010–0.050, Schritt 0.002, Apex-X ≈ 124.5 mm (PA 0.010) bis ≈ 196.6 mm
(PA 0.050).

## 10. Analyse-Pipeline — Detail

### 10.1 Lokalisierung (Hybrid)

1. **Primär — Auto-Erkennung der Rahmen-Box, farbunabhängig.** Die
   Filamentfarbe wechselt je Druck, daher keine feste Farbschwelle. Die
   Rahmen-Box wird als gesättigte, gleichmäßige zusammenhängende Region
   segmentiert, die sich vom texturierten Bett abhebt. Aus den 4 Ecken wird
   die Homographie zu den GCode-Rahmen-Koordinaten berechnet. Optionaler
   `--color`-Hinweis zur Disambiguierung.
2. **Fallback — gespeicherte Kalibrierung.** Einmal ermittelte Homographie
   aus der Konfigurationsdatei.
3. **Letzter Ausweg — manuelle 4 Ecken.** Vom Nutzer angegeben.

Ergebnis: `LocalizationResult` mit Homographie-Matrix und Konfidenzwert.

### 10.2 Messung

- Pro PA-Gruppe: Extrusions-Linienbreite senkrecht zur Chevron-Arm-Richtung
  abtasten — auf dem geraden Armabschnitt (Referenzbreite) und durch den
  Apex.
- Zu niedriger PA → Materialwulst am Apex (lokal breiter).
- Zu hoher PA → Lücke/Unterextrusion am Apex (lokal schmaler/unterbrochen).
- Score pro Gruppe = Betrag der Breiten-Abweichung am Apex gegenüber der
  Referenzbreite. Mittelung über die (typ. 3) Chevrons je Gruppe gegen
  Rauschen.
- Subpixel-fähige Breitenschätzung (Intensitäts-Integral/Schwerpunkt), da
  die Auflösung der Engpass ist.

### 10.3 Auswahl

- Bester PA = Gruppe mit minimalem Score.
- Score-Kurve über alle PA-Werte fitten (V-/Parabel-Form) → interpoliertes
  Optimum zwischen den gedruckten Schritten; zusätzlich den nächsten
  gedruckten Schritt ausgeben.
- **Konfidenz** aus: effektiver Auflösung, Qualität des Kurven-Fits,
  Monotonie/Eindeutigkeit der Score-Kurve.

### 10.4 Ehrlichkeit zur Genauigkeit

Laut den Vorversuchs-Notizen (`tests/fixtures/README.md`) lieferte die Webcam in Vorversuchen 0.034 statt
der wahren 0.028 (3 Schritte zu hoch) — die Auflösung ist die harte
Obergrenze. Das Tool gibt **immer** eine Konfidenz mit aus und behauptet
keine Scheingenauigkeit.

## 11. Klipper-Anbindung

Im Drucker-Config (mit dem `klipper-config`-Skill erstellt):

- `[gcode_shell_command pa_generate]` — ruft den Python-Generator.
- `[gcode_shell_command pa_analyze]` — ruft den Python-Analyzer.
- `[gcode_macro PA_CALIBRATE]` — Einstiegspunkt; reicht Parameter (`TEMP`,
  `FLOW`, `PA_START`, `PA_END`, `PA_STEP`, …) an `pa_generate` weiter und
  startet anschließend den Druck.

Das vorhandene `PRINT_END`-Macro wird wiederverwendet (parkt den Kopf aus
dem Kamerabereich); der Analyse-Trigger steht als letzte Zeile *nach*
`PRINT_END` im generierten GCode.

## 12. Fehlerbehandlung

| Fall | Verhalten |
|---|---|
| Generierung schlägt fehl | Macro startet **keinen** Druck; klare Fehlermeldung. (Signalisierungs-Mechanismus bei Implementierung verifizieren — siehe §15.) |
| Rahmen-Box nicht erkannt | Fallback-Kette: gespeicherte Kalibrierung → manuelle Ecken → Abbruch mit klarer Meldung. |
| Webcam nicht erreichbar | Klare Fehlermeldung; kein Crash, kein Pseudo-Ergebnis. |
| Score-Kurve uneindeutig/nicht monoton | Ergebnis mit **niedriger Konfidenz** ausgeben, Uneindeutigkeit explizit benennen. |
| HEIC-Bild, `pillow-heif` fehlt | Klare Meldung mit Installationshinweis. |
| GCode ohne erkennbare Pattern-Gruppen | Abbruch mit klarer Meldung. |

## 13. Test-Strategie (TDD)

Alle Tests laufen auf Windows ohne Drucker. Die Fixtures liegen in
`tests/fixtures/` — aus dem nicht im Repo enthaltenen Briefing-Ordner
`reference/` übernommen.

| Komponente | Test | Erwartung |
|---|---|---|
| `gcode_generator` | Eigenschaftstests | gültiger GCode; PA monoton; Round-Trip durch eigenen Parser konsistent |
| `gcode_parser` | gegen `pa_pattern.gcode` | exakt 21 PA-Werte, 0.010–0.050, Schritt 0.002; Apex-X ≈ 124.5–196.6 mm; Setup-Befehle ignoriert; Layer dedupliziert |
| `localizer` | gegen `pa_snap.jpg`, `pa_snap2.jpg` | Rahmen-Box erkannt; Homographie bildet auf plausibles Rechteck ab |
| `analyzer` | **Gate** gegen `IMG_3843.HEIC` (Handy-Foto) | Ergebnis im Band 0.026–0.030 (Ziel 0.028) |
| `analyzer` | gegen `pa_snap.jpg`, `pa_snap2.jpg` | läuft durch, plausibler Wert; Genauigkeit ehrlich dokumentiert |
| Integration | `generate → parse` | Round-Trip-Konsistenz |

**Wichtige Unterscheidung:** Das Handy-Foto-Gate (±1 Schritt) ist der harte
Korrektheits-Beweis des Algorithmus bei ausreichender Auflösung. Die
Webcam-Genauigkeit ist auflösungsbegrenzt — Ziel ist eine *Verbesserung*
gegenüber den 0.034 der Vorversuche, keine garantierte ±1-Schritt-Genauigkeit.

## 14. Akzeptanzkriterien

- **A1** — `gcode_parser` liefert für `tests/fixtures/pa_pattern.gcode` exakt
  21 PA-Werte 0.010–0.050 (Schritt 0.002) mit korrekten Apex-Positionen.
- **A2** — `gcode_generator` erzeugt GCode, der vom eigenen Parser
  verlustfrei zurückgelesen werden kann (Round-Trip).
- **A3** — `analyzer` liefert für `tests/fixtures/IMG_3843.HEIC` einen
  PA-Wert im Band 0.026–0.030.
- **A4** — `analyzer` läuft für `tests/fixtures/pa_snap.jpg`/`pa_snap2.jpg`
  fehlerfrei durch und liefert einen plausiblen Wert mit Konfidenz.
- **A5** — Die gesamte Test-Suite ist auf Windows ohne Drucker grün.
- **A6** — `PA_CALIBRATE` druckt am echten Drucker ein Pattern und gibt nach
  Druckende einen PA-Wert in der Klipper-Konsole aus (Live-Test).

## 15. Annahmen und zu verifizieren

Folgende Punkte werden **zu Beginn der Implementierung am echten Drucker
verifiziert** — nicht geraten:

- **V1** — `gcode_shell_command` ist in `klippy/extras/` installiert; wie es
  einen Fehler-Exit-Code signalisiert (bestimmt die Fehler-Absicherung in
  §12).
- **V2** — Was `PRINT_END` genau tut: Parkposition relativ zum Kamerabild,
  ob/wie weit das Bett in Z abgesenkt wird, ob Heizungen abgeschaltet werden
  (beeinflusst Snapshot-Sichtbarkeit und -Zeitpunkt).
- **V3** — Maximale Webcam-Auflösung (`/server/webcams/list`) — ob höher als
  die 1280×960 der Beispiel-Snapshots möglich ist.
- **V4** — Python 3.13 + `opencv-python-headless` auf dem Pi
  verfügbar/installierbar.
- **V5** — Geometrie-Konventionen des realen Patterns (Reihenfolge der
  Chevron-Segmente, Anzahl Chevrons pro Gruppe) gegen den generierten GCode
  abgleichen.

## 16. Projekt-Setup und Deployment

- Python-3.13-Paket mit `pyproject.toml`, Test-Runner `pytest`.
- **Öffentliches GitHub-Repository** — daher dürfen keinerlei Secrets
  committed werden.
- **`.gitignore`** schließt aus: den kompletten Briefing-Ordner `reference/`
  (enthält u.a. `drucker-zugang.txt` mit Klartext-Passwort), die
  projekt-lokale `MEMORY.md` (enthält die Drucker-Zugangsdaten) sowie
  Python-Standard-Artefakte.
- Die für die Tests benötigten Fixtures werden aus `reference/` nach
  `tests/fixtures/` kopiert und committed (siehe §13).
- Projekt-lokale `CLAUDE.md` (Kontext, Befehls-Palette, Projekt-Regeln) —
  **ohne Secrets**, wird committed. Verbindungs-Details verweisen auf die
  `MEMORY.md`.
- Projekt-lokale `MEMORY.md` (Drucker-IP, User, Passwort, Pfade) — **nicht**
  committed, steht in `.gitignore`.
- Deployment auf den Pi per `plink`/Base64-Transfer (Befehls-Palette).

## 17. Offene Punkte für die Plan-Phase

- Konkrete Aufschlüsselung der TDD-Tasks (RED/GREEN je Modul).
- Reihenfolge: zuerst reine Logik-Module (`gcode_parser`, `gcode_generator`),
  dann Bildverarbeitung, zuletzt Drucker-Integration.
