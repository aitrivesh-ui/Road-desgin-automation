# Dynamo graphs (Civil 3D)

Dynamo `.dyn` files are JSON graphs tied to a specific Dynamo build; they are fragile in git across versions. **Recommended workflow:** build each graph once in Civil 3D, then save next to these scripts.

**Windows — optional Python helpers:** from `civil3d_automation/`, run **`install_tools.bat`** (or `install.bat` at the repo root) so preflight, tests, and Excel export scripts have their dependencies; see `../tools/README.md`.

## Build each module (M1–M8)

1. Open **Dynamo** from Civil 3D (Manage tab).
2. **New** graph.
3. Add a **Python Script** node.
4. Set engine to **IronPython 2** (match [Markings hub in the handbook](../../road_automation_complete.html#sec-marking)).
5. Open the matching file under `../python/`, copy **entire** contents into the Python Script node.
6. Add **String** / **Number** input nodes and wire to the Python node **in order** matching the `IN[0]…` docstring at the top of each script.
7. Add a **Watch** node on `OUT`.
8. **Save** as:

| File | Python source | Typical inputs |
|------|----------------|----------------|
| `M1_Alignment.dyn` | `m1_alignment_from_csv.py` | csv path, name, style, label set, start station |
| `M2_Profile.dyn` | `m2_profile_from_csv.py` | csv, alignment, profile name, layer, styles, grade QA |
| `M3_CorridorRegions.dyn` | `m3_corridor_regions_from_csv.py` | csv, corridor, assembly |
| `M4_Volumes.dyn` | `m4_corridor_rebuild_volumes.py` | corridor, EG, FG, out CSV, vol name |
| `M5_Signage.dyn` | `m5_signage_from_csv.py` | csv, alignment, layer, XData app |
| `M6_Sheets.dyn` | `m6_sheets_helper.py` | alignment, out dir |
| `M7_BOQ.dyn` | `m7_boq_rollup.py` | vol CSV, mark layer, sign layer, payitems, BOQ out |
| `M8_RunAll.dyn` | `m8_run_all.py` | absolute path to `config/project.json`, optional step list |

9. Expose graphs in **Dynamo Player** (right graph → publish / add to player library per your Civil version).

## M8 vs individual graphs

- Run **M1→M7** individually while testing.
- Use **M8** only after paths in `config/project.json` resolve correctly from the JSON file’s folder (`../csv/…`, `../out/…`).

## Marking module (existing)

The road marking generator remains in [road_automation_complete.html — Markings hub](../../road_automation_complete.html#sec-marking). Paste that script into its own graph between **M4** and **M5** in your production order.

---

## Dynamo Player as the “data popup” (labels and notes)

Goal: whoever opens the graph sees **what to paste** and **in which socket**, without opening the Python editor.

### No extra packages (recommended default)

1. After wiring `IN[0]…`, **rename** each **String** / **Number** node in Dynamo to the full phrase from the script docstring (e.g. `Absolute path to config\project.json` instead of `String`).
2. Add a **Group** around the Python node and inputs; set the group title to the module id (**M1**, **M8**, …).
3. Add **Note** nodes (yellow stickies) next to fragile inputs:
   - **M8 `IN[0]`** — Must be the **absolute** Windows path to `project.json`. Tip: run `tools/run_preflight.bat` and use **Copy project.json path**.
   - **M8 `IN[1]`** — Optional **step filter** (comma-separated, no spaces required). Empty = run all of `m1` through `m7`. Examples:

   | Example value | Effect |
   |---------------|--------|
   | *(empty)* | `m1,m2,m3,m4,m5,m6,m7` |
   | `m1,m2` | Alignment + profile only |
   | `m4` | Corridor rebuild + volumes only |
   | `m5,m7` | Signage then BOQ (ensure prerequisites exist in the drawing) |

4. Connect the Python **`OUT`** to a **Watch** node. Messages beginning with `OK:` mean the step completed; `ERROR:` means fix data or Civil objects before continuing.

### Optional: Data Shapes (form-style UI)

If your firm allows Dynamo packages, **Data Shapes** (or similar) can present real form fields instead of raw String nodes. Trade-offs: package install per Civil version, training, and graphs that are **not** self-contained. If you adopt it, document the package name and version in [API_NOTES.md](../API_NOTES.md).

### Example Player checklist (ASCII)

```
[M8_RunAll graph]
  (String) Absolute path to project.json ----> Python IN[0]
  (String) Step filter e.g. m1,m2,m4 --------> Python IN[1]   [optional; can leave default empty]
  (Watch) <------------------------------------ Python OUT
```

Same pattern for M1–M7: one row per `IN[n]` from the top-of-file docstring in each `m*.py`.

### Bundling `.dyn` files in git

Graph files are **version-sensitive**. If you commit `.dyn` files, record **Civil 3D year**, **Dynamo build**, and **IronPython** setting in [API_NOTES.md](../API_NOTES.md) so others can reproduce the graph.
