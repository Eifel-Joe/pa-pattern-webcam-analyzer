# Etappe 3 — Software-Integration — Implementierungsplan

> **Für agentische Umsetzung:** ERFORDERLICHES SUB-SKILL:
> `superpowers:subagent-driven-development` (empfohlen) oder
> `superpowers:executing-plans`, um diesen Plan Task für Task umzusetzen.
> Schritte nutzen Checkbox-Syntax (`- [ ]`).

**Ziel:** Aus der fertigen Bild→PA-Pipeline ein nutzbares CLI-Tool machen —
Konfiguration, Webcam-Snapshot, Report, eine CLI mit drei Subkommandos und
den zweistufigen Mess-Workflow als testbare Funktion.

**Architektur:** Sechs unabhängige Blatt-Module (`config`, `webcam`,
`report`, Parser-Carry-over, `analyzer`-Refactor, `two_stage`) plus die
`cli` als Verdrahtung. Jedes Modul hat eine Verantwortung und eine schmale
Schnittstelle. Alles auf Windows ohne Drucker testbar.

**Tech Stack:** Python 3.13, Standardbibliothek (`json`, `urllib`,
`argparse`, `http.server` für Tests), aufbauend auf den Etappe-1/2-Modulen.
Keine neuen externen Abhängigkeiten.

**Bezug:** Spec `docs/specs/2026-05-22-etappe3-integration.md`.

---

## Datei-Struktur

```
src/pa_analyzer/
├── config.py        # NEU: load_config() → Config                  [Task 1]
├── webcam.py        # NEU: fetch_snapshot() HTTP-Snapshot           [Task 2]
├── report.py        # NEU: format_result(), write_json(), read_json [Task 3]
├── gcode_parser.py  # ändern: _tokenize modus-bewusst (G91/M82)     [Task 4]
├── analyzer.py      # ändern: analyze_image() extrahieren           [Task 5]
├── two_stage.py     # NEU: refine_bounds()                          [Task 6]
└── cli.py           # NEU: main() mit generate/analyze/run          [Task 7]
tests/
├── conftest.py                 # ändern: http_server-Fixture        [Task 2]
├── test_config.py              # NEU                                [Task 1]
├── test_webcam.py              # NEU                                [Task 2]
├── test_report.py              # NEU                                [Task 3]
├── test_gcode_parser.py        # ergänzen: Carry-over-Tests         [Task 4]
├── test_analyzer.py            # ergänzen: analyze_image-Test       [Task 5]
├── test_two_stage.py           # NEU                                [Task 6]
├── test_cli.py                 # NEU                                [Task 7]
└── test_integration_etappe3.py # NEU                                [Task 8]
pyproject.toml       # ändern: [project.scripts]-Entry-Point         [Task 7]
```

Test-Runner verbatim: `.venv/Scripts/python.exe -m pytest`.
Ausgangsstand: 76 Tests grün.

---

## Task 1: `config` — Konfiguration laden

Lädt die nicht-pattern-bezogenen Laufzeit-Einstellungen (Webcam-URL,
Datei-Pfade) aus einer JSON-Datei. Fehlt die Datei, gelten Defaults.

**Files:**
- Create: `src/pa_analyzer/config.py`
- Test: `tests/test_config.py`

- [ ] **Schritt 1: Tests schreiben** — `tests/test_config.py`

```python
"""Tests für das Laden der Konfiguration."""
import json

from pa_analyzer.config import Config, load_config


def test_load_config_fehlende_datei_liefert_defaults(tmp_path):
    cfg = load_config(tmp_path / "gibt_es_nicht.json")
    assert cfg == Config()


def test_load_config_liest_werte(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({
        "webcam_url": "http://drucker/snapshot",
        "gcode_path": "/home/pi/pa.gcode",
        "report_path": "/home/pi/report.json",
    }), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.webcam_url == "http://drucker/snapshot"
    assert cfg.gcode_path == "/home/pi/pa.gcode"
    assert cfg.report_path == "/home/pi/report.json"


def test_load_config_ignoriert_unbekannte_schluessel(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({
        "webcam_url": "http://drucker/snapshot",
        "veraltete_option": 123,
    }), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.webcam_url == "http://drucker/snapshot"
    assert cfg.gcode_path == "pa_calibration.gcode"  # Default
```

- [ ] **Schritt 2: Tests ausführen — RED**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -v`
Erwartet: FAIL (`ModuleNotFoundError: pa_analyzer.config`).

- [ ] **Schritt 3: `config.py` implementieren**

```python
"""Lädt die Werkzeug-Konfiguration aus einer JSON-Datei.

Enthält die nicht-pattern-bezogenen Laufzeit-Einstellungen: Webcam-URL und
Datei-Pfade. Pattern-Parameter gehören dagegen zu GeneratorParams.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """Laufzeit-Konfiguration. Alle Felder haben Defaults, sodass das
    Werkzeug auch ohne Konfigurationsdatei läuft."""

    webcam_url: str = ""
    gcode_path: str = "pa_calibration.gcode"
    report_path: str = "pa_report.json"


def load_config(path: str | Path) -> Config:
    """Lädt die Konfiguration aus einer JSON-Datei.

    Fehlt die Datei, werden reine Default-Werte zurückgegeben. Unbekannte
    Schlüssel in der Datei werden ignoriert (vorwärtskompatibel).
    """
    path = Path(path)
    if not path.is_file():
        return Config()
    data = json.loads(path.read_text(encoding="utf-8"))
    known = {f.name for f in fields(Config)}
    return Config(**{k: v for k, v in data.items() if k in known})
```

- [ ] **Schritt 4: Tests ausführen — GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -v`
Erwartet: PASS (3 Tests).

- [ ] **Schritt 5: Commit**

```bash
git add src/pa_analyzer/config.py tests/test_config.py
git commit -m "config: Laufzeit-Konfiguration aus JSON laden"
```

---

## Task 2: `webcam` — HTTP-Snapshot

Holt ein Webcam-Standbild per HTTP und dekodiert es als BGR-Array. Nutzt
nur die Standardbibliothek. Der Test fährt einen echten lokalen
HTTP-Server (kein Mock).

**Files:**
- Create: `src/pa_analyzer/webcam.py`
- Modify: `tests/conftest.py` (Fixture `http_server` ergänzen)
- Test: `tests/test_webcam.py`

- [ ] **Schritt 1: `tests/conftest.py` komplett ersetzen**

Die gesamte Datei `tests/conftest.py` ersetzen durch (bestehende
`pa_pattern_gcode`-Fixture bleibt erhalten, `http_server` kommt hinzu):

```python
"""Gemeinsame pytest-Fixtures."""
import functools
import http.server
import threading
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def pa_pattern_gcode() -> str:
    """Roher Text des Beispiel-GCodes (OrcaSlicer-PA-Pattern, 4 Layer)."""
    return (FIXTURES_DIR / "pa_pattern.gcode").read_text(
        encoding="utf-8", errors="replace"
    )


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler ohne Request-Logging (leise Tests)."""

    def log_message(self, *args):
        pass


@pytest.fixture
def http_server():
    """Lokaler HTTP-Server, der den fixtures-Ordner ausliefert.

    Liefert die Basis-URL; wird nach dem Test sauber beendet.
    """
    handler = functools.partial(_QuietHandler, directory=str(FIXTURES_DIR))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
```

- [ ] **Schritt 2: Tests schreiben** — `tests/test_webcam.py`

```python
"""Tests für den Webcam-Snapshot-Abruf."""
import numpy as np
import pytest

from pa_analyzer.webcam import fetch_snapshot


def test_fetch_snapshot_liefert_bgr_array(http_server):
    img = fetch_snapshot(f"{http_server}/pa_snap.jpg")
    assert isinstance(img, np.ndarray)
    assert img.ndim == 3 and img.shape[2] == 3
    assert img.dtype == np.uint8


def test_fetch_snapshot_unerreichbar_wirft_connectionerror():
    # Port 1 ist privilegiert und hier garantiert ohne laufenden Server.
    with pytest.raises(ConnectionError):
        fetch_snapshot("http://127.0.0.1:1/snapshot.jpg")


def test_fetch_snapshot_kein_bild_wirft_valueerror(http_server):
    # pa_pattern.gcode ist eine Textdatei, kein dekodierbares Bild.
    with pytest.raises(ValueError):
        fetch_snapshot(f"{http_server}/pa_pattern.gcode")
```

- [ ] **Schritt 3: Tests ausführen — RED**

Run: `.venv/Scripts/python.exe -m pytest tests/test_webcam.py -v`
Erwartet: FAIL (`ModuleNotFoundError: pa_analyzer.webcam`).

- [ ] **Schritt 4: `webcam.py` implementieren**

```python
"""Holt einen Webcam-Snapshot per HTTP als BGR-numpy-Array.

Nutzt nur die Standardbibliothek (`urllib`) — ein einzelner GET-Request
rechtfertigt keine zusätzliche Abhängigkeit.
"""
from __future__ import annotations

import urllib.request

import cv2
import numpy as np

_TIMEOUT_S = 10.0


def fetch_snapshot(url: str) -> np.ndarray:
    """Lädt ein Webcam-Standbild von `url` und dekodiert es als BGR-Array.

    Wirft `ConnectionError`, wenn die Webcam nicht erreichbar ist, und
    `ValueError`, wenn die Antwort kein dekodierbares Bild ist.
    """
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_S) as resp:
            data = resp.read()
    except OSError as exc:
        # urllib.error.URLError/HTTPError und Socket-Timeouts sind alle
        # OSError-Subklassen.
        raise ConnectionError(
            f"Webcam-Snapshot nicht abrufbar: {url} ({exc})") from exc
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(
            f"Webcam-Antwort ist kein dekodierbares Bild: {url}")
    return img
```

- [ ] **Schritt 5: Tests ausführen — GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/test_webcam.py -v`
Erwartet: PASS (3 Tests).

- [ ] **Schritt 6: Commit**

```bash
git add src/pa_analyzer/webcam.py tests/test_webcam.py tests/conftest.py
git commit -m "webcam: HTTP-Snapshot per urllib als BGR-Array"
```

---

## Task 3: `report` — Ergebnis formatieren und speichern

Formatiert ein `AnalysisResult` für die Konsole und schreibt/liest es als
JSON-Report.

**Files:**
- Create: `src/pa_analyzer/report.py`
- Test: `tests/test_report.py`

- [ ] **Schritt 1: Tests schreiben** — `tests/test_report.py`

```python
"""Tests für die Report-Ausgabe."""
import json

from pa_analyzer.model import AnalysisResult
from pa_analyzer.report import format_result, read_json, write_json

_RESULT = AnalysisResult(
    best_pa=0.0285,
    nearest_step=0.028,
    confidence=0.7,
    scores=((0.024, 1.2), (0.026, 0.9), (0.028, 0.4)),
)


def test_format_result_enthaelt_kernwerte():
    text = format_result(_RESULT)
    assert "0.0285" in text
    assert "0.0280" in text
    assert "70 %" in text


def test_write_json_ist_round_trip_faehig(tmp_path):
    p = tmp_path / "report.json"
    write_json(_RESULT, p)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["best_pa"] == 0.0285
    assert data["nearest_step"] == 0.028
    assert data["confidence"] == 0.7
    assert data["scores"] == [[0.024, 1.2], [0.026, 0.9], [0.028, 0.4]]


def test_read_json_rekonstruiert_analysisresult(tmp_path):
    p = tmp_path / "report.json"
    write_json(_RESULT, p)
    wieder = read_json(p)
    assert wieder == _RESULT
```

- [ ] **Schritt 2: Tests ausführen — RED**

Run: `.venv/Scripts/python.exe -m pytest tests/test_report.py -v`
Erwartet: FAIL (`ModuleNotFoundError: pa_analyzer.report`).

- [ ] **Schritt 3: `report.py` implementieren**

```python
"""Formatiert ein AnalysisResult für Konsole und JSON-Report."""
from __future__ import annotations

import json
from pathlib import Path

from .model import AnalysisResult


def format_result(result: AnalysisResult) -> str:
    """Erzeugt eine mehrzeilige, menschenlesbare Ergebnis-Zusammenfassung."""
    return "\n".join([
        "PA-Analyse-Ergebnis",
        f"  Optimaler PA-Wert:     {result.best_pa:.4f}  (interpoliert)",
        f"  Nächster Druckschritt: {result.nearest_step:.4f}",
        f"  Konfidenz:             {result.confidence * 100:.0f} %",
    ])


def write_json(result: AnalysisResult, path: str | Path) -> None:
    """Schreibt das Ergebnis als JSON-Datei (UTF-8, eingerückt)."""
    payload = {
        "best_pa": result.best_pa,
        "nearest_step": result.nearest_step,
        "confidence": result.confidence,
        "scores": [[pa, score] for pa, score in result.scores],
    }
    Path(path).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")


def read_json(path: str | Path) -> AnalysisResult:
    """Liest einen zuvor mit `write_json` geschriebenen Report zurück."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return AnalysisResult(
        best_pa=data["best_pa"],
        nearest_step=data["nearest_step"],
        confidence=data["confidence"],
        scores=tuple((pa, score) for pa, score in data["scores"]),
    )
```

- [ ] **Schritt 4: Tests ausführen — GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/test_report.py -v`
Erwartet: PASS (3 Tests).

- [ ] **Schritt 5: Commit**

```bash
git add src/pa_analyzer/report.py tests/test_report.py
git commit -m "report: Ergebnis formatieren, als JSON schreiben und lesen"
```

---

## Task 4: Parser-Carry-over — G91/M82-Robustheit

Macht `_tokenize` modus-bewusst, damit der Parser auch extern erzeugten
GCode korrekt liest: G90/G91 (absolute/relative XY), M82/M83
(absolute/relative Extrusion), `G92 E` (Extruder-Origin). Defaults G90/M83 —
das bisherige Verhalten bleibt unverändert, alle 76 Tests bleiben grün.

**Files:**
- Modify: `src/pa_analyzer/gcode_parser.py`
- Test: `tests/test_gcode_parser.py` (ergänzen)

- [ ] **Schritt 1: Carry-over-Tests ans Ende von `tests/test_gcode_parser.py` anhängen**

```python
# ── Carry-over: G90/G91, M82/M83 (Etappe 3) ───────────────────────────

_BASIS = """\
G90
M83
SET_PRESSURE_ADVANCE ADVANCE=0.02
G1 X10 Y10 F1000
G1 X12 Y12 E0.5 F1000
G1 X10 Y14 E0.5 F1000
"""

_RELATIV_XY = """\
G91
M83
SET_PRESSURE_ADVANCE ADVANCE=0.02
G1 X10 Y10 F1000
G1 X2 Y2 E0.5 F1000
G1 X-2 Y2 E0.5 F1000
"""

_ABSOLUT_E = """\
G90
M82
SET_PRESSURE_ADVANCE ADVANCE=0.02
G1 X10 Y10 F1000
G1 X12 Y12 E0.5 F1000
G1 X10 Y14 E1.0 F1000
"""

_ABSOLUT_E_G92 = """\
G90
M82
SET_PRESSURE_ADVANCE ADVANCE=0.02
G1 X10 Y10 F1000
G1 X12 Y12 E0.5 F1000
G92 E0
G1 X10 Y14 E0.5 F1000
"""


def test_parse_g91_relativ_wie_g90_absolut():
    # Relative XY-Positionierung muss dasselbe Pattern ergeben wie die
    # absolute Variante mit identischer Geometrie.
    assert parse(_RELATIV_XY).groups == parse(_BASIS).groups


def test_parse_m82_absolut_e_wie_m83_relativ():
    # Bei M82 wird die Extrusion über das Delta zur vorigen E-Position
    # bestimmt — gleiches Pattern wie die relative M83-Variante.
    assert parse(_ABSOLUT_E).groups == parse(_BASIS).groups


def test_parse_m82_mit_g92_reset():
    # G92 E0 setzt den Extruder-Origin zurück; der folgende Move mit
    # E0.5 ist danach wieder eine Extrusion (Delta +0.5).
    assert parse(_ABSOLUT_E_G92).groups == parse(_BASIS).groups
```

- [ ] **Schritt 2: Tests ausführen — RED**

Run: `.venv/Scripts/python.exe -m pytest tests/test_gcode_parser.py -k "g91 or m82" -v`
Erwartet: FAIL — `test_parse_g91_relativ_wie_g90_absolut` und
`test_parse_m82_*` schlagen fehl (der Parser ignoriert die Modi noch).

- [ ] **Schritt 3: `_tokenize` durch die modus-bewusste Fassung ersetzen**

Die gesamte Funktion `_tokenize` in `src/pa_analyzer/gcode_parser.py`
ersetzen durch (`G92` wird über das erste Wort der Zeile erkannt — keine
neue Regex nötig):

```python
def _tokenize(gcode_text: str) -> Iterator[tuple[str, object]]:
    """Yieldet ('pa', wert: float) und ('move', _Move) in Datei-Reihenfolge.

    Modus-bewusst: G90/G91 schalten zwischen absoluter und relativer
    XY-Positionierung, M82/M83 zwischen absoluter und relativer Extrusion;
    `G92 E<wert>` setzt den Extruder-Origin. Defaults sind G90/M83 — der
    von diesem Projekt erzeugte GCode nutzt genau diese Modi, daher bleibt
    sein Parsing unverändert.

    Zeilen ohne XY-Änderung (Retract, reine F-Zeilen) erzeugen kein
    move-Token.
    """
    cur_x = 0.0
    cur_y = 0.0
    prev_e = 0.0
    abs_xy = True   # G90
    abs_e = False   # M83
    for raw in gcode_text.splitlines():
        # GCode-Kommentar entfernen, damit Achsen-Regexes keine Werte
        # aus Kommentartext aufgreifen (z.B. "; X123" wäre sonst ein Treffer).
        line = raw.split(";", 1)[0].strip()
        if not line:
            continue
        word = line.split()[0].upper()
        if word == "G90":
            abs_xy = True
            continue
        if word == "G91":
            abs_xy = False
            continue
        if word == "M82":
            abs_e = True
            continue
        if word == "M83":
            abs_e = False
            continue
        if word == "G92":
            me = _AXIS_RE["e"].search(line)
            if me:
                prev_e = float(me.group(1))
            continue
        pa = _PA_RE.match(line)
        if pa:
            yield ("pa", float(pa.group(1)))
            continue
        if not _G1_RE.match(line):
            continue
        mx = _AXIS_RE["x"].search(line)
        my = _AXIS_RE["y"].search(line)
        me = _AXIS_RE["e"].search(line)
        if mx:
            val = float(mx.group(1))
            cur_x = val if abs_xy else cur_x + val
        if my:
            val = float(my.group(1))
            cur_y = val if abs_xy else cur_y + val
        extruding = False
        if me:
            e_val = float(me.group(1))
            if abs_e:
                # Absolute Extrusion: nur ein positives Delta zur vorigen
                # E-Position ist echte Extrusion (ein Retract hat E < prev).
                extruding = (e_val - prev_e) > 0
                prev_e = e_val
            else:
                extruding = e_val > 0
        if mx or my:
            yield ("move", _Move(cur_x, cur_y, extruding))
```

- [ ] **Schritt 4: Tests ausführen — GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/test_gcode_parser.py -v`
Erwartet: PASS — die 3 neuen Carry-over-Tests grün, alle bisherigen
Parser-Tests weiterhin grün (Defaults G90/M83 = altes Verhalten).

- [ ] **Schritt 5: Gesamtsuite — keine Regression**

Run: `.venv/Scripts/python.exe -m pytest -q`
Erwartet: PASS (79 Tests: 76 bisher + 3 neu).

- [ ] **Schritt 6: Commit**

```bash
git add src/pa_analyzer/gcode_parser.py tests/test_gcode_parser.py
git commit -m "gcode_parser: G90/G91 und M82/M83 modus-bewusst tokenisieren"
```

---

## Task 5: `analyzer`-Refactor — `analyze_image` extrahieren

Spaltet `analyze()` in einen ndarray-Einstiegspunkt `analyze_image()` und
einen dünnen Pfad-Wrapper `analyze()`. Die Webcam liefert ein ndarray; der
`run`-Befehl der CLI braucht diesen Einstiegspunkt.

**Files:**
- Modify: `src/pa_analyzer/analyzer.py`
- Test: `tests/test_analyzer.py` (ergänzen)

- [ ] **Schritt 1: Importe in `tests/test_analyzer.py` erweitern**

Die bestehende Import-Zeile `from pa_analyzer.analyzer import analyze`
ersetzen durch:

```python
from pa_analyzer.analyzer import analyze, analyze_image
from pa_analyzer.image_loader import load_image
```

- [ ] **Schritt 2: Test ans Ende von `tests/test_analyzer.py` anhängen**

```python
def test_analyze_image_wie_analyze_ueber_pfad(gcode):
    # analyze_image (ndarray-Einstieg) muss exakt dasselbe liefern wie
    # analyze über den Datei-Pfad.
    img = load_image(FIXTURES / "IMG_3843.HEIC")
    via_image = analyze_image(img, gcode)
    via_path = analyze(FIXTURES / "IMG_3843.HEIC", gcode)
    assert via_image == via_path
```

- [ ] **Schritt 3: Test ausführen — RED**

Run: `.venv/Scripts/python.exe -m pytest tests/test_analyzer.py -k analyze_image -v`
Erwartet: FAIL (`ImportError: cannot import name 'analyze_image'`).

- [ ] **Schritt 4: `analyzer.py` ersetzen**

Die gesamte Datei `src/pa_analyzer/analyzer.py` ersetzen durch:

```python
"""Pipeline-Integration: Bild + GCode → optimaler PA-Wert."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .apex_analyzer import measure_groups
from .gcode_parser import parse
from .image_loader import load_image
from .model import AnalysisResult
from .orientation import pick_orientation
from .pa_estimator import estimate_pa
from .pattern_locator import filament_mask, locate_quad
from .rectifier import rectify


def analyze_image(image: np.ndarray, gcode_text: str) -> AnalysisResult:
    """Ermittelt den optimalen PA-Wert aus einem bereits geladenen Bild
    (BGR-Array) und dem zugehörigen GCode.

    Pipeline: GCode parsen → Filament-Maske → Eckpunkte → Orientierung →
    entzerren → Apex-Messung → PA-Schätzung.
    """
    model = parse(gcode_text)
    # Zentrale Boundary-Validierung: für GCode ohne auswertbares Pattern
    # liefert parse() leere groups bzw. None-Felder. An der Systemgrenze
    # abfangen — sonst kryptischer Fehler tief in der Vision-Pipeline.
    if (not model.groups or model.frame_box is None
            or model.content_bounds is None):
        raise ValueError(
            "analyze: GCode enthält kein auswertbares PA-Pattern "
            "(keine PA-Gruppen, Rahmen-Box oder Druck-Geometrie).")
    mask = filament_mask(image)
    quad = locate_quad(mask)
    rotation, _ratio = pick_orientation(mask, quad, model)
    warped = rectify(mask, quad, rotation, model)
    measurements = measure_groups(warped, model)
    return estimate_pa(measurements)


def analyze(image_path: str | Path, gcode_text: str) -> AnalysisResult:
    """Ermittelt den optimalen PA-Wert aus einem Foto des gedruckten
    Patterns (Datei-Pfad) und dem zugehörigen GCode.

    Pipeline: Bild laden → `analyze_image`.
    """
    return analyze_image(load_image(image_path), gcode_text)
```

- [ ] **Schritt 5: Tests ausführen — GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/test_analyzer.py -v`
Erwartet: PASS — der neue Test grün, die 4 bisherigen `test_analyzer`-Tests
weiterhin grün (`analyze()` verhält sich unverändert).

- [ ] **Schritt 6: Commit**

```bash
git add src/pa_analyzer/analyzer.py tests/test_analyzer.py
git commit -m "analyzer: ndarray-Einstiegspunkt analyze_image extrahieren"
```

---

## Task 6: `two_stage` — Lauf-2-Grenzen ableiten

Reine Funktion, die aus einem Lauf-1-`AnalysisResult` die engeren,
feiner gestaffelten PA-Grenzen für einen zweiten Mess-Lauf ableitet.

**Files:**
- Create: `src/pa_analyzer/two_stage.py`
- Test: `tests/test_two_stage.py`

- [ ] **Schritt 1: Tests schreiben** — `tests/test_two_stage.py`

```python
"""Tests für die Lauf-2-Grenzen-Ableitung (zweistufiger Workflow)."""
import pytest

from pa_analyzer.model import AnalysisResult
from pa_analyzer.two_stage import refine_bounds


def _result(best_pa):
    """Lauf-1-Ergebnis mit 21 PA-Werten 0.010..0.050, Schritt 0.002."""
    scores = tuple((round(0.010 + i * 0.002, 3), 1.0) for i in range(21))
    return AnalysisResult(
        best_pa=best_pa, nearest_step=round(best_pa, 3),
        confidence=0.5, scores=scores)


def test_refine_bounds_umschliesst_best_pa():
    start, end, _ = refine_bounds(_result(best_pa=0.028))
    assert start < 0.028 < end


def test_refine_bounds_schrittweite_feiner():
    _, _, step = refine_bounds(_result(best_pa=0.028))
    # Original-Schritt 0.002 -> halbiert 0.001.
    assert step == pytest.approx(0.001)


def test_refine_bounds_fenster_drei_schritte():
    start, end, _ = refine_bounds(_result(best_pa=0.028))
    # +/- 3 * 0.002 = +/- 0.006 um best_pa.
    assert start == pytest.approx(0.022)
    assert end == pytest.approx(0.034)


def test_refine_bounds_klemmt_start_auf_null():
    # best_pa nahe 0 -> start darf nicht negativ werden.
    start, _, _ = refine_bounds(_result(best_pa=0.004))
    assert start == 0.0
```

- [ ] **Schritt 2: Tests ausführen — RED**

Run: `.venv/Scripts/python.exe -m pytest tests/test_two_stage.py -v`
Erwartet: FAIL (`ModuleNotFoundError: pa_analyzer.two_stage`).

- [ ] **Schritt 3: `two_stage.py` implementieren**

```python
"""Leitet aus einem Lauf-1-Ergebnis die PA-Grenzen für einen feineren
zweiten Mess-Lauf ab (zweistufiger Workflow, siehe Vision-Spike §6).

Wirkprinzip: Der dominante Webcam-Fehler ist die räumliche
Lokalisierungs-Ungenauigkeit — sie ist pattern-relativ. Ein feiner
gestaffelter zweiter Lauf übersetzt denselben räumlichen Fehler in einen
kleineren absoluten PA-Fehler.
"""
from __future__ import annotations

from .model import AnalysisResult

_WINDOW_STEPS = 3   # halbe Fensterbreite in Original-Schrittweiten
_STEP_DIVISOR = 2   # Verfeinerungsfaktor der Schrittweite


def refine_bounds(result: AnalysisResult) -> tuple[float, float, float]:
    """Liefert (pa_start, pa_end, pa_step) für den zweiten Lauf.

    Das Fenster umspannt `best_pa ± 3 × Original-Schrittweite` (deckt die
    Lauf-1-Unsicherheit ab), die Schrittweite wird halbiert. `pa_start`
    wird auf >= 0 geklemmt. Die Original-Schrittweite stammt aus den
    PA-Werten von `result.scores` — kein Hardcoding.
    """
    pa_values = [pa for pa, _ in result.scores]
    orig_step = pa_values[1] - pa_values[0]
    new_step = round(orig_step / _STEP_DIVISOR, 6)
    half_window = _WINDOW_STEPS * orig_step
    start = max(0.0, round(result.best_pa - half_window, 6))
    end = round(result.best_pa + half_window, 6)
    return (start, end, new_step)
```

- [ ] **Schritt 4: Tests ausführen — GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/test_two_stage.py -v`
Erwartet: PASS (4 Tests).

- [ ] **Schritt 5: Commit**

```bash
git add src/pa_analyzer/two_stage.py tests/test_two_stage.py
git commit -m "two_stage: Lauf-2-PA-Grenzen aus dem Lauf-1-Ergebnis ableiten"
```

---

## Task 7: `cli` — Kommandozeilen-Schnittstelle

Verdrahtet alle Module zu drei Subkommandos und legt den Konsolen-Entry-
Point an.

**Files:**
- Create: `src/pa_analyzer/cli.py`
- Modify: `pyproject.toml`
- Test: `tests/test_cli.py`

- [ ] **Schritt 1: Tests schreiben** — `tests/test_cli.py`

```python
"""Tests für die Kommandozeilen-Schnittstelle."""
import json
from pathlib import Path

from pa_analyzer.cli import main
from pa_analyzer.gcode_parser import parse

FIXTURES = Path(__file__).parent / "fixtures"


def test_generate_schreibt_gueltigen_gcode(tmp_path):
    out = tmp_path / "pattern.gcode"
    rc = main(["generate", "-o", str(out),
               "--pa-start", "0.0", "--pa-end", "0.05", "--pa-step", "0.005"])
    assert rc == 0
    assert out.is_file()
    model = parse(out.read_text(encoding="utf-8"))
    assert len(model.groups) == 11  # 0.0..0.05 Schritt 0.005


def test_analyze_laeuft_und_gibt_ergebnis(capsys):
    rc = main(["analyze", str(FIXTURES / "IMG_3843.HEIC"),
               str(FIXTURES / "pa_pattern.gcode")])
    assert rc == 0
    assert "PA-Analyse-Ergebnis" in capsys.readouterr().out


def test_analyze_fehlende_datei_gibt_fehlercode(tmp_path, capsys):
    rc = main(["analyze", str(tmp_path / "gibt_es_nicht.jpg"),
               str(FIXTURES / "pa_pattern.gcode")])
    assert rc == 1
    assert "Fehler" in capsys.readouterr().err


def test_run_ohne_webcam_url_gibt_fehlercode(tmp_path, capsys):
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({}), encoding="utf-8")
    rc = main(["--config", str(cfg), "run",
               "--gcode", str(FIXTURES / "pa_pattern.gcode")])
    assert rc == 1
    assert "webcam_url" in capsys.readouterr().err


def test_run_ueber_lokalen_http_server(tmp_path, http_server, capsys):
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({
        "webcam_url": f"{http_server}/pa_snap.jpg",
    }), encoding="utf-8")
    rc = main(["--config", str(cfg), "run",
               "--gcode", str(FIXTURES / "pa_pattern.gcode")])
    assert rc == 0
    assert "PA-Analyse-Ergebnis" in capsys.readouterr().out
```

- [ ] **Schritt 2: Tests ausführen — RED**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cli.py -v`
Erwartet: FAIL (`ModuleNotFoundError: pa_analyzer.cli`).

- [ ] **Schritt 3: `cli.py` implementieren**

```python
"""Kommandozeilen-Einstiegspunkt des PA-Analyzers.

Subkommandos:
  generate  Pattern-GCode aus Parametern erzeugen (Phase 1)
  analyze   eine lokale Bilddatei auswerten (offline/manuell)
  run       einen Webcam-Snapshot holen und auswerten (Phase 3)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analyzer import analyze, analyze_image
from .config import load_config
from .gcode_generator import GeneratorParams, generate
from .model import AnalysisResult
from .report import format_result, read_json, write_json
from .two_stage import refine_bounds
from .webcam import fetch_snapshot

_DEFAULTS = GeneratorParams()


def _atomic_write(path: Path, text: str) -> None:
    """Schreibt `text` atomar: erst in eine temporäre Datei, dann
    umbenennen — so wird nie ein halb geschriebenes Pattern gedruckt."""
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _read_gcode(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


def _print_report(result: AnalysisResult, json_path: str | None) -> int:
    """Gibt das Ergebnis aus und schreibt es optional als JSON."""
    print(format_result(result))
    if json_path:
        write_json(result, json_path)
        print(f"Report geschrieben: {json_path}")
    return 0


def _cmd_generate(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    out_path = Path(args.output or cfg.gcode_path)
    if args.refine_from:
        start, end, step = refine_bounds(read_json(args.refine_from))
    else:
        start, end, step = args.pa_start, args.pa_end, args.pa_step
    params = GeneratorParams(pa_start=start, pa_end=end, pa_step=step)
    _atomic_write(out_path, generate(params))
    print(f"GCode geschrieben: {out_path}  "
          f"(PA {start}..{end}, Schritt {step})")
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    result = analyze(args.image, _read_gcode(args.gcode))
    return _print_report(result, args.json)


def _cmd_run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    if not cfg.webcam_url:
        print("Fehler: keine webcam_url konfiguriert.", file=sys.stderr)
        return 1
    gcode_text = _read_gcode(args.gcode or cfg.gcode_path)
    image = fetch_snapshot(cfg.webcam_url)
    result = analyze_image(image, gcode_text)
    return _print_report(result, args.json)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pa-analyzer",
        description="Automatische Pressure-Advance-Kalibrierung.")
    parser.add_argument("--config", default="pa_analyzer.json",
                        help="Pfad zur JSON-Konfiguration")
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="Pattern-GCode erzeugen")
    g.add_argument("-o", "--output", help="Ziel-Datei (Default aus Config)")
    g.add_argument("--pa-start", type=float, default=_DEFAULTS.pa_start)
    g.add_argument("--pa-end", type=float, default=_DEFAULTS.pa_end)
    g.add_argument("--pa-step", type=float, default=_DEFAULTS.pa_step)
    g.add_argument("--refine-from",
                   help="Report-JSON aus Lauf 1 für die Lauf-2-Grenzen")
    g.set_defaults(func=_cmd_generate)

    a = sub.add_parser("analyze", help="lokale Bilddatei auswerten")
    a.add_argument("image", help="Bilddatei (JPG/PNG/HEIC)")
    a.add_argument("gcode", help="zugehörige GCode-Datei")
    a.add_argument("--json", help="Report zusätzlich als JSON schreiben")
    a.set_defaults(func=_cmd_analyze)

    r = sub.add_parser("run", help="Webcam-Snapshot holen und auswerten")
    r.add_argument("--gcode", help="GCode-Datei (Default aus Config)")
    r.add_argument("--json", help="Report zusätzlich als JSON schreiben")
    r.set_defaults(func=_cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI-Einstiegspunkt. Liefert den Exit-Code (0 = Erfolg)."""
    args = _build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError) as exc:
        # FileNotFoundError, ConnectionError (Webcam) und ValueError
        # (ungültiges Bild / kein Pattern) sind erwartbare Nutzungsfehler —
        # klare Meldung statt Python-Traceback.
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Schritt 4: `pyproject.toml` um den Entry-Point erweitern**

Nach der `dependencies`-Liste (vor `[tool.pytest.ini_options]`) einfügen:

```toml
[project.scripts]
pa-analyzer = "pa_analyzer.cli:main"
```

- [ ] **Schritt 5: Tests ausführen — GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cli.py -v`
Erwartet: PASS (5 Tests).

- [ ] **Schritt 6: Commit**

```bash
git add src/pa_analyzer/cli.py tests/test_cli.py pyproject.toml
git commit -m "cli: Subkommandos generate/analyze/run und Konsolen-Entry-Point"
```

---

## Task 8: Integration — End-zu-End-Kette

Prüft die vollständige Etappe-3-Kette aus Nutzersicht: Pattern erzeugen →
auswerten → Report → verfeinern → Lauf-2-Pattern erzeugen.

**Files:**
- Create: `tests/test_integration_etappe3.py`

- [ ] **Schritt 1: Integrationstest schreiben** — `tests/test_integration_etappe3.py`

```python
"""End-zu-End-Test der Etappe-3-Integration (CLI-Kette)."""
from pathlib import Path

from pa_analyzer.cli import main
from pa_analyzer.gcode_parser import parse
from pa_analyzer.report import read_json

FIXTURES = Path(__file__).parent / "fixtures"


def test_generate_analyze_refine_kette(tmp_path):
    # 1. Lauf-1-Pattern erzeugen.
    gcode1 = tmp_path / "lauf1.gcode"
    assert main(["generate", "-o", str(gcode1), "--pa-start", "0.0",
                 "--pa-end", "0.05", "--pa-step", "0.005"]) == 0
    assert len(parse(gcode1.read_text(encoding="utf-8")).groups) == 11

    # 2. Echtes Foto auswerten, Report als JSON schreiben (E3-A2).
    report = tmp_path / "report.json"
    assert main(["analyze", str(FIXTURES / "IMG_3843.HEIC"),
                 str(FIXTURES / "pa_pattern.gcode"),
                 "--json", str(report)]) == 0
    result = read_json(report)
    assert 0.026 <= result.best_pa <= 0.030

    # 3. Lauf-2-Pattern aus dem Report verfeinern.
    gcode2 = tmp_path / "lauf2.gcode"
    assert main(["generate", "-o", str(gcode2),
                 "--refine-from", str(report)]) == 0
    pa2 = [g.pa_value for g in parse(
        gcode2.read_text(encoding="utf-8")).groups]
    # Lauf 2 ist enger als der volle Lauf-1-Bereich und nicht-negativ.
    assert min(pa2) >= 0.0
    assert 0.0 < max(pa2) - min(pa2) < 0.05
```

- [ ] **Schritt 2: Test ausführen — GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/test_integration_etappe3.py -v`
Erwartet: PASS (1 Test). **Falls die Band-Prüfung in Schritt 2 fehlschlägt**,
ist ein echter Pipeline-Fehler zu suchen (`superpowers:systematic-debugging`)
— der Erwartungswert ist durch Etappe 2 belegt und NICHT aufzuweichen.

- [ ] **Schritt 3: Gesamte Test-Suite ausführen**

Run: `.venv/Scripts/python.exe -m pytest -q`
Erwartet: PASS (99 Tests: 76 aus Etappe 1/2 + 23 aus Etappe 3, keine
Regressionen).

- [ ] **Schritt 4: Commit**

```bash
git add tests/test_integration_etappe3.py
git commit -m "test: End-zu-End-Integration der Etappe-3-CLI-Kette"
```

---

## Abschluss Etappe 3

Nach Task 8 ist der Stand:
- Lauffähiges CLI-Tool `pa-analyzer` mit `generate`/`analyze`/`run`.
- Konfiguration, Webcam-Snapshot, Report, zweistufiger Workflow integriert.
- Parser robust gegen extern erzeugten GCode (G91/M82/G92).
- Akzeptanzkriterien E3-A1 bis E3-A6 erfüllt; gesamte Suite grün auf
  Windows ohne Drucker.

**Bewusst auf Etappe 4 (Hardware) verschoben:** Klipper-Macros
(`gcode_shell_command`, `PA_CALIBRATE`), der Live-Test (Haupt-Spec A6,
V1–V5) und die Kalibrierungs-Fallbacks (Haupt-Spec §10.1). Sie brauchen
den echten Drucker.
