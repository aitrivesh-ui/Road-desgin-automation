# -*- coding: utf-8 -*-
"""
M7 — BOQ-style CSV rollup (corridor volumes + marking solids + signage blocks).

Dynamo inputs:
  IN[0] : str — optional path to M4 volumes CSV (same folder convention as project)
  IN[1] : str — marking solids layer (e.g. C-ROAD-MARK)
  IN[2] : str — signage layer (e.g. C-SGN-FURN)
  IN[3] : str — payitems.csv path
  IN[4] : str — output BOQ CSV path
  IN[5] : str — optional corridor name (reserved for future QTO hooks)
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
    OpenMode, Transaction, BlockTableRecord, Solid3d, BlockReference,
)
from Autodesk.Civil.ApplicationServices import CivilApplication

MARK_XDATA = 'ROAD_MARK_SRC'
KNOWN_TYPES = ('M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8', 'M9', 'M10')


def _load_paymap(path):
    m = {}
    with codecs.open(path, 'r', encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            m[(r['source'].strip(), r['key'].strip())] = r
    return m


def _read_volume_csv(path):
    if not path or not os.path.isfile(path):
        return {}
    out = {}
    with codecs.open(path, 'r', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return out
    r0 = rows[-1]
    out[('volumes', 'cut_m3')] = float(r0.get('cut_m3', 0) or 0)
    out[('volumes', 'fill_m3')] = float(r0.get('fill_m3', 0) or 0)
    out[('volumes', 'net_m3')] = float(r0.get('net_m3', 0) or 0)
    return out


def _marking_stats(tr, db, layer):
    by_type = {}
    bt = tr.GetObject(db.BlockTableId, OpenMode.ForRead)
    msp = tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForRead)
    for oid in msp:
        ent = tr.GetObject(oid, OpenMode.ForRead)
        if ent.Layer != layer:
            continue
        if not isinstance(ent, Solid3d):
            continue
        xd = ent.GetXDataForApplication(MARK_XDATA)
        if xd is None:
            continue
        mtype = None
        for tv in xd:
            if tv.TypeCode == 1000 and str(tv.Value) in KNOWN_TYPES:
                mtype = str(tv.Value)
        if mtype is None:
            continue
        ext = ent.GeometricExtents
        approx_len = math.hypot(ext.MaxPoint.X - ext.MinPoint.X, ext.MaxPoint.Y - ext.MinPoint.Y)
        by_type[mtype] = by_type.get(mtype, 0.0) + approx_len
    return by_type


def _signage_counts(tr, db, layer):
    counts = {}
    bt = tr.GetObject(db.BlockTableId, OpenMode.ForRead)
    msp = tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForRead)
    for oid in msp:
        ent = tr.GetObject(oid, OpenMode.ForRead)
        if ent.Layer != layer:
            continue
        if not isinstance(ent, BlockReference):
            continue
        br = ent
        btr = tr.GetObject(br.BlockTableRecord, OpenMode.ForRead)
        nm = btr.Name
        counts[nm] = counts.get(nm, 0) + 1
    return counts


def _corridor_material_stub(civdoc, corridor_name):
    """Placeholder for material volumes — extend with your QTO API."""
    return {}


def run(vol_csv, mark_layer, sign_layer, pay_path, out_csv, corridor_name):
    if not pay_path or not os.path.isfile(pay_path):
        return 'ERROR: payitems CSV path missing or not found.'
    if not out_csv:
        return 'ERROR: output BOQ CSV path required.'
    pay = _load_paymap(pay_path)
    vols = _read_volume_csv(vol_csv)

    doc = Application.DocumentManager.MdiActiveDocument
    db = doc.Database
    civdoc = CivilApplication.ActiveDocument

    with doc.LockDocument():
        with db.TransactionManager.StartTransaction() as tr:
            marks = _marking_stats(tr, db, mark_layer)
            signs = _signage_counts(tr, db, sign_layer)
            mats = _corridor_material_stub(civdoc, corridor_name or '')
            tr.Commit()

    qty_lookup = {}
    qty_lookup.update(vols)
    qty_lookup.update(mats)
    for k, v in marks.items():
        qty_lookup[('marking', k)] = v
    for blk, c in signs.items():
        qty_lookup[('signage', blk)] = float(c)

    d = os.path.dirname(out_csv)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with codecs.open(out_csv, 'w', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['pay_item', 'description', 'unit', 'quantity', 'source', 'key'])
        for (src, key), row in sorted(pay.items(), key=lambda x: x[1].get('pay_item', '')):
            q = qty_lookup.get((src, key))
            if q is None:
                continue
            w.writerow([
                row.get('pay_item', ''),
                row.get('description', ''),
                row.get('unit', ''),
                '%.4f' % float(q),
                src,
                key,
            ])

    return 'OK: BOQ CSV written to ' + out_csv


vol_csv = IN[0] if len(IN) > 0 else ''
mark_layer = IN[1] if len(IN) > 1 else 'C-ROAD-MARK'
sign_layer = IN[2] if len(IN) > 2 else 'C-SGN-FURN'
pay_path = IN[3] if len(IN) > 3 else ''
out_csv = IN[4] if len(IN) > 4 else ''
corridor_name = IN[5] if len(IN) > 5 else ''

OUT = run(vol_csv, mark_layer, sign_layer, pay_path, out_csv, corridor_name)
