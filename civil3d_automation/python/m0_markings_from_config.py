# -*- coding: utf-8 -*-
"""
M0 — Road markings from schedule CSV (IRC:35-2015, MoRTH §803).

Dynamo / M8 inputs:
  IN[0] alignment name
  IN[1] markings_schedule.csv path
  IN[2] curve_table.csv path (from M1, for no-passing CL-DY)
  IN[3] marking_quantities output CSV path
  IN[4] default design speed kph (optional, default 80)
  IN[5] XData app name (optional, default IRC35_ROAD_MARK_V2)
"""
import clr
import csv
import codecs
import os

clr.AddReference('AcMgd')
clr.AddReference('AcDbMgd')
clr.AddReference('AeccDbMgd')

from Autodesk.AutoCAD.ApplicationServices import Application
from Autodesk.AutoCAD.DatabaseServices import (
    OpenMode, BlockTableRecord, LayerTableRecord, RegAppTableRecord,
)
from Autodesk.Civil.ApplicationServices import CivilApplication
from Autodesk.Civil.DatabaseServices import Alignment

_CORE = None
_LOG = None


def _load_module(name):
    here = os.path.dirname(__file__) if '__file__' in dir() else os.path.join(os.getcwd(), 'python')
    p = os.path.join(here, name + '.py')
    g = {}
    if os.path.isfile(p):
        exec(compile(open(p).read(), p, 'exec'), g)
    return g


def _ensure_core():
    global _CORE, _LOG
    if _CORE is not None:
        return _CORE, _LOG
    _CORE = _load_module('irc35_marking_core')
    _LOG = _load_module('_log_utils')
    g = _load_module('_geom_utils')
    if g:
        _LOG = dict(_LOG)
        _LOG.update(g)
    return _CORE, _LOG


def _ensure_layer(tr, db, layer_name, color_idx=7):
    lt = tr.GetObject(db.LayerTableId, OpenMode.ForWrite)
    if lt.Has(layer_name):
        return
    ltr = LayerTableRecord()
    ltr.Name = layer_name
    ltr.ColorIndex = int(color_idx)
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


def _read_schedule(path):
    if not path or not os.path.isfile(path):
        return []
    rows = []
    with codecs.open(path, 'r', encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def _offset_from_row(r):
    try:
        return float(r.get('offset_m', 0) or 0)
    except Exception:
        return 0.0


def run(align_name, schedule_path, curve_table_path, qty_csv_path, design_speed_kph, xdata_app):
    core, lu = _ensure_core()
    log = lu['log_new']('M0')
    log_add = lu['log_add']
    out_wrap = lu['out_wrap']
    dense_fn = lu.get('get_dense_points')
    xdata_app = xdata_app or core.get('XDATA_APP_DEFAULT', 'IRC35_ROAD_MARK_V2')

    data = {
        'spans_placed': 0,
        'solids_runs': 0,
        'no_pass_zones': 0,
        'qty_rows': 0,
    }
    qty_rows = []

    if not schedule_path or not os.path.isfile(schedule_path):
        log_add(log, 'ERROR', 'SCHEDULE_MISSING', 'markings_schedule CSV not found: ' + str(schedule_path))
        return out_wrap(log, data, legacy_msg='ERROR: markings_schedule CSV not found.')

    schedule = _read_schedule(schedule_path)
    if not schedule:
        log_add(log, 'ERROR', 'SCHEDULE_EMPTY', 'markings_schedule has no data rows.')
        return out_wrap(log, data, legacy_msg='ERROR: markings_schedule empty.')

    try:
        catalogue = core['load_catalogue']()
    except Exception as ex:
        log_add(log, 'ERROR', 'CATALOGUE', str(ex))
        return out_wrap(log, data, legacy_msg='ERROR: ' + str(ex))

    for i, r in enumerate(schedule):
        mt = (r.get('mark_type') or '').strip().upper()
        _, err = core['validate_mark_type'](mt, catalogue)
        if err:
            log_add(log, 'ERROR', 'MARK_TYPE', err, row=i + 1)
            return out_wrap(log, data, legacy_msg='ERROR: ' + err)
        mat = (r.get('material') or 'thermoplastic').strip().lower()
        _, err = core['validate_material'](mat, catalogue)
        if err:
            log_add(log, 'ERROR', 'MATERIAL', err, row=i + 1)
            return out_wrap(log, data, legacy_msg='ERROR: ' + err)

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

    curve_rows = core['read_curve_table_csv'](curve_table_path)
    if not curve_rows:
        log_add(log, 'WARN', 'CURVE_TABLE', 'No curve table — no-passing zones disabled.')

    with doc.LockDocument():
        with db.TransactionManager.StartTransaction() as tr:
            bt = tr.GetObject(db.BlockTableId, OpenMode.ForRead)
            msp = tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite)
            align = tr.GetObject(align_id, OpenMode.ForRead)
            _ensure_regapp(tr, db, xdata_app)

            try:
                align_len = float(align.Length)
            except Exception:
                align_len = 0.0
                if schedule:
                    try:
                        align_len = max(float(r.get('chainage_to', 0) or 0) for r in schedule)
                    except Exception:
                        align_len = 10000.0

            nopass = core['build_nopassing_intervals'](
                curve_rows, align_len, float(design_speed_kph or 80), catalogue
            )
            data['no_pass_zones'] = len(nopass)
            if nopass:
                log_add(log, 'INFO', 'NO_PASS', 'Computed %d no-passing zone(s).' % len(nopass))

            for idx, r in enumerate(schedule):
                try:
                    s0 = float(r['chainage_from'])
                    s1 = float(r['chainage_to'])
                except Exception:
                    log_add(log, 'WARN', 'CHAINAGE', 'Skipping row %d: bad chainage.' % (idx + 1))
                    continue
                if s1 <= s0:
                    log_add(log, 'WARN', 'CHAINAGE', 'Row %d: chainage_to must exceed chainage_from.' % (idx + 1))
                    continue

                base_type = (r.get('mark_type') or 'CL-D').strip().upper()
                material = (r.get('material') or 'thermoplastic').strip().lower()
                offset_m = _offset_from_row(r)
                spans = core['overlap_intervals'](s0, s1, nopass)

                for seg_i, (cs0, cs1, forced) in enumerate(spans):
                    mtype = forced if forced else base_type
                    if forced == 'CL-DY' and base_type == 'CL-D':
                        log_add(
                            log,
                            'WARN',
                            'NO_PASS_OVERRIDE',
                            'CL-D replaced by CL-DY at chainage %.1f–%.1f' % (cs0, cs1),
                            station=cs0,
                        )

                    source_key = '%s|%d|%d|%.3f|%.3f|%s' % (
                        align_name, idx, seg_i, cs0, cs1, mtype
                    )
                    pts = core['sample_alignment_offset'](
                        align, cs0, cs1, offset_m, core.get('SAMPLE_INTERVAL_M', 0.5), dense_fn
                    )
                    spec, _ = core['mark_spec'](mtype, catalogue)
                    layer, _ = core['layer_for_mark'](material, mtype, catalogue)
                    _ensure_layer(tr, db, layer, spec.get('color_idx', 7))

                    area, mlen, nseg, perr = core['place_mark_solid_run'](
                        tr, msp, pts, mtype, material, source_key, xdata_app, catalogue
                    )
                    if perr:
                        log_add(log, 'WARN', 'PLACE_FAIL', perr, station=cs0)
                        continue

                    data['spans_placed'] += 1
                    data['solids_runs'] += 1
                    qty_rows.append({
                        'mark_type': mtype,
                        'material': material,
                        'length_m': mlen,
                        'area_m2': area,
                        'chainage_from': cs0,
                        'chainage_to': cs1,
                    })
                    log_add(
                        log,
                        'INFO',
                        'MARK_PLACED',
                        '%s %s %.1f–%.1f m | %.1fm | %.2f m2' % (mtype, material, cs0, cs1, mlen, area),
                        station=cs0,
                    )

            tr.Commit()

    if qty_csv_path:
        try:
            core['write_marking_qty_csv'](qty_csv_path, qty_rows)
            data['qty_rows'] = len(qty_rows)
            log_add(log, 'INFO', 'QTY_CSV', 'Wrote %d row(s) to %s' % (len(qty_rows), qty_csv_path))
        except Exception as ex:
            log_add(log, 'ERROR', 'QTY_CSV', 'Failed to write marking quantities: ' + str(ex))

    log_add(log, 'INFO', 'M0_SAMPLE', 'Alignment sampled at 0.5 m for marking solids.')
    legacy = 'OK: M0 placed %d marking run(s), %d qty row(s), %d no-pass zone(s).' % (
        data['solids_runs'],
        len(qty_rows),
        data['no_pass_zones'],
    )
    log_add(log, 'INFO', 'M0_OK', legacy)
    return out_wrap(log, data, legacy_msg=legacy)


align_name = IN[0]
schedule_path = IN[1] if len(IN) > 1 else ''
curve_table_path = IN[2] if len(IN) > 2 else ''
qty_csv_path = IN[3] if len(IN) > 3 else ''
design_speed_kph = IN[4] if len(IN) > 4 else 80
xdata_app = IN[5] if len(IN) > 5 else 'IRC35_ROAD_MARK_V2'

OUT = run(align_name, schedule_path, curve_table_path, qty_csv_path, design_speed_kph, xdata_app)
