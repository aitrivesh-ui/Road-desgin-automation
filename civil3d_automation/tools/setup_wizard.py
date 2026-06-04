# -*- coding: utf-8 -*-
"""
Road automation — project setup wizard (Python 3 + tkinter/ttk).

Creates config/project.json through a guided GUI, then runs preflight.

Usage:
  python setup_wizard.py            — GUI mode
  python setup_wizard.py --cli      — CLI prompted mode
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Field definitions: (tab_name, [(key, label, hint, default), ...])
# ---------------------------------------------------------------------------
TABS = [
    (
        "Project info",
        [
            ("project.number",   "Project number",  "e.g. PRJ-2026-001",               "PRJ-2026-001"),
            ("project.name",     "Project name",    "Short descriptive title",          "New road project"),
            ("project.revision", "Revision",        "e.g. REV-A",                      "REV-A"),
            ("project.designer", "Designer",        "Initials or full name (optional)", ""),
            ("project.checker",  "Checker",         "Initials or full name (optional)", ""),
        ],
    ),
    (
        "Civil 3D names",
        [
            ("names.alignment",      "Alignment name",  "Must match Civil 3D object name",  "MAIN-CL"),
            ("names.profile_fg",     "FG profile name", "Finished-grade profile name",      "MAIN-FG"),
            ("names.corridor",       "Corridor name",   "Corridor object name",             "MAIN-COR"),
            ("names.assembly",       "Assembly name",   "Must exist in the template DWG",   "BasicLaneAssembly"),
            ("names.surface_eg",     "EG surface name", "Existing-ground surface",          "EG"),
            ("names.surface_fg",     "FG surface name", "Finished-grade surface (M4)",      "FG"),
            ("names.layers.marking", "Marking layer",   "Layer for road markings (M7)",     "C-ROAD-MARK"),
            ("names.layers.signage", "Signage layer",   "Layer for sign blocks (M5/M7)",    "C-SGN-FURN"),
        ],
    ),
    (
        "Styles",
        [
            ("styles.alignment",       "Alignment style",     "Must exist in template DWG", "Standard"),
            ("styles.alignment_label", "Alignment label set", "Label set name",             "Standard"),
            ("styles.profile",         "Profile style",       "Must exist in template DWG", "Standard"),
            ("styles.profile_label",   "Profile label set",   "Label set name",             "Standard"),
        ],
    ),
    (
        "Design parameters",
        [
            ("design.start_station", "Start station (m)", "Chainage of alignment start point",   "0.0"),
            ("design.max_grade_pct", "Max grade (%)",     "Grade QA upper limit — M2 will warn", "8.0"),
            ("design.min_grade_pct", "Min grade (%)",     "Grade QA lower limit — M2 will warn", "0.3"),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Config assembly
# ---------------------------------------------------------------------------

def _build_config(values: dict[str, str]) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "project": {},
        "paths": {
            "alignment_pi":   "csv/alignment_pi.csv",
            "profile_pvis":   "csv/profile_pvis.csv",
            "section_widths": "csv/section_widths.csv",
            "signage":        "csv/signage_schedule.csv",
            "payitems":       "csv/payitems.csv",
            "volumes_csv":    "out/volumes.csv",
            "boq_csv":        "out/boq.csv",
            "qa_log":         "out/qa/run_log.txt",
        },
        "names":  {"layers": {}},
        "styles": {},
        "design": {},
    }
    for key, val in values.items():
        parts = key.split(".")
        sec = parts[0]
        if sec == "project":
            cfg["project"][parts[1]] = val
        elif sec == "names":
            if len(parts) == 3:
                cfg["names"]["layers"][parts[2]] = val
            else:
                cfg["names"][parts[1]] = val
        elif sec == "styles":
            cfg["styles"][parts[1]] = val
        elif sec == "design":
            try:
                cfg["design"][parts[1]] = float(val)
            except ValueError:
                cfg["design"][parts[1]] = val
    return cfg


def _write_config(cfg: dict[str, Any], dest: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")


def _run_preflight(project_json: str, strict: bool = False) -> list[str]:
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    try:
        from preflight_validate import validate_project
        return validate_project(project_json, strict=strict)
    except ImportError:
        return ["[SKIP] preflight_validate not found — skipping preflight."]


def _default_dest() -> str:
    here = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    return os.path.join(here, "config", "project.json")


# ---------------------------------------------------------------------------
# CLI mode
# ---------------------------------------------------------------------------

def run_cli() -> int:
    print("Road automation — project setup wizard (CLI)")
    print("=" * 52)
    values: dict[str, str] = {}
    for tab_name, fields in TABS:
        print(f"\n--- {tab_name} ---")
        for key, label, hint, default in fields:
            raw = input(f"  {label} [{default}]: ").strip()
            values[key] = raw if raw else default

    dest_default = _default_dest()
    raw_dest = input(f"\nSave project.json to [{dest_default}]: ").strip()
    dest = raw_dest if raw_dest else dest_default

    cfg = _build_config(values)
    _write_config(cfg, dest)
    print(f"\n[OK] Written: {dest}")

    strict = input("Run strict preflight? [y/N]: ").strip().lower() == "y"
    print("\nRunning preflight...")
    for line in _run_preflight(dest, strict=strict):
        print(" ", line)
    return 0


# ---------------------------------------------------------------------------
# GUI mode
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
    root.title("Road automation — project setup wizard")
    root.minsize(700, 600)
    root.configure(bg=BG_LIGHT)

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TNotebook",           background=BG_DARK, tabmargins=[0, 0, 0, 0])
    style.configure("TNotebook.Tab",       background=BG_DARK, foreground="#aaaaaa",
                                            padding=[14, 6],    font=FONT_BODY)
    style.map("TNotebook.Tab",
              background=[("selected", BG_LIGHT)],
              foreground=[("selected", BG_DARK)],
              font=[("selected", ("Segoe UI", 10, "bold"))])
    style.configure("TFrame",             background=BG_LIGHT)
    style.configure("TLabel",             background=BG_LIGHT, font=FONT_BODY)
    style.configure("TEntry",             font=FONT_BODY)
    style.configure("TCheckbutton",       background=BG_LIGHT, font=FONT_BODY)
    style.configure("Accent.TButton",     background=BTN_GREEN, foreground="white",
                                           font=("Segoe UI", 10, "bold"), padding=[10, 6])
    style.map("Accent.TButton",           background=[("active", "#145230")])

    banner = tk.Frame(root, bg=BG_DARK, height=52)
    banner.pack(fill=tk.X)
    banner.pack_propagate(False)
    tk.Label(
        banner, text="Road Design Automation — Project Setup Wizard",
        bg=BG_DARK, fg=ACCENT, font=("Segoe UI", 13, "bold"),
    ).pack(side=tk.LEFT, padx=16, pady=10)

    nb = ttk.Notebook(root)
    nb.pack(fill=tk.BOTH, expand=True, padx=12, pady=(10, 4))

    entries: dict[str, tk.StringVar] = {}

    for tab_name, fields in TABS:
        frame = ttk.Frame(nb, padding=(16, 14))
        nb.add(frame, text=tab_name)
        ttk.Label(frame, text=tab_name, font=FONT_HEAD).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 12)
        )
        for i, (key, label, hint, default) in enumerate(fields, start=1):
            var = tk.StringVar(value=default)
            entries[key] = var
            ttk.Label(frame, text=label, width=24, anchor="w").grid(
                row=i, column=0, sticky="w", pady=5
            )
            ttk.Entry(frame, textvariable=var, width=34).grid(
                row=i, column=1, sticky="ew", padx=(8, 8), pady=5
            )
            ttk.Label(frame, text=hint, foreground="#888888").grid(
                row=i, column=2, sticky="w"
            )
        frame.columnconfigure(1, weight=1)

    bot = ttk.Frame(root, padding=(12, 2, 12, 4))
    bot.pack(fill=tk.X)
    dest_var = tk.StringVar(value=_default_dest())
    strict_var = tk.BooleanVar(value=False)

    ttk.Label(bot, text="Save project.json to:").grid(row=0, column=0, sticky="w")
    ttk.Entry(bot, textvariable=dest_var, width=54).grid(
        row=0, column=1, sticky="ew", padx=(6, 6)
    )
    ttk.Button(
        bot, text="Browse…",
        command=lambda: dest_var.set(
            filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON", "*.json")],
                initialfile="project.json",
            ) or dest_var.get()
        ),
    ).grid(row=0, column=2)
    ttk.Checkbutton(bot, text="Run strict preflight checks", variable=strict_var).grid(
        row=1, column=0, columnspan=3, sticky="w", pady=(4, 0)
    )
    bot.columnconfigure(1, weight=1)

    act = ttk.Frame(root, padding=(12, 4, 12, 4))
    act.pack(fill=tk.X)

    result_txt = scrolledtext.ScrolledText(
        root, height=10, wrap=tk.WORD, font=("Consolas", 9),
        bg="#1e1e1e", fg="#d4d4d4", insertbackground="white",
    )

    def generate() -> None:
        values: dict[str, str] = {}
        for _, fields in TABS:
            for key, _, _, default in fields:
                raw = entries[key].get().strip()
                values[key] = raw if raw else default
        dest = dest_var.get().strip()
        if not dest:
            result_txt.insert(tk.END, "[ERROR] No destination path set.\n")
            return
        cfg = _build_config(values)
        try:
            _write_config(cfg, dest)
        except OSError as ex:
            result_txt.insert(tk.END, f"[ERROR] Cannot write file:\n  {ex}\n")
            return
        result_txt.delete("1.0", tk.END)
        result_txt.insert(tk.END, f"[OK] Written: {dest}\n\n--- Preflight ---\n")
        for line in _run_preflight(dest, strict=strict_var.get()):
            result_txt.insert(tk.END, line + "\n")
        result_txt.see(tk.END)

    ttk.Button(
        act, text="Generate project.json + run preflight",
        style="Accent.TButton", command=generate,
    ).pack(side=tk.LEFT)

    result_txt.pack(fill=tk.BOTH, expand=False, padx=12, pady=(4, 10))

    root.mainloop()


def main() -> None:
    if "--cli" in sys.argv:
        sys.exit(run_cli())
    try:
        run_gui()
    except ImportError as ex:
        if "tkinter" in str(ex).lower():
            print("Tkinter not available — falling back to CLI mode.\n")
            sys.exit(run_cli())
        raise


if __name__ == "__main__":
    main()
