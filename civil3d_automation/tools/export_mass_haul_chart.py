# -*- coding: utf-8 -*-
"""
Export a simple mass-haul ordinate chart (SVG) from mass_haul_ordinates.csv.

Handbook v2 improvement #07 — offline substitute for Recharts in Excel/DPR.

Usage:
  python export_mass_haul_chart.py path/to/mass_haul.csv -o path/to/chart.svg
  python export_mass_haul_chart.py --project config/project.json
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys


def _read_ordinates(csv_path: str) -> tuple[list[float], list[float]]:
    stations: list[float] = []
    ordinates: list[float] = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            try:
                stations.append(float(row.get("station_m", 0) or 0))
                ordinates.append(float(row.get("ordinate_m3", 0) or 0))
            except (TypeError, ValueError):
                continue
    return stations, ordinates


def build_svg(
    stations: list[float],
    ordinates: list[float],
    width: int = 900,
    height: int = 320,
    title: str = "Mass haul ordinate",
) -> str:
    if not stations or not ordinates:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d">'
            '<text x="20" y="40">No mass haul data</text></svg>'
            % (width, height)
        )

    pad_l, pad_r, pad_t, pad_b = 60, 20, 40, 50
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    x0, x1 = min(stations), max(stations)
    y_vals = ordinates + [0.0]
    y0, y1 = min(y_vals), max(y_vals)
    if abs(x1 - x0) < 1e-6:
        x1 = x0 + 1.0
    if abs(y1 - y0) < 1e-6:
        y1 = y0 + 1.0
    y_pad = (y1 - y0) * 0.1
    y0 -= y_pad
    y1 += y_pad

    def sx(sta: float) -> float:
        return pad_l + (sta - x0) / (x1 - x0) * plot_w

    def sy(ord_m3: float) -> float:
        return pad_t + plot_h - (ord_m3 - y0) / (y1 - y0) * plot_h

    pts = " ".join("%.2f,%.2f" % (sx(stations[i]), sy(ordinates[i])) for i in range(len(stations)))
    zero_y = sy(0.0)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (
            width,
            height,
            width,
            height,
        ),
        '<rect width="100%%" height="100%%" fill="#faf9f5"/>',
        '<text x="%d" y="24" font-family="sans-serif" font-size="14" fill="#1a2e50">%s</text>'
        % (pad_l, title),
        '<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#c8c2b8"/>'
        % (pad_l, zero_y, width - pad_r, zero_y),
        '<polyline fill="none" stroke="#1a7a6e" stroke-width="2" points="%s"/>' % pts,
        '<text x="%d" y="%d" font-size="11" fill="#7a7468">Station (m)</text>'
        % (pad_l + plot_w // 2 - 40, height - 12),
        '<text x="12" y="%d" font-size="11" fill="#7a7468" transform="rotate(-90 12,%d)">Ordinate (m³)</text>'
        % (pad_t + plot_h // 2, pad_t + plot_h // 2),
        "</svg>",
    ]
    return "\n".join(lines)


def export_chart(csv_path: str, out_path: str, meta_path: str | None = None) -> str:
    stations, ordinates = _read_ordinates(csv_path)
    title = "Mass haul ordinate"
    if meta_path and os.path.isfile(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        lead = meta.get("economic_lead_m")
        if lead is not None:
            title = "Mass haul — economic lead %.1f m" % float(lead)
    svg = build_svg(stations, ordinates, title=title)
    d = os.path.dirname(out_path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg)
    return out_path


def _root_from_project(project_json: str) -> str:
    base = os.path.dirname(os.path.abspath(project_json))
    return os.path.normpath(os.path.join(base, ".."))


def export_from_project(project_json: str) -> str | None:
    with open(project_json, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    paths = cfg.get("paths") or {}
    mh = paths.get("mass_haul_csv")
    if not mh:
        return None
    root = _root_from_project(project_json)
    csv_path = os.path.normpath(os.path.join(root, mh.replace("/", os.sep)))
    if not os.path.isfile(csv_path):
        return None
    out_rel = paths.get("mass_haul_chart_svg", "out/mass_haul_chart.svg")
    out_path = os.path.normpath(os.path.join(root, out_rel.replace("/", os.sep)))
    meta_rel = paths.get("mass_haul_meta", "")
    meta_path = (
        os.path.normpath(os.path.join(root, meta_rel.replace("/", os.sep))) if meta_rel else None
    )
    return export_chart(csv_path, out_path, meta_path)


def main() -> int:
    ap = argparse.ArgumentParser(description="Export mass haul ordinate chart (SVG).")
    ap.add_argument("csv_or_project", help="mass_haul CSV or config/project.json")
    ap.add_argument("-o", "--output", help="Output .svg path (required for CSV input)")
    args = ap.parse_args()
    src = args.csv_or_project
    if src.lower().endswith(".json"):
        out = export_from_project(src)
        if not out:
            print("WARN: mass_haul_csv missing or not generated yet.")
            return 1
        print("OK: Wrote %s" % out)
        return 0
    if not args.output:
        ap.error("-o is required when input is a CSV file")
    export_chart(src, args.output)
    print("OK: Wrote %s" % args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
