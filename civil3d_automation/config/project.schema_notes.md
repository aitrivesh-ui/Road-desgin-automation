# `project.json` field reference

Copy `project.example.json` to `config/project.json` and edit (on Windows you can run **`install_tools.bat`** once: it creates `project.json` from the example only if the file is missing). JSON does not allow comments; use this table when unsure.

## `project`

| Field | Purpose |
|--------|---------|
| `number`, `name`, `revision` | Labels for QA logs and your own traceability. |
| `designer`, `checker` | Optional text fields for issue records. |

## `paths` (relative to `civil3d_automation/` folder — the parent of `config/`)

| Key | File role | If wrong |
|-----|-----------|----------|
| `alignment_pi` | M1 input CSV | M1 errors: file not found or bad columns. |
| `profile_pvis` | M2 input CSV | M2 errors similarly. |
| `section_widths` | M3 input CSV | M3 cannot add regions. |
| `signage` | M5 input CSV | M5 cannot place signs. |
| `payitems` | M7 pay-item dictionary | M7: missing file or columns → BOQ fails. |
| `volumes_csv` | **M4 output** (M7 input) | Path must be writable for M4. If missing before first M4 run, that is normal. |
| `boq_csv` | **M7 output** | Parent folder is created if needed. |
| `qa_log` | M8 append-only text log | Folder `out/qa/` should exist or will be created per script behavior. |

After each **M8** run, the same folder as `qa_log` also receives **`last_run_manifest.json`** (step timings and short output previews). Safe to delete; it is overwritten every run.

## `names`

| Key | Typical Civil object | If wrong |
|-----|----------------------|----------|
| `alignment` | Alignment name created by M1 | M2+ fail if alignment missing. |
| `profile_fg` | Finish-ground profile (M2) | M2 fails or wrong profile. |
| `corridor` | Corridor for M3/M4 | “Corridor not found” errors. |
| `assembly` | Default assembly for M3 rows without `assembly_name` | M3 `BaselineRegions.Add` fails. |
| `surface_eg`, `surface_fg` | TIN surface names for M4 | M4 “Surfaces not found”. |
| `layers.marking`, `layers.signage` | Layers for M7 quantity scan | M7 counts nothing on wrong layer. |

## `styles`

Must match **style and label set names** in your template DWT/DWG (e.g. `Standard`).

## `design`

| Key | Used by | Notes |
|-----|---------|--------|
| `start_station` | M1 | Starting chainage for alignment. |
| `max_grade_pct`, `min_grade_pct` | M2 | Grade QA warnings only; does not change geometry by itself. |
