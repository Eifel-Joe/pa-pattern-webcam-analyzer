# Spec: PA-Analyzer Etappe 4 — Hardware-Integration & Veröffentlichungs-Reife

- **Datum:** 2026-05-23
- **Status:** Entwurf
- **Bezug:** Haupt-Spec `docs/specs/2026-05-22-pa-pattern-webcam-analyzer.md`
  (§4 Architektur, §11 Klipper-Anbindung, §15 zu-verifizieren, §16
  Deployment) und Etappe-3-Spec `docs/specs/2026-05-22-etappe3-integration.md`.

---

## 1. Ziel

Etappe 1–3 lieferten ein voll getestetes CLI-Tool. Etappe 4 verbindet es
mit dem echten Drucker (Klipper-Macros, Live-Test) und macht das Repo
**veröffentlichungsreif**: vollständig, von Dritten installierbar.

## 2. Zweiteilung des Umfangs

Etappe 4 zerfällt in zwei klar getrennte Teile mit unterschiedlichem
Freigabe-Modus:

### Teil A — drucker-unabhängig (wird ohne Drucker umgesetzt und getestet)

- **A1** Generator-Trailer: `generate()` hängt die Analyse-Trigger-Zeile an.
- **A2** Klipper-Macros als committete Repo-Dateien (`klipper/pa_calibrate.cfg`).
- **A3** `install.sh` im Repo-Root — Abhängigkeits-Prüfung und Einrichtung.
- **A4** `README.md` — Projektbeschreibung, Installation, Nutzung.

Teil A ist auf Windows ohne Drucker abschließbar (A1 voll TDD-getestet;
A2–A4 sind Config/Skript/Doku und werden per Review abgenommen).

### Teil B — drucker-gebunden (NUR nach ausdrücklicher Nutzer-Freigabe)

- **B1** Verifikation V1–V5 der Haupt-Spec §15 am laufenden Drucker.
- **B2** Deployment auf den Raspberry Pi (`git clone`, `install.sh`).
- **B3** Live-Druck-Test — Akzeptanzkriterium A6.
- **B4** Kalibrierungs-Fallbacks (Haupt-Spec §10.1) — nur falls die
  automatische Lokalisierung am realen Webcam-Bild versagt.

> **Freigabe-Gate:** Teil B berührt physische Drucke. Er wird **erst nach
> ausdrücklicher Freigabe durch den Nutzer** begonnen. Teil A wird vorab
> vollständig umgesetzt; dieser Spec-Teil dokumentiert Teil B als
> Prozedur, nicht als sofort auszuführende Aufgabe.

## 3. Teil A — Detail

### 3.1 A1: Generator-Trailer

Die generierte GCode-Datei wird per `SDCARD_PRINT_FILE` gedruckt; ihre
**letzte Zeile** stößt nach Druckende die Auswertung an (Haupt-Spec §4,
Phase 3).

- `GeneratorParams` bekommt ein neues Feld
  `analyze_gcode: str = "RUN_SHELL_COMMAND CMD=pa_analyze"`.
- `generate()` hängt diese Zeile **nach** `end_gcode` an. Ist
  `analyze_gcode` leer, wird nichts angehängt (Generator bleibt für
  Nicht-Klipper-Nutzung verwendbar).
- Konsistent mit den vorhandenen Feldern `start_gcode`/`end_gcode`.

`RUN_SHELL_COMMAND` ist das vom `gcode_shell_command`-Modul
bereitgestellte Kommando; `pa_analyze` ist der in A2 definierte Macro-Name.

### 3.2 A2: Klipper-Macros

Datei `klipper/pa_calibrate.cfg` — vom Nutzer per `[include]` in die
`printer.cfg` eingebunden:

- `[gcode_shell_command pa_generate]` — ruft `pa-analyzer generate`.
- `[gcode_shell_command pa_analyze]` — ruft `pa-analyzer run`.
- `[gcode_macro PA_CALIBRATE]` — Einstiegspunkt; nimmt `PA_START`,
  `PA_END`, `PA_STEP` (mit Defaults), reicht sie an `pa_generate` weiter
  und startet anschließend `SDCARD_PRINT_FILE`.

Die Datei ist ein **Template** mit einem dokumentierten Installations-
Pfad (Default `/home/pi/pa-pattern-webcam-analyzer`). Pfad- und
Timeout-Feinheiten, die von V1/V2/V4 abhängen, sind im Datei-Kopf als
anzupassende Stellen markiert und werden in Teil B verifiziert.

### 3.3 A3: install.sh

Bash-Skript im Repo-Root, ausgeführt auf dem Pi. Prüft und richtet ein:

1. Python ≥ 3.13 vorhanden — sonst klarer Abbruch.
2. Virtuelle Umgebung `.venv` anlegen, Projekt installieren
   (`pip install .` zieht `opencv-python-headless`, `numpy`,
   `pillow-heif`).
3. Prüfen, ob `gcode_shell_command` in Klipper verfügbar ist — sonst
   klarer Hinweis (kein harter Abbruch, da nachinstallierbar).
4. Abschluss-Hinweis: welche `.cfg` in die `printer.cfg` aufzunehmen ist
   und dass `pa_analyzer.json` zu konfigurieren ist.

Das Skript ist **idempotent** (mehrfach ausführbar) und bricht bei einem
fehlenden Muss-Kriterium mit Exit-Code ≠ 0 und klarer Meldung ab.

### 3.4 A4: README.md

Im Repo-Root. Inhalt: Kurzbeschreibung (Was/Warum), Voraussetzungen,
Installation (`install.sh`), Nutzung der CLI (`generate`/`analyze`/`run`),
Klipper-Einbindung (`PA_CALIBRATE`), Hinweis auf die
Auflösungs-Ehrlichkeit (Konfidenz), Lizenz-/Repo-Hinweis. Keine Secrets.

## 4. Teil B — Prozedur (drucker-gebunden, nutzer-freigegeben)

### 4.1 B1: Verifikation V1–V5 (Haupt-Spec §15)

Am laufenden Drucker, **lesend** (keine Drucke): `gcode_shell_command`
installiert + Fehler-Signalisierung (V1); `PRINT_END`-Verhalten (V2);
maximale Webcam-Auflösung (V3); Python/OpenCV auf dem Pi (V4);
Pattern-Geometrie-Abgleich (V5). Ergebnisse fließen in die finale
Macro-/`install.sh`-Feinabstimmung.

### 4.2 B2: Deployment

`git clone`/`git pull` auf dem Pi, `install.sh` ausführen,
`pa_analyzer.json` konfigurieren, `pa_calibrate.cfg` einbinden.

### 4.3 B3: Live-Druck-Test (A6)

`PA_CALIBRATE` aufrufen → Pattern wird gedruckt → nach Druckende liefert
der Analyzer einen PA-Wert. Vorgehen nach REGEL 2 Phase 5 (Live-Test mit
Nutzer-Bestätigung) und REGEL 6 (Diagnose-Build bei unklarer Wurzel).

### 4.4 B4: Kalibrierungs-Fallbacks

Nur falls B3 zeigt, dass die automatische Lokalisierung am realen
Webcam-Bild versagt: gespeicherte Homographie + manuelle Ecken-Eingabe
(Haupt-Spec §10.1). Bekommt bei Bedarf einen eigenen Plan.

## 5. Akzeptanzkriterien

- **E4-A1** — `generate()` hängt die `analyze_gcode`-Zeile nach
  `end_gcode` an; leeres `analyze_gcode` → keine Zeile. TDD-getestet.
- **E4-A2** — `klipper/pa_calibrate.cfg` ist im Repo, syntaktisch
  plausibel, enthält die drei benötigten Sektionen.
- **E4-A3** — `install.sh` liegt im Repo-Root, ist idempotent und bricht
  bei fehlendem Python ≥ 3.13 klar ab.
- **E4-A4** — `README.md` deckt Beschreibung, Installation und Nutzung ab.
- **E4-A5** — gesamte Test-Suite grün auf Windows ohne Drucker.
- **E4-A6** (Teil B, nutzer-freigegeben) — `PA_CALIBRATE` druckt am echten
  Drucker ein Pattern und gibt nach Druckende einen PA-Wert aus.

## 6. Offene Punkte für die Plan-Phase

- TDD-Task für A1; Umsetzungs-Tasks für A2–A4 mit Review.
- Teil B bekommt **keinen** TDD-Plan — er ist eine hardware-gebundene
  Prozedur und wird erst nach Nutzer-Freigabe begonnen.
