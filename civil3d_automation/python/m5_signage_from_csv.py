# -*- coding: utf-8 -*-
"""
M5 — Place signage blocks from CSV at alignment station/offset.
Dynamo inputs:
  IN[0] : str — path to signage_schedule.csv
  IN[1] : str — alignment name
  IN[2] : str — layer name for new inserts
  IN[3] : str — optional XData app name (default ROAD_SIGN_CSV) for idempotent re-run
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
from Autodesk.AutoCAD.Geometry import Point3d
from Autodesk.Civil.ApplicationServices import CivilApplication
from Autodesk.Civil.DatabaseServices import Alignment

XDATA_APP_DEFAULT = 'ROAD_SIGN_CSV'


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


def run(csv_path, align_name, layer_name, xdata_app):
    if not os.path.isfile(csv_path):
        return 'ERROR: CSV not found: ' + str(csv_path)

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
        return 'ERROR: Alignment not found: ' + align_name

    placed = 0
    missing = []

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
                    missing.append(bname)
                    continue
                bid = bt[bname]
                sta = float(r['station_m'])
                off = float(r['offset_m'])
                side = r['side'].strip().upper()
                if side == 'L':
                    off = -abs(off)
                else:
                    off = abs(off)

                ins = align.PointLocation(sta, off)
                p0 = align.PointLocation(sta - 0.05, 0)
                p1 = align.PointLocation(sta + 0.05, 0)
                ang = math.atan2(p1.Y - p0.Y, p1.X - p0.X)
                if r.get('rotation_deg'):
                    try:
                        ang = float(r['rotation_deg']) * math.pi / 180.0
                    except Exception:
                        pass

                br = BlockReference(ins, bid)
                br.Layer = layer_name
                br.Rotation = ang
                rb = ResultBuffer(
                    TypedValue(1001, xdata_app),
                    TypedValue(1000, r.get('row', str(placed))),
                )
                br.XData = rb
                msp.AppendEntity(br)
                tr.AddNewlyCreatedDBObject(br, True)
                placed += 1

            tr.Commit()

    msg = 'OK: Placed %d block(s) on layer "%s".' % (placed, layer_name)
    if missing:
        msg += ' Missing blocks: ' + ', '.join(sorted(set(missing)))
    return msg


csv_path = IN[0]
align_name = IN[1]
layer_name = IN[2] if len(IN) > 2 else 'C-SGN-FURN'
xdata_app = IN[3] if len(IN) > 3 else XDATA_APP_DEFAULT

OUT = run(csv_path, align_name, layer_name, xdata_app)
