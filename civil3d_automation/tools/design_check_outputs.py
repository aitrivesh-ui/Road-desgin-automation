# -*- coding: utf-8 -*-
"""
Post-run sanity read of volumes + BOQ CSVs referenced by project.json (stdlib only).

Usage:
  python design_check_outputs.py path/to/config/project.json
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys


def root_from_project_json(project_json: str) -> str:
    base = os.path.dirname(os.path.abspath(project_json))
    return os.path.normpath(os.path.join(base, ".."))


def resolve_path(root: str, rel: str) -> str:
    return os.path.normpath(os.path.join(root, rel.replace("/", os.sep)))


def _summary_volume_row(rows: list[dict]) -> dict | None:
    for r in rows:
        if (r.get("record_type") or "").strip().lower() == "summary":
            return r
    return rows[-1] if rows else None


def _parse_boq_abstract(bp: str) -> tuple[int, dict[str, str]]:
    """Return (quantity_row_count, abstract_key -> amount string)."""
    qty_rows = 0
    abstract: dict[str, str] = {}
    with open(bp, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if not row:
                continue
            if row[0] == "ABSTRACT" and len(row) >= 8:
                key = (row[7] or "").strip()
                amt = (row[5] or "").strip()
                if key:
                    abstract[key] = amt
            elif row[0] and row[0] != "pay_item" and row[0] != "ABSTRACT":
                qty_rows += 1
    return qty_rows, abstract


def run_checks(project_json: str) -> list[str]:
    lines: list[str] = []
    if not os.path.isfile(project_json):
        lines.append("ERROR: project.json not found: " + project_json)
        return lines

    root = root_from_project_json(project_json)
    with open(project_json, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    paths = cfg.get("paths") or {}
    design = cfg.get("design") or {}

    vol = paths.get("volumes_csv")
    if vol:
        vp = resolve_path(root, vol)
        if not os.path.isfile(vp):
            lines.append("WARN: Volumes CSV not found yet: " + vp)
        else:
            with open(vp, "r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            if not rows:
                lines.append("WARN: Volumes CSV is empty (no data rows).")
            else:
                r = _summary_volume_row(rows)
                if r is None:
                    lines.append("WARN: Volumes CSV has no data rows.")
                else:
                    lines.append(
                        "OK: Volumes summary — cut_m3=%s fill_m3=%s net_m3=%s"
                        % (r.get("cut_m3", "?"), r.get("fill_m3", "?"), r.get("net_m3", "?"))
                    )
                    swell_cols = (
                        "cut_haul_m3",
                        "fill_borrow_m3",
                        "borrow_req_m3",
                        "spoil_m3",
                    )
                    missing = [c for c in swell_cols if not r.get(c)]
                    if missing:
                        lines.append(
                            "WARN: Volumes summary missing swell columns: %s"
                            % ", ".join(missing)
                        )
                    else:
                        lines.append(
                            "OK: Swell summary — haul=%s borrow=%s spoil=%s borrow_req=%s"
                            % (
                                r.get("cut_haul_m3"),
                                r.get("fill_borrow_m3"),
                                r.get("spoil_m3"),
                                r.get("borrow_req_m3"),
                            )
                        )
                region_count = sum(
                    1 for row in rows if (row.get("record_type") or "").lower() == "region"
                )
                if region_count:
                    lines.append("OK: Volumes CSV has %d region row(s)." % region_count)

    mh = paths.get("mass_haul_csv")
    interval = float(design.get("volume_sample_interval_m", 20) or 20)
    meta_path = resolve_path(root, paths.get("alignment_meta", "")) if paths.get("alignment_meta") else ""
    length_m = 1000.0
    if meta_path and os.path.isfile(meta_path):
        with open(meta_path, "r", encoding="utf-8") as mf:
            meta = json.load(mf)
        if meta.get("total_length_m") is not None:
            length_m = float(meta["total_length_m"])

    if mh:
        mp = resolve_path(root, mh)
        if not os.path.isfile(mp):
            lines.append("WARN: Mass haul CSV not found yet: " + mp)
        else:
            with open(mp, "r", encoding="utf-8-sig", newline="") as f:
                mh_rows = list(csv.DictReader(f))
            expected = max(1, int(round(length_m / interval))) + 1
            actual = len(mh_rows)
            if abs(actual - expected) > 1:
                lines.append(
                    "WARN: Mass haul row count %d (expected ~%d for length %.0f m / interval %.0f m)."
                    % (actual, expected, length_m, interval)
                )
            else:
                lines.append(
                    "OK: Mass haul row count %d (~expected %d)." % (actual, expected)
                )
            chart_rel = paths.get("mass_haul_chart_svg", "out/mass_haul_chart.svg")
            chart_path = resolve_path(root, chart_rel)
            try:
                tools_dir = os.path.dirname(os.path.abspath(__file__))
                if tools_dir not in sys.path:
                    sys.path.insert(0, tools_dir)
                import export_mass_haul_chart as mhc

                meta_rel = paths.get("mass_haul_meta", "")
                meta_p = resolve_path(root, meta_rel) if meta_rel else None
                mhc.export_chart(mp, chart_path, meta_p)
                lines.append("OK: Mass haul chart SVG — %s" % chart_path)
            except Exception as ex:
                lines.append("WARN: Mass haul chart export failed: %s" % ex)

    boq = paths.get("boq_csv")
    required_abstract = (
        "SUBTOTAL",
        "CONTINGENCY",
        "TOTAL_WORK",
        "GST",
        "LABOUR_CESS",
        "SUPERVISION",
        "GRAND_TOTAL",
    )
    if boq:
        bp = resolve_path(root, boq)
        if not os.path.isfile(bp):
            lines.append("WARN: BOQ CSV not found yet: " + bp)
        else:
            qty_rows, abstract = _parse_boq_abstract(bp)
            if qty_rows == 0:
                lines.append("WARN: BOQ CSV has no quantity rows (check payitems map vs model).")
            else:
                lines.append("OK: BOQ CSV has %d quantity row(s)." % qty_rows)
            missing_abs = [k for k in required_abstract if k not in abstract]
            if missing_abs:
                lines.append(
                    "WARN: BOQ abstract incomplete — missing keys: %s (re-run M7)."
                    % ", ".join(missing_abs)
                )
            else:
                lines.append(
                    "OK: BOQ abstract — subtotal=%s contingency=%s total_work=%s grand_total=%s"
                    % (
                        abstract.get("SUBTOTAL", "?"),
                        abstract.get("CONTINGENCY", "?"),
                        abstract.get("TOTAL_WORK", "?"),
                        abstract.get("GRAND_TOTAL", "?"),
                    )
                )

    manifest_rel = paths.get("dpr_sheet_manifest")
    if manifest_rel:
        mp = resolve_path(root, manifest_rel)
        if not os.path.isfile(mp):
            lines.append("WARN: DPR sheet manifest not found yet: " + mp)
        else:
            with open(mp, "r", encoding="utf-8") as mf:
                manifest = json.load(mf)
            xs_val = manifest.get("xs_validation") or {}
            n_sta = xs_val.get("n_stations", 0)
            cap = xs_val.get("capacity_stations", 0)
            if manifest.get("total_length_m", 0) > 0 and n_sta <= 0:
                lines.append(
                    "WARN: DPR manifest has no n_stations — run M4 for XS sheet count."
                )
            elif n_sta > 0 and cap < n_sta:
                lines.append(
                    "WARN: DPR XS sheets cover %d stations but manifest lists %d."
                    % (cap, n_sta)
                )
            else:
                lines.append(
                    "OK: DPR manifest — %d sheets; PP=%s XS=%s."
                    % (
                        len(manifest.get("sheets", [])),
                        (manifest.get("sheet_counts") or {}).get("PP", "?"),
                        (manifest.get("sheet_counts") or {}).get("XS", "?"),
                    )
                )
            mh_meta_rel = paths.get("mass_haul_meta")
            if mh_meta_rel and os.path.isfile(resolve_path(root, mh_meta_rel)):
                with open(resolve_path(root, mh_meta_rel), "r", encoding="utf-8") as jf:
                    mh_meta = json.load(jf)
                sc = mh_meta.get("sample_count")
                if sc is not None and n_sta and int(sc) != int(n_sta):
                    lines.append(
                        "WARN: manifest n_stations=%s vs mass_haul_meta.sample_count=%s."
                        % (n_sta, sc)
                    )

    if len(lines) == 0:
        lines.append("INFO: No volumes_csv / boq_csv paths in project.json.")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description="Read volumes/BOQ outputs for quick sanity checks.")
    ap.add_argument("project_json", help="Path to config/project.json")
    args = ap.parse_args()
    lines = run_checks(args.project_json)
    print("\n".join(lines))
    return 1 if any(x.startswith("ERROR:") for x in lines) else 0


if __name__ == "__main__":
    sys.exit(main())
