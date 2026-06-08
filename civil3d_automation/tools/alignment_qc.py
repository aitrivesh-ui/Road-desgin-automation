"""
alignment_qc.py — Alignment PI Quality Control
Pre-processes alignment_pi.csv before the Dynamo M1 run.
Detects: duplicates, coordinate outliers, impossible deflections,
perpendicular offset anomalies, impossible spiral geometry, short tangents.

CLI:
  python alignment_qc.py --cli csv/alignment_pi.csv
  python alignment_qc.py --cli csv/alignment_pi.csv --tolerance 2.0 --min-spacing 5.0 \\
      --auto-remove --out-csv out/alignment_pi_qc.csv --out-report out/alignment_qc_report.txt
"""

import csv as _csv
import math
import os
import sys
from typing import List, NamedTuple, Optional

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

DEFAULT_OUT_CSV    = os.path.join(ROOT, "out", "alignment_pi_qc.csv")
DEFAULT_OUT_REPORT = os.path.join(ROOT, "out", "alignment_qc_report.txt")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class PIRow(NamedTuple):
    pi_id:            str
    easting:          float
    northing:         float
    radius_m:         float
    spiral_in_m:      float
    spiral_out_m:     float
    design_speed_kph: float


class QCIssue(NamedTuple):
    pi_id:     str
    check:     str    # DUPLICATE_PI | COORD_OUTLIER | PERP_OFFSET | IMPOSSIBLE_DEFLECTION |
                      # NEAR_TANGENT | IMPOSSIBLE_SPIRAL | SHORT_TANGENT
    severity:  str    # ERROR | WARN
    removable: bool   # True = auto-remove is safe
    message:   str
    value:     float  # numeric value that triggered the flag


# ---------------------------------------------------------------------------
# CSV reader
# ---------------------------------------------------------------------------

_REQUIRED = {"pi_id", "easting", "northing", "radius_m",
             "spiral_in_m", "spiral_out_m", "design_speed_kph"}


def _flt(row: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return default


def read_alignment_pi(path: str) -> List[PIRow]:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Not found: {path}")
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = _csv.DictReader(f)
        missing = _REQUIRED - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
        rows = []
        for i, row in enumerate(reader, 2):
            rows.append(PIRow(
                pi_id            = str(row.get("pi_id", f"PI-{i}")).strip(),
                easting          = _flt(row, "easting"),
                northing         = _flt(row, "northing"),
                radius_m         = _flt(row, "radius_m"),
                spiral_in_m      = _flt(row, "spiral_in_m"),
                spiral_out_m     = _flt(row, "spiral_out_m"),
                design_speed_kph = _flt(row, "design_speed_kph", 80.0),
            ))
    return rows


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _dist(a: PIRow, b: PIRow) -> float:
    return math.hypot(b.easting - a.easting, b.northing - a.northing)


def _bearing(dx: float, dy: float) -> float:
    """Bearing from north, clockwise (rad)."""
    return math.atan2(dx, dy)


def _deflection_deg(prev: PIRow, cur: PIRow, nxt: PIRow) -> float:
    """Signed deflection angle at cur (degrees). Positive = right turn."""
    b_in  = _bearing(cur.easting  - prev.easting,  cur.northing  - prev.northing)
    b_out = _bearing(nxt.easting  - cur.easting,   nxt.northing  - cur.northing)
    delta = b_out - b_in
    while delta >  math.pi: delta -= 2 * math.pi
    while delta < -math.pi: delta += 2 * math.pi
    return math.degrees(delta)


def _perp_offset(prev: PIRow, cur: PIRow, nxt: PIRow) -> float:
    """Perpendicular distance of cur from the chord prev→nxt."""
    dx = nxt.easting  - prev.easting
    dy = nxt.northing - prev.northing
    chord = math.hypot(dx, dy)
    if chord < 1e-6:
        return 0.0
    return abs((dx * (prev.northing - cur.northing)
                - dy * (prev.easting  - cur.easting)) / chord)


def _tangent_length(R: float, delta_deg: float, Ls_in: float, Ls_out: float) -> float:
    """Approximate full tangent length for a curve at a PI."""
    if R <= 0:
        return 0.0
    delta_rad = abs(math.radians(delta_deg))
    if delta_rad < 1e-6:
        return 0.0
    theta_in  = Ls_in  / (2.0 * R) if Ls_in  > 0 else 0.0
    theta_out = Ls_out / (2.0 * R) if Ls_out > 0 else 0.0
    delta_circ = max(0.0, delta_rad - theta_in - theta_out)
    try:
        T = R * math.tan(delta_circ / 2.0) + Ls_in / 2.0 + Ls_out / 2.0
    except Exception:
        T = R * math.tan(delta_rad / 2.0)
    return T


def _median(values: list) -> float:
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def _mad(values: list, med: float) -> float:
    return _median([abs(v - med) for v in values])


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------

def check_duplicate_pis(pis: List[PIRow], min_spacing_m: float) -> List[QCIssue]:
    issues: List[QCIssue] = []
    for i in range(len(pis) - 1):
        d = _dist(pis[i], pis[i + 1])
        if d < min_spacing_m:
            issues.append(QCIssue(
                pi_id=pis[i + 1].pi_id,
                check="DUPLICATE_PI",
                severity="ERROR",
                removable=True,
                message=(f"PI {pis[i+1].pi_id} is {d:.2f} m from PI {pis[i].pi_id} "
                         f"(min spacing {min_spacing_m:.1f} m)"),
                value=d,
            ))
    return issues


def check_coordinate_outliers(pis: List[PIRow]) -> List[QCIssue]:
    if len(pis) < 4:
        return []
    issues: List[QCIssue] = []
    eastings  = [p.easting  for p in pis]
    northings = [p.northing for p in pis]

    for coords, label, getter in [
        (eastings,  "easting",  lambda p: p.easting),
        (northings, "northing", lambda p: p.northing),
    ]:
        med = _median(coords)
        mad = _mad(coords, med)
        if mad < 1.0:
            continue  # all values nearly identical — skip
        fence = 5.0 * mad
        for p in pis:
            val = getter(p)
            if abs(val - med) > fence:
                issues.append(QCIssue(
                    pi_id=p.pi_id,
                    check="COORD_OUTLIER",
                    severity="ERROR",
                    removable=True,
                    message=(f"PI {p.pi_id} {label}={val:.3f} deviates "
                             f"{abs(val-med):.1f} m from median (fence={fence:.1f} m)"),
                    value=abs(val - med),
                ))
    return issues


def check_deflection_angles(pis: List[PIRow],
                             max_deflection_deg: float = 160.0) -> List[QCIssue]:
    issues: List[QCIssue] = []
    for i in range(1, len(pis) - 1):
        delta = _deflection_deg(pis[i - 1], pis[i], pis[i + 1])
        abs_d = abs(delta)
        if abs_d > max_deflection_deg:
            issues.append(QCIssue(
                pi_id=pis[i].pi_id,
                check="IMPOSSIBLE_DEFLECTION",
                severity="ERROR",
                removable=False,
                message=(f"PI {pis[i].pi_id} deflection {abs_d:.1f}° > {max_deflection_deg:.0f}° "
                         f"— near U-turn or data error"),
                value=abs_d,
            ))
        elif abs_d < 0.5 and pis[i].radius_m > 0:
            issues.append(QCIssue(
                pi_id=pis[i].pi_id,
                check="NEAR_TANGENT",
                severity="WARN",
                removable=False,
                message=(f"PI {pis[i].pi_id} deflection {abs_d:.2f}° < 0.5° "
                         f"but radius_m={pis[i].radius_m:.0f} — may be redundant PI"),
                value=abs_d,
            ))
    return issues


def check_perpendicular_offsets(pis: List[PIRow],
                                 tolerance_m: float = 2.0) -> List[QCIssue]:
    if len(pis) < 3:
        return []
    issues: List[QCIssue] = []

    # Compute all chord offsets for outlier context
    offsets = [_perp_offset(pis[i - 1], pis[i], pis[i + 1])
               for i in range(1, len(pis) - 1)]
    med_off = _median(offsets) if offsets else 0.0

    for i in range(1, len(pis) - 1):
        off = offsets[i - 1]
        is_stat_outlier = (off > 3.0 * med_off and med_off > 0.1)
        if off > tolerance_m:
            sev = "ERROR" if (off > tolerance_m * 3 or is_stat_outlier) else "WARN"
            issues.append(QCIssue(
                pi_id=pis[i].pi_id,
                check="PERP_OFFSET",
                severity=sev,
                removable=False,
                message=(f"PI {pis[i].pi_id} perpendicular offset {off:.2f} m from chord "
                         f"PI[{i-1}]→PI[{i+1}] exceeds tolerance {tolerance_m:.1f} m"
                         + (" (statistical outlier)" if is_stat_outlier else "")),
                value=off,
            ))
    return issues


def check_spiral_geometry(pis: List[PIRow]) -> List[QCIssue]:
    issues: List[QCIssue] = []
    for i in range(1, len(pis) - 1):
        p = pis[i]
        R    = p.radius_m
        Ls_i = p.spiral_in_m
        Ls_o = p.spiral_out_m
        if R <= 0 or (Ls_i + Ls_o) <= 0:
            continue
        delta_deg = abs(_deflection_deg(pis[i - 1], p, pis[i + 1]))
        delta_rad = math.radians(delta_deg)
        theta_in  = Ls_i / (2.0 * R)
        theta_out = Ls_o / (2.0 * R)
        if (theta_in + theta_out) >= delta_rad:
            issues.append(QCIssue(
                pi_id=p.pi_id,
                check="IMPOSSIBLE_SPIRAL",
                severity="ERROR",
                removable=False,
                message=(f"PI {p.pi_id}: spiral angles ({math.degrees(theta_in):.1f}°+"
                         f"{math.degrees(theta_out):.1f}°) ≥ deflection {delta_deg:.1f}° "
                         f"— spirals exceed available arc. Reduce spiral lengths."),
                value=math.degrees(theta_in + theta_out),
            ))
        # Clothoid parameter A adequacy
        for Ls, label in [(Ls_i, "in"), (Ls_o, "out")]:
            if Ls <= 0:
                continue
            A = math.sqrt(R * Ls)
            A_abs = math.sqrt(R * R / 9.0)   # absolute minimum A = R/3
            if A < A_abs:
                issues.append(QCIssue(
                    pi_id=p.pi_id,
                    check="IMPOSSIBLE_SPIRAL",
                    severity="WARN",
                    removable=False,
                    message=(f"PI {p.pi_id} spiral_{label}: A={A:.1f} < A_min_abs={A_abs:.1f} "
                             f"(R={R:.0f}, Ls={Ls:.0f})"),
                    value=A,
                ))
    return issues


def check_tangent_lengths(pis: List[PIRow],
                           min_tangent_m: float = 20.0) -> List[QCIssue]:
    """Flag consecutive curve PIs with insufficient tangent between them."""
    issues: List[QCIssue] = []
    for i in range(1, len(pis) - 2):
        cur = pis[i]
        nxt = pis[i + 1]
        if cur.radius_m <= 0 or nxt.radius_m <= 0:
            continue
        # Distance between the two PI points
        chord = _dist(cur, nxt)
        d_cur = abs(_deflection_deg(pis[i - 1], cur, nxt))
        d_nxt = abs(_deflection_deg(cur, nxt, pis[i + 2] if i + 2 < len(pis) else nxt))
        T_cur = _tangent_length(cur.radius_m, d_cur, cur.spiral_in_m,  cur.spiral_out_m)
        T_nxt = _tangent_length(nxt.radius_m, d_nxt, nxt.spiral_in_m,  nxt.spiral_out_m)
        avail = chord - T_cur - T_nxt
        if avail < min_tangent_m:
            issues.append(QCIssue(
                pi_id=nxt.pi_id,
                check="SHORT_TANGENT",
                severity="WARN",
                removable=False,
                message=(f"PI {cur.pi_id}→{nxt.pi_id}: available tangent {avail:.1f} m "
                         f"< min {min_tangent_m:.1f} m (T_prev={T_cur:.1f}, T_next={T_nxt:.1f})"),
                value=avail,
            ))
    return issues


# ---------------------------------------------------------------------------
# Run all checks
# ---------------------------------------------------------------------------

def run_checks(pis: List[PIRow],
               tolerance_m:      float = 2.0,
               min_spacing_m:    float = 5.0,
               min_tangent_m:    float = 20.0,
               max_deflection:   float = 160.0) -> List[QCIssue]:
    issues: List[QCIssue] = []
    issues += check_duplicate_pis(pis, min_spacing_m)
    issues += check_coordinate_outliers(pis)
    issues += check_deflection_angles(pis, max_deflection)
    issues += check_perpendicular_offsets(pis, tolerance_m)
    issues += check_spiral_geometry(pis)
    issues += check_tangent_lengths(pis, min_tangent_m)
    return issues


# ---------------------------------------------------------------------------
# Auto-fix: remove removable ERROR rows
# ---------------------------------------------------------------------------

def apply_auto_remove(pis: List[PIRow], issues: List[QCIssue]) -> List[PIRow]:
    remove_ids = {iss.pi_id for iss in issues
                  if iss.removable and iss.severity == "ERROR"}
    return [p for p in pis if p.pi_id not in remove_ids]


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

_QC_HEADERS = [
    "pi_id", "easting", "northing", "radius_m", "spiral_in_m",
    "spiral_out_m", "design_speed_kph", "qc_status", "chord_dist_m",
    "delta_deg", "notes",
]


def write_cleaned_csv(orig_pis: List[PIRow], cleaned_pis: List[PIRow],
                      issues: List[QCIssue], path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    issue_map: dict = {}
    for iss in issues:
        if iss.pi_id not in issue_map:
            issue_map[iss.pi_id] = []
        issue_map[iss.pi_id].append(iss)

    cleaned_ids = {p.pi_id for p in cleaned_pis}

    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = _csv.writer(f)
        w.writerow(_QC_HEADERS)
        for p in orig_pis:
            row_issues = issue_map.get(p.pi_id, [])
            if p.pi_id not in cleaned_ids:
                status = "REMOVED"
            elif row_issues:
                status = row_issues[0].check
            else:
                status = "OK"

            # chord distance to chord (0 for first/last PI)
            chord_dist = row_issues[0].value if row_issues and \
                row_issues[0].check == "PERP_OFFSET" else 0.0

            notes = "; ".join(iss.message for iss in row_issues) if row_issues else ""

            w.writerow([
                p.pi_id, p.easting, p.northing, p.radius_m,
                p.spiral_in_m, p.spiral_out_m, p.design_speed_kph,
                status, f"{chord_dist:.3f}", "", notes,
            ])


def write_report(orig_pis: List[PIRow], cleaned_pis: List[PIRow],
                 issues: List[QCIssue], params: dict, path: str) -> List[str]:
    lines: List[str] = []
    errors = [i for i in issues if i.severity == "ERROR"]
    warns  = [i for i in issues if i.severity == "WARN"]
    removed = len(orig_pis) - len(cleaned_pis)

    lines.append("=" * 70)
    lines.append("ALIGNMENT PI QC REPORT")
    lines.append("=" * 70)
    lines.append(f"Input:   {params.get('input_csv', '?')}  ({len(orig_pis)} PIs)")
    lines.append(f"Params:  tolerance={params.get('tolerance_m',2.0):.1f}m  "
                 f"min_spacing={params.get('min_spacing_m',5.0):.1f}m  "
                 f"min_tangent={params.get('min_tangent_m',20.0):.1f}m")
    lines.append("")

    if not issues:
        lines.append("All checks passed — no issues found.")
    else:
        lines.append("ISSUES FOUND")
        lines.append("-" * 70)
        for iss in issues:
            action = "REMOVABLE" if iss.removable else "REVIEW REQUIRED"
            lines.append(f"[{iss.severity:<5}] {iss.check:<25} {iss.message}   ACTION: {action}")

    lines.append("")
    lines.append("SUMMARY")
    lines.append(f"  Total PIs  : {len(orig_pis)}")
    lines.append(f"  Errors     : {len(errors)}")
    lines.append(f"  Warnings   : {len(warns)}")
    lines.append(f"  Removed    : {removed}")
    lines.append(f"  Output PIs : {len(cleaned_pis)}")

    result = "PASS" if not issues else ("FAIL" if errors else "PASS WITH WARNINGS")
    lines.append(f"RESULT: {result}")
    lines.append("=" * 70)

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return lines


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_pipeline(input_csv:       str,
                 tolerance_m:     float = 2.0,
                 min_spacing_m:   float = 5.0,
                 min_tangent_m:   float = 20.0,
                 max_deflection:  float = 160.0,
                 auto_remove:     bool  = False,
                 out_csv:         str   = DEFAULT_OUT_CSV,
                 out_report:      str   = DEFAULT_OUT_REPORT) -> List[str]:
    log: List[str] = []
    log.append(f"Input  : {input_csv}")

    try:
        pis = read_alignment_pi(input_csv)
    except (FileNotFoundError, ValueError) as exc:
        log.append(f"[ERROR] {exc}")
        return log

    log.append(f"  {len(pis)} PI rows loaded")

    issues = run_checks(pis, tolerance_m, min_spacing_m, min_tangent_m, max_deflection)
    cleaned = apply_auto_remove(pis, issues) if auto_remove else pis

    params = dict(input_csv=input_csv, tolerance_m=tolerance_m,
                  min_spacing_m=min_spacing_m, min_tangent_m=min_tangent_m)

    write_cleaned_csv(pis, cleaned, issues, out_csv)
    log.append(f"CSV    : {out_csv}  ({len(cleaned)} PIs)")

    report_lines = write_report(pis, cleaned, issues, params, out_report)
    log.append(f"Report : {out_report}")
    log.append("")
    log.extend(report_lines)
    return log


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

def _launch_gui() -> None:
    try:
        import tkinter as tk
        from tkinter import ttk, filedialog, scrolledtext
    except ImportError:
        print("Tkinter unavailable — use --cli mode")
        sys.exit(1)

    root = tk.Tk()
    root.title("Alignment PI Quality Control")
    root.configure(bg="#1c2030")
    root.geometry("720x620")

    BG, FG, AMBER = "#1c2030", "#f0f0f0", "#F0A500"
    BG_P = "#252a3a"

    def _lrow(parent, label, var, pick_fn=None, w=50):
        f = tk.Frame(parent, bg=BG_P)
        f.pack(fill="x", padx=10, pady=3)
        tk.Label(f, text=label, bg=BG_P, fg="#9098b0",
                 width=18, anchor="w").pack(side="left")
        ttk.Entry(f, textvariable=var, width=w).pack(side="left", padx=4)
        if pick_fn:
            ttk.Button(f, text="…", width=3, command=pick_fn).pack(side="left")

    frm = tk.Frame(root, bg="#252a3a", pady=6)
    frm.pack(fill="x")
    tk.Label(frm, text="Alignment PI QC", bg="#252a3a", fg=AMBER,
             font=("Segoe UI", 12, "bold"), padx=12).pack(side="left")

    body = tk.Frame(root, bg=BG_P)
    body.pack(fill="x", pady=4)

    in_var   = tk.StringVar(value=os.path.join(ROOT, "csv", "alignment_pi.csv"))
    csv_var  = tk.StringVar(value=DEFAULT_OUT_CSV)
    rpt_var  = tk.StringVar(value=DEFAULT_OUT_REPORT)
    tol_var  = tk.StringVar(value="2.0")
    spc_var  = tk.StringVar(value="5.0")
    tan_var  = tk.StringVar(value="20.0")
    def_var  = tk.StringVar(value="160.0")
    auto_var = tk.BooleanVar(value=False)

    _lrow(body, "alignment_pi.csv",    in_var,  lambda: in_var.set(
        filedialog.askopenfilename(filetypes=[("CSV","*.csv"),("All","*.*")]) or in_var.get()))
    _lrow(body, "Output CSV",          csv_var, lambda: csv_var.set(
        filedialog.asksaveasfilename(defaultextension=".csv") or csv_var.get()))
    _lrow(body, "Output report",       rpt_var, lambda: rpt_var.set(
        filedialog.asksaveasfilename(defaultextension=".txt") or rpt_var.get()))
    _lrow(body, "Tolerance (m)",       tol_var, w=12)
    _lrow(body, "Min spacing (m)",     spc_var, w=12)
    _lrow(body, "Min tangent (m)",     tan_var, w=12)
    _lrow(body, "Max deflection (°)",  def_var, w=12)

    opt = tk.Frame(body, bg=BG_P)
    opt.pack(fill="x", padx=10, pady=3)
    ttk.Checkbutton(opt, text="Auto-remove DUPLICATE and COORD_OUTLIER errors",
                    variable=auto_var).pack(side="left")

    log_box = scrolledtext.ScrolledText(root, bg="#0d1117", fg=FG, height=16,
                                        font=("Courier New", 9), relief="flat")
    log_box.tag_configure("ok",    foreground="#28a745")
    log_box.tag_configure("warn",  foreground="#ffc107")
    log_box.tag_configure("error", foreground="#dc3545")
    log_box.pack(fill="both", expand=True, padx=10, pady=6)

    def _run():
        log_box.configure(state="normal")
        log_box.delete("1.0", "end")
        try:
            tol = float(tol_var.get())
            spc = float(spc_var.get())
            tan = float(tan_var.get())
            dfl = float(def_var.get())
        except ValueError:
            log_box.insert("end", "[ERROR] Non-numeric parameter value\n", "error")
            log_box.configure(state="disabled")
            return
        for line in run_pipeline(in_var.get(), tol, spc, tan, dfl,
                                 auto_var.get(), csv_var.get(), rpt_var.get()):
            tag = "ok" if line.startswith("RESULT: PASS") or line.startswith("OK") else \
                  "warn" if "WARN" in line else \
                  "error" if "ERROR" in line or "FAIL" in line else ""
            log_box.insert("end", line + "\n", tag)
        log_box.configure(state="disabled")

    btn_row = tk.Frame(root, bg=BG)
    btn_row.pack(pady=4)
    ttk.Button(btn_row, text="▶  Run QC", command=_run).pack(side="left", padx=6)
    ttk.Button(btn_row, text="Close",     command=root.destroy).pack(side="left")

    root.mainloop()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def run_cli(args: list) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        prog="alignment_qc.py --cli",
        description="Alignment PI Quality Control — detect outliers, duplicates, bad spirals",
    )
    parser.add_argument("input_csv",        help="Path to alignment_pi.csv")
    parser.add_argument("--tolerance",      type=float, default=2.0, dest="tolerance_m",
                        help="Centreline offset tolerance in metres (default 2.0)")
    parser.add_argument("--min-spacing",    type=float, default=5.0, dest="min_spacing_m",
                        help="Minimum PI spacing in metres (default 5.0)")
    parser.add_argument("--min-tangent",    type=float, default=20.0, dest="min_tangent_m",
                        help="Minimum tangent between curves in metres (default 20.0)")
    parser.add_argument("--max-deflection", type=float, default=160.0, dest="max_deflection",
                        help="Maximum deflection angle in degrees (default 160.0)")
    parser.add_argument("--auto-remove",    action="store_true",
                        help="Remove removable ERROR rows from output CSV")
    parser.add_argument("--out-csv",        default=DEFAULT_OUT_CSV,    dest="out_csv")
    parser.add_argument("--out-report",     default=DEFAULT_OUT_REPORT, dest="out_report")
    parsed = parser.parse_args(args)

    lines = run_pipeline(
        parsed.input_csv, parsed.tolerance_m, parsed.min_spacing_m,
        parsed.min_tangent_m, parsed.max_deflection, parsed.auto_remove,
        parsed.out_csv, parsed.out_report,
    )
    for line in lines:
        print(line)

    errors = sum(1 for l in lines if "[ERROR]" in l or "RESULT: FAIL" == l.strip())
    return 1 if errors else 0


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] == "--cli":
        sys.exit(run_cli(argv[1:]))
    _launch_gui()


if __name__ == "__main__":
    main()
