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


@pytest.fixture
def minimal_conf(tmp_path) -> Path:
    """Minimal-pa_analyzer.conf mit start_gcode — Voraussetzung für
    `pa-analyzer generate` (PRINT_START-Signaturen sind nicht genormt;
    ohne explizite Konfiguration bricht generate ab)."""
    cfg = tmp_path / "pa_analyzer.conf"
    cfg.write_text(
        "[macros]\n"
        "start_gcode =\n"
        "    PRINT_START EXTRUDER={temp} BED={bed_temp}\n",
        encoding="utf-8")
    return cfg


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
