"""Tests für den Webcam-Snapshot-Abruf."""
import socket

import numpy as np
import pytest

from pa_analyzer.webcam import fetch_snapshot


def test_fetch_snapshot_liefert_bgr_array(http_server):
    img = fetch_snapshot(f"{http_server}/pa_snap.jpg")
    assert isinstance(img, np.ndarray)
    assert img.ndim == 3 and img.shape[2] == 3
    assert img.dtype == np.uint8


def test_fetch_snapshot_unerreichbar_wirft_connectionerror():
    # Einen OS-vergebenen Port binden und sofort schließen — danach ist
    # er garantiert ohne Listener (sofortiges ECONNREFUSED, plattform-
    # unabhängig und schnell).
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    with pytest.raises(ConnectionError):
        fetch_snapshot(f"http://127.0.0.1:{port}/snapshot.jpg")


def test_fetch_snapshot_kein_bild_wirft_valueerror(http_server):
    # pa_pattern.gcode ist eine Textdatei, kein dekodierbares Bild.
    with pytest.raises(ValueError):
        fetch_snapshot(f"{http_server}/pa_pattern.gcode")
