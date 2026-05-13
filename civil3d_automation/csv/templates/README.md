# Blank CSV templates (header-only)

Copy these files into `civil3d_automation/csv/` (next to your working data) and fill rows in Excel or any editor. Save as **CSV UTF-8** where your editor offers it, to avoid character encoding issues.

| File | Used by | Notes |
|------|---------|--------|
| `alignment_pi.csv` | M1 | At least two data rows with PI coordinates. |
| `profile_pvis.csv` | M2 | Stations and elevations along the alignment. |
| `section_widths.csv` | M3 | Corridor region ranges; optional column `assembly_name` per row overrides the default from Dynamo / `project.json`. |
| `signage_schedule.csv` | M5 | Block names must exist in the template DWG. |
| `payitems.csv` | M7 | Maps `source` + `key` to contract pay items. |

**M4** writes the volumes CSV path listed in `project.json` → `paths.volumes_csv`; there is no separate “input” template for that file.

See also: `config/project.example.json`, `config/project.schema_notes.md`, and the **Preflight** helper under `tools/`.

## Excel starter workbook

File: **`RoadAutomation_DataStarter.xlsx`** (same folder as this README).

- **Regenerate** after you change template column names: from repo root, install optional deps (double-click **`install.bat`**, or run `pip install -r civil3d_automation/requirements-tools.txt`), then run:

  ```bat
  python civil3d_automation/tools/build_starter_workbook.py
  ```

- The workbook has a **README** sheet (export instructions) and one sheet per input CSV with the correct header row frozen at row 1.

- Excel cannot run Dynamo; use it only to prepare tables, then save as CSV into `civil3d_automation/csv/`.
