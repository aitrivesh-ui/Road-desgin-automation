# -*- coding: utf-8 -*-
"""
M10 — Cross-Section Generator (Sample Lines + Section Views).

Reads section stations from sections.csv OR auto-generates them at a fixed
interval along the alignment, then creates a SampleLineGroup and individual
SampleLine objects in the Civil 3D document.  Attempts to place SectionViews
in a grid layout; logs a note if the API is unavailable (version-dependent).
Finally writes a sections_list.csv to the out/ directory.

Dynamo inputs:
  IN[0] : str — absolute path to config/project.json

project.json keys used:
  paths.sections              → csv/sections.csv         (optional)
  names.alignment             → alignment name            (e.g. DEMO-CL)
  names.sample_line_group     → SL-GROUP                 (default)
  design.section_interval_m   → 25.0                     (default)
  design.section_left_width_m → 15.0                     (default)
  design.section_right_width_m→ 15.0                     (default)

sections.csv columns (all optional — if file missing, stations are auto-generated):
  station_m, label, left_width_m, right_width_m

Output CSV  out/sections_list.csv:
  station_m, label, left_width_m, right_width_m, sl_created
"""
import clr
import csv
import codecs
import os
import json
import math

clr.AddReference('AcMgd')
clr.AddReference('AcDbMgd')
clr.AddReference('AeccDbMgd')

from Autodesk.AutoCAD.ApplicationServices import Application
from Autodesk.AutoCAD.DatabaseServices import (
    OpenMode, BlockTable, BlockTableRecord,
    LayerTableRecord, LayerTable,
    RegAppTableRecord, RegAppTable,
)
from Autodesk.AutoCAD.Geometry import Point3d
from Autodesk.AutoCAD.Colors import Color, ColorMethod
from Autodesk.Civil.ApplicationServices import CivilApplication
from Autodesk.Civil.DatabaseServices import Alignment

# Imported below conditionally to handle version differences
# from Autodesk.Civil.DatabaseServices import SampleLineGroup, SampleLine


# ---------------------------------------------------------------------------
# Utility helpers (mirrors m9 / project conventions)
# ---------------------------------------------------------------------------

def _resolve(root, rel):
    """Absolute path: join root + rel, normalised."""
    return os.path.normpath(os.path.join(root, rel.replace('/', os.sep)))


def _ensure_layer(tr, db, name, color_idx=4):
    """Create layer *name* (ACI colour 4 = cyan) if absent."""
    lt = tr.GetObject(db.LayerTableId, OpenMode.ForRead)
    if lt.Has(name):
        return
    ltr = LayerTableRecord()
    ltr.Name  = name
    ltr.Color = Color.FromColorIndex(ColorMethod.ByAci, color_idx)
    lt2 = tr.GetObject(db.LayerTableId, OpenMode.ForWrite)
    lt2.Add(ltr)
    tr.AddNewlyCreatedDBObject(ltr, True)


def _ensure_regapp(tr, db, app_name):
    """Register XData app name if not already in RegAppTable."""
    rat = tr.GetObject(db.RegAppTableId, OpenMode.ForRead)
    if rat.Has(app_name):
        return
    ratr = RegAppTableRecord()
    ratr.Name = app_name
    rat2 = tr.GetObject(db.RegAppTableId, OpenMode.ForWrite)
    rat2.Add(ratr)
    tr.AddNewlyCreatedDBObject(ratr, True)


def _find_alignment(tr, civdoc, name):
    """Return Alignment object matching *name*, or None."""
    for aid in civdoc.GetAlignmentIds():
        a = tr.GetObject(aid, OpenMode.ForRead)
        if a.Name == name:
            return a
    return None


def _fmt_label(sta):
    """Format a station value as STA_X+YYY (e.g. STA_0+025)."""
    km  = int(sta) // 1000
    rem = int(sta) % 1000
    return 'STA_%d+%03d' % (km, rem)


# ---------------------------------------------------------------------------
# Station list builders
# ---------------------------------------------------------------------------

def _stations_from_csv(csv_path):
    """
    Parse sections.csv and return a list of dicts:
      [{'station_m': float, 'label': str,
        'left_width_m': float, 'right_width_m': float}, ...]
    Returns None if the file does not exist.
    """
    if not os.path.isfile(csv_path):
        return None
    rows = []
    with codecs.open(csv_path, 'r', encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            try:
                sta  = float(r['station_m'])
                lw   = float(r.get('left_width_m')  or 15.0)
                rw   = float(r.get('right_width_m') or 15.0)
                lbl  = (r.get('label') or '').strip() or _fmt_label(sta)
                rows.append({
                    'station_m':     sta,
                    'label':         lbl,
                    'left_width_m':  lw,
                    'right_width_m': rw,
                })
            except Exception:
                pass  # skip malformed rows
    return rows if rows else None


def _stations_auto(sta_start, sta_end, interval, left_w, right_w):
    """
    Auto-generate station list from sta_start to sta_end at *interval* spacing.
    Always includes the end station.
    """
    rows = []
    sta  = sta_start
    while sta <= sta_end + 1e-6:
        clamped = min(sta, sta_end)
        rows.append({
            'station_m':     clamped,
            'label':         _fmt_label(clamped),
            'left_width_m':  left_w,
            'right_width_m': right_w,
        })
        if abs(clamped - sta_end) < 1e-6:
            break
        sta += interval
    return rows


# ---------------------------------------------------------------------------
# Civil 3D object creators
# ---------------------------------------------------------------------------

def _get_or_create_slg(tr, civdoc, align_id, slg_name):
    """
    Find an existing SampleLineGroup named *slg_name*, or create a new one.
    Returns the SampleLineGroup object (opened ForWrite) and its ObjectId.
    """
    from Autodesk.Civil.DatabaseServices import SampleLineGroup

    # Check if a group with this name already exists on the alignment
    try:
        existing_ids = SampleLineGroup.GetSampleLineGroupIds(align_id)
        for sid in existing_ids:
            grp = tr.GetObject(sid, OpenMode.ForRead)
            if grp.Name == slg_name:
                return tr.GetObject(sid, OpenMode.ForWrite), sid
    except Exception:
        pass

    # Create new group
    slg_id = SampleLineGroup.Create(slg_name, align_id, civdoc)
    slg    = tr.GetObject(slg_id, OpenMode.ForWrite)
    return slg, slg_id


def _create_sample_line(tr, slg, station, left_w, right_w):
    """
    Create a SampleLine at *station* with the given left/right offsets.
    Returns True on success.
    """
    from Autodesk.Civil.DatabaseServices import SampleLine

    sl_id = SampleLine.Create(slg, station)
    sl    = tr.GetObject(sl_id, OpenMode.ForWrite)
    sl.MaxLeftOffset  = left_w
    sl.MaxRightOffset = right_w
    return True


def _try_section_views(tr, db, civdoc, slg_id, notes):
    """
    Attempt to create SectionView objects in a grid layout.
    Grid: 5 columns, rows grow downward.  Each view is offset 50 m horizontally,
    100 m vertically per row, starting at (0, -100).
    Wraps in try/except — Civil 3D API for SectionView varies by version.
    """
    try:
        from Autodesk.Civil.DatabaseServices import SectionView
    except ImportError:
        notes.append('NOTE: SectionView not available in this Civil 3D version — skipped.')
        return

    try:
        slg        = tr.GetObject(slg_id, OpenMode.ForRead)
        sl_ids     = list(slg.GetSampleLineIds())
        cols       = 5
        col_gap    = 50.0
        row_gap    = 100.0
        base_x     = 0.0
        base_y     = -100.0
        view_count = 0

        for idx, sl_id in enumerate(sl_ids):
            col   = idx % cols
            row   = idx // cols
            vx    = base_x + col * col_gap
            vy    = base_y - row * row_gap
            loc   = Point3d(vx, vy, 0.0)
            try:
                SectionView.Create(sl_id, loc)
                view_count += 1
            except Exception as sv_err:
                notes.append(
                    'NOTE: SectionView.Create failed at index %d: %s'
                    % (idx, str(sv_err))
                )
                break   # if first one fails, rest will too — stop looping

        if view_count:
            notes.append(
                'NOTE: Created %d SectionView(s) in grid layout.' % view_count
            )
    except Exception as e:
        notes.append('NOTE: SectionView block failed: %s' % str(e))


# ---------------------------------------------------------------------------
# Output CSV writer
# ---------------------------------------------------------------------------

def _write_output_csv(out_path, station_rows, sl_results):
    """
    Write sections_list.csv with a sl_created column (True/False/ERROR).
    *sl_results* is a dict keyed by station float.
    """
    d = os.path.dirname(out_path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with codecs.open(out_path, 'w', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['station_m', 'label', 'left_width_m', 'right_width_m', 'sl_created'])
        for r in station_rows:
            sta = r['station_m']
            w.writerow([
                '%.3f' % sta,
                r['label'],
                '%.3f' % r['left_width_m'],
                '%.3f' % r['right_width_m'],
                str(sl_results.get(sta, False)),
            ])


# ---------------------------------------------------------------------------
# Main run function
# ---------------------------------------------------------------------------

def run(project_json):
    if not os.path.isfile(project_json):
        return 'ERROR: project.json not found: %s' % project_json

    with codecs.open(project_json, 'r', encoding='utf-8-sig') as f:
        cfg = json.load(f)

    cfg_dir = os.path.dirname(os.path.abspath(project_json))
    root    = os.path.normpath(os.path.join(cfg_dir, '..'))

    paths  = cfg.get('paths',  {})
    names  = cfg.get('names',  {})
    design = cfg.get('design', {})

    align_name  = names.get('alignment', 'ALIGN')
    slg_name    = names.get('sample_line_group', 'SL-GROUP')
    interval    = float(design.get('section_interval_m',    25.0))
    left_w_def  = float(design.get('section_left_width_m',  15.0))
    right_w_def = float(design.get('section_right_width_m', 15.0))

    sections_rel = paths.get('sections', 'csv/sections.csv')
    sections_csv = _resolve(root, sections_rel)

    out_csv = _resolve(root, 'out/sections_list.csv')

    doc    = Application.DocumentManager.MdiActiveDocument
    db     = doc.Database
    civdoc = CivilApplication.ActiveDocument

    notes    = []
    warnings = []

    with doc.LockDocument():
        with db.TransactionManager.StartTransaction() as tr:

            # ---- Find alignment ----
            align = _find_alignment(tr, civdoc, align_name)
            if align is None:
                tr.Abort()
                return 'ERROR: Alignment not found: %s' % align_name

            align_id  = align.ObjectId
            sta_start = align.StartingStation
            sta_end   = align.EndingStation

            # ---- Build station list ----
            station_rows = _stations_from_csv(sections_csv)
            if station_rows is None:
                notes.append(
                    'NOTE: sections.csv not found (%s) — '
                    'auto-generating at %.1f m intervals.'
                    % (sections_csv, interval)
                )
                station_rows = _stations_auto(
                    sta_start, sta_end, interval, left_w_def, right_w_def
                )
            else:
                notes.append(
                    'NOTE: Loaded %d station(s) from %s.'
                    % (len(station_rows), sections_csv)
                )

            if not station_rows:
                tr.Abort()
                return 'ERROR: No stations to process.'

            # ---- Get / create SampleLineGroup ----
            try:
                slg, slg_id = _get_or_create_slg(tr, civdoc, align_id, slg_name)
            except Exception as slg_err:
                tr.Abort()
                return 'ERROR: SampleLineGroup create/find failed: %s' % str(slg_err)

            # ---- Create SampleLines ----
            sl_results = {}
            created    = 0

            for r in station_rows:
                sta = r['station_m']
                lw  = r['left_width_m']
                rw  = r['right_width_m']
                # Clamp station to alignment range
                if sta < sta_start - 1e-3 or sta > sta_end + 1e-3:
                    warnings.append(
                        'WARN: Station %.3f is outside alignment range '
                        '[%.3f, %.3f] — skipped.' % (sta, sta_start, sta_end)
                    )
                    sl_results[sta] = 'SKIPPED'
                    continue
                try:
                    ok = _create_sample_line(tr, slg, sta, lw, rw)
                    sl_results[sta] = ok
                    if ok:
                        created += 1
                except Exception as sl_err:
                    warnings.append(
                        'WARN: SampleLine at %.3f failed: %s' % (sta, str(sl_err))
                    )
                    sl_results[sta] = 'ERROR'

            # ---- Attempt SectionViews ----
            _try_section_views(tr, db, civdoc, slg_id, notes)

            tr.Commit()

    # ---- Write output CSV ----
    try:
        _write_output_csv(out_csv, station_rows, sl_results)
        notes.append('NOTE: Sections list written to %s' % out_csv)
    except Exception as csv_err:
        warnings.append('WARN: Could not write sections_list.csv: %s' % str(csv_err))

    msg = ('OK: M10 cross-sections — SampleLineGroup "%s" on alignment "%s", '
           '%d of %d sample lines created.'
           % (slg_name, align_name, created, len(station_rows)))

    if notes:
        msg += ' | ' + ' ; '.join(notes)
    if warnings:
        msg += ' | ' + ' ; '.join(warnings)

    return msg


# ---------------------------------------------------------------------------
# Dynamo entry point  (IN[0] = project.json path)
# ---------------------------------------------------------------------------
try:
    _cfg_path = str(IN[0])
    OUT = run(_cfg_path)
except Exception as e:
    OUT = 'ERROR: M10 exception: %s' % str(e)
