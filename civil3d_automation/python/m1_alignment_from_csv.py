# -*- coding: utf-8 -*-
"""
M1 — Alignment from PI CSV (polyline-style fixed lines).
Dynamo inputs:
  IN[0] : str — full path to alignment_pi.csv
  IN[1] : str — alignment name (must not already exist)
  IN[2] : str — alignment style name (e.g. Standard)
  IN[3] : str — alignment label set name (e.g. Standard)
  IN[4] : float — optional start station (default 0)
  IN[5] : str — optional curve_table.csv output path
  IN[6] : float — optional design speed km/h (overrides project when set)
  IN[7] : str — optional alignment_meta.json output path
"""
import clr
import csv
import codecs
import os
import math
import json

clr.AddReference('AcMgd')
clr.AddReference('AcDbMgd')
clr.AddReference('AecBaseMgd')
clr.AddReference('AeccDbMgd')

from Autodesk.AutoCAD.ApplicationServices import Application
from Autodesk.AutoCAD.DatabaseServices import OpenMode, Transaction
from Autodesk.AutoCAD.Geometry import Point3d
from Autodesk.Civil.ApplicationServices import CivilApplication
from Autodesk.Civil.DatabaseServices import Alignment

_LOG = None
_IRC38 = None
_ALN_ENT = None

CURVE_TABLE_HEADERS = [
    'station_m', 'radius_m', 'pi_id', 'design_speed_kph',
    'station_tc', 'station_ec', 'delta_deg', 'L_arc',
    'spiral_in_m', 'spiral_out_m', 'side', 'Ls_calc_m', 'Ls_min_m', 'osd_m',
]


def _py_dir():
    return os.path.dirname(__file__) if '__file__' in dir() else os.path.join(os.getcwd(), 'python')


def _load_helper(mod_name):
    p = os.path.join(_py_dir(), mod_name)
    g = {}
    if os.path.isfile(p):
        exec(compile(open(p).read(), p, 'exec'), g)
    return g


def _ensure_log_utils():
    global _LOG
    if _LOG is None:
        _LOG = _load_helper('_log_utils.py')
    return _LOG


def _ensure_irc38():
    global _IRC38
    if _IRC38 is None:
        _IRC38 = _load_helper('irc38_geometry.py')
    return _IRC38


def _ensure_aln_ent():
    global _ALN_ENT
    if _ALN_ENT is None:
        _ALN_ENT = _load_helper('_alignment_entities.py')
    return _ALN_ENT


def _read_csv(path):
    rows = []
    with codecs.open(path, 'r', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def _design_from_cfg(project_cfg, speed_override=None):
    design = (project_cfg or {}).get('design') or {}
    irc38 = design.get('irc38') or {}
    return {
        'design_speed_kph': float(speed_override if speed_override is not None else design.get('design_speed_kph', 80) or 80),
        'superelevation_pct': design.get('superelevation_pct', 7.0),
        'friction': design.get('friction'),
        'rate_change_c': design.get('rate_change_c', 0.5),
        'critical_factor': irc38.get('critical_radius_factor', 0.5),
    }


def _resolve_speed_kph(row, design):
    try:
        spd = float(row.get('design_speed_kph', 0) or 0)
        if spd > 0:
            return spd
    except Exception:
        pass
    return float(design.get('design_speed_kph', 80) or 80)


def _resolve_e_pct(row, design):
    try:
        e = row.get('superelevation_pct', '')
        if e not in (None, ''):
            return float(e)
    except Exception:
        pass
    return design.get('superelevation_pct', 7.0)


def _bearing_deg(x0, y0, x1, y1):
    return math.degrees(math.atan2(x1 - x0, y1 - y0))


def _deflection_and_side(p0, p1, p2):
    """External deflection at PI p1; side L/R from plan cross product."""
    b_in = _bearing_deg(p0[0], p0[1], p1[0], p1[1])
    b_out = _bearing_deg(p1[0], p1[1], p2[0], p2[1])
    delta = (b_out - b_in + 180.0) % 360.0 - 180.0
    defl = abs(delta)
    if defl < 1e-6:
        return 0.0, ''
    cross = (p1[0] - p0[0]) * (p2[1] - p1[1]) - (p1[1] - p0[1]) * (p2[0] - p1[0])
    side = 'L' if cross > 0 else 'R'
    return defl, side


def _chord_length(p0, p1):
    return math.hypot(p1[0] - p0[0], p1[1] - p0[1])


def _build_curve_rows_from_pis(pis, start_station, design):
    """PI fallback curve table rows (Phase 1 — geometry still straight segments)."""
    irc = _ensure_irc38()
    rows_out = []
    if len(pis) < 2:
        return rows_out
    coords = []
    for r in pis:
        coords.append((float(r['easting']), float(r['northing'])))
    sta = float(start_station)
    cum = [sta]
    for i in range(1, len(coords)):
        sta += _chord_length(coords[i - 1], coords[i])
        cum.append(sta)
    for i, r in enumerate(pis):
        try:
            rad = float(r.get('radius_m', 0) or 0)
        except Exception:
            continue
        if rad <= 0:
            continue
        vd = _resolve_speed_kph(r, design)
        e_pct = _resolve_e_pct(r, design)
        spi = float(r.get('spiral_in_m', 0) or 0)
        spo = float(r.get('spiral_out_m', 0) or 0)
        defl, side = 0.0, ''
        if 0 < i < len(coords) - 1:
            defl, side = _deflection_and_side(coords[i - 1], coords[i], coords[i + 1])
        ls_calc = irc.get('spiral_length', lambda *a: 0)(vd, rad, design.get('rate_change_c'))
        ls_min = irc.get('ls_min_table', lambda *a: 0)(vd)
        osd = irc.get('osd_table', lambda *a: None)(vd)
        sta_pi = cum[i]
        l_arc = rad * math.radians(defl) if defl > 0 else 0.0
        half_arc = l_arc * 0.5
        row = {
            'station_m': '%.3f' % sta_pi,
            'radius_m': '%.3f' % rad,
            'pi_id': r.get('pi_id', ''),
            'design_speed_kph': '%.0f' % vd,
            'station_tc': '%.3f' % max(sta_pi - half_arc, float(start_station)),
            'station_ec': '%.3f' % min(sta_pi + half_arc, cum[-1]),
            'delta_deg': '%.3f' % defl,
            'L_arc': '%.3f' % l_arc,
            'spiral_in_m': '%.3f' % spi,
            'spiral_out_m': '%.3f' % spo,
            'side': side,
            'Ls_calc_m': '%.3f' % ls_calc,
            'Ls_min_m': '%.3f' % ls_min,
            'osd_m': '' if osd is None else '%.1f' % osd,
            '_superelevation_pct': e_pct,
            '_vd': vd,
        }
        rows_out.append(row)
    return rows_out


def _validate_curve_rows(log, log_add, curve_rows, design):
    irc = _ensure_irc38()
    validate = irc.get('validate_radius')
    if not validate:
        return
    for row in curve_rows:
        try:
            rad = float(row.get('radius_m', 0) or 0)
            if rad <= 0:
                continue
            vd = float(row.get('_vd', row.get('design_speed_kph', 80)) or 80)
            e_pct = row.get('_superelevation_pct', design.get('superelevation_pct'))
            sta = float(row.get('station_m', 0) or 0)
            sev, code, r_min, crit_r = validate(
                rad, vd, e_pct, design.get('friction'), design.get('critical_factor')
            )
            if not sev:
                continue
            msg = 'Radius %.1f m < R_min %.1f m (critical %.1f m) at PI %s' % (
                rad, r_min, crit_r, row.get('pi_id', '?')
            )
            log_add(
                log, sev, code, msg,
                station=sta, radius_m=rad, r_min_m=r_min, critical_r_m=crit_r, design_speed_kph=vd,
            )
        except Exception:
            pass


def _write_curve_table(path, curve_rows):
    if not path:
        return
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with codecs.open(path, 'w', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(CURVE_TABLE_HEADERS)
        for r in curve_rows:
            w.writerow([r.get(h, '') for h in CURVE_TABLE_HEADERS])


def _write_alignment_meta(path, meta):
    if not path:
        return
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with codecs.open(path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)


def run(
    csv_path,
    alignment_name,
    style_name,
    label_set_name,
    start_station,
    curve_table_path,
    design_speed_override=None,
    meta_path=None,
    project_cfg=None,
):
    lu = _ensure_log_utils()
    log_new = lu.get('log_new', lambda m=None: {'entries': []})
    log_add = lu.get('log_add', lambda l, s, c, m, **k: l)
    out_wrap = lu.get('out_wrap', lambda l, d=None, legacy_msg=None: legacy_msg or '')
    safe_civil = lu.get('safe_civil')

    design = _design_from_cfg(project_cfg, design_speed_override)
    log = log_new('M1')
    data = {
        'curve_table': curve_table_path or '',
        'alignment_meta': meta_path or '',
        'alignment_name': alignment_name,
        'segments': 0,
        'total_length_m': 0.0,
        'curve_row_count': 0,
    }

    if not os.path.isfile(csv_path):
        log_add(log, 'ERROR', 'CSV_NOT_FOUND', 'CSV not found: ' + str(csv_path))
        return out_wrap(log, data, legacy_msg='ERROR: CSV not found: ' + str(csv_path))

    pis = _read_csv(csv_path)
    if len(pis) < 2:
        log_add(log, 'ERROR', 'PI_COUNT', 'Need at least 2 PI rows')
        return out_wrap(log, data, legacy_msg='ERROR: Need at least 2 PI rows')

    aln_ent = _ensure_aln_ent()
    geom_mode = aln_ent.get('geometry_mode', lambda d: 'polyline')(design)
    has_curves = aln_ent.get('pis_have_curves', lambda p: False)(pis)

    if geom_mode == 'polyline' and has_curves:
        for r in pis:
            try:
                rad = float(r.get('radius_m', 0) or 0)
                spi = float(r.get('spiral_in_m', 0) or 0)
                spo = float(r.get('spiral_out_m', 0) or 0)
                if rad != 0 or spi != 0 or spo != 0:
                    log_add(
                        log,
                        'WARN',
                        'PI_CURVE_STUB',
                        'PI %s has radius/spiral — polyline mode uses straight segments; set design.alignment.geometry_mode to scs.'
                        % r.get('pi_id', '?'),
                    )
            except Exception:
                pass

    curve_rows = _build_curve_rows_from_pis(pis, start_station, design)
    _validate_curve_rows(log, log_add, curve_rows, design)

    doc = Application.DocumentManager.MdiActiveDocument
    db = doc.Database
    civdoc = CivilApplication.ActiveDocument

    for aid in civdoc.GetAlignmentIds():
        if Alignment.GetAlignmentName(aid) == alignment_name:
            log_add(log, 'ERROR', 'ALIGN_EXISTS', "Alignment '%s' already exists." % alignment_name)
            return out_wrap(log, data, legacy_msg="ERROR: Alignment '%s' already exists." % alignment_name)

    build_state = {'total_length': 0.0, 'align_handle': ''}

    def _create_align():
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
                    build_state['align_handle'] = str(align_id)
                except Exception:
                    build_state['align_handle'] = alignment_name
                try:
                    align.ReferenceStation = float(start_station)
                except Exception:
                    pass
                ents = align.Entities
                pts = []
                for r in pis:
                    pts.append(Point3d(float(r['easting']), float(r['northing']), 0.0))
                populate = aln_ent.get('populate_entities')
                if populate:
                    seg_n, mode_used = populate(ents, pis, pts, design, log, log_add)
                    build_state['geometry_mode'] = mode_used
                    build_state['segments'] = seg_n
                else:
                    for i in range(len(pts) - 1):
                        ents.AddFixedLine(pts[i], pts[i + 1])
                    build_state['geometry_mode'] = 'polyline'
                    build_state['segments'] = len(pts) - 1
                try:
                    build_state['total_length'] = float(align.Length)
                except Exception:
                    tl = 0.0
                    for i in range(len(pts) - 1):
                        tl += pts[i].DistanceTo(pts[i + 1])
                    build_state['total_length'] = tl
                try:
                    spd = _resolve_speed_kph(pis[0], design)
                    if spd > 0 and hasattr(align, 'DesignSpeedSummary') and align.DesignSpeedSummary is not None:
                        align.DesignSpeedSummary.Clear()
                        align.DesignSpeedSummary.AddDesignSpeed(float(start_station), spd)
                except Exception:
                    pass
                tr.Commit()
        return build_state.get('segments', len(pts) - 1)

    if safe_civil:
        seg_count, err = safe_civil(log, 'Alignment.Create', _create_align, 'Cannot create alignment', module_id='M1')
        if err:
            return out_wrap(log, data, legacy_msg='ERROR: Alignment.Create failed')
    else:
        try:
            seg_count = _create_align()
        except Exception as ex:
            log_add(log, 'ERROR', 'CIVIL_API_FAIL', str(ex), api='Alignment.Create')
            return out_wrap(log, data, legacy_msg='ERROR: ' + str(ex))

    total_length = build_state['total_length']
    align_handle = build_state['align_handle']
    geom_used = build_state.get('geometry_mode', geom_mode)

    data['segments'] = seg_count
    data['geometry_mode'] = geom_used
    data['total_length_m'] = round(total_length, 3)
    data['aln_id'] = align_handle or alignment_name
    data['curve_row_count'] = len(curve_rows)

    if curve_table_path:
        try:
            _write_curve_table(curve_table_path, curve_rows)
            log_add(
                log, 'INFO', 'CURVE_TABLE',
                'Wrote curve table (%d rows) to %s.' % (len(curve_rows), curve_table_path),
            )
        except Exception as ex:
            log_add(log, 'WARN', 'CURVE_TABLE_FAIL', str(ex))

    if meta_path:
        try:
            meta = {
                'alignment_name': alignment_name,
                'aln_id': data['aln_id'],
                'total_length_m': data['total_length_m'],
                'design_speed_kph': design['design_speed_kph'],
                'start_station_m': float(start_station),
                'curve_row_count': len(curve_rows),
            }
            _write_alignment_meta(meta_path, meta)
            log_add(log, 'INFO', 'ALIGN_META', 'Wrote alignment metadata.')
        except Exception as ex:
            log_add(log, 'WARN', 'ALIGN_META_FAIL', str(ex))

    legacy = 'OK: Alignment "%s" created (%s, %d entities, L=%.3f m).' % (
        alignment_name, geom_used, seg_count, total_length
    )
    log_add(log, 'INFO', 'M1_OK', legacy)
    return out_wrap(log, data, legacy_msg=legacy)


_project_cfg = globals().get('PROJECT_CFG') or {}
_paths = _project_cfg.get('paths') or {}
_design = _project_cfg.get('design') or {}

csv_path = IN[0]
alignment_name = IN[1]
style_name = IN[2] if len(IN) > 2 else 'Standard'
label_set_name = IN[3] if len(IN) > 3 else 'Standard'
start_station = float(IN[4]) if len(IN) > 4 and IN[4] is not None else float(_design.get('start_station', 0.0) or 0.0)
curve_table_path = IN[5] if len(IN) > 5 else _paths.get('curve_table', '')
design_speed_override = None
if len(IN) > 6 and IN[6] is not None:
    try:
        design_speed_override = float(IN[6])
    except Exception:
        design_speed_override = None
meta_path = IN[7] if len(IN) > 7 else _paths.get('alignment_meta', '')

OUT = run(
    csv_path,
    alignment_name,
    style_name,
    label_set_name,
    start_station,
    curve_table_path,
    design_speed_override=design_speed_override,
    meta_path=meta_path,
    project_cfg=_project_cfg,
)
