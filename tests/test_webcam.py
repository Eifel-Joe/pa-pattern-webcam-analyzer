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
