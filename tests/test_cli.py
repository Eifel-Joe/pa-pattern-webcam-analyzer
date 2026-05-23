"""Tests für die Kommandozeilen-Schnittstelle."""
import socket
from pathlib import Path

from pa_analyzer.cli import main
from pa_analyzer.gcode_parser import parse

FIXTURES = Path(__file__).parent / "fixtures"


def _write_conf(path: Path, body: str) -> None:
    """Hilfsfunktion: pa_analyzer.conf-Inhalt schreiben."""
    path.write_text(body, encoding="utf-8")


def test_generate_schreibt_gueltigen_gcode(tmp_path, minimal_conf):
    out = tmp_path / "pattern.gcode"
    rc = main(["--config", str(minimal_conf), "generate", "-o", str(out),
               "--pa-start", "0.0", "--pa-end", "0.05", "--pa-step", "0.005"])
    assert rc == 0
    assert out.is_file()
    model = parse(out.read_text(encoding="utf-8"))
    assert len(model.groups) == 11  # 0.0..0.05 Schritt 0.005


def test_generate_ohne_start_gcode_bricht_klar_ab(tmp_path, capsys):
    # Voraussetzung start_gcode fehlt — generate muss mit klarer Meldung
    # abbrechen statt heimlich den Default zu nehmen.
    cfg = tmp_path / "pa_analyzer.conf"
    _write_conf(cfg, "[webcam]\nurl = http://drucker/snap\n")
    rc = main(["--config", str(cfg), "generate", "-o", str(tmp_path / "x.gcode"),
               "--pa-start", "0.0", "--pa-end", "0.05", "--pa-step", "0.005"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "start_gcode" in err
    assert "pa_analyzer.example.conf" in err


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
    # Leere Config -> keine webcam_url -> klarer Abbruch.
    cfg = tmp_path / "pa_analyzer.conf"
    _write_conf(cfg, "")
    rc = main(["--config", str(cfg), "run",
               "--gcode", str(FIXTURES / "pa_pattern.gcode")])
    assert rc == 1
    assert "webcam_url" in capsys.readouterr().err


def test_run_ueber_lokalen_http_server(tmp_path, http_server, capsys):
    report = tmp_path / "report.json"
    cfg = tmp_path / "pa_analyzer.conf"
    _write_conf(cfg, (
        f"[webcam]\nurl = {http_server}/pa_snap.jpg\n\n"
        f"[paths]\nreport_path = {report}\n"))
    rc = main(["--config", str(cfg), "run",
               "--gcode", str(FIXTURES / "pa_pattern.gcode")])
    assert rc == 0
    assert "PA-Analyse-Ergebnis" in capsys.readouterr().out
    # run schreibt den Report ohne --json nach dem konfigurierten Pfad.
    assert report.is_file()


def test_generate_honoriert_config_start_gcode(tmp_path):
    # Wenn die Config einen abweichenden start_gcode hat (andere
    # PRINT_START-Signatur), muss die CLI ihn in den erzeugten GCode
    # einbauen — Platzhalter {temp}/{bed_temp} werden substituiert.
    cfg = tmp_path / "pa_analyzer.conf"
    _write_conf(cfg, (
        "[macros]\n"
        "start_gcode =\n"
        "    PRINT_START HOTEND={temp} BED_TEMP={bed_temp} MATERIAL=PLA\n"))
    out = tmp_path / "pattern.gcode"
    rc = main(["--config", str(cfg), "generate", "-o", str(out),
               "--temp", "215", "--bed-temp", "60"])
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert "PRINT_START HOTEND=215 BED_TEMP=60 MATERIAL=PLA" in text
    # Der Klipper-Standard-Default darf NICHT erscheinen:
    assert "PRINT_START EXTRUDER=215 BED=60" not in text


def test_generate_skipt_purge_wenn_start_macro_purgt(tmp_path):
    # Wenn der User in der .conf vermerkt, dass sein PRINT_START schon
    # eine Purge-Linie zieht (purge_in_start_macro = true), darf der
    # Generator KEINE zweite emittieren — doppelter Purge waere nur
    # Material-Verschwendung.
    cfg = tmp_path / "pa_analyzer.conf"
    cfg.write_text(
        "[macros]\n"
        "start_gcode =\n"
        "    PRINT_START EXTRUDER={temp} BED={bed_temp}\n"
        "purge_in_start_macro = true\n",
        encoding="utf-8")
    out = tmp_path / "pattern.gcode"
    rc = main(["--config", str(cfg), "generate", "-o", str(out),
               "--pa-start", "0.0", "--pa-end", "0.01", "--pa-step", "0.005"])
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    # Header dokumentiert, dass Purge aus ist:
    assert "purge_length=0.0" in text
    # Default-Purge-End-Position (X10+80=90 bei bed_y/2=150) darf
    # nicht im Output stehen:
    assert "G1 X90 Y150" not in text


def test_generate_uebernimmt_filament_parameter(tmp_path, minimal_conf):
    # Hotend-Temperatur, Bett-Temperatur und Extrusionsfaktor MUESSEN in
    # den GCode einfliessen. Klipper-Konvention: PRINT_START bekommt
    # EXTRUDER/BED als Parameter und uebernimmt das Heizen.
    out = tmp_path / "pattern.gcode"
    rc = main(["--config", str(minimal_conf), "generate", "-o", str(out),
               "--pa-start", "0.0", "--pa-end", "0.05", "--pa-step", "0.005",
               "--temp", "230", "--bed-temp", "70", "--flow", "1.05"])
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    # PRINT_START traegt die Temperaturen:
    assert "PRINT_START EXTRUDER=230 BED=70" in text
    # Header-Kommentar dokumentiert alle drei Werte:
    assert "temp=230" in text
    assert "bed_temp=70" in text
    assert "extrusion_multiplier=1.05" in text


def test_run_webcam_offline_gibt_fehlercode(tmp_path, capsys):
    # Konfigurierte Webcam-URL zeigt auf einen sofort geschlossenen Port:
    # die ConnectionError aus fetch_snapshot muss zentral als sauberer
    # Fehler (Exit-Code 1, Meldung auf stderr) abgefangen werden.
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    cfg = tmp_path / "pa_analyzer.conf"
    _write_conf(cfg, (
        f"[webcam]\nurl = http://127.0.0.1:{port}/snapshot.jpg\n"))
    rc = main(["--config", str(cfg), "run",
               "--gcode", str(FIXTURES / "pa_pattern.gcode")])
    assert rc == 1
    assert "Fehler" in capsys.readouterr().err
