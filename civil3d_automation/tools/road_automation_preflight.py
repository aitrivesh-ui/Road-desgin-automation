# -*- coding: utf-8 -*-
"""
Road automation preflight — validate project.json paths and CSV headers (Python 3).

Run: python road_automation_preflight.py
Or: run_preflight.bat from this folder (Windows).

CLI (no tkinter required):
  python road_automation_preflight.py --validate path\\to\\project.json [--strict]
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

from preflight_validate import root_from_project_json, validate_project, validation_failed

import clone_new_job


def run_cli(project_json: str, strict: bool = False) -> int:
    lines = validate_project(project_json, strict=strict)
    print("\n".join(lines))
    return 1 if validation_failed(lines) else 0


def run_gui(initial_json: str | None) -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext

    class PreflightApp(tk.Frame):
        def __init__(self, master: tk.Tk):
            super().__init__(master, padx=10, pady=10)
            self.master.title("Road automation — preflight")
            self.master.minsize(560, 420)
            self.project_json: str | None = None
            self.strict_var = tk.BooleanVar(value=False)

            row1 = tk.Frame(self)
            row1.pack(fill=tk.X)
            tk.Button(row1, text="Select civil3d_automation folder…", command=self._pick_root).pack(
                side=tk.LEFT, padx=(0, 8)
            )
            tk.Button(row1, text="Select project.json…", command=self._pick_json).pack(side=tk.LEFT)

            self.lbl_path = tk.Label(self, text="No folder selected.", anchor="w", justify=tk.LEFT)
            self.lbl_path.pack(fill=tk.X, pady=(8, 4))

            opt_row = tk.Frame(self)
            opt_row.pack(fill=tk.X)
            tk.Checkbutton(opt_row, text="Strict data checks (PI count, profile stations, region overlap)", variable=self.strict_var).pack(side=tk.LEFT)

            tk.Button(self, text="Run checks", command=self._run).pack(anchor="w", pady=(4, 0))

            self.txt = scrolledtext.ScrolledText(self, height=14, wrap=tk.WORD, font=("Consolas", 9))
            self.txt.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

            btn_row = tk.Frame(self)
            btn_row.pack(fill=tk.X, pady=(8, 0))
            tk.Button(btn_row, text="Open csv folder", command=self._open_csv).pack(side=tk.LEFT, padx=(0, 6))
            tk.Button(btn_row, text="Open config folder", command=self._open_config).pack(
                side=tk.LEFT, padx=(0, 6)
            )
            tk.Button(btn_row, text="Copy project.json path", command=self._copy_json).pack(side=tk.LEFT, padx=(0, 6))
            tk.Button(btn_row, text="Clone new job…", command=self._clone_job).pack(side=tk.LEFT)

            self.pack(fill=tk.BOTH, expand=True)

        def _default_project_json(self, root: str) -> str:
            return os.path.normpath(os.path.join(root, "config", "project.json"))

        def _pick_root(self) -> None:
            d = filedialog.askdirectory(title="Select civil3d_automation folder")
            if not d:
                return
            pj = self._default_project_json(d)
            self.project_json = pj
            self.lbl_path.config(text=pj if os.path.isfile(pj) else d + " (no config/project.json yet)")

        def _pick_json(self) -> None:
            f = filedialog.askopenfilename(
                title="Select project.json",
                filetypes=[("JSON", "*.json"), ("All", "*.*")],
            )
            if not f:
                return
            self.project_json = os.path.normpath(f)
            self.lbl_path.config(text=self.project_json)

        def _run(self) -> None:
            self.txt.delete("1.0", tk.END)
            if not self.project_json:
                self.txt.insert(tk.END, "Select a folder or project.json first.\n")
                return
            for line in validate_project(self.project_json, strict=self.strict_var.get()):
                self.txt.insert(tk.END, line + "\n")

        def _clone_job(self) -> None:
            from tkinter import simpledialog

            parent = filedialog.askdirectory(title="Select parent folder for the new job (new subfolder will be created)")
            if not parent:
                return
            name = simpledialog.askstring(
                "New job",
                "New folder name (will contain civil3d_automation inside):",
                initialvalue="MyRoadJob",
            )
            if not name or not str(name).strip():
                return
            dest = os.path.normpath(os.path.join(parent, str(name).strip(), "civil3d_automation"))
            if os.path.exists(dest):
                if not messagebox.askyesno(
                    "Clone",
                    "Folder already exists:\n%s\nDelete and replace?" % dest,
                ):
                    return
                shutil.rmtree(dest, ignore_errors=True)
            src = root_from_project_json(self.project_json) if self.project_json and os.path.isfile(self.project_json) else None
            if not src or not os.path.isdir(os.path.join(src, "python")):
                src = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
            try:
                pj = clone_new_job.clone_package(dest, source_root=src, project_number=None, force=False)
                messagebox.showinfo("Clone", "Created:\n%s\n\nConfig:\n%s" % (dest, pj))
            except Exception as ex:
                messagebox.showerror("Clone", str(ex))

        def _root(self) -> str | None:
            if not self.project_json or not os.path.isfile(self.project_json):
                return None
            return root_from_project_json(self.project_json)

        def _open_csv(self) -> None:
            root = self._root()
            if not root:
                messagebox.showwarning("Preflight", "Select a valid project.json first.")
                return
            path = os.path.join(root, "csv")
            self._open_in_explorer(path)

        def _open_config(self) -> None:
            root = self._root()
            if not root:
                messagebox.showwarning("Preflight", "Select a valid project.json first.")
                return
            path = os.path.join(root, "config")
            self._open_in_explorer(path)

        @staticmethod
        def _open_in_explorer(path: str) -> None:
            path = os.path.abspath(path)
            if not os.path.isdir(path):
                messagebox.showwarning("Preflight", "Folder does not exist: " + path)
                return
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.run(["xdg-open", path], check=False)

        def _copy_json(self) -> None:
            if not self.project_json or not os.path.isfile(self.project_json):
                messagebox.showwarning("Preflight", "No valid project.json selected.")
                return
            p = os.path.abspath(self.project_json)
            top = self.winfo_toplevel()
            top.clipboard_clear()
            top.clipboard_append(p)
            messagebox.showinfo("Preflight", "Copied to clipboard:\n" + p)

    root = tk.Tk()
    app = PreflightApp(root)
    if initial_json and os.path.isfile(initial_json):
        app.project_json = os.path.normpath(os.path.abspath(initial_json))
        app.lbl_path.config(text=app.project_json)
    root.mainloop()


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] == "--validate":
        strict = "--strict" in argv
        rest = [a for a in argv[1:] if a != "--strict"]
        if not rest:
            print(
                "Usage: python road_automation_preflight.py --validate path\\to\\project.json [--strict]",
                file=sys.stderr,
            )
            sys.exit(2)
        sys.exit(run_cli(rest[0], strict=strict))
    initial: str | None = None
    if argv and os.path.isfile(argv[0]):
        initial = argv[0]
    try:
        run_gui(initial)
    except ImportError as ex:
        if "tkinter" in str(ex).lower():
            print(
                "Tkinter is not available. Use CLI mode:\n"
                "  python road_automation_preflight.py --validate path\\to\\project.json",
                file=sys.stderr,
            )
            if initial:
                sys.exit(run_cli(initial))
            sys.exit(2)
        raise


if __name__ == "__main__":
    main()
