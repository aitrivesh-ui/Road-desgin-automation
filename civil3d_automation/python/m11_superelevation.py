# -*- coding: utf-8 -*-
"""
M11 — Superelevation Assignment from CSV.

Reads superelevation.csv, attempts to apply control points via the Civil 3D
SupElevAssignment API (Civil 3D 2022+, gracefully skipped if unavailable),
writes an MText annotation table to the drawing on layer C-SUPER, and writes
a formatted superelevation_table.csv to the output path.

Dynamo inputs:
  IN[0] : str — absolute path to config/project.json

project.json keys consumed:
  paths.superelevation        -> csv/superelevation.csv
  paths.super_table_csv       -> out/superelevation_table.csv
  names.alignment             -> alignment name
  names.layers.superelevation -> layer name (default C-SUPER)
  design.normal_crown_m       -> optional normal crown width metres (default 0.0)
"""
import clr
clr.AddReference('AcMgd')
clr.AddReference('AcDbMgd')
clr.AddReference('AeccDbMgd')

import codecs, csv, os, json, math

from Autodesk.AutoCAD.ApplicationServices import Application
from Autodesk.AutoCAD.DatabaseServices import (
    Transaction, OpenMode, BlockTableRecord, BlockTable,
    ResultBuffer, TypedValue, Polyline, Polyline3d, Poly3dType,
    Point3dCollection, MText,
)
from Autodesk.AutoCAD.Geometry import Point2d, Point3d
from Autodesk.Civil.ApplicationServices import CivilApplication
from Autodesk.Civil.DatabaseServices import Alignment


# ---------------------------------------------------------------------------
# Helpers
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


def _read_super_csv(path):
    rows = []
    with codecs.open(path, 'r', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(project_json):
    if not os.path.isfile(project_json):
        return 'ERROR: project.json not found: %s' % project_json

    try:
        with codecs.open(project_json, 'r', encoding='utf-8-sig') as fj:
            cfg = json.loads(fj.read())
    except Exception as ex:
        return 'ERROR: Cannot parse project.json: %s' % str(ex)

    base = os.path.dirname(os.path.abspath(project_json))
    root = os.path.normpath(os.path.join(base, '..'))

    paths  = cfg.get('paths', {})
    names  = cfg.get('names', {})
    design = cfg.get('design', {})
    layers = names.get('layers', {})

    # --- resolve paths -------------------------------------------------------
    super_csv_rel = paths.get('superelevation', 'csv/superelevation.csv')
    super_csv     = _resolve(root, super_csv_rel)

    table_csv_rel = paths.get('super_table_csv', 'out/superelevation_table.csv')
    table_csv     = _resolve(root, table_csv_rel)

    align_name   = names.get('alignment', 'ALIGN')
    layer_name   = layers.get('superelevation', 'C-SUPER')
    normal_crown = float(design.get('normal_crown_m', 0.0))

    # --- read superelevation CSV ---------------------------------------------
    if not os.path.isfile(super_csv):
        return 'ERROR: Superelevation CSV not found: %s' % super_csv

    try:
        rows = _read_super_csv(super_csv)
    except Exception as ex:
        return 'ERROR: Cannot read superelevation CSV: %s' % str(ex)

    if not rows:
        return 'ERROR: Superelevation CSV is empty: %s' % super_csv

    required_cols = ['station_m', 'left_slope_pct', 'right_slope_pct', 'transition_length_m']
    for col in required_cols:
        if col not in rows[0]:
            return 'ERROR: Superelevation CSV missing column: %s' % col

    # --- open Civil 3D document & transaction --------------------------------
    doc    = Application.DocumentManager.MdiActiveDocument
    db     = doc.Database
    civdoc = CivilApplication.ActiveDocument

    # Locate alignment id before main transaction
    align_id = None
    for aid in civdoc.GetAlignmentIds():
        try:
            with db.TransactionManager.StartTransaction() as tr_peek:
                a_tmp = tr_peek.GetObject(aid, OpenMode.ForRead)
                if a_tmp.Name == align_name:
                    align_id = aid
                tr_peek.Abort()
        except Exception:
            pass
        if align_id is not None:
            break

    api_msg = ''

    with doc.LockDocument():
        with db.TransactionManager.StartTransaction() as tr:
            bt  = tr.GetObject(db.BlockTableId, OpenMode.ForRead)
            msp = tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite)

            # C-SUPER layer — color 3 (green)
            _ensure_layer(tr, db, layer_name, color_idx=3)

            # --- Try SupElevAssignment API (Civil 3D 2022+) ------------------
            try:
                from Autodesk.Civil.DatabaseServices import SupElevAssignment
                if align_id is None:
                    raise ValueError('Alignment not found: %s' % align_name)

                align_w = tr.GetObject(align_id, OpenMode.ForWrite)
                se_coll = align_w.SupElevAssignmentCollection

                try:
                    se_coll.Clear()
                except Exception:
                    pass

                for row in rows:
                    sta   = float(row['station_m'])
                    l_pct = float(row['left_slope_pct'])
                    r_pct = float(row['right_slope_pct'])
                    se_coll.AddControlPoint(sta, l_pct / 100.0, r_pct / 100.0)

                api_msg = 'SupElevAssignment API applied (%d pts)' % len(rows)

            except Exception as ex_api:
                api_msg = 'SupElevAssignment API skipped (%s)' % str(ex_api)

            # --- MText annotation table in drawing ---------------------------
            mt = MText()
            mt.Location   = Point3d(0.0, -200.0, 0.0)
            mt.Layer      = layer_name
            mt.TextHeight = 2.5

            # \\P = MText paragraph break
            content  = '{\\C3;SUPERELEVATION TABLE}\\P'
            content += '{\\C7;STA (m)  |  LEFT%%  |  RIGHT%%  |  TRANS(m)}\\P'
            content += '-------------------------------------------\\P'
            for row in rows:
                sta   = float(row['station_m'])
                l_pct = float(row['left_slope_pct'])
                r_pct = float(row['right_slope_pct'])
                tran  = float(row['transition_length_m'])
                content += 'STA %s: L=%.1f%%  R=%.1f%%  T=%.1fm\\P' % (
                    row['station_m'].strip(), l_pct, r_pct, tran
                )

            mt.Contents = content
            msp.AppendEntity(mt)
            tr.AddNewlyCreatedDBObject(mt, True)

            tr.Commit()

    # --- Write superelevation_table.csv -------------------------------------
    out_dir = os.path.dirname(table_csv)
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    try:
        with codecs.open(table_csv, 'w', encoding='utf-8') as f:
            writer = csv.writer(f, lineterminator='\n')
            writer.writerow([
                'station_m', 'left_slope_pct', 'right_slope_pct',
                'transition_length_m', 'normal_crown_m'
            ])
            for row in rows:
                sta   = row['station_m'].strip()
                l_pct = '%.4f' % float(row['left_slope_pct'])
                r_pct = '%.4f' % float(row['right_slope_pct'])
                tran  = '%.4f' % float(row['transition_length_m'])
                writer.writerow([sta, l_pct, r_pct, tran, '%.4f' % normal_crown])
    except Exception as ex_csv:
        return 'ERROR: Cannot write output CSV: %s' % str(ex_csv)

    return (
        'OK: M11 superelevation — %d stations processed. '
        'Layer=%s. Table CSV: %s. %s'
    ) % (len(rows), layer_name, table_csv, api_msg)


# ---------------------------------------------------------------------------
# Dynamo entry point
# ---------------------------------------------------------------------------

try:
    _project_json = IN[0]
    OUT = run(_project_json)
except Exception as _ex_top:
    OUT = 'ERROR: Unhandled exception in M11: %s' % str(_ex_top)
