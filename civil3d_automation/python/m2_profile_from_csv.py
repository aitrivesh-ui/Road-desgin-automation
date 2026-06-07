# -*- coding: utf-8 -*-
"""
M2 — Finished-grade profile from PVI CSV.
Dynamo inputs:
  IN[0] csv path
  IN[1] alignment name
  IN[2] profile name
  IN[3] layer (default 0)
  IN[4] profile style (default Standard)
  IN[5] profile label set (default Standard)
  IN[6] max grade % (default from project or 8.0)
  IN[7] min grade % (default from project or 0.5)
  IN[8] optional pvi_table.json output path
"""
import clr
import csv
import codecs
import json
import os

clr.AddReference('AcMgd')
clr.AddReference('AcDbMgd')
clr.AddReference('AeccDbMgd')

from Autodesk.AutoCAD.ApplicationServices import Application
from Autodesk.AutoCAD.DatabaseServices import OpenMode, Transaction
from Autodesk.AutoCAD.Geometry import Point2d
from Autodesk.Civil.ApplicationServices import CivilApplication
from Autodesk.Civil.DatabaseServices import Alignment, Profile

_LOG = None
_IRC66 = None


def _ensure_log_utils():
    global _LOG
    if _LOG is not None:
        return _LOG
    here = os.path.dirname(__file__) if '__file__' in dir() else os.path.join(os.getcwd(), 'python')
    p = os.path.join(here, '_log_utils.py')
    g = {}
    if os.path.isfile(p):
        exec(compile(open(p).read(), p, 'exec'), g)
    _LOG = g
    return g


def _ensure_irc66():
    global _IRC66
    if _IRC66 is not None:
        return _IRC66
    here = os.path.dirname(__file__) if '__file__' in dir() else os.path.join(os.getcwd(), 'python')
    p = os.path.join(here, 'irc66_profile_core.py')
    g = {}
    if os.path.isfile(p):
        exec(compile(open(p).read(), p, 'exec'), g)
    _IRC66 = g
    return g


def _read_csv(path):
    rows = []
    with codecs.open(path, 'r', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def _design_from_cfg(project_cfg, gmax_in, gmin_in, vd_in=None):
    design = (project_cfg or {}).get('design') or {}
    gmax = float(gmax_in) if gmax_in is not None else float(design.get('max_grade_pct', 8.0) or 8.0)
    gmin = float(gmin_in) if gmin_in is not None else float(design.get('min_grade_pct', 0.5) or 0.5)
    vd = float(design.get('design_speed_kph', 80) or 80)
    if vd_in is not None:
        try:
            vd = float(vd_in)
        except Exception:
            pass
    enforce_k = design.get('irc66_enforce_k', True)
    if isinstance(enforce_k, str):
        enforce_k = enforce_k.lower() not in ('0', 'false', 'no')
    terrain = str(design.get('terrain', 'plain') or 'plain')
    kerbed = design.get('kerbed_road', True)
    if isinstance(kerbed, str):
        kerbed = kerbed.lower() not in ('0', 'false', 'no')
    return {
        'gmax': gmax,
        'gmin': gmin,
        'vd': vd,
        'irc66_enforce_k': bool(enforce_k),
        'terrain': terrain,
        'kerbed_road': bool(kerbed),
    }


def _read_alignment_meta(meta_path):
    if not meta_path or not os.path.isfile(meta_path):
        return None
    try:
        with codecs.open(meta_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _write_pvi_table(path, payload):
    if not path:
        return
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with codecs.open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)


def _apply_validation_log(log, log_add, issues):
    for item in issues:
        if len(item) >= 4:
            sev, code, msg, sta = item[0], item[1], item[2], item[3]
        else:
            sev, code, msg = item[0], item[1], item[2]
            sta = None
        kw = {}
        if sta is not None:
            kw['station'] = sta
        log_add(log, sev, code, msg, **kw)


def run(
    csv_path,
    align_name,
    profile_name,
    layer_name,
    style_name,
    label_set_name,
    gmax,
    gmin,
    pvi_table_path=None,
    design_speed_kph=None,
    irc66_enforce_k=True,
    terrain='plain',
    kerbed_road=True,
    project_cfg=None,
):
    lu = _ensure_log_utils()
    irc = _ensure_irc66()
    log = lu['log_new']('M2')
    log_add = lu['log_add']
    out_wrap = lu['out_wrap']
    safe_civil = lu.get('safe_civil')

    dsg = _design_from_cfg(project_cfg, gmax, gmin, design_speed_kph)
    gmax = dsg['gmax']
    gmin = dsg['gmin']
    vd = dsg['vd']
    irc66_enforce_k = dsg['irc66_enforce_k'] if irc66_enforce_k is None else irc66_enforce_k
    terrain = dsg['terrain'] if terrain is None else terrain
    kerbed_road = dsg['kerbed_road'] if kerbed_road is None else kerbed_road

    paths = (project_cfg or {}).get('paths') or {}
    meta_path = paths.get('alignment_meta', '')
    if meta_path and not os.path.isabs(meta_path):
        root = (project_cfg or {}).get('_root', '')
        if root:
            meta_path = os.path.normpath(os.path.join(root, meta_path))

    data = {
        'tangents': 0,
        'pvi_table': pvi_table_path or '',
        'profile_name': profile_name,
        'alignment_name': align_name,
    }

    if not os.path.isfile(csv_path):
        log_add(log, 'ERROR', 'CSV_NOT_FOUND', 'CSV not found: ' + str(csv_path))
        return out_wrap(log, data, legacy_msg='ERROR: CSV not found: ' + str(csv_path))

    rows = _read_csv(csv_path)
    if len(rows) < 2:
        log_add(log, 'ERROR', 'PVI_COUNT', 'Need at least 2 PVI rows')
        return out_wrap(log, data, legacy_msg='ERROR: Need at least 2 PVI rows')

    rows.sort(key=lambda r: float(r['station_m']))

    if irc:
        issues = irc['validate_all'](
            rows, vd, gmax, gmin,
            irc66_enforce_k=irc66_enforce_k,
            kerbed_road=kerbed_road,
            terrain=terrain,
            max_grade_override=gmax,
            check_osd=True,
        )
        _apply_validation_log(log, log_add, issues)

    for i, row in enumerate(rows):
        vc = float(row.get('curve_length_m', 0) or 0)
        if vc > 0 and (i == 0 or i == len(rows) - 1):
            log_add(
                log, 'WARN', 'V_CURVE_ENDPOINT',
                'Vertical curve at endpoint PVI sta %.1f ignored by Civil layout.' % float(row['station_m']),
                station=float(row['station_m']),
            )

    meta = _read_alignment_meta(meta_path)
    if meta is not None:
        total_len = meta.get('total_length_m')
        if total_len is not None:
            try:
                max_sta = max(float(r['station_m']) for r in rows)
                if max_sta > float(total_len) + 1e-3:
                    log_add(
                        log, 'WARN', 'ALIGN_RANGE',
                        'Profile max station %.1f exceeds alignment length %.1f m from alignment_meta.'
                        % (max_sta, float(total_len)),
                    )
            except Exception:
                pass

    doc = Application.DocumentManager.MdiActiveDocument
    db = doc.Database
    civdoc = CivilApplication.ActiveDocument

    align_id = None
    for aid in civdoc.GetAlignmentIds():
        if Alignment.GetAlignmentName(aid) == align_name:
            align_id = aid
            break
    if align_id is None:
        log_add(
            log, 'ERROR', 'ALIGN_MISSING',
            'Alignment not found: %s (run M1 first).' % align_name,
        )
        return out_wrap(log, data, legacy_msg='ERROR: Alignment not found: ' + align_name)

    with doc.LockDocument():
        with db.TransactionManager.StartTransaction() as tr:
            align = tr.GetObject(align_id, OpenMode.ForRead)
            for ex in align.GetProfileIds():
                p = tr.GetObject(ex, OpenMode.ForRead)
                if p.Name == profile_name:
                    log_add(log, 'ERROR', 'PROFILE_EXISTS', 'Profile "%s" already exists.' % profile_name)
                    return out_wrap(log, data, legacy_msg='ERROR: Profile "%s" already exists.' % profile_name)
            tr.Commit()

    def _create_profile():
        return Profile.CreateByLayout(profile_name, civdoc, align_name, layer_name, style_name, label_set_name)

    if safe_civil:
        prof_id, err = safe_civil(log, 'Profile.CreateByLayout', _create_profile, 'Profile not created', module_id='M2')
        if err:
            return out_wrap(log, data, legacy_msg='ERROR: Profile.CreateByLayout failed: ' + str(err))
    else:
        try:
            prof_id = Profile.CreateByLayout(profile_name, civdoc, align_name, layer_name, style_name, label_set_name)
        except Exception as ex:
            log_add(log, 'ERROR', 'CIVIL_API_FAIL', str(ex), api='Profile.CreateByLayout')
            return out_wrap(log, data, legacy_msg='ERROR: Profile.CreateByLayout failed: ' + str(ex))

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
                    log_add(log, 'WARN', 'V_CURVE_SKIP', 'Vertical curve at sta %.1f skipped: %s' % (sta, str(ex)), station=sta)
            tr.Commit()

    if irc and pvi_table_path:
        try:
            payload = irc['build_pvi_table_records'](rows, vd, profile_name, align_name, terrain)
            _write_pvi_table(pvi_table_path, payload)
            log_add(
                log, 'INFO', 'PVI_TABLE_WRITTEN',
                'Wrote pvi_table (%d PVIs) to %s' % (len(rows), pvi_table_path),
            )
        except Exception as ex:
            log_add(log, 'WARN', 'PVI_TABLE_FAIL', 'Could not write pvi_table: %s' % str(ex))

    data['tangents'] = len(rows) - 1
    legacy = 'OK: Profile "%s" created with %d tangents.' % (profile_name, data['tangents'])
    log_add(log, 'INFO', 'M2_OK', legacy)
    return out_wrap(log, data, legacy_msg=legacy)


_project_cfg = globals().get('PROJECT_CFG') or {}
_paths = _project_cfg.get('paths') or {}
_root = globals().get('PROJECT_ROOT') or ''
if _root:
    _project_cfg = dict(_project_cfg)
    _project_cfg['_root'] = _root

csv_path = IN[0]
align_name = IN[1]
profile_name = IN[2]
layer_name = IN[3] if len(IN) > 3 else '0'
style_name = IN[4] if len(IN) > 4 else 'Standard'
label_set_name = IN[5] if len(IN) > 5 else 'Standard'
gmax = float(IN[6]) if len(IN) > 6 and IN[6] is not None else None
gmin = float(IN[7]) if len(IN) > 7 and IN[7] is not None else None
pvi_table_path = IN[8] if len(IN) > 8 else _paths.get('pvi_table', '')

OUT = run(
    csv_path,
    align_name,
    profile_name,
    layer_name,
    style_name,
    label_set_name,
    gmax,
    gmin,
    pvi_table_path=pvi_table_path,
    project_cfg=_project_cfg,
)
