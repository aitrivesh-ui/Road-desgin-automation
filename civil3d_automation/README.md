# Civil 3D M1–M8 automation package

This folder implements the construction plan: runnable **IronPython** scripts for Dynamo for Civil 3D, sample **CSV** inputs, **`project.json`** for M8, and Markdown notes. **No HTML file is required at runtime**—Dynamo and the Python helpers use JSON, CSV, and your DWG only.

**Handbook (optional reading):** [road_automation_complete.html](../road_automation_complete.html) — one file with sections: [#sec-ultimate](../road_automation_complete.html#sec-ultimate) overview, [#sec-user-guide](../road_automation_complete.html#sec-user-guide) install and run order, [#sec-beginners](../road_automation_complete.html#sec-beginners) primer, [#sec-testing](../road_automation_complete.html#sec-testing) testing, [#sec-marking](../road_automation_complete.html#sec-marking) markings, [#sec-advanced](../road_automation_complete.html#sec-advanced) advanced playbook.

## Install (Windows, Python helpers)

Double-click **`install_tools.bat`** in this folder (or **`install.bat`** in the repo root). That installs `requirements-tools.txt` with your **Python 3.8+** (`py -3` or `python` on PATH) and creates **`config/project.json`** from **`project.example.json`** only if `project.json` is absent. Civil 3D, Dynamo, and IronPython are installed separately with Autodesk software; this step covers preflight, unit tests, and optional Excel tooling only.

## Layout

| Path | Purpose |
|------|---------|
| [API_NOTES.md](API_NOTES.md) | API assumptions and verification checklist |
| [config/project.json](config/project.json) | Single config for M8 orchestrator |
| [config/project.example.json](config/project.example.json) | Starter copy for new jobs |
| [config/project.schema_notes.md](config/project.schema_notes.md) | Plain-language field reference for `project.json` |
| [csv/templates/](csv/templates/) | **Header-only CSV templates** + `RoadAutomation_DataStarter.xlsx` — copy into `csv/` and fill |
| [install_tools.bat](install_tools.bat) | One-click **pip install** for tool dependencies + optional `project.json` bootstrap |
| [tools/](tools/) | Windows **preflight** helper (validate paths/headers, copy JSON path) |
| [csv/](csv/) | Sample data (edit for your project) |
| [python/](python/) | One script per module — paste into Dynamo Python Script node |
| [dynamo/README_BUILD_GRAPHS.md](dynamo/README_BUILD_GRAPHS.md) | How to wire Dynamo Player graphs |
| [template/README.md](template/README.md) | What to put in your seed DWT/DWG |
| [out/qa/](out/qa/) | M8 appends a run log when `paths.qa_log` is set |

## Run order

1. Prepare template drawing (layers, styles, blocks, surfaces) — see `template/README.md`.
2. **New full copy of this folder:** run `python tools/clone_new_job.py --dest "…\YourJob\civil3d_automation"` (see `tools/README.md`), or copy `config/project.example.json` to `config/project.json` and copy header-only files from `csv/templates/` into `csv/`. On Windows, **`install_tools.bat`** can create `project.json` from the example if missing and install Python tool dependencies. Optionally run `tools/run_preflight.bat`.
3. Edit `config/project.json` and CSV files under `csv/`.
4. In Civil 3D, run **M1** then **M2**, … or run **M8** with absolute path to `project.json`.
5. Run the **marking** graph (see [Markings hub](../road_automation_complete.html#sec-marking) in the handbook) for each source line.
6. **M7** writes `out/boq_*.csv` for Excel / BOQ.

## Idempotency

- **M5** erases prior inserts tagged with the same XData app (`ROAD_SIGN_CSV` by default) before placing.
- **M1/M2** fail if the alignment/profile name already exists — delete or rename in Civil 3D before re-run.
- **M3** adds regions; duplicate region names may error — adjust CSV or clear regions in Civil UI.

## Version pinning

Record your Civil 3D year, Dynamo build, and Python engine in `API_NOTES.md` after first successful run.

## Related docs

- [road_automation_complete.html](../road_automation_complete.html#sec-beginners) — concepts, glossary, error hints  
- [road_automation_complete.html](../road_automation_complete.html#sec-marking) — marking module + pipeline overview  
- [road_automation_complete.html](../road_automation_complete.html#sec-advanced) — extended playbook narrative

## Testing

See **[TESTING.md](TESTING.md)** for validation steps, sample CSV snippets, and Civil 3D run order. **HTML:** [road_automation_complete.html](../road_automation_complete.html#sec-testing).

From the `civil3d_automation` folder run [`run_tests.bat`](run_tests.bat) (or `python -m unittest discover -s tools -p "test_*.py" -v`). Requires Python 3; optional tests use **openpyxl** — run [`install_tools.bat`](install_tools.bat) once (or `pip install -r requirements-tools.txt`).

## Version control (recommended)

- Keep **`config/project.json`** and **`csv/*.csv`** on a branch or tag that matches each drawing issue (e.g. `issue/REV-B`).  
- Do not commit machine-specific absolute paths inside JSON; use repo-relative `csv/…` paths as in `project.example.json`.  
- Commit **`last_run_manifest.json`** only if you use it for audit trails; otherwise add it to `.gitignore` per team policy.
