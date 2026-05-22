"""Lädt Bilddateien (JPG/PNG/HEIC) als BGR-numpy-Array für OpenCV."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pillow_heif
from PIL import Image, ImageOps

# Registriert HEIC/HEIF als PIL-Format (Modul-Import-Seiteneffekt,
# der dokumentierte Weg von pillow-heif).
pillow_heif.register_heif_opener()


def load_image(path: str | Path) -> np.ndarray:
    """Lädt ein Bild als BGR-uint8-Array.

    Unterstützt JPG, PNG und HEIC/HEIF — alle über PIL, sodass die
    EXIF-Orientierung einheitlich angewendet wird (wichtig für
    Handy-Fotos, deren Sensor-Layout vom Anzeige-Layout abweicht). Das
    Format wird am Datei-Inhalt erkannt, nicht an der Endung.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Bilddatei nicht gefunden: {path}")

    try:
        pil = ImageOps.exif_transpose(Image.open(path))
        rgb = np.array(pil.convert("RGB"))
    except Exception as exc:
        raise ValueError(f"Bild konnte nicht gelesen werden: {path}") from exc

    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
