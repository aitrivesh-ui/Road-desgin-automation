# -*- coding: utf-8 -*-
"""
Road Automation — Pipeline Launcher  (Python 3 + tkinter).

Single GUI to select and run any combination of M1–M20.

  M1–M15  run inside Civil 3D via Dynamo (m8_run_all.py).
          The launcher generates the IN[1] step-filter string and
          copies it to the clipboard — paste it into Dynamo Player.

  M16–M20 are Python 3 tools that run directly from this launcher.

Usage:
  python tools/pipeline_launcher.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk

# ---------------------------------------------------------------------------
# Module catalogue
# ---------------------------------------------------------------------------

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# (step_id, display_name, description, group)
# group: "dynamo"  → runs inside Civil 3D via m8_run_all.py  IN[1]
# group: "python3" → run directly from this launcher
MODULES = [
    ("m1",  "M1  Alignment from CSV",       "Creates Civil 3D alignment from alignment_pi.csv",              "dynamo"),
    ("m2",  "M2  Profile from CSV",          "Creates finished-grade profile from profile_pvis.csv",          "dynamo"),
    ("m3",  "M3  Corridor regions",          "Applies corridor regions from section_widths.csv",              "dynamo"),
    ("m4",  "M4  Corridor build + volumes",  "Rebuilds corridor and extracts cut/fill volumes to CSV",        "dynamo"),
    ("m5",  "M5  Signage from CSV",          "Inserts sign block references from signage_schedule.csv",       "dynamo"),
    ("m6",  "M6  Sheets helper",             "Exports alignment geometry to a sheets manifest CSV",           "dynamo"),
    ("m7",  "M7  BOQ rollup",                "Compiles Bill of Quantities from volumes + markings + signage", "dynamo"),
    ("m9",  "M9  Road markings",             "Draws solid/dashed/arrow markings along alignment",             "dynamo"),
    ("m10", "M10 Cross-section generator",   "Creates SampleLineGroup + SampleLines + SectionViews",         "dynamo"),
    ("m11", "M11 Superelevation",            "Assigns superelevation from superelevation.csv",                "dynamo"),
    ("m12", "M12 Mass haul diagram",         "Average-end-area mass haul curve on C-MASSHAUL layer",         "dynamo"),
    ("m13", "M13 Plan sheets",               "Creates paper-space plan layouts tiling the alignment",        "dynamo"),
    ("m14", "M14 Long-section sheets",       "Creates ProfileView grid in model space",                      "dynamo"),
    ("m15", "M15 Standard details",          "Imports block details from DWGs into DETAILS layout",          "dynamo"),
    ("m16", "M16 Pavement design",           "Austroads pavement thickness design (pavement_inputs.csv)",    "python3"),
    ("m17", "M17 Drainage design",           "Rational method + Manning culvert sizing (catchments.csv)",    "python3"),
    ("m18", "M18 Intersection design",       "Turning lane geometry + kerb returns (intersections.csv)",     "python3"),
    ("m19", "M19 Report generator",          "Multi-sheet Excel design report with charts (openpyxl)",       "python3"),
    ("m20", "M20 Design verifier",           "Cross-checks all outputs: OK / WARN / ERROR report",           "python3"),
    ("m21", "M21 Curve schedule",            "Validates clothoid A, K-values, SSD — curve_schedule.csv",     "python3"),
]

TOOL_SCRIPTS = {
    "m16": os.path.join(ROOT, "tools", "pavement_design.py"),
    "m17": os.path.join(ROOT, "tools", "drainage_design.py"),
    "m18": os.path.join(ROOT, "tools", "intersection_design.py"),
    "m19": os.path.join(ROOT, "tools", "report_generator.py"),
    "m20": os.path.join(ROOT, "tools", "design_verifier.py"),
    "m21": os.path.join(ROOT, "tools", "m21_curve_schedule.py"),
}

# ---------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------

BG_DARK   = "#1c2030"
BG_MID    = "#252a3a"
BG_LIGHT  = "#f4f4f6"
ACCENT    = "#F0A500"
GREEN     = "#1c6f44"
BLUE_H    = "#2563eb"
RED_ERR   = "#cc2222"
WARN_COL  = "#cc6600"
FONT_BODY = ("Segoe UI", 10)
FONT_HEAD = ("Segoe UI", 11, "bold")
FONT_MONO = ("Consolas", 9)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_project_json() -> str:
    return os.path.join(ROOT, "config", "project.json")


def _run_tool(step_id: str, project_json: str, log_widget) -> None:
    script = TOOL_SCRIPTS.get(step_id)
    if not script or not os.path.isfile(script):
        _log(log_widget, f"[ERROR]  Script not found: {script}\n", RED_ERR)
        return

    cmd = [sys.executable, script]
    if step_id in ("m19", "m20"):
        cmd.append(project_json)
    elif step_id == "m21":
        import json as _json
        try:
            with open(project_json, "r", encoding="utf-8") as _f:
                _cfg = _json.load(_f)
            _paths = _cfg.get("paths", {})
            _base  = os.path.normpath(os.path.join(os.path.dirname(project_json), ".."))
            _align = os.path.join(_base, _paths.get("alignment_pi",  "csv/alignment_pi.csv"))
            _prof  = os.path.join(_base, _paths.get("profile_pvis",  "csv/profile_pvis.csv"))
        except Exception:
            _align = os.path.join(ROOT, "csv", "alignment_pi.csv")
            _prof  = os.path.join(ROOT, "csv", "profile_pvis.csv")
        cmd += ["--cli", _align, _prof]

    _log(log_widget, f"\n▶  Running {step_id.upper()} — {script}\n", ACCENT)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.stdout:
            _log(log_widget, result.stdout)
        if result.stderr:
            _log(log_widget, result.stderr, WARN_COL)
        if result.returncode == 0:
            _log(log_widget, f"[OK]  {step_id.upper()} completed.\n", GREEN)
        else:
            _log(log_widget, f"[ERROR]  {step_id.upper()} exited with code {result.returncode}\n", RED_ERR)
    except subprocess.TimeoutExpired:
        _log(log_widget, f"[ERROR]  {step_id.upper()} timed out (120 s).\n", RED_ERR)
    except Exception as exc:
        _log(log_widget, f"[ERROR]  {step_id.upper()}: {exc}\n", RED_ERR)


def _log(widget, text: str, color: str | None = None) -> None:
    widget.configure(state="normal")
    if color:
        tag = f"col_{color.replace('#','')}"
        widget.tag_configure(tag, foreground=color)
        widget.insert(tk.END, text, tag)
    else:
        widget.insert(tk.END, text)
    widget.see(tk.END)
    widget.configure(state="disabled")


# ---------------------------------------------------------------------------
# Main GUI
# ---------------------------------------------------------------------------

def run_gui() -> None:
    root = tk.Tk()
    root.title("Road Design Automation — Pipeline Launcher")
    root.minsize(900, 700)
    root.configure(bg=BG_LIGHT)

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TNotebook",     background=BG_DARK, tabmargins=[0, 0, 0, 0])
    style.configure("TNotebook.Tab", background=BG_DARK, foreground="#aaaaaa",
                    padding=[16, 7], font=FONT_BODY)
    style.map("TNotebook.Tab",
              background=[("selected", BG_LIGHT)],
              foreground=[("selected", BG_DARK)],
              font=[("selected", ("Segoe UI", 10, "bold"))])
    for w in ("TFrame", "TLabel", "TLabelframe"):
        style.configure(w, background=BG_LIGHT, font=FONT_BODY)
    style.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"))
    style.configure("TCheckbutton", background=BG_LIGHT, font=FONT_BODY)
    style.configure("Green.TButton", background=GREEN, foreground="white",
                    font=("Segoe UI", 10, "bold"), padding=[12, 6])
    style.map("Green.TButton", background=[("active", "#145230")])
    style.configure("Blue.TButton", background=BLUE_H, foreground="white",
                    font=("Segoe UI", 10, "bold"), padding=[12, 6])
    style.map("Blue.TButton", background=[("active", "#1d4ed8")])
    style.configure("Dark.TButton", background=BG_MID, foreground="white",
                    font=("Segoe UI", 9), padding=[8, 4])
    style.map("Dark.TButton", background=[("active", "#333a50")])

    # ── Banner ──────────────────────────────────────────────────────────────
    banner = tk.Frame(root, bg=BG_DARK, height=56)
    banner.pack(fill=tk.X)
    banner.pack_propagate(False)
    tk.Label(banner, text="Road Design Automation — Pipeline Launcher  M1 → M20",
             bg=BG_DARK, fg=ACCENT, font=("Segoe UI", 14, "bold")).pack(
        side=tk.LEFT, padx=18, pady=12)

    nb = ttk.Notebook(root)
    nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=(8, 0))

    # ── Shared state ────────────────────────────────────────────────────────
    proj_var  = tk.StringVar(value=_default_project_json())
    check_vars: dict[str, tk.BooleanVar] = {
        mid: tk.BooleanVar(value=True) for mid, *_ in MODULES
    }

    # ====================================================================
    # TAB 1 — Select modules
    # ====================================================================
    t1 = ttk.Frame(nb, padding=(14, 12))
    nb.add(t1, text="  Select Modules  ")

    # Project JSON row
    pj_frame = ttk.Frame(t1)
    pj_frame.pack(fill=tk.X, pady=(0, 10))
    ttk.Label(pj_frame, text="project.json:").pack(side=tk.LEFT)
    ttk.Entry(pj_frame, textvariable=proj_var, width=62).pack(
        side=tk.LEFT, padx=(8, 6))
    ttk.Button(pj_frame, text="Browse…", style="Dark.TButton",
               command=lambda: proj_var.set(
                   filedialog.askopenfilename(
                       title="Select project.json",
                       filetypes=[("JSON", "*.json"), ("All", "*.*")],
                   ) or proj_var.get()
               )).pack(side=tk.LEFT)

    # Two-column checklist
    cols_frame = ttk.Frame(t1)
    cols_frame.pack(fill=tk.BOTH, expand=True)

    dynamo_mods  = [(mid, name, desc) for mid, name, desc, grp in MODULES if grp == "dynamo"]
    python3_mods = [(mid, name, desc) for mid, name, desc, grp in MODULES if grp == "python3"]

    def _section(parent, title, color, mods, col):
        lf = tk.LabelFrame(parent, text=f"  {title}  ",
                           bg=BG_LIGHT, fg=color,
                           font=("Segoe UI", 10, "bold"),
                           relief="groove", bd=2)
        lf.grid(row=0, column=col, sticky="nsew", padx=(0 if col else 0, 8 if col == 0 else 0))
        for mid, name, desc in mods:
            row = ttk.Frame(lf)
            row.pack(fill=tk.X, padx=8, pady=2)
            cb = ttk.Checkbutton(row, variable=check_vars[mid])
            cb.pack(side=tk.LEFT)
            tk.Label(row, text=name, font=("Segoe UI", 10, "bold"),
                     bg=BG_LIGHT, anchor="w", width=24).pack(side=tk.LEFT)
            tk.Label(row, text=desc, font=("Segoe UI", 9),
                     fg="#555555", bg=BG_LIGHT, anchor="w").pack(side=tk.LEFT, padx=(6, 0))

    _section(cols_frame,
             "Civil 3D / Dynamo  (M1–M15)  — run via m8_run_all.py",
             "#2563eb", dynamo_mods, 0)
    _section(cols_frame,
             "Python 3 tools  (M16–M20)  — run directly",
             GREEN, python3_mods, 1)
    cols_frame.columnconfigure(0, weight=3)
    cols_frame.columnconfigure(1, weight=2)

    # Select all / none buttons
    btn_row = ttk.Frame(t1)
    btn_row.pack(fill=tk.X, pady=(8, 4))
    def _all(v):
        for bv in check_vars.values():
            bv.set(v)
    def _group(group, v):
        for mid, _, _, grp in MODULES:
            if grp == group:
                check_vars[mid].set(v)

    ttk.Button(btn_row, text="Select all",        style="Dark.TButton",
               command=lambda: _all(True)).pack(side=tk.LEFT, padx=(0, 4))
    ttk.Button(btn_row, text="Clear all",         style="Dark.TButton",
               command=lambda: _all(False)).pack(side=tk.LEFT, padx=(0, 10))
    ttk.Button(btn_row, text="Civil 3D only",     style="Dark.TButton",
               command=lambda: [_all(False), _group("dynamo",  True)]).pack(side=tk.LEFT, padx=(0, 4))
    ttk.Button(btn_row, text="Python tools only", style="Dark.TButton",
               command=lambda: [_all(False), _group("python3", True)]).pack(side=tk.LEFT)

    # ---- Sheet Options (collapsible) -----------------------------------
    _sheet_expanded = tk.BooleanVar(value=False)
    _sheet_lf_ref: list = []

    def _toggle_sheet_options():
        if _sheet_expanded.get():
            _sheet_expanded.set(False)
            toggle_btn.configure(text="▶  Sheet Options (station range / sheet cap)")
            if _sheet_lf_ref:
                _sheet_lf_ref[0].pack_forget()
        else:
            _sheet_expanded.set(True)
            toggle_btn.configure(text="▼  Sheet Options (station range / sheet cap)")
            if _sheet_lf_ref:
                _sheet_lf_ref[0].pack(fill=tk.X, pady=(4, 0))

    toggle_btn = ttk.Button(t1, text="▶  Sheet Options (station range / sheet cap)",
                            style="Dark.TButton", command=_toggle_sheet_options)
    toggle_btn.pack(anchor="w", pady=(6, 0))

    sheet_lf = tk.LabelFrame(t1, text="  Sheet Options  ",
                             bg=BG_LIGHT, font=("Segoe UI", 9, "bold"),
                             relief="groove", bd=1)
    _sheet_lf_ref.append(sheet_lf)

    _sta_start_var  = tk.StringVar(value="")
    _sta_end_var    = tk.StringVar(value="")
    _max_plan_var   = tk.StringVar(value="")
    _max_ls_var     = tk.StringVar(value="")

    def _sopt_row(parent, label, var, hint):
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, padx=8, pady=3)
        ttk.Label(row, text=label, width=22, anchor="w").pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=var, width=14).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Label(row, text=hint, foreground="#777777", font=("Segoe UI", 8)).pack(side=tk.LEFT)

    _sopt_row(sheet_lf, "Start station (m):",       _sta_start_var, "override alignment start  (blank = use full alignment)")
    _sopt_row(sheet_lf, "End station (m):",          _sta_end_var,   "override alignment end    (blank = use full alignment)")
    _sopt_row(sheet_lf, "Max plan sheets:",           _max_plan_var,  "cap number of M13 plan layouts created  (blank = no cap)")
    _sopt_row(sheet_lf, "Max long-section sheets:",   _max_ls_var,    "cap number of M14 long-section layouts  (blank = no cap)")

    def _write_sheet_opts():
        import json as _json
        pj = proj_var.get()
        if not os.path.isfile(pj):
            return
        try:
            with open(pj, "r", encoding="utf-8") as _f:
                _cfg = _json.load(_f)
        except Exception:
            return
        design = _cfg.setdefault("design", {})

        def _set_or_null(key, sv):
            val = sv.get().strip()
            design[key] = float(val) if val else None

        _set_or_null("station_range_start",   _sta_start_var)
        _set_or_null("station_range_end",      _sta_end_var)
        _set_or_null("max_sheets_plan",        _max_plan_var)
        _set_or_null("max_sheets_longsection", _max_ls_var)

        with open(pj, "w", encoding="utf-8") as _f:
            _json.dump(_cfg, _f, indent=2)
        apply_btn.configure(text="Written ✓")
        sheet_lf.after(1800, lambda: apply_btn.configure(text="Write to project.json"))

    def _clear_sheet_opts():
        for v in (_sta_start_var, _sta_end_var, _max_plan_var, _max_ls_var):
            v.set("")

    so_btn_row = ttk.Frame(sheet_lf)
    so_btn_row.pack(fill=tk.X, padx=8, pady=(4, 6))
    apply_btn = ttk.Button(so_btn_row, text="Write to project.json",
                           style="Blue.TButton", command=_write_sheet_opts)
    apply_btn.pack(side=tk.LEFT, padx=(0, 8))
    ttk.Button(so_btn_row, text="Clear", style="Dark.TButton",
               command=_clear_sheet_opts).pack(side=tk.LEFT)
    ttk.Label(so_btn_row, text="Writes values directly into the project.json design section.",
              foreground="#666666", font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(12, 0))

    # ====================================================================
    # TAB 2 — Dynamo step filter (M1-M15)
    # ====================================================================
    t2 = ttk.Frame(nb, padding=(14, 12))
    nb.add(t2, text="  Dynamo (M1–M15)  ")

    ttk.Label(t2, text="Dynamo step filter  —  paste into m8_run_all.py  IN[1]",
              font=FONT_HEAD).pack(anchor="w", pady=(0, 6))

    filter_var = tk.StringVar()

    def _update_filter(*_):
        selected = [mid for mid, _, _, grp in MODULES
                    if grp == "dynamo" and check_vars[mid].get()]
        filter_var.set(",".join(selected) if selected else "(none selected)")

    for bv in check_vars.values():
        bv.trace_add("write", _update_filter)
    _update_filter()

    filter_box = ttk.Frame(t2)
    filter_box.pack(fill=tk.X, pady=(0, 8))
    filter_entry = tk.Entry(filter_box, textvariable=filter_var,
                            font=("Consolas", 11), bg="#f0f4e8",
                            relief="solid", bd=1, state="readonly")
    filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6)

    def _copy():
        root.clipboard_clear()
        root.clipboard_append(filter_var.get())
        copy_btn.configure(text="Copied ✓")
        root.after(1800, lambda: copy_btn.configure(text="Copy to clipboard"))

    copy_btn = ttk.Button(filter_box, text="Copy to clipboard",
                          style="Blue.TButton", command=_copy)
    copy_btn.pack(side=tk.LEFT, padx=(8, 0))

    instructions = (
        "HOW TO USE\n\n"
        "1.  Open your Civil 3D project drawing (.dwg).\n"
        "2.  In Dynamo Player, set  IN[0]  to the full path of config/project.json.\n"
        "3.  Set  IN[1]  to the step filter string above (or leave blank to run all).\n"
        "4.  Run  m8_run_all.py  in Dynamo Player.\n\n"
        "Step filter examples:\n"
        "  m1,m2,m3          — run alignment, profile, corridor only\n"
        "  m4                — rebuild volumes only\n"
        "  m9,m10,m11        — road markings, sections, superelevation\n"
        "  (blank / default) — run all M1–M15 in order\n\n"
        "TIP: Run M1–M4 first (geometry build), then M5–M15 (output generation).\n"
        "After the Dynamo run, switch to the Python 3 Tools tab to run M16–M20."
    )
    info_txt = tk.Text(t2, font=FONT_MONO, wrap=tk.WORD,
                       bg="#f7f8fc", relief="flat", bd=0,
                       height=14, state="normal")
    info_txt.insert(tk.END, instructions)
    info_txt.configure(state="disabled")
    info_txt.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

    # ====================================================================
    # TAB 3 — Run Python 3 tools (M16-M20)
    # ====================================================================
    t3 = ttk.Frame(nb, padding=(14, 12))
    nb.add(t3, text="  Python Tools (M16–M20)  ")

    ttk.Label(t3, text="Run Python 3 tools directly — M16 to M20",
              font=FONT_HEAD).pack(anchor="w", pady=(0, 8))

    # Status indicators per tool
    status_vars: dict[str, tk.StringVar] = {
        mid: tk.StringVar(value="waiting") for mid, _, _, grp in MODULES if grp == "python3"
    }
    status_labels: dict[str, tk.Label] = {}

    tool_frame = ttk.Frame(t3)
    tool_frame.pack(fill=tk.X, pady=(0, 8))
    for i, (mid, name, desc, grp) in enumerate(m for m in MODULES if m[3] == "python3"):
        row = tk.Frame(tool_frame, bg=BG_LIGHT)
        row.grid(row=i, column=0, sticky="ew", pady=3)
        tool_frame.columnconfigure(0, weight=1)

        cb = ttk.Checkbutton(row, variable=check_vars[mid])
        cb.pack(side=tk.LEFT)
        tk.Label(row, text=name, font=("Segoe UI", 10, "bold"),
                 bg=BG_LIGHT, width=20, anchor="w").pack(side=tk.LEFT)
        tk.Label(row, text=desc, font=("Segoe UI", 9),
                 fg="#555555", bg=BG_LIGHT, anchor="w").pack(side=tk.LEFT, padx=(6, 20))
        lbl = tk.Label(row, textvariable=status_vars[mid],
                       font=("Segoe UI", 9, "bold"), bg=BG_LIGHT, fg="#888888", width=10)
        lbl.pack(side=tk.RIGHT)
        status_labels[mid] = lbl

    # Log area
    log_txt = scrolledtext.ScrolledText(
        t3, height=16, wrap=tk.WORD, font=FONT_MONO,
        bg="#1e1e1e", fg="#d4d4d4", insertbackground="white",
        state="disabled")
    log_txt.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

    def _set_status(mid: str, status: str) -> None:
        colours = {"waiting": "#888888", "running": ACCENT,
                   "done": GREEN, "error": RED_ERR, "skipped": "#888888"}
        status_vars[mid].set(status)
        status_labels[mid].configure(fg=colours.get(status, "#888888"))

    def _run_selected() -> None:
        selected_py3 = [mid for mid, _, _, grp in MODULES
                        if grp == "python3" and check_vars[mid].get()]
        if not selected_py3:
            _log(log_txt, "[WARN]  No Python 3 tools selected.\n", WARN_COL)
            return

        proj = proj_var.get().strip()
        if not os.path.isfile(proj):
            _log(log_txt, f"[ERROR]  project.json not found: {proj}\n", RED_ERR)
            return

        run_btn.configure(state="disabled")
        _log(log_txt, f"project.json: {proj}\n", ACCENT)

        def _worker():
            for mid in selected_py3:
                _set_status(mid, "running")
                _run_tool(mid, proj, log_txt)
                # Check last log line for error
                content = log_txt.get("1.0", tk.END)
                last_lines = content.strip().splitlines()
                last = last_lines[-1] if last_lines else ""
                if "[ERROR]" in last or "ERROR" in last:
                    _set_status(mid, "error")
                else:
                    _set_status(mid, "done")

            _log(log_txt, "\nAll selected tools finished.\n", GREEN)
            run_btn.configure(state="normal")

        threading.Thread(target=_worker, daemon=True).start()

    run_btn = ttk.Button(t3, text="Run selected Python 3 tools  (M16–M20)",
                         style="Green.TButton", command=_run_selected)
    run_btn.pack(side=tk.LEFT, pady=(8, 0))

    ttk.Button(t3, text="Clear log", style="Dark.TButton",
               command=lambda: [log_txt.configure(state="normal"),
                                log_txt.delete("1.0", tk.END),
                                log_txt.configure(state="disabled")]
               ).pack(side=tk.LEFT, padx=(8, 0), pady=(8, 0))

    # ====================================================================
    # Status bar
    # ====================================================================
    statusbar = tk.Frame(root, bg=BG_DARK, height=26)
    statusbar.pack(fill=tk.X, side=tk.BOTTOM)
    statusbar.pack_propagate(False)
    sb_lbl = tk.Label(statusbar, text="", bg=BG_DARK, fg="#aaaaaa",
                      font=("Segoe UI", 9))
    sb_lbl.pack(side=tk.LEFT, padx=12, pady=4)

    def _update_statusbar(*_):
        dynamo_sel  = sum(1 for mid, _, _, g in MODULES if g == "dynamo"  and check_vars[mid].get())
        python3_sel = sum(1 for mid, _, _, g in MODULES if g == "python3" and check_vars[mid].get())
        sb_lbl.configure(
            text=f"{dynamo_sel} Dynamo step(s) + {python3_sel} Python tool(s) selected   |   "
                 f"project: {os.path.basename(proj_var.get())}"
        )

    for bv in check_vars.values():
        bv.trace_add("write", _update_statusbar)
    proj_var.trace_add("write", _update_statusbar)
    _update_statusbar()

    root.mainloop()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        run_gui()
    except ImportError as exc:
        if "tkinter" in str(exc).lower():
            print("Tkinter not available — install python3-tk.", file=sys.stderr)
            sys.exit(2)
        raise


if __name__ == "__main__":
    main()
