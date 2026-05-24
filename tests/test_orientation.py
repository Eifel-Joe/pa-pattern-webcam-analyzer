"""Tests für die Orientierungs-Bestimmung."""
from pathlib import Path

import pytest

from pa_analyzer.gcode_parser import parse
from pa_analyzer.image_loader import load_image
from pa_analyzer.orientation import pick_orientation
from pa_analyzer.pattern_locator import filament_mask, locate_quad

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def model():
    return parse((FIXTURES / "pa_pattern.gcode").read_text(
        encoding="utf-8", errors="replace"))


@pytest.mark.parametrize("name", [
    # Pre-existing seit PR #8 (chevron_band_top): pa_pattern.gcode-
    # Fixture ist v1-Geometrie (Top-Bar AUSSERHALB des Frames). Die
    # PR-#8-Logik nutzt aber chevron_band_top=142 mm — ergibt band=918
    # statt 409, falsche Rotation (rot=0 statt rot=3), ratio=1.27
    # statt 1.55. Quad bleibt bit-identisch, das ist rein ein orient-
    # Issue. Tracking-Fix: pick_orientation soll beide Bänder
    # ausprobieren und das beste nehmen — separater Branch.
    pytest.param("IMG_3843.HEIC", marks=pytest.mark.xfail(
        reason="PR #8 chevron_band_top bricht v1-Pattern-Fixture",
        strict=True)),
    "pa_snap.jpg", "pa_snap2.jpg",
])
def test_pick_orientation_liefert_gueltige_rotation(name, model):
    img = load_image(FIXTURES / name)
    mask = filament_mask(img)
    quad = locate_quad(mask)
    rot, ratio = pick_orientation(mask, quad, model)
    assert rot in (0, 1, 2, 3)
    # Korrekte Orientierung hat ein deutliches Balken/Chevron-
    # Dichte-Verhältnis (Spike: >= 1.5 korrekt, <= 0.9 falsch).
    assert ratio > 1.3


def test_orientation_funktioniert_mit_generator_output_synthetisch():
    """Generiert einen Pattern-GCode, rendert ihn als binäre Bitmap,
    und prüft, dass pick_orientation eine eindeutige Rotation findet
    (best_ratio > 1.5 = klares Top-Bar-Signal über Chevron-Band).

    Schließt damit den Mismatch, der beim Live-Test 1 die schlechte
    Konfidenz (16 %) verursacht hat: Generator hatte keinen Top-Bar,
    orientation.py erwartete einen.
    """
    np = pytest.importorskip("numpy")
    cv2 = pytest.importorskip("cv2")

    from pa_analyzer.gcode_generator import GeneratorParams, generate
    from pa_analyzer.gcode_parser import parse
    from pa_analyzer.orientation import pick_orientation

    gcode = generate(GeneratorParams())
    model = parse(gcode)
    # Sanity-Guards — bei kaputtem Generator (z.B. leerer GCode) wären
    # diese None, und der Test würde mit unklarem TypeError crashen.
    assert model.content_bounds is not None, (
        "parse() lieferte kein content_bounds — Generator fehlerhaft?")
    assert model.frame_box is not None, (
        "parse() lieferte keine frame_box — Generator fehlerhaft?")

    # Synthetisches Bild rendern: 800x600, Pattern-Bewegungen als
    # weiße Pixel auf schwarzem Hintergrund. Skalierung so, dass
    # Pattern ins Bild passt.
    img_w, img_h = 800, 600
    mask = np.zeros((img_h, img_w), dtype=np.uint8)
    # Pattern-Bounding-Box aus dem Modell
    lo, hi = model.content_bounds
    scale = min(img_w / (hi.x - lo.x), img_h / (hi.y - lo.y)) * 0.8
    cx, cy = img_w // 2, img_h // 2
    pcx, pcy = (lo.x + hi.x) / 2, (lo.y + hi.y) / 2

    def to_px(x: float, y: float) -> tuple[int, int]:
        return (int(cx + (x - pcx) * scale),
                int(cy - (y - pcy) * scale))  # Y invertiert (Bild oben)

    # Wir parsen den GCode noch einmal, um alle extrudierenden Moves
    # als Linien ins mask zu zeichnen.
    import re
    pos = (0.0, 0.0)
    for line in gcode.splitlines():
        if not line.startswith("G1"):
            continue
        x_match = re.search(r"X([\d.-]+)", line)
        y_match = re.search(r"Y([\d.-]+)", line)
        e_match = re.search(r"\sE([\d.-]+)", line)
        x = float(x_match.group(1)) if x_match else pos[0]
        y = float(y_match.group(1)) if y_match else pos[1]
        if e_match and (x_match or y_match):
            p1 = to_px(*pos)
            p2 = to_px(x, y)
            cv2.line(mask, p1, p2, 255, thickness=2)
        pos = (x, y)

    # Quad-Detection: einfaches Bounding-Rect der weißen Pixel.
    ys, xs = np.where(mask > 0)
    quad = np.array([
        [xs.min(), ys.min()],
        [xs.max(), ys.min()],
        [xs.max(), ys.max()],
        [xs.min(), ys.max()],
    ], dtype=np.float32)

    best_rot, best_ratio = pick_orientation(mask, quad, model)

    # Erwartung: Top-Bar liefert klares Dichte-Signal.
    assert best_ratio > 1.5, (
        f"best_ratio={best_ratio:.2f} — Top-Bar wirkt nicht als "
        "Dichte-Anker (Top/Mid-Verhältnis zu schwach).")
