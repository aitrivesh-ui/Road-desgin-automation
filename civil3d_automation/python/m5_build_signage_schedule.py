# -*- coding: utf-8 -*-
"""
M5 pre-Civil — Build signage schedule from curve_table, alignment_meta, fill_depth.

Usage:
  python m5_build_signage_schedule.py --project ../config/project.json

Writes paths.signage_generated (merged manual + auto when merge_manual).
"""
from __future__ import absolute_import, print_function

import argparse
import csv
import json
import math
import os
import sys

SCHEDULE_HEADERS = [
    'row',
    'station_m',
    'offset_m',
    'side',
    'sign_code',
    'block_name',
    'rotation_deg',
    'source',
]

DEDUPE_TOL_M = 0.5


def _root_from_project(project_json):
    base = os.path.dirname(os.path.abspath(project_json))
    return os.path.normpath(os.path.join(base, '..'))


def _resolve(root, rel):
    if not rel:
        return ''
    return os.path.normpath(os.path.join(root, rel.replace('/', os.sep)))


def load_catalogue(root):
    path = os.path.join(root, 'config', 'irc67_signage_catalogue.json')
    if not os.path.isfile(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def read_csv_rows(path):
    if not path or not os.path.isfile(path):
        return []
    import codecs
    with codecs.open(path, 'r', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def read_alignment_meta(path):
    if not path or not os.path.isfile(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _f(row, key, default=0.0):
    try:
        v = row.get(key, '')
        if v in (None, ''):
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _sign_row(station_m, sign_code, block_name, side, offset_m, source, row_id):
    return {
        'row': str(row_id),
        'station_m': '%.3f' % station_m,
        'offset_m': '%.3f' % offset_m,
        'side': side,
        'sign_code': sign_code,
        'block_name': block_name,
        'rotation_deg': '',
        'source': source,
    }


def km_post_spacing_m(design, catalogue):
    signage = design.get('signage') or {}
    if design.get('km_post_spacing_m') not in (None, ''):
        return float(design['km_post_spacing_m'])
    road_class = (design.get('road_class') or 'nh_sh').lower()
    by_class = catalogue.get('km_post_spacing_by_road_class') or {}
    if road_class in by_class:
        return float(by_class[road_class])
    if road_class == 'urban':
        return 200.0
    return 500.0


def build_km_posts(total_length_m, start_station, spacing_m, offset_m, catalogue, row_start):
    signs = catalogue.get('signs') or {}
    km = signs.get('KM') or {}
    block = km.get('block_name', 'SGN_KM_POST')
    code = km.get('sign_code', 'KM')
    off = float(km.get('default_offset_m', offset_m))
    rows = []
    rid = row_start
    sta = float(start_station)
    total = float(total_length_m)
    spacing = float(spacing_m)
    if spacing <= 0:
        return rows, rid
    n = 0
    while sta <= total + 1e-6:
        rows.append(_sign_row(sta, code, block, 'L', off, 'auto', rid))
        rid += 1
        n += 1
        sta = float(start_station) + n * spacing
    return rows, rid


def pick_warning_sign(curve, catalogue):
    """W-2 for sharp curves (R < 300 or deflection >= 25 deg), else W-1."""
    signs = catalogue.get('signs') or {}
    w1 = signs.get('W-1') or {}
    w2 = signs.get('W-2') or {}
    r = _f(curve, 'radius_m', 0)
    defl = _f(curve, 'delta_deg', 0)
    r_max = float(w1.get('w2_radius_max_m', 300))
    defl_min = float(w1.get('w2_deflection_min_deg', 25))
    if r > 0 and (r < r_max or defl >= defl_min):
        return w2
    return w1


def build_warnings(curve_rows, advance_m, start_station, offset_m, catalogue, row_start):
    rows = []
    rid = row_start
    for cv in curve_rows:
        r = _f(cv, 'radius_m', 0)
        if r <= 0:
            continue
        tc = cv.get('station_tc', '')
        if tc in (None, ''):
            sta_pi = _f(cv, 'station_m', 0)
            l_arc = _f(cv, 'L_arc', 0)
            tc_val = max(sta_pi - l_arc * 0.5, float(start_station))
        else:
            tc_val = _f(cv, 'station_tc', 0)
        sta = max(tc_val - float(advance_m), float(start_station))
        sign = pick_warning_sign(cv, catalogue)
        code = sign.get('sign_code', 'W-1')
        block = sign.get('block_name', 'SGN_W1_CURVE')
        off = float(sign.get('default_offset_m', offset_m))
        side = (cv.get('side') or 'R').strip().upper()
        if side not in ('L', 'R'):
            side = 'R'
        rows.append(_sign_row(sta, code, block, side, off, 'auto', rid))
        rid += 1
    return rows, rid


def delineator_spacing(radius_m, catalogue):
    sp = catalogue.get('delineator_spacing_m') or {}
    r = float(radius_m)
    if r <= 0:
        return None
    if r < 300:
        return float(sp.get('lt_300', 8))
    if r <= 600:
        return float(sp.get('300_to_600', 15))
    return None


def build_delineators(curve_rows, offset_m, catalogue, row_start):
    signs = catalogue.get('signs') or {}
    deln = signs.get('DELINEATOR') or {}
    block = deln.get('block_name', 'SGN_DELINEATOR')
    code = deln.get('sign_code', 'DELINEATOR')
    off = float(deln.get('default_offset_m', offset_m))
    rows = []
    rid = row_start
    for cv in curve_rows:
        r = _f(cv, 'radius_m', 0)
        spacing = delineator_spacing(r, catalogue)
        if spacing is None:
            continue
        tc = _f(cv, 'station_tc', _f(cv, 'station_m', 0))
        ec = _f(cv, 'station_ec', tc)
        if ec < tc:
            l_arc = _f(cv, 'L_arc', 0)
            ec = tc + l_arc
        sta = tc
        while sta <= ec + 1e-6:
            rows.append(_sign_row(sta, code, block, 'BOTH', off, 'auto', rid))
            rid += 1
            sta += spacing
    return rows, rid


def build_guardrails(fill_rows, threshold_m, offset_m, catalogue, row_start):
    signs = catalogue.get('signs') or {}
    gr = signs.get('GUARDRAIL') or {}
    block = gr.get('block_name', 'SGN_GUARDRAIL_W_BEAM')
    code = gr.get('sign_code', 'GUARDRAIL')
    off = float(gr.get('default_offset_m', offset_m))
    rows = []
    rid = row_start
    for fr in fill_rows:
        depth = _f(fr, 'fill_depth_m', 0)
        if depth <= float(threshold_m):
            continue
        sta = _f(fr, 'station_m', 0)
        rows.append(_sign_row(sta, code, block, 'BOTH', off, 'auto', rid))
        rid += 1
    return rows, rid


def _dedupe_key(row):
    return (
        round(_f(row, 'station_m', 0) / DEDUPE_TOL_M),
        (row.get('block_name') or '').strip(),
        (row.get('side') or '').strip().upper(),
    )


def merge_schedules(manual_rows, auto_rows):
    """Manual rows win on duplicate (station, block, side) within tolerance."""
    out = []
    manual_keys = set()
    for r in manual_rows:
        rr = dict(r)
        if not rr.get('source'):
            rr['source'] = 'manual'
        out.append(rr)
        manual_keys.add(_dedupe_key(rr))
    for r in auto_rows:
        if _dedupe_key(r) in manual_keys:
            continue
        out.append(r)
    for i, r in enumerate(out, start=1):
        r['row'] = str(i)
    return out


def write_schedule(path, rows):
    import codecs
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with codecs.open(path, 'w', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=SCHEDULE_HEADERS, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow({h: r.get(h, '') for h in SCHEDULE_HEADERS})


def run_build(cfg, root, out_path):
    """Entry for M8 IronPython: write merged schedule to out_path."""
    warnings = []
    rows, wlog = build_schedule(cfg, root, warnings)
    write_schedule(out_path, rows)
    return rows, wlog, warnings


def build_schedule(cfg, root, warnings=None):
    """
    Build merged signage schedule. Appends human-readable warnings to list if provided.
    Returns (rows, warnings_list).
    """
    paths = cfg.get('paths') or {}
    design = cfg.get('design') or {}
    signage_cfg = design.get('signage') or {}
    catalogue = load_catalogue(root)

    wlog = warnings if warnings is not None else []
    offset_m = float(signage_cfg.get('default_offset_m', 4.5))
    advance_m = float(signage_cfg.get('warning_advance_m', catalogue.get('warning_advance_m', 60)))
    threshold_m = float(
        signage_cfg.get(
            'guardrail_fill_threshold_m',
            catalogue.get('guardrail_fill_threshold_m', 3),
        )
    )
    start_station = float(design.get('start_station', 0.0))

    curve_path = _resolve(root, paths.get('curve_table', ''))
    meta_path = _resolve(root, paths.get('alignment_meta', ''))
    fill_path = _resolve(root, paths.get('fill_depth_csv', ''))
    manual_path = _resolve(root, paths.get('signage', ''))

    curve_rows = read_csv_rows(curve_path)
    if not curve_rows and paths.get('curve_table'):
        wlog.append('WARN: curve_table missing — skipping warning signs and delineators')
    elif curve_path and not os.path.isfile(curve_path):
        wlog.append('WARN: curve_table not found at %s' % curve_path)

    meta = read_alignment_meta(meta_path)
    total_length = _f(meta, 'total_length_m', 0)
    if total_length <= 0 and curve_rows:
        # fallback: max station_ec or station_m
        for cv in curve_rows:
            total_length = max(total_length, _f(cv, 'station_ec', 0), _f(cv, 'station_m', 0))

    auto_rows = []
    rid = 1

    if total_length > 0:
        spacing = km_post_spacing_m(design, catalogue)
        km_rows, rid = build_km_posts(total_length, start_station, spacing, offset_m, catalogue, rid)
        auto_rows.extend(km_rows)
    elif paths.get('alignment_meta'):
        wlog.append('WARN: alignment_meta missing or total_length_m — skipping km-posts')

    if curve_rows:
        warn_rows, rid = build_warnings(curve_rows, advance_m, start_station, offset_m, catalogue, rid)
        auto_rows.extend(warn_rows)
        del_rows, rid = build_delineators(curve_rows, offset_m, catalogue, rid)
        auto_rows.extend(del_rows)

    fill_rows = read_csv_rows(fill_path)
    if fill_rows:
        gr_rows, rid = build_guardrails(fill_rows, threshold_m, offset_m, catalogue, rid)
        auto_rows.extend(gr_rows)
    elif paths.get('fill_depth_csv'):
        wlog.append('WARN: fill_depth_csv missing — skipping guardrail auto rows')

    merge_manual = signage_cfg.get('merge_manual', True)
    if merge_manual and manual_path and os.path.isfile(manual_path):
        manual_rows = read_csv_rows(manual_path)
        for r in manual_rows:
            if not r.get('source'):
                r['source'] = 'manual'
        rows = merge_schedules(manual_rows, auto_rows)
    else:
        rows = auto_rows
        for i, r in enumerate(rows, start=1):
            r['row'] = str(i)

    return rows, wlog


def main(argv=None):
    p = argparse.ArgumentParser(description='Build M5 signage schedule CSV')
    p.add_argument('--project', required=True, help='Path to config/project.json')
    p.add_argument('--output', help='Override output CSV path')
    args = p.parse_args(argv)

    if not os.path.isfile(args.project):
        print('ERROR: project not found: %s' % args.project, file=sys.stderr)
        return 1

    with open(args.project, 'r', encoding='utf-8') as f:
        cfg = json.load(f)

    root = _root_from_project(args.project)
    paths = cfg.get('paths') or {}
    out_rel = args.output or paths.get('signage_generated', 'out/signage_generated.csv')
    out_path = out_rel if os.path.isabs(out_rel) else _resolve(root, out_rel)

    warnings = []
    rows, wlog = build_schedule(cfg, root, warnings)
    for w in wlog:
        print(w)

    write_schedule(out_path, rows)
    counts = {}
    for r in rows:
        sc = r.get('sign_code') or '?'
        counts[sc] = counts.get(sc, 0) + 1
    print('OK: wrote %d row(s) to %s' % (len(rows), out_path))
    for sc, n in sorted(counts.items()):
        print('  %s: %d' % (sc, n))
    return 0


if __name__ == '__main__':
    sys.exit(main())
