# -*- coding: utf-8 -*-
"""
M6 — DPR sheet manifest + NHAI PKG drawing numbers + title block attributes.
Dynamo inputs:
  IN[0] alignment name
  IN[1] output directory (sheets / PDF staging)
  IN[2] optional JSON string — full dpr config block
  IN[3] optional alignment_meta.json path
  IN[4] optional dpr_sheet_manifest.json output path
  IN[5] optional mass_haul_csv path
  IN[6] optional mass_haul_meta.json path
  IN[7] optional irc37_cache path
  IN[8] optional start_station (float string)
  IN[9] optional volume_sample_interval_m (float string)
"""
import clr
import os
import json
import math

clr.AddReference('AcMgd')
clr.AddReference('AcDbMgd')
clr.AddReference('AeccDbMgd')

from Autodesk.AutoCAD.ApplicationServices import Application
from Autodesk.AutoCAD.DatabaseServices import Transaction, OpenMode
from Autodesk.Civil.ApplicationServices import CivilApplication
from Autodesk.Civil.DatabaseServices import Alignment

_LOG = None
_DPR_CORE = None


def _ensure_log_utils():
    global _LOG
    if _LOG is not None:
        return _LOG
    here = os.path.dirname(__file__) if '__file__' in dir() else os.path.join(os.getcwd(), 'python')
    p = os.path.join(here, '_log_utils.py')
    g = {}
    if os.path.isfile(p):
        exec(compile(open(p).read(), p, 'exec'), g)
    _LOG = g
    return g


def _ensure_dpr_core():
    global _DPR_CORE
    if _DPR_CORE is not None:
        return _DPR_CORE
    here = os.path.dirname(__file__) if '__file__' in dir() else os.path.join(os.getcwd(), 'python')
    p = os.path.join(here, 'dpr_sheet_core.py')
    g = {}
    if os.path.isfile(p):
        exec(compile(open(p).read(), p, 'exec'), g)
    _DPR_CORE = g
    return g


def _load_json(path):
    if not path or not os.path.isfile(path):
        return {}
    with open(path, 'r') as f:
        return json.load(f)


def _alignment_length(align_id):
    try:
        return float(Alignment.GetAlignmentLength(align_id))
    except Exception:
        pass
    try:
        aln = Alignment.GetAlignment(align_id)
        return float(aln.Length)
    except Exception:
        return 0.0


def _apply_title_blocks(manifest, dpr_cfg, log_add, log):
    """Set title block attributes on layouts when block/tags exist."""
    attr_map = (dpr_cfg or {}).get('attribute_map') or {
        'drg_no': 'DRG_NO',
        'rev': 'REV',
        'ch_from': 'CHAINAGE_FROM',
        'ch_to': 'CHAINAGE_TO',
    }
    block_name = (dpr_cfg or {}).get('title_block_name') or ''
    applied = 0
    doc = Application.DocumentManager.MdiActiveDocument
    if doc is None:
        log_add(log, 'WARN', 'NO_DOC', 'No active document for title blocks.')
        return manifest

    db = doc.Database
    layout_mgr = db.LayoutDictionaryId
    sheet_by_id = {}
    for sh in manifest.get('sheets', []):
        sheet_by_id[sh.get('sheet_id', '')] = sh

    try:
        tr = doc.TransactionManager.StartTransaction()
        try:
            layout_dict = tr.GetObject(layout_mgr, OpenMode.ForRead)
            for layout_id in layout_dict:
                layout = tr.GetObject(layout_id, OpenMode.ForRead)
                lname = layout.LayoutName
                if lname.upper() in ('MODEL',):
                    continue
                sheet = sheet_by_id.get(lname)
                if sheet is None:
                    for sid, sh in sheet_by_id.items():
                        if sid and lname.find(sid) >= 0:
                            sheet = sh
                            break
                if sheet is None:
                    continue
                btr_id = layout.BlockTableRecordId
                btr = tr.GetObject(btr_id, OpenMode.ForRead)
                for ent_id in btr:
                    ent = tr.GetObject(ent_id, OpenMode.ForRead)
                    if ent.GetType().Name != 'BlockReference':
                        continue
                    if block_name and ent.Name != block_name:
                        continue
                    ent_upgrade = tr.GetObject(ent_id, OpenMode.ForWrite)
                    for att_id in ent_upgrade.AttributeCollection:
                        att = tr.GetObject(att_id, OpenMode.ForWrite)
                        tag = att.Tag.upper()
                        if tag == attr_map.get('drg_no', 'DRG_NO').upper():
                            att.TextString = sheet.get('drg_no', '')
                        elif tag == attr_map.get('rev', 'REV').upper():
                            att.TextString = sheet.get('revision', '')
                        elif tag == attr_map.get('ch_from', 'CHAINAGE_FROM').upper():
                            if 'ch_from' in sheet:
                                att.TextString = '%.3f' % sheet['ch_from']
                        elif tag == attr_map.get('ch_to', 'CHAINAGE_TO').upper():
                            if 'ch_to' in sheet:
                                att.TextString = '%.3f' % sheet['ch_to']
                    sheet['title_block_applied'] = True
                    applied += 1
            tr.Commit()
        except Exception as ex:
            tr.Abort()
            log_add(log, 'WARN', 'TITLE_BLOCK', str(ex))
    except Exception as ex:
        log_add(log, 'WARN', 'TITLE_BLOCK', str(ex))

    log_add(log, 'INFO', 'TITLE_BLOCKS', 'Applied attributes on %d layout(s).' % applied)
    return manifest


def _publish_stub(manifest, pdf_dir, log_add, log):
    """Stage PDF paths and optional AutoCAD SCRIPT for batch PUBLISH (manual run)."""
    if not pdf_dir:
        return manifest
    if not os.path.isdir(pdf_dir):
        try:
            os.makedirs(pdf_dir)
        except Exception as ex:
            log_add(log, 'WARN', 'PDF_DIR', str(ex))
            return manifest
    scr_lines = ['; ROADGEN M6 — batch publish helper (run SCRIPT command in Civil 3D)', '']
    for sh in manifest.get('sheets', []):
        sid = sh.get('sheet_id', 'sheet')
        pdf_path = os.path.join(pdf_dir, sid + '.pdf')
        sh['publish'] = {
            'status': 'pending',
            'path': pdf_path,
            'note': 'Run SCRIPT on publish.scr or use Sheet Set Manager; see template/README.md',
        }
        scr_lines.append('; Sheet %s — %s' % (sid, sh.get('drg_no', '')))
        scr_lines.append('-PUBLISH')
    scr_path = os.path.join(pdf_dir, 'publish.scr')
    try:
        with open(scr_path, 'w') as sf:
            sf.write('\n'.join(scr_lines) + '\n')
        manifest['publish_script'] = scr_path
        log_add(
            log,
            'INFO',
            'PDF_SCR',
            'Wrote %s — run SCRIPT in Civil 3D after layouts/view frames exist.' % scr_path,
        )
    except Exception as ex:
        log_add(log, 'WARN', 'PDF_SCR', str(ex))
    log_add(log, 'INFO', 'PDF_STUB', 'Publish paths staged under %s (manual step).' % pdf_dir)
    return manifest


def run(
    align_name,
    out_dir,
    dpr_json,
    meta_path='',
    manifest_path='',
    mass_haul_csv='',
    mass_haul_meta='',
    irc37_path='',
    start_station_s='',
    interval_s='',
):
    lu = _ensure_log_utils()
    dc = _ensure_dpr_core()
    log = lu['log_new']('M6')
    log_add = lu['log_add']
    out_wrap = lu['out_wrap']

    dpr = {}
    if dpr_json:
        try:
            dpr = json.loads(dpr_json) if isinstance(dpr_json, str) else dpr_json
        except Exception as ex:
            log_add(log, 'WARN', 'DPR_JSON', str(ex))

    civdoc = CivilApplication.ActiveDocument
    found = False
    align_len = 0.0
    for aid in civdoc.GetAlignmentIds():
        if Alignment.GetAlignmentName(aid) == align_name:
            found = True
            align_len = _alignment_length(aid)
            break

    if not found:
        log_add(log, 'WARN', 'ALIGN_MISSING', 'Alignment not found for view frames.')
    else:
        log_add(log, 'INFO', 'VIEW_FRAMES', 'Alignment found — extend ViewFrameGroup.Create when API confirmed.')

    L = dc.resolve_total_length_m(meta_path, mass_haul_csv)
    if L <= 0 and align_len > 0:
        L = align_len
        log_add(log, 'INFO', 'LENGTH', 'Using alignment API length %.1f m.' % L)

    try:
        start_station = float(start_station_s) if start_station_s not in ('', None) else 0.0
    except Exception:
        start_station = 0.0
    try:
        interval = float(interval_s) if interval_s not in ('', None) else 20.0
    except Exception:
        interval = 20.0

    n_sta = dc.resolve_n_stations(mass_haul_meta, mass_haul_csv, L, interval)
    layers = dc.load_irc37_layers(irc37_path)
    manifest = dc.build_sheet_manifest(dpr, L, n_sta, start_station, layers)

    xs_warn = dc.validate_xs_station_count(manifest, lambda lvl, code, msg: log_add(log, lvl, code, msg))

    if manifest_path:
        try:
            dc.write_manifest(manifest, manifest_path)
            log_add(log, 'INFO', 'MANIFEST', 'Wrote %s (%d sheets).' % (
                manifest_path, len(manifest.get('sheets', []))))
        except Exception as ex:
            log_add(log, 'WARN', 'MANIFEST', str(ex))

    pdf_dir = out_dir
    if out_dir and not out_dir.lower().endswith('pdf'):
        pdf_dir = os.path.join(out_dir, '..', 'pdf')
        pdf_dir = os.path.normpath(pdf_dir)
    manifest = _publish_stub(manifest, pdf_dir, log_add, log)

    if found:
        manifest = _apply_title_blocks(manifest, dpr, log_add, log)
        if manifest_path:
            try:
                dc.write_manifest(manifest, manifest_path)
            except Exception:
                pass

    counts = manifest.get('sheet_counts', {})
    for code, n in sorted(counts.items()):
        log_add(log, 'INFO', 'SHEET_COUNT', '%s: %d' % (code, n))

    data = {
        'manifest_path': manifest_path or '',
        'total_length_m': manifest.get('total_length_m', 0),
        'n_stations': manifest.get('n_stations', 0),
        'sheet_counts': counts,
        'xs_validation': manifest.get('xs_validation', {}),
        'xs_warn': xs_warn or '',
        'drawing_numbers': [{'sheet_type': s['code'], 'drg_no': s['drg_no'], 'sheet_id': s['sheet_id']}
                            for s in manifest.get('sheets', [])],
    }

    lines = [
        'M6 DPR sheet manifest.',
        'Alignment "%s" %s.' % (align_name, 'found' if found else 'MISSING'),
        'Length %.1f m; stations %d; PP=%d XS=%d.' % (
            manifest.get('total_length_m', 0),
            manifest.get('n_stations', 0),
            counts.get('PP', 0),
            counts.get('XS', 0),
        ),
    ]
    if manifest_path:
        lines.append('Manifest: ' + manifest_path)
    if out_dir:
        lines.append('Sheets folder: ' + str(out_dir))
        if not os.path.isdir(out_dir):
            try:
                os.makedirs(out_dir)
            except Exception as ex:
                log_add(log, 'WARN', 'OUT_DIR', str(ex))
    lines.append('Publish: manual PUBLISH or Sheet Set Manager (see template/README.md).')

    legacy = ('OK: ' if found else 'WARN: ') + ' | '.join(lines)
    log_add(log, 'INFO', 'M6_OK', legacy)
    return out_wrap(log, data, legacy_msg=legacy)


align_name = IN[0]
out_dir = IN[1] if len(IN) > 1 else ''
dpr_json = IN[2] if len(IN) > 2 else ''
meta_path = IN[3] if len(IN) > 3 else ''
manifest_path = IN[4] if len(IN) > 4 else ''
mass_haul_csv = IN[5] if len(IN) > 5 else ''
mass_haul_meta = IN[6] if len(IN) > 6 else ''
irc37_path = IN[7] if len(IN) > 7 else ''
start_station_s = IN[8] if len(IN) > 8 else ''
interval_s = IN[9] if len(IN) > 9 else ''

OUT = run(
    align_name, out_dir, dpr_json, meta_path, manifest_path,
    mass_haul_csv, mass_haul_meta, irc37_path, start_station_s, interval_s,
)
