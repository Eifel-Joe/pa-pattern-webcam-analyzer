# Vision-Spike Etappe 2 — Erkenntnis-Bericht

- **Datum:** 2026-05-22
- **Zweck:** Empirische Validierung der Bildverarbeitungs-Pipeline an den
  echten Fixtures, bevor der TDD-Plan für Etappe 2 geschrieben wird.
- **Status:** Abgeschlossen — Pipeline validiert.

> Der Spike-Code lag unter `spike/` (Wegwerf-Code, gitignored). Dieses
> Dokument hält die übertragbaren Erkenntnisse fest und ist die Grundlage
> des Etappe-2-Plans.

---

## 1. Kern-Ergebnis

Die Pipeline funktioniert. Alle drei Fixtures liefern einen PA-Wert im
Zielband 0.026–0.030 (Referenz-Wahrheit 0.028):

| Fixture | PA (Parabel-Fit) | diskret | belastbar? |
|---|---|---|---|
| Handy-Foto (`IMG_3843.HEIC`) | 0.0291 | 0.030 | **ja** (Std ~0.0023 bei Ecken-Störung) |
| Webcam `pa_snap.jpg` | 0.0260 | 0.024 | nein (Std ~0.0137 ≈ 7 PA-Schritte) |
| Webcam `pa_snap2.jpg` | 0.0289 | 0.028 | nein (auflösungslimitiert) |

**Nur das Handy-Foto-Ergebnis ist belastbar.** Die Webcam-Snapshots
(~270 px Pattern-Breite) sind zu grob für ±1-Schritt-Genauigkeit — das
bestätigt die README-Lesson (Vorversuch kam auf 0.034). Die
Pipeline-Logik ist korrekt; das Webcam-Material ist der Engpass.

## 2. Validierte Pipeline

### 2.1 Lokalisierung

HSV-Konvertierung → Filament-Maske: dominanter Hue aus den gesättigten
Pixeln (Otsu-Schwelle auf dem Sättigungskanal), zirkuläre Hue-Distanz
< 18 → größte zusammenhängende Komponente → Löcher schließen.

**Schlüssel-Lektion:** Die 4 Eckpunkte über `cv2.minAreaRect` bestimmen,
**nicht** über `convexHull` + `approxPolyDP`. Die Chevron-Einkerbungen in
der Box-Kante verleiten die Hull-Approximation zu falschen Extrempunkten
→ verscherte Homographie. `minAreaRect` liefert ein echtes rotiertes
Rechteck und ist robust gegen die Einkerbungen.

Parameter: `sat_thr = max(60, Otsu(S))`; Hue-Toleranz 18;
Close-Kernel `bildbreite // 120 | 1`.

### 2.2 Orientierungs-Disambiguierung

Das Pattern ist nahezu punktsymmetrisch — die 4 möglichen Rotationen des
`minAreaRect` lassen sich **nicht** über Chevron-Energie trennen.

**Lösung — Balken-Dichte-Check:** Der Beschriftungs-Balken ist
Vollfüllung (~92 % Maskenanteil), die Chevron-Zone ist gestreift
(~60 %). Verhältnis Balken-Band / Chevron-Band: korrekte Rotation
1.55–1.88, alle falschen ≤ 0.91 — eindeutige, deterministische Trennung
auf allen drei Fixtures.

### 2.3 Entzerrung (Homographie)

`cv2.getPerspectiveTransform` (4 Box-Ecken → normierter Bett-Raum) +
`cv2.warpPerspective`. Bewährte Auflösung: **24 px/mm**. Die projizierten
GCode-Chevrons lagen nach dem `minAreaRect`-Ansatz praktisch
deckungsgleich auf den gedruckten Linien (Restdrift ~1–2 px in einer
Ecke — für die Messung unkritisch).

### 2.4 Messung — Zwei-Box-Flächenmethode

Die naheliegende „Linienbreite quer zum Arm" **scheiterte**: Bei 24 px/mm
liegen die 3 Perimeter-Linien einer Gruppe nur ~13.7 px auseinander; der
Breiten-Lauf greift Nachbarlinien → verrauscht und instabil.

**Was funktioniert — Filament-Flächenanteil in chevron-lokalen Boxen:**

- `fill_in`: kleine Box (halbe Kante 0.6 mm) zentriert auf dem
  Soll-Apex. Fällt ab, wenn bei zu hohem PA eine **Lücke** entsteht.
- `fill_out`: dieselbe Box 0.75 mm nach außen versetzt. Hoch bei zu
  niedrigem PA (**Wulst** quillt über die Spitze).
- `score = (1 − fill_in) + fill_out` — bestraft Lücke und Wulst;
  Minimum = optimaler PA.
- Pro PA-Gruppe Median über die 3 Chevrons; Score 3-fach geglättet;
  Parabel-Fit ±3 Punkte um das diskrete Minimum für den interpolierten
  Wert.

Box-Achsen = Apex-Winkelhalbierende + Tangente (rotationsfest), Abtastung
per `cv2.remap` mit rotiertem Raster.

**Bekannte Schwäche:** `fill_in` sättigt bei niedrigem PA (~0.95 für alle
kleinen Werte) → die untere Score-Flanke ist flach. Die
Über-PA-Erkennung (Lücke) ist schärfer als die Unter-PA-Erkennung
(Wulst). Verbesserungsidee für später: `fill_out` stärker gewichten oder
eine dritte Box weiter außen.

## 3. Empfohlene Modul-Aufteilung für Etappe 2

| Modul | Aufgabe |
|---|---|
| `image_loader` | HEIC/JPG laden, EXIF-Transpose (pillow-heif) |
| `pattern_locator` | Filament-Maske + größte Komponente + `minAreaRect` → 4 Ecken |
| `orientation` | Rotation über Balken/Chevron-Dichte-Verhältnis bestimmen |
| `rectifier` | `getPerspectiveTransform` + `warpPerspective`, 24 px/mm |
| `apex_analyzer` | Zwei-Box `fill_in`/`fill_out` je PA-Gruppe |
| `pa_estimator` | Score-Kurve, Glättung, Minimum, Parabel-Fit |
| `gcode_parser` | bereits fertig (Etappe 1) — liefert die Soll-Geometrie |

Bibliotheken: **nur OpenCV + numpy** (kein scikit-image/scipy nötig),
plus `pillow-heif` für HEIC.

## 4. Konsequenzen für die TDD-Strategie

**Feste Erwartungswerte möglich:**
- Homographie/Entzerrung: gegen ein synthetisch gerendertes Test-Pattern
  mit exakt bekannten Ecken (Re-Projektionsfehler ≈ 0 prüfbar).
- Orientierungs-Erkennung: harte Erwartung der korrekten Rotation auf
  allen Fixtures (Dichte-Margin 1.5 vs. 0.9 ist groß genug).
- Flächen-Messung (`box_fill`): exakte Anteile auf konstruierten Masken.

**Toleranz-Bänder nötig:**
- End-to-End-PA Handy-Foto: `abs(pa − 0.028) <= 0.004` (Band, kein
  Punkt-Wert).
- Webcam-Snapshots: nur „Pipeline läuft ohne Crash, Ergebnis im weiten
  Plausibilitätsbereich 0.01–0.05" — **keine** engen PA-Erwartungen.

## 5. Harte Grenze: Auflösung

Die Genauigkeit ist auflösungsgebunden. Webcam-Snapshots (~270 px
Pattern-Breite) erlauben nur ±3–4 PA-Schritte; jeder Pixel
Ecken-Fehler wirkt ~4× stärker als beim Handy-Foto. Für ±1-Schritt
braucht es Handy-Foto-Auflösung (Pattern > ~1500 px breit).

Eine bessere Webcam-Positionierung (Pattern formatfüllend, frontaler)
bringt mehr als jede Algorithmus-Verbesserung. Dies ist in der
Etappe-2-Doku und in der Konfidenz-Ausgabe des Tools ehrlich
abzubilden.
