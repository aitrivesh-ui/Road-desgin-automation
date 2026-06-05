# -*- coding: utf-8 -*-
"""
Road Automation — M20  Design Verifier  (Python 3, stdlib only).

Cross-checks all project output CSVs against geometric bounds, design
standards, and internal consistency rules.

Usage:
  python design_verifier.py                          uses project.json from default location
  python design_verifier.py <path/to/project.json>  explicit path
  python design_verifier.py --help

Output:
  out/design_verification.txt   (OK / WARN / ERROR prefix convention)
"""
from __future__ import annotations

import csv as _csv
import json
import math
import os
import sys
from typing import List, Tuple

# ---------------------------------------------------------------------------
# Root resolution
# ---------------------------------------------------------------------------

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DEFAULT_PROJECT_JSON = os.path.join(ROOT, "config", "project.json")
DEFAULT_OUT          = os.path.join(ROOT, "out", "design_verification.txt")


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

Finding = Tuple[str, str]   # (level, message) — level is OK / WARN / ERROR


def _ok(msg: str)   -> Finding: return ("OK",    msg)
def _warn(msg: str) -> Finding: return ("WARN",  msg)
def _err(msg: str)  -> Finding: return ("ERROR", msg)
def _skip(msg: str) -> Finding: return ("SKIP",  msg)


# ---------------------------------------------------------------------------
# CSV reader helper
# ---------------------------------------------------------------------------

def _read_csv(path: str) -> List[dict]:
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8-sig") as f:
        return list(_csv.DictReader(f))


def _float(row: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Individual check suites
# ---------------------------------------------------------------------------

def check_alignment(rows: List[dict]) -> List[Finding]:
    findings: List[Finding] = []
    if not rows:
        return [_skip("alignment_pi.csv not found or empty")]
    for i, r in enumerate(rows):
        sta = _float(r, "easting")
        radius = _float(r, "radius_m")
        speed  = _float(r, "design_speed_kph", 80)
        if radius > 0 and speed > 0:
            # Minimum radius check: R_min ≈ V² / (127 × (e + f))
            # Using e=0.07, f=0.14 (typical)
            r_min = speed ** 2 / (127 * (0.07 + 0.14))
            if radius < r_min:
                findings.append(_warn(
                    f"PI row {i+2}: radius {radius:.1f} m < recommended minimum "
                    f"{r_min:.1f} m at {speed:.0f} km/h"
                ))
    if not findings:
        findings.append(_ok(f"alignment_pi.csv — {len(rows)} PI(s), radii OK"))
    return findings


def check_profile(rows: List[dict], max_grade: float, min_grade: float) -> List[Finding]:
    findings: List[Finding] = []
    if not rows:
        return [_skip("profile_pvis.csv not found or empty")]
    prev_sta = prev_elev = None
    for i, r in enumerate(rows):
        sta  = _float(r, "station_m")
        elev = _float(r, "elevation_m")
        if prev_sta is not None and sta > prev_sta:
            grade = abs((elev - prev_elev) / (sta - prev_sta)) * 100
            if grade > max_grade:
                findings.append(_warn(
                    f"profile_pvis row {i+2}: grade {grade:.2f}% exceeds "
                    f"max_grade_pct {max_grade:.1f}%"
                ))
            if grade < min_grade and grade > 1e-6:
                findings.append(_warn(
                    f"profile_pvis row {i+2}: grade {grade:.2f}% below "
                    f"min_grade_pct {min_grade:.2f}%"
                ))
        prev_sta, prev_elev = sta, elev
    if len(findings) == 0:
        findings.append(_ok(
            f"profile_pvis.csv — {len(rows)} PVI(s), grades within "
            f"[{min_grade:.2f}%, {max_grade:.1f}%]"
        ))
    return findings


def check_volumes(rows: List[dict]) -> List[Finding]:
    if not rows:
        return [_skip("volumes.csv not found or empty")]
    findings: List[Finding] = []
    total_cut = total_fill = 0.0
    for r in rows:
        total_cut  += _float(r, "cut_m3")
        total_fill += _float(r, "fill_m3")
    if total_cut <= 0 and total_fill <= 0:
        findings.append(_warn("volumes.csv: both cut and fill are zero — check corridor build"))
    else:
        ratio = total_cut / total_fill if total_fill > 0 else float("inf")
        sev   = _ok if 0.7 <= ratio <= 1.3 else _warn
        findings.append(sev(
            f"volumes.csv: cut={total_cut:,.1f} m3, fill={total_fill:,.1f} m3, "
            f"ratio={ratio:.2f}"
        ))
    return findings


def check_pavement(rows: List[dict]) -> List[Finding]:
    if not rows:
        return [_skip("pavement_design.csv not found — run M16 first")]
    findings: List[Finding] = []
    for r in rows:
        rid  = r.get("region_id", "?")
        tot  = _float(r, "total_thickness_mm")
        cbr  = _float(r, "design_cbr", 5.0)
        esa  = _float(r, "design_esa_million", 1.0)
        # Sanity: total thickness must be > 200 mm for any real road
        if tot < 200:
            findings.append(_warn(
                f"pavement region {rid}: total thickness {tot:.0f} mm seems low "
                f"(CBR={cbr:.1f}, ESA={esa:.2f} M)"
            ))
        # Max: thick pavement > 1000 mm is unusual
        elif tot > 1000:
            findings.append(_warn(
                f"pavement region {rid}: total thickness {tot:.0f} mm seems very high"
            ))
        else:
            findings.append(_ok(
                f"pavement region {rid}: {tot:.0f} mm OK (CBR={cbr:.1f}, ESA={esa:.2f} M)"
            ))
    return findings


def check_drainage(rows: List[dict]) -> List[Finding]:
    if not rows:
        return [_skip("drainage_design.csv not found — run M17 first")]
    findings: List[Finding] = []
    for r in rows:
        cid    = r.get("catchment_id", "?")
        hwd    = _float(r, "hw_d_ratio")
        status = r.get("status", "")
        if "NO FIT" in status.upper():
            findings.append(_err(
                f"Catchment {cid}: no culvert size fits — consider twin culvert or box"
            ))
        elif hwd > 1.5:
            findings.append(_warn(
                f"Catchment {cid}: HW/D={hwd:.2f} > 1.5 — review headwall design"
            ))
        else:
            findings.append(_ok(f"Catchment {cid}: culvert OK (HW/D={hwd:.2f})"))
    return findings


def check_boq(boq_rows: List[dict], vol_rows: List[dict]) -> List[Finding]:
    findings: List[Finding] = []
    if not boq_rows:
        return [_skip("boq.csv not found — run M7 first")]

    boq_items = {r.get("key", ""): _float(r, "quantity") for r in boq_rows}

    # Verify BOQ cut/fill matches volumes if volumes file is present
    if vol_rows:
        total_cut  = sum(_float(r, "cut_m3")  for r in vol_rows)
        total_fill = sum(_float(r, "fill_m3") for r in vol_rows)
        boq_cut  = boq_items.get("cut_m3",  boq_items.get("roadway_excavation_m3", 0))
        boq_fill = boq_items.get("fill_m3", boq_items.get("fill_compaction_m3",    0))

        if total_cut > 0 and boq_cut > 0:
            diff_pct = abs(boq_cut - total_cut) / total_cut * 100
            if diff_pct > 10:
                findings.append(_warn(
                    f"BOQ cut={boq_cut:,.1f} m3 vs volumes cut={total_cut:,.1f} m3 "
                    f"({diff_pct:.1f}% difference)"
                ))
            else:
                findings.append(_ok(f"BOQ cut matches volumes within {diff_pct:.1f}%"))

    findings.append(_ok(f"boq.csv: {len(boq_rows)} line item(s) present"))
    return findings


def check_mass_haul(rows: List[dict]) -> List[Finding]:
    if not rows:
        return [_skip("mass_haul.csv not found — run M12 first")]
    findings: List[Finding] = []
    max_surplus = max((_float(r, "cumulative_net_m3") for r in rows), default=0.0)
    min_deficit = min((_float(r, "cumulative_net_m3") for r in rows), default=0.0)
    if abs(min_deficit) > 50000:
        findings.append(_warn(
            f"Mass haul: peak deficit {min_deficit:,.0f} m3 — consider borrow pit"
        ))
    if max_surplus > 50000:
        findings.append(_warn(
            f"Mass haul: peak surplus {max_surplus:,.0f} m3 — consider waste site"
        ))
    if not findings:
        findings.append(_ok(
            f"mass_haul.csv: {len(rows)} stations, "
            f"max surplus={max_surplus:,.0f} m3, max deficit={min_deficit:,.0f} m3"
        ))
    return findings


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def run_verification(project_json: str) -> List[Finding]:
    if not os.path.isfile(project_json):
        return [_err(f"project.json not found: {project_json}")]

    with open(project_json, "r", encoding="utf-8-sig") as f:
        cfg = json.load(f)

    base   = os.path.dirname(os.path.abspath(project_json))
    root   = os.path.normpath(os.path.join(base, ".."))
    paths  = cfg.get("paths",  {})
    design = cfg.get("design", {})

    def _p(key: str, default: str) -> str:
        return os.path.normpath(os.path.join(root, paths.get(key, default)))

    align_rows   = _read_csv(_p("alignment_pi",         "csv/alignment_pi.csv"))
    profile_rows = _read_csv(_p("profile_pvis",         "csv/profile_pvis.csv"))
    vol_rows     = _read_csv(_p("volumes_csv",           "out/volumes.csv"))
    boq_rows     = _read_csv(_p("boq_csv",              "out/boq.csv"))
    pave_rows    = _read_csv(os.path.join(root, "out", "pavement_design.csv"))
    drain_rows   = _read_csv(os.path.join(root, "out", "drainage_design.csv"))
    haul_rows    = _read_csv(_p("mass_haul_csv",         "out/mass_haul.csv"))

    max_grade = float(design.get("max_grade_pct", 8.0))
    min_grade = float(design.get("min_grade_pct", 0.3))

    findings: List[Finding] = []
    findings += check_alignment(align_rows)
    findings += check_profile(profile_rows, max_grade, min_grade)
    findings += check_volumes(vol_rows)
    findings += check_pavement(pave_rows)
    findings += check_drainage(drain_rows)
    findings += check_boq(boq_rows, vol_rows)
    findings += check_mass_haul(haul_rows)
    return findings


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def write_report(findings: List[Finding], out_path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    errors   = sum(1 for lv, _ in findings if lv == "ERROR")
    warnings = sum(1 for lv, _ in findings if lv == "WARN")
    oks      = sum(1 for lv, _ in findings if lv == "OK")
    skips    = sum(1 for lv, _ in findings if lv == "SKIP")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("=" * 72 + "\n")
        f.write("Road Design Automation — M20 Design Verification Report\n")
        f.write("=" * 72 + "\n\n")
        for level, msg in findings:
            f.write(f"[{level:<5}]  {msg}\n")
        f.write("\n" + "-" * 72 + "\n")
        f.write(f"Summary: {oks} OK  |  {warnings} WARN  |  {errors} ERROR  |  {skips} SKIP\n")
        if errors > 0:
            f.write("RESULT: FAIL — review ERROR items before proceeding.\n")
        elif warnings > 0:
            f.write("RESULT: PASS WITH WARNINGS — review WARN items.\n")
        else:
            f.write("RESULT: PASS\n")
        f.write("=" * 72 + "\n")


def print_report(findings: List[Finding]) -> None:
    errors   = sum(1 for lv, _ in findings if lv == "ERROR")
    warnings = sum(1 for lv, _ in findings if lv == "WARN")
    for level, msg in findings:
        print(f"[{level:<5}]  {msg}")
    print()
    if errors > 0:
        print(f"RESULT: FAIL — {errors} error(s), {warnings} warning(s).")
    elif warnings > 0:
        print(f"RESULT: PASS WITH WARNINGS — {warnings} warning(s).")
    else:
        print("RESULT: PASS")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = sys.argv[1:]
    if "--help" in args or "-h" in args:
        print(__doc__)
        sys.exit(0)

    project_json = args[0] if args and not args[0].startswith("-") else DEFAULT_PROJECT_JSON
    print(f"Verifying project: {project_json}\n")

    findings = run_verification(project_json)
    print_report(findings)
    write_report(findings, DEFAULT_OUT)
    print(f"\nReport written: {DEFAULT_OUT}")

    errors = sum(1 for lv, _ in findings if lv == "ERROR")
    sys.exit(1 if errors > 0 else 0)


if __name__ == "__main__":
    main()
