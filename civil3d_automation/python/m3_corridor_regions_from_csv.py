# -*- coding: utf-8 -*-
"""
M3 — Corridor baseline regions from section_widths.csv.
Adds one region per CSV row (station ranges). Width/target columns are validated but
subassembly parameter edits are version-specific — extend after regions work.

Dynamo inputs:
  IN[0] : str — path to section_widths.csv
  IN[1] : str — corridor name
  IN[2] : str — default assembly name (used if CSV row has no assembly_name)
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
from Autodesk.Civil.DatabaseServices import Corridor


def _read_csv(path):
    rows = []
    with codecs.open(path, 'r', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def run(csv_path, corridor_name, default_assembly):
    notes = []
    if not os.path.isfile(csv_path):
        return 'ERROR: CSV not found: ' + str(csv_path)

    rows = _read_csv(csv_path)
    doc = Application.DocumentManager.MdiActiveDocument
    db = doc.Database
    civdoc = CivilApplication.ActiveDocument

    cor_id = None
    for cid in civdoc.CorridorCollection.GetCorridorIds():
        if Corridor.GetCorridorName(cid) == corridor_name:
            cor_id = cid
            break
    if cor_id is None:
        return 'ERROR: Corridor not found: ' + corridor_name

    with doc.LockDocument():
        with db.TransactionManager.StartTransaction() as tr:
            cor = tr.GetObject(cor_id, OpenMode.ForWrite)
            if cor.Baselines.Count < 1:
                return 'ERROR: Corridor has no baselines.'
            baseline = cor.Baselines[0]
            regions = baseline.BaselineRegions

            for r in rows:
                rid = r['region_id'].strip()
                asm = (r.get('assembly_name') or '').strip() or default_assembly
                s0 = float(r['start_sta'])
                s1 = float(r['end_sta'])
                try:
                    regions.Add(rid, asm, s0, s1)
                except Exception as ex:
                    return 'ERROR: BaselineRegions.Add failed for %s: %s' % (rid, str(ex))

            notes.append('Note: lane_width / shoulder / targets in CSV require manual subassembly mapping or API extension.')

            cor.Rebuild()
            tr.Commit()

    msg = 'OK: %d corridor region(s) applied on "%s".' % (len(rows), corridor_name)
    if notes:
        msg += ' | ' + ' '.join(notes)
    return msg


csv_path = IN[0]
corridor_name = IN[1]
default_assembly = IN[2] if len(IN) > 2 else 'BasicLaneAssembly'

OUT = run(csv_path, corridor_name, default_assembly)
