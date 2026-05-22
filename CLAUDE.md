# CLAUDE.md — PA-Pattern-Webcam-Analyzer

## Projekt-Kontext

Werkzeug zur automatischen Pressure-Advance-Kalibrierung eines Klipper-3D-
Druckers. Es generiert ein Chevron-PA-Kalibrier-Pattern als GCode, druckt es
über ein Klipper-Macro, fotografiert das Ergebnis per Drucker-Webcam und
ermittelt quantitativ den optimalen PA-Wert. Python 3.13 + OpenCV.
Entwicklung auf Windows, Betrieb auf dem Raspberry Pi (Klipper-Host).

Vollständige Spezifikation:
`docs/specs/2026-05-22-pa-pattern-webcam-analyzer.md`.

## Sprache

Alle Antworten und Dokumente auf **Deutsch**.

## Befehls-Palette

Konkrete Verbindungs-Details (IP, User, Passwort, Pfade) stehen in
`MEMORY.md` (projekt-lokal, **nicht** im Repo). `<IP>` / `<PW>` unten sind
Platzhalter dafür.

Remote-Befehl auf dem Pi (Windows, Bash-Tool, **niemals** PowerShell):

    "C:\Program Files\PuTTY\plink.exe" -pw "<PW>" -batch pi@<IP> "<cmd>"

Webcam-Snapshot:

    http://<IP>/webcam/?action=snapshot

Datei vom Pi holen (base64-Transfer, pscp ist unzuverlässig):

    plink ... "base64 /pfad/datei" > local.b64
    base64 -d local.b64 > local.datei

Tests:

    python -m pytest -q

Deployment auf den Pi (Repo ist öffentlich → per git):

    # auf dem Pi:
    git clone <repo-url>   # bzw. git pull

## Projekt-Regeln

- **PA-Parameter immer aus dem GCode parsen, niemals hardcoden** — Anzahl
  Chevrons, PA-Bereich, Schrittweite. Siehe Spec §9.
- **Öffentliches Repo:** keinerlei Secrets committen. `.gitignore` schließt
  `reference/`, `MEMORY.md` und `.claude/` aus.
- Specs → `docs/specs/`, Pläne → `docs/plans/` (Format `YYYY-MM-DD-<name>.md`).
- TDD verbindlich: kein Produktionscode ohne vorher fehlschlagenden Test.
- Reine Logik-Module (`gcode_generator`, `gcode_parser`) ohne externe
  Abhängigkeiten halten — trivial unit-testbar.

## Verbindungs-Details

→ `MEMORY.md` (projekt-lokal, nicht im Repo).

---

Die globalen Iron Laws aus `~/.claude/CLAUDE.md` (Regeln 0–8) gelten
zusätzlich automatisch.
