# Testing the Road Design Automation — M1 to M20

**Web reference:** [road_automation_complete.html](../road_automation_complete.html) — same topics as a single-page HTML guide for offline browsers.

This document covers validating inputs, running automated checks outside Civil 3D, testing the full M1–M20 pipeline, and verifying outputs.  For installation and Dynamo graph wiring, see [dynamo/README_BUILD_GRAPHS.md](dynamo/README_BUILD_GRAPHS.md).  On Windows, run **`install.bat`** at the repo root (or **`install_tools.bat`** in this folder) once to install Python 3 dependencies.

---

## 1. Pipeline overview

| Group | Modules | Where it runs |
|-------|---------|--------------|
| **Geometry build** | M1 Alignment, M2 Profile, M3 Corridor, M4 Volumes | Civil 3D via Dynamo (`m8_run_all.py`) |
| **Output generation** | M5 Signage, M6 Sheets helper, M7 BOQ | Civil 3D via Dynamo |
| **Road markings & sections** | M9 Markings, M10 Cross-sections, M11 Superelevation | Civil 3D via Dynamo |
| **Analysis & sheets** | M12 Mass haul, M13 Plan sheets, M14 Long-section sheets, M15 Standard details | Civil 3D via Dynamo |
| **Design tools** | M16 Pavement, M17 Drainage, M18 Intersections | Python 3 — standalone |
| **Reporting** | M19 Report generator, M20 Design verifier | Python 3 — standalone |

**Quickest path to run everything:**
```bat
python tools\pipeline_launcher.py
```
The launcher shows a checkbox list for all M1–M20, generates the Dynamo step-filter string for M1–M15, and runs M16–M20 directly.

---

## 2. Prerequisites

| Requirement | Notes |
|-------------|-------|
| **Python 3.8+** on PATH | Separate from Civil 3D's IronPython 2 |
| **openpyxl** | `pip install -r requirements-tools.txt` (or run `install_tools.bat`) |
| **Civil 3D 2022+** with Dynamo | For M1–M15 |
| **Template DWG** | Layers, styles, assembly names, EG surface — see [template/README.md](template/README.md) |

---

## 3. Input CSV files

### 3a. Required CSVs (M1–M8)

| `project.json` key | File | Module | Required columns |
|--------------------|------|--------|-----------------|
| `paths.alignment_pi` | `csv/alignment_pi.csv` | M1 | `pi_id`, `easting`, `northing`, `radius_m`, `spiral_in_m`, `spiral_out_m`, `design_speed_kph` |
| `paths.profile_pvis` | `csv/profile_pvis.csv` | M2 | `station_m`, `elevation_m`, `k_crest`, `k_sag`, `curve_length_m` |
| `paths.section_widths` | `csv/section_widths.csv` | M3 | `region_id`, `start_sta`, `end_sta`, `lane_width_m`, `shoulder_l_m`, `shoulder_r_m`, `target_l`, `target_r` |
| `paths.signage` | `csv/signage_schedule.csv` | M5 | `row`, `station_m`, `offset_m`, `side`, `sign_code`, `block_name`, `rotation_deg` |
| `paths.payitems` | `csv/payitems.csv` | M7 | `source`, `key`, `pay_item`, `description`, `unit` |

### 3b. New CSVs (M9–M18)

| `project.json` key | File | Module | Required columns |
|--------------------|------|--------|-----------------|
| `paths.road_markings` | `csv/road_markings.csv` | M9 | `mark_id`, `station_start_m`, `station_end_m`, `offset_m`, `side`, `mark_type`, `width_m` |
| `paths.sections` | `csv/sections.csv` | M10 | `station_m`, `label`, `left_width_m`, `right_width_m` *(optional — auto-generated if absent)* |
| `paths.superelevation` | `csv/superelevation.csv` | M11 | `station_m`, `left_slope_pct`, `right_slope_pct`, `transition_length_m` |
| `paths.pavement_inputs` | `csv/pavement_inputs.csv` | M16 | `region_id`, `start_sta`, `end_sta`, `traffic_esa_million`, `subgrade_cbr`, `design_life_years` |
| `paths.catchments` | `csv/catchments.csv` | M17 | `catchment_id`, `area_ha`, `runoff_coeff`, `tc_minutes`, `rainfall_intensity_mmh`, `station_m`, `offset_m`, `side` |
| `paths.intersections` | `csv/intersections.csv` | M18 | `int_id`, `station_m`, `road_name`, `angle_deg`, `left_turn_lanes`, `right_turn_lanes`, `radius_m`, `approach_speed_kph` |

Blank header-only templates for every CSV are in **`csv/templates/`**.  To generate the full Excel starter workbook with example rows and dropdowns:
```bat
python tools\build_starter_workbook.py
```

### 3c. Minimal sample data (strict-friendly)

**`alignment_pi.csv`**
```csv
pi_id,easting,northing,radius_m,spiral_in_m,spiral_out_m,design_speed_kph
A1,5000,8000,0,0,0,80
A2,5200,8120,300,0,0,80
A3,5600,8300,0,0,0,80
```

**`profile_pvis.csv`**
```csv
station_m,elevation_m,k_crest,k_sag,curve_length_m
0,212.5,0,0,0
300,215.0,40,0,0
700,213.0,0,35,0
```

**`section_widths.csv`**
```csv
region_id,start_sta,end_sta,lane_width_m,shoulder_l_m,shoulder_r_m,target_l,target_r
R1,0,500,3.5,1.5,1.5,EG,EG
R2,500,700,3.5,2.0,2.0,EG,EG
```

**`road_markings.csv`**
```csv
mark_id,station_start_m,station_end_m,offset_m,side,mark_type,width_m,dash_length_m,gap_length_m
RM-001,0,700,0,C,CENTRE_DASH,0.15,3,9
RM-002,0,700,3.5,L,EDGE_SOLID,0.15,0,0
RM-003,0,700,3.5,R,EDGE_SOLID,0.15,0,0
```

**`pavement_inputs.csv`**
```csv
region_id,start_sta,end_sta,traffic_esa_million,subgrade_cbr,design_life_years
R1,0,500,2.5,6,20
R2,500,700,1.0,8,20
```

**`catchments.csv`**
```csv
catchment_id,area_ha,runoff_coeff,tc_minutes,rainfall_intensity_mmh,station_m,offset_m,side,invert_us_m,invert_ds_m,slope_pct,length_m
CA-001,3.2,0.70,18,95,350,8.0,R,0,0,1.0,12
```

**`intersections.csv`**
```csv
int_id,station_m,road_name,angle_deg,left_turn_lanes,right_turn_lanes,radius_m,approach_speed_kph
INT-001,400,Side Road 1,0,1,1,10,60
```

---

## 4. Step 1 — Preflight (no Civil 3D needed)

From the **`civil3d_automation`** directory:

```bat
rem Basic header + path check
python tools\road_automation_preflight.py --validate "%CD%\config\project.json"

rem Add strict data checks (PI count, station order, region overlaps)
python tools\road_automation_preflight.py --validate "%CD%\config\project.json" --strict
```

Exit code **1** means at least one `ERROR:` line was found.

Or open the GUI:
```bat
tools\run_preflight.bat
```

Expected output for a passing run:
```
OK: alignment_pi.csv — columns match.
OK: profile_pvis.csv — columns match.
OK: section_widths.csv — columns match.
OK: signage — columns match.
OK: payitems — columns match.
OK: road_markings.csv — columns match.
...
```

---

## 5. Step 2 — DGPS survey → CSV (optional)

If your input geometry comes from a DGPS survey file:

```bat
rem Auto-detect format (Generic CSV, Trimble DC, Leica GSI, LandXML, Lat/Lon)
python tools\survey_to_csv.py --cli survey_data.csv

rem Explicit format
python tools\survey_to_csv.py --cli survey_data.gsi --format gsi

rem GUI wizard
python tools\survey_to_csv.py
```

The tool writes `alignment_pi.csv`, `profile_pvis.csv`, `section_widths.csv`, and `signage_schedule.csv` ready for use in M1–M5.

---

## 6. Step 3 — Automated unit tests (Python 3)

From the **`civil3d_automation`** directory:

```bat
run_tests.bat
```

Or directly:
```bat
python -m unittest discover -s tools -p "test_*.py" -v
```

Covers preflight validation (including strict rules), `clone_new_job`, `design_check_outputs`, and workbook export.

---

## 7. Step 4 — Run M1–M15 in Civil 3D (Dynamo)

### Option A — Pipeline Launcher (recommended)

```bat
python tools\pipeline_launcher.py
```

1. On the **Select Modules** tab, check/uncheck any combination of M1–M20.
2. Switch to **Dynamo (M1–M15)** tab — the step-filter string updates live.  Click **Copy to clipboard**.
3. In Dynamo Player, open the graph that hosts `m8_run_all.py`.
4. Set **IN[0]** to the absolute path of `config/project.json`.
5. Set **IN[1]** to the copied filter string (or leave blank to run all M1–M15).
6. Run the graph.

### Option B — Dynamo Player manually

| Dynamo input | Value |
|---|---|
| `IN[0]` | Absolute path to `config/project.json`, e.g. `D:\project\civil3d_automation\config\project.json` |
| `IN[1]` | Step filter (optional). Leave blank = run all. Examples below. |

**Step filter examples:**

| Filter string | What runs |
|---|---|
| *(blank)* | All M1–M15 in order |
| `m1,m2,m3,m4` | Geometry build only |
| `m9,m10,m11` | Road markings, cross-sections, superelevation |
| `m12,m13,m14,m15` | Mass haul + sheet generation |
| `m4` | Rebuild volumes only (re-run after corridor edit) |

### What to check after the Dynamo run

| Output | Path | Created by |
|--------|------|-----------|
| Volumes CSV | `out/volumes.csv` | M4 |
| BOQ CSV | `out/boq.csv` | M7 |
| Sections list | `out/sections_list.csv` | M10 |
| Mass haul CSV | `out/mass_haul.csv` | M12 |
| QA log | `out/qa/run_log.txt` | M8 |
| Last run manifest | `out/qa/last_run_manifest.json` | M8 |

---

## 8. Step 5 — Run M16–M20 Python tools

### Option A — Pipeline Launcher

In the launcher's **Python Tools (M16–M20)** tab:
1. Check the tools you want to run.
2. Click **Run selected Python 3 tools**.  Status badges update live; output streams to the log panel.

### Option B — Command line

```bat
rem M16 — Pavement design
python tools\pavement_design.py --cli csv\pavement_inputs.csv --out out\pavement_design.csv

rem M17 — Drainage design
python tools\drainage_design.py --cli csv\catchments.csv --out out\drainage_design.csv

rem M18 — Intersection design
python tools\intersection_design.py --cli csv\intersections.csv

rem M19 — Excel report
python tools\report_generator.py config\project.json

rem M20 — Design verifier
python tools\design_verifier.py config\project.json
```

### Option C — GUI for each tool

Each Python 3 tool has its own tkinter GUI — just run it without arguments:
```bat
python tools\pavement_design.py
python tools\drainage_design.py
python tools\intersection_design.py
```

### Expected outputs

| Output file | Module | Contents |
|-------------|--------|---------|
| `out/pavement_design.csv` | M16 | Total thickness, layer split, materials per region |
| `out/drainage_design.csv` | M17 | Culvert diameter, HW/D ratio, flow per catchment |
| `out/intersection_geometry.csv` | M18 | Kerb return length, turn lane length, SSD |
| `out/offset_alignment_inputs.csv` | M18 | Offset data for Civil 3D import |
| `out/report/design_report.xlsx` | M19 | Multi-sheet Excel with charts |
| `out/design_verification.txt` | M20 | OK / WARN / ERROR cross-checks |

---

## 9. Step 6 — Post-run output check

```bat
python tools\design_check_outputs.py "%CD%\config\project.json"
```

Then run the **design verifier** for a full pass/fail report:

```bat
python tools\design_verifier.py config\project.json
```

M20 checks:
- Alignment radii vs minimum for design speed
- Profile grades within `design.max_grade_pct` / `design.min_grade_pct`
- Cut/fill volumes non-zero, cut:fill ratio
- Pavement thickness sanity (200–1000 mm)
- Culvert HW/D ≤ 1.5
- BOQ quantities vs volume CSV consistency
- Mass haul peak surplus/deficit thresholds

Exit code 0 = PASS, 1 = at least one ERROR.

---

## 10. Idempotency and re-runs

| Module | Behaviour on re-run |
|--------|---------------------|
| M1 / M2 | Delete or rename the existing Civil alignment/profile object first |
| M3 | Clear existing corridor regions before re-applying |
| M5 | Prior sign blocks tagged with XData `ROAD_SIGN_CSV` are erased before re-insert |
| M9 | Prior marking entities tagged with `ROAD_MARK_CSV` are erased before re-draw |
| M10 | `_get_or_create_slg()` reuses an existing SampleLineGroup by name |
| M13 / M14 | Layouts named `PLAN-001`, `LS-001` etc. are skipped if they already exist |
| M16–M20 | Always overwrite output CSVs / TXT — safe to re-run |

---

## 11. Troubleshooting quick map

| Symptom | Likely cause |
|---------|-------------|
| `ERROR: … missing column` | CSV header typo or extra space — compare to section 3 tables |
| Strict: "at least 2 PI data rows" | Only one data row in `alignment_pi.csv` |
| Strict: "station_m strictly increasing" | Profile stations out of order or duplicated |
| Strict: "overlapping regions" | `section_widths` station ranges overlap |
| `ERROR: Alignment not found: DEMO-CL` | `names.alignment` in `project.json` doesn't match the Civil 3D object name |
| M4/M7 odd results | Template missing EG/FG surface, or wrong corridor/surface names in `project.json` |
| M9: block not found | Block definition `MARK_<type>` not present in the DWG — M9 logs a WARN and continues |
| M16: KeyError | `pavement_inputs.csv` missing a required column — run preflight first |
| M17: `NO FIT` status | Catchment peak flow exceeds largest culvert (3000 mm) — consider twin culvert or box |
| M19: `openpyxl` import error | Run `pip install openpyxl` or `install_tools.bat` |
| Pipeline launcher: tools not running | Ensure `config/project.json` path is set correctly on the launcher's Select Modules tab |

---

## 12. Full end-to-end checklist

```
[ ] 1. Fill CSV data (use build_starter_workbook.py for guided Excel template)
[ ] 2. Run preflight:          python tools\road_automation_preflight.py --validate config\project.json --strict
[ ] 3. Open project DWG in Civil 3D (layers, styles, assembly, EG surface ready)
[ ] 4. Launch pipeline UI:     python tools\pipeline_launcher.py
[ ] 5. Select modules → copy Dynamo step filter → run m8_run_all in Dynamo Player
[ ] 6. Verify out/volumes.csv, out/boq.csv, out/mass_haul.csv exist
[ ] 7. Switch to Python Tools tab in launcher → run M16–M20
[ ] 8. Check out/design_verification.txt — all OK / acceptable WARN
[ ] 9. Open out/report/design_report.xlsx — review all sheets
[ ] 10. Commit CSVs + project.json to version control
```
