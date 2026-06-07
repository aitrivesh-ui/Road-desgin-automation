# -*- coding: utf-8 -*-
"""
DPR sheet manifest — NHAI PKG drawing numbers and sheet counts (stdlib only).

Usage:
  python dpr_sheet_core.py --project config/project.json
"""
from __future__ import absolute_import, print_function

import argparse
import codecs
import csv
import json
import math
import os
import sys

SHEET_CODES = ('GEN', 'PP', 'XS', 'TCS', 'PVT', 'DRN', 'SGN')

DEFAULT_DPR = {
    'package_id': 'PKG-01',
    'revision': 'REV-A',
    'pp_sheet_length_m': 500,
    'xs_per_sheet': 20,
    'drn_sheet_length_m': 2000,
    'sgn_sheet_length_m': 2000,
    'scales': {
        'gen': 50000,
        'pp_h': 2000,
        'pp_v': 500,
        'xs': 200,
        'tcs': 100,
        'drn': 2000,
        'sgn': 2000,
    },
    'title_block_name': 'MORTH_A1',
    'attribute_map': {
        'drg_no': 'DRG_NO',
        'rev': 'REV',
        'ch_from': 'CHAINAGE_FROM',
        'ch_to': 'CHAINAGE_TO',
    },
}


def format_drg_no(package_id, sheet_code, serial):
    """NHAI convention: PKG-01/PP/001."""
    pid = (package_id or 'PKG-01').strip()
    code = (sheet_code or 'PP').strip().upper()
    return '%s/%s/%03d' % (pid, code, int(serial))


def _sheet_id(code, serial):
    """Handbook sheet id e.g. PP-001, GEN-01."""
    code = code.upper()
    if code == 'GEN':
        return '%s-%02d' % (code, serial)
    return '%s-%03d' % (code, serial)


def _scale_str(scales, code):
    scales = scales or {}
    if code == 'PP':
        h = scales.get('pp_h', 2000)
        v = scales.get('pp_v', 500)
        return '1:%d/1:%d' % (int(h), int(v))
    key = {'GEN': 'gen', 'XS': 'xs', 'TCS': 'tcs', 'DRN': 'drn', 'SGN': 'sgn'}.get(code)
    if code == 'PVT':
        return 'NTS'
    if key and scales.get(key):
        return '1:%d' % int(scales[key])
    return ''


def _ceil_div(n, d):
    if d <= 0:
        return 1
    return int(math.ceil(float(n) / float(d)))


def read_alignment_meta(path):
    if not path or not os.path.isfile(path):
        return {}
    with codecs.open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def read_mass_haul_meta(path):
    if not path or not os.path.isfile(path):
        return {}
    with codecs.open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def count_mass_haul_stations(csv_path):
    if not csv_path or not os.path.isfile(csv_path):
        return 0
    with codecs.open(csv_path, 'r', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    return len(rows)


def resolve_total_length_m(alignment_meta_path, mass_haul_csv_path=None):
    """Length from alignment_meta, else last station in mass_haul CSV."""
    meta = read_alignment_meta(alignment_meta_path)
    if meta.get('total_length_m') is not None:
        return float(meta['total_length_m'])
    if mass_haul_csv_path and os.path.isfile(mass_haul_csv_path):
        with codecs.open(mass_haul_csv_path, 'r', encoding='utf-8-sig') as f:
            rows = list(csv.DictReader(f))
        if rows:
            try:
                return float(rows[-1].get('station_m', 0) or 0)
            except (TypeError, ValueError):
                pass
    return 0.0


def resolve_n_stations(mass_haul_meta_path, mass_haul_csv_path, total_length_m, interval_m):
    """Station count for XS sheets — prefer M4 sample_count."""
    mh_meta = read_mass_haul_meta(mass_haul_meta_path)
    sc = mh_meta.get('sample_count')
    if sc is not None:
        try:
            n = int(sc)
            if n > 0:
                return n
        except (TypeError, ValueError):
            pass
    n_csv = count_mass_haul_stations(mass_haul_csv_path)
    if n_csv > 0:
        return n_csv
    if total_length_m > 0 and interval_m > 0:
        return int(math.floor(total_length_m / interval_m)) + 1
    return 0


def load_irc37_layers(irc37_path):
    if not irc37_path or not os.path.isfile(irc37_path):
        return None
    with codecs.open(irc37_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    layers = data.get('layers') or data.get('layers_mm')
    if layers:
        return layers
    return data if isinstance(data, dict) else None


def build_sheet_manifest(
    dpr_cfg,
    total_length_m,
    n_stations,
    start_station=0.0,
    irc37_layers=None,
):
    """
    Build full DPR sheet list per handbook M7.
    Returns dict with sheets[] and summary counts.
    """
    dpr = dict(DEFAULT_DPR)
    dpr.update(dpr_cfg or {})

    package_id = dpr.get('package_id', 'PKG-01')
    revision = dpr.get('revision', 'REV-A')
    pp_len = float(dpr.get('pp_sheet_length_m', 500) or 500)
    xs_per = int(dpr.get('xs_per_sheet', 20) or 20)
    drn_len = float(dpr.get('drn_sheet_length_m', 2000) or 2000)
    sgn_len = float(dpr.get('sgn_sheet_length_m', 2000) or 2000)
    scales = dpr.get('scales') or DEFAULT_DPR['scales']

    L = max(0.0, float(total_length_m or 0))
    start = float(start_station or 0)
    sheets = []

    def add(code, serial, extra=None):
        row = {
            'code': code,
            'serial': serial,
            'sheet_id': _sheet_id(code, serial),
            'drg_no': format_drg_no(package_id, code, serial),
            'scale': _scale_str(scales, code),
            'revision': revision,
            'title_block_applied': False,
        }
        if extra:
            row.update(extra)
        sheets.append(row)

    # GEN-01
    add('GEN', 1)

    # PP-001 … n
    pp_count = max(1, _ceil_div(L, pp_len)) if L > 0 else 1
    for i in range(1, pp_count + 1):
        ch_from = start + (i - 1) * pp_len
        ch_to = min(start + i * pp_len, start + L) if L > 0 else start + i * pp_len
        add('PP', i, {'ch_from': round(ch_from, 3), 'ch_to': round(ch_to, 3)})

    # XS-001 … n
    xs_count = max(1, _ceil_div(n_stations, xs_per)) if n_stations > 0 else 1
    for i in range(1, xs_count + 1):
        add('XS', i)

    add('TCS', 1)
    pvt_extra = {}
    if irc37_layers is not None:
        pvt_extra['pavement_layers'] = irc37_layers
    add('PVT', 1, pvt_extra)

    drn_count = max(1, _ceil_div(L, drn_len)) if L > 0 else 1
    for i in range(1, drn_count + 1):
        add('DRN', i)

    sgn_count = max(1, _ceil_div(L, sgn_len)) if L > 0 else 1
    for i in range(1, sgn_count + 1):
        add('SGN', i)

    by_code = {}
    for s in sheets:
        by_code[s['code']] = by_code.get(s['code'], 0) + 1

    return {
        'contract_version': 1,
        'package_id': package_id,
        'revision': revision,
        'total_length_m': round(L, 3),
        'n_stations': int(n_stations),
        'start_station': round(start, 3),
        'sheet_counts': by_code,
        'xs_validation': {
            'n_stations': int(n_stations),
            'xs_per_sheet': xs_per,
            'xs_sheet_count': by_code.get('XS', 0),
            'capacity_stations': by_code.get('XS', 0) * xs_per,
        },
        'sheets': sheets,
    }


def write_manifest(manifest, out_path):
    d = os.path.dirname(out_path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with codecs.open(out_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write('\n')
    return out_path


def validate_xs_station_count(manifest, log_fn=None):
    """WARN when cross-section station count is missing or inconsistent."""
    xv = manifest.get('xs_validation') or {}
    n = xv.get('n_stations', 0)
    L = manifest.get('total_length_m', 0) or 0
    if L > 0 and n <= 0:
        msg = (
            'No sample-line count for XS sheets (run M4 or provide mass_haul_meta). '
            'XS sheet count uses minimum of 1.'
        )
        if log_fn:
            log_fn('WARN', 'XS_STATIONS_MISSING', msg)
        return msg
    return None


def build_from_project(project_json, root=None):
    """Load project.json and build manifest dict."""
    with codecs.open(project_json, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    if root is None:
        base = os.path.dirname(os.path.abspath(project_json))
        root = os.path.normpath(os.path.join(base, '..'))

    def resolve(rel):
        if not rel:
            return ''
        return os.path.normpath(os.path.join(root, rel.replace('/', os.sep)))

    paths = cfg.get('paths', {})
    design = cfg.get('design', {})
    dpr = cfg.get('dpr', {})

    meta_path = resolve(paths.get('alignment_meta', ''))
    mh_csv = resolve(paths.get('mass_haul_csv', ''))
    mh_meta = resolve(paths.get('mass_haul_meta', ''))
    irc_path = resolve(paths.get('irc37_cache') or paths.get('pavement_design', ''))

    L = resolve_total_length_m(meta_path, mh_csv)
    interval = float(design.get('volume_sample_interval_m', 20) or 20)
    n_sta = resolve_n_stations(mh_meta, mh_csv, L, interval)
    start = float(design.get('start_station', 0) or 0)
    layers = load_irc37_layers(irc_path)

    manifest = build_sheet_manifest(dpr, L, n_sta, start, layers)
    return manifest, cfg, root


def main(argv=None):
    ap = argparse.ArgumentParser(description='Build DPR sheet manifest from project.json')
    ap.add_argument('--project', required=True, help='Path to config/project.json')
    ap.add_argument('--out', default='', help='Override manifest output path')
    args = ap.parse_args(argv)

    manifest, cfg, root = build_from_project(args.project)
    paths = cfg.get('paths', {})
    out_rel = args.out or paths.get('dpr_sheet_manifest', 'out/dpr_sheet_manifest.json')
    out_path = args.out if args.out and os.path.isabs(args.out) else os.path.join(
        root, out_rel.replace('/', os.sep)
    )

    warn = validate_xs_station_count(manifest)
    write_manifest(manifest, out_path)

    counts = manifest.get('sheet_counts', {})
    print('Wrote %s' % out_path)
    print('  length_m=%.1f  n_stations=%d' % (
        manifest.get('total_length_m', 0),
        manifest.get('n_stations', 0),
    ))
    print('  sheets: %s' % ', '.join('%s=%d' % (k, v) for k, v in sorted(counts.items())))
    if warn:
        print('WARN: %s' % warn)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
