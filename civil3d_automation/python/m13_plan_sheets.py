# -*- coding: utf-8 -*-
"""
M13 — Plan Sheet Layout.
Creates paper-space layouts with viewports tiling along the alignment.
One layout per sheet, named PLAN-001, PLAN-002, ...

Dynamo inputs:
  IN[0] : str — full path to project.json

project.json keys used:
  names.alignment           — alignment name
  design.plan_scale         — (default 1000)  denominator of scale 1:X
  design.sheet_width_mm     — (default 594)   e.g. A1 landscape
  design.sheet_height_mm    — (default 420)
  project.number            — project number string (for title block)
  project.name              — project name string
  project.revision          — revision string
"""
import clr
clr.AddReference('AcMgd')
clr.AddReference('AcDbMgd')
clr.AddReference('AeccDbMgd')
import codecs, csv, os, json, math

from Autodesk.AutoCAD.ApplicationServices import Application
from Autodesk.AutoCAD.DatabaseServices import (
    Transaction, OpenMode, BlockTableRecord, BlockTable,
    LayoutManager, Layout, Viewport, MText, DBText,
)
from Autodesk.AutoCAD.DatabaseServices import Polyline as AcPolyline
from Autodesk.AutoCAD.Geometry import Point2d, Point3d
from Autodesk.Civil.ApplicationServices import CivilApplication
from Autodesk.Civil.DatabaseServices import Alignment, ProfileView


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _resolve(base, rel):
    return os.path.normpath(os.path.join(base, rel.replace('/', os.sep)))


def _find_alignment(tr, civdoc, name):
    for aid in civdoc.GetAlignmentIds():
        a = tr.GetObject(aid, OpenMode.ForRead)
        if a.Name == name:
            return a, aid
    return None, None


def _ensure_layer(tr, db, name, color_idx=7):
    from Autodesk.AutoCAD.DatabaseServices import LayerTable, LayerTableRecord
    from Autodesk.AutoCAD.Colors import Color, ColorMethod
    lt = tr.GetObject(db.LayerTableId, OpenMode.ForRead)
    if not lt.Has(name):
        ltr = LayerTableRecord()
        ltr.Name = name
        ltr.Color = Color.FromColorIndex(ColorMethod.ByAci, color_idx)
        lt2 = tr.GetObject(db.LayerTableId, OpenMode.ForWrite)
        lt2.Add(ltr)
        tr.AddNewlyCreatedDBObject(ltr, True)


def _layout_exists(lm, name):
    """Return True if a layout with this name already exists."""
    try:
        lid = lm.GetLayoutId(name)
        return lid is not None and lid.IsValid
    except Exception:
        return False


def _add_border(tr, ps_btr, sheet_w, sheet_h, layer_name):
    """Add a rectangular border polyline 5 mm inside sheet edges."""
    border = AcPolyline()
    border.AddVertexAt(0, Point2d(5.0, 5.0), 0, 0, 0)
    border.AddVertexAt(1, Point2d(sheet_w - 5.0, 5.0), 0, 0, 0)
    border.AddVertexAt(2, Point2d(sheet_w - 5.0, sheet_h - 5.0), 0, 0, 0)
    border.AddVertexAt(3, Point2d(5.0, sheet_h - 5.0), 0, 0, 0)
    border.Closed = True
    border.Layer = layer_name
    ps_btr.AppendEntity(border)
    tr.AddNewlyCreatedDBObject(border, True)


def _add_dbtext(tr, ps_btr, text_str, x, y, height, layer_name):
    """Add a DBText entity at paper-space coordinate (x, y)."""
    txt = DBText()
    txt.Position = Point3d(x, y, 0.0)
    txt.TextString = text_str
    txt.Height = height
    txt.Layer = layer_name
    ps_btr.AppendEntity(txt)
    tr.AddNewlyCreatedDBObject(txt, True)


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def run(project_json_path):
    msgs = []

    # ---- 1. Read project.json ----
    if not os.path.isfile(project_json_path):
        return 'ERROR: project.json not found: %s' % project_json_path

    try:
        with codecs.open(project_json_path, 'r', encoding='utf-8-sig') as fh:
            cfg = json.load(fh)
    except Exception as ex:
        return 'ERROR: Cannot parse project.json: %s' % str(ex)

    align_name = cfg.get('names', {}).get('alignment', '')
    design     = cfg.get('design', {})
    plan_scale = float(design.get('plan_scale',     1000))
    sheet_w    = float(design.get('sheet_width_mm',  594))
    sheet_h    = float(design.get('sheet_height_mm', 420))
    proj_info  = cfg.get('project', {})
    proj_num   = str(proj_info.get('number',   ''))
    proj_name  = str(proj_info.get('name',     ''))
    proj_rev   = str(proj_info.get('revision', 'A'))

    if not align_name:
        return 'ERROR: names.alignment is missing in project.json'

    # ---- 2. Get active document ----
    doc    = Application.DocumentManager.MdiActiveDocument
    db     = doc.Database
    civdoc = CivilApplication.ActiveDocument
    lm     = LayoutManager.Current

    # Sheet coverage in metres: 85 % of sheet width used for plan viewport
    sheet_coverage_m = plan_scale * (sheet_w * 0.85 / 1000.0)

    created = 0
    skipped = 0
    sheet_ranges = []

    with doc.LockDocument():
        with db.TransactionManager.StartTransaction() as tr:

            # Ensure layers
            _ensure_layer(tr, db, 'C-SHEET-BORDER', 7)  # white
            _ensure_layer(tr, db, 'C-SHEET-TEXT',   3)  # green

            # ---- 3. Find alignment ----
            align, align_id = _find_alignment(tr, civdoc, align_name)
            if align is None:
                tr.Abort()
                return 'ERROR: Alignment not found: %s' % align_name

            sta_start = align.StartingStation
            sta_end   = align.EndingStation
            align_len = sta_end - sta_start

            if align_len <= 0:
                tr.Abort()
                return 'ERROR: Alignment has zero or negative length'

            msgs.append('Alignment "%s": %.3f m to %.3f m (length %.1f m)' % (
                align_name, sta_start, sta_end, align_len))

            # ---- 4. Calculate sheet station ranges ----
            sta = sta_start
            while sta < sta_end:
                sta_nxt = min(sta + sheet_coverage_m, sta_end)
                sheet_ranges.append((sta, sta_nxt))
                sta += sheet_coverage_m

            msgs.append('%d plan sheets at 1:%d (%.1f m/sheet)' % (
                len(sheet_ranges), int(plan_scale), sheet_coverage_m))

            # ---- 5. Create one layout per sheet ----
            for idx, (sta_s, sta_e) in enumerate(sheet_ranges):
                sheet_num   = idx + 1
                layout_name = 'PLAN-%03d' % sheet_num

                # Skip if already exists (idempotent re-run)
                if _layout_exists(lm, layout_name):
                    msgs.append('SKIP: "%s" already exists' % layout_name)
                    skipped += 1
                    continue

                try:
                    # 5a. Create layout
                    layout_id = lm.CreateLayout(layout_name)
                    layout    = tr.GetObject(layout_id, OpenMode.ForWrite)

                    # 5b. Paper-space block record for this layout
                    ps_btr = tr.GetObject(
                        layout.BlockTableRecordId, OpenMode.ForWrite)

                    # 5c. Add viewport
                    mid_sta = (sta_s + sta_e) / 2.0
                    try:
                        mid_pt_3d = align.PointLocation(mid_sta, 0.0)
                        view_cx = mid_pt_3d.X
                        view_cy = mid_pt_3d.Y
                    except Exception as pt_ex:
                        msgs.append(
                            'WARN: PointLocation failed (sheet %d): %s' % (
                                sheet_num, str(pt_ex)))
                        view_cx = 0.0
                        view_cy = 0.0

                    vp = Viewport()
                    # Centre of viewport in paper space
                    vp.CenterPoint = Point3d(sheet_w / 2.0, sheet_h * 0.55, 0.0)
                    vp.Width       = sheet_w * 0.85
                    vp.Height      = sheet_h * 0.70
                    vp.CustomScale = 1.0 / plan_scale
                    vp.ViewCenter  = Point2d(view_cx, view_cy)
                    vp.On          = True
                    ps_btr.AppendEntity(vp)
                    tr.AddNewlyCreatedDBObject(vp, True)

                    # 5d. Sheet title text at bottom of sheet
                    title_str = (
                        'PLAN SHEET %d  STA %.0f - %.0f  '
                        'Scale 1:%d  %s %s  Rev %s'
                    ) % (
                        sheet_num, sta_s, sta_e, int(plan_scale),
                        proj_num, proj_name, proj_rev,
                    )
                    _add_dbtext(tr, ps_btr, title_str,
                                10.0, 5.0, 3.5, 'C-SHEET-TEXT')

                    # 5e. Border rectangle
                    _add_border(tr, ps_btr, sheet_w, sheet_h, 'C-SHEET-BORDER')

                    created += 1
                    msgs.append('Created: %s  STA %.0f - %.0f' % (
                        layout_name, sta_s, sta_e))

                except Exception as sheet_ex:
                    msgs.append('ERROR (sheet %d / %s): %s' % (
                        sheet_num, layout_name, str(sheet_ex)))

            tr.Commit()

    summary = (
        'OK: M13 Plan Sheets — %d created, %d skipped (existing). '
        'Total %d sheets, alignment %.1f m, scale 1:%d, %.1f m/sheet.'
    ) % (
        created, skipped, len(sheet_ranges),
        align_len, int(plan_scale), sheet_coverage_m,
    )
    return summary + '\n' + '\n'.join(msgs)


# ---------------------------------------------------------------------------
# Dynamo entry point
# ---------------------------------------------------------------------------
try:
    _proj_json = IN[0]
    OUT = run(_proj_json)
except Exception as _top_ex:
    import traceback
    OUT = 'FATAL ERROR in m13_plan_sheets:\n%s' % traceback.format_exc()
