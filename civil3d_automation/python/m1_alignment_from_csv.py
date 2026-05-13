# -*- coding: utf-8 -*-
"""
M1 — Alignment from PI CSV (polyline-style fixed lines).
Dynamo inputs:
  IN[0] : str — full path to alignment_pi.csv
  IN[1] : str — alignment name (must not already exist)
  IN[2] : str — alignment style name (e.g. Standard)
  IN[3] : str — alignment label set name (e.g. Standard)
  IN[4] : float — optional start station (default 0)

Non-zero radius_m / spirals: logged as QA warnings only (extend with AddFreeCurve / SCS as needed).
"""
import clr
import csv
import codecs
import os

clr.AddReference('AcMgd')
clr.AddReference('AcDbMgd')
clr.AddReference('AecBaseMgd')
clr.AddReference('AeccDbMgd')

from Autodesk.AutoCAD.ApplicationServices import Application
from Autodesk.AutoCAD.DatabaseServices import OpenMode, Transaction
from Autodesk.AutoCAD.Geometry import Point3d
from Autodesk.Civil.ApplicationServices import CivilApplication
from Autodesk.Civil.DatabaseServices import Alignment


def _read_csv(path):
    rows = []
    with codecs.open(path, 'r', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def run(csv_path, alignment_name, style_name, label_set_name, start_station):
    warnings = []
    if not os.path.isfile(csv_path):
        return 'ERROR: CSV not found: ' + str(csv_path)

    pis = _read_csv(csv_path)
    if len(pis) < 2:
        return 'ERROR: Need at least 2 PI rows'

    for r in pis:
        try:
            if float(r.get('radius_m', 0) or 0) != 0 or float(r.get('spiral_in_m', 0) or 0) != 0:
                warnings.append('QA: PI %s has radius/spiral — geometry is still straight segments; extend script for curves.' % r.get('pi_id', '?'))
        except Exception:
            pass

    doc = Application.DocumentManager.MdiActiveDocument
    db = doc.Database
    civdoc = CivilApplication.ActiveDocument

    # Check duplicate name
    for aid in civdoc.GetAlignmentIds():
        if Alignment.GetAlignmentName(aid) == alignment_name:
            return "ERROR: Alignment '%s' already exists — rename or delete first." % alignment_name

    with doc.LockDocument():
        with db.TransactionManager.StartTransaction() as tr:
            layer_name = '0'
            try:
                align_id = Alignment.Create(
                    civdoc, alignment_name, None, layer_name, style_name, label_set_name
                )
            except Exception:
                align_id = Alignment.Create(
                    civdoc, alignment_name, '', layer_name, style_name, label_set_name
                )
            align = tr.GetObject(align_id, OpenMode.ForWrite)
            try:
                align.ReferenceStation = float(start_station)
            except Exception:
                pass

            ents = align.Entities
            pts = []
            for r in pis:
                x = float(r['easting'])
                y = float(r['northing'])
                z = 0.0
                pts.append(Point3d(x, y, z))

            for i in range(len(pts) - 1):
                ents.AddFixedLine(pts[i], pts[i + 1])

            # Design speed from first row if present
            try:
                spd = float(pis[0].get('design_speed_kph', 0) or 0)
                if spd > 0 and hasattr(align, 'DesignSpeedSummary') and align.DesignSpeedSummary is not None:
                    align.DesignSpeedSummary.Clear()
                    align.DesignSpeedSummary.AddDesignSpeed(float(start_station), spd)
            except Exception:
                pass

            tr.Commit()

    msg = 'OK: Alignment "%s" created with %d fixed-line segments.' % (alignment_name, len(pts) - 1)
    if warnings:
        msg += ' | ' + ' ; '.join(warnings)
    return msg


csv_path = IN[0]
alignment_name = IN[1]
style_name = IN[2] if len(IN) > 2 else 'Standard'
label_set_name = IN[3] if len(IN) > 3 else 'Standard'
start_station = float(IN[4]) if len(IN) > 4 and IN[4] is not None else 0.0

OUT = run(csv_path, alignment_name, style_name, label_set_name, start_station)
