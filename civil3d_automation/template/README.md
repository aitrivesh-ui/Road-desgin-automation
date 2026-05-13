# Template drawing (manual setup)

Civil 3D cannot seed a binary `.dwg` from this repository in a portable way. Create one template and reuse it for all modules.

## Required before running M1–M7

1. **Layers:** `0`, `C-ROAD-MARK`, `C-SGN-FURN` (or names matching `config/project.json`).
2. **Alignment style + label set:** names matching `project.json` → `styles.alignment`, `styles.alignment_label`.
3. **Profile style + label set:** `styles.profile`, `styles.profile_label`.
4. **Assemblies:** at least one assembly whose name matches `names.assembly` (used by M3 sample CSV).
5. **Blocks for M5:** block definitions matching `signage_schedule.csv` → `block_name` column (e.g. `SGN_STOP`).
6. **Surfaces for M4/M7 (optional):** EG and FG TIN surfaces named in `project.json` (`names.surface_eg`, `names.surface_fg`).

Save as `template/RoadAutomation_Template.dwt` (or `.dwg`) and copy for each test project.

For **Python 3 helpers** (preflight, tests, optional Excel export) outside Civil 3D, run **`install_tools.bat`** in the parent `civil3d_automation` folder once — see the repository **[README.md](../../README.md)** (sections **Quick start** and **Tools outside Civil 3D**).
