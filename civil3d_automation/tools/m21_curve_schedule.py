"""
m21_curve_schedule.py — M21 Curve Schedule
Computes horizontal and vertical curve parameters, validates against
Austroads design speed tables, and flags clothoid, K-value, and SSD issues.

CLI:
  python m21_curve_schedule.py --cli alignment_pi.csv profile_pvis.csv
  python m21_curve_schedule.py --cli alignment_pi.csv profile_pvis.csv \
      --out-csv out/curve_schedule.csv --out-report out/curve_schedule_report.txt
"""

import csv as _csv
import math
import os
import sys
from typing import List, NamedTuple, Optional, Tuple

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

DEFAULT_CSV_OUT    = os.path.join(ROOT, "out", "curve_schedule.csv")
DEFAULT_REPORT_OUT = os.path.join(ROOT, "out", "curve_schedule_report.txt")

# ---------------------------------------------------------------------------
# Austroads 6th Edition Table 6.6 / 6.7 — minimum K-values by design speed
# ---------------------------------------------------------------------------
K_CREST_MIN: dict = {60: 10, 70: 17, 80: 26, 90: 39, 100: 55, 110: 75, 120: 100, 130: 130}
K_SAG_MIN:   dict = {60:  8, 70: 12, 80: 16, 90: 21, 100: 27, 110:  34, 120:  43, 130:  54}

# Friction-banking minimum radius constants
_E, _F = 0.07, 0.14          # superelevation, lateral friction factor

# Clothoid adequacy thresholds (A = sqrt(R * L_s))
_CLOTHOID_DESIRABLE_RATIO = 1.0 / 3.0   # A_min_desirable = R / sqrt(3)
_CLOTHOID_ABSOLUTE_RATIO  = 1.0 / 9.0   # A_min_absolute  = R / 3

# Sight distance: driver eye height h1=1.15 m, object height h2=0.20 m (Austroads)
_H1 = 1.15
_H2 = 0.20

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
class PIRow(NamedTuple):
    pi_id:           str
    easting:         float
    northing:        float
    radius_m:        float
    spiral_in_m:     float
    spiral_out_m:    float
    design_speed_kph: float


class PVIRow(NamedTuple):
    idx:             int
    station_m:       float
    elevation_m:     float
    k_crest:         float
    k_sag:           float
    curve_length_m:  float


class HCurveResult(NamedTuple):
    pi_id:             str
    station_approx_m:  Optional[float]
    delta_deg:         float
    turn:              str           # "L", "R", or "—"
    radius_m:          float
    spiral_in_m:       float
    spiral_out_m:      float
    tangent_m:         float
    curve_length_m:    float
    A_in:              Optional[float]
    A_out:             Optional[float]
    R_min:             float
    design_speed_kph:  float
    status:            str           # OK / WARN / ERROR
    notes:             str


class VCurveResult(NamedTuple):
    pvi_index:              int
    station_m:              float
    grade_in_pct:           float
    grade_out_pct:          float
    delta_g_pct:            float
    curve_type:             str      # "crest", "sag", or "grade"
    k_provided:             float
    k_min_req:              int
    curve_length_provided_m: float
    curve_length_min_req_m: float
    design_speed_kph:       float
    status:                 str
    notes:                  str


# ---------------------------------------------------------------------------
# CSV readers
# ---------------------------------------------------------------------------
_PI_COLS   = {"pi_id", "easting", "northing", "radius_m",
              "spiral_in_m", "spiral_out_m", "design_speed_kph"}
_PVI_COLS  = {"station_m", "elevation_m", "k_crest", "k_sag", "curve_length_m"}


def _flt(row: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return default


def read_alignment_pi(path: str) -> List[PIRow]:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"alignment_pi.csv not found: {path}")
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = _csv.DictReader(f)
        missing = _PI_COLS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"alignment_pi.csv missing columns: {', '.join(sorted(missing))}")
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


def read_profile_pvis(path: str) -> List[PVIRow]:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"profile_pvis.csv not found: {path}")
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = _csv.DictReader(f)
        missing = _PVI_COLS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"profile_pvis.csv missing columns: {', '.join(sorted(missing))}")
        rows = []
        for i, row in enumerate(reader, 2):
            rows.append(PVIRow(
                idx            = i - 1,
                station_m      = _flt(row, "station_m"),
                elevation_m    = _flt(row, "elevation_m"),
                k_crest        = _flt(row, "k_crest"),
                k_sag          = _flt(row, "k_sag"),
                curve_length_m = _flt(row, "curve_length_m"),
            ))
    return rows


# ---------------------------------------------------------------------------
# Horizontal curve computation
# ---------------------------------------------------------------------------
def _bearing(dx: float, dy: float) -> float:
    """Bearing in radians from north, clockwise (surveyors' convention)."""
    return math.atan2(dx, dy)


def _nearest_speed(v: float, table: dict) -> int:
    """Round design speed to nearest key in lookup table."""
    keys = sorted(table.keys())
    return min(keys, key=lambda k: abs(k - v))


def _r_min(v_kph: float) -> float:
    return v_kph ** 2 / (127.0 * (_E + _F))


def _clothoid_status(R: float, A: Optional[float]) -> Tuple[str, str]:
    """Return (status, note) for a clothoid parameter A given radius R."""
    if A is None:
        return "OK", ""
    A_des = math.sqrt(R * R * _CLOTHOID_DESIRABLE_RATIO)
    A_abs = math.sqrt(R * R * _CLOTHOID_ABSOLUTE_RATIO)
    if A < A_abs:
        return "ERROR", f"A={A:.1f} < absolute min {A_abs:.1f} (R/{int(1/_CLOTHOID_ABSOLUTE_RATIO)})"
    if A < A_des:
        return "WARN",  f"A={A:.1f} < desirable {A_des:.1f} (R/{int(1/_CLOTHOID_DESIRABLE_RATIO)})"
    return "OK", ""


def compute_horizontal_curves(pis: List[PIRow]) -> List[HCurveResult]:
    results: List[HCurveResult] = []
    n = len(pis)
    if n < 2:
        return results

    for i in range(1, n - 1):
        prev, cur, nxt = pis[i - 1], pis[i], pis[i + 1]

        # Bearings of incoming and outgoing tangents
        b_in  = _bearing(cur.easting - prev.easting,  cur.northing - prev.northing)
        b_out = _bearing(nxt.easting  - cur.easting,  nxt.northing  - cur.northing)

        # Deflection angle (always 0–180°)
        delta_rad = b_out - b_in
        while delta_rad >  math.pi: delta_rad -= 2 * math.pi
        while delta_rad < -math.pi: delta_rad += 2 * math.pi

        turn      = "R" if delta_rad < 0 else "L" if delta_rad > 0 else "—"
        delta_deg = abs(math.degrees(delta_rad))
        delta_rad = abs(delta_rad)

        R = cur.radius_m
        Ls_in  = cur.spiral_in_m
        Ls_out = cur.spiral_out_m

        notes_parts: List[str] = []

        # Tangent point — skip curve geometry
        if R == 0:
            results.append(HCurveResult(
                pi_id=cur.pi_id, station_approx_m=None,
                delta_deg=delta_deg, turn=turn,
                radius_m=0, spiral_in_m=0, spiral_out_m=0,
                tangent_m=0, curve_length_m=0,
                A_in=None, A_out=None, R_min=0,
                design_speed_kph=cur.design_speed_kph,
                status="OK", notes="Tangent (radius=0)",
            ))
            continue

        # Circular tangent length T = R·tan(Δ/2)
        tan_half = math.tan(delta_rad / 2.0)
        T_circ   = R * tan_half

        # Spiral contribution
        A_in  = math.sqrt(R * Ls_in)  if Ls_in  > 0 else None
        A_out = math.sqrt(R * Ls_out) if Ls_out > 0 else None

        # Spiral angle (radians)
        theta_in  = Ls_in  / (2 * R) if Ls_in  > 0 else 0.0
        theta_out = Ls_out / (2 * R) if Ls_out > 0 else 0.0

        delta_circ = max(0.0, delta_rad - theta_in - theta_out)
        L_circ = R * delta_circ
        T_total = R * math.tan((delta_rad - theta_in - theta_out) / 2.0 + (theta_in + theta_out) / 2.0) \
                  + Ls_in / 2.0 + Ls_out / 2.0 if (Ls_in + Ls_out) > 0 else T_circ
        L_total = Ls_in + L_circ + Ls_out

        # Minimum radius
        R_min = _r_min(cur.design_speed_kph)

        # Status — start with most severe
        status = "OK"

        if R < R_min:
            status = "ERROR"
            notes_parts.append(f"R={R:.0f}<Rmin={R_min:.0f}")

        for A_val, label in [(A_in, "in"), (A_out, "out")]:
            s, note = _clothoid_status(R, A_val)
            if note:
                notes_parts.append(f"spiral_{label}: {note}")
            if s == "ERROR":
                status = "ERROR"
            elif s == "WARN" and status == "OK":
                status = "WARN"

        results.append(HCurveResult(
            pi_id=cur.pi_id,
            station_approx_m=None,
            delta_deg=round(delta_deg, 4),
            turn=turn,
            radius_m=R,
            spiral_in_m=Ls_in,
            spiral_out_m=Ls_out,
            tangent_m=round(T_total, 3),
            curve_length_m=round(L_total, 3),
            A_in=round(A_in, 2) if A_in else None,
            A_out=round(A_out, 2) if A_out else None,
            R_min=round(R_min, 1),
            design_speed_kph=cur.design_speed_kph,
            status=status,
            notes="; ".join(notes_parts) if notes_parts else "",
        ))

    # Compound / reverse curve detection (second pass)
    _flag_compound_reverse(results, pis)

    return results


def _flag_compound_reverse(results: List[HCurveResult], pis: List[PIRow]) -> None:
    """Mutate result notes for compound and reverse curves (in-place rebuild)."""
    for j in range(1, len(results)):
        prev_r = results[j - 1]
        cur_r  = results[j]
        if prev_r.radius_m == 0 or cur_r.radius_m == 0:
            continue

        same_dir = (prev_r.turn == cur_r.turn)
        diff_rad = abs(prev_r.radius_m - cur_r.radius_m) > 0.5

        if same_dir and diff_rad:
            extra = "Compound curve — different radii, same direction"
            results[j] = cur_r._replace(
                status="WARN" if cur_r.status == "OK" else cur_r.status,
                notes=(cur_r.notes + "; " + extra).lstrip("; "),
            )

        if not same_dir and prev_r.curve_length_m > 0 and cur_r.curve_length_m > 0:
            # Check available tangent length between curves
            # Approximation: distance PI[i] to PI[i+1] minus both tangent lengths
            pi_prev = pis[j]      # interior PI for results[j-1]
            pi_cur  = pis[j + 1]  # interior PI for results[j]
            dist = math.hypot(pi_cur.easting - pi_prev.easting,
                               pi_cur.northing - pi_prev.northing)
            avail_tangent = dist - prev_r.tangent_m - cur_r.tangent_m
            if avail_tangent < 2 * max(prev_r.tangent_m, cur_r.tangent_m):
                extra = f"Reverse curve — short tangent avail={avail_tangent:.1f} m"
                results[j] = cur_r._replace(
                    status="WARN" if cur_r.status == "OK" else cur_r.status,
                    notes=(cur_r.notes + "; " + extra).lstrip("; "),
                )


# ---------------------------------------------------------------------------
# Vertical curve computation
# ---------------------------------------------------------------------------
def _ssd(v_kph: float) -> float:
    """Stopping sight distance (m) — Austroads formula."""
    v_ms = v_kph / 3.6
    return v_ms * 2.5 + v_ms ** 2 / (2.0 * 3.4)


def _l_crest_ssd(ssd: float) -> float:
    """Minimum crest curve length for SSD (object height 0.20 m)."""
    denom = (math.sqrt(2 * _H1) + math.sqrt(2 * _H2)) ** 2
    return ssd ** 2 / denom * 100  # factor of 100 converts % to fraction


def compute_vertical_curves(pvis: List[PVIRow],
                             default_speed: float = 80.0) -> List[VCurveResult]:
    results: List[VCurveResult] = []
    n = len(pvis)
    if n < 3:
        return results

    for i in range(1, n - 1):
        prev, cur, nxt = pvis[i - 1], pvis[i], pvis[i + 1]

        dsta1 = cur.station_m - prev.station_m
        dsta2 = nxt.station_m - cur.station_m
        if dsta1 <= 0 or dsta2 <= 0:
            continue

        g1 = (cur.elevation_m  - prev.elevation_m) / dsta1 * 100.0
        g2 = (nxt.elevation_m  - cur.elevation_m)  / dsta2 * 100.0
        dg = g2 - g1

        if abs(dg) < 0.01:
            results.append(VCurveResult(
                pvi_index=i, station_m=cur.station_m,
                grade_in_pct=round(g1,3), grade_out_pct=round(g2,3),
                delta_g_pct=round(dg,3), curve_type="grade",
                k_provided=0, k_min_req=0,
                curve_length_provided_m=0, curve_length_min_req_m=0,
                design_speed_kph=default_speed,
                status="OK", notes="Grade tangent — no vertical curve",
            ))
            continue

        curve_type = "crest" if dg < 0 else "sag"

        # K-value from user input
        k_provided = cur.k_crest if curve_type == "crest" else cur.k_sag
        speed      = default_speed   # TODO: interpolate from alignment if linked
        speed_key  = _nearest_speed(speed, K_CREST_MIN)
        k_min      = K_CREST_MIN[speed_key] if curve_type == "crest" else K_SAG_MIN[speed_key]

        L_provided = cur.curve_length_m if cur.curve_length_m > 0 \
                     else k_provided * abs(dg) if k_provided > 0 else 0.0
        L_min_req  = k_min * abs(dg)

        notes_parts: List[str] = []
        status = "OK"

        if k_provided == 0 and cur.curve_length_m == 0:
            status = "WARN"
            notes_parts.append("No K or curve length supplied")
        elif k_provided < k_min:
            lvl = "ERROR" if k_provided < k_min * 0.8 else "WARN"
            status = lvl
            notes_parts.append(f"K={k_provided}<K_min={k_min} at {speed_key} km/h")

        # Crest SSD check
        if curve_type == "crest" and L_provided > 0:
            ssd = _ssd(speed)
            L_ssd = _l_crest_ssd(ssd)
            if L_provided < L_ssd:
                if status == "OK":
                    status = "WARN"
                notes_parts.append(f"SSD={ssd:.0f}m needs L≥{L_ssd:.0f}m (have {L_provided:.0f}m)")

        results.append(VCurveResult(
            pvi_index=i,
            station_m=cur.station_m,
            grade_in_pct=round(g1, 3),
            grade_out_pct=round(g2, 3),
            delta_g_pct=round(dg, 3),
            curve_type=curve_type,
            k_provided=k_provided,
            k_min_req=k_min,
            curve_length_provided_m=round(L_provided, 1),
            curve_length_min_req_m=round(L_min_req, 1),
            design_speed_kph=speed,
            status=status,
            notes="; ".join(notes_parts),
        ))

    return results


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------
_H_CSV = [
    "pi_id", "delta_deg", "turn", "radius_m", "spiral_in_m", "spiral_out_m",
    "tangent_m", "curve_length_m", "A_in", "A_out", "R_min",
    "design_speed_kph", "status", "notes",
]
_V_CSV = [
    "pvi_index", "station_m", "grade_in_pct", "grade_out_pct", "delta_g_pct",
    "curve_type", "k_provided", "k_min_req",
    "curve_length_provided_m", "curve_length_min_req_m",
    "design_speed_kph", "status", "notes",
]


def write_csv(h_results: List[HCurveResult], v_results: List[VCurveResult],
              path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = _csv.writer(f)
        w.writerow(["# HORIZONTAL CURVES"])
        w.writerow(_H_CSV)
        for r in h_results:
            w.writerow([
                r.pi_id, r.delta_deg, r.turn, r.radius_m,
                r.spiral_in_m, r.spiral_out_m, r.tangent_m, r.curve_length_m,
                r.A_in if r.A_in is not None else "",
                r.A_out if r.A_out is not None else "",
                r.R_min, r.design_speed_kph, r.status, r.notes,
            ])
        w.writerow([])
        w.writerow(["# VERTICAL CURVES"])
        w.writerow(_V_CSV)
        for r in v_results:
            w.writerow([
                r.pvi_index, r.station_m, r.grade_in_pct, r.grade_out_pct,
                r.delta_g_pct, r.curve_type, r.k_provided, r.k_min_req,
                r.curve_length_provided_m, r.curve_length_min_req_m,
                r.design_speed_kph, r.status, r.notes,
            ])


def _summary_line(label: str, items: list, key: str) -> str:
    counts = {"OK": 0, "WARN": 0, "ERROR": 0}
    for r in items:
        counts[getattr(r, key, "OK")] = counts.get(getattr(r, key, "OK"), 0) + 1
    return (f"  {label}: {len(items)} curves — "
            f"OK={counts['OK']} WARN={counts['WARN']} ERROR={counts['ERROR']}")


def write_report(h_results: List[HCurveResult], v_results: List[VCurveResult],
                 path: str) -> List[str]:
    lines: List[str] = []
    lines.append("=" * 70)
    lines.append("CURVE SCHEDULE REPORT")
    lines.append("=" * 70)
    lines.append("")
    lines.append("HORIZONTAL CURVES")
    lines.append("-" * 70)
    for r in h_results:
        if r.notes or r.status != "OK":
            lines.append(f"[{r.status:5s}] PI {r.pi_id}: R={r.radius_m:.0f}m  "
                         f"Δ={r.delta_deg:.2f}°  T={r.tangent_m:.1f}m  "
                         f"L={r.curve_length_m:.1f}m  {r.notes}")
        else:
            lines.append(f"[OK   ] PI {r.pi_id}: R={r.radius_m:.0f}m  "
                         f"Δ={r.delta_deg:.2f}°  T={r.tangent_m:.1f}m  L={r.curve_length_m:.1f}m")
    lines.append(_summary_line("Horizontal", [r for r in h_results if r.radius_m > 0], "status"))
    lines.append("")
    lines.append("VERTICAL CURVES")
    lines.append("-" * 70)
    for r in v_results:
        if r.curve_type == "grade":
            continue
        lines.append(f"[{r.status:5s}] PVI sta={r.station_m:.1f}m  {r.curve_type.upper()}  "
                     f"Δg={r.delta_g_pct:+.3f}%  K_prov={r.k_provided}  "
                     f"K_min={r.k_min_req}  L_min={r.curve_length_min_req_m:.1f}m"
                     + (f"  {r.notes}" if r.notes else ""))
    lines.append(_summary_line("Vertical", [r for r in v_results if r.curve_type != "grade"], "status"))
    lines.append("")

    all_errors = [r for r in h_results if r.status == "ERROR"] + \
                 [r for r in v_results if r.status == "ERROR"]
    all_warns  = [r for r in h_results if r.status == "WARN"]  + \
                 [r for r in v_results if r.status == "WARN"]
    result = "PASS" if not all_errors else "FAIL"
    if all_warns and not all_errors:
        result = "PASS WITH WARNINGS"
    lines.append(f"RESULT: {result}  ({len(all_errors)} error(s), {len(all_warns)} warning(s))")
    lines.append("=" * 70)

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return lines


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def run_pipeline(align_path: str, profile_path: str,
                 csv_out: str, report_out: str) -> List[str]:
    log: List[str] = []
    log.append(f"Alignment PI : {align_path}")
    log.append(f"Profile PVIs : {profile_path}")

    try:
        pis  = read_alignment_pi(align_path)
        pvis = read_profile_pvis(profile_path)
    except (FileNotFoundError, ValueError) as exc:
        log.append(f"[ERROR] {exc}")
        return log

    log.append(f"  {len(pis)} PI rows, {len(pvis)} PVI rows")

    h_results = compute_horizontal_curves(pis)
    v_results = compute_vertical_curves(pvis)

    write_csv(h_results, v_results, csv_out)
    log.append(f"CSV written  : {csv_out}")

    report_lines = write_report(h_results, v_results, report_out)
    log.append(f"Report written: {report_out}")
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
        print("Tkinter unavailable — use: python m21_curve_schedule.py --cli <align> <profile>")
        sys.exit(1)

    root = tk.Tk()
    root.title("M21 — Curve Schedule")
    root.configure(bg="#1c2030")
    root.geometry("700x540")

    BG, FG, AMBER = "#1c2030", "#f0f0f0", "#F0A500"

    def _row(parent, label, var, pick_fn):
        f = tk.Frame(parent, bg="#252a3a")
        f.pack(fill="x", padx=10, pady=3)
        tk.Label(f, text=label, bg="#252a3a", fg="#9098b0", width=16, anchor="w").pack(side="left")
        ttk.Entry(f, textvariable=var, width=50).pack(side="left", padx=4)
        ttk.Button(f, text="…", width=3, command=pick_fn).pack(side="left")

    frm = tk.Frame(root, bg="#252a3a", pady=6)
    frm.pack(fill="x")
    tk.Label(frm, text="M21  Curve Schedule", bg="#252a3a", fg=AMBER,
             font=("Segoe UI", 12, "bold"), padx=12).pack(side="left")

    body = tk.Frame(root, bg="#252a3a")
    body.pack(fill="x", pady=4)

    align_var   = tk.StringVar(value=os.path.join(ROOT, "csv", "alignment_pi.csv"))
    profile_var = tk.StringVar(value=os.path.join(ROOT, "csv", "profile_pvis.csv"))
    csv_var     = tk.StringVar(value=DEFAULT_CSV_OUT)
    report_var  = tk.StringVar(value=DEFAULT_REPORT_OUT)

    _row(body, "alignment_pi.csv",  align_var,   lambda: align_var.set(
         filedialog.askopenfilename(filetypes=[("CSV","*.csv"),("All","*.*")]) or align_var.get()))
    _row(body, "profile_pvis.csv",  profile_var, lambda: profile_var.set(
         filedialog.askopenfilename(filetypes=[("CSV","*.csv"),("All","*.*")]) or profile_var.get()))
    _row(body, "Output CSV",        csv_var,     lambda: csv_var.set(
         filedialog.asksaveasfilename(defaultextension=".csv",
             filetypes=[("CSV","*.csv")]) or csv_var.get()))
    _row(body, "Output report",     report_var,  lambda: report_var.set(
         filedialog.asksaveasfilename(defaultextension=".txt",
             filetypes=[("Text","*.txt")]) or report_var.get()))

    log_box = scrolledtext.ScrolledText(root, bg="#0d1117", fg=FG, height=16,
                                        font=("Courier New", 9), relief="flat")
    log_box.tag_configure("ok",    foreground="#28a745")
    log_box.tag_configure("warn",  foreground="#ffc107")
    log_box.tag_configure("error", foreground="#dc3545")
    log_box.pack(fill="both", expand=True, padx=10, pady=6)

    def _run():
        log_box.configure(state="normal")
        log_box.delete("1.0", "end")
        for line in run_pipeline(align_var.get(), profile_var.get(),
                                 csv_var.get(), report_var.get()):
            tag = "ok" if line.startswith("[OK") or line.startswith("OK") else \
                  "warn" if "WARN" in line else \
                  "error" if "ERROR" in line or "FAIL" in line else ""
            log_box.insert("end", line + "\n", tag)
        log_box.configure(state="disabled")

    btn_row = tk.Frame(root, bg=BG)
    btn_row.pack(pady=4)
    ttk.Button(btn_row, text="▶  Run", command=_run).pack(side="left", padx=6)
    ttk.Button(btn_row, text="Close",  command=root.destroy).pack(side="left")

    root.mainloop()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def run_cli(args: list) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        prog="m21_curve_schedule.py --cli",
        description="M21 Curve Schedule — validate horizontal and vertical curve geometry",
    )
    parser.add_argument("alignment_pi",  help="Path to alignment_pi.csv")
    parser.add_argument("profile_pvis",  help="Path to profile_pvis.csv")
    parser.add_argument("--out-csv",     default=DEFAULT_CSV_OUT,
                        dest="out_csv",  help="Output CSV path")
    parser.add_argument("--out-report",  default=DEFAULT_REPORT_OUT,
                        dest="out_report", help="Output report .txt path")
    parsed = parser.parse_args(args)

    lines = run_pipeline(parsed.alignment_pi, parsed.profile_pvis,
                         parsed.out_csv, parsed.out_report)
    for line in lines:
        print(line)

    errors = [l for l in lines if "[ERROR]" in l or "RESULT: FAIL" in l]
    return 1 if errors else 0


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] == "--cli":
        sys.exit(run_cli(argv[1:]))
    _launch_gui()


if __name__ == "__main__":
    main()
