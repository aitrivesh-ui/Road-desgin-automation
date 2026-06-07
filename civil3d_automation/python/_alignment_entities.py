# -*- coding: utf-8 -*-
"""
Alignment entity builders for M1 — polyline (default) and opt-in PI fixed curves (SCS).

IronPython 2.7 / Civil 3D. No imports from Civil in unit tests — pure helpers only at top.
"""
from __future__ import absolute_import

import math


def geometry_mode(design):
    """polyline | scs — default polyline for backward compatibility."""
    aln = (design or {}).get('alignment') or {}
    mode = str(aln.get('geometry_mode', 'polyline') or 'polyline').strip().lower()
    if mode not in ('polyline', 'scs'):
        return 'polyline'
    return mode


def scs_fallback_enabled(design):
    aln = (design or {}).get('alignment') or {}
    return aln.get('scs_fallback', True) is not False


def pis_have_curves(pis):
    for r in pis:
        try:
            if float(r.get('radius_m', 0) or 0) > 0:
                return True
        except Exception:
            pass
    return False


def interior_curve_pis(pis):
    """Indices of interior PIs with radius_m > 0."""
    out = []
    for i in range(1, len(pis) - 1):
        try:
            if float(pis[i].get('radius_m', 0) or 0) > 0:
                out.append(i)
        except Exception:
            pass
    return out


def populate_polyline(entities, points):
    """Add fixed lines between consecutive Point3d."""
    n = 0
    for i in range(len(points) - 1):
        entities.AddFixedLine(points[i], points[i + 1])
        n += 1
    return n


def _try_add_fixed_curve(entities, p_start, p_end, p_pi, radius_m):
    """Try Civil 3D signatures documented across 2022–2025 builds."""
    r = float(radius_m)
    attempts = []

    def _call(fn, args):
        fn(*args)
        return True

    if hasattr(entities, 'AddFixedCurve'):
        attempts.append(lambda: _call(entities.AddFixedCurve, (p_start, p_end, p_pi, r)))
        attempts.append(lambda: _call(entities.AddFixedCurve, (p_start, p_pi, p_end, r)))
    if hasattr(entities, 'AddFreeCurve'):
        attempts.append(lambda: _call(entities.AddFreeCurve, (p_start, p_end, p_pi, r)))

    last_err = None
    for fn in attempts:
        try:
            if fn():
                return True, 'AddFixedCurve'
        except Exception as ex:
            last_err = ex
    return False, str(last_err) if last_err else 'no_curve_api'


def populate_scs(entities, points, pis, log, log_add):
    """
    Build alignment with fixed curves at interior PIs (radius from CSV).
    Spirals in CSV are not modeled as separate entities yet.
    Returns (segment_count, used_scs_bool).
    """
    n_pts = len(points)
    if n_pts < 2:
        return 0, False

    seg_count = 0
    used_curve = False
    i = 0
    while i < n_pts - 1:
        if i + 2 < n_pts:
            try:
                rad = float(pis[i + 1].get('radius_m', 0) or 0)
            except Exception:
                rad = 0.0
            if rad > 0:
                ok, api = _try_add_fixed_curve(
                    entities, points[i], points[i + 2], points[i + 1], rad
                )
                if ok:
                    seg_count += 1
                    used_curve = True
                    spi = float(pis[i + 1].get('spiral_in_m', 0) or 0)
                    spo = float(pis[i + 1].get('spiral_out_m', 0) or 0)
                    if spi > 0 or spo > 0:
                        log_add(
                            log,
                            'INFO',
                            'SCS_SPIRAL_CSV',
                            'PI %s spiral lengths in CSV not built as entities yet (curve only).'
                            % pis[i + 1].get('pi_id', '?'),
                        )
                    i += 2
                    continue
                log_add(
                    log,
                    'WARN',
                    'SCS_CURVE_FAIL',
                    'PI %s AddFixedCurve failed (%s).'
                    % (pis[i + 1].get('pi_id', '?'), api),
                )
        entities.AddFixedLine(points[i], points[i + 1])
        seg_count += 1
        i += 1
    return seg_count, used_curve


def populate_entities(entities, pis, points, design, log, log_add):
    """
    Populate AlignmentEntityCollection. Returns (segment_count, geometry_mode_used).
    """
    mode = geometry_mode(design)
    if mode == 'scs' and pis_have_curves(pis):
        seg_count, used = populate_scs(entities, points, pis, log, log_add)
        if used:
            log_add(log, 'INFO', 'M1_SCS', 'Built alignment with fixed curves at PI(s).')
            return seg_count, 'scs'
        if scs_fallback_enabled(design):
            log_add(
                log,
                'WARN',
                'SCS_FALLBACK',
                'SCS curve API unavailable — falling back to fixed lines.',
            )
            return populate_polyline(entities, points), 'polyline'
        log_add(log, 'ERROR', 'SCS_REQUIRED', 'geometry_mode=scs but no curve API succeeded.')
        return 0, 'scs'
    return populate_polyline(entities, points), 'polyline'
