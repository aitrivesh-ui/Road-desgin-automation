# -*- coding: utf-8 -*-
"""
Road Automation — M16  Pavement Design Calculator  (Python 3 + tkinter).

Reads pavement_inputs.csv and produces pavement_design.csv using a
simplified Austroads-inspired empirical method.

Input CSV columns:
  region_id, start_sta, end_sta, traffic_esa_million, subgrade_cbr, design_life_years

Output CSV:
  pavement_design.csv

Usage:
  python pavement_design.py                                     GUI wizard
  python pavement_design.py --cli pavement_inputs.csv           headless
  python pavement_design.py --cli pavement_inputs.csv \\
      --out out/pavement_design.csv
"""
from __future__ import annotations

import csv as _csv
import math
import os
import sys
from typing import NamedTuple, List

# ---------------------------------------------------------------------------
# Root / output directory convention
# ---------------------------------------------------------------------------

ROOT = (os.environ.get("ROAD_ROOT") or
        os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class PavementInput(NamedTuple):
    region_id: str
    start_sta: float
    end_sta: float
    traffic_esa_million: float
    subgrade_cbr: float
    design_life_years: float


class PavementResult(NamedTuple):
    region_id: str
    start_sta: float
    end_sta: float
    total_thickness_mm: float
    wearing_course_mm: float
    base_mm: float
    subbase_mm: float
    base_material: str
    subbase_material: str
    design_cbr: float
    design_esa_million: float


# ---------------------------------------------------------------------------
# Input reader
# ---------------------------------------------------------------------------

REQUIRED_COLS = {
    "region_id", "start_sta", "end_sta",
    "traffic_esa_million", "subgrade_cbr", "design_life_years",
}

OUTPUT_HEADERS = [
    "region_id", "start_sta", "end_sta", "total_thickness_mm",
    "wearing_course_mm", "base_mm", "subbase_mm",
    "base_material", "subbase_material",
    "design_cbr", "design_esa_million",
]


def read_inputs(path: str) -> List[PavementInput]:
    """Read pavement_inputs.csv and return a list of PavementInput records."""
    rows: List[PavementInput] = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = _csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        missing = REQUIRED_COLS - set(fieldnames)
        if missing:
            raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
        for i, row in enumerate(reader, start=2):
            try:
                rows.append(PavementInput(
                    region_id           = row["region_id"].strip(),
                    start_sta           = float(row["start_sta"]),
                    end_sta             = float(row["end_sta"]),
                    traffic_esa_million = float(row["traffic_esa_million"]),
                    subgrade_cbr        = float(row["subgrade_cbr"]),
                    design_life_years   = float(row["design_life_years"]),
                ))
            except (ValueError, KeyError) as exc:
                raise ValueError(f"Row {i}: {exc}") from exc
    if not rows:
        raise ValueError("Input file contains no data rows.")
    return rows


# ---------------------------------------------------------------------------
# Pavement design engine  (simplified Austroads empirical method)
# ---------------------------------------------------------------------------

def _material_selection(cbr: float):
    """Return (base_material, subbase_material) based on subgrade CBR."""
    if cbr >= 10.0:
        return "Crushed Rock", "Gravel"
    if cbr >= 5.0:
        return "Crushed Rock", "Imported Fill"
    return "Crushed Rock", "Select Fill"


def design_pavement(inp: PavementInput) -> PavementResult:
    """Apply empirical thickness formula and layer split."""
    cbr = inp.subgrade_cbr
    esa = inp.traffic_esa_million

    # Total structural thickness (mm)
    # Simplified Austroads-inspired: T = 150 + 75*log10(ESA+1) + 300/CBR
    t_total = 150.0 + 75.0 * math.log10(esa + 1.0) + 300.0 / cbr

    # Layer split
    wearing_course_mm = 40.0
    base_mm           = min(200.0, t_total * 0.45)
    subbase_mm        = t_total - wearing_course_mm - base_mm

    # Apply minimums
    base_mm    = max(100.0, base_mm)
    subbase_mm = max(100.0, subbase_mm)

    # Recalculate total with minimums applied
    t_total = wearing_course_mm + base_mm + subbase_mm

    base_mat, subbase_mat = _material_selection(cbr)

    return PavementResult(
        region_id          = inp.region_id,
        start_sta          = inp.start_sta,
        end_sta            = inp.end_sta,
        total_thickness_mm = round(t_total, 1),
        wearing_course_mm  = round(wearing_course_mm, 1),
        base_mm            = round(base_mm, 1),
        subbase_mm         = round(subbase_mm, 1),
        base_material      = base_mat,
        subbase_material   = subbase_mat,
        design_cbr         = inp.subgrade_cbr,
        design_esa_million = inp.traffic_esa_million,
    )


def run_design(inputs: List[PavementInput]) -> List[PavementResult]:
    return [design_pavement(inp) for inp in inputs]


# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------

def write_results(results: List[PavementResult], path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = _csv.writer(f)
        w.writerow(OUTPUT_HEADERS)
        for r in results:
            w.writerow([
                r.region_id, r.start_sta, r.end_sta, r.total_thickness_mm,
                r.wearing_course_mm, r.base_mm, r.subbase_mm,
                r.base_material, r.subbase_material,
                r.design_cbr, r.design_esa_million,
            ])


# ---------------------------------------------------------------------------
# Summary table builder (console + GUI log)
# ---------------------------------------------------------------------------

def build_summary(results: List[PavementResult]) -> List[str]:
    lines: List[str] = []
    header = (
        f"{'Region':<8} {'Start':>10} {'End':>10} {'Total(mm)':>10} "
        f"{'Wear(mm)':>9} {'Base(mm)':>9} {'Sub(mm)':>8} "
        f"{'Base Mat':<14} {'Subbase Mat':<14}"
    )
    sep = "-" * len(header)
    lines.append("")
    lines.append("PAVEMENT DESIGN SUMMARY")
    lines.append(sep)
    lines.append(header)
    lines.append(sep)
    for r in results:
        lines.append(
            f"{r.region_id:<8} {r.start_sta:>10.1f} {r.end_sta:>10.1f} "
            f"{r.total_thickness_mm:>10.1f} {r.wearing_course_mm:>9.1f} "
            f"{r.base_mm:>9.1f} {r.subbase_mm:>8.1f} "
            f"{r.base_material:<14} {r.subbase_material:<14}"
        )
    lines.append(sep)
    lines.append(f"  {len(results)} region(s) designed.")
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_pipeline(input_path: str, output_path: str) -> List[str]:
    log: List[str] = []
    log.append(f"Input  : {input_path}")
    log.append(f"Output : {output_path}")
    log.append("")

    inputs  = read_inputs(input_path)
    log.append(f"Read {len(inputs)} region(s) from input file.")

    results = run_design(inputs)
    write_results(results, output_path)
    log.append(f"Wrote {len(results)} result row(s) -> {output_path}")

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
    root.title("Road Automation — M16 Pavement Design Calculator")
    root.minsize(820, 620)
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
    style.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"))
    style.configure("Accent.TButton", background=BTN_GREEN, foreground="white",
                    font=("Segoe UI", 10, "bold"), padding=[10, 6])
    style.map("Accent.TButton", background=[("active", "#145230")])

    # Banner
    banner = tk.Frame(root, bg=BG_DARK, height=52)
    banner.pack(fill=tk.X)
    banner.pack_propagate(False)
    tk.Label(banner, text="Road Design Automation — M16  Pavement Design Calculator",
             bg=BG_DARK, fg=ACCENT, font=("Segoe UI", 13, "bold")
             ).pack(side=tk.LEFT, padx=16, pady=10)

    nb = ttk.Notebook(root)
    nb.pack(fill=tk.BOTH, expand=True, padx=12, pady=(10, 4))

    # Shared state
    in_var  = tk.StringVar()
    out_var = tk.StringVar(value=os.path.join(ROOT, "csv", "pavement_design.csv"))

    # ── Tab 1: Input ─────────────────────────────────────────────────────
    t1 = ttk.Frame(nb, padding=(16, 14))
    nb.add(t1, text="Input")

    ttk.Label(t1, text="Pavement Inputs CSV", font=FONT_HEAD).grid(
        row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

    ttk.Label(t1, text="Input CSV:").grid(row=1, column=0, sticky="w")
    ttk.Entry(t1, textvariable=in_var, width=58).grid(
        row=1, column=1, sticky="ew", padx=(8, 8))

    preview_tree = ttk.Treeview(t1,
        columns=("region_id", "start_sta", "end_sta", "esa", "cbr", "life"),
        show="headings", height=12)
    for col, lbl, w in [
        ("region_id", "Region",     80),
        ("start_sta", "Start Sta", 100),
        ("end_sta",   "End Sta",   100),
        ("esa",       "ESA (M)",   100),
        ("cbr",       "CBR",        80),
        ("life",      "Life (yr)", 100),
    ]:
        preview_tree.heading(col, text=lbl)
        preview_tree.column(col, width=w, anchor="center")

    def _browse_in():
        p = filedialog.askopenfilename(
            title="Select pavement_inputs.csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not p:
            return
        in_var.set(p)
        try:
            rows = read_inputs(p)
            preview_tree.delete(*preview_tree.get_children())
            for r in rows:
                preview_tree.insert("", "end", values=(
                    r.region_id, f"{r.start_sta:.1f}", f"{r.end_sta:.1f}",
                    f"{r.traffic_esa_million:.2f}", f"{r.subgrade_cbr:.1f}",
                    f"{r.design_life_years:.0f}"))
        except Exception as exc:
            preview_tree.delete(*preview_tree.get_children())
            preview_tree.insert("", "end", values=(f"ERROR: {exc}", "", "", "", "", ""))

    ttk.Button(t1, text="Browse…", command=_browse_in).grid(row=1, column=2)
    preview_tree.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=(10, 0))
    sb1 = ttk.Scrollbar(t1, orient="vertical", command=preview_tree.yview)
    preview_tree.configure(yscrollcommand=sb1.set)
    sb1.grid(row=3, column=3, sticky="ns")
    t1.columnconfigure(1, weight=1)
    t1.rowconfigure(3, weight=1)

    ttk.Label(t1, text=(
        "Required columns: region_id, start_sta, end_sta, "
        "traffic_esa_million, subgrade_cbr, design_life_years"
    ), foreground="#666666", wraplength=620, justify="left").grid(
        row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))

    # ── Tab 2: Results ───────────────────────────────────────────────────
    t2 = ttk.Frame(nb, padding=(16, 14))
    nb.add(t2, text="Results")

    ttk.Label(t2, text="Pavement Design Results", font=FONT_HEAD).grid(
        row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

    ttk.Label(t2, text="Output CSV:").grid(row=1, column=0, sticky="w")
    ttk.Entry(t2, textvariable=out_var, width=58).grid(
        row=1, column=1, sticky="ew", padx=(8, 8))
    ttk.Button(t2, text="Browse…", command=lambda: out_var.set(
        filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="pavement_design.csv") or out_var.get()
    )).grid(row=1, column=2)

    res_tree = ttk.Treeview(t2,
        columns=("region_id", "start_sta", "end_sta", "total", "wearing",
                 "base", "subbase", "base_mat", "sub_mat"),
        show="headings", height=9)
    for col, lbl, w in [
        ("region_id", "Region",      70),
        ("start_sta", "Start",       90),
        ("end_sta",   "End",         90),
        ("total",     "Total (mm)", 90),
        ("wearing",   "Wear (mm)",  90),
        ("base",      "Base (mm)",  90),
        ("subbase",   "Sub (mm)",   90),
        ("base_mat",  "Base Mat",  120),
        ("sub_mat",   "Subbase Mat",120),
    ]:
        res_tree.heading(col, text=lbl)
        res_tree.column(col, width=w, anchor="center")

    res_tree.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=(10, 0))
    sb2 = ttk.Scrollbar(t2, orient="vertical", command=res_tree.yview)
    res_tree.configure(yscrollcommand=sb2.set)
    sb2.grid(row=3, column=3, sticky="ns")

    log_txt = scrolledtext.ScrolledText(
        t2, height=8, wrap=tk.WORD, font=("Consolas", 9),
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
            results = run_design(read_inputs(in_var.get()))
            res_tree.delete(*res_tree.get_children())
            for r in results:
                res_tree.insert("", "end", values=(
                    r.region_id, f"{r.start_sta:.1f}", f"{r.end_sta:.1f}",
                    f"{r.total_thickness_mm:.1f}", f"{r.wearing_course_mm:.1f}",
                    f"{r.base_mm:.1f}", f"{r.subbase_mm:.1f}",
                    r.base_material, r.subbase_material))
        except Exception as exc:
            log_txt.insert(tk.END, f"[ERROR] {exc}\n")
        log_txt.see(tk.END)

    ttk.Button(t2, text="Generate pavement_design.csv",
               style="Accent.TButton", command=_generate
               ).grid(row=2, column=0, sticky="w", pady=(8, 0))

    root.mainloop()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def run_cli(args: list) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        prog="pavement_design.py --cli",
        description="M16 Pavement Design Calculator (CLI mode)")
    parser.add_argument("input_csv", help="Path to pavement_inputs.csv")
    parser.add_argument("--out", default=None,
                        help="Output CSV path (default: <ROOT>/csv/pavement_design.csv)")
    parsed = parser.parse_args(args)

    out_path = parsed.out or os.path.join(ROOT, "csv", "pavement_design.csv")
    try:
        for line in run_pipeline(parsed.input_csv, out_path):
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
            print("Tkinter unavailable — use: python pavement_design.py --cli <file>",
                  file=sys.stderr)
            sys.exit(2)
        raise


if __name__ == "__main__":
    main()
