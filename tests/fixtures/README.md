# Referenz-Material — PA-Pattern-Webcam-Analyzer

Test- und Referenzdaten aus dem Schwesterprojekt (LLL-Python), erzeugt
2026-05-22. Dient als Eingabe-Beispiel und Test-Fixture fuer das neue
Projekt.

## Dateien

| Datei | Inhalt |
|---|---|
| `pa_pattern.gcode` | OrcaSlicer 2.3.2 PA-Pattern-GCode (Chevron-Variante), wie auf dem Drucker gedruckt. Enthaelt Geometrie + `SET_PRESSURE_ADVANCE`-Befehle. |
| `pa_snap.jpg` | Webcam-Snapshot (1280x960), Drucker-Monitoring-Cam, schraeger Winkel. |
| `pa_snap2.jpg` | Zweiter Webcam-Snapshot, gleiches Setup. |
| `IMG_3843.HEIC` | Hochaufloesendes Handy-Nahfoto des fertigen Patterns (senkrecht, formatfuellend). Beste Referenz fuer die Auswertung — hartes Korrektheits-Gate der Tests. |

Diese Dateien wurden aus dem Briefing-Ordner `reference/` in die
Test-Fixtures uebernommen. `reference/` selbst ist nicht Teil des Repos.

## Pattern-Parameter — IMMER aus dem GCode lesen, NIEMALS hardcoden

**WICHTIG:** Anzahl Chevrons, PA-Wertebereich und Schrittweite sind
NICHT fix. Sie haengen von den Test-Parametern ab (Start-PA, End-PA,
Schritt) und aendern sich von Druck zu Druck. Das Tool MUSS diese
Werte bei jedem Lauf dynamisch aus dem zugehoerigen GCode parsen:

- `SET_PRESSURE_ADVANCE ADVANCE=<wert>` steht jeweils direkt vor dem
  Zeichnen jeder Chevron-Gruppe. Die Liste dieser Befehle liefert
  Anzahl + exakte PA-Werte + Reihenfolge.
- Die erste Bewegung nach jedem `SET_PRESSURE_ADVANCE` liefert die
  X-Position der Gruppe -> Mapping Bildposition -> PA-Wert.
- Rahmen-Kasten-Koordinaten (fuer die Homographie) ebenfalls aus dem
  GCode ableiten, nicht annehmen.

Hardcoden von "21" oder "0.010-0.050" = Bug. Immer parsen.

### Werte DIESES Sample-GCodes (nur als Beispiel/Test-Fixture)

- 21 PA-Werte: 0.010 bis 0.050, Schritt 0.002. PA steigt links->rechts.
- Layout entlang X: PA 0.010 bei X~124.5mm, PA 0.050 bei X~196.6mm,
  ~3.6mm Abstand pro Gruppe. Alle bei Y~142mm.
- 4 Layer, 0.80mm Hoehe. Testbedingungen lt. Dateiname: 180mm/s @ 3000mm/s2.

## Manuell ermitteltes Ergebnis (Referenz-Wahrheit fuer Tests)

Bei diesem Druck wurde der optimale PA-Wert **~0.028** ermittelt —
sowohl per menschlichem Augenmass als auch per Bildanalyse des
Nahfotos. Der Tool-Output sollte fuer dieses Sample ebenfalls ~0.028
(+/- 1 Chevron = 0.026-0.030) liefern.

## Lessons aus den Vorversuchen

- Webcam-Snapshot (schraeg, Pattern nur ~270px breit): Erstanalyse kam
  auf 0.034 — ~3 Chevrons zu hoch. Die Ueber-PA-Raufranzung rechts war
  bei der niedrigen Aufloesung nicht erkennbar.
- Nahfoto: klare Lesung 0.028. Die rechte Pattern-Haelfte zeigt
  deutliche Ausfransung (Ueber-PA), linke Haelfte glatt.
- Fazit: Perspektivkorrektur (Homographie ueber den Rahmen-Kasten)
  loest den Winkel; die Aufloesung bleibt der harte Engpass.
