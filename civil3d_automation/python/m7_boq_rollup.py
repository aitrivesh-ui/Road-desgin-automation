# -*- coding: utf-8 -*-
"""
M7 — BOQ CSV rollup with state SOR rates and tax abstract rows.
Dynamo inputs:
  IN[0] volumes CSV, IN[1] marking layer prefix, IN[2] signage layer, IN[3] payitems,
  IN[4] BOQ out, IN[5] corridor name, IN[6] state_code, IN[7] state_sor_rates.json path
  IN[8] marking_quantities CSV (optional)
  IN[9] irc37_cache JSON (optional)
  IN[10] paved_area_m2 (optional)
  IN[11] signage_counts JSON (optional)
  IN[12] boq_abstract_csv (optional — separate abstract when set)
"""
import clr
import csv
import codecs
import os
import math
import json
import sys

clr.AddReference('AcMgd')
clr.AddReference('AcDbMgd')
clr.AddReference('AeccDbMgd')

from Autodesk.AutoCAD.ApplicationServices import Application
from Autodesk.AutoCAD.DatabaseServices import (
    OpenMode, Transaction, BlockTableRecord, Solid3d, BlockReference,
)
from Autodesk.Civil.ApplicationServices import CivilApplication

MARK_XDATA = 'IRC35_ROAD_MARK_V2'
MARK_XDATA_LEGACY = 'ROAD_MARK_SRC'
SIGN_XDATA = 'ROAD_SIGN_CSV'
_SIGN_BLOCK_ALIASES = None
_LOG = None
_BC = None


def _boq_core():
    global _BC
    if _BC is not None:
        return _BC
    here = os.path.dirname(__file__) if '__file__' in dir() else os.path.join(os.getcwd(), 'python')
    if here not in sys.path:
        sys.path.insert(0, here)
    import boq_core
    _BC = boq_core
    return _BC


def _load_sign_block_aliases():
    global _SIGN_BLOCK_ALIASES
    if _SIGN_BLOCK_ALIASES is not None:
        return _SIGN_BLOCK_ALIASES
    aliases = {
        'SGN_W1_CURVE': 'SGN_W1',
        'SGN_W2_CURVE': 'SGN_W2',
        'SGN_KM_POST': 'SGN_KM_POST',
        'SGN_DELINEATOR': 'SGN_DELINEATOR',
        'SGN_GUARDRAIL_W_BEAM': 'SGN_GUARDRAIL',
        'SGN_STOP': 'SGN_STOP',
        'SGN_SPEED_50': 'SGN_SPEED_50',
    }
    here = os.path.dirname(__file__) if '__file__' in dir() else os.path.join(os.getcwd(), 'python')
    cat_path = os.path.normpath(os.path.join(here, '..', 'config', 'irc67_signage_catalogue.json'))
    if os.path.isfile(cat_path):
        try:
            with codecs.open(cat_path, 'r', encoding='utf-8') as f:
                cat = json.load(f)
            for sign in (cat.get('signs') or {}).values():
                bn = sign.get('block_name')
                pk = sign.get('payitem_key')
                if bn and pk:
                    aliases[bn] = pk
        except Exception:
            pass
    _SIGN_BLOCK_ALIASES = aliases
    return aliases


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


def _marking_stats(tr, db, layer_prefix):
    by_type = {}
    bt = tr.GetObject(db.BlockTableId, OpenMode.ForRead)
    msp = tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForRead)
    prefix = (layer_prefix or 'C-ROAD-MARK').upper()
    for oid in msp:
        ent = tr.GetObject(oid, OpenMode.ForRead)
        if not isinstance(ent, Solid3d):
            continue
        lyr = (ent.Layer or '').upper()
        if not lyr.startswith('C-ROAD-MARK') and not lyr.startswith(prefix):
            continue
        xd = ent.GetXDataForApplication(MARK_XDATA)
        if xd is None:
            xd = ent.GetXDataForApplication(MARK_XDATA_LEGACY)
        if xd is None:
            continue
        mtype = None
        for tv in xd:
            if tv.TypeCode == 1000:
                mtype = str(tv.Value)
                break
        if mtype is None or '|' in mtype:
            continue
        ext = ent.GeometricExtents
        approx_len = math.hypot(ext.MaxPoint.X - ext.MinPoint.X, ext.MaxPoint.Y - ext.MinPoint.Y)
        by_type[mtype] = by_type.get(mtype, 0.0) + approx_len
    return by_type


def _signage_counts(tr, db, layer, xdata_app):
    aliases = _load_sign_block_aliases()
    counts = {}
    bt = tr.GetObject(db.BlockTableId, OpenMode.ForRead)
    msp = tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForRead)
    for oid in msp:
        ent = tr.GetObject(oid, OpenMode.ForRead)
        if ent.Layer != layer:
            continue
        if not isinstance(ent, BlockReference):
            continue
        xd = ent.GetXDataForApplication(xdata_app)
        if xd is None:
            continue
        btr = tr.GetObject(ent.BlockTableRecord, OpenMode.ForRead)
        nm = btr.Name
        key = aliases.get(nm, nm)
        counts[key] = counts.get(key, 0) + 1
    return counts


def run(
    vol_csv,
    mark_layer,
    sign_layer,
    pay_path,
    out_csv,
    corridor_name,
    state_code,
    sor_path,
    marking_qty_csv=None,
    irc37_cache_path=None,
    paved_area_m2=None,
    signage_counts_json=None,
    abstract_csv=None,
):
    bc = _boq_core()
    lu = _ensure_log_utils()
    log = lu['log_new']('M7')
    log_add = lu['log_add']
    out_wrap = lu['out_wrap']
    data = {'rows': 0, 'taxes': {}}

    if not pay_path or not os.path.isfile(pay_path):
        log_add(log, 'ERROR', 'PAYITEMS', 'payitems CSV missing')
        return out_wrap(log, data, legacy_msg='ERROR: payitems CSV path missing or not found.')
    if not out_csv:
        log_add(log, 'ERROR', 'OUT_PATH', 'output BOQ CSV path required')
        return out_wrap(log, data, legacy_msg='ERROR: output BOQ CSV path required')

    qty_lookup = bc.read_volume_csv(vol_csv)
    _, mark_len, mark_area = bc.load_marking_quantities_csv(marking_qty_csv)
    use_mark_csv = bool(mark_len or mark_area)

    if use_mark_csv:
        log_add(log, 'INFO', 'MARKING_QTY_CSV', 'Using marking_quantities CSV (%d types).' % len(set(list(mark_len.keys()) + list(mark_area.keys()))))
    else:
        mark_len = {}
        mark_area = {}

    try:
        area = float(paved_area_m2 or 0)
    except (TypeError, ValueError):
        area = 0.0
    pave_qty = bc.load_pavement_quantities(irc37_cache_path, area)
    if pave_qty:
        qty_lookup.update(pave_qty)
        log_add(log, 'INFO', 'IRC37_BOQ', 'Pavement volumes from irc37_cache x paved_area_m2=%.2f.' % area)
    elif irc37_cache_path and os.path.isfile(irc37_cache_path):
        log_add(log, 'WARN', 'IRC37_BOQ', 'paved_area_m2 not set — pavement payitems skipped.')

    sign_json = bc.load_signage_counts_json(signage_counts_json)
    if sign_json:
        qty_lookup.update(sign_json)
        log_add(log, 'INFO', 'SIGNAGE_JSON', 'Merged signage_counts.json (%d keys).' % len(sign_json))

    doc = Application.DocumentManager.MdiActiveDocument
    db = doc.Database

    with doc.LockDocument():
        with db.TransactionManager.StartTransaction() as tr:
            if not use_mark_csv:
                marks = _marking_stats(tr, db, mark_layer)
                for k, v in marks.items():
                    qty_lookup[('marking', k)] = v
                    mark_len[k] = v
            if not sign_json:
                signs = _signage_counts(tr, db, sign_layer, SIGN_XDATA)
                for blk, c in signs.items():
                    qty_lookup[('signage', blk)] = float(c)
            tr.Commit()

    rows_written, subtotal, taxes = bc.write_boq_csv(
        out_csv,
        pay_path,
        qty_lookup,
        mark_len,
        mark_area,
        state_code,
        sor_path,
        abstract_csv=abstract_csv,
    )

    data['rows'] = rows_written
    data['subtotal'] = subtotal
    data['taxes'] = taxes
    log_add(log, 'INFO', 'M7_TAX', 'Abstract rows written (grand_total=%.2f).' % taxes.get('grand_total', 0))
    legacy = 'OK: BOQ CSV written (%d items, state=%s).' % (rows_written, state_code or 'none')
    log_add(log, 'INFO', 'M7_OK', legacy)
    return out_wrap(log, data, legacy_msg=legacy)


# Re-export for tests importing from m7 module name
def compute_taxes(subtotal, tax_cfg=None):
    return _boq_core().compute_taxes(subtotal, tax_cfg)


def load_rates(state_code, sor_path, rate_keys, base_rates=None):
    return _boq_core().load_rates(state_code, sor_path, rate_keys, base_rates)


vol_csv = IN[0] if len(IN) > 0 else ''
mark_layer = IN[1] if len(IN) > 1 else 'C-ROAD-MARK-THERMO'
sign_layer = IN[2] if len(IN) > 2 else 'C-SGN-FURN'
pay_path = IN[3] if len(IN) > 3 else ''
out_csv = IN[4] if len(IN) > 4 else ''
corridor_name = IN[5] if len(IN) > 5 else ''
state_code = IN[6] if len(IN) > 6 else ''
sor_path = IN[7] if len(IN) > 7 else ''
marking_qty_csv = IN[8] if len(IN) > 8 else ''
irc37_cache_path = IN[9] if len(IN) > 9 else ''
paved_area_m2 = IN[10] if len(IN) > 10 else ''
signage_counts_json = IN[11] if len(IN) > 11 else ''
abstract_csv = IN[12] if len(IN) > 12 else ''

OUT = run(
    vol_csv, mark_layer, sign_layer, pay_path, out_csv, corridor_name, state_code, sor_path,
    marking_qty_csv, irc37_cache_path, paved_area_m2, signage_counts_json, abstract_csv,
)
