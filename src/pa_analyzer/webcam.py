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
