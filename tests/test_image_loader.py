"""Tests für den Bild-Loader."""
from pathlib import Path

import numpy as np
import pytest

from pa_analyzer.image_loader import load_image

FIXTURES = Path(__file__).parent / "fixtures"


def test_laedt_jpg_als_bgr_array():
    img = load_image(FIXTURES / "pa_snap.jpg")
    assert isinstance(img, np.ndarray)
    assert img.shape == (960, 1280, 3)
    assert img.dtype == np.uint8


def test_laedt_heic():
    img = load_image(FIXTURES / "IMG_3843.HEIC")
    assert isinstance(img, np.ndarray)
    assert img.ndim == 3 and img.shape[2] == 3
    # 12-MP-Handy-Foto, EXIF-transponiert
    assert max(img.shape[:2]) == 4032
    assert min(img.shape[:2]) == 3024


def test_fehlende_datei_wirft():
    with pytest.raises(FileNotFoundError):
        load_image(FIXTURES / "gibt_es_nicht.jpg")
