# Civil 3D automation package

Runnable **M0–M8** pipeline: Dynamo (IronPython 2) scripts, `config/project.json`, sample `csv/`, and Python 3 validation tools.

## Documentation

| File | Purpose |
|------|---------|
| **[TESTING.md](TESTING.md)** | Full test procedures (Markdown, for diffs and editors) |
| **[../testing_guide.html](../testing_guide.html)** | Same workflow in the browser — start here for step-by-step QA |

## Quick start

1. Run **`install_tools.bat`** (or repo-root **`install.bat`**) once for Python 3 tools.
2. Copy `config/project.example.json` → `config/project.json` if needed; edit paths and CSVs.
3. Prepare a Civil 3D template DWG (layers in `template/layers_bim.csv`, assemblies/surfaces per `names` in `project.json`).
4. **Without Civil:** `run_tests.bat` and `python tools\road_automation_preflight.py --validate config\project.json`
5. **With Civil 3D:** Dynamo Player → `m8_run_all.py` → **IN[0]** = absolute path to `config\project.json`

## M8 run order

Default: `m1 → m2 → m3 → m4 → m0 → m5 → m6 → m7`

| Step | Script | Role |
|------|--------|------|
| m1 | `m1_alignment_from_csv.py` | Alignment + `out/curve_table.csv` |
| m2 | `m2_profile_from_csv.py` | Profile + `out/pvi_table.json` |
| m3 | `m3_corridor_regions_from_csv.py` | Corridor regions + IRC:37 cache |
| m4 | `m4_corridor_rebuild_volumes.py` | Volumes, mass haul, fill depth |
| m0 | `m0_markings_from_config.py` | Road markings (after M1) |
| m5 | `m5_signage_from_csv.py` | Signage blocks |
| m6 | `m6_sheets_helper.py` | DPR sheet manifest (handbook M07) |
| m7 | `m7_boq_rollup.py` | BOQ CSV (handbook M06) |

Paste each script from `python/` into a Dynamo **Python Script** node (IronPython 2). Save graphs under `dynamo/`.

## Layout

| Path | Purpose |
|------|---------|
| `config/` | `project.json`, catalogues, state SOR rates |
| `csv/` | Project inputs; blanks in `csv/templates/` |
| `python/` | Module scripts for Dynamo |
| `tools/` | Preflight, tests, design checks |
| `out/` | Generated artifacts after a run |
