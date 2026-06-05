# -*- coding: utf-8 -*-
"""
M15 — Standard Details Insertion.
Reads a CSV of standard detail blocks, creates a single 'DETAILS' paper-space
layout, and inserts each block (or a placeholder text if the block is missing)
in a grid arrangement.

Dynamo inputs:
  IN[0] : str — full path to project.json

project.json keys used:
  paths.details  — relative path to details CSV (default 'csv/details.csv')
  project.number, project.name, project.revision

details.csv columns (with header row):
  detail_id, block_name, description, scale, sheet_ref

Example rows:
  D01, DT_TYPICAL_XSEC, Typical cross-section, 100, DWG-STD-001
  D02, DT_CULVERT_TYPE1, Type 1 culvert detail,  50, DWG-STD-002
  D03, DT_KERB_DETAIL,   Kerb and channel,        20, DWG-STD-003
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
    BlockReference,
)
from Autodesk.AutoCAD.DatabaseServices import Polyline as AcPolyline
from Autodesk.AutoCAD.Geometry import Point2d, Point3d, Scale3d
from Autodesk.Civil.ApplicationServices import CivilApplication
from Autodesk.Civil.DatabaseServices import Alignment, ProfileView

# Grid parameters for placing detail blocks in paper space
COLS_PER_ROW   = 3      # max detail blocks per row
CELL_WIDTH_MM  = 250.0  # horizontal spacing between detail origins (mm)
CELL_HEIGHT_MM = 200.0  # vertical spacing between detail rows (mm)
GRID_X_ORIGIN  = 20.0   # left margin from sheet edge (mm)
GRID_Y_ORIGIN  = 20.0   # bottom margin (first row baseline)
LABEL_OFFSET_Y = -15.0  # label text below block origin

DETAILS_LAYOUT = 'DETAILS'


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _resolve(base, rel):
    return os.path.normpath(os.path.join(base, rel.replace('/', os.sep)))


def _find_alignment(tr, civdoc, name):
    for aid in civdoc.GetAlignmentIds():
        a = tr.GetObject(aid, OpenMode.ForRead)
        if a.Name == name:
            return a
    return None


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


def _add_dbtext(tr, btr, text_str, x, y, height, layer_name):
    txt = DBText()
    txt.Position = Point3d(x, y, 0.0)
    txt.TextString = text_str
    txt.Height = height
    txt.Layer = layer_name
    btr.AppendEntity(txt)
    tr.AddNewlyCreatedDBObject(txt, True)


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


def _add_placeholder_box(tr, btr, text_str, x, y, w, h, layer_name):
    """Draw a dashed rectangle + text label for a missing block."""
    box = AcPolyline()
    box.AddVertexAt(0, Point2d(x,     y),     0, 0, 0)
    box.AddVertexAt(1, Point2d(x + w, y),     0, 0, 0)
    box.AddVertexAt(2, Point2d(x + w, y + h), 0, 0, 0)
    box.AddVertexAt(3, Point2d(x,     y + h), 0, 0, 0)
    box.Closed = True
    box.Layer  = layer_name
    btr.AppendEntity(box)
    tr.AddNewlyCreatedDBObject(box, True)

    lbl = DBText()
    lbl.Position   = Point3d(x + 5.0, y + h / 2.0, 0.0)
    lbl.TextString = text_str
    lbl.Height     = 4.0
    lbl.Layer      = layer_name
    btr.AppendEntity(lbl)
    tr.AddNewlyCreatedDBObject(lbl, True)


def _read_details_csv(csv_path):
    """Read details CSV and return list of dicts. Raises on bad file."""
    rows = []
    with codecs.open(csv_path, 'r', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            # Normalise key names (strip whitespace)
            clean = {}
            for k, v in row.items():
                clean[k.strip()] = v.strip() if v else ''
            rows.append(clean)
    return rows


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

    base_dir = os.path.dirname(project_json_path)

    details_rel = cfg.get('paths', {}).get('details', 'csv/details.csv')
    details_csv = _resolve(base_dir, details_rel)

    design     = cfg.get('design', {})
    sheet_w    = float(design.get('sheet_width_mm',  594))
    sheet_h    = float(design.get('sheet_height_mm', 420))
    proj_info  = cfg.get('project', {})
    proj_num   = str(proj_info.get('number',   ''))
    proj_name  = str(proj_info.get('name',     ''))
    proj_rev   = str(proj_info.get('revision', 'A'))

    # ---- 2. Read details CSV ----
    if not os.path.isfile(details_csv):
        return ('ERROR: details CSV not found: %s  '
                '(set paths.details in project.json)') % details_csv

    try:
        rows = _read_details_csv(details_csv)
    except Exception as csv_ex:
        return 'ERROR: Cannot read details CSV: %s' % str(csv_ex)

    if not rows:
        return 'WARN: details CSV is empty: %s' % details_csv

    msgs.append('Read %d rows from: %s' % (len(rows), details_csv))

    # ---- 3. Get active document ----
    doc = Application.DocumentManager.MdiActiveDocument
    db  = doc.Database

    placed  = 0
    missing = []

    with doc.LockDocument():
        with db.TransactionManager.StartTransaction() as tr:

            # Layers
            _ensure_layer(tr, db, 'C-SHEET-BORDER', 7)
            _ensure_layer(tr, db, 'C-SHEET-TEXT',   3)
            _ensure_layer(tr, db, 'C-DET-BLOCK',    2)  # yellow for blocks
            _ensure_layer(tr, db, 'C-DET-MISSING',  1)  # red for placeholders

            lm = LayoutManager.Current

            # ---- 4. Get or create the DETAILS layout ----
            if _layout_exists(lm, DETAILS_LAYOUT):
                layout_id = lm.GetLayoutId(DETAILS_LAYOUT)
                msgs.append('Using existing layout: %s' % DETAILS_LAYOUT)
            else:
                layout_id = lm.CreateLayout(DETAILS_LAYOUT)
                msgs.append('Created layout: %s' % DETAILS_LAYOUT)

            layout = tr.GetObject(layout_id, OpenMode.ForWrite)

            # ---- 5. Paper-space block record for DETAILS layout ----
            ps_btr = tr.GetObject(layout.BlockTableRecordId, OpenMode.ForWrite)

            # Block table (read once, used for every row)
            bt = tr.GetObject(db.BlockTableId, OpenMode.ForRead)

            # ---- 6. Add STANDARD DETAILS heading ----
            heading = 'STANDARD DETAILS  %s %s  Rev %s' % (
                proj_num, proj_name, proj_rev)
            _add_dbtext(
                tr, ps_btr, heading,
                GRID_X_ORIGIN, sheet_h - 15.0,
                6.0, 'C-SHEET-TEXT')

            # ---- 7. Place each detail block (or placeholder) in a grid ----
            for i, row in enumerate(rows):
                detail_id   = row.get('detail_id',   str(i + 1))
                block_name  = row.get('block_name',  '').strip()
                description = row.get('description', '').strip()
                sheet_ref   = row.get('sheet_ref',   '').strip()

                try:
                    detail_scale = float(row.get('scale', 100) or 100)
                except (ValueError, TypeError):
                    detail_scale = 100.0

                # Grid position
                col    = i % COLS_PER_ROW
                row_no = i // COLS_PER_ROW
                x_pos  = GRID_X_ORIGIN + col * CELL_WIDTH_MM
                # Rows grow upward from GRID_Y_ORIGIN; first row is top-most
                # (count rows down from below the heading)
                y_pos  = sheet_h - 30.0 - row_no * CELL_HEIGHT_MM

                # Scale factor: paper-space is in mm; blocks are drawn in metres
                # at 1:1 model units. We need to fit the block into a ~150x120 mm
                # paper-space cell at the given scale.
                # The actual block insertion is at paper-space coordinates, so
                # we scale down: 1 mm paper = detail_scale mm model.
                scale_factor = 1.0 / detail_scale if detail_scale != 0 else 1.0

                label_str = '%s: %s  1:%d  %s' % (
                    detail_id, description, int(detail_scale), sheet_ref)

                if block_name and bt.Has(block_name):
                    # ---- 7a. Insert block reference ----
                    try:
                        block_def_id = bt[block_name]
                        br = BlockReference(
                            Point3d(x_pos, y_pos, 0.0),
                            block_def_id,
                        )
                        br.ScaleFactors = Scale3d(scale_factor)
                        br.Layer = 'C-DET-BLOCK'
                        ps_btr.AppendEntity(br)
                        tr.AddNewlyCreatedDBObject(br, True)
                        placed += 1
                        msgs.append(
                            'Placed: %s (%s) at (%.0f, %.0f) scale 1:%d' % (
                                block_name, detail_id,
                                x_pos, y_pos, int(detail_scale)))
                    except Exception as br_ex:
                        msgs.append(
                            'ERROR inserting block "%s": %s' % (
                                block_name, str(br_ex)))
                        missing.append(block_name)
                        # Fall through to placeholder
                        _add_placeholder_box(
                            tr, ps_btr,
                            'ERR: %s' % block_name,
                            x_pos, y_pos,
                            CELL_WIDTH_MM * 0.9, CELL_HEIGHT_MM * 0.6,
                            'C-DET-MISSING')
                else:
                    # ---- 7b. Block not found — add placeholder box ----
                    display_name = block_name if block_name else '(no block name)'
                    missing.append(display_name)
                    msgs.append(
                        'MISSING block "%s" (%s) — placeholder added' % (
                            display_name, detail_id))
                    _add_placeholder_box(
                        tr, ps_btr,
                        'MISSING: %s' % display_name,
                        x_pos, y_pos,
                        CELL_WIDTH_MM * 0.9, CELL_HEIGHT_MM * 0.6,
                        'C-DET-MISSING')

                # ---- 7c. Text label below the detail ----
                _add_dbtext(
                    tr, ps_btr, label_str,
                    x_pos, y_pos + LABEL_OFFSET_Y,
                    2.5, 'C-SHEET-TEXT')

            # ---- 8. Missing-block note ----
            if missing:
                note_parts = ['MISSING BLOCKS:'] + list(set(missing))
                note_str = '  '.join(note_parts)
                _add_dbtext(
                    tr, ps_btr, note_str,
                    GRID_X_ORIGIN, 10.0,
                    2.5, 'C-SHEET-TEXT')

            # ---- 9. Border ----
            _add_border(tr, ps_btr, sheet_w, sheet_h, 'C-SHEET-BORDER')

            tr.Commit()

    # Build summary
    missing_unique = sorted(set(missing))
    summary_parts = [
        'OK: M15 Standard Details — %d detail(s) placed, %d block(s) missing.' % (
            placed, len(missing_unique)),
        'Layout: %s' % DETAILS_LAYOUT,
    ]
    if missing_unique:
        summary_parts.append('Missing blocks: %s' % ', '.join(missing_unique))

    return '\n'.join(summary_parts + msgs)


# ---------------------------------------------------------------------------
# Dynamo entry point
# ---------------------------------------------------------------------------
try:
    _proj_json = IN[0]
    OUT = run(_proj_json)
except Exception as _top_ex:
    import traceback
    OUT = 'FATAL ERROR in m15_standard_details:\n%s' % traceback.format_exc()
