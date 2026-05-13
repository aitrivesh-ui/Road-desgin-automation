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
- **[Package README](civil3d_automation/README.md)** — M1–M8 layout, run order, testing, version control tips
- **[Testing guide (Markdown)](civil3d_automation/TESTING.md)** — validation steps and sample data (for editors and diffs)
- **[API notes](civil3d_automation/API_NOTES.md)** — Civil 3D / Dynamo assumptions after upgrades

## Tools (Python 3, not Civil’s IronPython)

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
