# -*- coding: utf-8 -*-
"""
M14 — Long-Section (Profile) Sheet Layout.
Creates paper-space layouts referencing Civil 3D ProfileView objects tiled
along the alignment.  One layout per sheet, named LSECT-001, LSECT-002, ...

If ProfileView.Create is unavailable (API version mismatch), a model-space
rectangle placeholder is inserted instead and the layout viewport points at it.

Dynamo inputs:
  IN[0] : str — full path to project.json

project.json keys used:
  names.alignment           — alignment name
  names.profile_fg          — finished-grade profile name (informational)
  styles.profile            — profile view style name   (default 'Standard')
  styles.profile_label      — band set style name       (default 'Standard')
  design.profile_scale_h    — (default 1000) horizontal scale denominator
  design.profile_scale_v    — (default 100)  vertical  scale denominator
  design.sheet_width_mm     — (default 594)
  design.sheet_height_mm    — (default 420)
  project.number, project.name, project.revision
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
    try:
        lid = lm.GetLayoutId(name)
        return lid is not None and lid.IsValid
    except Exception:
        return False


def _add_border(tr, ps_btr, sheet_w, sheet_h, layer_name):
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
    txt = DBText()
    txt.Position = Point3d(x, y, 0.0)
    txt.TextString = text_str
    txt.Height = height
    txt.Layer = layer_name
    ps_btr.AppendEntity(txt)
    tr.AddNewlyCreatedDBObject(txt, True)


def _add_mspace_placeholder(tr, msp, label, x_origin, y_origin,
                            box_w, box_h, layer_name):
    """
    Insert a simple model-space rectangle + text as a ProfileView placeholder
    when ProfileView.Create is not available.

    Returns the bounding box centre (cx, cy) suitable for a viewport ViewCenter.
    """
    rect = AcPolyline()
    rect.AddVertexAt(0, Point2d(x_origin, y_origin), 0, 0, 0)
    rect.AddVertexAt(1, Point2d(x_origin + box_w, y_origin), 0, 0, 0)
    rect.AddVertexAt(2, Point2d(x_origin + box_w, y_origin + box_h), 0, 0, 0)
    rect.AddVertexAt(3, Point2d(x_origin, y_origin + box_h), 0, 0, 0)
    rect.Closed = True
    rect.Layer = layer_name
    msp.AppendEntity(rect)
    tr.AddNewlyCreatedDBObject(rect, True)

    lbl_txt = DBText()
    lbl_txt.Position = Point3d(x_origin + 5.0, y_origin + box_h / 2.0, 0.0)
    lbl_txt.TextString = label
    lbl_txt.Height = 5.0
    lbl_txt.Layer = layer_name
    msp.AppendEntity(lbl_txt)
    tr.AddNewlyCreatedDBObject(lbl_txt, True)

    cx = x_origin + box_w / 2.0
    cy = y_origin + box_h / 2.0
    return cx, cy


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

    align_name    = cfg.get('names',   {}).get('alignment',   '')
    profile_name  = cfg.get('names',   {}).get('profile_fg',  '')
    pv_style      = cfg.get('styles',  {}).get('profile',     'Standard')
    pv_band_style = cfg.get('styles',  {}).get('profile_label','Standard')
    design        = cfg.get('design',  {})
    scale_h       = float(design.get('profile_scale_h',  1000))
    scale_v       = float(design.get('profile_scale_v',   100))
    sheet_w       = float(design.get('sheet_width_mm',    594))
    sheet_h       = float(design.get('sheet_height_mm',   420))
    proj_info     = cfg.get('project', {})
    proj_num      = str(proj_info.get('number',   ''))
    proj_name_str = str(proj_info.get('name',     ''))
    proj_rev      = str(proj_info.get('revision', 'A'))

    if not align_name:
        return 'ERROR: names.alignment missing in project.json'

    # ---- 2. Get active document ----
    doc    = Application.DocumentManager.MdiActiveDocument
    db     = doc.Database
    civdoc = CivilApplication.ActiveDocument
    lm     = LayoutManager.Current

    # Sheet coverage in metres: 80 % of sheet width used for long section
    sheet_coverage_m = scale_h * (sheet_w * 0.80 / 1000.0)

    created  = 0
    skipped  = 0
    pv_api   = True     # will be set False if ProfileView.Create fails
    sheet_ranges = []

    # Placeholder layout: model-space rectangles stacked vertically.
    # Each box is proportional to the long-section sheet area in model space.
    # box_w = sheet_coverage_m (matches horizontal scale)
    # box_h = sheet_h * 0.70 * scale_v / 1000 (matches vertical scale in metres)
    box_w_m = sheet_coverage_m
    box_h_m = sheet_h * 0.70 * scale_v / 1000.0
    placeholder_y_spacing = box_h_m * 1.5   # vertical gap between placeholders
    placeholder_x_origin  = -sheet_coverage_m * 0.1   # slight left margin in MS

    with doc.LockDocument():
        with db.TransactionManager.StartTransaction() as tr:

            # Layers
            _ensure_layer(tr, db, 'C-SHEET-BORDER', 7)
            _ensure_layer(tr, db, 'C-SHEET-TEXT',   3)
            _ensure_layer(tr, db, 'C-PROF-VIEW',    5)  # blue

            # ---- 3. Find alignment and station range ----
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

            msgs.append('Alignment "%s": %.3f m to %.3f m (%.1f m)' % (
                align_name, sta_start, sta_end, align_len))
            msgs.append('Profile: "%s"  Style: "%s"  Band: "%s"' % (
                profile_name, pv_style, pv_band_style))

            # ---- 4. Apply optional station range override ----
            override_s = design.get('station_range_start')
            override_e = design.get('station_range_end')
            align_sta_start = sta_start  # keep original for sheet numbering offset
            if override_s is not None:
                sta_start = max(float(override_s), sta_start)
            if override_e is not None:
                sta_end   = min(float(override_e), sta_end)
            if sta_start >= sta_end:
                tr.Abort()
                return 'ERROR: station_range_start >= station_range_end after clamping'

            # ---- 5. Build sheet station ranges ----
            sta = sta_start
            while sta < sta_end:
                sta_nxt = min(sta + sheet_coverage_m, sta_end)
                sheet_ranges.append((sta, sta_nxt))
                sta += sheet_coverage_m

            # Apply optional sheet cap
            max_s = design.get('max_sheets_longsection')
            if max_s is not None:
                sheet_ranges = sheet_ranges[:int(max_s)]

            msgs.append('%d long-section sheets at H1:%d V1:%d (%.1f m/sheet)' % (
                len(sheet_ranges), int(scale_h), int(scale_v), sheet_coverage_m))

            sheet_num_offset = int((sta_start - align_sta_start) / sheet_coverage_m)

            # Model space block record (for placeholders / ProfileViews)
            bt  = tr.GetObject(db.BlockTableId, OpenMode.ForRead)
            msp = tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite)

            # ---- 6. Create one layout per sheet ----
            for idx, (sta_s, sta_e) in enumerate(sheet_ranges):
                sheet_num   = sheet_num_offset + idx + 1
                layout_name = 'LSECT-%03d' % sheet_num
                pv_name     = 'PV-%03d' % sheet_num

                if _layout_exists(lm, layout_name):
                    msgs.append('SKIP: "%s" already exists' % layout_name)
                    skipped += 1
                    continue

                # ---- 5a. Create layout ----
                try:
                    layout_id = lm.CreateLayout(layout_name)
                    layout    = tr.GetObject(layout_id, OpenMode.ForWrite)
                    ps_btr    = tr.GetObject(
                        layout.BlockTableRecordId, OpenMode.ForWrite)
                except Exception as lay_ex:
                    msgs.append('ERROR creating layout %s: %s' % (
                        layout_name, str(lay_ex)))
                    continue

                # ---- 5b. Try ProfileView.Create ----
                pv_cx = placeholder_x_origin + box_w_m / 2.0
                pv_cy = idx * placeholder_y_spacing + box_h_m / 2.0

                if pv_api:
                    try:
                        pv_id = ProfileView.Create(
                            civdoc,
                            pv_name,
                            align_id,
                            sta_s,
                            sta_e,
                            pv_style,
                            pv_band_style,
                        )
                        pv_obj = tr.GetObject(pv_id, OpenMode.ForRead)
                        # ProfileView.Location gives origin; centre for viewport
                        pv_origin = pv_obj.Location
                        # Estimate ProfileView extents from scale
                        pv_width_ms  = (sta_e - sta_s)   # 1:1 in station axis
                        pv_height_ms = box_h_m
                        pv_cx = pv_origin.X + pv_width_ms / 2.0
                        pv_cy = pv_origin.Y + pv_height_ms / 2.0
                        msgs.append('ProfileView "%s" created for %s' % (
                            pv_name, layout_name))
                    except Exception as pv_ex:
                        pv_api = False
                        msgs.append(
                            'WARN: ProfileView.Create unavailable — using '
                            'rectangle placeholder. Error: %s' % str(pv_ex))

                # If ProfileView API failed, draw a model-space placeholder
                if not pv_api:
                    placeholder_label = (
                        'LSECT %d  STA %.0f - %.0f  H1:%d V1:%d'
                    ) % (sheet_num, sta_s, sta_e, int(scale_h), int(scale_v))
                    y_origin = idx * placeholder_y_spacing
                    pv_cx, pv_cy = _add_mspace_placeholder(
                        tr, msp,
                        placeholder_label,
                        placeholder_x_origin,
                        y_origin,
                        box_w_m,
                        box_h_m,
                        'C-PROF-VIEW',
                    )

                # ---- 5c. Viewport pointing at ProfileView / placeholder ----
                try:
                    # Viewport fills 80 % width, 60 % height of sheet
                    vp = Viewport()
                    vp.CenterPoint = Point3d(sheet_w / 2.0, sheet_h * 0.55, 0.0)
                    vp.Width       = sheet_w * 0.80
                    vp.Height      = sheet_h * 0.60
                    vp.CustomScale = 1.0 / scale_h
                    vp.ViewCenter  = Point2d(pv_cx, pv_cy)
                    vp.On          = True
                    ps_btr.AppendEntity(vp)
                    tr.AddNewlyCreatedDBObject(vp, True)
                except Exception as vp_ex:
                    msgs.append('WARN: viewport error (%s): %s' % (
                        layout_name, str(vp_ex)))

                # ---- 5d. Sheet title text ----
                try:
                    title_str = (
                        'LONG SECTION %d  STA %.0f - %.0f  '
                        'H 1:%d  V 1:%d  %s %s  Rev %s'
                    ) % (
                        sheet_num, sta_s, sta_e,
                        int(scale_h), int(scale_v),
                        proj_num, proj_name_str, proj_rev,
                    )
                    _add_dbtext(tr, ps_btr, title_str,
                                10.0, 5.0, 3.5, 'C-SHEET-TEXT')
                except Exception as txt_ex:
                    msgs.append('WARN: title text error (%s): %s' % (
                        layout_name, str(txt_ex)))

                # ---- 5e. Border ----
                try:
                    _add_border(tr, ps_btr, sheet_w, sheet_h, 'C-SHEET-BORDER')
                except Exception as bd_ex:
                    msgs.append('WARN: border error (%s): %s' % (
                        layout_name, str(bd_ex)))

                created += 1
                msgs.append('Created: %s  STA %.0f - %.0f' % (
                    layout_name, sta_s, sta_e))

            tr.Commit()

    pv_method = 'ProfileView.Create' if pv_api else 'rectangle placeholder (ProfileView.Create API unavailable)'
    summary = (
        'OK: M14 Long-Section Sheets — %d created, %d skipped (existing). '
        'Total %d sheets, %.1f m alignment, H1:%d V1:%d. '
        'Profile view method: %s.'
    ) % (
        created, skipped, len(sheet_ranges),
        align_len, int(scale_h), int(scale_v),
        pv_method,
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
    OUT = 'FATAL ERROR in m14_longsection_sheets:\n%s' % traceback.format_exc()
