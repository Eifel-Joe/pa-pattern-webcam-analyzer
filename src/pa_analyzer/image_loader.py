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
