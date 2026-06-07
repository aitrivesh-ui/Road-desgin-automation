# -*- coding: utf-8 -*-
"""
IRC:38-1988 horizontal alignment helpers (no Civil 3D imports).
Used by M1 and Python 3 unit tests in tools/.
"""
from __future__ import absolute_import

import math

# Handbook design-speed table (ROADGEN v2 / IRC:38).
SPEED_TABLE = {
    40: {'f': 0.17, 'r_min_tab': 60, 'ls_min': 15, 'ssd': 45, 'osd': None},
    60: {'f': 0.15, 'r_min_tab': 130, 'ls_min': 25, 'ssd': 90, 'osd': 270},
    80: {'f': 0.14, 'r_min_tab': 230, 'ls_min': 35, 'ssd': 120, 'osd': 370},
    100: {'f': 0.12, 'r_min_tab': 360, 'ls_min': 50, 'ssd': 150, 'osd': 470},
    120: {'f': 0.10, 'r_min_tab': 720, 'ls_min': 60, 'ssd': 180, 'osd': None},
}

SPEED_BUCKETS = sorted(SPEED_TABLE.keys())
DEFAULT_E_MAX_PCT = 7.0
DEFAULT_C_RATE = 0.5
DEFAULT_CRITICAL_FACTOR = 0.5


def nearest_speed_bucket(vd_kph):
    vd = float(vd_kph or 80)
    return min(SPEED_BUCKETS, key=lambda k: abs(k - vd))


def friction_coefficient(vd_kph, friction_override=None):
    if friction_override is not None and friction_override != '':
        return float(friction_override)
    return float(SPEED_TABLE[nearest_speed_bucket(vd_kph)]['f'])


def superelevation_decimal(superelevation_pct=None):
    if superelevation_pct is None or superelevation_pct == '':
        return DEFAULT_E_MAX_PCT / 100.0
    return float(superelevation_pct) / 100.0


def r_min_formula(vd_kph, superelevation_pct=None, friction_override=None):
    """R_min = Vd^2 / (127 * (e + f))."""
    vd = float(vd_kph or 80)
    e = superelevation_decimal(superelevation_pct)
    f = friction_coefficient(vd, friction_override)
    denom = 127.0 * (e + f)
    if denom <= 0:
        return 0.0
    return (vd * vd) / denom


def spiral_length(vd_kph, radius_m, rate_c=None):
    """Ls = 0.036 * Vd^3 / (R * C)."""
    r = float(radius_m or 0)
    if r <= 0:
        return 0.0
    c = float(rate_c if rate_c is not None else DEFAULT_C_RATE)
    if c <= 0:
        c = DEFAULT_C_RATE
    vd = float(vd_kph or 80)
    return 0.036 * (vd ** 3) / (r * c)


def ls_min_table(vd_kph):
    return float(SPEED_TABLE[nearest_speed_bucket(vd_kph)]['ls_min'])


def osd_table(vd_kph):
    bucket = nearest_speed_bucket(vd_kph)
    osd = SPEED_TABLE[bucket].get('osd')
    return float(osd) if osd is not None else None


def ssd_table(vd_kph):
    return float(SPEED_TABLE[nearest_speed_bucket(vd_kph)]['ssd'])


def validate_radius(radius_m, vd_kph, superelevation_pct=None, friction_override=None, critical_factor=None):
    """
    Returns (severity, code, r_min, critical_r) where severity is None if OK.
    """
    r = float(radius_m or 0)
    if r <= 0:
        return None, None, 0.0, 0.0
    r_min = r_min_formula(vd_kph, superelevation_pct, friction_override)
    cf = float(critical_factor if critical_factor is not None else DEFAULT_CRITICAL_FACTOR)
    critical_r = r_min * cf
    if r < critical_r:
        return 'ERROR', 'IRC38_R_CRITICAL', r_min, critical_r
    if r < r_min:
        return 'WARN', 'IRC38_R_MIN', r_min, critical_r
    return None, None, r_min, critical_r


def lateral_clearance_m(radius_m, vd_kph):
    """m = R * (1 - cos(SSD / 2R))."""
    r = float(radius_m or 0)
    if r <= 0:
        return 0.0
    ssd = ssd_table(vd_kph)
    arg = ssd / (2.0 * r)
    return r * (1.0 - math.cos(arg))
