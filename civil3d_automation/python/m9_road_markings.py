# -*- coding: utf-8 -*-
"""
M9 — Road Marking Automation from CSV.

Reads road_markings.csv and draws pavement marking polylines / block inserts
on the named alignment.  Supported mark types:
  CENTRE_SOLID, CENTRE_DASH, EDGE_SOLID, EDGE_DASH
  STOP_LINE, CROSSWALK
  ARROW_LEFT, ARROW_RIGHT, ARROW_THROUGH, ARROW_U_TURN, ARROW_MERGE

Dynamo inputs:
  IN[0] : str — absolute path to config/project.json

project.json keys used:
  paths.road_markings  → csv/road_markings.csv
  names.alignment      → alignment name  (e.g. DEMO-CL)
  names.layers.marking → C-ROAD-MARK

CSV columns (road_markings.csv):
  mark_id, start_sta, end_sta, side, mark_type, offset_m, width_m, dash_m, gap_m

Idempotent: all entities previously tagged with XData app ROAD_MARK_CSV are
erased before new entities are created.
"""
import clr
import csv
import codecs
import os
import json
import math

clr.AddReference('AcMgd')
clr.AddReference('AcDbMgd')
clr.AddReference('AeccDbMgd')

from Autodesk.AutoCAD.ApplicationServices import Application
from Autodesk.AutoCAD.DatabaseServices import (
    OpenMode, BlockTable, BlockTableRecord, BlockReference,
    LayerTableRecord, LayerTable,
    RegAppTableRecord, RegAppTable,
    ResultBuffer, TypedValue,
    Polyline3d, Poly3dType, Point3dCollection,
)
from Autodesk.AutoCAD.Geometry import Point3d
from Autodesk.AutoCAD.Colors import Color, ColorMethod
from Autodesk.Civil.ApplicationServices import CivilApplication
from Autodesk.Civil.DatabaseServices import Alignment

# XData registration tag (used for idempotent erase)
XDATA_APP = 'ROAD_MARK_CSV'

# Sample spacing (metres) when building continuous polylines
SAMPLE_STEP = 1.0

# Prefix prepended to mark_type to form the block name for arrows
ARROW_BLOCK_PREFIX = 'MARK_'

# mark_type values that map to block inserts
ARROW_TYPES = ('ARROW_LEFT', 'ARROW_RIGHT', 'ARROW_THROUGH',
               'ARROW_U_TURN', 'ARROW_MERGE')

# mark_type values that create a transverse line across the road
TRANSVERSE_TYPES = ('STOP_LINE', 'CROSSWALK')


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _resolve(root, rel):
    """Return an absolute path by joining root and rel (converts / to os.sep)."""
    return os.path.normpath(os.path.join(root, rel.replace('/', os.sep)))


def _ensure_layer(tr, db, name, color_idx=30):
    """Create layer *name* with ACI colour *color_idx* if it does not exist."""
    lt = tr.GetObject(db.LayerTableId, OpenMode.ForRead)
    if lt.Has(name):
        return
    ltr = LayerTableRecord()
    ltr.Name = name
    ltr.Color = Color.FromColorIndex(ColorMethod.ByAci, color_idx)
    lt2 = tr.GetObject(db.LayerTableId, OpenMode.ForWrite)
    lt2.Add(ltr)
    tr.AddNewlyCreatedDBObject(ltr, True)


def _ensure_regapp(tr, db, app_name):
    """Register *app_name* in the RegApp table if not already present."""
    rat = tr.GetObject(db.RegAppTableId, OpenMode.ForRead)
    if rat.Has(app_name):
        return
    ratr = RegAppTableRecord()
    ratr.Name = app_name
    rat2 = tr.GetObject(db.RegAppTableId, OpenMode.ForWrite)
    rat2.Add(ratr)
    tr.AddNewlyCreatedDBObject(ratr, True)


def _erase_prior(tr, db):
    """
    Erase every entity in ModelSpace that carries ROAD_MARK_CSV XData.
    Returns the count of erased entities.
    """
    bt  = tr.GetObject(db.BlockTableId, OpenMode.ForRead)
    msp = tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite)
    erased = 0
    for eid in msp:
        try:
            ent = tr.GetObject(eid, OpenMode.ForRead)
            xd  = ent.GetXDataForApplication(XDATA_APP)
            if xd is not None:
                tr.GetObject(eid, OpenMode.ForWrite).Erase()
                erased += 1
        except Exception:
            pass
    return erased


def _find_alignment(tr, civdoc, name):
    """Return the Alignment object whose Name matches *name*, or None."""
    for aid in civdoc.GetAlignmentIds():
        a = tr.GetObject(aid, OpenMode.ForRead)
        if a.Name == name:
            return a
    return None


def _make_xdata(mark_id):
    """Build a ResultBuffer that tags an entity with XDATA_APP + mark_id."""
    return ResultBuffer(
        TypedValue(1001, XDATA_APP),
        TypedValue(1000, str(mark_id)),
    )


def _pt_at(align, sta, off, sta_start, sta_end):
    """
    Sample align.PointLocation(sta, off), clamping sta to [sta_start, sta_end].
    Returns a Point3d or None on failure.
    """
    clamped = max(sta_start, min(sta_end, sta))
    try:
        p = align.PointLocation(clamped, off)
        z = p.Z if hasattr(p, 'Z') else 0.0
        return Point3d(p.X, p.Y, z)
    except Exception:
        return None


def _append_pline(tr, msp, pts, layer, mark_id):
    """
    Create a Polyline3d from *pts* (list of Point3d), add it to *msp*, and
    apply XData.  Returns the entity or None when fewer than 2 points given.
    """
    if len(pts) < 2:
        return None
    col = Point3dCollection()
    for p in pts:
        col.Add(p)
    pl = Polyline3d(Poly3dType.SimplePoly, col, False)
    pl.Layer   = layer
    pl.XData   = _make_xdata(mark_id)
    msp.AppendEntity(pl)
    tr.AddNewlyCreatedDBObject(pl, True)
    return pl


# ---------------------------------------------------------------------------
# Geometry builders — one per mark family
# ---------------------------------------------------------------------------

def _build_solid(tr, msp, align, row, layer, sta_start, sta_end):
    """Sample alignment and create one continuous Polyline3d."""
    off  = float(row['offset_m'])
    side = row['side'].strip().upper()
    if side == 'L':
        off = -abs(off)
    elif side == 'R':
        off = abs(off)
    # side == 'C'  → offset used as-is (normally 0 for centre line)

    r_sta0 = max(sta_start, float(row['start_sta']))
    r_sta1 = min(sta_end,   float(row['end_sta']))
    if r_sta1 <= r_sta0:
        return 0

    pts  = []
    sta  = r_sta0
    while sta <= r_sta1 + 1e-6:
        p = _pt_at(align, min(sta, r_sta1), off, sta_start, sta_end)
        if p is not None:
            pts.append(p)
        sta += SAMPLE_STEP

    # Guarantee the exact end station is sampled
    p_end = _pt_at(align, r_sta1, off, sta_start, sta_end)
    if p_end is not None and (not pts or abs(pts[-1].X - p_end.X) > 0.01 or abs(pts[-1].Y - p_end.Y) > 0.01):
        pts.append(p_end)

    mark_id = row.get('mark_id', '?')
    if _append_pline(tr, msp, pts, layer, mark_id) is not None:
        return 1
    return 0


def _build_dash(tr, msp, align, row, layer, sta_start, sta_end):
    """
    Create one Polyline3d per dash segment, advancing through dash+gap cycles.
    """
    off  = float(row['offset_m'])
    side = row['side'].strip().upper()
    if side == 'L':
        off = -abs(off)
    elif side == 'R':
        off = abs(off)

    r_sta0  = max(sta_start, float(row['start_sta']))
    r_sta1  = min(sta_end,   float(row['end_sta']))
    dash_m  = float(row.get('dash_m') or 3.0)
    gap_m   = float(row.get('gap_m')  or 9.0)
    mark_id = row.get('mark_id', '?')
    cycle   = dash_m + gap_m

    if r_sta1 <= r_sta0 or dash_m <= 0 or cycle <= 0:
        return 0

    created = 0
    pos     = r_sta0
    while pos < r_sta1 - 1e-6:
        dash_end = min(pos + dash_m, r_sta1)
        pts = []
        s   = pos
        while s <= dash_end + 1e-6:
            p = _pt_at(align, min(s, dash_end), off, sta_start, sta_end)
            if p is not None:
                pts.append(p)
            s += SAMPLE_STEP
        if _append_pline(tr, msp, pts, layer, mark_id) is not None:
            created += 1
        pos += cycle

    return created


def _build_transverse(tr, msp, align, row, layer, sta_start, sta_end):
    """
    Create a transverse Polyline3d (STOP_LINE or CROSSWALK) perpendicular to
    the alignment at the mid-station of the mark station range.
    """
    side    = row['side'].strip().upper()
    off     = float(row['offset_m'])
    mark_id = row.get('mark_id', '?')

    r_sta0  = max(sta_start, float(row['start_sta']))
    r_sta1  = min(sta_end,   float(row['end_sta']))
    mid_sta = (r_sta0 + r_sta1) / 2.0

    # Determine left/right sweep widths from the centre line
    if side == 'C':
        # offset_m is used as the half-width on each side
        left_w  = abs(off) if abs(off) > 0.01 else 4.0
        right_w = left_w
    elif side == 'L':
        left_w  = abs(off)
        right_w = 0.0
    else:  # R
        left_w  = 0.0
        right_w = abs(off)

    # Safety fallback: minimum 4 m reach
    if left_w < 0.01 and right_w < 0.01:
        left_w  = 4.0
        right_w = 4.0

    try:
        p_left  = align.PointLocation(mid_sta, -left_w)
        p_right = align.PointLocation(mid_sta,  right_w)
    except Exception:
        return 0

    pts = [
        Point3d(p_left.X,  p_left.Y,  getattr(p_left,  'Z', 0.0)),
        Point3d(p_right.X, p_right.Y, getattr(p_right, 'Z', 0.0)),
    ]
    if _append_pline(tr, msp, pts, layer, mark_id) is not None:
        return 1
    return 0


def _build_arrow(tr, msp, db, align, row, layer, sta_start, sta_end):
    """
    Insert a named block (MARK_<mark_type>) at the mid-station / offset.
    Returns (count_created, warning_string).
    """
    mark_type  = row['mark_type'].strip().upper()
    block_name = ARROW_BLOCK_PREFIX + mark_type   # e.g. MARK_ARROW_LEFT
    mark_id    = row.get('mark_id', '?')

    r_sta0  = max(sta_start, float(row['start_sta']))
    r_sta1  = min(sta_end,   float(row['end_sta']))
    mid_sta = (r_sta0 + r_sta1) / 2.0

    off  = float(row['offset_m'])
    side = row['side'].strip().upper()
    if side == 'L':
        off = -abs(off)
    elif side == 'R':
        off = abs(off)

    try:
        ins_raw = align.PointLocation(mid_sta, off)
        ins_pt  = Point3d(ins_raw.X, ins_raw.Y, getattr(ins_raw, 'Z', 0.0))
    except Exception as ex:
        return 0, 'WARN: PointLocation failed mark_id %s: %s' % (str(mark_id), str(ex))

    bt = tr.GetObject(db.BlockTableId, OpenMode.ForRead)
    if not bt.Has(block_name):
        return 0, ('WARN: Block "%s" not in drawing — skipped mark_id %s'
                   % (block_name, str(mark_id)))

    # Alignment tangent angle for block rotation
    try:
        p0  = align.PointLocation(max(sta_start, mid_sta - 0.05), 0)
        p1  = align.PointLocation(min(sta_end,   mid_sta + 0.05), 0)
        ang = math.atan2(p1.Y - p0.Y, p1.X - p0.X)
    except Exception:
        ang = 0.0

    bid = bt[block_name]
    br  = BlockReference(ins_pt, bid)
    br.Layer    = layer
    br.Rotation = ang
    br.XData    = _make_xdata(mark_id)
    msp.AppendEntity(br)
    tr.AddNewlyCreatedDBObject(br, True)
    return 1, ''


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def run(project_json):
    if not os.path.isfile(project_json):
        return 'ERROR: project.json not found: %s' % project_json

    with codecs.open(project_json, 'r', encoding='utf-8-sig') as f:
        cfg = json.load(f)

    cfg_dir = os.path.dirname(os.path.abspath(project_json))
    root    = os.path.normpath(os.path.join(cfg_dir, '..'))

    paths  = cfg.get('paths', {})
    names  = cfg.get('names', {})
    layers = names.get('layers', {})

    mark_csv_rel = paths.get('road_markings', 'csv/road_markings.csv')
    mark_csv     = _resolve(root, mark_csv_rel)
    align_name   = names.get('alignment', 'ALIGN')
    mark_layer   = layers.get('marking', 'C-ROAD-MARK')

    if not os.path.isfile(mark_csv):
        return 'ERROR: road_markings CSV not found: %s' % mark_csv

    rows = []
    with codecs.open(mark_csv, 'r', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    if not rows:
        return 'OK: road_markings.csv is empty — nothing to draw.'

    doc    = Application.DocumentManager.MdiActiveDocument
    db     = doc.Database
    civdoc = CivilApplication.ActiveDocument

    created  = 0
    warnings = []

    with doc.LockDocument():
        with db.TransactionManager.StartTransaction() as tr:
            _ensure_layer(tr, db, mark_layer, 30)   # 30 = orange
            _ensure_regapp(tr, db, XDATA_APP)

            erased = _erase_prior(tr, db)

            align = _find_alignment(tr, civdoc, align_name)
            if align is None:
                tr.Abort()
                return 'ERROR: Alignment not found: %s' % align_name

            sta_start = align.StartingStation
            sta_end   = align.EndingStation

            bt  = tr.GetObject(db.BlockTableId, OpenMode.ForRead)
            msp = tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite)

            for row in rows:
                try:
                    mark_type = row.get('mark_type', '').strip().upper()

                    if mark_type in ARROW_TYPES:
                        n, warn = _build_arrow(tr, msp, db, align, row,
                                               mark_layer, sta_start, sta_end)
                        created += n
                        if warn:
                            warnings.append(warn)

                    elif mark_type in TRANSVERSE_TYPES:
                        created += _build_transverse(tr, msp, align, row,
                                                     mark_layer, sta_start, sta_end)

                    elif mark_type in ('CENTRE_DASH', 'EDGE_DASH'):
                        created += _build_dash(tr, msp, align, row,
                                               mark_layer, sta_start, sta_end)

                    elif mark_type in ('CENTRE_SOLID', 'EDGE_SOLID'):
                        created += _build_solid(tr, msp, align, row,
                                                mark_layer, sta_start, sta_end)

                    else:
                        warnings.append(
                            'WARN: Unknown mark_type "%s" (mark_id %s) — '
                            'drawn as solid line fallback.'
                            % (mark_type, row.get('mark_id', '?'))
                        )
                        created += _build_solid(tr, msp, align, row,
                                                mark_layer, sta_start, sta_end)

                except Exception as row_err:
                    warnings.append(
                        'WARN: mark_id %s failed: %s'
                        % (row.get('mark_id', '?'), str(row_err))
                    )

            tr.Commit()

    msg = ('OK: M9 road markings — %d prior erased, %d entities created '
           'on layer "%s".' % (erased, created, mark_layer))
    if warnings:
        msg += ' | ' + ' ; '.join(warnings)
    return msg


# ---------------------------------------------------------------------------
# Dynamo entry point  (IN[0] = project.json path)
# ---------------------------------------------------------------------------
try:
    _cfg_path = str(IN[0])
    OUT = run(_cfg_path)
except Exception as e:
    OUT = 'ERROR: M9 exception: %s' % str(e)
