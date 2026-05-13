# Testing the road design automation

**Web version (optional):** [road_automation_complete.html](../road_automation_complete.html#sec-testing) — same topics as a single HTML page for browsers; **not used** by preflight, Dynamo, or tests.

This document describes how to validate inputs, run automated checks outside Civil 3D, and exercise the Dynamo (M1–M8) pipeline with the **sample CSVs** shipped in this repo.

For installation and graph wiring, see [road_automation_complete.html — User guide](../road_automation_complete.html#sec-user-guide) and [dynamo/README_BUILD_GRAPHS.md](dynamo/README_BUILD_GRAPHS.md). On Windows, run **`install.bat`** at the repo root or **`install_tools.bat`** in this folder once to install Python 3 tool dependencies (`requirements-tools.txt`) and bootstrap `config/project.json` if needed.

---

## 1. What you are testing

| Layer | What runs | Purpose |
|--------|-----------|---------|
| **Python 3 tools** | `tools/road_automation_preflight.py`, `design_check_outputs.py`, unit tests | CSV headers, paths, optional geometry rules; smoke checks without Civil 3D |
| **Civil 3D + Dynamo** | `python/m8_run_all.py` (or M1→M7 individually) | End-to-end automation against a template DWG |

---

## 2. Prerequisites

- **Python 3** on your PATH (separate from Civil 3D’s IronPython 2).
- Optional: run **`install_tools.bat`** in this folder (or **`install.bat`** at the repo root) once — same as `pip install -r requirements-tools.txt` — for workbook export tests and tooling extras.
- **Civil 3D** with Dynamo and IronPython 2 for full pipeline tests.
- A **template drawing** (layers, styles, assembly names, EG/FG surfaces) that matches the names in `config/project.json` — see [template/README.md](template/README.md).

---

## 3. Sample data in this repository

The folder **`csv/`** contains editable examples you can use for a first run:

| File | Role |
|------|------|
| [csv/alignment_pi.csv](csv/alignment_pi.csv) | PI coordinates for **M1** (four points `A1`–`A4`) |
| [csv/profile_pvis.csv](csv/profile_pvis.csv) | Profile PVIs for **M2** (stations 0 → 1100 m) |
| [csv/section_widths.csv](csv/section_widths.csv) | Corridor regions for **M3** (`R1`: 0–800, `R2`: 800–1400) |
| [csv/signage_schedule.csv](csv/signage_schedule.csv) | Sign inserts for **M5** |
| [csv/payitems.csv](csv/payitems.csv) | Pay-item mapping for **M7** BOQ rollup |

Configuration is **`config/project.json`** (copy from [config/project.example.json](config/project.example.json), or on Windows run **`install_tools.bat`** / repo-root **`install.bat`** if `project.json` is missing). Paths inside JSON are **relative to the `civil3d_automation` folder** (the package root), not to the JSON file.

**Expected CSV column headers** (must match exactly; UTF-8 with BOM is fine):

| CSV key in `project.json` | Required columns |
|---------------------------|------------------|
| `paths.alignment_pi` | `pi_id`, `easting`, `northing`, `radius_m`, `spiral_in_m`, `spiral_out_m`, `design_speed_kph` |
| `paths.profile_pvis` | `station_m`, `elevation_m`, `k_crest`, `k_sag`, `curve_length_m` |
| `paths.section_widths` | `region_id`, `start_sta`, `end_sta`, `lane_width_m`, `shoulder_l_m`, `shoulder_r_m`, `target_l`, `target_r` |
| `paths.signage` | `row`, `station_m`, `offset_m`, `side`, `sign_code`, `block_name`, `rotation_deg` |
| `paths.payitems` | `source`, `key`, `pay_item`, `description`, `unit` |

After **M4**, `paths.volumes_csv` (default `out/volumes.csv`) should contain: `corridor`, `eg_surface`, `fg_surface`, `volume_surface`, `cut_m3`, `fill_m3`, `net_m3`.

Blank templates: [csv/templates/](csv/templates/).

---

## 4. Minimal copy-paste samples (strict-friendly)

Use these if you want the smallest valid datasets for **`--strict`** preflight (at least two alignment PIs, strictly increasing profile stations, non-overlapping regions, `start_sta < end_sta`).

**`alignment_pi.csv`**

```csv
pi_id,easting,northing,radius_m,spiral_in_m,spiral_out_m,design_speed_kph
A1,5000,8000,0,0,0,80
A2,5200,8120,0,0,0,80
```

**`profile_pvis.csv`**

```csv
station_m,elevation_m,k_crest,k_sag,curve_length_m
0,212.5,0,0,0
100,214,0,0,0
```

**`section_widths.csv`**

```csv
region_id,start_sta,end_sta,lane_width_m,shoulder_l_m,shoulder_r_m,target_l,target_r
R1,0,100,3.5,2,2,EOP_L,EOP_R
```

**`signage_schedule.csv`** (one row example)

```csv
row,station_m,offset_m,side,sign_code,block_name,rotation_deg
1,10,4.5,L,X,BLK,
```

**`payitems.csv`** (links volume keys to pay items)

```csv
source,key,pay_item,description,unit
volumes,cut_m3,1,cut,m3
volumes,fill_m3,1,fill,m3
```

Replace block names, targets (`EOP_L` / `EOP_R`), and assembly names with objects that exist in **your** template DWG.

---

## 5. Step-by-step: validate before Civil 3D

If you have not installed Python tool dependencies yet, run **`install_tools.bat`** in this folder (or **`install.bat`** at the repo root) once.

1. Open a terminal **in the `civil3d_automation` folder** (the directory that contains `config/`, `csv/`, `python/`, `tools/`).
2. **Header and path validation** (no GUI):

   ```bat
   python tools\road_automation_preflight.py --validate "%CD%\config\project.json"
   ```

3. Add **strict data checks** (alignment PI count, profile station order, region overlaps):

   ```bat
   python tools\road_automation_preflight.py --validate "%CD%\config\project.json" --strict
   ```

   Exit code **1** means at least one line starts with `ERROR:`.

4. Optional: double-click **`tools/run_preflight.bat`** for the GUI (select the same `project.json`). Use **Strict data checks** for the same rules as `--strict`.

5. **Clone a clean job** (optional):

   ```bat
   python tools\clone_new_job.py --dest "D:\jobs\Demo\civil3d_automation" --number "PRJ-2026-DEMO"
   ```

   Then edit the new `config/project.json` and fill `csv/*.csv`.

---

## 6. Step-by-step: automated unit tests (Python 3)

From the **`civil3d_automation`** directory:

```bat
run_tests.bat
```

Or:

```bat
python -m unittest discover -s tools -p "test_*.py" -v
```

These tests cover preflight validation (including strict rules), `clone_new_job`, `design_check_outputs`, and workbook export when `csv/templates/RoadAutomation_DataStarter.xlsx` is present.

---

## 7. Step-by-step: test inside Civil 3D (M8)

1. Complete sections **3–5** so preflight passes for your `project.json`.
2. Open your **template DWG** in Civil 3D; confirm surfaces, alignment/profile styles, **assembly** name (e.g. `BasicLaneAssembly` in [config/project.example.json](config/project.example.json)), and layer names match `project.json` → `names` and `styles`.
3. In Dynamo Player, run the graph that hosts **`m8_run_all.py`**.
4. **IN[0]**: absolute path to `config/project.json`, for example:

   `D:\road desgin automation\civil3d_automation\config\project.json`

5. **IN[1]** (optional): comma-separated steps, default `m1,m2,m3,m4,m5,m6,m7`. Examples:
   - `m1,m2` — alignment and profile only  
   - `m1,m2,m3,m4` — stop before signage/BOQ  

6. After a successful run, check:
   - **`out/volumes.csv`** (after M4)
   - **`out/boq.csv`** or path set in `paths.boq_csv` (after M7)
   - **`out/qa/run_log.txt`** and **`out/qa/last_run_manifest.json`** if `paths.qa_log` is set

7. **Post-run CSV check** (Python 3):

   ```bat
   python tools\design_check_outputs.py "%CD%\config\project.json"
   ```

---

## 8. Idempotency and re-runs (manual QA)

- **M1 / M2**: Re-running with the same alignment or profile **name** may fail; delete or rename the Civil object first.
- **M5**: Prior inserts with the same XData app id are removed before re-insert (see package [README.md](README.md)).
- **M3**: Duplicate `region_id` values or overlapping station ranges can error; adjust the CSV or clear regions in Civil.

---

## 9. Troubleshooting quick map

| Symptom | Likely cause |
|---------|----------------|
| `ERROR:` from preflight — missing column | CSV header typo or extra space; compare to section 3 table |
| Strict: “at least 2 PI data rows” | Only one data row in `alignment_pi.csv` |
| Strict: “station_m … strictly increasing” | Profile stations out of order or duplicated |
| Strict: “overlapping regions” | `section_widths` station ranges overlap on the station line (not merely touching at one chainage) |
| Dynamo: CSV not found | Wrong `project.json` path or paths in JSON not relative to package root |
| M4/M7 odd results | Template missing EG/FG, wrong corridor/surface names |

For Dynamo `ERROR:` strings and glossary, see [road_automation_complete.html — Beginner primer](../road_automation_complete.html#sec-beginners).
