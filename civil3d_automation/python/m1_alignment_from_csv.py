# -*- coding: utf-8 -*-
"""
M1 — Alignment from PI CSV with real curve/spiral geometry.
Dynamo inputs:
  IN[0] : str   — full path to alignment_pi.csv
  IN[1] : str   — alignment name (must not already exist)
  IN[2] : str   — alignment style name (e.g. Standard)
  IN[3] : str   — alignment label set name (e.g. Standard)
  IN[4] : float — optional start station (default 0)
  IN[5] : str   — optional path to project.json (for design tolerances)

Curve insertion: three-tier ladder per PI:
  Tier 1 (Civil 3D 2022+): AddFreeSpiralCurveSpiral — full SCS with clothoid transitions
  Tier 2:                   AddFreeCurve            — simple arc, no spirals
  Tier 3 (fallback):        AddFixedLine segments   — tangent only, warning logged
"""
import clr
import csv
import codecs
import json
import math
import os

clr.AddReference('AcMgd')
clr.AddReference('AcDbMgd')
clr.AddReference('AecBaseMgd')
clr.AddReference('AeccDbMgd')

from Autodesk.AutoCAD.ApplicationServices import Application
from Autodesk.AutoCAD.DatabaseServices import OpenMode
from Autodesk.AutoCAD.Geometry import Point3d
from Autodesk.Civil.ApplicationServices import CivilApplication
from Autodesk.Civil.DatabaseServices import Alignment


# ---------------------------------------------------------------------------
# helpers (IronPython 2.7 — no f-strings, no type hints)
# ---------------------------------------------------------------------------

def _read_csv(path):
    rows = []
    with codecs.open(path, 'r', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def _load_design_params(project_json_path):
    """Load tolerance/spacing/tangent params from project.json with safe defaults."""
    defaults = {
        'centreline_tolerance_m': 2.0,
        'min_pi_spacing_m': 5.0,
        'min_tangent_length_m': 20.0,
    }
    if not project_json_path or not os.path.isfile(str(project_json_path)):
        return defaults
    try:
        with codecs.open(str(project_json_path), 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        d = cfg.get('design', {})
        for k in defaults:
            if k in d and d[k] is not None:
                defaults[k] = float(d[k])
    except Exception:
        pass
    return defaults


def _bearing(dx, dy):
    """Bearing in radians from north (atan2 of easting, northing deltas)."""
    return math.atan2(dx, dy)


def _perp_offset(prev_pt, cur_pt, nxt_pt):
    """Perpendicular distance from cur_pt to chord prev_pt→nxt_pt (metres)."""
    ax = prev_pt.X
    ay = prev_pt.Y
    bx = nxt_pt.X
    by = nxt_pt.Y
    px = cur_pt.X
    py = cur_pt.Y
    chord = math.sqrt((bx - ax) ** 2 + (by - ay) ** 2)
    if chord < 1e-9:
        return 0.0
    # Cross-product magnitude / chord
    return abs((bx - ax) * (ay - py) - (ax - px) * (by - ay)) / chord


def _deflection_deg(bearing_in, bearing_out):
    """Signed deflection angle in degrees (-180..+180). Positive = right."""
    delta = math.degrees(bearing_out - bearing_in)
    while delta > 180.0:
        delta -= 360.0
    while delta < -180.0:
        delta += 360.0
    return delta


def _run_qc_checks(pis, pts, tolerance_m, min_spacing_m, min_tangent_m):
    """
    Pre-geometry QA pass. Returns list of warning strings.
    pis  — list of dict rows
    pts  — list of Point3d matching pis
    """
    warnings = []
    n = len(pis)

    # 1. Near-duplicate / short spacing check
    for i in range(1, n):
        dx = pts[i].X - pts[i - 1].X
        dy = pts[i].Y - pts[i - 1].Y
        d = math.sqrt(dx * dx + dy * dy)
        if d < min_spacing_m:
            warnings.append(
                'QA-W: PI %s too close to PI %s (%.1f m < %.1f m min spacing)'
                % (pis[i].get('pi_id', str(i)), pis[i - 1].get('pi_id', str(i - 1)),
                   d, min_spacing_m)
            )

    # 2. Perpendicular chord offset outliers (interior PIs only)
    if n >= 3:
        offsets = []
        for i in range(1, n - 1):
            offsets.append(_perp_offset(pts[i - 1], pts[i], pts[i + 1]))
        if offsets:
            sorted_offs = sorted(offsets)
            mid = len(sorted_offs) // 2
            median_off = (sorted_offs[mid] if len(sorted_offs) % 2 == 1
                         else (sorted_offs[mid - 1] + sorted_offs[mid]) / 2.0)
            for i in range(1, n - 1):
                off = offsets[i - 1]
                if off > tolerance_m and (median_off < 1e-9 or off > 3.0 * median_off):
                    warnings.append(
                        'QA-W: PI %s perpendicular offset %.1f m from chord (tol %.1f m) — possible misaligned survey point'
                        % (pis[i].get('pi_id', str(i)), off, tolerance_m)
                    )

    # 3. Deflection angle sanity
    for i in range(1, n - 1):
        dx_in  = pts[i].X - pts[i - 1].X
        dy_in  = pts[i].Y - pts[i - 1].Y
        dx_out = pts[i + 1].X - pts[i].X
        dy_out = pts[i + 1].Y - pts[i].Y
        b_in  = _bearing(dx_in,  dy_in)
        b_out = _bearing(dx_out, dy_out)
        delta = abs(_deflection_deg(b_in, b_out))
        if delta > 160.0:
            warnings.append(
                'QA-W: PI %s deflection %.1f deg > 160 deg — near-tangent or wrong entry'
                % (pis[i].get('pi_id', str(i)), delta)
            )

    # 4. Impossible spiral geometry
    for r in pis:
        R    = float(r.get('radius_m',    0) or 0)
        Ls_i = float(r.get('spiral_in_m',  0) or 0)
        Ls_o = float(r.get('spiral_out_m', 0) or 0)
        if R > 0 and (Ls_i + Ls_o) > 0:
            theta_i = Ls_i / (2.0 * R)
            theta_o = Ls_o / (2.0 * R)
            if theta_i + theta_o >= math.pi:
                warnings.append(
                    'QA-E: PI %s spiral lengths (%.1f + %.1f) exceed 360 deg for R=%.1f — geometry impossible; spirals omitted'
                    % (r.get('pi_id', '?'), Ls_i, Ls_o, R)
                )

    # 5. Short available tangent between consecutive curves
    for i in range(1, n - 1):
        R_prev = float(pis[i - 1].get('radius_m', 0) or 0)
        R_cur  = float(pis[i].get('radius_m', 0)     or 0)
        if R_prev > 0 and R_cur > 0:
            dx = pts[i].X - pts[i - 1].X
            dy = pts[i].Y - pts[i - 1].Y
            avail = math.sqrt(dx * dx + dy * dy)
            if avail < min_tangent_m:
                warnings.append(
                    'QA-W: Tangent between PI %s and PI %s is %.1f m (min %.1f m) — compound/reverse curve likely'
                    % (pis[i - 1].get('pi_id', str(i - 1)), pis[i].get('pi_id', str(i)),
                       avail, min_tangent_m)
                )

    return warnings


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------

def run(csv_path, alignment_name, style_name, label_set_name, start_station,
        project_json_path):
    warnings = []
    if not os.path.isfile(csv_path):
        return 'ERROR: CSV not found: ' + str(csv_path)

    pis = _read_csv(csv_path)
    if len(pis) < 2:
        return 'ERROR: Need at least 2 PI rows'

    # Load design tolerances
    params = _load_design_params(project_json_path)
    tol_m         = params['centreline_tolerance_m']
    min_spacing   = params['min_pi_spacing_m']
    min_tangent   = params['min_tangent_length_m']

    # Build Point3d list
    pts = []
    for r in pis:
        try:
            x = float(r['easting'])
            y = float(r['northing'])
        except (KeyError, ValueError):
            return 'ERROR: Bad easting/northing in row: ' + str(r)
        pts.append(Point3d(x, y, 0.0))

    # Pre-geometry QA
    qc_warns = _run_qc_checks(pis, pts, tol_m, min_spacing, min_tangent)
    warnings.extend(qc_warns)

    doc    = Application.DocumentManager.MdiActiveDocument
    db     = doc.Database
    civdoc = CivilApplication.ActiveDocument

    # Check duplicate alignment name
    for aid in civdoc.GetAlignmentIds():
        if Alignment.GetAlignmentName(aid) == alignment_name:
            return "ERROR: Alignment '%s' already exists — rename or delete first." % alignment_name

    curves_inserted = 0
    curves_tier1    = 0
    curves_tier2    = 0
    curves_fallback = 0

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
                align.ReferenceStation = float(start_station)
            except Exception:
                pass

            ents = align.Entities
            n    = len(pts)

            # ----------------------------------------------------------------
            # Step 1: Add ALL tangent lines; keep entity references for
            #         curve-insertion API that replaces tangent pairs.
            # ----------------------------------------------------------------
            tangent_ents = []
            for i in range(n - 1):
                ent = ents.AddFixedLine(pts[i], pts[i + 1])
                tangent_ents.append(ent)

            # ----------------------------------------------------------------
            # Step 2: Insert curves at interior PIs (three-tier ladder).
            #
            # Civil 3D "free" geometry: the API removes the adjacent tangent
            # segments and replaces them with a tangent–curve–tangent chain,
            # maintaining the fixed endpoints of the outer tangents.
            # ----------------------------------------------------------------
            for i in range(1, n - 1):
                R    = float(pis[i].get('radius_m',    0) or 0)
                Ls_i = float(pis[i].get('spiral_in_m',  0) or 0)
                Ls_o = float(pis[i].get('spiral_out_m', 0) or 0)
                if R <= 0:
                    continue

                # Validate spiral geometry; zero out if impossible
                if Ls_i > 0 or Ls_o > 0:
                    theta_i = Ls_i / (2.0 * R)
                    theta_o = Ls_o / (2.0 * R)
                    if theta_i + theta_o >= math.pi:
                        warnings.append(
                            'QA: PI %s spiral omitted — combined angle %.1f deg >= 360 deg'
                            % (pis[i].get('pi_id', '?'), math.degrees(theta_i + theta_o))
                        )
                        Ls_i = 0.0
                        Ls_o = 0.0

                prev_ent = tangent_ents[i - 1]
                next_ent = tangent_ents[i]
                inserted = False

                # -- Tier 1: Spiral-Curve-Spiral (Civil 3D 2022+) --
                if (Ls_i > 0 or Ls_o > 0) and not inserted:
                    try:
                        ents.AddFreeSpiralCurveSpiral(
                            prev_ent, pts[i], next_ent, Ls_i, R, Ls_o
                        )
                        inserted     = True
                        curves_tier1 += 1
                        curves_inserted += 1
                    except Exception as e_scs:
                        warnings.append(
                            'QA: PI %s SCS failed (%s); trying simple arc'
                            % (pis[i].get('pi_id', '?'), str(e_scs)[:80])
                        )

                # -- Tier 2: Simple free arc (no spirals) --
                if not inserted:
                    try:
                        ents.AddFreeCurve(prev_ent, pts[i], next_ent, R)
                        inserted     = True
                        curves_tier2 += 1
                        curves_inserted += 1
                    except Exception as e_arc:
                        warnings.append(
                            'QA: PI %s arc failed (%s); kept as tangent'
                            % (pis[i].get('pi_id', '?'), str(e_arc)[:80])
                        )

                # -- Tier 3: tangent already in place — nothing to do --
                if not inserted:
                    curves_fallback += 1
                    warnings.append(
                        'QA: PI %s — straight tangent only (no curve API available)'
                        % pis[i].get('pi_id', '?')
                    )

            # Design speed from first row
            try:
                spd = float(pis[0].get('design_speed_kph', 0) or 0)
                if spd > 0 and hasattr(align, 'DesignSpeedSummary') and align.DesignSpeedSummary is not None:
                    align.DesignSpeedSummary.Clear()
                    align.DesignSpeedSummary.AddDesignSpeed(float(start_station), spd)
            except Exception:
                pass

            tr.Commit()

    msg = (
        'OK: Alignment "%s" created. Segments: %d tangent(s). '
        'Curves: %d inserted (%d SCS, %d arc, %d tangent-only).'
        % (alignment_name, n - 1, curves_inserted,
           curves_tier1, curves_tier2, curves_fallback)
    )
    if warnings:
        msg += '\n' + '\n'.join(warnings)
    return msg


# ---------------------------------------------------------------------------
# Dynamo entry point
# ---------------------------------------------------------------------------
csv_path          = IN[0]
alignment_name    = IN[1]
style_name        = IN[2] if len(IN) > 2 else 'Standard'
label_set_name    = IN[3] if len(IN) > 3 else 'Standard'
start_station     = float(IN[4]) if len(IN) > 4 and IN[4] is not None else 0.0
project_json_path = IN[5] if len(IN) > 5 and IN[5] is not None else ''

OUT = run(csv_path, alignment_name, style_name, label_set_name,
          start_station, project_json_path)
