# -*- coding: utf-8 -*-
"""
M3 — Corridor baseline regions from section_widths.csv + IRC:37 thickness cache.
Dynamo inputs:
  IN[0] : str — path to section_widths.csv
  IN[1] : str — corridor name
  IN[2] : str — default assembly name
  IN[3] : str — optional JSON design.irc37 {cbr_pct, msa, climate, apply_to_assembly}
  IN[4] : str — optional irc37_cache JSON output path
  IN[5] : str — optional alignment_meta.json (clamp end_sta)
  IN[6] : str — optional assembly_thickness_report.csv path
  IN[7] : str — optional section_width_report.csv path
"""
import clr
import csv
import codecs
import os
import json

clr.AddReference('AcMgd')
clr.AddReference('AcDbMgd')
clr.AddReference('AeccDbMgd')

from Autodesk.AutoCAD.ApplicationServices import Application
from Autodesk.AutoCAD.DatabaseServices import OpenMode, Transaction
from Autodesk.Civil.ApplicationServices import CivilApplication
from Autodesk.Civil.DatabaseServices import Corridor

_LOG = None

ASSEMBLY_LAYER_PARAMS = (
    ('GSB', 'Subbase', 'Depth'),
    ('WMM', 'Base', 'Depth'),
    ('DBM', 'Pavement', 'Depth'),
    ('BC', 'Pavement1', 'Depth'),
)


def _ensure_log_utils():
    global _LOG
    if _LOG is not None:
        return _LOG
    here = os.path.dirname(__file__) if '__file__' in dir() else os.path.join(os.getcwd(), 'python')
    g = {}
    for mod in ('_log_utils', 'irc37_engine'):
        p = os.path.join(here, mod + '.py')
        if os.path.isfile(p):
            exec(compile(open(p).read(), p, 'exec'), g)
    _LOG = g
    return g


def _read_csv(path):
    rows = []
    with codecs.open(path, 'r', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def _read_alignment_meta(path):
    if not path or not os.path.isfile(path):
        return None
    with codecs.open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _write_csv_report(path, headers, data_rows):
    if not path:
        return
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with codecs.open(path, 'w', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(headers)
        for row in data_rows:
            w.writerow(row)


def _write_thickness_report(path, design, assembly_name, apply_to_assembly):
    if not path or not design or design.get('empty'):
        return
    layers_mm = design.get('layers_mm') or {}
    rows = []
    for layer, subasm, param in ASSEMBLY_LAYER_PARAMS:
        mm = layers_mm.get(layer, '')
        status = 'pending_manual'
        if apply_to_assembly:
            status = 'apply_to_assembly_requested'
        rows.append([layer, mm, '%s.%s' % (subasm, param), assembly_name, status])
    _write_csv_report(path, ['layer', 'design_mm', 'assembly_param', 'assembly_name', 'status'], rows)


def _write_width_report(path, rows, default_assembly):
    if not path:
        return
    out = []
    for r in rows:
        rid = (r.get('region_id') or '').strip()
        asm = (r.get('assembly_name') or '').strip() or default_assembly
        lane = r.get('lane_width_m', '')
        sl = r.get('shoulder_l_m', '')
        sr = r.get('shoulder_r_m', '')
        if lane or sl or sr:
            out.append([rid, asm, lane, sl, sr, 'report_only', 'Subassembly width API not applied'])
    if out:
        _write_csv_report(
            path,
            ['region_id', 'assembly_name', 'lane_width_m', 'shoulder_l_m', 'shoulder_r_m', 'status', 'note'],
            out,
        )


def _region_exists(regions, region_id):
    for i in range(regions.Count):
        reg = regions[i]
        name = getattr(reg, 'RegionName', None) or getattr(reg, 'Name', None)
        if name and str(name) == region_id:
            return i
    return -1


def _remove_region(regions, region_id):
    idx = _region_exists(regions, region_id)
    if idx < 0:
        return False
    try:
        regions.Remove(regions[idx])
        return True
    except Exception:
        try:
            regions.RemoveAt(idx)
            return True
        except Exception:
            return False


def _try_apply_assembly_thickness(db, assembly_name, design, log, log_add):
    if not design or design.get('empty'):
        return False
    layers_mm = design.get('layers_mm') or {}
    try:
        from Autodesk.Civil.DatabaseServices import Assembly
    except Exception:
        log_add(log, 'WARN', 'IRC37_ASM_API', 'Assembly type not available for thickness apply.')
        return False
    applied = 0
    with db.TransactionManager.StartTransaction() as tr:
        civdoc = CivilApplication.ActiveDocument
        for aid in civdoc.AssemblyCollection.GetAssemblyIds():
            asm = tr.GetObject(aid, OpenMode.ForRead)
            if Assembly.GetAssemblyName(aid) != assembly_name:
                continue
            asm_w = tr.GetObject(aid, OpenMode.ForWrite)
            for layer, subasm_code, param_name in ASSEMBLY_LAYER_PARAMS:
                if layer not in layers_mm:
                    continue
                depth_m = float(layers_mm[layer]) / 1000.0
                try:
                    asm_w.SetParameter(subasm_code, param_name, depth_m)
                    applied += 1
                    log_add(
                        log,
                        'INFO',
                        'IRC37_ASM_SET',
                        '%s %s=%.3f m' % (layer, param_name, depth_m),
                    )
                except Exception as ex:
                    log_add(
                        log,
                        'WARN',
                        'IRC37_ASM_PARAM',
                        '%s.%s: %s' % (subasm_code, param_name, ex),
                    )
            tr.Commit()
            break
    return applied > 0


def run(
    csv_path,
    corridor_name,
    default_assembly,
    irc37_json,
    irc37_cache_path,
    alignment_meta_path='',
    thickness_report_path='',
    width_report_path='',
):
    lu = _ensure_log_utils()
    log = lu['log_new']('M3')
    log_add = lu['log_add']
    out_wrap = lu['out_wrap']
    safe_civil = lu.get('safe_civil')
    data = {'regions': 0, 'irc37': {}, 'regions_replaced': 0}

    if not os.path.isfile(csv_path):
        log_add(log, 'ERROR', 'CSV_NOT_FOUND', 'CSV not found: ' + str(csv_path))
        return out_wrap(log, data, legacy_msg='ERROR: CSV not found: ' + str(csv_path))

    rows = _read_csv(csv_path)
    meta = _read_alignment_meta(alignment_meta_path)
    align_len = None
    if meta and meta.get('total_length_m') is not None:
        align_len = float(meta['total_length_m'])

    apply_to_assembly = False
    if irc37_json:
        try:
            spec = json.loads(irc37_json) if isinstance(irc37_json, str) else irc37_json
            apply_to_assembly = bool(spec.get('apply_to_assembly', False))
            if lu.get('irc37_design'):
                design = lu['irc37_design'](
                    spec.get('cbr_pct', 6),
                    spec.get('msa', 10),
                    spec.get('climate', 'moderate'),
                )
                if design and not design.get('empty'):
                    data['irc37'] = design
                    snapped = design.get('snapped') or {}
                    msg = 'IRC:37 %s' % json.dumps(design.get('layers_mm') or {})
                    if design.get('fallback'):
                        log_add(log, 'WARN', 'IRC37_FALLBACK', 'Nearest catalogue key used: ' + str(snapped.get('key')))
                    log_add(log, 'INFO', 'IRC37_OK', msg)
                    cbr_in = float(design.get('cbr_pct', 0))
                    msa_in = float(design.get('msa', 0))
                    cbr_s = float(snapped.get('cbr_pct', cbr_in))
                    msa_s = float(snapped.get('msa', msa_in))
                    if abs(cbr_in - cbr_s) > 1.0 or abs(msa_in - msa_s) > 15.0:
                        log_add(
                            log,
                            'WARN',
                            'IRC37_SNAP',
                            'Input CBR/msa snapped (%.1f,%.1f) -> (%.1f,%.1f).'
                            % (cbr_in, msa_in, cbr_s, msa_s),
                        )
                    _write_thickness_report(
                        thickness_report_path,
                        design,
                        default_assembly,
                        apply_to_assembly,
                    )
                    if irc37_cache_path:
                        d = os.path.dirname(irc37_cache_path)
                        if d and not os.path.isdir(d):
                            os.makedirs(d)
                        with codecs.open(irc37_cache_path, 'w', encoding='utf-8') as f:
                            f.write(json.dumps(design, indent=2))
                            f.write('\n')
                else:
                    log_add(log, 'WARN', 'IRC37_MISS', 'No catalogue match for CBR/msa/climate.')
        except Exception as ex:
            log_add(log, 'WARN', 'IRC37_FAIL', str(ex))

    _write_width_report(width_report_path, rows, default_assembly)
    width_rows = [r for r in rows if r.get('lane_width_m') or r.get('shoulder_l_m') or r.get('shoulder_r_m')]
    if width_rows:
        log_add(
            log,
            'WARN',
            'M3_WIDTH_REPORT',
            '%d region(s) with width targets — see section_width_report (API not applied).'
            % len(width_rows),
        )

    doc = Application.DocumentManager.MdiActiveDocument
    db = doc.Database
    civdoc = CivilApplication.ActiveDocument

    cor_id = None
    for cid in civdoc.CorridorCollection.GetCorridorIds():
        if Corridor.GetCorridorName(cid) == corridor_name:
            cor_id = cid
            break
    if cor_id is None:
        log_add(log, 'ERROR', 'CORRIDOR_MISSING', 'Corridor not found: ' + corridor_name)
        return out_wrap(log, data, legacy_msg='ERROR: Corridor not found: ' + corridor_name)

    if apply_to_assembly and data.get('irc37'):
        try:
            _try_apply_assembly_thickness(db, default_assembly, data['irc37'], log, log_add)
        except Exception as ex:
            log_add(log, 'WARN', 'IRC37_ASM_FAIL', str(ex))

    def _apply_regions():
        replaced = 0
        added = 0
        with doc.LockDocument():
            with db.TransactionManager.StartTransaction() as tr:
                cor = tr.GetObject(cor_id, OpenMode.ForWrite)
                if cor.Baselines.Count < 1:
                    raise Exception('Corridor has no baselines.')
                baseline = cor.Baselines[0]
                regions = baseline.BaselineRegions
                for r in rows:
                    rid = r['region_id'].strip()
                    asm = (r.get('assembly_name') or '').strip() or default_assembly
                    s0 = float(r['start_sta'])
                    s1 = float(r['end_sta'])
                    if align_len is not None and s1 > align_len:
                        log_add(
                            log,
                            'WARN',
                            'REGION_CLAMP',
                            'region %s end_sta %.3f clamped to alignment length %.3f.'
                            % (rid, s1, align_len),
                        )
                        s1 = align_len
                    if s0 >= s1:
                        log_add(log, 'ERROR', 'REGION_STA', 'region %s: start_sta must be < end_sta.' % rid)
                        continue
                    if _remove_region(regions, rid):
                        replaced += 1
                    regions.Add(rid, asm, s0, s1)
                    added += 1
                    if r.get('region_breaks'):
                        log_add(log, 'INFO', 'REGION_BREAK', 'region_breaks=%s on %s' % (r['region_breaks'], rid))
                cor.Rebuild()
                tr.Commit()
        return added, replaced

    if safe_civil:
        result, err = safe_civil(log, 'BaselineRegions.Add', _apply_regions, 'Region add failed', module_id='M3')
        if err:
            return out_wrap(log, data, legacy_msg='ERROR: BaselineRegions.Add failed: ' + str(err))
        n, replaced = result
    else:
        try:
            n, replaced = _apply_regions()
        except Exception as ex:
            log_add(log, 'ERROR', 'CIVIL_API_FAIL', str(ex), api='BaselineRegions.Add')
            return out_wrap(log, data, legacy_msg='ERROR: BaselineRegions.Add failed: ' + str(ex))

    data['regions'] = n
    data['regions_replaced'] = replaced
    legacy = 'OK: %d corridor region(s) on "%s" (%d replaced).' % (n, corridor_name, replaced)
    log_add(log, 'INFO', 'M3_OK', legacy)
    return out_wrap(log, data, legacy_msg=legacy)


csv_path = IN[0]
corridor_name = IN[1]
default_assembly = IN[2] if len(IN) > 2 else 'BasicLaneAssembly'
irc37_json = IN[3] if len(IN) > 3 else ''
irc37_cache_path = IN[4] if len(IN) > 4 else ''
alignment_meta_path = IN[5] if len(IN) > 5 else ''
thickness_report_path = IN[6] if len(IN) > 6 else ''
width_report_path = IN[7] if len(IN) > 7 else ''

OUT = run(
    csv_path,
    corridor_name,
    default_assembly,
    irc37_json,
    irc37_cache_path,
    alignment_meta_path,
    thickness_report_path,
    width_report_path,
)
