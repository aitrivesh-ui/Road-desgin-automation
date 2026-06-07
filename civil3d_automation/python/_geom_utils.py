# -*- coding: utf-8 -*-
"""Geometry helpers — 0.5 m curve sub-sampling (IronPython 2.7)."""
import math

DEFAULT_INTERVAL_M = 0.5
TIGHT_CURVE_RADIUS_M = 200.0


def get_dense_points(align, start_sta, end_sta, interval=DEFAULT_INTERVAL_M):
    """
    Sample alignment between start_sta and end_sta at fixed chainage interval.
    align: Civil Alignment with PointLocation(station, offset).
    Returns list of (station, point3d).
    """
    interval = float(interval or DEFAULT_INTERVAL_M)
    if interval <= 0:
        interval = DEFAULT_INTERVAL_M
    s0 = float(start_sta)
    s1 = float(end_sta)
    if s1 < s0:
        s0, s1 = s1, s0
    pts = []
    sta = s0
    while sta <= s1 + 1e-6:
        try:
            p = align.PointLocation(sta, 0.0)
            pts.append((sta, p))
        except Exception:
            pass
        sta += interval
    if pts and abs(pts[-1][0] - s1) > 1e-3:
        try:
            p = align.PointLocation(s1, 0.0)
            pts.append((s1, p))
        except Exception:
            pass
    return pts


def polyline_length_from_points(point_pairs):
    total = 0.0
    for i in range(1, len(point_pairs)):
        p0 = point_pairs[i - 1][1]
        p1 = point_pairs[i][1]
        total += math.hypot(p1.X - p0.X, p1.Y - p0.Y)
    return total


def estimate_radius_from_three_points(p0, p1, p2):
    """Approximate curve radius from three XY points (m). Returns None if collinear."""
    x1, y1 = p0.X, p0.Y
    x2, y2 = p1.X, p1.Y
    x3, y3 = p2.X, p2.Y
    d = 2.0 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-9:
        return None
    ux = ((x1 * x1 + y1 * y1) * (y2 - y3) + (x2 * x2 + y2 * y2) * (y3 - y1) + (x3 * x3 + y3 * y3) * (y1 - y2)) / d
    uy = ((x1 * x1 + y1 * y1) * (x3 - x2) + (x2 * x2 + y2 * y2) * (x1 - x3) + (x3 * x3 + y3 * y3) * (x2 - x1)) / d
    r = math.hypot(x1 - ux, y1 - uy)
    return r if r > 1e-6 else None
