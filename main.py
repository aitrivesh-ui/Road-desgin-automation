"""
main.py — Road Design Automation hub.

Single window, step-by-step workflow.  Click a step in the sidebar; the right
panel shows what it does and a button to launch that tool.  The hub stays open
while tools run in their own windows.

Usage:  python main.py
"""

import os
import sys
import subprocess
import tkinter as tk

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "civil3d_automation", "tools")

# ---------------------------------------------------------------------------
# Step catalogue  (in workflow order)
# ---------------------------------------------------------------------------
STEPS = [
    {
        "num":    "1",
        "id":     "wizard",
        "title":  "Project Setup",
        "sub":    "Create config/project.json",
        "colour": "#2e6da4",
        "desc": (
            "Start here every new project.\n\n"
            "The Setup Wizard walks you through four tabs:\n"
            "  • Project info  (number, name, revision, designer)\n"
            "  • Civil 3D names  (alignment, surface, assembly)\n"
            "  • Styles  (label / band sets)\n"
            "  • Design parameters  (speed, road class, intervals)\n\n"
            "Click Generate at the end to write config/project.json "
            "and run an automatic preflight check."
        ),
        "script": os.path.join(TOOLS, "setup_wizard.py"),
        "btn":    "Open Setup Wizard",
    },
    {
        "num":    "2",
        "id":     "survey",
        "title":  "DGPS Survey → CSV",
        "sub":    "Auto-generate input CSVs from a survey file",
        "colour": "#1c6f44",
        "desc": (
            "Skip manual CSV entry if you have a DGPS survey file.\n\n"
            "Supported formats (auto-detected):\n"
            "  • Generic CSV / TXT\n"
            "  • Trimble DC  and  Trimble CSV\n"
            "  • Leica GSI  (8-word and 16-word)\n"
            "  • LandXML\n\n"
            "The wizard generates ready-to-use CSVs for M1–M5:\n"
            "  alignment_pi.csv  •  profile_pvis.csv\n"
            "  section_widths.csv  •  signage_schedule.csv\n\n"
            "After this step, go straight to Step 3 Preflight — "
            "skip manual CSV editing."
        ),
        "script": os.path.join(TOOLS, "survey_to_csv.py"),
        "btn":    "Open Survey Importer",
    },
    {
        "num":    "3",
        "id":     "preflight",
        "title":  "Preflight Validation",
        "sub":    "Validate project.json and all CSV files",
        "colour": "#7b4f00",
        "desc": (
            "Always run before opening Civil 3D.\n\n"
            "Checks every required CSV exists, headers are correct, "
            "and paths in project.json resolve.\n\n"
            "Result codes:\n"
            "  OK     — check passed\n"
            "  WARN   — optional key missing  (add if module is needed)\n"
            "  INFO   — output file not yet created  (normal before first run)\n"
            "  ERROR  — must fix before proceeding\n\n"
            "Do not open Civil 3D if any ERROR lines appear."
        ),
        "script": os.path.join(TOOLS, "road_automation_preflight.py"),
        "btn":    "Open Preflight",
    },
    {
        "num":    "4",
        "id":     "launcher",
        "title":  "Pipeline Launcher",
        "sub":    "Run any combination of M1–M20",
        "colour": "#4a90d9",
        "desc": (
            "Main control panel for the full pipeline.\n\n"
            "Three tabs:\n"
            "  • Select Modules  — tick any M1–M20 combination\n"
            "  • Dynamo (M1–M15)  — copies the step-filter string\n"
            "    to clipboard; paste into Civil 3D Dynamo Player IN[1]\n"
            "  • Python Tools (M16–M20)  — runs tools directly with\n"
            "    live status badges and log output\n\n"
            "Keep this window open throughout your entire workflow. "
            "You can re-run individual modules after design changes "
            "without re-running the full pipeline."
        ),
        "script": os.path.join(TOOLS, "pipeline_launcher.py"),
        "btn":    "Open Pipeline Launcher",
    },
    {
        "num":    "5",
        "id":     "dashboard",
        "title":  "Tools Dashboard",
        "sub":    "M16–M20 Python design tools",
        "colour": "#5a3fa0",
        "desc": (
            "Focused view for the five Python design tools:\n\n"
            "  M16  Pavement design      Austroads thickness design\n"
            "  M17  Drainage design      Rational method + Manning culverts\n"
            "  M18  Intersection design  Turning lanes + kerb returns\n"
            "  M19  Report generator     Multi-sheet Excel with charts\n"
            "  M20  Design verifier      Cross-check all outputs OK/WARN/ERROR\n\n"
            "Each tool shows a status badge and streams its output to a "
            "log panel.  Use this instead of the launcher when you only "
            "need to re-run Python tools after a Civil 3D change."
        ),
        "script": os.path.join(TOOLS, "dashboard.py"),
        "btn":    "Open Tools Dashboard",
    },
]

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
C = {
    "bg":    "#1c2030",
    "mid":   "#252a3a",
    "panel": "#2e3449",
    "fg":    "#f0f0f0",
    "dim":   "#9098b0",
    "amber": "#F0A500",
    "sep":   "#3a4260",
    "sel":   "#2e3c5a",
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    root = tk.Tk()
    root.title("Road Design Automation")
    root.configure(bg=C["bg"])
    root.geometry("860x580")
    root.minsize(720, 460)

    # ── two-column layout ────────────────────────────────────────────────────
    sidebar = tk.Frame(root, bg=C["mid"], width=230)
    sidebar.pack(side=tk.LEFT, fill=tk.Y)
    sidebar.pack_propagate(False)

    content = tk.Frame(root, bg=C["bg"])
    content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # ── sidebar: app title ───────────────────────────────────────────────────
    tk.Label(sidebar,
             text="Road Design\nAutomation",
             font=("Segoe UI", 13, "bold"),
             bg=C["mid"], fg=C["amber"],
             anchor="w", padx=16, pady=16, justify="left",
             ).pack(fill=tk.X)
    tk.Frame(sidebar, bg=C["sep"], height=1).pack(fill=tk.X)

    # ── content panels (one per step, shown/hidden) ──────────────────────────
    panels: dict[str, tk.Frame] = {}
    for step in STEPS:
        pnl = tk.Frame(content, bg=C["bg"])
        panels[step["id"]] = pnl

    # ── sidebar buttons ──────────────────────────────────────────────────────
    btn_frames: dict[str, tk.Frame] = {}

    def _select(step_id: str) -> None:
        for sid, frm in btn_frames.items():
            bg = C["sel"] if sid == step_id else C["mid"]
            frm.configure(bg=bg)
            for w in frm.winfo_children():
                w.configure(bg=bg)
                if isinstance(w, tk.Frame):
                    for ww in w.winfo_children():
                        try:
                            ww.configure(bg=bg)
                        except tk.TclError:
                            pass
        for sid, pnl in panels.items():
            if sid == step_id:
                pnl.place(relx=0, rely=0, relwidth=1, relheight=1)
            else:
                pnl.place_forget()

    for i, step in enumerate(STEPS):
        col = step["colour"]

        row = tk.Frame(sidebar, bg=C["mid"], cursor="hand2")
        row.pack(fill=tk.X)
        btn_frames[step["id"]] = row

        # coloured number badge
        tk.Label(row, text=step["num"],
                 font=("Segoe UI", 11, "bold"),
                 bg=col, fg=C["fg"], width=3, pady=14,
                 ).pack(side=tk.LEFT)

        # text
        txt = tk.Frame(row, bg=C["mid"], padx=10)
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=4)
        tk.Label(txt, text=step["title"],
                 font=("Segoe UI", 10, "bold"),
                 bg=C["mid"], fg=C["fg"], anchor="w").pack(fill=tk.X)
        tk.Label(txt, text=step["sub"],
                 font=("Segoe UI", 8),
                 bg=C["mid"], fg=C["dim"], anchor="w").pack(fill=tk.X)

        tk.Frame(sidebar, bg=C["sep"], height=1).pack(fill=tk.X)

        # click binding (row + all children)
        sid = step["id"]
        for widget in (row, *row.winfo_children(), *txt.winfo_children()):
            widget.bind("<Button-1>", lambda e, s=sid: _select(s))

        # ── right-panel content ──────────────────────────────────────────────
        pnl = panels[step["id"]]

        # coloured header
        tk.Label(pnl,
                 text=f"Step {step['num']}  —  {step['title']}",
                 font=("Segoe UI", 15, "bold"),
                 bg=col, fg=C["fg"],
                 anchor="w", padx=28, pady=16,
                 ).pack(fill=tk.X)

        tk.Label(pnl, text=step["sub"],
                 font=("Segoe UI", 10),
                 bg=C["panel"], fg=C["dim"],
                 anchor="w", padx=28, pady=6,
                 ).pack(fill=tk.X)

        # body
        body = tk.Frame(pnl, bg=C["bg"], padx=28, pady=22)
        body.pack(fill=tk.BOTH, expand=True)

        tk.Label(body, text=step["desc"],
                 font=("Segoe UI", 10),
                 bg=C["bg"], fg=C["fg"],
                 justify="left", anchor="nw", wraplength=520,
                 ).pack(anchor="w")

        tk.Frame(body, bg=C["sep"], height=1).pack(fill=tk.X, pady=(20, 18))

        def _launch(s=step["script"]):
            subprocess.Popen([sys.executable, s])

        tk.Button(body,
                  text=step["btn"],
                  font=("Segoe UI", 11, "bold"),
                  bg=col, fg=C["fg"],
                  activebackground=col,
                  relief="flat", padx=22, pady=10,
                  cursor="hand2",
                  command=_launch,
                  ).pack(anchor="w")

        if i < len(STEPS) - 1:
            nxt = STEPS[i + 1]
            tk.Label(body,
                     text=f"Next:  Step {nxt['num']} — {nxt['title']}",
                     font=("Segoe UI", 9),
                     bg=C["bg"], fg=C["dim"],
                     ).pack(anchor="w", pady=(14, 0))

    # start on step 1
    _select(STEPS[0]["id"])
    root.mainloop()


if __name__ == "__main__":
    main()
