"""Tests für die Kommandozeilen-Schnittstelle."""
import json
import socket
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
    report = tmp_path / "report.json"
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({
        "webcam_url": f"{http_server}/pa_snap.jpg",
        "report_path": str(report),
    }), encoding="utf-8")
    rc = main(["--config", str(cfg), "run",
               "--gcode", str(FIXTURES / "pa_pattern.gcode")])
    assert rc == 0
    assert "PA-Analyse-Ergebnis" in capsys.readouterr().out
    # run schreibt den Report ohne --json nach dem konfigurierten Pfad.
    assert report.is_file()


def test_generate_uebernimmt_temp_und_flow(tmp_path):
    # Drucktemperatur und Extrusionsfaktor MUESSEN in den GCode einfliessen
    # (Spec §5 Entscheidung 2: einbacken statt indirekt). Ohne --temp/--flow
    # waere die generierte Datei filament-unabhaengig und damit falsch fuer
    # den realen Druck.
    out = tmp_path / "pattern.gcode"
    rc = main(["generate", "-o", str(out),
               "--pa-start", "0.0", "--pa-end", "0.05", "--pa-step", "0.005",
               "--temp", "230", "--flow", "1.05"])
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    # Temperatur wird per M109 eingebacken:
    assert "M109 S230" in text
    # Header-Kommentar dokumentiert beide Werte:
    assert "temp=230" in text
    assert "extrusion_multiplier=1.05" in text


def test_run_webcam_offline_gibt_fehlercode(tmp_path, capsys):
    # Konfigurierte Webcam-URL zeigt auf einen sofort geschlossenen Port:
    # die ConnectionError aus fetch_snapshot muss zentral als sauberer
    # Fehler (Exit-Code 1, Meldung auf stderr) abgefangen werden.
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({
        "webcam_url": f"http://127.0.0.1:{port}/snapshot.jpg",
    }), encoding="utf-8")
    rc = main(["--config", str(cfg), "run",
               "--gcode", str(FIXTURES / "pa_pattern.gcode")])
    assert rc == 1
    assert "Fehler" in capsys.readouterr().err
