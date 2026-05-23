"""Kommandozeilen-Einstiegspunkt des PA-Analyzers.

Subkommandos:
  generate  Pattern-GCode aus Parametern erzeugen (Phase 1)
  analyze   eine lokale Bilddatei auswerten (offline/manuell)
  run       einen Webcam-Snapshot holen und auswerten (Phase 3)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analyzer import analyze, analyze_image
from .config import load_config
from .gcode_generator import GeneratorParams, generate
from .model import AnalysisResult
from .report import format_result, read_json, write_json
from .two_stage import refine_bounds
from .webcam import fetch_snapshot

_DEFAULTS = GeneratorParams()


def _atomic_write(path: Path, text: str) -> None:
    """Schreibt `text` atomar: erst in eine temporäre Datei, dann
    umbenennen — so wird nie ein halb geschriebenes Pattern gedruckt."""
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _read_gcode(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


def _print_report(result: AnalysisResult, json_path: str | None) -> int:
    """Gibt das Ergebnis aus und schreibt es optional als JSON."""
    print(format_result(result))
    if json_path:
        write_json(result, json_path)
        print(f"Report geschrieben: {json_path}")
    return 0


def _cmd_generate(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    out_path = Path(args.output or cfg.gcode_path)
    if args.refine_from:
        start, end, step = refine_bounds(read_json(args.refine_from))
    else:
        start, end, step = args.pa_start, args.pa_end, args.pa_step
    # temp und flow gehen unabhaengig vom Refine-Pfad ein: filament-
    # spezifische Werte muessen vom Aufrufer (User / PA_CALIBRATE-Macro)
    # kommen — sie wechseln je Lauf, nicht je Pattern-Bereich.
    params = GeneratorParams(
        pa_start=start, pa_end=end, pa_step=step,
        temp=args.temp, bed_temp=args.bed_temp,
        extrusion_multiplier=args.flow, fan_speed=args.fan)
    _atomic_write(out_path, generate(params))
    print(f"GCode geschrieben: {out_path}  "
          f"(PA {start}..{end}, Schritt {step}, "
          f"Hotend {args.temp}°C, Bett {args.bed_temp}°C, "
          f"Flow {args.flow}, Fan {args.fan})")
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    result = analyze(args.image, _read_gcode(args.gcode))
    return _print_report(result, args.json)


def _cmd_run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    if not cfg.webcam_url:
        print("Fehler: keine webcam_url konfiguriert.", file=sys.stderr)
        return 1
    gcode_text = _read_gcode(args.gcode or cfg.gcode_path)
    image = fetch_snapshot(cfg.webcam_url)
    result = analyze_image(image, gcode_text)
    # Der produktive run-Lauf schreibt immer einen JSON-Report (Spec F6);
    # --json überschreibt den konfigurierten report_path.
    return _print_report(result, args.json or cfg.report_path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pa-analyzer",
        description="Automatische Pressure-Advance-Kalibrierung.")
    parser.add_argument("--config", default="pa_analyzer.json",
                        help="Pfad zur JSON-Konfiguration")
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="Pattern-GCode erzeugen")
    g.add_argument("-o", "--output", help="Ziel-Datei (Default aus Config)")
    g.add_argument("--pa-start", type=float, default=_DEFAULTS.pa_start)
    g.add_argument("--pa-end", type=float, default=_DEFAULTS.pa_end)
    g.add_argument("--pa-step", type=float, default=_DEFAULTS.pa_step)
    g.add_argument("--temp", type=float, default=_DEFAULTS.temp,
                   help="Hotend-Temperatur in °C (M109)")
    g.add_argument("--bed-temp", type=float, default=_DEFAULTS.bed_temp,
                   help="Bett-Temperatur in °C (M190)")
    g.add_argument("--flow", type=float,
                   default=_DEFAULTS.extrusion_multiplier,
                   help="Extrusionsfaktor / Flow Ratio (Faktor um 1.0)")
    g.add_argument("--fan", type=float, default=_DEFAULTS.fan_speed,
                   help="Lüfter-PWM ab Layer 2 (0..1). Default 1.0 (PLA); "
                        "PETG/ABS deutlich niedriger oder 0.")
    g.add_argument("--refine-from",
                   help="Report-JSON aus Lauf 1 für die Lauf-2-Grenzen")
    g.set_defaults(func=_cmd_generate)

    a = sub.add_parser("analyze", help="lokale Bilddatei auswerten")
    a.add_argument("image", help="Bilddatei (JPG/PNG/HEIC)")
    a.add_argument("gcode", help="zugehörige GCode-Datei")
    a.add_argument("--json", help="Report zusätzlich als JSON schreiben")
    a.set_defaults(func=_cmd_analyze)

    r = sub.add_parser("run", help="Webcam-Snapshot holen und auswerten")
    r.add_argument("--gcode", help="GCode-Datei (Default aus Config)")
    r.add_argument("--json", help="Report zusätzlich als JSON schreiben")
    r.set_defaults(func=_cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI-Einstiegspunkt. Liefert den Exit-Code (0 = Erfolg)."""
    args = _build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError) as exc:
        # FileNotFoundError, ConnectionError (Webcam) und ValueError
        # (ungültiges Bild / kein Pattern) sind erwartbare Nutzungsfehler —
        # klare Meldung statt Python-Traceback.
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
