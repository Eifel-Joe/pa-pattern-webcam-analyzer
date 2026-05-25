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


def test_generate_skipt_cooldown_wenn_end_macro_kuehlt(tmp_path):
    # Wenn der User in der .conf vermerkt, dass sein PRINT_END schon
    # Heizungen aus + Luefter aus macht, darf der Generator nicht
    # zusaetzlich M104 S0 / M140 S0 / M107 emittieren.
    cfg = tmp_path / "pa_analyzer.conf"
    cfg.write_text(
        "[macros]\n"
        "start_gcode =\n"
        "    PRINT_START EXTRUDER={temp} BED={bed_temp}\n"
        "cooldown_in_end_macro = true\n",
        encoding="utf-8")
    out = tmp_path / "pattern.gcode"
    rc = main(["--config", str(cfg), "generate", "-o", str(out),
               "--pa-start", "0.0", "--pa-end", "0.01", "--pa-step", "0.005"])
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert "M104 S0" not in text
    assert "M140 S0" not in text
    assert "M107" not in text
    # PRINT_END + Analyse-Trigger muessen bleiben:
    assert "PRINT_END" in text
    assert "RUN_SHELL_COMMAND CMD=pa_analyze" in text


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


def test_generate_honoriert_cli_speed_und_accel(tmp_path, minimal_conf,
                                                  capsys):
    gcode_path = tmp_path / "out.gcode"
    from pa_analyzer.cli import main
    main([
        "--config", str(minimal_conf),
        "generate", "-o", str(gcode_path),
        "--speed", "150",
        "--accel", "2500",
    ])
    gc = gcode_path.read_text(encoding="utf-8")
    # speed_print=150 → F-Werte im G1-Print mit F9000 (150*60)
    assert " F9000" in gc, "CLI --speed kommt nicht im GCode an"
    # accel=2500 → SET_VELOCITY_LIMIT ACCEL=2500
    assert "SET_VELOCITY_LIMIT ACCEL=2500" in gc


def test_generate_zieht_speed_accel_aus_config(tmp_path, capsys):
    cfg = tmp_path / "test.conf"
    cfg.write_text(
        "[macros]\nstart_gcode = PRINT_START\n"
        "[generator]\nspeed_print = 80\naccel = 1500\n",
        encoding="utf-8")
    gcode_path = tmp_path / "out.gcode"
    from pa_analyzer.cli import main
    main(["--config", str(cfg), "generate", "-o", str(gcode_path)])
    gc = gcode_path.read_text(encoding="utf-8")
    assert " F4800" in gc  # 80 * 60
    assert "SET_VELOCITY_LIMIT ACCEL=1500" in gc


def test_generate_cli_ueberschreibt_config(tmp_path, capsys):
    cfg = tmp_path / "test.conf"
    cfg.write_text(
        "[macros]\nstart_gcode = PRINT_START\n"
        "[generator]\nspeed_print = 80\naccel = 1500\n",
        encoding="utf-8")
    gcode_path = tmp_path / "out.gcode"
    from pa_analyzer.cli import main
    main([
        "--config", str(cfg), "generate", "-o", str(gcode_path),
        "--speed", "200",  # überschreibt Config-80
    ])
    gc = gcode_path.read_text(encoding="utf-8")
    assert " F12000" in gc       # 200*60, CLI hat gewonnen
    assert "SET_VELOCITY_LIMIT ACCEL=1500" in gc  # Accel kam aus Config


def test_generate_honoriert_cli_walls(tmp_path, minimal_conf):
    gcode_path = tmp_path / "out.gcode"
    from pa_analyzer.cli import main
    # Default-G1-Count merken (mit wall_count=3) und vergleichen
    default_path = tmp_path / "default.gcode"
    main([
        "--config", str(minimal_conf),
        "generate", "-o", str(default_path),
    ])
    default_count = sum(
        1 for l in default_path.read_text(encoding="utf-8").splitlines()
        if l.startswith("G1"))
    main([
        "--config", str(minimal_conf),
        "generate", "-o", str(gcode_path),
        "--walls", "5",
    ])
    gc = gcode_path.read_text(encoding="utf-8")
    g1_count = sum(1 for l in gc.splitlines() if l.startswith("G1"))
    # wall_count=5 → deutlich mehr Chevron-Moves als wall_count=3.
    # Mindestens 30 % mehr (konservativ; tatsächlich ~67 % mehr Chevron-Moves
    # plus ~Label-Moves bleiben gleich).
    assert g1_count > default_count * 1.3, (
        f"--walls 5 erzeugt nur {g1_count} G1-Moves vs "
        f"{default_count} Default (wall_count=3) — Param wirkt nicht")


def test_generate_walls_default_wenn_kein_arg(tmp_path, minimal_conf):
    # Ohne --walls greift GeneratorParams-Default 3.
    # Aus Params berechnen statt fester Schwelle, damit der Test
    # robust gegen pa_step/Pattern-Geometrie-Änderungen ist.
    gcode_path = tmp_path / "out.gcode"
    from pa_analyzer.cli import main
    main([
        "--config", str(minimal_conf),
        "generate", "-o", str(gcode_path),
    ])
    gc = gcode_path.read_text(encoding="utf-8")
    g1_count = sum(1 for l in gc.splitlines() if l.startswith("G1"))
    # Mindest-Schwelle: Pattern muss Top-Bar + alle Chevrons + Labels haben.
    # Konservativ: > 200 G1-Moves bei jeder vernünftigen PA-Konfiguration.
    assert g1_count > 200, (
        f"Default-G1-Count {g1_count} zu niedrig — "
        "Default-Pattern unvollständig?")
