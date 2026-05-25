#!/usr/bin/env python3
"""Rendert das vorgeschlagene neue Pattern (kürzere Arme, weiter Apex-Abstand)
direkt aus dem Generator, damit man sieht ob die Chevrons klar getrennt sind.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from pa_analyzer.apex_analyzer import BOX_HALF_MM, OUT_OFFSET_MM  # noqa: E402
from pa_analyzer.gcode_generator import GeneratorParams, generate  # noqa: E402
from pa_analyzer.gcode_parser import parse  # noqa: E402


def render_for_params(p: GeneratorParams, out_path: str) -> None:
    gcode = generate(p)
    m = parse(gcode)
    lo, hi = m.content_bounds
    # Bisschen Padding um die Inhaltsbox damit Labels rechts der Pattern
    # nicht abgeschnitten werden
    pad_mm = 6.0
    px_per_mm = 12
    w = int((hi.x - lo.x + 2 * pad_mm) * px_per_mm)
    h = int((hi.y - lo.y + 2 * pad_mm) * px_per_mm)
    img = np.full((h, w, 3), 32, np.uint8)

    def to_px(pt_x, pt_y):
        return (int((pt_x - lo.x + pad_mm) * px_per_mm),
                int((hi.y - pt_y + pad_mm) * px_per_mm))

    # Raw-GCode-Linien rendern. Farben:
    #   Frame-Wände      : Grün
    #   Top-Bar-Perimeter: Hellgrün
    #   45°-Infill       : Orange
    #   Chevrons         : Rot
    #   Labels           : Cyan
    #   Travel           : Dunkelgrau (nicht gerendert für Übersichtlichkeit)
    import re
    pos_x, pos_y = 0.0, 0.0
    pa_value = None  # None vor erstem SET_PA, sonst der aktuelle PA-Wert
    in_label_block = False  # True nach SET_PA=0 (Layer 1)
    saw_first_set_pa = False

    for line in gcode.splitlines():
        # State-Tracking
        if line.startswith("SET_PRESSURE_ADVANCE"):
            m_pa = re.search(r"ADVANCE=([\d.-]+)", line)
            if m_pa:
                pa_value = float(m_pa.group(1))
                in_label_block = (pa_value == 0.0 and saw_first_set_pa)
                saw_first_set_pa = True
            continue
        if not line.startswith("G1"):
            continue
        m_x = re.search(r"X([\d.-]+)", line)
        m_y = re.search(r"Y([\d.-]+)", line)
        m_e = re.search(r"\sE([\d.-]+)", line)
        new_x = float(m_x.group(1)) if m_x else pos_x
        new_y = float(m_y.group(1)) if m_y else pos_y
        if m_e and (m_x or m_y):
            # Extrudierte Print-Linie
            if in_label_block:
                color = (255, 200, 0)  # Cyan: Labels
            elif "Fill: Print" in line:
                color = (0, 140, 255)  # Orange: Infill
            elif pa_value is None or pa_value == 0.0:
                # Vor erstem SET_PA: Frame + Top-Bar-Perimeter + Anker
                # (Chevrons kommen ERST nach SET_PA mit pa>0 oder pa=0
                # für die Frame-Zeichnung. Wir nehmen "vor Layer-Loop"
                # als Frame-Style.)
                color = (0, 220, 0)    # Grün: Frame/Top-Bar-Walls
            else:
                color = (0, 60, 220)   # Rot: Chevrons
            cv2.line(img, to_px(pos_x, pos_y), to_px(new_x, new_y), color, 2)
        # Position immer aktualisieren (auch für Travels)
        if m_x or m_y:
            pos_x, pos_y = new_x, new_y

    # Apex-Marker (Mess-Boxen) wie zuvor — über die Linien-Rendering
    for g in m.groups:
        apx = to_px(g.apex.x, g.apex.y)
        cv2.circle(img, apx, 3, (0, 255, 255), -1)
        bh = int(BOX_HALF_MM * px_per_mm)
        cv2.rectangle(img, (apx[0] - bh, apx[1] - bh),
                      (apx[0] + bh, apx[1] + bh), (255, 255, 0), 1)

    # Frame-Marker-Outline (gestrichelt, dezent grau) zur Orientierung
    if m.frame_box:
        fpts = np.array(
            [to_px(p_.x, p_.y) for p_ in m.frame_box.corners], np.int32)
        cv2.polylines(img, [fpts], True, (60, 60, 60), 1)

    cv2.imwrite(out_path, img)
    print(f"Saved: {out_path} ({w}x{h} px, {hi.x-lo.x:.1f}x{hi.y-lo.y:.1f} mm)")


def main():
    # v4 Vorschlag: Orca-Stil — lange Arme für volle Druckgeschwindigkeit,
    # weiter Apex-Abstand für klare Trennung
    render_for_params(
        GeneratorParams(
            wall_side_length=30.0,    # zurück zu v2-Länge (Arme >10mm für 180mm/s+3000a)
            pattern_spacing=18.0,     # weit: group_advance ~20 mm, Chevrons klar getrennt
            pa_step=0.01,             # 9 statt 17 Werte → Pattern bleibt unter 200 mm
        ),
        "reference/render_v4.png",
    )


if __name__ == "__main__":
    main()
