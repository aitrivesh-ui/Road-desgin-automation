# -*- coding: utf-8 -*-
"""
Road Automation — M17  Drainage Design Calculator  (Python 3 + tkinter).

Reads catchments.csv and produces:
  drainage_design.csv   — peak flow + culvert sizing per catchment
  culvert_schedule.csv  — schedule of all culverts

Rational method for peak flow; Manning's equation for culvert capacity.

Input CSV columns:
  catch_id, name, area_ha, runoff_coeff, tc_min, rainfall_intensity_mm_h,
  outlet_station_m, invert_in_m, invert_out_m, slope_pct

Usage:
  python drainage_design.py                           GUI wizard
  python drainage_design.py --cli catchments.csv      headless
"""
from __future__ import annotations

import csv as _csv
import math
import os
import sys
from typing import NamedTuple, List, Optional

# ---------------------------------------------------------------------------
# Root / output directory convention
# ---------------------------------------------------------------------------

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class Catchment(NamedTuple):
    catch_id: str
    name: str
    area_ha: float
    runoff_coeff: float
    tc_min: float
    rainfall_intensity_mm_h: float
    outlet_station_m: float
    invert_in_m: float
    invert_out_m: float
    slope_pct: float


class DrainageResult(NamedTuple):
    catch_id: str
    name: str
    area_ha: float
    peak_flow_m3s: float
    required_culvert_dia_mm: int
    culvert_capacity_m3s: float
    hw_d_ratio: float
    design_adequate: str


class CulvertScheduleRow(NamedTuple):
    culvert_id: str
    outlet_station_m: float
    diameter_mm: int
    length_m: float
    invert_in_m: float
    invert_out_m: float
    material: str
    design_flow_m3s: float


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CULVERT_DIAMETERS_MM = [450, 600, 750, 900, 1050, 1200, 1500, 1800]
MANNING_N_CONCRETE   = 0.013
FREEBOARD_FACTOR     = 1.20   # 20 % capacity margin
CULVERT_MATERIAL     = "Concrete RCP"

DRAINAGE_HEADERS = [
    "catch_id", "name", "area_ha", "peak_flow_m3s",
    "required_culvert_dia_mm", "culvert_capacity_m3s",
    "hw_d_ratio", "design_adequate",
]
CULVERT_HEADERS = [
    "culvert_id", "outlet_station_m", "diameter_mm", "length_m",
    "invert_in_m", "invert_out_m", "material", "design_flow_m3s",
]

REQUIRED_COLS = {
    "catch_id", "name", "area_ha", "runoff_coeff", "tc_min",
    "rainfall_intensity_mm_h", "outlet_station_m",
    "invert_in_m", "invert_out_m", "slope_pct",
}


# ---------------------------------------------------------------------------
# Input reader
# ---------------------------------------------------------------------------

def read_catchments(path: str) -> List[Catchment]:
    rows: List[Catchment] = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = _csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        missing = REQUIRED_COLS - set(fieldnames)
        if missing:
            raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
        for i, row in enumerate(reader, start=2):
            try:
                rows.append(Catchment(
                    catch_id                = row["catch_id"].strip(),
                    name                    = row["name"].strip(),
                    area_ha                 = float(row["area_ha"]),
                    runoff_coeff            = float(row["runoff_coeff"]),
                    tc_min                  = float(row["tc_min"]),
                    rainfall_intensity_mm_h = float(row["rainfall_intensity_mm_h"]),
                    outlet_station_m        = float(row["outlet_station_m"]),
                    invert_in_m             = float(row["invert_in_m"]),
                    invert_out_m            = float(row["invert_out_m"]),
                    slope_pct               = float(row["slope_pct"]),
                ))
            except (ValueError, KeyError) as exc:
                raise ValueError(f"Row {i}: {exc}") from exc
    if not rows:
        raise ValueError("Input file contains no data rows.")
    return rows


# ---------------------------------------------------------------------------
# Hydraulic engine
# ---------------------------------------------------------------------------

def rational_flow(c: float, i_mm_h: float, a_ha: float) -> float:
    """Rational method: Q (m3/s) = C * I * A / 360."""
    return c * i_mm_h * a_ha / 360.0


def mannings_capacity(dia_m: float, slope_frac: float) -> float:
    """Full-pipe Manning's Q for a circular pipe (m3/s)."""
    r = dia_m / 4.0                               # hydraulic radius for full pipe
    a_pipe = math.pi * (dia_m / 2.0) ** 2
    if slope_frac <= 0.0:
        return 0.0
    return (1.0 / MANNING_N_CONCRETE) * a_pipe * r ** (2.0 / 3.0) * math.sqrt(slope_frac)


def hw_d_ratio_approx(q_design: float, dia_m: float, slope_frac: float) -> float:
    """
    Approximate HW/D for inlet control using simplified FHWA chart relationship.
    For full-pipe or below: HW/D = (Q / Q_full)^0.5 capped at 1.5 then scaled.
    """
    q_full = mannings_capacity(dia_m, slope_frac)
    if q_full <= 0.0:
        return 9.99
    ratio = q_design / q_full
    # Simplified inlet-control approximation
    hwd = 0.5 + 0.6 * ratio
    return round(min(hwd, 2.5), 3)


def size_culvert(
    q_m3s: float, slope_pct: float
) -> tuple[int, float, float]:
    """
    Return (diameter_mm, capacity_m3s, hw_d_ratio) for the smallest
    standard diameter whose capacity >= q_m3s * FREEBOARD_FACTOR.
    """
    slope_frac = slope_pct / 100.0
    q_required = q_m3s * FREEBOARD_FACTOR
    for dia_mm in CULVERT_DIAMETERS_MM:
        dia_m = dia_mm / 1000.0
        cap   = mannings_capacity(dia_m, slope_frac)
        if cap >= q_required:
            hwd = hw_d_ratio_approx(q_m3s, dia_m, slope_frac)
            return dia_mm, round(cap, 4), hwd
    # If no standard size is adequate, return largest
    dia_mm = CULVERT_DIAMETERS_MM[-1]
    dia_m  = dia_mm / 1000.0
    cap    = mannings_capacity(dia_m, slope_frac)
    hwd    = hw_d_ratio_approx(q_m3s, dia_m, slope_frac)
    return dia_mm, round(cap, 4), hwd


def design_catchment(c: Catchment, index: int) -> tuple[DrainageResult, CulvertScheduleRow]:
    q = rational_flow(c.runoff_coeff, c.rainfall_intensity_mm_h, c.area_ha)
    dia_mm, cap, hwd = size_culvert(q, c.slope_pct)

    adequate = "Yes" if (cap >= q * FREEBOARD_FACTOR and hwd <= 1.5) else "No"

    # Culvert length from invert difference and slope
    slope_frac = c.slope_pct / 100.0
    if slope_frac > 0:
        length_m = abs(c.invert_in_m - c.invert_out_m) / slope_frac
    else:
        length_m = 10.0
    length_m = max(length_m, 3.0)

    result = DrainageResult(
        catch_id                = c.catch_id,
        name                    = c.name,
        area_ha                 = c.area_ha,
        peak_flow_m3s           = round(q, 4),
        required_culvert_dia_mm = dia_mm,
        culvert_capacity_m3s    = cap,
        hw_d_ratio              = hwd,
        design_adequate         = adequate,
    )
    schedule = CulvertScheduleRow(
        culvert_id        = f"CUL-{index:03d}",
        outlet_station_m  = c.outlet_station_m,
        diameter_mm       = dia_mm,
        length_m          = round(length_m, 1),
        invert_in_m       = c.invert_in_m,
        invert_out_m      = c.invert_out_m,
        material          = CULVERT_MATERIAL,
        design_flow_m3s   = round(q, 4),
    )
    return result, schedule


def run_design(catchments: List[Catchment]):
    results:  List[DrainageResult]    = []
    schedule: List[CulvertScheduleRow] = []
    for i, c in enumerate(catchments, start=1):
        res, sched = design_catchment(c, i)
        results.append(res)
        schedule.append(sched)
    return results, schedule


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------

def write_drainage(results: List[DrainageResult], path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = _csv.writer(f)
        w.writerow(DRAINAGE_HEADERS)
        for r in results:
            w.writerow([
                r.catch_id, r.name, r.area_ha, r.peak_flow_m3s,
                r.required_culvert_dia_mm, r.culvert_capacity_m3s,
                r.hw_d_ratio, r.design_adequate,
            ])


def write_schedule(schedule: List[CulvertScheduleRow], path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = _csv.writer(f)
        w.writerow(CULVERT_HEADERS)
        for s in schedule:
            w.writerow([
                s.culvert_id, s.outlet_station_m, s.diameter_mm, s.length_m,
                s.invert_in_m, s.invert_out_m, s.material, s.design_flow_m3s,
            ])


# ---------------------------------------------------------------------------
# Summary builder
# ---------------------------------------------------------------------------

def build_summary(results: List[DrainageResult], schedule: List[CulvertScheduleRow]) -> List[str]:
    lines: List[str] = []
    header = (
        f"{'ID':<6} {'Name':<20} {'Area(ha)':>9} {'Q(m3/s)':>8} "
        f"{'Dia(mm)':>8} {'Cap(m3/s)':>10} {'HW/D':>6} {'OK?':>5}"
    )
    sep = "-" * len(header)
    lines.append("")
    lines.append("DRAINAGE DESIGN SUMMARY")
    lines.append(sep)
    lines.append(header)
    lines.append(sep)
    for r in results:
        lines.append(
            f"{r.catch_id:<6} {r.name[:20]:<20} {r.area_ha:>9.2f} "
            f"{r.peak_flow_m3s:>8.4f} {r.required_culvert_dia_mm:>8} "
            f"{r.culvert_capacity_m3s:>10.4f} {r.hw_d_ratio:>6.3f} "
            f"{r.design_adequate:>5}"
        )
    lines.append(sep)

    inadequate = [r for r in results if r.design_adequate == "No"]
    if inadequate:
        lines.append(f"  WARNING: {len(inadequate)} catchment(s) do not meet design criteria.")
    else:
        lines.append("  All catchments meet design criteria.")

    lines.append("")
    lines.append(f"CULVERT SCHEDULE  ({len(schedule)} culvert(s))")
    lines.append("-" * 60)
    for s in schedule:
        lines.append(
            f"  {s.culvert_id}  Sta:{s.outlet_station_m:.1f}m  "
            f"Dia:{s.diameter_mm}mm  L:{s.length_m:.1f}m  "
            f"Q:{s.design_flow_m3s:.4f}m3/s")
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_pipeline(input_path: str, out_dir: str) -> List[str]:
    log: List[str] = []
    drainage_path = os.path.join(out_dir, "drainage_design.csv")
    schedule_path = os.path.join(out_dir, "culvert_schedule.csv")

    log.append(f"Input          : {input_path}")
    log.append(f"Drainage output: {drainage_path}")
    log.append(f"Schedule output: {schedule_path}")
    log.append("")

    catchments = read_catchments(input_path)
    log.append(f"Read {len(catchments)} catchment(s).")

    results, schedule = run_design(catchments)

    write_drainage(results, drainage_path)
    write_schedule(schedule, schedule_path)
    log.append(f"Wrote {len(results)} drainage rows  -> {drainage_path}")
    log.append(f"Wrote {len(schedule)} culvert rows   -> {schedule_path}")

    log.extend(build_summary(results, schedule))
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
    root.title("Road Automation — M17 Drainage Design Calculator")
    root.minsize(860, 640)
    root.configure(bg=BG_LIGHT)

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TNotebook",     background=BG_DARK, tabmargins=[0, 0, 0, 0])
    style.configure("TNotebook.Tab", background=BG_DARK, foreground="#aaaaaa",
                    padding=[14, 6], font=FONT_BODY)
    style.map("TNotebook.Tab",
              background=[("selected", BG_LIGHT)],
              foreground=[("selected", BG_DARK)],
              font=[("selected", ("Segoe UI", 10, "bold"))])
    for w in ("TFrame", "TLabel", "TLabelframe"):
        style.configure(w, background=BG_LIGHT, font=FONT_BODY)
    style.configure("Accent.TButton", background=BTN_GREEN, foreground="white",
                    font=("Segoe UI", 10, "bold"), padding=[10, 6])
    style.map("Accent.TButton", background=[("active", "#145230")])

    # Banner
    banner = tk.Frame(root, bg=BG_DARK, height=52)
    banner.pack(fill=tk.X)
    banner.pack_propagate(False)
    tk.Label(banner, text="Road Design Automation — M17  Drainage Design Calculator",
             bg=BG_DARK, fg=ACCENT, font=("Segoe UI", 13, "bold")
             ).pack(side=tk.LEFT, padx=16, pady=10)

    nb = ttk.Notebook(root)
    nb.pack(fill=tk.BOTH, expand=True, padx=12, pady=(10, 4))

    in_var  = tk.StringVar()
    out_var = tk.StringVar(value=os.path.join(ROOT, "csv"))

    # ── Tab 1: Input ─────────────────────────────────────────────────────
    t1 = ttk.Frame(nb, padding=(16, 14))
    nb.add(t1, text="Input")

    ttk.Label(t1, text="Catchments CSV", font=FONT_HEAD).grid(
        row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

    ttk.Label(t1, text="Input CSV:").grid(row=1, column=0, sticky="w")
    ttk.Entry(t1, textvariable=in_var, width=58).grid(
        row=1, column=1, sticky="ew", padx=(8, 8))

    prev_tree = ttk.Treeview(t1,
        columns=("id", "name", "area", "c", "tc", "i", "sta", "slope"),
        show="headings", height=12)
    for col, lbl, w in [
        ("id",    "ID",        60),
        ("name",  "Name",     140),
        ("area",  "Area(ha)", 80),
        ("c",     "C",         55),
        ("tc",    "Tc(min)",   80),
        ("i",     "I(mm/h)",   80),
        ("sta",   "Sta(m)",    80),
        ("slope", "Slope(%)",  80),
    ]:
        prev_tree.heading(col, text=lbl)
        prev_tree.column(col, width=w, anchor="center")

    def _browse_in():
        p = filedialog.askopenfilename(
            title="Select catchments.csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not p:
            return
        in_var.set(p)
        try:
            rows = read_catchments(p)
            prev_tree.delete(*prev_tree.get_children())
            for r in rows:
                prev_tree.insert("", "end", values=(
                    r.catch_id, r.name, f"{r.area_ha:.2f}",
                    f"{r.runoff_coeff:.2f}", f"{r.tc_min:.0f}",
                    f"{r.rainfall_intensity_mm_h:.0f}",
                    f"{r.outlet_station_m:.1f}", f"{r.slope_pct:.2f}"))
        except Exception as exc:
            prev_tree.delete(*prev_tree.get_children())
            prev_tree.insert("", "end", values=(f"ERROR: {exc}", "", "", "", "", "", "", ""))

    ttk.Button(t1, text="Browse…", command=_browse_in).grid(row=1, column=2)
    prev_tree.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=(10, 0))
    sb1 = ttk.Scrollbar(t1, orient="vertical", command=prev_tree.yview)
    prev_tree.configure(yscrollcommand=sb1.set)
    sb1.grid(row=3, column=3, sticky="ns")
    t1.columnconfigure(1, weight=1)
    t1.rowconfigure(3, weight=1)

    ttk.Label(t1, text=(
        "Required columns: catch_id, name, area_ha, runoff_coeff, tc_min, "
        "rainfall_intensity_mm_h, outlet_station_m, invert_in_m, invert_out_m, slope_pct"
    ), foreground="#666666", wraplength=660, justify="left").grid(
        row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))

    # ── Tab 2: Results ───────────────────────────────────────────────────
    t2 = ttk.Frame(nb, padding=(16, 14))
    nb.add(t2, text="Results")

    ttk.Label(t2, text="Drainage Design Results", font=FONT_HEAD).grid(
        row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

    ttk.Label(t2, text="Output folder:").grid(row=1, column=0, sticky="w")
    ttk.Entry(t2, textvariable=out_var, width=58).grid(
        row=1, column=1, sticky="ew", padx=(8, 8))
    ttk.Button(t2, text="Browse…", command=lambda: out_var.set(
        filedialog.askdirectory(title="Output folder") or out_var.get()
    )).grid(row=1, column=2)

    res_tree = ttk.Treeview(t2,
        columns=("id", "name", "q", "dia", "cap", "hwd", "ok"),
        show="headings", height=8)
    for col, lbl, w in [
        ("id",   "ID",        60),
        ("name", "Name",     140),
        ("q",    "Q(m3/s)",  90),
        ("dia",  "Dia(mm)",  80),
        ("cap",  "Cap(m3/s)",90),
        ("hwd",  "HW/D",     70),
        ("ok",   "OK?",      55),
    ]:
        res_tree.heading(col, text=lbl)
        res_tree.column(col, width=w, anchor="center")
    res_tree.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=(10, 0))
    sb2 = ttk.Scrollbar(t2, orient="vertical", command=res_tree.yview)
    res_tree.configure(yscrollcommand=sb2.set)
    sb2.grid(row=3, column=3, sticky="ns")

    log_txt = scrolledtext.ScrolledText(
        t2, height=9, wrap=tk.WORD, font=("Consolas", 9),
        bg="#1e1e1e", fg="#d4d4d4", insertbackground="white")
    log_txt.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
    t2.columnconfigure(1, weight=1)
    t2.rowconfigure(3, weight=1)
    t2.rowconfigure(4, weight=1)

    def _generate():
        log_txt.delete("1.0", tk.END)
        if not in_var.get() or not os.path.isfile(in_var.get()):
            log_txt.insert(tk.END, "[ERROR] Select a valid input CSV on the Input tab.\n")
            nb.select(t1)
            return
        try:
            lines = run_pipeline(in_var.get(), out_var.get())
            for line in lines:
                log_txt.insert(tk.END, line + "\n")
            catchments = read_catchments(in_var.get())
            results, _ = run_design(catchments)
            res_tree.delete(*res_tree.get_children())
            for r in results:
                tag = "" if r.design_adequate == "Yes" else "warn"
                res_tree.insert("", "end", tag=tag, values=(
                    r.catch_id, r.name, f"{r.peak_flow_m3s:.4f}",
                    r.required_culvert_dia_mm, f"{r.culvert_capacity_m3s:.4f}",
                    f"{r.hw_d_ratio:.3f}", r.design_adequate))
            res_tree.tag_configure("warn", foreground="#cc3300")
        except Exception as exc:
            log_txt.insert(tk.END, f"[ERROR] {exc}\n")
        log_txt.see(tk.END)

    ttk.Button(t2, text="Generate drainage CSV files",
               style="Accent.TButton", command=_generate
               ).grid(row=2, column=0, sticky="w", pady=(8, 0))

    root.mainloop()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def run_cli(args: list) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        prog="drainage_design.py --cli",
        description="M17 Drainage Design Calculator (CLI mode)")
    parser.add_argument("input_csv", help="Path to catchments.csv")
    parser.add_argument("--out", default=None,
                        help="Output folder (default: <ROOT>/csv)")
    parsed = parser.parse_args(args)

    out_dir = parsed.out or os.path.join(ROOT, "csv")
    try:
        for line in run_pipeline(parsed.input_csv, out_dir):
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
            print("Tkinter unavailable — use: python drainage_design.py --cli <file>",
                  file=sys.stderr)
            sys.exit(2)
        raise


if __name__ == "__main__":
    main()
