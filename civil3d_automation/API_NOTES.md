# Civil 3D + Dynamo API baseline (M1–M8)

**Target host:** Autodesk Civil 3D 2022–2025 with Dynamo 2.x  
**Python:** IronPython 2.7 in Python Script nodes (default for many Civil installs). For CPython 3 Dynamo, references and some types differ—branch in code after confirming Manage → Dynamo → Python engine.

**Python 3 (preflight, clone, tests, optional Excel):** separate install on the workstation. On Windows, run **`install_tools.bat`** in `civil3d_automation/` or **`install.bat`** at the repo root once to install `requirements-tools.txt`.

## Assemblies (IronPython)

```python
import clr
clr.AddReference('AcMgd')
clr.AddReference('AcDbMgd')
clr.AddReference('AecBaseMgd')
clr.AddReference('AeccDbMgd')
```

`Autodesk.Civil.ApplicationServices.CivilApplication.ActiveDocument` returns `CivilDocument`.

## Document lock and transactions

Match the pattern used in [road_automation_complete.html — Markings hub](../road_automation_complete.html#sec-marking):

- `Application.DocumentManager.MdiActiveDocument`
- `with doc.LockDocument():`
- `with db.TransactionManager.StartTransaction() as tr:`

## Alignment (M1)

- **Create empty alignment:** `Alignment.Create(civilDoc, alignmentName, siteName, layerName, styleName, labelSetName)`  
  - Use `""` for siteless alignment if `null` is rejected.  
  - Layer, alignment style, and label set **must exist** in the template DWG.
- **Geometry:** `AlignmentEntityCollection` via `alignment.Entities`.
  - **Implemented path:** `AddFixedLine(Point3d, Point3d)` between consecutive PI points (polyline-style alignment). Z on `Point3d` is typically 0 for plan geometry.
  - **Not auto-built in v1:** spiral columns in CSV; non-zero `radius_m` triggers QA warnings only—extend with `AddFreeCurve` / `AddFreeSCS` using entity IDs when you need true curve groups.

Reference: [Alignment.Create](https://civapidocs.com/2024/858c3c00-a967-985f-8c9a-750447e4c9e7.htm), [AlignmentEntityCollection](https://civapidocs.com/2024/58c5b585-6744-f5e2-1fb1-274ec5d57cd2.htm).

## Profile (M2)

- **Create FG profile:** `Profile.CreateByLayout(profileName, civilDoc, alignmentName, layerName, styleName, labelSetName)` (string overload avoids resolving `ObjectId`s for layer/styles).
- **Entities:** `profile.Entities` (`ProfileEntityCollection`).
  - Tangents: `AddFixedTangent(Point2d, Point2d)` with **X = station**, **Y = elevation** in layout space.
  - Vertical curves: e.g. `AddFreeSymmetricParabolaByPVIAndCurveLength` attached to internal `ProfilePVI` when `curve_length_m > 0` (see Civil 3D API help for your year).

## Corridor (M3–M4)

- **Regions:** `corridor.Baselines[0].BaselineRegions.Add(regionName, assemblyName, startStation, endStation)` then `corridor.Rebuild()`.  
  - Assembly name must match an assembly in the drawing.
- **Widths / targets:** subassembly parameters and offset targets are version- and PKT-specific; extend M3 after regions are stable.
- **Volumes:** create or refresh a volume surface (e.g. `TinVolumeSurface`) between EG and FG, then read volume properties—confirm exact class names for your Civil year.

## Signage (M5)

- Insert blocks with `BlockReference(Point3d, ObjectId)` where `ObjectId` is from `BlockTable[blockName]`.
- Station → point: `Alignment.PointLocation(station, offset)`; tangent: `Alignment.GetDirectionVector2dAtStation(station)` or equivalent **for your API version** (method names vary—verify in Object Browser / help).

## Sheets (M6)

- View frame groups and batch publish are the **highest-variance** area across versions.
- **6a:** Build view frames via Civil API when signatures are confirmed.  
- **6b:** Prefer `-PUBLISH` with a generated `.dsd`, or a documented manual publish step until automated publish is verified.

## BOQ (M7)

- Marking solids: XData app `ROAD_MARK_SRC` and type string per [road_automation_complete.html — Markings hub](../road_automation_complete.html#sec-marking).
- Corridor quantities: use Corridor QTO / material APIs for your version; replace placeholder loops with validated calls.
- **Excel:** IronPython often has no `openpyxl`—default output is **CSV**; open in Excel or use Power Query.

## Orchestration (M8)

- Avoid `import` of sibling `.py` files from Dynamo unless `sys.path` is configured.  
- **Recommended:** one Dynamo graph with **multiple Python Script nodes** wired in sequence, or paste the combined runner in `m8_run_all.py`.
- **Run manifest:** Each successful M8 run overwrites `out/qa/last_run_manifest.json` (next to `paths.qa_log`) with step ids, wall-clock seconds per step, and a short text preview of each module output—useful for performance notes and support.
- **Committing `.dyn` graphs:** Dynamo graphs are tied to a specific Dynamo build. If you version `.dyn` files in git, record **Civil 3D year**, **Dynamo build number**, and **Python engine** (IronPython 2 vs CPython 3) in this file so others can reproduce or rebuild graphs.

## Verification checklist (run inside Civil 3D)

1. Template DWG contains layers, alignment/profile styles, label sets, and block names used by CSVs.  
2. Each module returns a string starting with `OK:` or `ERROR:` and writes optional logs under `out/qa/`.  
3. After Civil upgrade, re-run this checklist and update `API_NOTES.md` with any signature changes.
