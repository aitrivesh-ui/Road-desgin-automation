# -*- coding: utf-8 -*-
"""
M12 - Mass Haul Diagram.

Reads project volumes (from M4 volumes_csv) and station list (from M10
sections_list.csv, or generated from alignment geometry), distributes
volumes uniformly across stations, writes out/mass_haul.csv with cumulative
net earthwork, and creates a Polyline mass haul diagram in the active drawing
on layer C-MASSHAUL (color 6, magenta).

A zero-datum reference line and an MText title label are also added to the
drawing at diagram origin Point3d(0, -400, 0).

Dynamo inputs:
  IN[0] : str - absolute path to config/project.json

project.json keys consumed:
  paths.volumes_csv         -> out/volumes_demo.csv       (from M4)
  paths.sections_list_csv   -> out/sections_list.csv      (from M10, optional)
  paths.mass_haul_csv       -> out/mass_haul.csv          (output)
  design.section_interval_m -> 25.0                       (fallback station spacing)
  design.plan_scale         -> 1000                       (horizontal diagram scale)
  names.alignment           -> alignment name             (for geometry fallback)

Output:
  OUT : str - 'OK: ...' summary or 'ERROR: ...'
"""
import clr
clr.AddReference('AcMgd')
clr.AddReference('AcDbMgd')
clr.AddReference('AeccDbMgd')

import codecs, csv, os, json, math

from Autodesk.AutoCAD.ApplicationServices import Application
from Autodesk.AutoCAD.DatabaseServices import (
    Transaction, OpenMode, BlockTableRecord, BlockTable,
    ResultBuffer, TypedValue, Polyline, Polyline3d, Poly3dType,
    Point3dCollection, MText,
)
from Autodesk.AutoCAD.Geometry import Point2d, Point3d
from Autodesk.Civil.ApplicationServices import CivilApplication
from Autodesk.Civil.DatabaseServices import Alignment

# Alias so the spec-style import name works in docstrings/comments too
AcPolyline = Polyline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve(base, rel):
    """Resolve a project-relative path (forward slashes ok) to absolute."""
    return os.path.normpath(os.path.join(base, rel.replace('/', os.sep)))


def _find_alignment(tr, civdoc, name):
    """Return Alignment object (ForRead) for *name*, or None."""
    for aid in civdoc.GetAlignmentIds():
        a = tr.GetObject(aid, OpenMode.ForRead)
        if hasattr(a, 'Name') and a.Name == name:
            return a
    return None


def _ensure_layer(tr, db, name, color_idx=7):
    """Create layer *name* if it does not already exist."""
    from Autodesk.AutoCAD.DatabaseServices import LayerTable, LayerTableRecord
    from Autodesk.AutoCAD.Colors import Color, ColorMethod
    lt = tr.GetObject(db.LayerTableId, OpenMode.ForRead)
    if not lt.Has(name):
        ltr = LayerTableRecord()
        ltr.Name = name
        ltr.Color = Color.FromColorIndex(ColorMethod.ByAci, color_idx)
        lt2 = tr.GetObject(db.LayerTableId, OpenMode.ForWrite)
        lt2.Add(ltr)
        tr.AddNewlyCreatedDBObject(ltr, True)


def _read_volumes_csv(path):
    """
    Return (total_cut_m3, total_fill_m3) from the M4 volumes CSV.
    Reads the last data row (summary row written by M4).
    Returns (0.0, 0.0) on any error so the rest of the module still runs.
    """
    if not path or not os.path.isfile(path):
        return 0.0, 0.0
    try:
        with codecs.open(path, 'r', encoding='utf-8-sig') as fh:
            rows = list(csv.DictReader(fh))
        if not rows:
            return 0.0, 0.0
        last = rows[-1]
        cut  = float(last.get('cut_m3',  0) or 0)
        fill = float(last.get('fill_m3', 0) or 0)
        return cut, fill
    except Exception:
        return 0.0, 0.0


def _read_sections_stations(path):
    """
    Return sorted list of float station values from M10 sections_list.csv.
    Expected column: station_m  (or first numeric column).
    Returns empty list if the file does not exist or cannot be parsed.
    """
    stations = []
    if not path or not os.path.isfile(path):
        return stations
    try:
        with codecs.open(path, 'r', encoding='utf-8-sig') as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                # Try 'station_m' first, then first column value
                val = row.get('station_m', '').strip()
                if not val:
                    # fall back to first column
                    first_key = list(row.keys())[0] if row else ''
                    val = row.get(first_key, '').strip()
                try:
                    stations.append(float(val))
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass
    return sorted(set(stations))


def _generate_stations(start, end, interval):
    """
    Generate a list of stations from *start* to *end* (inclusive) with
    *interval* spacing.  Always includes start; snaps last point to end
    if not already there.
    """
    if interval <= 0.0:
        interval = 25.0
    stations = []
    sta = start
    while sta <= end + 1e-6:
        stations.append(round(sta, 4))
        sta += interval
    if stations and abs(stations[-1] - end) > 1e-6:
        stations.append(round(end, 4))
    return stations


def _build_mass_haul_data(stations, total_cut, total_fill):
    """
    Distribute *total_cut* and *total_fill* uniformly across the intervals
    defined by *stations*.  Returns a list of dicts:
      station_m, incremental_cut_m3, incremental_fill_m3, cumulative_net_m3
    The first row always has zero incremental and zero cumulative.
    """
    n_intervals = max(len(stations) - 1, 1)
    inc_cut  = total_cut  / float(n_intervals)
    inc_fill = total_fill / float(n_intervals)

    data = []
    cumulative = 0.0
    for i, sta in enumerate(stations):
        if i == 0:
            row_cut  = 0.0
            row_fill = 0.0
        else:
            row_cut  = inc_cut
            row_fill = inc_fill
        cumulative += row_cut - row_fill
        data.append({
            'station_m':           sta,
            'incremental_cut_m3':  row_cut,
            'incremental_fill_m3': row_fill,
            'cumulative_net_m3':   cumulative,
        })
    return data


def _write_mass_haul_csv(path, data):
    """Write mass haul data list to *path* as CSV."""
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with codecs.open(path, 'w', encoding='utf-8') as fh:
        writer = csv.writer(fh, lineterminator='\n')
        writer.writerow([
            'station_m',
            'incremental_cut_m3',
            'incremental_fill_m3',
            'cumulative_net_m3',
        ])
        for row in data:
            writer.writerow([
                '%.4f' % row['station_m'],
                '%.4f' % row['incremental_cut_m3'],
                '%.4f' % row['incremental_fill_m3'],
                '%.4f' % row['cumulative_net_m3'],
            ])


def _diagram_coordinates(data, origin_x, origin_y, h_scale, v_scale):
    """
    Convert mass haul data rows to diagram (x, y) tuples in drawing units.

    X axis  = station / h_scale  (stations scaled down)
    Y axis  = origin_y + cumulative_net / v_scale

    Returns list of (x, y) float tuples, one per data row.
    """
    pts = []
    for row in data:
        x = origin_x + row['station_m'] / h_scale
        y = origin_y + row['cumulative_net_m3'] / v_scale
        pts.append((x, y))
    return pts


def _add_polyline(tr, msp, pts, layer):
    """
    Add a 2-D Polyline through *pts* [(x,y),...] to *msp* on *layer*.
    Returns the ObjectId of the new entity.
    """
    pline = AcPolyline()
    for i, (x, y) in enumerate(pts):
        pline.AddVertexAt(i, Point2d(x, y), 0, 0, 0)
    pline.Layer = layer
    msp.AppendEntity(pline)
    tr.AddNewlyCreatedDBObject(pline, True)
    return pline.ObjectId


def _add_datum_line(tr, msp, origin_x, origin_y, total_length_drawing, h_scale, layer):
    """
    Draw a horizontal zero-datum reference line at *origin_y* spanning
    the full diagram width.
    """
    x_end = origin_x + total_length_drawing / h_scale
    pline = AcPolyline()
    pline.AddVertexAt(0, Point2d(origin_x, origin_y), 0, 0, 0)
    pline.AddVertexAt(1, Point2d(x_end,    origin_y), 0, 0, 0)
    pline.Layer = layer
    msp.AppendEntity(pline)
    tr.AddNewlyCreatedDBObject(pline, True)


def _add_label(tr, msp, db, origin_x, origin_y, layer, total_cut, total_fill):
    """
    Place an MText title block for the mass haul diagram.
    Positioned slightly above the diagram origin.
    """
    net = total_cut - total_fill
    content  = '{\\C6;MASS HAUL DIAGRAM}\\P'
    content += '{\\C7;'
    content += 'Total Cut  : %.1f m3\\P' % total_cut
    content += 'Total Fill : %.1f m3\\P' % total_fill
    content += 'Net        : %.1f m3 (%s)\\P' % (
        abs(net),
        'Cut surplus' if net >= 0 else 'Fill deficit'
    )
    content += '}'

    mt = MText()
    mt.Location   = Point3d(origin_x, origin_y + 10.0, 0.0)
    mt.Layer      = layer
    mt.TextHeight = 2.5
    mt.Width      = 120.0
    mt.Contents   = content
    msp.AppendEntity(mt)
    tr.AddNewlyCreatedDBObject(mt, True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(project_json):
    if not os.path.isfile(project_json):
        return 'ERROR: project.json not found: %s' % project_json

    try:
        with codecs.open(project_json, 'r', encoding='utf-8-sig') as fj:
            cfg = json.loads(fj.read())
    except Exception as ex:
        return 'ERROR: Cannot parse project.json: %s' % str(ex)

    base = os.path.dirname(os.path.abspath(project_json))
    root = os.path.normpath(os.path.join(base, '..'))

    paths  = cfg.get('paths',  {})
    names  = cfg.get('names',  {})
    design = cfg.get('design', {})

    # --- resolve paths -------------------------------------------------------
    volumes_csv_rel      = paths.get('volumes_csv',       'out/volumes.csv')
    sections_list_csv_rel = paths.get('sections_list_csv', 'out/sections_list.csv')
    mass_haul_csv_rel    = paths.get('mass_haul_csv',     'out/mass_haul.csv')

    volumes_csv      = _resolve(root, volumes_csv_rel)
    sections_csv     = _resolve(root, sections_list_csv_rel)
    mass_haul_csv    = _resolve(root, mass_haul_csv_rel)

    align_name       = names.get('alignment', 'ALIGN')
    section_interval = float(design.get('section_interval_m', 25.0))
    plan_scale       = float(design.get('plan_scale', 1000.0))

    # --- read volumes from M4 ------------------------------------------------
    total_cut, total_fill = _read_volumes_csv(volumes_csv)

    # --- build station list --------------------------------------------------
    stations = _read_sections_stations(sections_csv)

    if not stations:
        # Fallback: get alignment geometry from Civil 3D
        doc    = Application.DocumentManager.MdiActiveDocument
        db     = doc.Database
        civdoc = CivilApplication.ActiveDocument
        align_start = 0.0
        align_end   = 500.0   # conservative default

        try:
            with db.TransactionManager.StartTransaction() as tr_peek:
                align_tmp = _find_alignment(tr_peek, civdoc, align_name)
                if align_tmp is not None:
                    align_start = align_tmp.StartingStation
                    align_end   = align_tmp.EndingStation
                tr_peek.Abort()
        except Exception:
            pass

        stations = _generate_stations(align_start, align_end, section_interval)

    if not stations:
        return 'ERROR: No stations available for mass haul diagram.'

    # --- build mass haul data rows -------------------------------------------
    data = _build_mass_haul_data(stations, total_cut, total_fill)

    # --- write output CSV ----------------------------------------------------
    try:
        _write_mass_haul_csv(mass_haul_csv, data)
    except Exception as ex_csv:
        return 'ERROR: Cannot write mass haul CSV: %s' % str(ex_csv)

    # --- diagram geometry parameters -----------------------------------------
    # Diagram origin is at (0, -400) in model space, below road alignment area
    ORIGIN_X = 0.0
    ORIGIN_Y = -400.0

    # Horizontal scale: station metres -> drawing units
    h_scale = plan_scale if plan_scale > 0.0 else 1000.0

    # Vertical scale: volumes -> drawing units
    # Target roughly 50 drawing units of amplitude for the diagram
    # v_scale = total_cut / 10, but guard against zero
    max_abs_cumulative = max(
        (abs(row['cumulative_net_m3']) for row in data),
        default=1.0
    ) or 1.0
    v_scale = max_abs_cumulative / 50.0 if max_abs_cumulative > 0.0 else 1.0

    diagram_pts = _diagram_coordinates(data, ORIGIN_X, ORIGIN_Y, h_scale, v_scale)

    # Span of the alignment in drawing units
    total_sta_length = stations[-1] - stations[0]

    # --- draw in AutoCAD / Civil 3D ------------------------------------------
    doc    = Application.DocumentManager.MdiActiveDocument
    db     = doc.Database
    civdoc = CivilApplication.ActiveDocument

    LAYER = 'C-MASSHAUL'

    with doc.LockDocument():
        with db.TransactionManager.StartTransaction() as tr:
            bt  = tr.GetObject(db.BlockTableId, OpenMode.ForRead)
            msp = tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite)

            # C-MASSHAUL layer — color 6 (magenta)
            _ensure_layer(tr, db, LAYER, color_idx=6)

            # Mass haul curve polyline
            if len(diagram_pts) >= 2:
                _add_polyline(tr, msp, diagram_pts, LAYER)

            # Zero-datum reference line
            _add_datum_line(tr, msp, ORIGIN_X, ORIGIN_Y, total_sta_length, h_scale, LAYER)

            # Title and statistics label
            _add_label(tr, msp, db, ORIGIN_X, ORIGIN_Y, LAYER, total_cut, total_fill)

            tr.Commit()

    # --- summary statistics --------------------------------------------------
    max_cut_sta  = max(data, key=lambda r: r['cumulative_net_m3'])
    min_fill_sta = min(data, key=lambda r: r['cumulative_net_m3'])
    net_vol      = total_cut - total_fill

    return (
        'OK: M12 mass haul - %d stations; '
        'cut=%.1f m3 fill=%.1f m3 net=%.1f m3; '
        'peak surplus STA %.1f; peak deficit STA %.1f; '
        'diagram layer=%s; CSV -> %s'
    ) % (
        len(data),
        total_cut, total_fill, net_vol,
        max_cut_sta['station_m'],
        min_fill_sta['station_m'],
        LAYER,
        mass_haul_csv,
    )


# ---------------------------------------------------------------------------
# Dynamo entry point
# ---------------------------------------------------------------------------

try:
    _project_json = IN[0]
    OUT = run(_project_json)
except Exception as _ex_top:
    OUT = 'ERROR: Unhandled exception in M12: %s' % str(_ex_top)
