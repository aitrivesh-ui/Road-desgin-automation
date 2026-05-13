# Road design automation

Civil 3D–centric workflow: **CSV + JSON** drive alignments, profiles, corridors, volumes, signage, and BOQ-style rollups via **Dynamo (IronPython 2)** scripts, plus small **Python 3** helpers for data checks outside Civil. An **optional HTML handbook** explains the system for people; it is not part of the execution path.

> **Note:** This repo is tooling and documentation, not a substitute for engineering sign-off. You supply standards, template DWGs, and QA.

**Automation vs this handbook:** The runnable system is **`civil3d_automation/`** (Dynamo scripts, `config/project.json`, `csv/`, Python tools). Nothing in Civil 3D or those scripts reads or depends on any HTML file. **[`road_automation_complete.html`](road_automation_complete.html)** exists only to explain concepts and procedures for operators and reviewers.

## What is in this repository

| Area | Description |
|------|-------------|
| **[`civil3d_automation/`](civil3d_automation/)** | M1–M8 Python scripts for Dynamo, sample CSVs, `project.json`, Dynamo graph notes, preflight/clone/export tools, unit tests |
| **HTML handbook** (repo root, optional) | **[`road_automation_complete.html`](road_automation_complete.html)** — narrative for operators; **not** used by Dynamo or Python tools at runtime |

For a single **readable** walkthrough (install, testing, markings, advanced topics), open **[`road_automation_complete.html`](road_automation_complete.html)** in a browser—it is documentation only; skip it if you already know the workflow.

## Quick start

**Windows — optional Python helpers (preflight, tests, Excel export):** double-click **`install.bat`** at the repo root (or **`civil3d_automation\install_tools.bat`** if you only copied that folder). That checks for **Python 3.8+**, installs [`civil3d_automation/requirements-tools.txt`](civil3d_automation/requirements-tools.txt), and creates `config/project.json` from `project.example.json` only if `project.json` is missing. Use `install.bat --nopause` from a terminal to skip the final “Press any key” prompt.

1. Install **Autodesk Civil 3D** (2022+ recommended) with **Dynamo** and **IronPython 2** for Python Script nodes.
2. Get the **`civil3d_automation/`** package onto your machine (clone the repo, copy the folder, or use `clone_new_job.py`). **M8 and the Python tools only need that folder**—not the HTML handbook.
3. Prepare a **template DWG/DWT** once (layers, styles, assemblies, blocks)—see [`civil3d_automation/template/README.md`](civil3d_automation/template/README.md).
4. If you did not use the installer, copy [`civil3d_automation/config/project.example.json`](civil3d_automation/config/project.example.json) to `config/project.json`, then edit names/paths and fill CSVs (or use [`csv/templates/`](civil3d_automation/csv/templates/) as blanks).
5. Optional: run [`civil3d_automation/tools/run_preflight.bat`](civil3d_automation/tools/run_preflight.bat) or `python road_automation_preflight.py --validate path\to\project.json [--strict]`.
6. In Civil 3D, run **M8** from Dynamo Player with the **absolute path** to `config/project.json`.

## Documentation map

- **[Complete handbook (HTML)](road_automation_complete.html)** — explanatory guide for people (section index); **not read by Civil 3D or automation scripts**
- **[Civil 3D automation package](#civil-3d-automation-package)** (below) — M1–M8 layout, run order, idempotency, version control
- **[Testing guide (Markdown)](civil3d_automation/TESTING.md)** — validation steps and sample data (for editors and diffs)
- **[API notes](civil3d_automation/API_NOTES.md)** — Civil 3D / Dynamo assumptions after upgrades
- **[Preflight & tools](civil3d_automation/tools/README.md)** — `run_preflight.bat`, CLI validate, clone/export helpers

## Civil 3D automation package

The **`civil3d_automation/`** folder is the runnable **M1–M8** package: **IronPython** scripts for Dynamo for Civil 3D, sample **CSV** inputs, **`project.json`** for M8, and Markdown notes beside the code. **No HTML file is required at runtime**—Dynamo and the Python helpers use JSON, CSV, and your DWG only. **There is no `README.md` inside this folder**—all package documentation is in this root file (section below).

**Optional HTML:** [Handbook sections](road_automation_complete.html) — [# Overview](road_automation_complete.html#sec-ultimate), [# User guide / install](road_automation_complete.html#sec-user-guide), [# Beginner primer](road_automation_complete.html#sec-beginners), [# Testing](road_automation_complete.html#sec-testing), [# Markings](road_automation_complete.html#sec-marking), [# Advanced](road_automation_complete.html#sec-advanced).

### Package layout

| Path | Purpose |
|------|---------|
| [civil3d_automation/API_NOTES.md](civil3d_automation/API_NOTES.md) | API assumptions and verification checklist |
| [civil3d_automation/config/project.json](civil3d_automation/config/project.json) | Single config for M8 orchestrator |
| [civil3d_automation/config/project.example.json](civil3d_automation/config/project.example.json) | Starter copy for new jobs |
| [civil3d_automation/config/project.schema_notes.md](civil3d_automation/config/project.schema_notes.md) | Plain-language field reference for `project.json` |
| [civil3d_automation/csv/templates/](civil3d_automation/csv/templates/) | **Header-only CSV templates** + `RoadAutomation_DataStarter.xlsx` — copy into `csv/` and fill |
| [civil3d_automation/install_tools.bat](civil3d_automation/install_tools.bat) | One-click **pip install** for tool dependencies + optional `project.json` bootstrap |
| [civil3d_automation/tools/](civil3d_automation/tools/) | Windows **preflight** helper (validate paths/headers, copy JSON path) |
| [civil3d_automation/csv/](civil3d_automation/csv/) | Sample data (edit for your project) |
| [civil3d_automation/python/](civil3d_automation/python/) | One script per module — paste into Dynamo Python Script node |
| [civil3d_automation/dynamo/README_BUILD_GRAPHS.md](civil3d_automation/dynamo/README_BUILD_GRAPHS.md) | How to wire Dynamo Player graphs |
| [civil3d_automation/template/README.md](civil3d_automation/template/README.md) | What to put in your seed DWT/DWG |
| [civil3d_automation/out/qa/](civil3d_automation/out/qa/) | M8 appends a run log when `paths.qa_log` is set |

### Run order

1. Prepare template drawing (layers, styles, blocks, surfaces) — see [`civil3d_automation/template/README.md`](civil3d_automation/template/README.md).
2. **New full copy of this folder:** from **`civil3d_automation/`**, run `python tools/clone_new_job.py --dest "…\YourJob\civil3d_automation"` (see [`tools/README.md`](civil3d_automation/tools/README.md)), or copy `config/project.example.json` to `config/project.json` and copy header-only files from `csv/templates/` into `csv/`. On Windows, **`install_tools.bat`** can create `project.json` from the example if missing and install Python tool dependencies. Optionally run `tools/run_preflight.bat`.
3. Edit `config/project.json` and CSV files under `csv/`.
4. In Civil 3D, run **M1** then **M2**, … or run **M8** with the absolute path to `project.json`.
5. Run the **marking** graph (see [Markings hub](road_automation_complete.html#sec-marking) in the handbook) for each source line.
6. **M7** writes `out/boq_*.csv` for Excel / BOQ.

### Idempotency

- **M5** erases prior inserts tagged with the same XData app (`ROAD_SIGN_CSV` by default) before placing.
- **M1/M2** fail if the alignment/profile name already exists — delete or rename in Civil 3D before re-run.
- **M3** adds regions; duplicate region names may error — adjust CSV or clear regions in Civil UI.

### Version pinning

Record your Civil 3D year, Dynamo build, and Python engine in [`civil3d_automation/API_NOTES.md`](civil3d_automation/API_NOTES.md) after first successful run.

### Testing

See **[civil3d_automation/TESTING.md](civil3d_automation/TESTING.md)** for validation steps, sample CSV snippets, and Civil 3D run order. **HTML:** [Testing section](road_automation_complete.html#sec-testing) of the handbook.

From **`civil3d_automation/`** run [`run_tests.bat`](civil3d_automation/run_tests.bat) (or `python -m unittest discover -s tools -p "test_*.py" -v`). Requires Python 3; optional tests use **openpyxl** — run [`install_tools.bat`](civil3d_automation/install_tools.bat) once (or `pip install -r civil3d_automation/requirements-tools.txt`).

### Version control (recommended)

- Keep **`config/project.json`** and **`csv/*.csv`** on a branch or tag that matches each drawing issue (e.g. `issue/REV-B`).
- Do not commit machine-specific absolute paths inside JSON; use repo-relative `csv/…` paths as in `project.example.json`.
- Commit **`last_run_manifest.json`** only if you use it for audit trails; otherwise add it to `.gitignore` per team policy.

## Tools outside Civil 3D

Python 3 helpers on the workstation (not Dynamo’s IronPython).

| Entry | Purpose |
|--------|---------|
| **`install.bat`** (repo root) or **`civil3d_automation/install_tools.bat`** | One-step `pip install` for tool dependencies; creates `config/project.json` from `project.example.json` only if missing |
| `civil3d_automation/tools/road_automation_preflight.py` | Validate `project.json` paths and CSV headers; optional `--strict` data checks |
| `civil3d_automation/tools/clone_new_job.py` | Clone a fresh package folder with blank CSVs + `project.json` |
| `civil3d_automation/tools/export_workbook_to_csv.py` | Export starter `.xlsx` sheets to CSV (needs `openpyxl`) |
| `civil3d_automation/tools/design_check_outputs.py` | Quick read of volumes / BOQ CSVs after a run |

Details: [`civil3d_automation/tools/README.md`](civil3d_automation/tools/README.md).

## Tests

From `civil3d_automation/`:

```bat
run_tests.bat
```

## License

Add a `LICENSE` file if you want to open-source this repo explicitly; until then, all rights reserved unless you state otherwise.

## Author

Maintained by **[aitrivesh-ui](https://github.com/aitrivesh-ui)** — upstream repo: **[Road-desgin-automation](https://github.com/aitrivesh-ui/Road-desgin-automation)**.
