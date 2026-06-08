# -*- coding: utf-8 -*-
"""IRC:37-2018 pavement catalogue lookup (IronPython 2.7 / CPython 3)."""
import json
import os

DEFAULT_CATALOGUE = 'config/irc37_catalogue.json'
LAYER_ORDER = ('GSB', 'WMM', 'DBM', 'BC')
MM_PER_M = 1000.0

_CATALOGUE_CACHE = {}


def _package_root_from_here():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, '..'))


def load_catalogue(path=None):
    root = _package_root_from_here()
    rel = path or DEFAULT_CATALOGUE
    full = rel if os.path.isabs(rel) else os.path.join(root, rel)
    full = os.path.normpath(full)
    if full not in _CATALOGUE_CACHE:
        with open(full, 'r', encoding='utf-8') as f:
            _CATALOGUE_CACHE[full] = json.load(f)
    return _CATALOGUE_CACHE[full]


def snap_bin(val, bins):
    """Snap value to nearest catalogue bin."""
    v = float(val)
    bl = [float(b) for b in bins]
    return min(bl, key=lambda b: abs(b - v))


def _table_key(msa_bin, cbr_bin):
    return '%d|%d' % (int(msa_bin), int(cbr_bin))


def _parse_table_key(key):
    parts = str(key).split('|')
    return int(parts[0]), int(parts[1])


def _lookup_table(cat, msa_bin, cbr_bin):
    table = cat.get('table') or {}
    k = _table_key(msa_bin, cbr_bin)
    if k in table:
        return dict(table[k]), k, False
    if not table:
        return {}, k, True
    best = min(
        table.keys(),
        key=lambda tk: abs(_parse_table_key(tk)[0] - msa_bin) + abs(_parse_table_key(tk)[1] - cbr_bin),
    )
    return dict(table[best]), best, True


def _lookup_entries(cat, cbr, msa, climate):
    climate = (climate or 'moderate').strip().lower()
    for entry in cat.get('entries', []):
        if cbr < float(entry['cbr_min']) or cbr > float(entry['cbr_max']):
            continue
        if msa < float(entry['msa_min']) or msa > float(entry['msa_max']):
            continue
        if entry.get('climate', 'moderate').lower() != climate:
            continue
        return dict(entry.get('thickness_mm', {})), None, False
    return {}, None, True


def _layers_to_m(layers_mm):
    out = {}
    for name, mm in layers_mm.items():
        out[name] = float(mm) / MM_PER_M
    return out


def _layers_list(layers_mm):
    rows = []
    for name in LAYER_ORDER:
        if name in layers_mm:
            rows.append({'name': name, 'thickness_mm': int(layers_mm[name])})
    for name in sorted(layers_mm.keys()):
        if name not in LAYER_ORDER:
            rows.append({'name': name, 'thickness_mm': int(layers_mm[name])})
    return rows


def irc37_design(cbr_pct, msa, climate='moderate', catalogue_path=None):
    """
    Lookup IRC:37-2018 Table 1 pavement composition.
    Returns contract dict with layers_mm, layers_m, layers[], snapped, inputs.
    """
    cat = load_catalogue(catalogue_path)
    cbr_in = float(cbr_pct)
    msa_in = float(msa)
    climate_in = (climate or 'moderate').strip().lower()

    bins = cat.get('bins') or {}
    msa_bins = bins.get('msa') or [2, 5, 10, 20, 30, 50, 100, 150]
    cbr_bins = bins.get('cbr') or [3, 5, 7, 8, 10]

    layers_mm = {}
    table_key = None
    fallback = False

    if climate_in != 'moderate' and cat.get('entries'):
        layers_mm, table_key, fallback = _lookup_entries(cat, cbr_in, msa_in, climate_in)
        if layers_mm:
            snapped = {'msa': msa_in, 'cbr_pct': cbr_in, 'key': table_key}
            meta = cat.get('meta') or {}
            version = cat.get('version') or meta.get('standard') or 'IRC:37-2018'
            return {
                'cbr_pct': cbr_in,
                'msa': msa_in,
                'climate': climate_in,
                'layers': _layers_list(layers_mm),
                'layers_mm': layers_mm,
                'layers_m': _layers_to_m(layers_mm),
                'snapped': snapped,
                'inputs': {'cbr_pct': cbr_in, 'msa': msa_in, 'climate': climate_in},
                'catalogue_version': version,
                'fallback': fallback,
                'empty': False,
            }

    if cat.get('table'):
        msa_b = snap_bin(msa_in, msa_bins)
        cbr_b = snap_bin(cbr_in, cbr_bins)
        layers_mm, table_key, fallback = _lookup_table(cat, msa_b, cbr_b)
        snapped = {'msa': msa_b, 'cbr_pct': cbr_b, 'key': table_key}
    else:
        msa_b = msa_in
        cbr_b = cbr_in
        snapped = {'msa': msa_b, 'cbr_pct': cbr_b, 'key': None}

    if not layers_mm and cat.get('entries'):
        layers_mm, table_key, fallback = _lookup_entries(cat, cbr_in, msa_in, climate_in)
        snapped = {'msa': msa_in, 'cbr_pct': cbr_in, 'key': table_key}

    meta = cat.get('meta') or {}
    version = cat.get('version') or meta.get('standard') or 'IRC:37-2018'

    if not layers_mm:
        return {
            'cbr_pct': cbr_in,
            'msa': msa_in,
            'climate': climate_in,
            'layers': [],
            'layers_mm': {},
            'layers_m': {},
            'snapped': snapped,
            'inputs': {'cbr_pct': cbr_in, 'msa': msa_in, 'climate': climate_in},
            'catalogue_version': version,
            'fallback': True,
            'empty': True,
        }

    return {
        'cbr_pct': cbr_in,
        'msa': msa_in,
        'climate': climate_in,
        'layers': _layers_list(layers_mm),
        'layers_mm': layers_mm,
        'layers_m': _layers_to_m(layers_mm),
        'snapped': snapped,
        'inputs': {'cbr_pct': cbr_in, 'msa': msa_in, 'climate': climate_in},
        'catalogue_version': version,
        'fallback': fallback,
        'empty': False,
    }


def irc37_design_legacy(cbr_pct, msa, climate='moderate', catalogue_path=None):
    """Backward-compatible: return layers_mm dict only."""
    result = irc37_design(cbr_pct, msa, climate, catalogue_path)
    return dict(result.get('layers_mm') or {})


def format_cache_json(design_result):
    """Normalize for irc37_cache file (PIPELINE_DATA_CONTRACT)."""
    if not design_result:
        return {}
    if design_result.get('layers') is not None and design_result.get('cbr_pct') is not None:
        return design_result
    layers_mm = design_result if isinstance(design_result, dict) else {}
    return {
        'cbr_pct': None,
        'msa': None,
        'climate': 'moderate',
        'layers': _layers_list(layers_mm),
        'layers_mm': layers_mm,
        'layers_m': _layers_to_m(layers_mm),
    }
