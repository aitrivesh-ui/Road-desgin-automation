# -*- coding: utf-8 -*-
"""
Road Automation — M18  Intersection Design Calculator  (Python 3).

Reads intersections.csv and produces intersection_geometry.csv and
offset_alignment_inputs.csv for import into Civil 3D.

Input CSV columns (intersections.csv):
  int_id, station_m, road_name, angle_deg, left_turn_lanes,
  right_turn_lanes, radius_m, approach_speed_kph

Output files:
  out/intersection_geometry.csv   — computed geometry per intersection
  out/offset_alignment_inputs.csv — offset alignment data for Civil 3D

Usage:
  python intersection_design.py                       GUI wizard
  python intersection_design.py --cli <input.csv>     headless
"""
from __future__ import annotations

import csv as _csv
import math
import os
import sys
from typing import List, NamedTuple, Optional

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

DEFAULT_GEOM_OUT   = os.path.join(ROOT, "out", "intersection_geometry.csv")
DEFAULT_OFFSET_OUT = os.path.join(ROOT, "out", "offset_alignment_inputs.csv")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class IntersectionInput(NamedTuple):
    int_id:            str
    station_m:         float
    road_name:         str
    angle_deg:         float   # skew angle relative to main alignment (0 = perpendicular)
    left_turn_lanes:   int
    right_turn_lanes:  int
    radius_m:          float   # kerb return radius
    approach_speed_kph: float


class IntersectionResult(NamedTuple):
    int_id:               str
    station_m:            float
    road_name:            str
    angle_deg:            float
    kerb_return_length_m: float
    turning_lane_length_m: float
    taper_length_m:       float
    offset_left_m:        float   # left edge of intersection box from CL
    offset_right_m:       float   # right edge of intersection box from CL
    sight_distance_m:     float   # stopping sight distance
    notes:                str


# ---------------------------------------------------------------------------
# Constants (Austroads-inspired defaults)
# ---------------------------------------------------------------------------

_LANE_WIDTH      = 3.5   # m
_SHOULDER        = 1.5   # m
_MIN_TAPER_RATIO = 30    # 1:30 taper for turn bays


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------

REQUIRED_COLS = {
    "int_id", "station_m", "road_name", "angle_deg",
    "left_turn_lanes", "right_turn_lanes", "radius_m", "approach_speed_kph",
}


def read_inputs(path: str) -> List[IntersectionInput]:
    rows: List[IntersectionInput] = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = _csv.DictReader(f)
        missing = REQUIRED_COLS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
        for i, row in enumerate(reader, start=2):
            try:
                rows.append(IntersectionInput(
                    int_id            = row["int_id"].strip(),
                    station_m         = float(row["station_m"]),
                    road_name         = row["road_name"].strip(),
                    angle_deg         = float(row["angle_deg"]),
                    left_turn_lanes   = int(float(row["left_turn_lanes"])),
                    right_turn_lanes  = int(float(row["right_turn_lanes"])),
                    radius_m          = float(row["radius_m"]),
                    approach_speed_kph= float(row["approach_speed_kph"]),
                ))
            except (ValueError, KeyError) as exc:
                raise ValueError(f"Row {i}: {exc}") from exc
    if not rows:
        raise ValueError("No data rows in input file.")
    return rows


# ---------------------------------------------------------------------------
# Design engine
# ---------------------------------------------------------------------------

def _stopping_sight_distance(speed_kph: float) -> float:
    """Austroads SSD (m) for given design speed."""
    v = speed_kph
    reaction_time = 2.5   # seconds
    deceleration  = 3.4   # m/s² (wet pavement)
    v_ms = v / 3.6
    return round(v_ms * reaction_time + (v_ms ** 2) / (2 * deceleration), 1)


def _kerb_return_arc(radius: float, angle_deg: float) -> float:
    """Arc length of kerb return for given radius and intersection angle."""
    # Corner angle for a perpendicular intersection = 90°
    # For skewed intersections, adjust by the skew angle
    corner_angle = 90.0 - abs(angle_deg)
    corner_angle = max(30.0, min(150.0, corner_angle))
    arc = radius * math.radians(corner_angle)
    return round(arc, 2)


def _turning_lane_length(speed_kph: float, lanes: int) -> float:
    """Required deceleration + storage length for turn bay."""
    if lanes <= 0:
        return 0.0
    v_ms = speed_kph / 3.6
    # Deceleration lane: v² / (2 × 2.5 m/s²)
    decel = (v_ms ** 2) / (2 * 2.5)
    # Storage: 20 m per turn lane
    storage = 20.0 * lanes
    return round(decel + storage, 1)


def _taper_length(lane_width: float, ratio: int) -> float:
    return round(lane_width * ratio, 1)


def design_intersection(inp: IntersectionInput) -> IntersectionResult:
    speed = inp.approach_speed_kph
    r     = inp.radius_m

    kerb_return   = _kerb_return_arc(r, inp.angle_deg)
    lt_len        = _turning_lane_length(speed, inp.left_turn_lanes)
    rt_len        = _turning_lane_length(speed, inp.right_turn_lanes)
    turn_lane_len = max(lt_len, rt_len)
    taper_len     = _taper_length(_LANE_WIDTH, _MIN_TAPER_RATIO)
    ssd           = _stopping_sight_distance(speed)

    # Offsets from centreline for intersection box
    base_lanes = 2  # one lane each way on main road
    left_extra  = inp.left_turn_lanes  * _LANE_WIDTH
    right_extra = inp.right_turn_lanes * _LANE_WIDTH
    offset_l = round(base_lanes * _LANE_WIDTH / 2 + left_extra + _SHOULDER, 2)
    offset_r = round(base_lanes * _LANE_WIDTH / 2 + right_extra + _SHOULDER, 2)

    notes_parts = []
    if abs(inp.angle_deg) > 15:
        notes_parts.append("Skew >15deg: check SSD for skewed intersection")
    if r < 6.0:
        notes_parts.append("Small radius: verify swept path for design vehicle")
    notes = "; ".join(notes_parts) if notes_parts else "OK"

    return IntersectionResult(
        int_id               = inp.int_id,
        station_m            = inp.station_m,
        road_name            = inp.road_name,
        angle_deg            = inp.angle_deg,
        kerb_return_length_m = kerb_return,
        turning_lane_length_m= turn_lane_len,
        taper_length_m       = taper_len,
        offset_left_m        = offset_l,
        offset_right_m       = offset_r,
        sight_distance_m     = ssd,
        notes                = notes,
    )


def run_design(inputs: List[IntersectionInput]) -> List[IntersectionResult]:
    return [design_intersection(inp) for inp in inputs]


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

GEOM_HEADERS = [
    "int_id", "station_m", "road_name", "angle_deg",
    "kerb_return_length_m", "turning_lane_length_m", "taper_length_m",
    "offset_left_m", "offset_right_m", "sight_distance_m", "notes",
]

OFFSET_HEADERS = [
    "int_id", "station_m", "road_name",
    "offset_left_m", "offset_right_m", "turning_lane_length_m",
]


def write_geometry(results: List[IntersectionResult], path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = _csv.writer(f)
        w.writerow(GEOM_HEADERS)
        for r in results:
            w.writerow([
                r.int_id, r.station_m, r.road_name, r.angle_deg,
                r.kerb_return_length_m, r.turning_lane_length_m, r.taper_length_m,
                r.offset_left_m, r.offset_right_m, r.sight_distance_m, r.notes,
            ])


def write_offset_inputs(results: List[IntersectionResult], path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = _csv.writer(f)
        w.writerow(OFFSET_HEADERS)
        for r in results:
            w.writerow([
                r.int_id, r.station_m, r.road_name,
                r.offset_left_m, r.offset_right_m, r.turning_lane_length_m,
            ])


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def build_summary(results: List[IntersectionResult]) -> List[str]:
    lines = ["", "INTERSECTION DESIGN SUMMARY", "-" * 72]
    hdr = f"{'ID':<8} {'STA':>8} {'Road':<16} {'KerbArc':>8} {'TurnLen':>8} {'SSD':>6} {'Notes'}"
    lines.append(hdr)
    lines.append("-" * 72)
    for r in results:
        lines.append(
            f"{r.int_id:<8} {r.station_m:>8.1f} {r.road_name:<16} "
            f"{r.kerb_return_length_m:>8.2f} {r.turning_lane_length_m:>8.1f} "
            f"{r.sight_distance_m:>6.1f}  {r.notes}"
        )
    lines.append("-" * 72)
    lines.append(f"  {len(results)} intersection(s) designed.")
    lines.append("")
    return lines


def run_pipeline(
    input_path: str,
    geom_out: str,
    offset_out: str,
) -> List[str]:
    log = [
        f"Input   : {input_path}",
        f"Geometry: {geom_out}",
        f"Offsets : {offset_out}",
        "",
    ]
    inputs  = read_inputs(input_path)
    log.append(f"Read {len(inputs)} intersection(s).")
    results = run_design(inputs)
    write_geometry(results, geom_out)
    write_offset_inputs(results, offset_out)
    log.append(f"Wrote geometry    → {geom_out}")
    log.append(f"Wrote offset data → {offset_out}")
    log.extend(build_summary(results))
    return log


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

def run_gui() -> None:
    import tkinter as tk
    from tkinter import ttk, filedialog, scrolledtext

    BG_DARK   = "#1c2030"
    BG_LIGHT  = "#f4f4f6"
    ACCENT    = "#F0A500"
    BTN_GREEN = "#1c6f44"
    FONT_BODY = ("Segoe UI", 10)
    FONT_HEAD = ("Segoe UI", 12, "bold")

    root = tk.Tk()
    root.title("Road Automation — M18 Intersection Design Calculator")
    root.minsize(820, 580)
    root.configure(bg=BG_LIGHT)

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TNotebook",     background=BG_DARK, tabmargins=[0, 0, 0, 0])
    style.configure("TNotebook.Tab", background=BG_DARK, foreground="#aaaaaa",
                    padding=[14, 6], font=FONT_BODY)
    style.map("TNotebook.Tab",
              background=[("selected", BG_LIGHT)],
              foreground=[("selected", BG_DARK)])
    for w in ("TFrame", "TLabel"):
        style.configure(w, background=BG_LIGHT, font=FONT_BODY)
    style.configure("Accent.TButton", background=BTN_GREEN, foreground="white",
                    font=("Segoe UI", 10, "bold"), padding=[10, 6])
    style.map("Accent.TButton", background=[("active", "#145230")])

    banner = tk.Frame(root, bg=BG_DARK, height=52)
    banner.pack(fill=tk.X)
    banner.pack_propagate(False)
    tk.Label(banner, text="Road Design Automation — M18  Intersection Design Calculator",
             bg=BG_DARK, fg=ACCENT, font=("Segoe UI", 13, "bold")).pack(
        side=tk.LEFT, padx=16, pady=10)

    nb = ttk.Notebook(root)
    nb.pack(fill=tk.BOTH, expand=True, padx=12, pady=(10, 4))

    in_var       = tk.StringVar()
    geom_var     = tk.StringVar(value=DEFAULT_GEOM_OUT)
    offset_var   = tk.StringVar(value=DEFAULT_OFFSET_OUT)

    # Tab 1 — Input
    t1 = ttk.Frame(nb, padding=(16, 14))
    nb.add(t1, text="Input")

    ttk.Label(t1, text="Intersections CSV", font=FONT_HEAD).grid(
        row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
    ttk.Label(t1, text="Input CSV:").grid(row=1, column=0, sticky="w")
    ttk.Entry(t1, textvariable=in_var, width=58).grid(row=1, column=1, sticky="ew", padx=(8, 8))

    preview_cols = ("int_id", "station_m", "road_name", "angle_deg", "radius_m", "speed_kph")
    preview_tree = ttk.Treeview(t1, columns=preview_cols, show="headings", height=10)
    for col, lbl, w in [
        ("int_id",    "ID",       7), ("station_m", "Sta (m)", 9),
        ("road_name", "Road",    14), ("angle_deg", "Angle°",  8),
        ("radius_m",  "Radius",   8), ("speed_kph", "Speed",   7),
    ]:
        preview_tree.heading(col, text=lbl)
        preview_tree.column(col, width=w * 10, anchor="center")
    preview_tree.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=(10, 0))
    sb = ttk.Scrollbar(t1, orient="vertical", command=preview_tree.yview)
    preview_tree.configure(yscrollcommand=sb.set)
    sb.grid(row=3, column=3, sticky="ns")
    t1.columnconfigure(1, weight=1)
    t1.rowconfigure(3, weight=1)

    def _browse():
        p = filedialog.askopenfilename(
            title="Select intersections.csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not p:
            return
        in_var.set(p)
        try:
            rows = read_inputs(p)
            preview_tree.delete(*preview_tree.get_children())
            for r in rows:
                preview_tree.insert("", "end", values=(
                    r.int_id, f"{r.station_m:.1f}", r.road_name,
                    f"{r.angle_deg:.1f}", f"{r.radius_m:.1f}",
                    f"{r.approach_speed_kph:.0f}"))
        except Exception as exc:
            preview_tree.delete(*preview_tree.get_children())
            preview_tree.insert("", "end", values=(f"ERROR: {exc}", "", "", "", "", ""))

    ttk.Button(t1, text="Browse…", command=_browse).grid(row=1, column=2)

    # Tab 2 — Results
    t2 = ttk.Frame(nb, padding=(16, 14))
    nb.add(t2, text="Results")

    ttk.Label(t2, text="Intersection Design Results", font=FONT_HEAD).grid(
        row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
    ttk.Label(t2, text="Geometry CSV:").grid(row=1, column=0, sticky="w")
    ttk.Entry(t2, textvariable=geom_var, width=50).grid(row=1, column=1, sticky="ew", padx=(8, 8))
    ttk.Button(t2, text="Browse…", command=lambda: geom_var.set(
        filedialog.asksaveasfilename(defaultextension=".csv",
            filetypes=[("CSV", "*.csv")], initialfile="intersection_geometry.csv") or geom_var.get()
    )).grid(row=1, column=2)
    ttk.Label(t2, text="Offset CSV:").grid(row=2, column=0, sticky="w", pady=(6, 0))
    ttk.Entry(t2, textvariable=offset_var, width=50).grid(row=2, column=1, sticky="ew", padx=(8, 8))
    ttk.Button(t2, text="Browse…", command=lambda: offset_var.set(
        filedialog.asksaveasfilename(defaultextension=".csv",
            filetypes=[("CSV", "*.csv")], initialfile="offset_alignment_inputs.csv") or offset_var.get()
    )).grid(row=2, column=2)

    log_txt = scrolledtext.ScrolledText(
        t2, height=16, wrap=tk.WORD, font=("Consolas", 9),
        bg="#1e1e1e", fg="#d4d4d4", insertbackground="white")
    log_txt.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=(10, 0))
    t2.columnconfigure(1, weight=1)
    t2.rowconfigure(4, weight=1)

    def _generate():
        log_txt.delete("1.0", tk.END)
        if not in_var.get() or not os.path.isfile(in_var.get()):
            log_txt.insert(tk.END, "[ERROR] Select a valid input CSV on the Input tab.\n")
            nb.select(t1)
            return
        try:
            for line in run_pipeline(in_var.get(), geom_var.get(), offset_var.get()):
                log_txt.insert(tk.END, line + "\n")
        except Exception as exc:
            log_txt.insert(tk.END, f"[ERROR] {exc}\n")
        log_txt.see(tk.END)

    ttk.Button(t2, text="Generate intersection design",
               style="Accent.TButton", command=_generate).grid(
        row=3, column=0, sticky="w", pady=(8, 0))

    root.mainloop()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def run_cli(args: list) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        prog="intersection_design.py --cli",
        description="M18 Intersection Design Calculator (CLI)")
    parser.add_argument("input_csv", help="Path to intersections.csv")
    parser.add_argument("--geom-out",   default=DEFAULT_GEOM_OUT)
    parser.add_argument("--offset-out", default=DEFAULT_OFFSET_OUT)
    parsed = parser.parse_args(args)
    try:
        for line in run_pipeline(parsed.input_csv, parsed.geom_out, parsed.offset_out):
            print(line)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] == "--cli":
        sys.exit(run_cli(argv[1:]))
    try:
        run_gui()
    except ImportError as exc:
        if "tkinter" in str(exc).lower():
            print("Tkinter unavailable — use: python intersection_design.py --cli <file>",
                  file=sys.stderr)
            sys.exit(2)
        raise


if __name__ == "__main__":
    main()
