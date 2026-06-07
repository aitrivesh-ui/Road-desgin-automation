# -*- coding: utf-8 -*-
"""
IRC:66-2011 vertical profile helpers (no Civil 3D imports).
IRC:73-2015 minimum drainage grade checks.
Used by M2 and Python 3 unit tests in tools/.
"""
from __future__ import absolute_import

import math

try:
    from irc38_geometry import nearest_speed_bucket, osd_table, ssd_table
except ImportError:
    from .irc38_geometry import nearest_speed_bucket, osd_table, ssd_table  # type: ignore

# Handbook ROADGEN v2 / IRC:66 table (plain terrain g_max).
IRC66_SPEED_TABLE = {
    100: {'ssd': 150, 'k_crest': 72, 'k_sag': 30, 'g_max_plain_pct': 3.0},
    80: {'ssd': 120, 'k_crest': 44, 'k_sag': 20, 'g_max_plain_pct': 4.0},
    60: {'ssd': 90, 'k_crest': 20, 'k_sag': 12, 'g_max_plain_pct': 5.0},
    40: {'ssd': 45, 'k_crest': 6, 'k_sag': 6, 'g_max_plain_pct': 7.0},
}

IRC66_BUCKETS = sorted(IRC66_SPEED_TABLE.keys())
CONTRACT_VERSION = 1


def _row_float(row, key, default=0.0):
    try:
        return float(row.get(key, default) or default)
    except (TypeError, ValueError):
        return float(default)


def grade_pct(e0, e1, sta0, sta1):
    """Longitudinal grade (%) from sta0,e0 to sta1,e1."""
    d = float(sta1) - float(sta0)
    if d <= 1e-9:
        return 0.0
    return (float(e1) - float(e0)) / d * 100.0


def irc66_row(vd_kph):
    bucket = nearest_speed_bucket(vd_kph)
    if bucket in IRC66_SPEED_TABLE:
        return IRC66_SPEED_TABLE[bucket]
    return IRC66_SPEED_TABLE[80]


def k_crest_formula(ssd_m):
    ssd = float(ssd_m)
    return (ssd * ssd) / 658.0


def k_sag_formula(ssd_m):
    ssd = float(ssd_m)
    return (ssd * ssd) / (120.0 + 3.5 * ssd)


def k_required(curve_type, vd_kph):
    row = irc66_row(vd_kph)
    if curve_type == 'crest':
        return float(row['k_crest'])
    if curve_type == 'sag':
        return float(row['k_sag'])
    return 0.0


def k_actual(vc_length_m, algebraic_diff_pct):
    a = abs(float(algebraic_diff_pct))
    l = float(vc_length_m)
    if a <= 1e-9 or l <= 0:
        return None
    return l / a


def k_osd_crest_min(vd_kph):
    """
    Advisory minimum crest K when OSD governs (parallel to K_crest = SSD²/658).
    Returns None when OSD not tabulated for speed.
    """
    osd = osd_table(vd_kph)
    if osd is None or osd <= 0:
        return None
    return (osd * osd) / 658.0


def g_max_for_terrain(vd_kph, terrain='plain', override_pct=None):
    if override_pct is not None and override_pct != '':
        return float(override_pct)
    t = str(terrain or 'plain').lower()
    if t in ('plain', 'plains', 'rolling'):
        return float(irc66_row(vd_kph)['g_max_plain_pct'])
    return float(irc66_row(vd_kph)['g_max_plain_pct'])


def classify_pvi(rows, index):
    """
    Crest: grade in positive, grade out negative (summit).
    Sag: grade in negative, grade out positive (valley).
    """
    n = len(rows)
    if index <= 0 or index >= n - 1:
        return 'none'
    g_in = grade_pct(
        _row_float(rows[index - 1], 'elevation_m'),
        _row_float(rows[index], 'elevation_m'),
        _row_float(rows[index - 1], 'station_m'),
        _row_float(rows[index], 'station_m'),
    )
    g_out = grade_pct(
        _row_float(rows[index], 'elevation_m'),
        _row_float(rows[index + 1], 'elevation_m'),
        _row_float(rows[index], 'station_m'),
        _row_float(rows[index + 1], 'station_m'),
    )
    if g_in > 1e-6 and g_out < -1e-6:
        return 'crest'
    if g_in < -1e-6 and g_out > 1e-6:
        return 'sag'
    return 'none'


def pvi_grades(rows, index):
    """Return (g_in_pct, g_out_pct, algebraic_diff_pct) for interior PVI."""
    n = len(rows)
    if index <= 0 or index >= n - 1:
        return 0.0, 0.0, 0.0
    g_in = grade_pct(
        _row_float(rows[index - 1], 'elevation_m'),
        _row_float(rows[index], 'elevation_m'),
        _row_float(rows[index - 1], 'station_m'),
        _row_float(rows[index], 'station_m'),
    )
    g_out = grade_pct(
        _row_float(rows[index], 'elevation_m'),
        _row_float(rows[index + 1], 'elevation_m'),
        _row_float(rows[index], 'station_m'),
        _row_float(rows[index + 1], 'station_m'),
    )
    return g_in, g_out, g_out - g_in


def tangent_issues(rows, gmax, gmin, kerbed_road=True, vd_kph=80, terrain='plain', max_grade_override=None):
    """Grade QA on tangents between PVIs."""
    issues = []
    g_cap = g_max_for_terrain(vd_kph, terrain, max_grade_override)
    use_cap = min(float(gmax), g_cap) if gmax is not None else g_cap
    for i in range(1, len(rows)):
        a, b = rows[i - 1], rows[i]
        sta0 = _row_float(a, 'station_m')
        sta1 = _row_float(b, 'station_m')
        g = grade_pct(_row_float(a, 'elevation_m'), _row_float(b, 'elevation_m'), sta0, sta1)
        if abs(g) > use_cap:
            issues.append((
                'WARN',
                'GRADE_MAX',
                'Grade %.2f%% exceeds max %.2f%% (sta %.1f–%.1f)' % (g, use_cap, sta0, sta1),
                None,
            ))
        if kerbed_road and abs(g) < float(gmin) and abs(g) > 1e-6:
            issues.append((
                'WARN',
                'IRC73_DRAINAGE',
                'Grade %.2f%% below min %.2f%% (sta %.1f–%.1f)' % (g, gmin, sta0, sta1),
                None,
            ))
        elif not kerbed_road and abs(g) < float(gmin) and abs(g) > 1e-6:
            issues.append((
                'WARN',
                'GRADE_MIN',
                'Grade %.2f%% below min %.2f%% (sta %.1f–%.1f)' % (g, gmin, sta0, sta1),
                None,
            ))
    return issues


def validate_pvi_row(rows, index, vd_kph, irc66_enforce_k=True, check_osd=True):
    """
    Returns list of (severity, code, message, station_m).
    """
    issues = []
    n = len(rows)
    if index <= 0 or index >= n - 1:
        return issues
    sta = _row_float(rows[index], 'station_m')
    vc_len = _row_float(rows[index], 'curve_length_m')
    if vc_len <= 0:
        return issues
    curve_type = classify_pvi(rows, index)
    if curve_type == 'none':
        return issues
    g_in, g_out, a_diff = pvi_grades(rows, index)
    k_act = k_actual(vc_len, a_diff)
    k_req = k_required(curve_type, vd_kph)
    if k_act is not None and k_req > 0 and k_act < k_req:
        code = 'IRC66_K_CREST' if curve_type == 'crest' else 'IRC66_K_SAG'
        sev = 'WARN'
        if irc66_enforce_k:
            sev = 'WARN'
        msg = (
            '%s at sta %.1f: K_actual %.1f < K_required %.1f (L=%.1f m, A=%.2f%%)'
            % (curve_type.capitalize(), sta, k_act, k_req, vc_len, a_diff)
        )
        issues.append((sev, code, msg, sta))
    if check_osd and curve_type == 'crest':
        k_osd = k_osd_crest_min(vd_kph)
        osd = osd_table(vd_kph)
        if k_osd is not None and k_act is not None and k_act < k_osd:
            msg = (
                'Crest at sta %.1f: K_actual %.1f < OSD minimum K %.1f (OSD=%.0f m)'
                % (sta, k_act, k_osd, osd)
            )
            issues.append(('WARN', 'IRC66_OSD_CREST', msg, sta))
    return issues


def build_pvi_record(rows, index, vd_kph, terrain='plain'):
    """Single PVI dict for pvi_table.json."""
    row = rows[index]
    sta = _row_float(row, 'station_m')
    elev = _row_float(row, 'elevation_m')
    vc_len = _row_float(row, 'curve_length_m')
    curve_type = classify_pvi(rows, index) if 0 < index < len(rows) - 1 else 'none'
    g_in, g_out, a_diff = pvi_grades(rows, index) if curve_type != 'none' else (0.0, 0.0, 0.0)
    k_act = k_actual(vc_len, a_diff) if vc_len > 0 else None
    k_req = k_required(curve_type, vd_kph) if curve_type in ('crest', 'sag') else None
    validation = []
    for sev, code, msg, st in validate_pvi_row(rows, index, vd_kph):
        if code not in validation:
            validation.append(code)
    rec = {
        'station_m': sta,
        'elevation_m': elev,
        'grade_in_pct': round(g_in, 4) if index > 0 else None,
        'grade_out_pct': round(g_out, 4) if index < len(rows) - 1 else None,
        'vc_length_m': vc_len,
        'algebraic_diff_pct': round(a_diff, 4) if vc_len > 0 else None,
        'k_actual': round(k_act, 2) if k_act is not None else None,
        'k_required': round(k_req, 2) if k_req is not None else None,
        'curve_type': curve_type,
        'validation': validation,
    }
    if curve_type == 'crest':
        osd = osd_table(vd_kph)
        k_osd = k_osd_crest_min(vd_kph)
        if osd is not None:
            rec['osd_m'] = osd
        if k_osd is not None:
            rec['k_osd_min'] = round(k_osd, 2)
    return rec


def build_pvi_table_records(rows, vd_kph, profile_name='', alignment_name='', terrain='plain'):
    """All PVIs for export."""
    pvis = []
    for i in range(len(rows)):
        pvis.append(build_pvi_record(rows, i, vd_kph, terrain))
    return {
        'contract_version': CONTRACT_VERSION,
        'profile_name': profile_name,
        'alignment_name': alignment_name,
        'design_speed_kph': float(vd_kph),
        'terrain': str(terrain or 'plain'),
        'ssd_m': ssd_table(vd_kph),
        'pvis': pvis,
    }


def validate_all(rows, vd_kph, gmax, gmin, irc66_enforce_k=True, kerbed_road=True,
                 terrain='plain', max_grade_override=None, check_osd=True):
    """Aggregate validation issues for M2 logging."""
    issues = []
    issues.extend(tangent_issues(
        rows, gmax, gmin, kerbed_road=kerbed_road, vd_kph=vd_kph,
        terrain=terrain, max_grade_override=max_grade_override,
    ))
    for i in range(1, len(rows) - 1):
        issues.extend(validate_pvi_row(
            rows, i, vd_kph, irc66_enforce_k=irc66_enforce_k, check_osd=check_osd,
        ))
    return issues


def formula_table_consistency():
    """Return list of (speed, k_crest_tab, k_crest_formula, ...) for tests."""
    out = []
    for vd in IRC66_BUCKETS:
        row = IRC66_SPEED_TABLE[vd]
        ssd = row['ssd']
        out.append({
            'vd': vd,
            'k_crest_tab': row['k_crest'],
            'k_crest_formula': round(k_crest_formula(ssd), 1),
            'k_sag_tab': row['k_sag'],
            'k_sag_formula': round(k_sag_formula(ssd), 1),
        })
    return out
