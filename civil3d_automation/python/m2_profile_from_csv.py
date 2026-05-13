# -*- coding: utf-8 -*-
"""
M2 — Finished-grade profile from PVI CSV.
Dynamo inputs:
  IN[0] : str — path to profile_pvis.csv
  IN[1] : str — existing alignment name
  IN[2] : str — new profile name
  IN[3] : str — layer name for profile
  IN[4] : str — profile style name
  IN[5] : str — profile label set name
  IN[6] : float — max grade |%| (QA)
  IN[7] : float — min grade |%| for drainage QA (use small positive e.g. 0.3)
"""
import clr
import csv
import codecs
import os

clr.AddReference('AcMgd')
clr.AddReference('AcDbMgd')
clr.AddReference('AeccDbMgd')

from Autodesk.AutoCAD.ApplicationServices import Application
from Autodesk.AutoCAD.DatabaseServices import OpenMode, Transaction
from Autodesk.AutoCAD.Geometry import Point2d
from Autodesk.Civil.ApplicationServices import CivilApplication
from Autodesk.Civil.DatabaseServices import Alignment, Profile


def _read_csv(path):
    rows = []
    with codecs.open(path, 'r', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def _grade_qa(pvis, gmax, gmin):
    issues = []
    for i in range(1, len(pvis)):
        a = pvis[i - 1]
        b = pvis[i]
        d = float(b['station_m']) - float(a['station_m'])
        if d <= 1e-9:
            continue
        g = (float(b['elevation_m']) - float(a['elevation_m'])) / d * 100.0
        if abs(g) > gmax:
            issues.append('Grade %.2f%% exceeds max %.2f%% (sta %.1f–%.1f)' % (g, gmax, float(a['station_m']), float(b['station_m'])))
        if abs(g) < gmin and abs(g) > 1e-6:
            issues.append('Grade %.2f%% below min %.2f%% (sta %.1f–%.1f)' % (g, gmin, float(a['station_m']), float(b['station_m'])))
    return issues


def run(csv_path, align_name, profile_name, layer_name, style_name, label_set_name, gmax, gmin):
    if not os.path.isfile(csv_path):
        return 'ERROR: CSV not found: ' + str(csv_path)

    rows = _read_csv(csv_path)
    rows.sort(key=lambda r: float(r['station_m']))
    qa = _grade_qa(rows, gmax, gmin)

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

    with doc.LockDocument():
        with db.TransactionManager.StartTransaction() as tr:
            align = tr.GetObject(align_id, OpenMode.ForRead)
            for ex in align.GetProfileIds():
                p = tr.GetObject(ex, OpenMode.ForRead)
                if p.Name == profile_name:
                    return 'ERROR: Profile "%s" already exists on alignment.' % profile_name
            tr.Commit()

    try:
        prof_id = Profile.CreateByLayout(
            profile_name, civdoc, align_name, layer_name, style_name, label_set_name
        )
    except Exception as ex:
        return 'ERROR: Profile.CreateByLayout failed: ' + str(ex)

    with doc.LockDocument():
        with db.TransactionManager.StartTransaction() as tr:
            prof = tr.GetObject(prof_id, OpenMode.ForWrite)
            ents = prof.Entities
            for i in range(1, len(rows)):
                a = rows[i - 1]
                b = rows[i]
                p0 = Point2d(float(a['station_m']), float(a['elevation_m']))
                p1 = Point2d(float(b['station_m']), float(b['elevation_m']))
                ents.AddFixedTangent(p0, p1)

            # Vertical curves at internal PVIs when length specified
            for i in range(1, len(rows) - 1):
                L = float(rows[i].get('curve_length_m', 0) or 0)
                if L <= 0:
                    continue
                sta = float(rows[i]['station_m'])
                try:
                    if hasattr(ents, 'AddFreeSymmetricParabolaByPVIAndCurveLength'):
                        pvi = None
                        for pv in prof.PVIs:
                            if abs(pv.Station - sta) < 1e-3:
                                pvi = pv
                                break
                        if pvi is not None:
                            ents.AddFreeSymmetricParabolaByPVIAndCurveLength(pvi, L)
                except Exception as ex:
                    qa.append('WARN: vertical curve at sta %.1f skipped: %s' % (sta, str(ex)))

            tr.Commit()

    msg = 'OK: Profile "%s" created with %d tangents.' % (profile_name, len(rows) - 1)
    if qa:
        msg += ' | ' + ' ; '.join(qa)
    return msg


csv_path = IN[0]
align_name = IN[1]
profile_name = IN[2]
layer_name = IN[3] if len(IN) > 3 else '0'
style_name = IN[4] if len(IN) > 4 else 'Standard'
label_set_name = IN[5] if len(IN) > 5 else 'Standard'
gmax = float(IN[6]) if len(IN) > 6 and IN[6] is not None else 8.0
gmin = float(IN[7]) if len(IN) > 7 and IN[7] is not None else 0.3

OUT = run(csv_path, align_name, profile_name, layer_name, style_name, label_set_name, gmax, gmin)
