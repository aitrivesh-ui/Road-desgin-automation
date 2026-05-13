# -*- coding: utf-8 -*-
"""Core preflight checks (stdlib only — no tkinter)."""
from __future__ import annotations

import csv
import json
import os

# Path keys in project.json -> required CSV columns (exact names, extra columns OK).
CSV_PATH_KEYS: dict[str, list[str]] = {
    "alignment_pi": [
        "pi_id",
        "easting",
        "northing",
        "radius_m",
        "spiral_in_m",
        "spiral_out_m",
        "design_speed_kph",
    ],
    "profile_pvis": [
        "station_m",
        "elevation_m",
        "k_crest",
        "k_sag",
        "curve_length_m",
    ],
    "section_widths": [
        "region_id",
        "start_sta",
        "end_sta",
        "lane_width_m",
        "shoulder_l_m",
        "shoulder_r_m",
        "target_l",
        "target_r",
    ],
    "signage": [
        "row",
        "station_m",
        "offset_m",
        "side",
        "sign_code",
        "block_name",
        "rotation_deg",
    ],
    "payitems": ["source", "key", "pay_item", "description", "unit"],
}

VOLUMES_HEADERS = [
    "corridor",
    "eg_surface",
    "fg_surface",
    "volume_surface",
    "cut_m3",
    "fill_m3",
    "net_m3",
]


def root_from_project_json(project_json: str) -> str:
    base = os.path.dirname(os.path.abspath(project_json))
    return os.path.normpath(os.path.join(base, ".."))


def resolve_path(root: str, rel: str) -> str:
    rel = rel.replace("/", os.sep)
    return os.path.normpath(os.path.join(root, rel))


def read_header_row(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        row = next(csv.reader(f), [])
    return [h.strip() for h in row]


def _read_data_rows(path: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            rows.append({k: (v or "").strip() if v is not None else "" for k, v in row.items()})
    return rows


def _strict_data_checks(root: str, paths: dict) -> list[str]:
    """Extra rules for data quality (optional --strict)."""
    out: list[str] = []

    rel = paths.get("alignment_pi")
    if rel:
        full = resolve_path(root, rel)
        if os.path.isfile(full):
            rows = _read_data_rows(full)
            pis = [r for r in rows if r.get("pi_id") or r.get("easting") or r.get("northing")]
            if len(pis) < 2:
                out.append(
                    "ERROR: Strict — alignment_pi.csv needs at least 2 PI data rows (found %d)." % len(pis)
                )
            else:
                out.append("OK: Strict — alignment has %d PI row(s)." % len(pis))

    rel = paths.get("profile_pvis")
    if rel:
        full = resolve_path(root, rel)
        if os.path.isfile(full):
            rows = _read_data_rows(full)
            stations: list[float] = []
            bad = False
            for r in rows:
                if not r.get("station_m"):
                    continue
                try:
                    stations.append(float(r["station_m"]))
                except ValueError:
                    out.append("ERROR: Strict — profile_pvis.csv has non-numeric station_m.")
                    bad = True
                    break
            if not bad and len(stations) >= 2:
                prev = stations[0]
                ok_inc = True
                for s in stations[1:]:
                    if s <= prev:
                        ok_inc = False
                        break
                    prev = s
                if not ok_inc:
                    out.append(
                        "ERROR: Strict — profile_pvis.csv station_m values must be strictly increasing."
                    )
                else:
                    out.append("OK: Strict — profile stations strictly increasing (%d points)." % len(stations))
            elif not bad and len(stations) < 2:
                out.append("WARN: Strict — fewer than 2 profile points; M2 may still run if Civil accepts.")

    rel = paths.get("section_widths")
    if rel:
        full = resolve_path(root, rel)
        if os.path.isfile(full):
            rows = _read_data_rows(full)
            intervals: list[tuple[float, float, str]] = []
            for r in rows:
                rid = r.get("region_id", "?")
                if not r.get("start_sta") or not r.get("end_sta"):
                    continue
                try:
                    s0 = float(r["start_sta"])
                    s1 = float(r["end_sta"])
                except ValueError:
                    out.append("ERROR: Strict — section_widths.csv has non-numeric start_sta/end_sta.")
                    continue
                if s0 >= s1:
                    out.append(
                        "ERROR: Strict — region %s: start_sta must be < end_sta (got %s, %s)."
                        % (rid, s0, s1)
                    )
                intervals.append((s0, s1, rid))
            intervals.sort(key=lambda x: x[0])
            for i in range(1, len(intervals)):
                a0, a1, ar = intervals[i - 1]
                b0, b1, br = intervals[i]
                if b0 < a1:
                    out.append(
                        "ERROR: Strict — overlapping regions %s and %s (stations %.4f–%.4f vs %.4f–%.4f)."
                        % (ar, br, a0, a1, b0, b1)
                    )
                    break
            else:
                if intervals:
                    out.append("OK: Strict — %d corridor region row(s), no station overlap." % len(intervals))

    return out


def validate_project(project_json: str, strict: bool = False) -> list[str]:
    lines: list[str] = []
    if not os.path.isfile(project_json):
        lines.append("ERROR: project.json not found at: " + project_json)
        return lines

    root = root_from_project_json(project_json)
    lines.append("Package root: " + root)
    lines.append("Config file: " + os.path.abspath(project_json))
    lines.append("")

    try:
        with open(project_json, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except json.JSONDecodeError as ex:
        lines.append("ERROR: Invalid JSON: " + str(ex))
        return lines

    paths = cfg.get("paths") or {}
    if not paths:
        lines.append("WARN: No paths object in project.json.")
        return lines

    for key, required in CSV_PATH_KEYS.items():
        rel = paths.get(key)
        if not rel:
            lines.append("WARN: paths.%s is missing in project.json." % key)
            continue
        full = resolve_path(root, rel)
        if not os.path.isfile(full):
            lines.append(
                "ERROR: Input CSV missing (%s): %s — Civil scripts will say CSV not found."
                % (key, full)
            )
            continue
        try:
            headers = read_header_row(full)
        except Exception as ex:
            lines.append("ERROR: Cannot read %s: %s" % (full, ex))
            continue
        header_set = set(headers)
        missing = [c for c in required if c not in header_set]
        if missing:
            lines.append(
                "ERROR: %s — missing column(s): %s"
                % (os.path.basename(full), ", ".join(missing))
            )
        else:
            lines.append("OK: %s — columns match." % os.path.basename(full))

    vol_rel = paths.get("volumes_csv")
    if vol_rel:
        vol_full = resolve_path(root, vol_rel)
        d = os.path.dirname(vol_full)
        if d and not os.path.isdir(d):
            lines.append(
                "WARN: Folder for volumes CSV does not exist yet: %s (M4 can create the file; create folder if needed.)"
                % d
            )
        if os.path.isfile(vol_full):
            headers = read_header_row(vol_full)
            missing = [c for c in VOLUMES_HEADERS if c not in set(headers)]
            if missing:
                lines.append(
                    "ERROR: volumes file has wrong columns (expected M4 output): missing %s"
                    % ", ".join(missing)
                )
            else:
                lines.append("OK: volumes CSV exists and looks like M4 output.")
        else:
            lines.append(
                "INFO: volumes CSV not created yet (normal before you run M4): %s"
                % vol_full
            )

    boq_rel = paths.get("boq_csv")
    if boq_rel:
        boq_full = resolve_path(root, boq_rel)
        bd = os.path.dirname(boq_full)
        if bd and not os.path.isdir(bd):
            lines.append(
                "INFO: BOQ output folder will be created by M7 if missing: %s" % bd
            )

    if strict:
        lines.append("")
        lines.append("--- Strict data checks ---")
        lines.extend(_strict_data_checks(root, paths))

    lines.append("")
    lines.append("Next: Copy the config path above into Dynamo Player IN[0] for m8_run_all.py (use absolute path).")
    return lines


def validation_failed(lines: list[str]) -> bool:
    return any(line.startswith("ERROR:") for line in lines)
