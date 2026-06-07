# -*- coding: utf-8 -*-
"""IRC:35 marking catalogue, geometry, and no-passing helpers (IronPython 2.7)."""
import math
import json
import codecs
import os
import csv

XDATA_APP_DEFAULT = 'IRC35_ROAD_MARK_V2'
SAMPLE_INTERVAL_M = 0.5
_CATALOGUE = None


def default_catalogue_path():
    here = os.path.dirname(__file__) if '__file__' in dir() else os.path.join(os.getcwd(), 'python')
    return os.path.normpath(os.path.join(here, '..', 'config', 'irc35_markings_catalogue.json'))


def load_catalogue(path=None):
    global _CATALOGUE
    if _CATALOGUE is not None and (path is None or path == ''):
        return _CATALOGUE
    p = path or default_catalogue_path()
    if not os.path.isfile(p):
        raise IOError('IRC35 catalogue not found: ' + str(p))
    with codecs.open(p, 'r', encoding='utf-8') as f:
        _CATALOGUE = json.load(f)
    return _CATALOGUE


def validate_mark_type(code, catalogue=None):
    cat = catalogue or load_catalogue()
    key = (code or '').strip().upper()
    types = cat.get('mark_types') or {}
    if key in types:
        return key, None
    return None, "mark_type '%s' not in IRC35 catalogue (valid: %s)" % (
        code,
        ', '.join(sorted(types.keys())),
    )


def validate_material(mat, catalogue=None):
    cat = catalogue or load_catalogue()
    key = (mat or 'thermoplastic').strip().lower()
    valid = cat.get('valid_materials') or list((cat.get('mat_layer') or {}).keys())
    if key in valid:
        return key, None
    return None, "material '%s' not valid (use: %s)" % (mat, ', '.join(valid))


def mark_spec(mark_type, catalogue=None):
    cat = catalogue or load_catalogue()
    mt, err = validate_mark_type(mark_type, cat)
    if err:
        return None, err
    spec = dict((cat.get('mark_types') or {})[mt])
    spec['code'] = mt
    return spec, None


def layer_for_mark(material, mark_type, catalogue=None):
    cat = catalogue or load_catalogue()
    mat, _ = validate_material(material, cat)
    spec, err = mark_spec(mark_type, cat)
    if err:
        return None, err
    base = (cat.get('mat_layer') or {}).get(mat, 'C-ROAD-MARK-THERMO')
    suffix = spec.get('layer_suffix', mark_type)
    return '%s-%s' % (base, suffix), None


def read_curve_table_csv(path):
    if not path or not os.path.isfile(path):
        return []
    rows = []
    with codecs.open(path, 'r', encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def build_nopassing_intervals(curve_rows, total_len, default_speed_kph=80, catalogue=None):
    """IRC:66 OSD vs radius — zones where R < osd/2 (handbook logic)."""
    cat = catalogue or load_catalogue()
    osd_table = cat.get('osd_kph') or {'80': 370, '60': 270, '50': 235, '100': 470}
    buffer_m = float(cat.get('nopass_buffer_m', 60))
    zones = []
    for cv in curve_rows:
        try:
            r = float(cv.get('radius_m', 0) or 0)
            if r <= 0:
                continue
            sta = float(cv.get('station_m', 0) or 0)
            spd = float(cv.get('design_speed_kph', default_speed_kph) or default_speed_kph)
            vd = int(round(spd / 10.0) * 10)
            if vd not in osd_table:
                keys = sorted([int(k) for k in osd_table.keys()])
                vd = min(keys, key=lambda k: abs(k - vd))
            osd = float(osd_table.get(str(vd), osd_table.get(vd, 370)))
            if r < osd / 2.0:
                z0 = max(0.0, sta - buffer_m)
                z1 = min(float(total_len), sta + buffer_m)
                if z1 > z0:
                    zones.append((z0, z1))
        except Exception:
            pass
    return merge_intervals(zones)


def merge_intervals(intervals):
    if not intervals:
        return []
    ivs = sorted([(float(a), float(b)) for a, b in intervals if b > a])
    merged = [ivs[0]]
    for s, e in ivs[1:]:
        ps, pe = merged[-1]
        if s <= pe + 1e-6:
            merged[-1] = (ps, max(pe, e))
        else:
            merged.append((s, e))
    return merged


def overlap_intervals(a0, a1, zones):
    """Split [a0,a1] into (chain_from, chain_to, mark_type) segments given no-pass zones."""
    spans = [(a0, a1, None)]
    for z0, z1 in zones:
        new_spans = []
        for s0, s1, forced in spans:
            if forced == 'CL-DY':
                new_spans.append((s0, s1, forced))
                continue
            if s1 <= z0 or s0 >= z1:
                new_spans.append((s0, s1, forced))
                continue
            if s0 < z0:
                new_spans.append((s0, min(s1, z0), forced))
            new_spans.append((max(s0, z0), min(s1, z1), 'CL-DY'))
            if s1 > z1:
                new_spans.append((max(s0, z1), s1, forced))
        spans = new_spans
    out = []
    for s0, s1, forced in spans:
        if s1 - s0 > 0.05:
            out.append((s0, s1, forced))
    return out


def build_segs(point3d_list):
    segs = []
    cum = 0.0
    for i in range(len(point3d_list) - 1):
        a = point3d_list[i]
        b = point3d_list[i + 1]
        d = math.hypot(b.X - a.X, b.Y - a.Y, b.Z - a.Z) if hasattr(b, 'Z') else math.hypot(b.X - a.X, b.Y - a.Y)
        if d > 1e-6:
            segs.append((cum, d, a, b))
            cum += d
    return segs, cum


def pt_at(segs, dist):
    for cs, sd, a, b in segs:
        if dist <= cs + sd + 1e-6:
            t = max(0.0, min(1.0, (dist - cs) / sd))
            if hasattr(a, 'Z'):
                from Autodesk.AutoCAD.Geometry import Point3d
                return Point3d(
                    a.X + (b.X - a.X) * t,
                    a.Y + (b.Y - a.Y) * t,
                    a.Z + (b.Z - a.Z) * t,
                )
            from Autodesk.AutoCAD.Geometry import Point3d
            return Point3d(a.X + (b.X - a.X) * t, a.Y + (b.Y - a.Y) * t, 0.0)
    if segs:
        return segs[-1][3]
    return None


def intervals(total, dash, gap, off=0.0):
    if dash == 0 or dash is None:
        return [(float(off), float(total))]
    ivs = []
    pos = float(off)
    cyc = float(dash) + float(gap)
    while pos < total:
        e = min(pos + float(dash), total)
        if e - pos > 0.05:
            ivs.append((pos, e))
        pos += cyc
    return ivs


def make_solid(tr, msp, pa, pb, w, th, ci, layer):
    from Autodesk.AutoCAD.DatabaseServices import Solid3d
    from Autodesk.AutoCAD.Geometry import Point3d, Vector3d, Matrix3d

    v = Vector3d(pb.X - pa.X, pb.Y - pa.Y, pb.Z - pa.Z)
    L = v.Length
    if L < 0.01:
        return None
    vn = v.GetNormal()
    up = Vector3d.ZAxis if abs(vn.Z) < 0.99 else Vector3d.XAxis
    right = vn.CrossProduct(up).GetNormal()
    up2 = right.CrossProduct(vn).GetNormal()
    mid = Point3d((pa.X + pb.X) / 2.0, (pa.Y + pb.Y) / 2.0, (pa.Z + pb.Z) / 2.0)
    s = Solid3d()
    s.CreateBox(L, w, th)
    s.TransformBy(
        Matrix3d.AlignCoordinateSystem(
            Point3d.Origin,
            Vector3d.XAxis,
            Vector3d.YAxis,
            Vector3d.ZAxis,
            mid,
            vn,
            right,
            up2,
        )
    )
    s.Layer = layer
    s.ColorIndex = int(ci)
    msp.AppendEntity(s)
    tr.AddNewlyCreatedDBObject(s, True)
    return s.ObjectId


def del_old_by_source_key(tr, msp, source_key, xdata_app):
    for eid in msp:
        try:
            ent = tr.GetObject(eid, OpenMode.ForRead)
            xd = ent.GetXDataForApplication(xdata_app)
        except Exception:
            continue
        if xd is None:
            continue
        matched = False
        for tv in xd:
            if tv.TypeCode == 1000 and str(tv.Value) == source_key:
                matched = True
                break
        if matched:
            ent.UpgradeOpen()
            ent.Erase()


def sample_alignment_offset(align, s0, s1, offset_m, interval, dense_fn):
    if dense_fn:
        pairs = dense_fn(align, s0, s1, interval)
        return [align.PointLocation(sta, float(offset_m)) for sta, _ in pairs]
    pts = []
    sta = float(s0)
    while sta <= float(s1) + 1e-6:
        try:
            pts.append(align.PointLocation(sta, float(offset_m)))
        except Exception:
            pass
        sta += float(interval)
    if pts and abs(sta - float(s1) - float(interval)) > 1e-3:
        try:
            pts.append(align.PointLocation(float(s1), float(offset_m)))
        except Exception:
            pass
    return pts


def place_mark_solid_run(tr, msp, pts, mark_type, material, source_key, xdata_app, catalogue=None):
    """Place dashed/solid strip solids along sampled points; return area, length."""
    from Autodesk.AutoCAD.DatabaseServices import BooleanOperationType, OpenMode, ResultBuffer, TypedValue

    spec, err = mark_spec(mark_type, catalogue)
    if err:
        return 0.0, 0.0, 0, err
    layer, lerr = layer_for_mark(material, mark_type, catalogue)
    if lerr:
        return 0.0, 0.0, 0, lerr
    if len(pts) < 2:
        return 0.0, 0.0, 0, 'fewer than 2 sample points'

    dash = float(spec.get('dash_m', 0))
    gap = float(spec.get('gap_m', 0))
    w = float(spec.get('width_m', 0.1))
    th = float(spec.get('thick_m', 0.006))
    ci = int(spec.get('color_idx', 7))

    segs, total = build_segs(pts)
    if total < 0.05:
        return 0.0, 0.0, 0, 'span too short'

    ivs = intervals(total, dash, gap, 0.0)
    if not ivs:
        return 0.0, 0.0, 0, 'no dash intervals'

    del_old_by_source_key(tr, msp, source_key, xdata_app)
    sids = []
    mlen = 0.0
    area = 0.0
    for s, e in ivs:
        pa = pt_at(segs, s)
        pb = pt_at(segs, e)
        if pa is None or pb is None:
            continue
        sid = make_solid(tr, msp, pa, pb, w, th, ci, layer)
        if sid:
            sids.append(sid)
            seg_len = e - s
            mlen += seg_len
            area += seg_len * w

    if not sids:
        return 0.0, 0.0, 0, 'no solids created'

    base = tr.GetObject(sids[0], OpenMode.ForWrite)
    for i in range(1, len(sids)):
        tool = tr.GetObject(sids[i], OpenMode.ForWrite)
        try:
            base.BooleanOperation(BooleanOperationType.BoolUnite, tool)
            tool.Erase()
        except Exception:
            pass

    rb = ResultBuffer(
        TypedValue(1001, xdata_app),
        TypedValue(1000, mark_type),
        TypedValue(1000, source_key),
        TypedValue(1000, material),
        TypedValue(1040, area),
        TypedValue(1040, mlen),
    )
    base.XData = rb
    return area, mlen, len(ivs), None


def write_marking_qty_csv(path, rows):
    if not path:
        return
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    headers = ['mark_type', 'material', 'length_m', 'area_m2', 'chainage_from', 'chainage_to']
    with codecs.open(path, 'w', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in rows:
            w.writerow([
                r.get('mark_type', ''),
                r.get('material', ''),
                '%.3f' % float(r.get('length_m', 0)),
                '%.3f' % float(r.get('area_m2', 0)),
                '%.3f' % float(r.get('chainage_from', 0)),
                '%.3f' % float(r.get('chainage_to', 0)),
            ])
