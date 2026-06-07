# -*- coding: utf-8 -*-
"""
M5 — Place signage blocks from CSV at alignment station/offset (0.5 m sampling on approach).
Dynamo inputs:
  IN[0] csv, IN[1] alignment, IN[2] layer, IN[3] XData app name
"""
import clr
import csv
import codecs
import os
import math

clr.AddReference('AcMgd')
clr.AddReference('AcDbMgd')
clr.AddReference('AeccDbMgd')

from Autodesk.AutoCAD.ApplicationServices import Application
from Autodesk.AutoCAD.DatabaseServices import (
    OpenMode, Transaction, BlockReference, BlockTable, BlockTableRecord,
    LayerTableRecord, ResultBuffer, TypedValue, RegAppTableRecord,
)
from Autodesk.Civil.ApplicationServices import CivilApplication
from Autodesk.Civil.DatabaseServices import Alignment

XDATA_APP_DEFAULT = 'ROAD_SIGN_CSV'
_LOG = None


def _ensure_helpers():
    global _LOG
    if _LOG is not None:
        return _LOG
    here = os.path.dirname(__file__) if '__file__' in dir() else os.path.join(os.getcwd(), 'python')
    g = {}
    for mod in ('_log_utils', '_geom_utils'):
        p = os.path.join(here, mod + '.py')
        if os.path.isfile(p):
            exec(compile(open(p).read(), p, 'exec'), g)
    _LOG = g
    return g


def _ensure_layer(tr, db, layer_name):
    lt = tr.GetObject(db.LayerTableId, OpenMode.ForWrite)
    if lt.Has(layer_name):
        return
    ltr = LayerTableRecord()
    ltr.Name = layer_name
    lt.Add(ltr)
    tr.AddNewlyCreatedDBObject(ltr, True)


def _ensure_regapp(tr, db, app):
    rat = tr.GetObject(db.RegAppTableId, OpenMode.ForWrite)
    if rat.Has(app):
        return
    ra = RegAppTableRecord()
    ra.Name = app
    rat.Add(ra)
    tr.AddNewlyCreatedDBObject(ra, True)


def _erase_prior_signs(tr, msp, app):
    for eid in msp:
        ent = tr.GetObject(eid, OpenMode.ForRead)
        try:
            x = ent.GetXDataForApplication(app)
        except Exception:
            continue
        if x is None:
            continue
        ent.UpgradeOpen()
        ent.Erase()


def _heading_from_dense(align, sta, dense_fn):
    pts = dense_fn(align, max(sta - 0.5, 0), sta + 0.5, 0.5)
    if len(pts) >= 2:
        p0 = pts[0][1]
        p1 = pts[-1][1]
        return math.atan2(p1.Y - p0.Y, p1.X - p0.X)
    p0 = align.PointLocation(sta - 0.05, 0)
    p1 = align.PointLocation(sta + 0.05, 0)
    return math.atan2(p1.Y - p0.Y, p1.X - p0.X)


def _offsets_for_side(side, offset_m):
    side = (side or 'R').strip().upper()
    off = abs(float(offset_m))
    if side == 'BOTH':
        return [('L', -off), ('R', off)]
    if side == 'L':
        return [('L', -off)]
    return [('R', off)]


def _place_block(msp, tr, align, bt, bid, sta, off_signed, ang, layer_name, xdata_app, meta):
    ins = align.PointLocation(sta, off_signed)
    br = BlockReference(ins, bid)
    br.Layer = layer_name
    br.Rotation = ang
    br.XData = ResultBuffer(
        TypedValue(1001, xdata_app),
        TypedValue(1000, meta.get('row', '')),
        TypedValue(1000, meta.get('sign_code', '')),
        TypedValue(1000, meta.get('source', '')),
        TypedValue(1040, float(sta)),
    )
    msp.AppendEntity(br)
    tr.AddNewlyCreatedDBObject(br, True)


def run(csv_path, align_name, layer_name, xdata_app):
    lu = _ensure_helpers()
    log = lu['log_new']('M5')
    log_add = lu['log_add']
    out_wrap = lu['out_wrap']
    dense_fn = lu.get('get_dense_points')
    data = {
        'placed': 0,
        'missing_blocks': [],
        'placed_by_block': {},
        'placed_by_sign_code': {},
    }

    if not os.path.isfile(csv_path):
        log_add(log, 'ERROR', 'CSV_NOT_FOUND', 'CSV not found: ' + str(csv_path))
        return out_wrap(log, data, legacy_msg='ERROR: CSV not found: ' + str(csv_path))

    rows = []
    with codecs.open(csv_path, 'r', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    doc = Application.DocumentManager.MdiActiveDocument
    db = doc.Database
    civdoc = CivilApplication.ActiveDocument

    align_id = None
    for aid in civdoc.GetAlignmentIds():
        if Alignment.GetAlignmentName(aid) == align_name:
            align_id = aid
            break
    if align_id is None:
        log_add(log, 'ERROR', 'ALIGN_MISSING', 'Alignment not found: ' + align_name)
        return out_wrap(log, data, legacy_msg='ERROR: Alignment not found: ' + align_name)

    placed = 0
    missing = []
    missing_set = set()
    by_block = {}
    by_code = {}

    with doc.LockDocument():
        with db.TransactionManager.StartTransaction() as tr:
            bt = tr.GetObject(db.BlockTableId, OpenMode.ForRead)
            msp = tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite)
            align = tr.GetObject(align_id, OpenMode.ForRead)
            _ensure_layer(tr, db, layer_name)
            _ensure_regapp(tr, db, xdata_app)
            _erase_prior_signs(tr, msp, xdata_app)

            for r in rows:
                bname = r['block_name'].strip()
                if not bt.Has(bname):
                    if bname not in missing_set:
                        missing.append(bname)
                        missing_set.add(bname)
                    continue
                bid = bt[bname]
                sta = float(r['station_m'])
                off = float(r['offset_m'])
                side = r['side'].strip().upper()
                if dense_fn:
                    ang = _heading_from_dense(align, sta, dense_fn)
                else:
                    p0 = align.PointLocation(sta - 0.05, 0)
                    p1 = align.PointLocation(sta + 0.05, 0)
                    ang = math.atan2(p1.Y - p0.Y, p1.X - p0.X)
                if r.get('rotation_deg'):
                    try:
                        ang = float(r['rotation_deg']) * math.pi / 180.0
                    except Exception:
                        pass
                meta = {
                    'row': r.get('row', str(placed)),
                    'sign_code': r.get('sign_code', ''),
                    'source': r.get('source', 'manual'),
                }
                for _side_lbl, off_signed in _offsets_for_side(side, off):
                    _place_block(
                        msp, tr, align, bt, bid, sta, off_signed, ang,
                        layer_name, xdata_app, meta,
                    )
                    placed += 1
                    by_block[bname] = by_block.get(bname, 0) + 1
                    sc = meta.get('sign_code') or bname
                    by_code[sc] = by_code.get(sc, 0) + 1
            tr.Commit()

    data['placed'] = placed
    data['missing_blocks'] = sorted(missing)
    data['placed_by_block'] = by_block
    data['placed_by_sign_code'] = by_code

    if missing:
        log_add(
            log, 'ERROR', 'BLOCK_MISSING',
            'Missing blocks: ' + ', '.join(data['missing_blocks']),
        )
    for sc, n in sorted(by_code.items()):
        log_add(log, 'INFO', 'M5_COUNT', '%s: %d placed' % (sc, n))
    log_add(log, 'INFO', 'M5_DENSE', 'Sign rotation uses 0.5 m sub-sampling where available.')
    legacy = 'OK: Placed %d block(s) on layer "%s".' % (placed, layer_name)
    if missing:
        legacy = 'ERROR: Missing block(s): %s. Placed %d of scheduled.' % (
            ', '.join(data['missing_blocks']), placed,
        )
    log_add(log, 'INFO', 'M5_OK', legacy)
    return out_wrap(log, data, legacy_msg=legacy)


csv_path = IN[0]
align_name = IN[1]
layer_name = IN[2] if len(IN) > 2 else 'C-SGN-FURN'
xdata_app = IN[3] if len(IN) > 3 else XDATA_APP_DEFAULT

OUT = run(csv_path, align_name, layer_name, xdata_app)
