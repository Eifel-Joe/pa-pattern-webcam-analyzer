# Etappe 2 — Bild→PA-Pipeline — Implementierungsplan

> **Für agentische Umsetzung:** ERFORDERLICHES SUB-SKILL: `superpowers:subagent-driven-development` (empfohlen) oder `superpowers:executing-plans`, um diesen Plan Task für Task umzusetzen. Schritte nutzen Checkbox-Syntax (`- [ ]`).

**Ziel:** Ein Analyzer, der aus einer Bilddatei eines gedruckten PA-Patterns und dem zugehörigen GCode den optimalen Pressure-Advance-Wert ermittelt.

**Architektur:** Pipeline aus sechs Modulen — Bild laden → Filament-Region lokalisieren → Orientierung bestimmen → perspektivisch entzerren → pro PA-Gruppe per Zwei-Box-Flächenmethode messen → Score-Kurve zum PA-Wert auswerten. Jede Stufe ist ein eigenes Modul mit klarer Schnittstelle. Die Pipeline wurde im Vision-Spike empirisch validiert (siehe `docs/specs/2026-05-22-etappe2-vision-spike.md`) — der Plan-Code ist die bereinigte Überführung des erprobten Spike-Codes, nicht spekulativ.

**Tech Stack:** Python 3.13, OpenCV (`opencv-python-headless`), numpy, `pillow-heif` (HEIC-Dekodierung), pytest. Aufbauend auf dem Etappe-1-`gcode_parser` und `model`.

**Referenz-Fakten** (aus dem Vision-Spike):
- Warp-Auflösung 24 px/mm. Filament-Maske: HSV, dominanter Hue aus gesättigten Pixeln, zirkuläre Hue-Distanz < 18.
- 4 Eckpunkte über `cv2.minAreaRect` (nicht `convexHull`/`approxPolyDP` — das verschert).
- Orientierung über Dichte-Verhältnis Balken-Band / Chevron-Band.
- Messung: Zwei-Box-Flächenanteil (`fill_in` auf Apex, `fill_out` 0.75 mm außen), `score = (1−fill_in) + fill_out`.
- Akzeptanz: Handy-Foto (`IMG_3843.HEIC`) → PA im Band 0.026–0.030; Webcam-Snapshots → nur Plausibilität (auflösungslimitiert).

**Hinweis zum `meta`-Carry-Over:** Der Etappe-1-Review empfahl `PatternModel.meta` (Referenz-Linienbreite). Der Vision-Spike hat den Linienbreiten-Messansatz verworfen; die validierte Zwei-Box-Methode braucht die Linienbreite nicht. `meta` wird daher **nicht** umgesetzt (YAGNI). Stattdessen wird `content_bounds` ergänzt — die Bounding-Box der Druck-Geometrie, die die Homographie-Pipeline benötigt.

**Carry-Over `G91`/`M82`:** Der Parser-Robustheits-Punkt bleibt für Etappe 3 (Integration) offen — er betrifft externen GCode, nicht die Vision-Pipeline.

---

## Datei-Struktur

```
src/pa_analyzer/
├── model.py            # erweitern: content_bounds, AnalysisResult        [Task 1]
├── gcode_parser.py      # erweitern: content_bounds befüllen               [Task 1]
├── image_loader.py     # load_image() — HEIC/JPG laden                     [Task 2]
├── pattern_locator.py  # filament_mask(), locate_quad()                    [Task 3]
├── orientation.py      # pick_orientation()                                [Task 4]
├── rectifier.py        # rectify() — Homographie + Warp, px/mm-Mapping     [Task 5]
├── apex_analyzer.py    # box_fill(), measure_groups()                      [Task 6]
├── pa_estimator.py     # estimate_pa() — Score-Kurve → AnalysisResult      [Task 7]
└── analyzer.py         # analyze() — Pipeline-Integration                  [Task 8]
tests/
├── test_image_loader.py                                                   [Task 2]
├── test_pattern_locator.py                                                [Task 3]
├── test_orientation.py                                                    [Task 4]
├── test_rectifier.py                                                      [Task 5]
├── test_apex_analyzer.py                                                  [Task 6]
├── test_pa_estimator.py                                                   [Task 7]
└── test_analyzer.py                                                       [Task 8]
```

Jedes Modul hat eine Verantwortung und eine schmale Schnittstelle. `model.py` bleibt abhängigkeitsfrei. Die Vision-Module (`pattern_locator` … `pa_estimator`) hängen nur von `cv2`/`numpy` und `model` ab, nicht voneinander — `analyzer.py` verdrahtet sie.

---

## Task 1: Datenmodell & Parser-Erweiterung, Projekt-Abhängigkeiten

Ergänzt das `PatternModel` um die Bounding-Box der Druck-Geometrie (Homographie-Referenz) und führt `AnalysisResult` ein. Trägt die Bildverarbeitungs-Abhängigkeiten in `pyproject.toml` ein.

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/pa_analyzer/model.py`
- Modify: `src/pa_analyzer/gcode_parser.py`
- Test: `tests/test_model.py` (ergänzen), `tests/test_gcode_parser.py` (ergänzen)

- [ ] **Schritt 1: `pyproject.toml` um Abhängigkeiten erweitern**

Die `[project]`-Tabelle um eine `dependencies`-Liste ergänzen (direkt nach der `requires-python`-Zeile):

```toml
dependencies = [
    "opencv-python-headless>=4.10",
    "numpy>=2.0",
    "pillow-heif>=0.18",
]
```

- [ ] **Schritt 2: Tests für `content_bounds` und `AnalysisResult` schreiben**

Ans Ende von `tests/test_model.py`:

```python
from pa_analyzer.model import AnalysisResult


def test_analysisresult_haelt_ergebnisfelder():
    r = AnalysisResult(
        best_pa=0.0285,
        nearest_step=0.028,
        confidence=0.7,
        scores=((0.01, 1.2), (0.012, 0.9)),
    )
    assert r.best_pa == pytest.approx(0.0285)
    assert r.nearest_step == pytest.approx(0.028)
    assert r.confidence == pytest.approx(0.7)
    assert len(r.scores) == 2
```

Ans Ende von `tests/test_gcode_parser.py`:

```python
def test_content_bounds_umschliesst_pattern(pa_pattern_gcode):
    # Bounding-Box aller extrudierten Pattern-Geometrie (Rahmen-Box +
    # Balken + Chevrons). Aus der GCode-Analyse: X ~100.7..199.3,
    # Y ~120.8..180.2.
    model = parse(pa_pattern_gcode)
    assert model.content_bounds is not None
    lo, hi = model.content_bounds
    assert lo.x == pytest.approx(100.731, abs=0.5)
    assert hi.x == pytest.approx(199.269, abs=0.5)
    assert lo.y == pytest.approx(120.787, abs=0.5)
    assert hi.y == pytest.approx(180.2, abs=1.0)
```

- [ ] **Schritt 3: Tests ausführen — RED**

Run: `python -m pytest tests/test_model.py tests/test_gcode_parser.py -k "analysisresult or content_bounds" -v`
Erwartet: FAIL (`AnalysisResult` nicht importierbar, `content_bounds` existiert nicht).

- [ ] **Schritt 4: `model.py` erweitern**

`AnalysisResult` ans Ende von `src/pa_analyzer/model.py` anhängen und `PatternModel` um `content_bounds` ergänzen. Das `PatternModel` wird zu:

```python
@dataclass(frozen=True)
class PatternModel:
    """Geparstes PA-Pattern: alle PA-Gruppen, die Rahmen-Box und die
    Bounding-Box der gesamten Druck-Geometrie."""

    groups: tuple[PaGroup, ...]
    frame_box: FrameBox | None = None
    content_bounds: tuple[Point, Point] | None = None


@dataclass(frozen=True)
class AnalysisResult:
    """Ergebnis der Bild-Auswertung."""

    best_pa: float                          # interpoliertes Optimum
    nearest_step: float                     # nächster gedruckter PA-Wert
    confidence: float                       # 0..1
    scores: tuple[tuple[float, float], ...]  # (pa_value, score) je Gruppe
```

- [ ] **Schritt 5: `gcode_parser.py` erweitern — `content_bounds` berechnen**

In `gcode_parser.py` eine Hilfsfunktion ergänzen und `parse()` anpassen. Die Bounding-Box wird aus allen extrudierenden Move-Endpunkten gebildet (der Tokenizer liefert sie bereits):

```python
def _content_bounds(gcode_text: str) -> tuple[Point, Point] | None:
    """Bounding-Box aller extrudierenden Move-Endpunkte (Rahmen-Box,
    Balken und Chevrons des Patterns)."""
    xs: list[float] = []
    ys: list[float] = []
    for kind, val in _tokenize(gcode_text):
        if kind == "move":
            move: _Move = val  # type: ignore[assignment]
            if move.extruding:
                xs.append(move.x)
                ys.append(move.y)
    if not xs:
        return None
    return Point(min(xs), min(ys)), Point(max(xs), max(ys))
```

`parse()` ersetzen durch:

```python
def parse(gcode_text: str) -> PatternModel:
    """Parst PA-Pattern-GCode in ein PatternModel."""
    groups = _dedupe_by_pa(_parse_groups(gcode_text))
    frame_box = _find_frame_box(gcode_text)
    content_bounds = _content_bounds(gcode_text)
    return PatternModel(
        groups=tuple(groups),
        frame_box=frame_box,
        content_bounds=content_bounds,
    )
```

- [ ] **Schritt 6: Tests ausführen — GREEN**

Run: `python -m pytest -v`
Erwartet: PASS (alle bisherigen 47 Tests + 2 neue). Falls `content_bounds` knapp außerhalb der Toleranz liegt: Es könnten Setup-/Anfahrt-Moves mitgezählt werden — prüfen, ob extrudierende Moves vor dem Pattern existieren, ggf. auf den Bereich ab der ersten echten PA-Gruppe eingrenzen. Erwartungswerte stammen aus der verifizierten GCode-Analyse.

- [ ] **Schritt 7: Commit**

```bash
git add pyproject.toml src/pa_analyzer/model.py src/pa_analyzer/gcode_parser.py tests/test_model.py tests/test_gcode_parser.py
git commit -m "Modell: content_bounds und AnalysisResult; Bildverarbeitungs-Abhaengigkeiten"
```

---

## Task 2: `image_loader` — Bild laden

Lädt JPG und HEIC zuverlässig als BGR-numpy-Array, mit EXIF-Orientierungs-Korrektur.

**Files:**
- Create: `src/pa_analyzer/image_loader.py`
- Test: `tests/test_image_loader.py`

- [ ] **Schritt 1: Tests schreiben** — `tests/test_image_loader.py`

```python
"""Tests für den Bild-Loader."""
from pathlib import Path

import numpy as np
import pytest

from pa_analyzer.image_loader import load_image

FIXTURES = Path(__file__).parent / "fixtures"


def test_laedt_jpg_als_bgr_array():
    img = load_image(FIXTURES / "pa_snap.jpg")
    assert isinstance(img, np.ndarray)
    assert img.shape == (960, 1280, 3)
    assert img.dtype == np.uint8


def test_laedt_heic():
    img = load_image(FIXTURES / "IMG_3843.HEIC")
    assert isinstance(img, np.ndarray)
    assert img.ndim == 3 and img.shape[2] == 3
    # 12-MP-Handy-Foto, EXIF-transponiert
    assert max(img.shape[:2]) == 4032
    assert min(img.shape[:2]) == 3024


def test_fehlende_datei_wirft():
    with pytest.raises(FileNotFoundError):
        load_image(FIXTURES / "gibt_es_nicht.jpg")
```

- [ ] **Schritt 2: Tests ausführen — RED**

Run: `python -m pytest tests/test_image_loader.py -v`
Erwartet: FAIL (`ModuleNotFoundError: pa_analyzer.image_loader`).

- [ ] **Schritt 3: `image_loader.py` implementieren**

```python
"""Lädt Bilddateien (JPG/HEIC) als BGR-numpy-Array für OpenCV."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pillow_heif
from PIL import Image, ImageOps

pillow_heif.register_heif_opener()


def load_image(path: str | Path) -> np.ndarray:
    """Lädt ein Bild als BGR-uint8-Array.

    Unterstützt JPG/PNG (über OpenCV) und HEIC (über pillow-heif).
    EXIF-Orientierung wird angewendet, damit Handy-Fotos korrekt
    ausgerichtet sind.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Bilddatei nicht gefunden: {path}")

    if path.suffix.lower() in (".heic", ".heif"):
        pil = ImageOps.exif_transpose(Image.open(path))
        rgb = np.array(pil.convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    img = cv2.imread(str(path))
    if img is None:
        raise ValueError(f"Bild konnte nicht gelesen werden: {path}")
    return img
```

- [ ] **Schritt 4: Tests ausführen — GREEN**

Run: `python -m pytest tests/test_image_loader.py -v`
Erwartet: PASS (3 Tests).

- [ ] **Schritt 5: Commit**

```bash
git add src/pa_analyzer/image_loader.py tests/test_image_loader.py
git commit -m "image_loader: JPG- und HEIC-Bilder als BGR-Array laden"
```

---

## Task 3: `pattern_locator` — Filament-Region lokalisieren

Erzeugt die Filament-Maske (farbunabhängig über die dominante Filamentfarbe) und bestimmt die 4 Eckpunkte der Druck-Region per `minAreaRect`.

**Files:**
- Create: `src/pa_analyzer/pattern_locator.py`
- Test: `tests/test_pattern_locator.py`

- [ ] **Schritt 1: Tests schreiben** — `tests/test_pattern_locator.py`

```python
"""Tests für die Pattern-Lokalisierung."""
from pathlib import Path

import numpy as np
import pytest

from pa_analyzer.image_loader import load_image
from pa_analyzer.pattern_locator import filament_mask, locate_quad

FIXTURES = Path(__file__).parent / "fixtures"


def test_filament_mask_ist_binaer():
    img = load_image(FIXTURES / "IMG_3843.HEIC")
    mask = filament_mask(img)
    assert mask.shape == img.shape[:2]
    assert mask.dtype == np.uint8
    assert set(np.unique(mask)).issubset({0, 255})


def test_filament_mask_erfasst_plausiblen_anteil():
    # Das Pattern füllt einen erkennbaren, aber nicht dominanten
    # Bildanteil — grobe Plausibilität gegen Totalausfall.
    img = load_image(FIXTURES / "IMG_3843.HEIC")
    anteil = filament_mask(img).mean() / 255
    assert 0.02 < anteil < 0.6


def test_locate_quad_liefert_vier_ecken():
    img = load_image(FIXTURES / "IMG_3843.HEIC")
    quad = locate_quad(filament_mask(img))
    assert quad.shape == (4, 2)


def test_locate_quad_umschliesst_patternregion_heic():
    # Aus dem Vision-Spike: die Druck-Region im Handy-Foto ist ein
    # rotiertes Rechteck mit Seitenverhältnis ~1.66 (Box+Balken
    # 98.5x59.4 mm). Die Quad-Fläche ist ein erheblicher Bildanteil.
    img = load_image(FIXTURES / "IMG_3843.HEIC")
    quad = locate_quad(filament_mask(img))
    seiten = [
        np.linalg.norm(quad[i] - quad[(i + 1) % 4]) for i in range(4)
    ]
    lang, kurz = max(seiten), min(seiten)
    assert 1.3 < lang / kurz < 2.1
    flaeche = lang * kurz
    bild = img.shape[0] * img.shape[1]
    assert 0.2 < flaeche / bild < 0.85
```

- [ ] **Schritt 2: Tests ausführen — RED**

Run: `python -m pytest tests/test_pattern_locator.py -v`
Erwartet: FAIL (`ModuleNotFoundError: pa_analyzer.pattern_locator`).

- [ ] **Schritt 3: `pattern_locator.py` implementieren**

Direkte Überführung von `filament()`/`blob_quad()` aus `spike/16_orient_final.py`. Die `soft`-Maske des Spikes wird weggelassen — die finale Pipeline nutzt sie nicht.

```python
"""Lokalisiert die gedruckte Pattern-Region im Bild.

Farbunabhängig: die dominante Filamentfarbe wird aus den gesättigten
Bildpixeln ermittelt, dann darauf maskiert. Die 4 Eckpunkte kommen aus
`cv2.minAreaRect` der größten zusammenhängenden Komponente.
"""
from __future__ import annotations

import cv2
import numpy as np


def _dominant_hue(hue: np.ndarray, mask: np.ndarray) -> int:
    """Häufigster Hue unter den maskierten Pixeln, zirkulär geglättet."""
    hist = np.bincount(hue[mask].ravel(), minlength=180).astype(float)
    tiled = np.r_[hist, hist, hist]
    smooth = np.convolve(tiled, np.ones(11) / 11, mode="same")[180:360]
    return int(np.argmax(smooth))


def filament_mask(img: np.ndarray) -> np.ndarray:
    """Binäre Maske (0/255) der gedruckten Filament-Pixel."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    sat_thr = max(60, int(cv2.threshold(sat, 0, 255, cv2.THRESH_OTSU)[0]))
    rough = (sat > sat_thr) & (val > 40) & (val < 250)
    h0 = _dominant_hue(hue, rough)
    dh = np.abs(hue.astype(int) - h0)
    dh = np.minimum(dh, 180 - dh)
    mask = ((dh < 18) & (sat > sat_thr) & (val > 40)).astype(np.uint8) * 255
    return mask


def locate_quad(mask: np.ndarray) -> np.ndarray:
    """4 Eckpunkte der größten zusammenhängenden Filament-Region.

    Reihenfolge: im Uhrzeigersinn ab der Ecke mit der kleinsten
    Koordinatensumme. Über `minAreaRect` — robust gegen die
    Chevron-Einkerbungen der Box-Kante (anders als convexHull).
    """
    opened = cv2.morphologyEx(
        mask, cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(opened)
    if n > 1:
        biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        opened = (lbl == biggest).astype(np.uint8) * 255
    ks = max(7, mask.shape[1] // 120) | 1
    closed = cv2.morphologyEx(
        opened, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ks, ks)))
    cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL,
                               cv2.CHAIN_APPROX_SIMPLE)
    big = max(cnts, key=cv2.contourArea)
    pts = cv2.boxPoints(cv2.minAreaRect(big)).astype(np.float64)
    center = pts.mean(axis=0)
    order = np.argsort(np.arctan2(pts[:, 1] - center[1],
                                  pts[:, 0] - center[0]))
    pts = pts[order]
    start = int(np.argmin(pts.sum(axis=1)))
    return np.roll(pts, -start, axis=0).astype(np.float32)
```

- [ ] **Schritt 4: Tests ausführen — GREEN**

Run: `python -m pytest tests/test_pattern_locator.py -v`
Erwartet: PASS (4 Tests).

- [ ] **Schritt 5: Commit**

```bash
git add src/pa_analyzer/pattern_locator.py tests/test_pattern_locator.py
git commit -m "pattern_locator: Filament-Maske und Eckpunkt-Erkennung"
```

---

## Task 4: `orientation` — Bild-Orientierung bestimmen

Das Pattern ist nahezu punktsymmetrisch; die 4 möglichen Rotationen des Quads müssen disambiguiert werden. Kriterium: das Dichte-Verhältnis Balken-Band / Chevron-Band (der Balken ist vollgefüllt, die Chevron-Zone gestreift).

**Files:**
- Create: `src/pa_analyzer/orientation.py`
- Test: `tests/test_orientation.py`

- [ ] **Schritt 1: Tests schreiben** — `tests/test_orientation.py`

```python
"""Tests für die Orientierungs-Bestimmung."""
from pathlib import Path

import pytest

from pa_analyzer.gcode_parser import parse
from pa_analyzer.image_loader import load_image
from pa_analyzer.orientation import pick_orientation
from pa_analyzer.pattern_locator import filament_mask, locate_quad

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def model():
    return parse((FIXTURES / "pa_pattern.gcode").read_text(
        encoding="utf-8", errors="replace"))


@pytest.mark.parametrize("name", ["IMG_3843.HEIC", "pa_snap.jpg",
                                  "pa_snap2.jpg"])
def test_pick_orientation_liefert_gueltige_rotation(name, model):
    img = load_image(FIXTURES / name)
    mask = filament_mask(img)
    quad = locate_quad(mask)
    rot, ratio = pick_orientation(mask, quad, model)
    assert rot in (0, 1, 2, 3)
    # Korrekte Orientierung hat ein deutliches Balken/Chevron-
    # Dichte-Verhältnis (Spike: >= 1.5 korrekt, <= 0.9 falsch).
    assert ratio > 1.3
```

- [ ] **Schritt 2: Tests ausführen — RED**

Run: `python -m pytest tests/test_orientation.py -v`
Erwartet: FAIL (`ModuleNotFoundError: pa_analyzer.orientation`).

- [ ] **Schritt 3: `orientation.py` implementieren**

Überführung von `pick_orientation()` aus `spike/16_orient_final.py`. Die Geometrie-Konstanten kommen aus dem `PatternModel` (`content_bounds` und `frame_box`) — kein Hardcoding.

```python
"""Bestimmt, welche der 4 Quad-Rotationen die korrekte Orientierung ist.

Das Pattern ist nahezu punktsymmetrisch. Eindeutiges Unterscheidungs-
merkmal: der Beschriftungs-Balken (Vollfüllung) liegt nur auf EINER
Seite. Die Rotation mit dem größten Dichte-Verhältnis Balken-Band /
Chevron-Band ist die richtige.
"""
from __future__ import annotations

import cv2
import numpy as np

from .model import PatternModel

PX_PER_MM = 24.0


def warp_size(model: PatternModel) -> tuple[int, int]:
    """(Breite, Höhe) des entzerrten Bildes in Pixeln."""
    lo, hi = model.content_bounds
    w = int(round((hi.x - lo.x) * PX_PER_MM))
    h = int(round((hi.y - lo.y) * PX_PER_MM))
    return w, h


def homography(quad: np.ndarray, rot: int, w: int, h: int) -> np.ndarray:
    norm = np.array([[0, 0], [w, 0], [w, h], [0, h]], np.float32)
    src = np.roll(quad, -rot, axis=0).astype(np.float32)
    return cv2.getPerspectiveTransform(src, norm)


def pick_orientation(
    mask: np.ndarray, quad: np.ndarray, model: PatternModel
) -> tuple[int, float]:
    """Liefert (beste Rotation 0..3, Dichte-Verhältnis der besten).

    Das Balken-Band ist der Bildstreifen oberhalb der Rahmen-Box-
    Oberkante; das Chevron-Band der Rest. Höchstes Verhältnis gewinnt.
    """
    w, h = warp_size(model)
    lo, hi = model.content_bounds
    # Oberkante der Rahmen-Box = Unterkante des Balkens.
    frame_top = max(p.y for p in model.frame_box.corners)
    band = int(round((hi.y - frame_top) * PX_PER_MM))

    best_rot, best_ratio = 0, -1.0
    for rot in range(4):
        hm = homography(quad, rot, w, h)
        warped = cv2.warpPerspective(mask, hm, (w, h))
        top = (warped[:band] > 0).mean()
        mid = (warped[band:] > 0).mean()
        ratio = top / mid if mid > 1e-3 else 0.0
        if ratio > best_ratio:
            best_rot, best_ratio = rot, ratio
    return best_rot, best_ratio
```

- [ ] **Schritt 4: Tests ausführen — GREEN**

Run: `python -m pytest tests/test_orientation.py -v`
Erwartet: PASS (3 Tests). Falls eine Rotation falsch erkannt wird: die Band-Höhe gegen `content_bounds`/`frame_box` prüfen — nicht den Erwartungswert aufweichen.

- [ ] **Schritt 5: Commit**

```bash
git add src/pa_analyzer/orientation.py tests/test_orientation.py
git commit -m "orientation: Rotations-Disambiguierung ueber Balken-Dichte"
```

> **Modul-Hinweis:** `orientation.py` beherbergt die Warp-Geometrie-
> Primitive (`PX_PER_MM`, `warp_size`, `homography`), da es das erste
> Modul der Pipeline ist, das sie benötigt. `rectifier` und
> `apex_analyzer` importieren sie von dort — Single Source of Truth,
> keine Duplikation.

---

## Task 5: `rectifier` — perspektivische Entzerrung

Wendet die Homographie für die gewählte Rotation an und entzerrt die Maske in den normierten Bett-Koordinaten-Raum. Stellt zusätzlich das Mapping GCode-mm → Warp-Pixel bereit.

**Files:**
- Create: `src/pa_analyzer/rectifier.py`
- Test: `tests/test_rectifier.py`

- [ ] **Schritt 1: Tests schreiben** — `tests/test_rectifier.py`

```python
"""Tests für die perspektivische Entzerrung."""
from pathlib import Path

import numpy as np
import pytest

from pa_analyzer.gcode_parser import parse
from pa_analyzer.image_loader import load_image
from pa_analyzer.orientation import pick_orientation, warp_size
from pa_analyzer.pattern_locator import filament_mask, locate_quad
from pa_analyzer.rectifier import bett_to_warp, rectify

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def model():
    return parse((FIXTURES / "pa_pattern.gcode").read_text(
        encoding="utf-8", errors="replace"))


def test_bett_to_warp_eckpunkte(model):
    # Untere-linke content_bounds-Ecke -> (0, Höhe); obere-rechte -> (Breite, 0).
    lo, hi = model.content_bounds
    w, h = warp_size(model)
    p_ll = bett_to_warp(lo.x, lo.y, model)
    p_or = bett_to_warp(hi.x, hi.y, model)
    assert p_ll == pytest.approx([0.0, h], abs=1.0)
    assert p_or == pytest.approx([w, 0.0], abs=1.0)


def test_rectify_liefert_warp_groesse(model):
    img = load_image(FIXTURES / "IMG_3843.HEIC")
    mask = filament_mask(img)
    quad = locate_quad(mask)
    rot, _ = pick_orientation(mask, quad, model)
    warped = rectify(mask, quad, rot, model)
    w, h = warp_size(model)
    assert warped.shape == (h, w)
    assert warped.dtype == np.uint8


def test_rectify_fuellt_plausibel(model):
    # Nach der Entzerrung füllt das Pattern einen erheblichen Teil
    # des normierten Bildes (Maske enthält Filament-Pixel).
    img = load_image(FIXTURES / "IMG_3843.HEIC")
    mask = filament_mask(img)
    quad = locate_quad(mask)
    rot, _ = pick_orientation(mask, quad, model)
    warped = rectify(mask, quad, rot, model)
    assert 0.2 < (warped > 0).mean() < 0.95
```

- [ ] **Schritt 2: Tests ausführen — RED**

Run: `python -m pytest tests/test_rectifier.py -v`
Erwartet: FAIL (`ModuleNotFoundError: pa_analyzer.rectifier`).

- [ ] **Schritt 3: `rectifier.py` implementieren**

```python
"""Entzerrt die maskierte Pattern-Region perspektivisch in den
normierten Bett-Koordinaten-Raum (siehe Vision-Spike)."""
from __future__ import annotations

import cv2
import numpy as np

from .model import PatternModel
from .orientation import PX_PER_MM, homography, warp_size


def bett_to_warp(x: float, y: float, model: PatternModel) -> np.ndarray:
    """GCode-Bett-Koordinate (mm) → (px, py) im entzerrten Bild.

    Die GCode-Y-Achse zeigt nach oben, die Bild-Y-Achse nach unten —
    daher wird Y an der Oberkante gespiegelt.
    """
    lo, hi = model.content_bounds
    return np.array([(x - lo.x) * PX_PER_MM, (hi.y - y) * PX_PER_MM])


def rectify(
    mask: np.ndarray, quad: np.ndarray, rot: int, model: PatternModel
) -> np.ndarray:
    """Entzerrt die Filament-Maske in den normierten Pattern-Raum.

    Ein abschließendes morphologisches Schließen (3×3) glättet die durch
    die Perspektiv-Transformation entstandenen Treppen-Artefakte.
    """
    w, h = warp_size(model)
    hm = homography(quad, rot, w, h)
    warped = cv2.warpPerspective(mask, hm, (w, h))
    return cv2.morphologyEx(
        warped, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
```

- [ ] **Schritt 4: Tests ausführen — GREEN**

Run: `python -m pytest tests/test_rectifier.py -v`
Erwartet: PASS (3 Tests).

- [ ] **Schritt 5: Commit**

```bash
git add src/pa_analyzer/rectifier.py tests/test_rectifier.py
git commit -m "rectifier: perspektivische Entzerrung in den Bett-Raum"
```

---

## Task 6: `apex_analyzer` — Zwei-Box-Messung

Misst pro PA-Gruppe den Filament-Flächenanteil in zwei kleinen, chevron-lokal ausgerichteten Boxen am Apex — die im Spike validierte Messmethode.

**Files:**
- Create: `src/pa_analyzer/apex_analyzer.py`
- Test: `tests/test_apex_analyzer.py`

- [ ] **Schritt 1: Tests schreiben** — `tests/test_apex_analyzer.py`

```python
"""Tests für die Zwei-Box-Apex-Messung."""
from pathlib import Path

import numpy as np
import pytest

from pa_analyzer.apex_analyzer import box_fill, measure_groups
from pa_analyzer.gcode_parser import parse
from pa_analyzer.image_loader import load_image
from pa_analyzer.orientation import pick_orientation
from pa_analyzer.pattern_locator import filament_mask, locate_quad
from pa_analyzer.rectifier import rectify

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def model():
    return parse((FIXTURES / "pa_pattern.gcode").read_text(
        encoding="utf-8", errors="replace"))


def test_box_fill_volle_maske():
    mask = np.full((100, 100), 255, np.uint8)
    f = box_fill(mask, np.array([50.0, 50.0]),
                 np.array([1.0, 0.0]), np.array([0.0, 1.0]), 10.0)
    assert f == pytest.approx(1.0)


def test_box_fill_leere_maske():
    mask = np.zeros((100, 100), np.uint8)
    f = box_fill(mask, np.array([50.0, 50.0]),
                 np.array([1.0, 0.0]), np.array([0.0, 1.0]), 10.0)
    assert f == pytest.approx(0.0)


def test_box_fill_halb_gefuellt():
    # Linke Hälfte gefüllt; Box mittig -> ~50 %.
    mask = np.zeros((100, 100), np.uint8)
    mask[:, :50] = 255
    f = box_fill(mask, np.array([50.0, 50.0]),
                 np.array([1.0, 0.0]), np.array([0.0, 1.0]), 10.0)
    assert 0.4 < f < 0.6


def test_measure_groups_liefert_eintrag_je_gruppe(model):
    img = load_image(FIXTURES / "IMG_3843.HEIC")
    mask = filament_mask(img)
    quad = locate_quad(mask)
    rot, _ = pick_orientation(mask, quad, model)
    warped = rectify(mask, quad, rot, model)
    measurements = measure_groups(warped, model)
    assert len(measurements) == 21
    for pa, fill_in, fill_out in measurements:
        assert 0.0 <= fill_in <= 1.0
        assert 0.0 <= fill_out <= 1.0
```

- [ ] **Schritt 2: Tests ausführen — RED**

Run: `python -m pytest tests/test_apex_analyzer.py -v`
Erwartet: FAIL (`ModuleNotFoundError: pa_analyzer.apex_analyzer`).

- [ ] **Schritt 3: `apex_analyzer.py` implementieren**

```python
"""Misst pro PA-Gruppe den Filament-Flächenanteil in zwei kleinen Boxen
am Chevron-Apex (Zwei-Box-Methode, validiert im Vision-Spike).

fill_in:  Box zentriert auf dem Soll-Apex — fällt, wenn bei zu hohem PA
          eine Lücke entsteht.
fill_out: dieselbe Box nach außen versetzt — hoch, wenn bei zu niedrigem
          PA Material über die Spitze quillt (Wulst).
"""
from __future__ import annotations

import cv2
import numpy as np

from .model import PatternModel
from .orientation import PX_PER_MM
from .rectifier import bett_to_warp

BOX_HALF_MM = 0.6     # halbe Kantenlänge der Mess-Box
OUT_OFFSET_MM = 0.75  # Versatz der Außen-Box entlang der Apex-Richtung


def box_fill(
    mask: np.ndarray,
    center: np.ndarray,
    axis_u: np.ndarray,
    axis_v: np.ndarray,
    half_px: float,
) -> float:
    """Filament-Anteil (0..1) in einem achsen-rotierten Quadrat.

    Das Quadrat wird per `cv2.remap` aus der Maske abgetastet — Achsen
    `axis_u`/`axis_v`, Mittelpunkt `center`, halbe Kante `half_px`.
    """
    grid = np.arange(-half_px, half_px + 1, 1.0)
    uu, vv = np.meshgrid(grid, grid)
    xs = (center[0] + axis_u[0] * uu + axis_v[0] * vv).astype(np.float32)
    ys = (center[1] + axis_u[1] * uu + axis_v[1] * vv).astype(np.float32)
    sampled = cv2.remap(mask, xs, ys, cv2.INTER_NEAREST, borderValue=0)
    return float((sampled > 0).mean())


def measure_groups(
    warped_mask: np.ndarray, model: PatternModel
) -> list[tuple[float, float, float]]:
    """Liefert je PA-Gruppe (pa_value, fill_in, fill_out).

    Pro Gruppe wird der Median über ihre Chevrons gebildet.
    """
    half = BOX_HALF_MM * PX_PER_MM
    offset = OUT_OFFSET_MM * PX_PER_MM
    result: list[tuple[float, float, float]] = []
    for group in model.groups:
        inner, outer = [], []
        for chevron in group.chevrons:
            s = bett_to_warp(chevron.start.x, chevron.start.y, model)
            a = bett_to_warp(chevron.apex.x, chevron.apex.y, model)
            e = bett_to_warp(chevron.end.x, chevron.end.y, model)
            u1 = (a - s) / np.linalg.norm(a - s)
            u2 = (a - e) / np.linalg.norm(a - e)
            out = u1 + u2
            out /= np.linalg.norm(out)
            tang = np.array([-out[1], out[0]])
            inner.append(box_fill(warped_mask, a, out, tang, half))
            outer.append(
                box_fill(warped_mask, a + out * offset, out, tang, half))
        result.append((group.pa_value, float(np.median(inner)),
                       float(np.median(outer))))
    return result
```

- [ ] **Schritt 4: Tests ausführen — GREEN**

Run: `python -m pytest tests/test_apex_analyzer.py -v`
Erwartet: PASS (4 Tests).

- [ ] **Schritt 5: Commit**

```bash
git add src/pa_analyzer/apex_analyzer.py tests/test_apex_analyzer.py
git commit -m "apex_analyzer: Zwei-Box-Flaechenmessung je PA-Gruppe"
```

---

## Task 7: `pa_estimator` — PA-Wert aus der Score-Kurve

Bildet aus den Apex-Messungen die Score-Kurve, findet das Minimum (mit Parabel-Interpolation) und schätzt eine Konfidenz.

**Files:**
- Create: `src/pa_analyzer/pa_estimator.py`
- Test: `tests/test_pa_estimator.py`

- [ ] **Schritt 1: Tests schreiben** — `tests/test_pa_estimator.py`

```python
"""Tests für die PA-Wert-Schätzung."""
import pytest

from pa_analyzer.model import AnalysisResult
from pa_analyzer.pa_estimator import estimate_pa


def _kurve(best_index):
    """Konstruiert 21 (pa, fill_in, fill_out)-Tripel mit V-förmigem
    Score und Minimum bei best_index."""
    out = []
    for i in range(21):
        pa = round(0.010 + i * 0.002, 3)
        # fill_in faellt bei hohem PA, fill_out faellt mit steigendem PA;
        # Score = (1-fill_in)+fill_out hat sein Tal bei best_index.
        dist = abs(i - best_index)
        fill_in = 1.0 if i <= best_index else max(0.0, 1.0 - 0.1 * dist)
        fill_out = max(0.0, 1.0 - 0.12 * (best_index - i)) if i <= best_index \
            else 0.0
        out.append((pa, fill_in, fill_out))
    return out


def test_estimate_pa_findet_minimum():
    result = estimate_pa(_kurve(best_index=9))  # PA 0.028
    assert isinstance(result, AnalysisResult)
    assert result.nearest_step == pytest.approx(0.028)
    assert abs(result.best_pa - 0.028) <= 0.003


def test_estimate_pa_scores_vollstaendig():
    result = estimate_pa(_kurve(best_index=9))
    assert len(result.scores) == 21


def test_estimate_pa_konfidenz_im_bereich():
    result = estimate_pa(_kurve(best_index=9))
    assert 0.0 <= result.confidence <= 1.0


def test_estimate_pa_flache_kurve_niedrige_konfidenz():
    # Konstante Messwerte -> flacher Score -> niedrige Konfidenz.
    flach = [(round(0.010 + i * 0.002, 3), 0.8, 0.3) for i in range(21)]
    result = estimate_pa(flach)
    assert result.confidence < 0.2
```

- [ ] **Schritt 2: Tests ausführen — RED**

Run: `python -m pytest tests/test_pa_estimator.py -v`
Erwartet: FAIL (`ModuleNotFoundError: pa_analyzer.pa_estimator`).

- [ ] **Schritt 3: `pa_estimator.py` implementieren**

```python
"""Ermittelt aus den Apex-Messungen den optimalen Pressure-Advance-Wert.

score = (1 − fill_in) + fill_out — bestraft Lücke (zu hoher PA) und
Wulst (zu niedriger PA). Das Minimum der geglätteten Score-Kurve ist
der optimale PA; ein Parabel-Fit um das Minimum liefert den
interpolierten Wert.
"""
from __future__ import annotations

import numpy as np

from .model import AnalysisResult


def estimate_pa(
    measurements: list[tuple[float, float, float]],
) -> AnalysisResult:
    """`measurements`: Liste von (pa_value, fill_in, fill_out)."""
    pa = np.array([m[0] for m in measurements], dtype=float)
    fill_in = np.array([m[1] for m in measurements], dtype=float)
    fill_out = np.array([m[2] for m in measurements], dtype=float)
    score = (1.0 - fill_in) + fill_out

    # Leichtes Glätten gegen Einzelausreißer (Ränder unverändert lassen).
    smooth = np.convolve(score, np.ones(3) / 3, mode="same")
    smooth[0], smooth[-1] = score[0], score[-1]

    k = int(np.argmin(smooth))
    best = float(pa[k])

    # Parabel-Fit ±3 Punkte um das diskrete Minimum für Sub-Schritt-Wert.
    lo, hi = max(0, k - 3), min(len(pa), k + 4)
    if hi - lo >= 3:
        coef = np.polyfit(pa[lo:hi], smooth[lo:hi], 2)
        if coef[0] > 0:
            vertex = -coef[1] / (2.0 * coef[0])
            if pa[0] <= vertex <= pa[-1]:
                best = float(vertex)

    # Konfidenz: Ausprägung des Minimums relativ zum Kurven-Mittel.
    span = float(smooth.mean() - smooth.min())
    confidence = float(np.clip(span / (smooth.mean() + 1e-6), 0.0, 1.0))

    return AnalysisResult(
        best_pa=best,
        nearest_step=float(pa[k]),
        confidence=confidence,
        scores=tuple((float(p), float(s)) for p, s in zip(pa, score)),
    )
```

- [ ] **Schritt 4: Tests ausführen — GREEN**

Run: `python -m pytest tests/test_pa_estimator.py -v`
Erwartet: PASS (4 Tests).

- [ ] **Schritt 5: Commit**

```bash
git add src/pa_analyzer/pa_estimator.py tests/test_pa_estimator.py
git commit -m "pa_estimator: Score-Kurve, Minimum und Konfidenz"
```

---

## Task 8: `analyzer` — Pipeline-Integration

Verdrahtet alle Module zur vollständigen Bild→PA-Pipeline und prüft sie End-zu-End gegen die echten Fixtures (Akzeptanzkriterium A3).

**Files:**
- Create: `src/pa_analyzer/analyzer.py`
- Test: `tests/test_analyzer.py`

- [ ] **Schritt 1: Tests schreiben** — `tests/test_analyzer.py`

```python
"""End-zu-End-Tests der Bild→PA-Pipeline."""
from pathlib import Path

import pytest

from pa_analyzer.analyzer import analyze
from pa_analyzer.model import AnalysisResult

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def gcode():
    return (FIXTURES / "pa_pattern.gcode").read_text(
        encoding="utf-8", errors="replace")


def test_analyze_handyfoto_trifft_referenzwert(gcode):
    # Akzeptanzkriterium A3: das hochauflösende Handy-Foto muss den
    # Referenz-PA 0.028 im Band 0.026-0.030 treffen.
    result = analyze(FIXTURES / "IMG_3843.HEIC", gcode)
    assert isinstance(result, AnalysisResult)
    assert 0.026 <= result.best_pa <= 0.030


def test_analyze_webcam_snapshot_laeuft_durch(gcode):
    # Akzeptanzkriterium A4: Webcam-Snapshots sind auflösungslimitiert —
    # geprüft wird nur, dass die Pipeline durchläuft und ein Ergebnis im
    # weiten Plausibilitätsbereich liefert (KEINE enge PA-Erwartung).
    for name in ("pa_snap.jpg", "pa_snap2.jpg"):
        result = analyze(FIXTURES / name, gcode)
        assert isinstance(result, AnalysisResult)
        assert 0.010 <= result.best_pa <= 0.050


def test_analyze_liefert_konfidenz_und_scores(gcode):
    result = analyze(FIXTURES / "IMG_3843.HEIC", gcode)
    assert 0.0 <= result.confidence <= 1.0
    assert len(result.scores) == 21
```

- [ ] **Schritt 2: Tests ausführen — RED**

Run: `python -m pytest tests/test_analyzer.py -v`
Erwartet: FAIL (`ModuleNotFoundError: pa_analyzer.analyzer`).

- [ ] **Schritt 3: `analyzer.py` implementieren**

```python
"""Pipeline-Integration: Bilddatei + GCode → optimaler PA-Wert."""
from __future__ import annotations

from pathlib import Path

from .apex_analyzer import measure_groups
from .gcode_parser import parse
from .image_loader import load_image
from .model import AnalysisResult
from .orientation import pick_orientation
from .pa_estimator import estimate_pa
from .pattern_locator import filament_mask, locate_quad
from .rectifier import rectify


def analyze(image_path: str | Path, gcode_text: str) -> AnalysisResult:
    """Ermittelt den optimalen PA-Wert aus einem Foto des gedruckten
    Patterns und dem zugehörigen GCode.

    Pipeline: GCode parsen → Bild laden → Filament-Maske → Eckpunkte →
    Orientierung → entzerren → Apex-Messung → PA-Schätzung.
    """
    model = parse(gcode_text)
    image = load_image(image_path)
    mask = filament_mask(image)
    quad = locate_quad(mask)
    rotation, _ratio = pick_orientation(mask, quad, model)
    warped = rectify(mask, quad, rotation, model)
    measurements = measure_groups(warped, model)
    return estimate_pa(measurements)
```

- [ ] **Schritt 4: Tests ausführen — GREEN**

Run: `python -m pytest tests/test_analyzer.py -v`
Erwartet: PASS (3 Tests). **Falls `test_analyze_handyfoto_trifft_referenzwert` fehlschlägt**, ist ein echter Pipeline-Fehler zu suchen (`superpowers:systematic-debugging`) — der Vision-Spike hat 0.029 für dieses Bild belegt. Den Erwartungswert NICHT aufweichen.

- [ ] **Schritt 5: Gesamte Test-Suite ausführen**

Run: `python -m pytest -v`
Erwartet: PASS (alle Tests aus Etappe 1 + Etappe 2, keine Regressionen).

- [ ] **Schritt 6: Commit**

```bash
git add src/pa_analyzer/analyzer.py tests/test_analyzer.py
git commit -m "analyzer: vollstaendige Bild->PA-Pipeline"
```

---

## Abschluss Etappe 2

Nach Task 8 ist der Stand:
- Lauffähige, getestete Bild→PA-Pipeline: aus Bilddatei + GCode den
  optimalen PA-Wert ermitteln.
- Akzeptanzkriterium **A3** (Handy-Foto trifft 0.028 ±1 Schritt) erfüllt.
- Akzeptanzkriterium **A4** (Webcam-Snapshots laufen durch) erfüllt;
  Genauigkeit auflösungslimitiert, ehrlich dokumentiert.

**Bewusst auf Etappe 3 verschoben:** `config`, `webcam` (HTTP-Snapshot),
`report`, die CLI, das Klipper-Macro, der Parser-Carry-Over `G91`/`M82`
sowie die Kalibrierungs-Fallbacks aus Spec §10.1 (gespeicherte
Kalibrierung, manuelle Ecken-Eingabe) — diese hängen an `config` und der
CLI. Etappe 2 setzt nur die automatische Lokalisierung um; der
Vision-Spike hat belegt, dass sie für den Hauptfall trägt. Mögliche
Verbesserung der Mess-Schärfe (stärkere Gewichtung von `fill_out`) ist
im Vision-Spike-Bericht §4 notiert.

