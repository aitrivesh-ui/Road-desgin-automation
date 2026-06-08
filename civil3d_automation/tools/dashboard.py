"""
dashboard.py — M16-M20 Road Design Tools Dashboard
Run: python tools/dashboard.py
"""

import os
import sys
import json
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
TOOLS_DIR   = os.path.dirname(os.path.abspath(__file__))
ROOT        = os.path.dirname(TOOLS_DIR)
DEFAULT_CFG = os.path.join(ROOT, "config", "project.json")

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
BG_DARK   = "#1c2030"
BG_MID    = "#252a3a"
BG_PANEL  = "#2e3449"
FG_WHITE  = "#f0f0f0"
FG_DIM    = "#9098b0"
AMBER     = "#F0A500"
GREEN     = "#28a745"
RED       = "#dc3545"
YELLOW    = "#ffc107"
BLUE      = "#4a90d9"
MONO_FONT = ("Consolas", 9) if sys.platform == "win32" else ("Courier New", 9)

STATUS_COLOURS = {
    "idle":    (FG_DIM,   "—"),
    "running": (YELLOW,   "Running…"),
    "ok":      (GREEN,    "Done ✓"),
    "error":   (RED,      "Failed ✗"),
}

# ---------------------------------------------------------------------------
# Helper — open file/folder in OS file manager
# ---------------------------------------------------------------------------
def _open_path(path: str) -> None:
    if not path or not os.path.exists(path):
        return
    target = path if os.path.isfile(path) else os.path.dirname(path)
    if sys.platform == "win32":
        os.startfile(target)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(["xdg-open", target])


# ---------------------------------------------------------------------------
# ToolPanel — reusable tab component
# ---------------------------------------------------------------------------
class ToolPanel(ttk.Frame):
    """One tab for a single M16-M20 tool."""

    def __init__(self, parent, module: str, description: str, colour: str = BLUE):
        super().__init__(parent)
        self.configure(style="Dark.TFrame")
        self._proc   = None
        self._queue  = queue.Queue()
        self._output_path = ""   # set by subclass before calling run()
        self._build_header(module, description, colour)
        self._log_var = None     # set by _build_log

    # ---- chrome --------------------------------------------------------

    def _build_header(self, module: str, description: str, colour: str) -> None:
        hdr = tk.Frame(self, bg=BG_MID, pady=8)
        hdr.pack(fill="x")
        badge = tk.Label(hdr, text=module, bg=colour, fg="white",
                         font=("Segoe UI", 11, "bold"), padx=10, pady=2)
        badge.pack(side="left", padx=(14, 10))
        tk.Label(hdr, text=description, bg=BG_MID, fg=FG_WHITE,
                 font=("Segoe UI", 11)).pack(side="left")
        # status badge on right
        self._status_lbl = tk.Label(hdr, text="—", bg=BG_MID, fg=FG_DIM,
                                    font=("Segoe UI", 10, "bold"), padx=12)
        self._status_lbl.pack(side="right")

    def _build_log(self, parent: tk.Widget) -> scrolledtext.ScrolledText:
        log = scrolledtext.ScrolledText(parent, bg=BG_DARK, fg=FG_WHITE,
                                        font=MONO_FONT, wrap="word",
                                        relief="flat", bd=0, height=14)
        log.tag_configure("ok",    foreground=GREEN)
        log.tag_configure("warn",  foreground=YELLOW)
        log.tag_configure("error", foreground=RED)
        log.tag_configure("info",  foreground=AMBER)
        log.configure(state="disabled")
        self._log_var = log
        return log

    def _row(self, parent: tk.Widget, label: str, var: tk.StringVar,
             browse_cb=None, readonly: bool = False) -> ttk.Entry:
        row = tk.Frame(parent, bg=BG_PANEL)
        row.pack(fill="x", padx=14, pady=3)
        tk.Label(row, text=label, bg=BG_PANEL, fg=FG_DIM,
                 width=18, anchor="w",
                 font=("Segoe UI", 9)).pack(side="left")
        state = "readonly" if readonly else "normal"
        ent = ttk.Entry(row, textvariable=var, width=55, style="Path.TEntry")
        ent.pack(side="left", padx=(0, 6))
        if browse_cb:
            ttk.Button(row, text="…", width=3, command=browse_cb).pack(side="left")
        return ent

    def _btn_row(self, parent: tk.Widget, run_cb, open_cb) -> None:
        row = tk.Frame(parent, bg=BG_PANEL)
        row.pack(fill="x", padx=14, pady=(8, 4))
        self._run_btn = ttk.Button(row, text="▶  Run", command=run_cb,
                                   style="Run.TButton", width=14)
        self._run_btn.pack(side="left", padx=(0, 8))
        self._open_btn = ttk.Button(row, text="📂  Open output", command=open_cb,
                                    width=16)
        self._open_btn.pack(side="left")
        ttk.Button(row, text="🗑  Clear log", command=self._clear_log,
                   width=12).pack(side="right")

    # ---- log helpers ---------------------------------------------------

    def _log(self, text: str) -> None:
        if self._log_var is None:
            return
        log = self._log_var
        log.configure(state="normal")
        tag = "ok" if text.startswith("OK") else \
              "warn" if "WARN" in text else \
              "error" if "ERROR" in text or "Traceback" in text else \
              "info" if text.startswith("[") else ""
        log.insert("end", text + "\n", tag)
        log.see("end")
        log.configure(state="disabled")

    def _clear_log(self) -> None:
        if self._log_var is None:
            return
        self._log_var.configure(state="normal")
        self._log_var.delete("1.0", "end")
        self._log_var.configure(state="disabled")

    # ---- subprocess / streaming ----------------------------------------

    def _set_status(self, state: str) -> None:
        fg, text = STATUS_COLOURS.get(state, (FG_DIM, "—"))
        self._status_lbl.configure(text=text, fg=fg)
        self._run_btn.configure(state="disabled" if state == "running" else "normal")

    def _run_cmd(self, cmd: list) -> None:
        self._clear_log()
        self._set_status("running")
        self._log(f"$ {' '.join(cmd)}\n")
        t = threading.Thread(target=self._stream, args=(cmd,), daemon=True)
        t.start()
        self._poll()

    def _stream(self, cmd: list) -> None:
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=ROOT,
            )
            for line in proc.stdout:
                self._queue.put(("line", line.rstrip()))
            proc.wait()
            self._queue.put(("done", proc.returncode))
        except Exception as exc:
            self._queue.put(("line", f"[ERROR] {exc}"))
            self._queue.put(("done", 1))

    def _poll(self) -> None:
        try:
            while True:
                kind, val = self._queue.get_nowait()
                if kind == "line":
                    self._log(val)
                elif kind == "done":
                    self._set_status("ok" if val == 0 else "error")
                    return
        except queue.Empty:
            pass
        self.after(80, self._poll)


# ---------------------------------------------------------------------------
# M16 — Pavement Design
# ---------------------------------------------------------------------------
class PavementPanel(ToolPanel):
    def __init__(self, parent):
        super().__init__(parent, "M16", "Pavement Design (Austroads empirical)", BLUE)
        self._in_var  = tk.StringVar(value=os.path.join(ROOT, "csv", "pavement_inputs.csv"))
        self._out_var = tk.StringVar(value=os.path.join(ROOT, "out", "pavement_design.csv"))
        self._build_form()

    def _build_form(self):
        body = tk.Frame(self, bg=BG_PANEL)
        body.pack(fill="x", pady=(6, 0))
        self._row(body, "Input CSV",  self._in_var,  lambda: self._pick_file(self._in_var,  "pavement_inputs.csv"))
        self._row(body, "Output CSV", self._out_var, lambda: self._pick_save(self._out_var, "pavement_design.csv"))
        self._btn_row(body, self._run, lambda: _open_path(self._out_var.get()))
        self._build_log(self).pack(fill="both", expand=True, padx=14, pady=(4, 14))

    def _pick_file(self, var, default):
        p = filedialog.askopenfilename(initialfile=default, filetypes=[("CSV", "*.csv"), ("All", "*.*")])
        if p: var.set(p)

    def _pick_save(self, var, default):
        p = filedialog.asksaveasfilename(initialfile=default, defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if p: var.set(p)

    def _run(self):
        cmd = [sys.executable, os.path.join(TOOLS_DIR, "pavement_design.py"),
               "--cli", self._in_var.get(), "--out", self._out_var.get()]
        self._run_cmd(cmd)


# ---------------------------------------------------------------------------
# M17 — Drainage Design
# ---------------------------------------------------------------------------
class DrainagePanel(ToolPanel):
    def __init__(self, parent):
        super().__init__(parent, "M17", "Drainage Design (Rational method + Manning culvert)", BLUE)
        self._in_var  = tk.StringVar(value=os.path.join(ROOT, "csv", "catchments.csv"))
        self._out_var = tk.StringVar(value=os.path.join(ROOT, "out", "drainage_design.csv"))
        self._build_form()

    def _build_form(self):
        body = tk.Frame(self, bg=BG_PANEL)
        body.pack(fill="x", pady=(6, 0))
        self._row(body, "Catchments CSV", self._in_var,  lambda: self._pick_file(self._in_var))
        self._row(body, "Output CSV",     self._out_var, lambda: self._pick_save(self._out_var))
        self._btn_row(body, self._run, lambda: _open_path(self._out_var.get()))
        self._build_log(self).pack(fill="both", expand=True, padx=14, pady=(4, 14))

    def _pick_file(self, var):
        p = filedialog.askopenfilename(filetypes=[("CSV", "*.csv"), ("All", "*.*")])
        if p: var.set(p)

    def _pick_save(self, var):
        p = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if p: var.set(p)

    def _run(self):
        cmd = [sys.executable, os.path.join(TOOLS_DIR, "drainage_design.py"),
               "--cli", self._in_var.get(), "--out", self._out_var.get()]
        self._run_cmd(cmd)


# ---------------------------------------------------------------------------
# M18 — Intersection Design
# ---------------------------------------------------------------------------
class IntersectionPanel(ToolPanel):
    def __init__(self, parent):
        super().__init__(parent, "M18", "Intersection Design (SSD, kerb return, turn lanes)", BLUE)
        self._in_var     = tk.StringVar(value=os.path.join(ROOT, "csv", "intersections.csv"))
        self._geom_var   = tk.StringVar(value=os.path.join(ROOT, "out", "intersection_geometry.csv"))
        self._offset_var = tk.StringVar(value=os.path.join(ROOT, "out", "offset_alignment_inputs.csv"))
        self._build_form()

    def _build_form(self):
        body = tk.Frame(self, bg=BG_PANEL)
        body.pack(fill="x", pady=(6, 0))
        self._row(body, "Intersections CSV", self._in_var,     lambda: self._pick(self._in_var))
        self._row(body, "Geometry output",   self._geom_var,   lambda: self._save(self._geom_var))
        self._row(body, "Offset output",     self._offset_var, lambda: self._save(self._offset_var))

        btn_row = tk.Frame(body, bg=BG_PANEL)
        btn_row.pack(fill="x", padx=14, pady=(8, 4))
        self._run_btn = ttk.Button(btn_row, text="▶  Run", command=self._run,
                                   style="Run.TButton", width=14)
        self._run_btn.pack(side="left", padx=(0, 8))
        ttk.Button(btn_row, text="📂  Open geometry", width=18,
                   command=lambda: _open_path(self._geom_var.get())).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="📂  Open offsets",  width=16,
                   command=lambda: _open_path(self._offset_var.get())).pack(side="left")
        ttk.Button(btn_row, text="🗑  Clear log", command=self._clear_log,
                   width=12).pack(side="right")

        self._build_log(self).pack(fill="both", expand=True, padx=14, pady=(4, 14))

    def _pick(self, var):
        p = filedialog.askopenfilename(filetypes=[("CSV", "*.csv"), ("All", "*.*")])
        if p: var.set(p)

    def _save(self, var):
        p = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if p: var.set(p)

    def _run(self):
        cmd = [sys.executable, os.path.join(TOOLS_DIR, "intersection_design.py"),
               "--cli", self._in_var.get(),
               "--geom-out",   self._geom_var.get(),
               "--offset-out", self._offset_var.get()]
        self._run_cmd(cmd)


# ---------------------------------------------------------------------------
# M19 — Report Generator
# ---------------------------------------------------------------------------
class ReportPanel(ToolPanel):
    def __init__(self, parent):
        super().__init__(parent, "M19", "Report Generator — multi-sheet Excel workbook", "#1c6f44")
        self._cfg_var = tk.StringVar(value=DEFAULT_CFG)
        self._out_var = tk.StringVar(value=os.path.join(ROOT, "out", "report", "design_report.xlsx"))
        self._build_form()

    def _build_form(self):
        body = tk.Frame(self, bg=BG_PANEL)
        body.pack(fill="x", pady=(6, 0))
        self._row(body, "project.json", self._cfg_var, self._pick_cfg)
        self._row(body, "Output xlsx",  self._out_var, lambda: self._save(self._out_var), readonly=False)

        info = tk.Frame(body, bg=BG_PANEL)
        info.pack(fill="x", padx=14, pady=(2, 4))
        tk.Label(info, text="Sheets: Cover · Alignment · Profile · Sections · Volumes · "
                            "Pavement · Drainage · BOQ · MassHaul · QA Log",
                 bg=BG_PANEL, fg=FG_DIM, font=("Segoe UI", 8), anchor="w").pack(fill="x")

        self._btn_row(body, self._run, lambda: _open_path(self._out_var.get()))
        self._build_log(self).pack(fill="both", expand=True, padx=14, pady=(4, 14))

    def _pick_cfg(self):
        p = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if p: self._cfg_var.set(p)

    def _save(self, var):
        p = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")])
        if p: var.set(p)

    def _run(self):
        cmd = [sys.executable, os.path.join(TOOLS_DIR, "report_generator.py"),
               self._cfg_var.get()]
        self._run_cmd(cmd)


# ---------------------------------------------------------------------------
# M20 — Design Verifier
# ---------------------------------------------------------------------------
class VerifierPanel(ToolPanel):
    def __init__(self, parent):
        super().__init__(parent, "M20", "Design Verifier — cross-check all outputs", "#1c6f44")
        self._cfg_var = tk.StringVar(value=DEFAULT_CFG)
        self._out_var = tk.StringVar(value=os.path.join(ROOT, "out", "design_verification.txt"))
        self._build_form()

    def _build_form(self):
        body = tk.Frame(self, bg=BG_PANEL)
        body.pack(fill="x", pady=(6, 0))
        self._row(body, "project.json",    self._cfg_var, self._pick_cfg)
        self._row(body, "Output txt",      self._out_var, None, readonly=True)

        checks = tk.Frame(body, bg=BG_PANEL)
        checks.pack(fill="x", padx=14, pady=(2, 4))
        items = ("Alignment radii", "Profile grades", "Cut/fill volumes",
                 "Pavement thickness", "Culvert HW/D ≤ 1.5", "BOQ consistency", "Mass haul peaks")
        txt = "Checks: " + " · ".join(items)
        tk.Label(checks, text=txt, bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 8), anchor="w", wraplength=640,
                 justify="left").pack(fill="x")

        self._btn_row(body, self._run, lambda: _open_path(self._out_var.get()))
        self._build_log(self).pack(fill="both", expand=True, padx=14, pady=(4, 14))

    def _pick_cfg(self):
        p = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if p: self._cfg_var.set(p)

    def _run(self):
        cmd = [sys.executable, os.path.join(TOOLS_DIR, "design_verifier.py"),
               self._cfg_var.get()]
        self._run_cmd(cmd)


# ---------------------------------------------------------------------------
# Home / Overview tab
# ---------------------------------------------------------------------------
class HomePanel(ttk.Frame):
    def __init__(self, parent, notebook: ttk.Notebook,
                 panels: dict, cfg_var: tk.StringVar):
        super().__init__(parent)
        self.configure(style="Dark.TFrame")
        self._notebook = notebook
        self._panels   = panels   # {"M16": PavementPanel, ...}
        self._cfg_var  = cfg_var
        self._build()

    def _build(self):
        # title
        hdr = tk.Frame(self, bg=BG_MID, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Road Design Automation — Python Tools Dashboard",
                 bg=BG_MID, fg=AMBER, font=("Segoe UI", 14, "bold"),
                 padx=16).pack(side="left")
        tk.Label(hdr, text="M16 – M20", bg=BG_MID, fg=FG_DIM,
                 font=("Segoe UI", 11), padx=6).pack(side="left")

        # project.json row
        cfg_row = tk.Frame(self, bg=BG_PANEL, pady=6)
        cfg_row.pack(fill="x", padx=0)
        tk.Label(cfg_row, text="project.json", bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 9), padx=14).pack(side="left")
        ent = ttk.Entry(cfg_row, textvariable=self._cfg_var, width=60, style="Path.TEntry")
        ent.pack(side="left", padx=6)
        ttk.Button(cfg_row, text="…", width=3,
                   command=self._pick_cfg).pack(side="left")
        ttk.Button(cfg_row, text="Reload status", width=14,
                   command=self._refresh).pack(side="right", padx=14)

        # module cards
        cards = tk.Frame(self, bg=BG_DARK)
        cards.pack(fill="both", expand=True, padx=14, pady=14)

        self._rows = {}
        modules = [
            ("M16", "Pavement Design",       BLUE,     "out/pavement_design.csv"),
            ("M17", "Drainage Design",        BLUE,     "out/drainage_design.csv"),
            ("M18", "Intersection Design",    BLUE,     "out/intersection_geometry.csv"),
            ("M19", "Report Generator",       "#1c6f44","out/report/design_report.xlsx"),
            ("M20", "Design Verifier",        "#1c6f44","out/design_verification.txt"),
            ("M21", "Curve Schedule",         PURPLE,   "out/curve_schedule.csv"),
        ]

        for i, (mod, name, colour, outrel) in enumerate(modules):
            row = tk.Frame(cards, bg=BG_PANEL, pady=8, padx=10)
            row.pack(fill="x", pady=4)

            badge = tk.Label(row, text=mod, bg=colour, fg="white",
                             font=("Segoe UI", 10, "bold"), width=5, pady=2)
            badge.pack(side="left", padx=(0, 10))

            tk.Label(row, text=name, bg=BG_PANEL, fg=FG_WHITE,
                     font=("Segoe UI", 10), width=24, anchor="w").pack(side="left")

            out_path = os.path.join(ROOT, outrel.replace("/", os.sep))
            status_lbl = tk.Label(row, bg=BG_PANEL, font=("Segoe UI", 9), padx=8)
            status_lbl.pack(side="left")
            self._rows[mod] = (status_lbl, out_path)

            ttk.Button(row, text="Open tab", width=10,
                       command=lambda m=mod: self._goto(m)).pack(side="right", padx=(0, 4))
            ttk.Button(row, text="▶ Run", style="Run.TButton", width=8,
                       command=lambda m=mod: self._quick_run(m)).pack(side="right", padx=(0, 4))
            open_btn = ttk.Button(row, text="📂", width=3,
                                  command=lambda p=out_path: _open_path(p))
            open_btn.pack(side="right", padx=(0, 6))

        self._refresh()

    def _pick_cfg(self):
        p = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if p:
            self._cfg_var.set(p)
            # propagate to M19 and M20 panels
            for key in ("M19", "M20"):
                panel = self._panels.get(key)
                if panel:
                    panel._cfg_var.set(p)

    def _goto(self, mod: str):
        tab_names = {"M16": 1, "M17": 2, "M18": 3, "M19": 4, "M20": 5, "M21": 6}
        idx = tab_names.get(mod)
        if idx is not None:
            self._notebook.select(idx)

    def _quick_run(self, mod: str):
        self._goto(mod)
        panel = self._panels.get(mod)
        if panel:
            panel._run()

    def _refresh(self):
        for mod, (lbl, path) in self._rows.items():
            if os.path.isfile(path):
                size = os.path.getsize(path)
                lbl.configure(text=f"Output exists ({size:,} bytes)", fg=GREEN, bg=BG_PANEL)
            else:
                lbl.configure(text="No output yet", fg=FG_DIM, bg=BG_PANEL)


# ---------------------------------------------------------------------------
# M21 — Curve Schedule
# ---------------------------------------------------------------------------
PURPLE = "#8b5cf6"

class CurveSchedulePanel(ToolPanel):
    def __init__(self, parent):
        super().__init__(parent, "M21", "Curve Schedule — clothoid A, K-values, SSD", PURPLE)
        self._align_var   = tk.StringVar(value=os.path.join(ROOT, "csv", "alignment_pi.csv"))
        self._profile_var = tk.StringVar(value=os.path.join(ROOT, "csv", "profile_pvis.csv"))
        self._csv_var     = tk.StringVar(value=os.path.join(ROOT, "out", "curve_schedule.csv"))
        self._report_var  = tk.StringVar(value=os.path.join(ROOT, "out", "curve_schedule_report.txt"))
        self._build_form()

    def _build_form(self):
        body = tk.Frame(self, bg=BG_PANEL)
        body.pack(fill="x", pady=(6, 0))
        self._row(body, "alignment_pi.csv",  self._align_var,   lambda: self._pick(self._align_var))
        self._row(body, "profile_pvis.csv",  self._profile_var, lambda: self._pick(self._profile_var))
        self._row(body, "Output CSV",        self._csv_var,     lambda: self._save(self._csv_var, ".csv"))
        self._row(body, "Output report",     self._report_var,  lambda: self._save(self._report_var, ".txt"))

        info = tk.Frame(body, bg=BG_PANEL)
        info.pack(fill="x", padx=14, pady=(2, 4))
        tk.Label(info,
                 text="Checks: radius vs Rmin · clothoid A parameter · K-value vs Austroads table · "
                      "SSD at crest · compound/reverse curves",
                 bg=BG_PANEL, fg=FG_DIM, font=("Segoe UI", 8),
                 anchor="w", wraplength=640, justify="left").pack(fill="x")

        btn_row = tk.Frame(body, bg=BG_PANEL)
        btn_row.pack(fill="x", padx=14, pady=(8, 4))
        self._run_btn = ttk.Button(btn_row, text="▶  Run", command=self._run,
                                   style="Run.TButton", width=14)
        self._run_btn.pack(side="left", padx=(0, 8))
        ttk.Button(btn_row, text="📂  Open CSV",    width=14,
                   command=lambda: _open_path(self._csv_var.get())).pack(side="left", padx=(0, 4))
        ttk.Button(btn_row, text="📂  Open report", width=14,
                   command=lambda: _open_path(self._report_var.get())).pack(side="left")
        ttk.Button(btn_row, text="🗑  Clear log", command=self._clear_log,
                   width=12).pack(side="right")

        self._build_log(self).pack(fill="both", expand=True, padx=14, pady=(4, 14))

    def _pick(self, var):
        p = filedialog.askopenfilename(filetypes=[("CSV", "*.csv"), ("All", "*.*")])
        if p: var.set(p)

    def _save(self, var, ext):
        p = filedialog.asksaveasfilename(defaultextension=ext,
                filetypes=[("CSV" if ext == ".csv" else "Text", f"*{ext}")])
        if p: var.set(p)

    def _run(self):
        cmd = [sys.executable, os.path.join(TOOLS_DIR, "m21_curve_schedule.py"),
               "--cli", self._align_var.get(), self._profile_var.get(),
               "--out-csv",    self._csv_var.get(),
               "--out-report", self._report_var.get()]
        self._run_cmd(cmd)


# ---------------------------------------------------------------------------
# Preflight tab
# ---------------------------------------------------------------------------
class PreflightPanel(ToolPanel):
    def __init__(self, parent):
        super().__init__(parent, "Preflight", "Validate all CSV headers and paths", "#6c4ba0")
        self._cfg_var    = tk.StringVar(value=DEFAULT_CFG)
        self._strict_var = tk.BooleanVar(value=True)
        self._build_form()

    def _build_form(self):
        body = tk.Frame(self, bg=BG_PANEL)
        body.pack(fill="x", pady=(6, 0))
        self._row(body, "project.json", self._cfg_var, self._pick_cfg)

        opt_row = tk.Frame(body, bg=BG_PANEL)
        opt_row.pack(fill="x", padx=14, pady=(2, 6))
        ttk.Checkbutton(opt_row, text="Strict mode (checks PI count, station order, region overlaps)",
                        variable=self._strict_var,
                        style="Dark.TCheckbutton").pack(side="left")

        btn_row = tk.Frame(body, bg=BG_PANEL)
        btn_row.pack(fill="x", padx=14, pady=(2, 4))
        self._run_btn = ttk.Button(btn_row, text="▶  Run preflight", command=self._run,
                                   style="Run.TButton", width=16)
        self._run_btn.pack(side="left", padx=(0, 8))
        ttk.Button(btn_row, text="🗑  Clear log", command=self._clear_log,
                   width=12).pack(side="right")

        self._build_log(self).pack(fill="both", expand=True, padx=14, pady=(4, 14))

    def _pick_cfg(self):
        p = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if p: self._cfg_var.set(p)

    def _run(self):
        preflight = os.path.join(TOOLS_DIR, "road_automation_preflight.py")
        cmd = [sys.executable, preflight, "--validate", self._cfg_var.get()]
        if self._strict_var.get():
            cmd.append("--strict")
        self._run_cmd(cmd)


# ---------------------------------------------------------------------------
# Workbook builder tab
# ---------------------------------------------------------------------------
class WorkbookPanel(ToolPanel):
    def __init__(self, parent):
        super().__init__(parent, "Workbook", "Build Excel starter workbook with templates", "#6c4ba0")
        self._out_var = tk.StringVar(value=os.path.join(ROOT, "road_design_starter.xlsx"))
        self._build_form()

    def _build_form(self):
        body = tk.Frame(self, bg=BG_PANEL)
        body.pack(fill="x", pady=(6, 0))
        self._row(body, "Output xlsx", self._out_var,
                  lambda: self._pick_save(self._out_var))

        info = tk.Frame(body, bg=BG_PANEL)
        info.pack(fill="x", padx=14, pady=(2, 4))
        tk.Label(info, text="Generates a workbook with one sheet per CSV (headers + example rows + dropdowns).",
                 bg=BG_PANEL, fg=FG_DIM, font=("Segoe UI", 8)).pack(anchor="w")

        self._btn_row(body, self._run, lambda: _open_path(self._out_var.get()))
        self._build_log(self).pack(fill="both", expand=True, padx=14, pady=(4, 14))

    def _pick_save(self, var):
        p = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")])
        if p: var.set(p)

    def _run(self):
        cmd = [sys.executable, os.path.join(TOOLS_DIR, "build_starter_workbook.py"),
               "--out", self._out_var.get()]
        self._run_cmd(cmd)


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------
class Dashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Road Design Automation — Tools Dashboard")
        self.configure(bg=BG_DARK)
        self.geometry("860x680")
        self.minsize(720, 560)

        self._apply_styles()
        self._cfg_var = tk.StringVar(value=DEFAULT_CFG)

        nb = ttk.Notebook(self, style="Dark.TNotebook")
        nb.pack(fill="both", expand=True, padx=0, pady=0)

        # Instantiate tool panels
        panels = {
            "M16": PavementPanel(nb),
            "M17": DrainagePanel(nb),
            "M18": IntersectionPanel(nb),
            "M19": ReportPanel(nb),
            "M20": VerifierPanel(nb),
            "M21": CurveSchedulePanel(nb),
        }

        home = HomePanel(nb, nb, panels, self._cfg_var)

        nb.add(home,             text="  Home  ")
        nb.add(panels["M16"],    text="  M16 Pavement  ")
        nb.add(panels["M17"],    text="  M17 Drainage  ")
        nb.add(panels["M18"],    text="  M18 Intersections  ")
        nb.add(panels["M19"],    text="  M19 Report  ")
        nb.add(panels["M20"],    text="  M20 Verify  ")
        nb.add(panels["M21"],    text="  M21 Curves  ")
        nb.add(PreflightPanel(nb),  text="  Preflight  ")
        nb.add(WorkbookPanel(nb),   text="  Workbook  ")

        # status bar
        bar = tk.Frame(self, bg=BG_MID, pady=3)
        bar.pack(fill="x", side="bottom")
        tk.Label(bar, textvariable=self._cfg_var, bg=BG_MID, fg=FG_DIM,
                 font=("Segoe UI", 8), anchor="w", padx=10).pack(side="left")
        tk.Label(bar, text="Road Design Automation • M16–M21 Python Tools",
                 bg=BG_MID, fg=FG_DIM, font=("Segoe UI", 8), padx=10).pack(side="right")

    def _apply_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")

        s.configure(".", background=BG_DARK, foreground=FG_WHITE,
                     troughcolor=BG_MID, selectbackground=AMBER,
                     selectforeground=BG_DARK, fieldbackground=BG_MID,
                     borderwidth=0, focusthickness=0)

        s.configure("Dark.TFrame",     background=BG_DARK)
        s.configure("Dark.TNotebook",  background=BG_DARK, tabmargins=[0, 0, 0, 0])
        s.configure("Dark.TNotebook.Tab", background=BG_MID, foreground=FG_DIM,
                    padding=[10, 5], font=("Segoe UI", 9))
        s.map("Dark.TNotebook.Tab",
              background=[("selected", BG_PANEL)],
              foreground=[("selected", AMBER)])

        s.configure("TEntry",       fieldbackground=BG_MID, foreground=FG_WHITE,
                    insertcolor=FG_WHITE, borderwidth=1, relief="flat")
        s.configure("Path.TEntry",  fieldbackground=BG_MID, foreground=FG_WHITE,
                    insertcolor=FG_WHITE)

        s.configure("TButton",      background=BG_MID, foreground=FG_WHITE,
                    padding=[6, 3], relief="flat", font=("Segoe UI", 9))
        s.map("TButton",
              background=[("active", BG_PANEL), ("pressed", BG_DARK)])

        s.configure("Run.TButton",  background=AMBER, foreground=BG_DARK,
                    font=("Segoe UI", 9, "bold"))
        s.map("Run.TButton",
              background=[("active", "#d08f00"), ("disabled", BG_MID)],
              foreground=[("disabled", FG_DIM)])

        s.configure("TCheckbutton", background=BG_PANEL, foreground=FG_WHITE)
        s.configure("Dark.TCheckbutton", background=BG_PANEL, foreground=FG_WHITE)
        s.map("TCheckbutton",
              background=[("active", BG_PANEL)])


def main():
    app = Dashboard()
    app.mainloop()


if __name__ == "__main__":
    main()
