# -*- coding: utf-8 -*-
"""
Road Automation — DGPS survey file importer (Python 3 + tkinter).

Reads survey point files and generates all road-design input CSVs.

Supported formats (auto-detected):
  Generic CSV/TXT  — any delimiter, auto column detection
  Trimble DC       — JB/MP/OP record format
  Trimble CSV      — Access quoted-header export
  Leica GSI        — 8-word and 16-word fixed format
  LandXML          — XML exchange format

Generated files:
  alignment_pi.csv      PI points detected from centreline bearing changes
  profile_pvis.csv      PVI points detected from grade changes
  section_widths.csv    Corridor regions from cross-section shots
  signage_schedule.csv  Sign locations from coded survey points

Usage:
  python survey_to_csv.py              GUI wizard
  python survey_to_csv.py --cli FILE   headless, all defaults
"""
from __future__ import annotations

import csv as _csv
import io
import math
import os
import re
import sys
import xml.etree.ElementTree as ET
from typing import Any, NamedTuple

# ---------------------------------------------------------------------------
# Data type
# ---------------------------------------------------------------------------

class SurveyPoint(NamedTuple):
    id: str
    easting: float
    northing: float
    elevation: float
    code: str


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EARTH_R = 6_371_000.0

CSV_HEADERS: dict[str, list[str]] = {
    "alignment_pi":     ["pi_id", "easting", "northing", "radius_m",
                          "spiral_in_m", "spiral_out_m", "design_speed_kph"],
    "profile_pvis":     ["station_m", "elevation_m", "k_crest", "k_sag",
                          "curve_length_m"],
    "section_widths":   ["region_id", "start_sta", "end_sta", "lane_width_m",
                          "shoulder_l_m", "shoulder_r_m", "target_l", "target_r"],
    "signage_schedule": ["row", "station_m", "offset_m", "side", "sign_code",
                          "block_name", "rotation_deg"],
}

DEFAULT_CODES = {
    "cl":    "CL,AL,RD,ROAD,CENTRE,CENTER,TCL",
    "left":  "LS,LC,LEFT,LB,LK",
    "right": "RS,RC,RIGHT,RB,RK",
    "sign":  "SGN,SIGN,SIG,FS",
}


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

def _is_geographic(pts: list[SurveyPoint]) -> bool:
    if not pts:
        return False
    return -180.0 <= pts[0].easting <= 180.0 and -90.0 <= pts[0].northing <= 90.0


def _project_geographic(pts: list[SurveyPoint]) -> list[SurveyPoint]:
    """Equirectangular projection centred on first point. <1 m error for <50 km roads."""
    lon0 = math.radians(pts[0].easting)
    lat0 = math.radians(pts[0].northing)
    out = []
    for p in pts:
        lon = math.radians(p.easting)
        lat = math.radians(p.northing)
        e = _EARTH_R * math.cos(lat0) * (lon - lon0)
        n = _EARTH_R * (lat - lat0)
        out.append(SurveyPoint(p.id, round(e, 3), round(n, 3), p.elevation, p.code))
    return out


# ---------------------------------------------------------------------------
# File readers
# ---------------------------------------------------------------------------

def _sniff_delimiter(text: str) -> str:
    head = text[:2000]
    counts = {d: head.count(d) for d in (',', ';', '\t', '|')}
    return max(counts, key=counts.get)


def _map_csv_columns(headers: list[str]) -> dict[str, int]:
    kw = {
        'id':   re.compile(r'(point|pt|name|^id$|^no$|num)', re.I),
        'e':    re.compile(r'(easting|east|^x$|^e$)', re.I),
        'n':    re.compile(r'(northing|north|^y$|^n$)', re.I),
        'z':    re.compile(r'(elev|height|^z$|^h$|alt|rl)', re.I),
        'code': re.compile(r'(code|desc|feature|attrib)', re.I),
    }
    mapping: dict[str, int] = {}
    for i, h in enumerate(headers):
        h2 = h.strip().strip('"')
        for role, pat in kw.items():
            if role not in mapping and pat.search(h2):
                mapping[role] = i
    # Positional fallback: assume Pt, N, E, Z, Code
    if 'n' not in mapping and 'e' not in mapping and len(headers) >= 3:
        mapping.setdefault('id', 0)
        mapping.setdefault('n',  1)
        mapping.setdefault('e',  2)
        mapping.setdefault('z',  3)
        if len(headers) >= 5:
            mapping.setdefault('code', 4)
    return mapping


def _is_numeric(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def read_generic_csv(text: str,
                     col_map: dict[str, int] | None = None) -> list[SurveyPoint]:
    text = text.lstrip('﻿')
    delim = _sniff_delimiter(text)
    rows = [r for r in _csv.reader(io.StringIO(text), delimiter=delim)
            if r and not r[0].lstrip().startswith('#')]
    if not rows:
        return []
    start = 0
    if rows and not _is_numeric(rows[0][0].strip().strip('"')):
        if col_map is None:
            col_map = _map_csv_columns(rows[0])
        start = 1
    if col_map is None:
        col_map = {'id': 0, 'n': 1, 'e': 2, 'z': 3}
        if len(rows[0]) >= 5:
            col_map['code'] = 4

    def _get(row: list[str], key: str, default: str = '') -> str:
        idx = col_map.get(key)
        if idx is None or idx >= len(row):
            return default
        return row[idx].strip().strip('"')

    pts: list[SurveyPoint] = []
    for i, row in enumerate(rows[start:], start=start):
        if not any(c.strip() for c in row):
            continue
        try:
            pts.append(SurveyPoint(
                _get(row, 'id', str(i)),
                float(_get(row, 'e', '0') or '0'),
                float(_get(row, 'n', '0') or '0'),
                float(_get(row, 'z', '0') or '0'),
                _get(row, 'code', '').upper(),
            ))
        except ValueError:
            continue
    return pts


def _parse_gsi_word(line: str, wid: str) -> float:
    m = re.search(r'\b' + wid + r'([.0-9]{4,6})([+\-])(\d+)', line)
    if not m:
        return 0.0
    fmt, sign_ch, digits = m.group(1), m.group(2), m.group(3)
    sign = 1.0 if sign_ch == '+' else -1.0
    dp = len(fmt.split('.')[1].rstrip('0')) if '.' in fmt else 0
    return sign * float(digits.lstrip('0') or '0') / (10 ** dp)


def read_leica_gsi(text: str) -> list[SurveyPoint]:
    pts: list[SurveyPoint] = []
    for line in text.splitlines():
        line = line.strip().lstrip('*')
        if not re.search(r'\d{2}[.0-9]{4}[+\-]\d', line):
            continue
        pt_m   = re.search(r'11[.0-9]{4,6}\+(\d+)', line)
        code_m = re.search(r'71[.0-9]{4,6}\+(\S+)', line)
        pt_id  = (pt_m.group(1).lstrip('0') or '0') if pt_m else str(len(pts) + 1)
        code   = code_m.group(1).strip().upper() if code_m else ''
        try:
            pts.append(SurveyPoint(
                pt_id,
                _parse_gsi_word(line, '81'),
                _parse_gsi_word(line, '82'),
                _parse_gsi_word(line, '83'),
                code,
            ))
        except (ValueError, ZeroDivisionError):
            continue
    return pts


def read_trimble_dc(text: str) -> list[SurveyPoint]:
    pts: list[SurveyPoint] = []
    # Modern MP record: MP,NM<name>,LA<lat>,LN<lon>,EL<elev>,--<code>
    for m in re.finditer(
        r'MP,NM([^,\r\n]+),LA([^,]+),LN([^,]+),EL([^,\r\n]+)(?:,--([^\r\n]*))?',
        text, re.I,
    ):
        try:
            pts.append(SurveyPoint(
                m.group(1).strip(),
                float(m.group(3)),          # LN = longitude = easting-like
                float(m.group(2)),          # LA = latitude  = northing-like
                float(m.group(4)),
                (m.group(5) or '').strip().upper(),
            ))
        except ValueError:
            continue
    if pts:
        return pts
    # Record-based fallback (older DC)
    cur: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('--'):
            if cur.get('nm') and cur.get('la') and ('ln' in cur or 'lo' in cur):
                try:
                    pts.append(SurveyPoint(
                        cur['nm'],
                        float(cur.get('ln', cur.get('lo', '0'))),
                        float(cur['la']),
                        float(cur.get('el', '0')),
                        cur.get('cd', '').upper(),
                    ))
                except ValueError:
                    pass
            cur = {}
        elif ' ' in line:
            k, _, v = line.partition(' ')
            cur[k.lower()] = v.strip()
    return pts


def read_landxml(text: str) -> list[SurveyPoint]:
    pts: list[SurveyPoint] = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return pts
    ns_m = re.search(r'\{([^}]+)\}', root.tag)
    ns = '{' + ns_m.group(1) + '}' if ns_m else ''
    for cg in root.iter(ns + 'CgPoint'):
        raw = (cg.text or '').strip().split()
        if len(raw) < 2:
            continue
        try:
            pts.append(SurveyPoint(
                cg.get('name', cg.get('id', str(len(pts) + 1))),
                float(raw[1]),
                float(raw[0]),
                float(raw[2]) if len(raw) > 2 else 0.0,
                cg.get('code', cg.get('desc', '')).upper(),
            ))
        except ValueError:
            continue
    return pts


# ---------------------------------------------------------------------------
# Format detection + unified reader
# ---------------------------------------------------------------------------

def detect_format(text: str) -> str:
    s = text.lstrip('﻿').lstrip()
    if s.startswith('<'):
        return 'landxml'
    if re.search(r'MP,NM|JB,NM|--GPS--|--Obs--', s[:600], re.I):
        return 'dc'
    if re.search(r'^\*?\d{2}[.0-9]{4}[+\-]\d', s, re.M):
        return 'gsi'
    return 'csv'


def read_survey_file(
    path: str,
    col_map: dict[str, int] | None = None,
) -> tuple[list[SurveyPoint], str]:
    with open(path, 'r', encoding='utf-8-sig', errors='replace') as f:
        text = f.read()
    fmt = detect_format(text)
    readers = {'landxml': read_landxml, 'gsi': read_leica_gsi,
               'dc': read_trimble_dc, 'csv': lambda t: read_generic_csv(t, col_map)}
    pts = readers[fmt](text)
    if pts and _is_geographic(pts):
        pts = _project_geographic(pts)
    return pts, fmt


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _dist(a: SurveyPoint, b: SurveyPoint) -> float:
    return math.sqrt((b.easting - a.easting) ** 2 + (b.northing - a.northing) ** 2)


def _bearing(a: SurveyPoint, b: SurveyPoint) -> float:
    return math.degrees(math.atan2(b.easting - a.easting, b.northing - a.northing)) % 360.0


def _deflection(b1: float, b2: float) -> float:
    d = (b2 - b1 + 360.0) % 360.0
    return d - 360.0 if d > 180.0 else d


def _cum_stations(pts: list[SurveyPoint]) -> list[float]:
    st = [0.0]
    for i in range(1, len(pts)):
        st.append(st[-1] + _dist(pts[i - 1], pts[i]))
    return st


def _sort_by_station(pts: list[SurveyPoint]) -> list[SurveyPoint]:
    """Nearest-neighbour traversal starting from an extreme endpoint."""
    if len(pts) <= 2:
        return list(pts)
    e_range = max(p.easting  for p in pts) - min(p.easting  for p in pts)
    n_range = max(p.northing for p in pts) - min(p.northing for p in pts)
    start = min(pts, key=lambda p: p.easting if e_range >= n_range else p.northing)
    ordered = [start]
    remaining = list(pts)
    remaining.remove(start)
    while remaining:
        last = ordered[-1]
        nearest = min(remaining, key=lambda p: _dist(last, p))
        ordered.append(nearest)
        remaining.remove(nearest)
    return ordered


def _filter_codes(pts: list[SurveyPoint], codes_str: str) -> list[SurveyPoint]:
    codes = {c.strip().upper() for c in codes_str.split(',') if c.strip()}
    if not codes:
        return list(pts)
    return [p for p in pts if p.code in codes]


# ---------------------------------------------------------------------------
# PI detection
# ---------------------------------------------------------------------------

def detect_pis(
    cl_pts: list[SurveyPoint],
    angle_threshold: float = 1.0,
    design_speed: float = 80.0,
    min_seg_m: float = 5.0,
) -> list[dict[str, Any]]:
    if len(cl_pts) < 2:
        return []
    pts = _sort_by_station(cl_pts)
    pis: list[dict[str, Any]] = [_pi_row(1, pts[0], design_speed)]
    pi_id = 2
    for i in range(1, len(pts) - 1):
        if _dist(pts[i - 1], pts[i]) < min_seg_m:
            continue
        b_in  = _bearing(pts[i - 1], pts[i])
        b_out = _bearing(pts[i],     pts[i + 1])
        if abs(_deflection(b_in, b_out)) >= angle_threshold:
            pis.append(_pi_row(pi_id, pts[i], design_speed))
            pi_id += 1
    pis.append(_pi_row(pi_id, pts[-1], design_speed))
    return pis


def _pi_row(pi_id: int, p: SurveyPoint, speed: float) -> dict[str, Any]:
    return {
        'pi_id':            pi_id,
        'easting':          round(p.easting,  3),
        'northing':         round(p.northing, 3),
        'radius_m':         0.0,
        'spiral_in_m':      0.0,
        'spiral_out_m':     0.0,
        'design_speed_kph': int(speed),
    }


# ---------------------------------------------------------------------------
# PVI detection
# ---------------------------------------------------------------------------

def detect_pvis(
    cl_pts: list[SurveyPoint],
    grade_threshold: float = 0.5,
) -> list[dict[str, Any]]:
    if len(cl_pts) < 2:
        return []
    pts = _sort_by_station(cl_pts)
    sta = _cum_stations(pts)
    pvis: list[dict[str, Any]] = [_pvi_row(sta[0], pts[0].elevation)]
    for i in range(1, len(pts) - 1):
        ds_in  = sta[i] - sta[i - 1]
        ds_out = sta[i + 1] - sta[i]
        if ds_in < 0.01 or ds_out < 0.01:
            continue
        g_in  = (pts[i].elevation - pts[i - 1].elevation) / ds_in  * 100.0
        g_out = (pts[i + 1].elevation - pts[i].elevation) / ds_out * 100.0
        if abs(g_out - g_in) >= grade_threshold:
            pvis.append(_pvi_row(sta[i], pts[i].elevation))
    pvis.append(_pvi_row(sta[-1], pts[-1].elevation))
    return pvis


def _pvi_row(station: float, elevation: float) -> dict[str, Any]:
    return {
        'station_m':      round(station,   3),
        'elevation_m':    round(elevation, 3),
        'k_crest':        0.0,
        'k_sag':          0.0,
        'curve_length_m': 0.0,
    }


# ---------------------------------------------------------------------------
# Section widths
# ---------------------------------------------------------------------------

def compute_sections(
    cl_pts: list[SurveyPoint],
    ls_pts: list[SurveyPoint],
    rs_pts: list[SurveyPoint],
    tol_m:  float = 10.0,
) -> list[dict[str, Any]]:
    if not cl_pts:
        return []
    pts = _sort_by_station(cl_pts)
    sta = _cum_stations(pts)

    def _nearest(p: SurveyPoint) -> int:
        return min(range(len(pts)), key=lambda i: _dist(pts[i], p))

    left_by:  dict[int, list[float]] = {}
    right_by: dict[int, list[float]] = {}
    for p in ls_pts:
        left_by.setdefault(_nearest(p), []).append(_dist(pts[_nearest(p)], p))
    for p in rs_pts:
        right_by.setdefault(_nearest(p), []).append(_dist(pts[_nearest(p)], p))

    all_idxs = sorted(set(left_by) | set(right_by))
    if not all_idxs:
        return [{'region_id': 1, 'start_sta': round(sta[0], 3),
                 'end_sta': round(sta[-1], 3), 'lane_width_m': 3.5,
                 'shoulder_l_m': 1.5, 'shoulder_r_m': 1.5,
                 'target_l': 'EG', 'target_r': 'EG'}]

    # Merge indices within tol_m into groups
    groups: list[list[int]] = []
    grp = [all_idxs[0]]
    for idx in all_idxs[1:]:
        if sta[idx] - sta[grp[-1]] <= tol_m:
            grp.append(idx)
        else:
            groups.append(grp)
            grp = [idx]
    groups.append(grp)

    regions: list[dict[str, Any]] = []
    for g, group in enumerate(groups):
        lo = [v for i in group for v in left_by.get(i,  [])]
        ro = [v for i in group for v in right_by.get(i, [])]
        lt = max(lo) if lo else 5.0
        rt = max(ro) if ro else 5.0
        sl = round(min(2.0, lt * 0.25), 2)
        sr = round(min(2.0, rt * 0.25), 2)
        lw = round(max(2.5, (lt + rt) / 2.0 - (sl + sr) / 2.0), 2)
        mid = sta[group[len(group) // 2]]
        s0  = sta[0] if g == 0 else (sta[groups[g - 1][len(groups[g - 1]) // 2]] + mid) / 2
        s1  = sta[-1] if g == len(groups) - 1 else (mid + sta[groups[g + 1][0]]) / 2
        regions.append({'region_id': g + 1, 'start_sta': round(s0, 3),
                        'end_sta': round(s1, 3), 'lane_width_m': lw,
                        'shoulder_l_m': sl, 'shoulder_r_m': sr,
                        'target_l': 'EG', 'target_r': 'EG'})
    return regions


# ---------------------------------------------------------------------------
# Signage extraction
# ---------------------------------------------------------------------------

def extract_signage(
    cl_pts:  list[SurveyPoint],
    sgn_pts: list[SurveyPoint],
) -> list[dict[str, Any]]:
    if not cl_pts or not sgn_pts:
        return []
    pts = _sort_by_station(cl_pts)
    sta = _cum_stations(pts)
    rows: list[dict[str, Any]] = []
    for row_id, sp in enumerate(sgn_pts, start=1):
        ni = min(range(len(pts)), key=lambda i: _dist(pts[i], sp))
        offset = round(_dist(pts[ni], sp), 3)
        if ni < len(pts) - 1:
            dx = pts[ni + 1].easting  - pts[ni].easting
            dy = pts[ni + 1].northing - pts[ni].northing
            sx = sp.easting  - pts[ni].easting
            sy = sp.northing - pts[ni].northing
            side = 'L' if (dx * sy - dy * sx) > 0 else 'R'
            brg  = _bearing(pts[ni], pts[ni + 1])
        else:
            side = 'R'
            brg  = _bearing(pts[ni - 1], pts[ni]) if ni > 0 else 0.0
        code = sp.code.upper()
        rows.append({'row': row_id, 'station_m': round(sta[ni], 3),
                     'offset_m': offset, 'side': side, 'sign_code': code,
                     'block_name': f'SIGN_{code}', 'rotation_deg': round(brg, 1)})
    return rows


# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------

def write_csv(rows: list[dict], headers: list[str], path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = _csv.DictWriter(f, fieldnames=headers, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_all(
    survey_file:  str,
    out_dir:      str,
    cl_codes:     str   = DEFAULT_CODES['cl'],
    left_codes:   str   = DEFAULT_CODES['left'],
    right_codes:  str   = DEFAULT_CODES['right'],
    sign_codes:   str   = DEFAULT_CODES['sign'],
    angle_thresh: float = 1.0,
    grade_thresh: float = 0.5,
    station_tol:  float = 10.0,
    design_speed: float = 80.0,
    col_map: dict[str, int] | None = None,
) -> list[str]:
    log: list[str] = []
    pts, fmt = read_survey_file(survey_file, col_map)
    log.append(f"Read {len(pts)} points  (format: {fmt.upper()})")
    all_codes = sorted({p.code for p in pts if p.code})
    log.append(f"Codes in file: {', '.join(all_codes) if all_codes else '(none)'}")

    cl  = _filter_codes(pts, cl_codes)
    ls  = _filter_codes(pts, left_codes)
    rs  = _filter_codes(pts, right_codes)
    sgn = _filter_codes(pts, sign_codes)

    if not cl and not ls and not rs:
        log.append("No matching codes — treating all points as centreline.")
        cl = list(pts)

    log.append(f"CL:{len(cl)}  Left:{len(ls)}  Right:{len(rs)}  Signs:{len(sgn)}")
    log.append("")

    if not cl:
        log.append("ERROR: No centreline points found. Check code settings.")
        return log

    for name, rows, headers in [
        ("alignment_pi",     detect_pis(cl, angle_thresh, design_speed),   CSV_HEADERS["alignment_pi"]),
        ("profile_pvis",     detect_pvis(cl, grade_thresh),                 CSV_HEADERS["profile_pvis"]),
        ("section_widths",   compute_sections(cl, ls, rs, station_tol),     CSV_HEADERS["section_widths"]),
        ("signage_schedule", extract_signage(cl, sgn),                      CSV_HEADERS["signage_schedule"]),
    ]:
        path = os.path.join(out_dir, name + ".csv")
        write_csv(rows, headers, path)
        log.append(f"  {name}.csv  →  {len(rows)} rows  →  {path}")

    log.append("")
    log.append("Review alignment_pi.csv  — set radius_m for curved PIs (default 0).")
    log.append("Review profile_pvis.csv  — set k_crest / k_sag values (default 0).")
    log.append("Run preflight: python tools/road_automation_preflight.py")
    return log


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

def run_gui() -> None:
    import tkinter as tk
    from tkinter import ttk, filedialog, scrolledtext

    BG_DARK   = "#1c2030"
    BG_LIGHT  = "#f4f4f6"
    ACCENT    = "#F0A500"
    BTN_GREEN = "#1c6f44"
    FONT_BODY = ("Segoe UI", 10)
    FONT_HEAD = ("Segoe UI", 12, "bold")

    root = tk.Tk()
    root.title("Road automation — DGPS survey importer")
    root.minsize(780, 640)
    root.configure(bg=BG_LIGHT)

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TNotebook",          background=BG_DARK, tabmargins=[0, 0, 0, 0])
    style.configure("TNotebook.Tab",      background=BG_DARK, foreground="#aaaaaa",
                                           padding=[14, 6], font=FONT_BODY)
    style.map("TNotebook.Tab",
              background=[("selected", BG_LIGHT)],
              foreground=[("selected", BG_DARK)],
              font=[("selected", ("Segoe UI", 10, "bold"))])
    for w in ("TFrame", "TLabel", "TCheckbutton", "TLabelframe"):
        style.configure(w, background=BG_LIGHT, font=FONT_BODY)
    style.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"))
    style.configure("TEntry",   font=FONT_BODY)
    style.configure("TSpinbox", font=FONT_BODY)
    style.configure("Accent.TButton", background=BTN_GREEN, foreground="white",
                    font=("Segoe UI", 10, "bold"), padding=[10, 6])
    style.map("Accent.TButton", background=[("active", "#145230")])

    # Banner
    banner = tk.Frame(root, bg=BG_DARK, height=52)
    banner.pack(fill=tk.X)
    banner.pack_propagate(False)
    tk.Label(banner, text="Road Design Automation — DGPS Survey Importer",
             bg=BG_DARK, fg=ACCENT, font=("Segoe UI", 13, "bold"),
             ).pack(side=tk.LEFT, padx=16, pady=10)

    nb = ttk.Notebook(root)
    nb.pack(fill=tk.BOTH, expand=True, padx=12, pady=(10, 4))

    # State
    _state: dict[str, Any] = {'pts': [], 'fmt': ''}
    path_var   = tk.StringVar()
    fmt_var    = tk.StringVar(value="—")
    count_var  = tk.StringVar(value="")
    out_var    = tk.StringVar(value=os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "csv")))
    code_vars  = {k: tk.StringVar(value=v) for k, v in DEFAULT_CODES.items()}
    angle_var  = tk.DoubleVar(value=1.0)
    grade_var  = tk.DoubleVar(value=0.5)
    tol_var    = tk.DoubleVar(value=10.0)
    speed_var  = tk.DoubleVar(value=80.0)
    det_var    = tk.StringVar(value="")

    # ── Tab 1: Load ──────────────────────────────────────────────────────
    t1 = ttk.Frame(nb, padding=(16, 14))
    nb.add(t1, text="1  Load file")
    ttk.Label(t1, text="Load survey file", font=FONT_HEAD).grid(
        row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

    ttk.Label(t1, text="File:", anchor="w").grid(row=1, column=0, sticky="w")
    ttk.Entry(t1, textvariable=path_var, width=56).grid(
        row=1, column=1, sticky="ew", padx=(8, 8))

    tree = ttk.Treeview(t1,
        columns=("id", "easting", "northing", "elevation", "code"),
        show="headings", height=13)
    for col, w in [("id", 9), ("easting", 15), ("northing", 15), ("elevation", 12), ("code", 9)]:
        tree.heading(col, text=col.title())
        tree.column(col, width=w * 8, anchor="center")

    info = ttk.Frame(t1)
    info.grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 4))
    ttk.Label(info, text="Format:").pack(side=tk.LEFT)
    ttk.Label(info, textvariable=fmt_var, foreground="#1c6f44",
              font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=(4, 16))
    ttk.Label(info, textvariable=count_var, foreground="#555555").pack(side=tk.LEFT)

    def _load(path: str | None = None) -> None:
        if not path:
            path = filedialog.askopenfilename(
                title="Select survey file",
                filetypes=[("Survey files", "*.csv *.txt *.gsi *.dc *.xml"),
                           ("All files", "*.*")])
        if not path:
            return
        try:
            pts, fmt = read_survey_file(path)
            _state['pts'] = pts
            _state['fmt'] = fmt
            path_var.set(path)
            fmt_var.set(fmt.upper())
            count_var.set(f"{len(pts)} points loaded")
            tree.delete(*tree.get_children())
            for p in pts[:300]:
                tree.insert("", "end", values=(
                    p.id, f"{p.easting:.3f}", f"{p.northing:.3f}",
                    f"{p.elevation:.3f}", p.code or "—"))
            codes = sorted({p.code for p in pts if p.code})
            det_var.set("Codes detected: " + (", ".join(codes) if codes else "(none)"))
        except Exception as ex:
            fmt_var.set("ERROR"); count_var.set(str(ex))

    ttk.Button(t1, text="Browse…", command=_load).grid(row=1, column=2)
    tree.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=(4, 0))
    sb = ttk.Scrollbar(t1, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    sb.grid(row=4, column=3, sticky="ns")
    t1.columnconfigure(1, weight=1)
    t1.rowconfigure(4, weight=1)

    # ── Tab 2: Codes ─────────────────────────────────────────────────────
    t2 = ttk.Frame(nb, padding=(16, 14))
    nb.add(t2, text="2  Assign codes")
    ttk.Label(t2, text="Assign point codes to roles", font=FONT_HEAD).grid(
        row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
    ttk.Label(t2,
        text="Comma-separated codes for each role.  "
             "Leave CL empty to treat ALL points as centreline (no-code surveys).",
        foreground="#555555", wraplength=560, justify="left",
    ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 12))
    ttk.Label(t2, textvariable=det_var, foreground="#1c6f44",
              wraplength=560).grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 10))

    roles = [('cl', 'Centreline (CL)', 'Points defining the road centreline'),
             ('left', 'Left side (LS)', 'Left shoulder / edge shots'),
             ('right', 'Right side (RS)', 'Right shoulder / edge shots'),
             ('sign', 'Signs (SGN)', 'Sign / furniture locations')]
    for i, (k, label, hint) in enumerate(roles, start=3):
        ttk.Label(t2, text=label, width=22, anchor="w").grid(row=i, column=0, sticky="w", pady=5)
        ttk.Entry(t2, textvariable=code_vars[k], width=36).grid(
            row=i, column=1, sticky="ew", padx=(8, 8), pady=5)
        ttk.Label(t2, text=hint, foreground="#888888").grid(row=i, column=2, sticky="w")
    t2.columnconfigure(1, weight=1)

    # ── Tab 3: Parameters ────────────────────────────────────────────────
    t3 = ttk.Frame(nb, padding=(16, 14))
    nb.add(t3, text="3  Parameters")
    ttk.Label(t3, text="Detection parameters", font=FONT_HEAD).grid(
        row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
    params = [
        (angle_var, "PI angle threshold (°)",
         "Minimum bearing change to detect a PI.\nLower = more PIs.  Typical: 0.5–2°",
         0.1, 45.0),
        (grade_var, "PVI grade threshold (%)",
         "Minimum grade change to detect a PVI.\nLower = more PVIs.  Typical: 0.3–1%",
         0.1, 20.0),
        (tol_var,   "Section grouping tolerance (m)",
         "Cross-section shots within this station\ndistance are merged into one region.",
         1.0, 100.0),
        (speed_var, "Design speed (km/h)",
         "Written to every PI row in alignment_pi.csv.",
         20.0, 200.0),
    ]
    for i, (var, label, hint, lo, hi) in enumerate(params, start=1):
        ttk.Label(t3, text=label, width=30, anchor="w").grid(row=i, column=0, sticky="w", pady=6)
        ttk.Spinbox(t3, textvariable=var, from_=lo, to=hi, increment=0.1,
                    width=10, format="%.1f").grid(row=i, column=1, sticky="w", padx=(8, 8))
        ttk.Label(t3, text=hint, foreground="#888888",
                  wraplength=320, justify="left").grid(row=i, column=2, sticky="w")
    t3.columnconfigure(2, weight=1)

    # ── Tab 4: Generate ──────────────────────────────────────────────────
    t4 = ttk.Frame(nb, padding=(16, 14))
    nb.add(t4, text="4  Generate")
    ttk.Label(t4, text="Generate CSVs", font=FONT_HEAD).grid(
        row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
    ttk.Label(t4, text="Output folder:").grid(row=1, column=0, sticky="w")
    ttk.Entry(t4, textvariable=out_var, width=54).grid(
        row=1, column=1, sticky="ew", padx=(8, 8))
    ttk.Button(t4, text="Browse…",
               command=lambda: out_var.set(
                   filedialog.askdirectory(title="Output folder") or out_var.get())
               ).grid(row=1, column=2)

    log_txt = scrolledtext.ScrolledText(
        t4, height=16, wrap=tk.WORD, font=("Consolas", 9),
        bg="#1e1e1e", fg="#d4d4d4", insertbackground="white")
    log_txt.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
    t4.columnconfigure(1, weight=1)
    t4.rowconfigure(3, weight=1)

    def _generate() -> None:
        if not path_var.get() or not os.path.isfile(path_var.get()):
            log_txt.insert(tk.END, "[ERROR] Load a survey file first (Tab 1).\n")
            nb.select(t1)
            return
        log_txt.delete("1.0", tk.END)
        log_txt.insert(tk.END, "Processing…\n\n")
        log_txt.update()
        try:
            lines = run_all(
                survey_file  = path_var.get(),
                out_dir      = out_var.get().strip(),
                cl_codes     = code_vars['cl'].get(),
                left_codes   = code_vars['left'].get(),
                right_codes  = code_vars['right'].get(),
                sign_codes   = code_vars['sign'].get(),
                angle_thresh = angle_var.get(),
                grade_thresh = grade_var.get(),
                station_tol  = tol_var.get(),
                design_speed = speed_var.get(),
            )
            for line in lines:
                log_txt.insert(tk.END, line + "\n")
        except Exception as ex:
            log_txt.insert(tk.END, f"[ERROR] {ex}\n")
        log_txt.see(tk.END)

    ttk.Button(t4, text="Generate all CSVs",
               style="Accent.TButton", command=_generate,
               ).grid(row=2, column=0, sticky="w", pady=(8, 0))

    root.mainloop()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def run_cli(survey_file: str) -> int:
    out_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "csv"))
    print(f"Input : {survey_file}")
    print(f"Output: {out_dir}\n")
    for line in run_all(survey_file, out_dir):
        print(line)
    return 0


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == '--cli':
        if len(args) < 2:
            print("Usage: python survey_to_csv.py --cli <survey_file>", file=sys.stderr)
            sys.exit(2)
        sys.exit(run_cli(args[1]))
    try:
        run_gui()
    except ImportError as ex:
        if "tkinter" in str(ex).lower():
            print("Tkinter unavailable — use: python survey_to_csv.py --cli <file>",
                  file=sys.stderr)
            sys.exit(2)
        raise


if __name__ == "__main__":
    main()
