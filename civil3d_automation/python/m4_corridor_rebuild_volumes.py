# -*- coding: utf-8 -*-
"""
M4 — Rebuild corridor, volume surface, swell/shrink columns, mass haul CSV.
Dynamo inputs:
  IN[0] corridor, IN[1] EG, IN[2] FG, IN[3] volumes CSV, IN[4] vol surface name,
  IN[5] soil_type, IN[6] mass_haul_csv path,
  IN[7] section_widths CSV (optional), IN[8] alignment_meta JSON (optional),
  IN[9] volume_sample_interval_m (optional, default 20),
  IN[10] fill_depth_csv path (optional), IN[11] mass_haul_meta JSON (optional)
"""
import clr
import csv
import codecs
import os
import json

clr.AddReference('AcMgd')
clr.AddReference('AcDbMgd')
clr.AddReference('AeccDbMgd')

from Autodesk.AutoCAD.ApplicationServices import Application
from Autodesk.AutoCAD.DatabaseServices import OpenMode, Transaction
from Autodesk.Civil.ApplicationServices import CivilApplication
from Autodesk.Civil.DatabaseServices import Corridor, TinVolumeSurface

_LOG = None

VOLUME_HEADERS = [
    'record_type', 'region_name', 'station_from', 'station_to', 'assembly_name',
    'corridor', 'eg_surface', 'fg_surface', 'volume_surface',
    'cut_m3', 'fill_m3', 'net_m3',
    'cut_bank_m3', 'fill_comp_m3',
    'cut_haul_m3', 'fill_borrow_m3', 'net_haul_m3', 'borrow_req_m3', 'spoil_m3',
    'cut_loose_m3', 'fill_compacted_m3',
    'swell_factor', 'shrink_factor', 'soil_type',
]


def _ensure_helpers():
    global _LOG
    if _LOG is not None:
        return _LOG
    here = os.path.dirname(__file__) if '__file__' in dir() else os.path.join(os.getcwd(), 'python')
    g = {}
    for mod in ('_log_utils', 'earthwork_factors'):
        p = os.path.join(here, mod + '.py')
        if os.path.isfile(p):
            exec(compile(open(p).read(), p, 'exec'), g)
    _LOG = g
    return g


def _read_csv(path):
    rows = []
    if not path or not os.path.isfile(path):
        return rows
    with codecs.open(path, 'r', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def _read_alignment_meta(path):
    if not path or not os.path.isfile(path):
        return None
    with codecs.open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _surface_id_by_name(tr, civdoc, name):
    for sid in civdoc.GetSurfaceIds():
        s = tr.GetObject(sid, OpenMode.ForRead)
        if hasattr(s, 'Name') and s.Name == name:
            return sid
    return None


def _volume_row(record_type, region_name, station_from, station_to, assembly_name,
                corridor_name, eg_name, fg_name, vname, cut, fill, ss):
    net = cut - fill
    return [
        record_type,
        region_name or '',
        '' if station_from is None else '%.3f' % station_from,
        '' if station_to is None else '%.3f' % station_to,
        assembly_name or '',
        corridor_name, eg_name, fg_name, vname,
        '%.3f' % cut, '%.3f' % fill, '%.3f' % net,
        '%.3f' % ss.get('cut_bank_m3', cut),
        '%.3f' % ss.get('fill_comp_m3', fill),
        '%.3f' % ss.get('cut_haul_m3', cut),
        '%.3f' % ss.get('fill_borrow_m3', fill),
        '%.3f' % ss.get('net_haul_m3', net),
        '%.3f' % ss.get('borrow_req_m3', 0),
        '%.3f' % ss.get('spoil_m3', 0),
        '%.3f' % ss.get('cut_loose_m3', cut),
        '%.3f' % ss.get('fill_compacted_m3', fill),
        ss.get('swell_factor', 1.0),
        ss.get('shrink_factor', 1.0),
        ss.get('soil_type', ''),
    ]


def run(
    corridor_name,
    eg_name,
    fg_name,
    out_csv,
    vol_name,
    soil_type,
    mass_haul_path,
    section_widths_path='',
    alignment_meta_path='',
    interval_m=20.0,
    fill_depth_path='',
    mass_haul_meta_path='',
):
    lu = _ensure_helpers()
    log = lu['log_new']('M4')
    log_add = lu['log_add']
    out_wrap = lu['out_wrap']
    safe_civil = lu.get('safe_civil')
    apply_ss = lu.get('apply_swell_shrink')
    mass_haul_fn = lu.get('mass_haul_ordinates')
    allocate_regions = lu.get('allocate_region_volumes')
    fill_depth_fn = lu.get('fill_depth_from_mass_haul')
    data = {}

    if not out_csv:
        log_add(log, 'ERROR', 'OUT_PATH', 'output CSV path required')
        return out_wrap(log, data, legacy_msg='ERROR: output CSV path required')

    doc = Application.DocumentManager.MdiActiveDocument
    db = doc.Database
    civdoc = CivilApplication.ActiveDocument
    cut = fill = net = 0.0
    vname = vol_name or (corridor_name + '_VOL')

    def _volumes():
        nonlocal cut, fill, net, vname
        with doc.LockDocument():
            with db.TransactionManager.StartTransaction() as tr:
                cor_id = None
                for cid in civdoc.CorridorCollection.GetCorridorIds():
                    if Corridor.GetCorridorName(cid) == corridor_name:
                        cor_id = cid
                        break
                if cor_id is None:
                    raise Exception('Corridor not found: ' + corridor_name)
                cor = tr.GetObject(cor_id, OpenMode.ForWrite)
                cor.Rebuild()
                eg_id = _surface_id_by_name(tr, civdoc, eg_name)
                fg_id = _surface_id_by_name(tr, civdoc, fg_name)
                if eg_id is None or fg_id is None:
                    raise Exception('Surfaces not found (EG=%s FG=%s).' % (eg_name, fg_name))
                vol_id = TinVolumeSurface.Create(vname, eg_id, fg_id)
                vol = tr.GetObject(vol_id, OpenMode.ForRead)
                try:
                    vp = vol.GetVolumeProperties()
                    cut = vp.UnadjustedCutVolume
                    fill = vp.UnadjustedFillVolume
                except Exception:
                    vp = vol.GetVolumeProperties()
                    cut = vp.AdjustedCutVolume
                    fill = vp.AdjustedFillVolume
                net = cut - fill
                tr.Commit()

    if safe_civil:
        _, err = safe_civil(log, 'TinVolumeSurface.Create', _volumes, 'Volume surface not created', module_id='M4')
        if err:
            return out_wrap(log, data, legacy_msg='ERROR: ' + str(err))
    else:
        try:
            _volumes()
        except Exception as ex:
            log_add(log, 'ERROR', 'CIVIL_API_FAIL', str(ex), api='TinVolumeSurface.Create')
            return out_wrap(log, data, legacy_msg='ERROR: ' + str(ex))

    ss = apply_ss(cut, fill, soil_type) if apply_ss else {
        'cut_m3': cut, 'fill_m3': fill, 'cut_bank_m3': cut, 'fill_comp_m3': fill,
        'cut_haul_m3': cut, 'fill_borrow_m3': fill, 'cut_loose_m3': cut,
        'fill_compacted_m3': fill, 'net_haul_m3': cut - fill,
        'borrow_req_m3': 0, 'spoil_m3': 0,
    }
    data.update(ss)

    region_rows = _read_csv(section_widths_path)
    meta = _read_alignment_meta(alignment_meta_path)
    length_m = 1000.0
    if meta and meta.get('total_length_m') is not None:
        length_m = float(meta['total_length_m'])

    d = os.path.dirname(out_csv)
    if d and not os.path.isdir(d):
        os.makedirs(d)

    csv_rows = []
    if region_rows and allocate_regions:
        splits = allocate_regions(cut, fill, region_rows)
        for reg in splits:
            rss = apply_ss(reg['cut_m3'], reg['fill_m3'], soil_type) if apply_ss else {}
            csv_rows.append(_volume_row(
                'region', reg['region_name'], reg['station_from'], reg['station_to'],
                reg.get('assembly_name', ''), corridor_name, eg_name, fg_name, vname,
                reg['cut_m3'], reg['fill_m3'], rss,
            ))
        data['regions'] = len(splits)
        log_add(log, 'INFO', 'M4_REGIONS', '%d region volume row(s) (proportional split).' % len(splits))

    csv_rows.append(_volume_row(
        'summary', '', None, None, '', corridor_name, eg_name, fg_name, vname, cut, fill, ss,
    ))

    with codecs.open(out_csv, 'w', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(VOLUME_HEADERS)
        for row in csv_rows:
            w.writerow(row)

    mh_summary = {}
    mh_rows = []
    if mass_haul_path and mass_haul_fn:
        mh_rows, mh_summary = mass_haul_fn(
            ss.get('cut_haul_m3', cut),
            ss.get('fill_borrow_m3', fill),
            interval_m=float(interval_m or 20.0),
            length_m=length_m,
        )
        md = os.path.dirname(mass_haul_path)
        if md and not os.path.isdir(md):
            os.makedirs(md)
        with codecs.open(mass_haul_path, 'w', encoding='utf-8') as mf:
            w = csv.writer(mf)
            w.writerow(['station_m', 'ordinate_m3', 'haul_direction', 'cumulative_volume',
                        'cut_ordinate_m3', 'fill_ordinate_m3', 'net_ordinate_m3'])
            for r in mh_rows:
                w.writerow([
                    r['station_m'], r['ordinate_m3'], r['haul_direction'],
                    r['cumulative_volume'], r['cut_ordinate_m3'],
                    r['fill_ordinate_m3'], r['net_ordinate_m3'],
                ])
        data['mass_haul'] = mh_summary
        log_add(
            log, 'INFO', 'MASS_HAUL',
            'Wrote %d ordinates; economic lead %.1f m' % (
                mh_summary.get('sample_count', len(mh_rows)),
                mh_summary.get('economic_lead_m', 0),
            ),
        )

        if mass_haul_meta_path:
            meta_dir = os.path.dirname(mass_haul_meta_path)
            if meta_dir and not os.path.isdir(meta_dir):
                os.makedirs(meta_dir)
            with codecs.open(mass_haul_meta_path, 'w', encoding='utf-8') as jf:
                jf.write(json.dumps(mh_summary, indent=2))
                jf.write('\n')

    if fill_depth_path and fill_depth_fn and mh_rows:
        fd_rows, max_fill = fill_depth_fn(mh_rows)
        fdd = os.path.dirname(fill_depth_path)
        if fdd and not os.path.isdir(fdd):
            os.makedirs(fdd)
        with codecs.open(fill_depth_path, 'w', encoding='utf-8') as ff:
            w = csv.writer(ff)
            w.writerow(['station_m', 'fill_depth_m', 'max_fill_height_m'])
            for r in fd_rows:
                w.writerow([r['station_m'], '%.3f' % r['fill_depth_m'], '%.3f' % r['max_fill_height_m']])
        data['max_fill_height_m'] = max_fill
        log_add(log, 'INFO', 'FILL_DEPTH', 'Wrote fill depth profile; max %.2f m' % max_fill)

    meta_out = {
        'volume_surface': vname,
        'corridor': corridor_name,
        'length_m': length_m,
        'interval_m': float(interval_m or 20.0),
        'region_split': 'proportional_by_chainage' if region_rows else 'none',
        'sample_line_count': mh_summary.get('sample_count', 0),
    }
    meta_path = os.path.join(d or '.', 'm4_volume_meta.json')
    with codecs.open(meta_path, 'w', encoding='utf-8') as mf:
        mf.write(json.dumps(meta_out, indent=2))
        mf.write('\n')
    data['meta_path'] = meta_path

    legacy = 'OK: Rebuilt corridor; volume "%s"; cut=%.3f fill=%.3f haul_cut=%.3f borrow=%.3f.' % (
        vname, cut, fill, ss.get('cut_haul_m3', cut), ss.get('fill_borrow_m3', fill))
    log_add(log, 'INFO', 'M4_OK', legacy)
    return out_wrap(log, data, legacy_msg=legacy)


corridor_name = IN[0]
eg_name = IN[1]
fg_name = IN[2]
out_csv = IN[3]
vol_name = IN[4] if len(IN) > 4 else ''
soil_type = IN[5] if len(IN) > 5 else 'ordinary_soil'
mass_haul_path = IN[6] if len(IN) > 6 else ''
section_widths_path = IN[7] if len(IN) > 7 else ''
alignment_meta_path = IN[8] if len(IN) > 8 else ''
interval_m = IN[9] if len(IN) > 9 else 20.0
fill_depth_path = IN[10] if len(IN) > 10 else ''
mass_haul_meta_path = IN[11] if len(IN) > 11 else ''

OUT = run(
    corridor_name, eg_name, fg_name, out_csv, vol_name, soil_type, mass_haul_path,
    section_widths_path, alignment_meta_path, interval_m, fill_depth_path, mass_haul_meta_path,
)
