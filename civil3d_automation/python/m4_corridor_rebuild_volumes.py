# -*- coding: utf-8 -*-
"""
M4 — Rebuild corridor, create TIN volume surface (EG vs FG), write CSV summary.
Uses TinVolumeSurface.Create(name, baseSurfaceId, comparisonSurfaceId) — Civil 3D 2022+.

Dynamo inputs:
  IN[0] : str — corridor name
  IN[1] : str — EG surface name (base / existing ground)
  IN[2] : str — FG surface name (comparison / design)
  IN[3] : str — output CSV path (full path)
  IN[4] : str — optional volume surface name (default corridor_VOL)
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
from Autodesk.Civil.ApplicationServices import CivilApplication
from Autodesk.Civil.DatabaseServices import Corridor, TinVolumeSurface


def _surface_id_by_name(tr, civdoc, name):
    for sid in civdoc.GetSurfaceIds():
        s = tr.GetObject(sid, OpenMode.ForRead)
        if hasattr(s, 'Name') and s.Name == name:
            return sid
    return None


def run(corridor_name, eg_name, fg_name, out_csv, vol_name):
    if not out_csv:
        return 'ERROR: output CSV path required'
    doc = Application.DocumentManager.MdiActiveDocument
    db = doc.Database
    civdoc = CivilApplication.ActiveDocument

    with doc.LockDocument():
        with db.TransactionManager.StartTransaction() as tr:
            cor_id = None
            for cid in civdoc.CorridorCollection.GetCorridorIds():
                if Corridor.GetCorridorName(cid) == corridor_name:
                    cor_id = cid
                    break
            if cor_id is None:
                return 'ERROR: Corridor not found: ' + corridor_name

            cor = tr.GetObject(cor_id, OpenMode.ForWrite)
            cor.Rebuild()

            eg_id = _surface_id_by_name(tr, civdoc, eg_name)
            fg_id = _surface_id_by_name(tr, civdoc, fg_name)
            if eg_id is None or fg_id is None:
                return 'ERROR: Surfaces not found (EG=%s FG=%s).' % (eg_name, fg_name)

            vname = vol_name or (corridor_name + '_VOL')
            try:
                vol_id = TinVolumeSurface.Create(vname, eg_id, fg_id)
            except Exception as ex:
                return 'ERROR: TinVolumeSurface.Create failed: ' + str(ex)

            vol = tr.GetObject(vol_id, OpenMode.ForRead)
            cut = 0.0
            fill = 0.0
            net = 0.0
            try:
                vp = vol.GetVolumeProperties()
                cut = vp.UnadjustedCutVolume
                fill = vp.UnadjustedFillVolume
                net = cut - fill
            except Exception:
                try:
                    vp = vol.GetVolumeProperties()
                    cut = vp.AdjustedCutVolume
                    fill = vp.AdjustedFillVolume
                    net = cut - fill
                except Exception:
                    pass

            tr.Commit()

    d = os.path.dirname(out_csv)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with codecs.open(out_csv, 'w', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['corridor', 'eg_surface', 'fg_surface', 'volume_surface', 'cut_m3', 'fill_m3', 'net_m3'])
        w.writerow([corridor_name, eg_name, fg_name, vname, '%.3f' % cut, '%.3f' % fill, '%.3f' % net])

    return 'OK: Rebuilt corridor; volume surface "%s"; wrote %s (cut=%.3f fill=%.3f net=%.3f).' % (
        vname, out_csv, cut, fill, net)


corridor_name = IN[0]
eg_name = IN[1]
fg_name = IN[2]
out_csv = IN[3]
vol_name = IN[4] if len(IN) > 4 else ''

OUT = run(corridor_name, eg_name, fg_name, out_csv, vol_name)
