# -*- coding: utf-8 -*-
"""
BOQ rollup core (stdlib only) — shared by m7_boq_rollup.py and unit tests.
NHAI abstract: contingency on subtotal; GST/cess/supervision on total_work.
"""
from __future__ import annotations

import csv
import json
import os

STATE_MULTIPLIERS = {
    "HR": 0.95,
    "PB": 0.98,
    "UP": 0.88,
    "RJ": 0.90,
    "DL": 1.00,
    "MH": 1.12,
    "GJ": 1.05,
    "KA": 1.08,
}

PAYITEM_OPTIONAL_COLS = ("qty_source", "morh_chapter", "rate_key")
PAVEMENT_LAYERS = ("GSB", "WMM", "DBM", "BC")

ABSTRACT_ROWS = (
    ("Subtotal", "SUBTOTAL", "subtotal"),
    ("Contingency 5%", "CONTINGENCY", "contingency"),
    ("Total work", "TOTAL_WORK", "total_work"),
    ("GST 18%", "GST", "gst"),
    ("Labour cess 1%", "LABOUR_CESS", "labour_cess"),
    ("Supervision 2%", "SUPERVISION", "supervision"),
    ("Grand total", "GRAND_TOTAL", "grand_total"),
)

VOLUME_KEYS = (
    "cut_m3",
    "fill_m3",
    "net_m3",
    "cut_haul_m3",
    "fill_borrow_m3",
    "borrow_req_m3",
    "spoil_m3",
    "cut_loose_m3",
    "fill_compacted_m3",
)


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_sor_data(sor_path: str | None, state_code: str | None) -> tuple[dict, dict, dict]:
    """Return (state_items, taxes_cfg, states_meta)."""
    if not sor_path or not os.path.isfile(sor_path) or not state_code:
        return {}, {}, {}
    data = _read_json(sor_path)
    states = data.get("states") or {}
    sc = state_code.upper()
    if sc not in states:
        return {}, data.get("taxes") or {}, states
    items = (data.get("items") or {}).get(sc, {})
    return items, data.get("taxes") or {}, states


def _state_multiplier(state_code: str, states_meta: dict) -> float:
    sc = (state_code or "").upper()
    if sc in states_meta:
        factor = states_meta[sc].get("default_rate_factor")
        if factor is not None:
            return float(factor)
    return float(STATE_MULTIPLIERS.get(sc, 1.0))


def load_rates(
    state_code: str | None,
    sor_path: str | None,
    rate_keys: list[str],
    base_rates: dict[str, float] | None = None,
) -> dict[str, float]:
    """
    Resolve rates for rate_keys (format source|key).
    Order: state JSON item -> base_rates * state multiplier -> base_rates * handbook multiplier.
    """
    base_rates = dict(base_rates or {})
    state_items, _, states_meta = load_sor_data(sor_path, state_code)
    mult = _state_multiplier(state_code or "", states_meta)
    out: dict[str, float] = {}
    for rk in rate_keys:
        if rk in state_items and state_items[rk] not in (None, ""):
            out[rk] = float(state_items[rk])
            continue
        base = base_rates.get(rk)
        if base is not None:
            out[rk] = round(float(base) * mult, 2)
        elif state_code:
            out[rk] = 0.0
    return out


def compute_taxes(subtotal: float, tax_cfg: dict | None = None) -> dict[str, float]:
    """NHAI handbook: taxes applied on total_work (subtotal + contingency)."""
    tax_cfg = tax_cfg or {}
    subtotal = float(subtotal or 0)
    contingency_pct = float(tax_cfg.get("contingency_pct", 5.0))
    gst_pct = float(tax_cfg.get("gst_pct", 18.0))
    labour_pct = float(tax_cfg.get("labour_cess_pct", 1.0))
    supervision_pct = float(tax_cfg.get("supervision_pct", 2.0))

    contingency = subtotal * contingency_pct / 100.0
    total_work = subtotal + contingency
    gst = total_work * gst_pct / 100.0
    labour_cess = total_work * labour_pct / 100.0
    supervision = total_work * supervision_pct / 100.0
    grand_total = total_work + gst + labour_cess + supervision

    return {
        "subtotal": round(subtotal, 2),
        "contingency": round(contingency, 2),
        "total_work": round(total_work, 2),
        "gst": round(gst, 2),
        "labour_cess": round(labour_cess, 2),
        "supervision": round(supervision, 2),
        "grand_total": round(grand_total, 2),
    }


def read_volume_csv(path: str | None) -> dict[tuple[str, str], float]:
    if not path or not os.path.isfile(path):
        return {}
    out: dict[tuple[str, str], float] = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return out
    r0 = None
    for r in rows:
        if (r.get("record_type") or "").strip().lower() == "summary":
            r0 = r
            break
    if r0 is None:
        r0 = rows[-1]
    for key in VOLUME_KEYS:
        val = r0.get(key)
        if val not in (None, ""):
            out[("volumes", key)] = float(val or 0)
    return out


def volume_summary_has_corrected(path: str | None) -> bool:
    vols = read_volume_csv(path)
    return ("volumes", "cut_haul_m3") in vols and ("volumes", "fill_borrow_m3") in vols


def load_marking_quantities_csv(path: str | None) -> tuple[dict[tuple[str, str], float], dict[str, float], dict[str, float]]:
    """
    Returns (empty lookup — use by_len/by_area via resolve_quantity, length_by_type, area_by_type).
    """
    by_len: dict[str, float] = {}
    by_area: dict[str, float] = {}
    if not path or not os.path.isfile(path):
        return {}, by_len, by_area
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            mt = (r.get("mark_type") or "").strip()
            if not mt:
                continue
            by_len[mt] = by_len.get(mt, 0.0) + float(r.get("length_m") or 0)
            by_area[mt] = by_area.get(mt, 0.0) + float(r.get("area_m2") or 0)
    return {}, by_len, by_area


def marking_qty_for_unit(mark_type: str, unit: str, by_len: dict[str, float], by_area: dict[str, float]) -> float | None:
    u = (unit or "").strip().lower().replace("²", "2")
    if u in ("m2", "sqm", "sq.m"):
        v = by_area.get(mark_type)
        return v if v and v > 0 else None
    if u in ("m", "rm", "metre", "meter"):
        v = by_len.get(mark_type)
        return v if v and v > 0 else None
    return by_len.get(mark_type) or by_area.get(mark_type)


def load_irc37_layer_thickness_m(path: str | None) -> dict[str, float]:
    if not path or not os.path.isfile(path):
        return {}
    data = _read_json(path)
    layers_mm = data.get("layers_mm") or {}
    if not layers_mm and data.get("layers"):
        for row in data["layers"]:
            if row.get("name"):
                layers_mm[row["name"]] = row.get("thickness_mm", 0)
    out: dict[str, float] = {}
    for layer in PAVEMENT_LAYERS:
        if layer in layers_mm:
            out[layer.lower()] = float(layers_mm[layer]) / 1000.0
    return out


def load_pavement_quantities(irc37_path: str | None, paved_area_m2: float) -> dict[tuple[str, str], float]:
    thickness = load_irc37_layer_thickness_m(irc37_path)
    area = float(paved_area_m2 or 0)
    if area <= 0:
        return {}
    out: dict[tuple[str, str], float] = {}
    for layer, thick_m in thickness.items():
        out[("pavement", layer)] = thick_m * area
    return out


def load_signage_counts_json(path: str | None) -> dict[tuple[str, str], float]:
    if not path or not os.path.isfile(path):
        return {}
    data = _read_json(path)
    counts = data.get("counts") or data
    out: dict[tuple[str, str], float] = {}
    if isinstance(counts, dict):
        for k, v in counts.items():
            out[("signage", str(k))] = float(v)
    return out


def load_paymap(path: str) -> dict[tuple[str, str], dict]:
    m: dict[tuple[str, str], dict] = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            m[(r["source"].strip(), r["key"].strip())] = r
    return m


def payitem_rate_key(row: dict) -> str:
    rk = (row.get("rate_key") or "").strip()
    if rk:
        return rk
    return "%s|%s" % (row.get("source", "").strip(), row.get("key", "").strip())


def resolve_qty_key(row: dict) -> tuple[str, str]:
    qs = (row.get("qty_source") or "").strip()
    if qs and "." in qs:
        parts = qs.split(".", 1)
        return parts[0].strip(), parts[1].strip()
    return row.get("source", "").strip(), row.get("key", "").strip()


def resolve_quantity(
    row: dict,
    qty_lookup: dict[tuple[str, str], float],
    marking_by_len: dict[str, float],
    marking_by_area: dict[str, float],
) -> float | None:
    src, key = resolve_qty_key(row)
    q = qty_lookup.get((src, key))
    if q is not None:
        return float(q)
    if src == "marking":
        return marking_qty_for_unit(key, row.get("unit", ""), marking_by_len, marking_by_area)
    return None


def known_qty_providers(paths: dict, root: str) -> set[tuple[str, str]]:
    """Static keys available without DWG scan."""
    providers: set[tuple[str, str]] = set()
    vol_path = paths.get("volumes_csv")
    if vol_path:
        full = os.path.normpath(os.path.join(root, vol_path.replace("/", os.sep)))
        providers.update(read_volume_csv(full).keys())
    mq = paths.get("marking_quantities")
    if mq:
        full = os.path.normpath(os.path.join(root, mq.replace("/", os.sep)))
        _, by_len, by_area = load_marking_quantities_csv(full)
        for mt in set(list(by_len.keys()) + list(by_area.keys())):
            providers.add(("marking", mt))
    pave_key = paths.get("irc37_cache") or paths.get("pavement_irc37")
    if pave_key:
        providers.add(("pavement", "gsb"))
        providers.add(("pavement", "wmm"))
        providers.add(("pavement", "dbm"))
        providers.add(("pavement", "bc"))
    sc = paths.get("signage_counts")
    if sc:
        full = os.path.normpath(os.path.join(root, sc.replace("/", os.sep)))
        providers.update(load_signage_counts_json(full).keys())
    providers.add(("signage", "SGN_STOP"))
    return providers


def write_abstract_rows(writer, taxes: dict[str, float]) -> None:
    writer.writerow([])
    for label, key, field in ABSTRACT_ROWS:
        writer.writerow(
            ["ABSTRACT", label, "", "", "", "%.2f" % taxes[field], "", key]
        )


def rollup_boq_lines(
    pay: dict[tuple[str, str], dict],
    qty_lookup: dict[tuple[str, str], float],
    marking_by_len: dict[str, float],
    marking_by_area: dict[str, float],
    rates: dict[str, float],
) -> tuple[list[list], float]:
    lines: list[list] = []
    subtotal = 0.0
    def _pay_item_sort_key(item):
        pi = item[1].get("pay_item", "")
        try:
            return tuple(int(p) if p.isdigit() else p for p in pi.replace("-", ".").split("."))
        except Exception:
            return (pi,)
    for (src, key), row in sorted(pay.items(), key=_pay_item_sort_key):
        q = resolve_quantity(row, qty_lookup, marking_by_len, marking_by_area)
        if q is None:
            continue
        rk = payitem_rate_key(row)
        rate = float(rates.get(rk, 0) or 0)
        amt = float(q) * rate if rate else 0.0
        subtotal += amt
        lines.append(
            [
                row.get("pay_item", ""),
                row.get("description", ""),
                row.get("unit", ""),
                "%.4f" % float(q),
                "%.4f" % rate if rate else "",
                "%.4f" % amt if rate else "",
                src,
                key,
            ]
        )
    return lines, subtotal


def write_boq_csv(
    out_csv: str,
    pay_path: str,
    qty_lookup: dict[tuple[str, str], float],
    marking_by_len: dict[str, float],
    marking_by_area: dict[str, float],
    state_code: str | None,
    sor_path: str | None,
    base_rates: dict[str, float] | None = None,
    abstract_csv: str | None = None,
) -> tuple[int, float, dict[str, float]]:
    pay = load_paymap(pay_path)
    rate_keys = [payitem_rate_key(row) for row in pay.values()]
    _, tax_cfg, _ = load_sor_data(sor_path, state_code)
    rates = load_rates(state_code, sor_path, rate_keys, base_rates)
    lines, subtotal = rollup_boq_lines(
        pay, qty_lookup, marking_by_len, marking_by_area, rates
    )
    taxes = compute_taxes(subtotal, tax_cfg)

    d = os.path.dirname(out_csv)
    if d and not os.path.isdir(d):
        os.makedirs(d)

    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pay_item", "description", "unit", "quantity", "rate", "amount", "source", "key"])
        for line in lines:
            w.writerow(line)
        if not abstract_csv:
            write_abstract_rows(w, taxes)

    if abstract_csv:
        ad = os.path.dirname(abstract_csv)
        if ad and not os.path.isdir(ad):
            os.makedirs(ad)
        with open(abstract_csv, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["pay_item", "description", "unit", "quantity", "rate", "amount", "source", "key"])
            write_abstract_rows(w, taxes)

    return len(lines), subtotal, taxes
