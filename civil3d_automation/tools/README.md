# Preflight helper (Windows + Python 3)

## Install Python tool dependencies (first time)

From the **`civil3d_automation`** folder (parent of this `tools` folder), double-click **`install_tools.bat`**, or from the repository root double-click **`install.bat`**. That runs `pip install -r requirements-tools.txt` and creates **`config/project.json`** from **`project.example.json`** only if `project.json` is missing. Civil 3D and Dynamo are installed separately.

---

Double-click **`run_preflight.bat`** (or run `python road_automation_preflight.py` from this folder).

**Documentation:** the optional HTML handbook is [`road_automation_complete.html`](../../road_automation_complete.html) at the repository root (for humans only; preflight and Dynamo do not use it).

## What it does

1. You select the **`civil3d_automation`** folder (it loads `config/project.json`) or pick `project.json` directly.
2. **Run checks** — Verifies that each input CSV referenced in `project.json` exists and that the **header row** includes every column the M1–M7 scripts expect.
3. **Volumes CSV** — If the file does not exist yet, you get an informational line (normal before M4). If it exists, headers are checked against the M4 output format.
4. Buttons **Open csv folder** / **Open config folder** — Opens Explorer on those subfolders.
5. **Copy project.json path** — Copies the absolute path for pasting into Dynamo Player as `IN[0]` for `m8_run_all.py`.

## Requirements

- **Python 3** on your PATH (the Civil 3D Dynamo IronPython runtime is separate; this tool uses normal Python 3).
- **Tkinter** — Included with the standard Windows Python installer. If you use a minimal embeddable build, install the full installer or add Tcl/Tk.

## Command line

**Validate only** (no GUI; works without tkinter — useful on minimal Python installs):

```bat
python road_automation_preflight.py --validate "D:\path\to\civil3d_automation\config\project.json" --strict
```

Add **`--strict`** to also check: at least two alignment PI rows, strictly increasing profile stations, non-overlapping corridor region station ranges, and `start_sta < end_sta` per region.

Exit code **1** if any line starts with `ERROR:`.

**GUI** with optional path preset:

```bat
python road_automation_preflight.py "D:\path\to\civil3d_automation\config\project.json"
```

The GUI opens with that file pre-selected (requires tkinter). Use the **Strict data checks** checkbox for the same rules as `--strict`. **Clone new job…** copies the whole `civil3d_automation` tree into `Parent\YourName\civil3d_automation` with fresh header-only CSVs and `config/project.json` from `project.example.json`.

## Clone new job (CLI)

```bat
python clone_new_job.py --dest "D:\jobs\RoadA\civil3d_automation" --number "PRJ-2026-ROADA" --force
```

`--force` deletes `dest` if it already exists. Omit `--number` to keep the example project number from `project.example.json`.

## Export workbook to CSV

```bat
pip install -r ..\requirements-tools.txt
python export_workbook_to_csv.py "..\csv\templates\RoadAutomation_DataStarter.xlsx" "D:\job\civil3d_automation\csv"
```

## Design check (post-run CSVs)

```bat
python design_check_outputs.py "D:\path\civil3d_automation\config\project.json"
```

## Automated tests

From the **`civil3d_automation`** folder (where `run_tests.bat` lives):

```bat
run_tests.bat
```

Or: `python -m unittest discover -s tools -p "test_*.py" -v`

## Excel starter workbook (optional)

To rebuild `csv/templates/RoadAutomation_DataStarter.xlsx` from the template CSV headers:

```bat
pip install -r ..\requirements-tools.txt
python build_starter_workbook.py
```

Run from the `tools` folder, or pass paths accordingly; see `build_starter_workbook.py` for the output location.
