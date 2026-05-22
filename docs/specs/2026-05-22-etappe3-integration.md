# Spec: PA-Analyzer Etappe 3 — Software-Integration

- **Datum:** 2026-05-22
- **Status:** Entwurf zur Freigabe
- **Bezug:** Unter-Spec zur Haupt-Spec `docs/specs/2026-05-22-pa-pattern-webcam-analyzer.md`
  (insbesondere §4 Architektur, §6 Komponenten, §10–§12).

---

## 1. Ziel und Umfang

Etappe 1 lieferte Generator und Parser, Etappe 2 die Bild→PA-Pipeline
(`analyze()`). Etappe 3 fügt die **Integrations-Schicht** hinzu, die daraus
ein nutzbares Kommandozeilen-Werkzeug macht: Konfiguration, Webcam-Snapshot,
Report-Ausgabe, eine CLI mit Subkommandos und den zweistufigen Mess-Workflow
als testbare Funktion.

Alles in Etappe 3 ist **auf Windows ohne Drucker testbar** (Haupt-Spec A5).

### Nicht-Umfang (bewusst auf Etappe 4 — Hardware — verschoben)

- **Klipper-Macros** (`gcode_shell_command pa_generate`/`pa_analyze`,
  `PA_CALIBRATE`). Begründung: Sie brauchen die Live-Verifikation V1/V2 der
  Haupt-Spec §15 (wie `gcode_shell_command` einen Fehler signalisiert, was
  `PRINT_END` genau tut) am echten Drucker.
- **Kalibrierungs-Fallbacks** (gespeicherte Homographie, manuelle
  Ecken-Eingabe; Haupt-Spec §10.1 Fallback 2/3). Begründung: Die automatische
  Lokalisierung wurde im Vision-Spike auf allen Fixtures validiert. Die
  Fallbacks sind Robustheits-Reserve — sinnvoll erst, wenn sich am realen
  Drucker zeigt, dass die Auto-Erkennung versagt (YAGNI). Sie hängen ohnehin
  an der Hardware-Etappe.

Damit gilt: **Etappe 3 = lauffähiges, voll getestetes CLI-Tool**;
**Etappe 4 = Drucker-Anbindung + Live-Test (A6) + ggf. Fallbacks.** Das
entspricht der Reihenfolge der Haupt-Spec §17 ("zuletzt Drucker-Integration").

## 2. Komponenten

| Modul | Datei | Aufgabe | Schnittstelle |
|---|---|---|---|
| `config` | `config.py` | Konfiguration laden | `load_config(path) -> Config` |
| `webcam` | `webcam.py` | HTTP-Snapshot holen | `fetch_snapshot(url) -> ndarray` |
| `report` | `report.py` | Ergebnis formatieren/schreiben | `format_result(result) -> str`, `write_json(result, path)` |
| `two_stage` | `two_stage.py` | Lauf-2-Grenzen ableiten | `refine_bounds(result) -> (start, end, step)` |
| `cli` | `cli.py` | Subkommandos `generate`/`analyze`/`run` | `main(argv=None) -> int` |
| `analyzer` | `analyzer.py` (erweitern) | ndarray-Einstiegspunkt | neu: `analyze_image(image, gcode_text)` |
| `gcode_parser` | `gcode_parser.py` (erweitern) | G91/M82-Robustheit | `_tokenize` modus-bewusst |

`config`, `report`, `two_stage` sind reine Logik-Module ohne externe
Abhängigkeiten (Haupt-Spec N4). `webcam` nutzt nur die Standardbibliothek
plus die schon vorhandenen `cv2`/`numpy`.

## 3. Design-Entscheidungen

### 3.1 Konfigurations-Format: JSON

| Option | Bewertung |
|---|---|
| **JSON (gewählt)** | `json` aus der Standardbibliothek liest und schreibt; das Tool liest die Datei selbst; winzige Datei. |
| TOML | Lesbar via `tomllib`, aber Schreiben (für später: Kalibrierungsdaten) bräuchte eine Extra-Abhängigkeit. Mischung Lesen-TOML/Schreiben-JSON wäre inkonsistent. |

**Entscheidung: JSON.** Die Haupt-Spec §6 nennt "TOML/JSON" offen; JSON ist
die abhängigkeitsärmere, in beide Richtungen stdlib-fähige Wahl.

`Config` ist eine frozen dataclass mit Default-Werten. `load_config` mischt
die Datei über die Defaults; **fehlende Datei → reine Defaults** (so läuft
`generate` ohne Konfiguration). Unbekannte Schlüssel in der Datei werden
ignoriert (vorwärtskompatibel).

### 3.2 Webcam-Abruf: stdlib `urllib`

Die Haupt-Spec §6 nannte `requests`. Ein einzelner Snapshot-GET ist mit
`urllib.request` aus der Standardbibliothek trivial. **Entscheidung:
`urllib.request`** — spart eine Abhängigkeit (Geist von N4). Die JPEG-Bytes
werden mit `cv2.imdecode` zum BGR-Array dekodiert.

### 3.3 CLI: drei Subkommandos

| Subkommando | Phase | Aufgabe |
|---|---|---|
| `generate` | 1 | `GeneratorParams` aus Argumenten → Pattern-GCode-Datei (atomar geschrieben). Optional `--refine-from REPORT.json` für Lauf 2. |
| `analyze` | — | Lokale Bilddatei + GCode-Datei → Ergebnis (offline/manuelle Auswertung, Tests). |
| `run` | 3 | Snapshot von der konfigurierten Webcam + GCode-Datei → Ergebnis + Report (produktiv). |

Einstiegspunkt `main(argv=None) -> int` (Exit-Code: 0 = Erfolg, ≠ 0 =
Fehler). `pyproject.toml` bekommt einen `[project.scripts]`-Eintrag
`pa-analyzer = "pa_analyzer.cli:main"`.

### 3.4 `analyze_image`-Einstiegspunkt

`analyzer.analyze()` lädt aktuell aus einem Datei-Pfad. Die Webcam liefert
dagegen direkt ein ndarray. `analyzer.py` wird um `analyze_image(image:
ndarray, gcode_text: str) -> AnalysisResult` ergänzt; `analyze(path,
gcode_text)` wird zum dünnen Wrapper (`analyze_image(load_image(path),
…)`). Das Etappe-2-Verhalten und alle bestehenden `test_analyzer.py`-Tests
bleiben unverändert. Die zentrale Boundary-Validierung wandert in
`analyze_image` (gilt damit für beide Einstiegspunkte).

### 3.5 Zweistufiger Workflow: `refine_bounds`

Reine Funktion `refine_bounds(result: AnalysisResult) -> tuple[float, float,
float]`, liefert `(pa_start, pa_end, pa_step)` für Lauf 2:

- **Fenster:** `best_pa ± 3 × Original-Schrittweite` — deckt die im
  Vision-Spike §6 genannte Lauf-1-Unsicherheit (±2–3 Schritte) ab.
- **Schrittweite:** halbe Original-Schrittweite — der feiner gestaffelte
  Lauf übersetzt denselben räumlichen Fehler in einen kleineren absoluten
  PA-Fehler (Vision-Spike §6).
- **Klemmung:** `pa_start` wird auf `≥ 0.0` geklemmt.

Die Original-Schrittweite wird aus `result.scores` abgeleitet (Differenz der
ersten beiden PA-Werte) — kein Hardcoding. Die tatsächliche
Zwei-Druck-Schleife ist Klipper-Seite (Etappe 4); Etappe 3 verdrahtet den
Workflow über `generate --refine-from REPORT.json`.

### 3.6 Parser-Carry-over G90/G91, M82/M83

`_tokenize` wird modus-bewusst, damit der Parser auch extern erzeugten GCode
(z.B. OrcaSlicer) korrekt liest:

- **G90/G91** — absolute bzw. relative XY-Positionierung.
- **M82/M83** — absolute bzw. relative Extrusion. Bei M82 wird `extruding`
  über das **Delta** zur vorigen E-Position bestimmt (sonst würde ein
  Retract als Extrusion fehlerkannt).
- **G92 E\<wert\>** — setzt den Extruder-Origin (häufig `G92 E0`).

**Defaults: G90 / M83** — exakt das bisherige Verhalten. Alle 76
bestehenden Tests bleiben unverändert grün; M83/G90 als bislang ignorierte
Zeilen werden nur noch explizit als Modus-Umschalter erkannt.

## 4. Fehlerbehandlung

| Fall | Verhalten |
|---|---|
| Konfigurationsdatei fehlt | Reine Default-Werte (kein Fehler). |
| `run` ohne konfigurierte `webcam_url` | Klare Fehlermeldung, Exit-Code ≠ 0. |
| Webcam nicht erreichbar | `ConnectionError` mit klarer Meldung; kein Crash. |
| Webcam-Antwort ist kein Bild | `ValueError` mit klarer Meldung. |
| GCode-Datei fehlt / Bilddatei fehlt | `FileNotFoundError` mit Pfad. |
| GCode ohne auswertbares Pattern | `ValueError` (Boundary-Validierung in `analyze_image`). |
| CLI-Fehler allgemein | Meldung auf stderr, Exit-Code ≠ 0 — kein Python-Traceback für den Endnutzer. |

## 5. Test-Strategie (TDD)

| Komponente | Test | Erwartung |
|---|---|---|
| `config` | Round-Trip + Defaults | JSON-Datei korrekt geladen; fehlende Datei → Defaults; unbekannte Schlüssel ignoriert. |
| `webcam` | lokaler `http.server` mit Fixture-JPEG | Erfolg liefert ndarray; toter Port → `ConnectionError`; Nicht-Bild → `ValueError`. |
| `report` | `format_result` + JSON | Formatierter Text enthält PA-Wert & Konfidenz; JSON ist round-trip-fähig. |
| `gcode_parser` | synthetischer G91- und M82+G92-GCode | ergibt dasselbe `PatternModel` wie die G90/M83-Variante. |
| `two_stage` | `refine_bounds` | Lauf-2-Grenzen umschließen `best_pa`, Schrittweite feiner, `start ≥ 0`. |
| `analyzer` | `analyze_image` gegen `IMG_3843.HEIC` | identisches Ergebnis wie `analyze` über den Pfad. |
| `cli` | argparse-Dispatch | `generate` schreibt Datei; `analyze` trifft das Band; `run` über lokalen HTTP-Server. |
| Integration | `generate → analyze → report → refine → generate` | durchgängig konsistent. |

Der Webcam-Test nutzt einen **echten** lokalen HTTP-Server
(`http.server.ThreadingHTTPServer` auf einem Hintergrund-Thread), der ein
Fixture-JPEG ausliefert — kein Mock. So wird der tatsächliche
HTTP-/Decode-Pfad geprüft.

## 6. Akzeptanzkriterien

- **E3-A1** — `pa-analyzer generate` schreibt gültigen GCode, den der eigene
  Parser verlustfrei zurücklesen kann.
- **E3-A2** — `pa-analyzer analyze tests/fixtures/IMG_3843.HEIC <gcode>`
  liefert einen PA-Wert im Band 0.026–0.030 (Haupt-Spec A3).
- **E3-A3** — `pa-analyzer run` holt einen Snapshot von einem (Test-)
  HTTP-Server und liefert ein `AnalysisResult`.
- **E3-A4** — `refine_bounds` liefert für ein Lauf-1-Ergebnis engere,
  `best_pa` umschließende Grenzen mit feinerer Schrittweite.
- **E3-A5** — Der Parser liest synthetischen G91- und M82-GCode korrekt
  (gleiches Modell wie die G90/M83-Variante).
- **E3-A6** — Die gesamte Test-Suite ist auf Windows ohne Drucker grün.

## 7. Offene Punkte für die Plan-Phase

- TDD-Task-Aufschlüsselung (RED/GREEN je Modul).
- Reihenfolge: erst die unabhängigen Blatt-Module (`config`, `webcam`,
  `report`, Parser-Carry-over, `analyzer`-Refactor, `two_stage`), dann die
  `cli` als Verdrahtung, zuletzt der Integrationstest.
