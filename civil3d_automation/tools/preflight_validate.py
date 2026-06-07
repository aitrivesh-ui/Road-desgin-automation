# -*- coding: utf-8 -*-
"""Core preflight checks (stdlib only — no tkinter)."""
from __future__ import annotations

import csv
import json
import os
import sys

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
        "superelevation_pct",
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
    # M9 — road markings
    "road_markings": [
        "mark_id", "station_start_m", "station_end_m",
        "offset_m", "side", "mark_type", "width_m",
    ],
    # M10 — cross-sections (optional CSV, auto-generated if absent — warn only)
    # M11 — superelevation
    "superelevation": [
        "station_m", "left_slope_pct", "right_slope_pct", "transition_length_m",
    ],
    # M16 — pavement inputs
    "pavement_inputs": [
        "region_id", "start_sta", "end_sta",
        "traffic_esa_million", "subgrade_cbr", "design_life_years",
    ],
    # M17 — drainage catchments
    "catchments": [
        "catchment_id", "area_ha", "runoff_coeff",
        "tc_minutes", "rainfall_intensity_mmh",
        "station_m", "offset_m", "side",
    ],
    # M18 — intersections
    "intersections": [
        "int_id", "station_m", "road_name", "angle_deg",
        "left_turn_lanes", "right_turn_lanes", "radius_m", "approach_speed_kph",
    ],
    "markings_schedule": [
        "chainage_from",
        "chainage_to",
        "mark_type",
        "material",
        "offset_m",
        "source",
    ],
}

PAYITEM_OPTIONAL_COLS = ["qty_source", "morh_chapter", "rate_key"]

MARKINGS_VALID_MATERIALS = ("thermoplastic", "paint", "cold_plastic")

VOLUMES_HEADERS = [
    "record_type",
    "corridor",
    "eg_surface",
    "fg_surface",
    "volume_surface",
    "cut_m3",
    "fill_m3",
    "net_m3",
]

VOLUMES_HEADERS_SWELL = VOLUMES_HEADERS + [
    "cut_bank_m3",
    "fill_comp_m3",
    "cut_haul_m3",
    "fill_borrow_m3",
    "borrow_req_m3",
    "spoil_m3",
    "cut_loose_m3",
    "swell_factor",
    "shrink_factor",
    "soil_type",
]

MASS_HAUL_HEADERS = [
    "station_m",
    "ordinate_m3",
    "haul_direction",
    "cumulative_volume",
]

VALID_SOIL_TYPES = (
    "loose_rock",
    "ordinary_soil",
    "soft_rock",
    "hard_rock",
    "murrum",
    "moorum",
)


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
            if not bad and rows:
                n = len(rows)
                for idx, r in enumerate(rows):
                    try:
                        vc = float(r.get("curve_length_m", 0) or 0)
                    except ValueError:
                        continue
                    if vc > 0 and (idx == 0 or idx == n - 1):
                        out.append(
                            "WARN: profile_pvis.csv — curve_length_m at endpoint station %.1f; M2 cannot apply VC at first/last PVI."
                            % float(r.get("station_m", 0) or 0)
                        )

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


def _load_irc67_known_blocks(root: str) -> set[str]:
    cat_path = os.path.join(root, "config", "irc67_signage_catalogue.json")
    if not os.path.isfile(cat_path):
        return set()
    try:
        with open(cat_path, "r", encoding="utf-8") as f:
            cat = json.load(f)
        known = set(cat.get("known_block_names") or [])
        for sign in (cat.get("signs") or {}).values():
            bn = sign.get("block_name")
            if bn:
                known.add(bn)
        return known
    except (json.JSONDecodeError, OSError):
        return set()


def _check_signage_block_names(root: str, csv_path: str) -> list[str]:
    """WARN when block_name not in IRC:67 catalogue (DWG check is runtime M5)."""
    out: list[str] = []
    known = _load_irc67_known_blocks(root)
    if not known:
        return out
    try:
        rows = _read_data_rows(csv_path)
    except OSError:
        return out
    unknown: set[str] = set()
    for r in rows:
        bn = (r.get("block_name") or "").strip()
        if bn and bn not in known:
            unknown.add(bn)
    if unknown:
        out.append(
            "WARN: Signage block_name not in irc67_signage_catalogue.json: %s"
            % ", ".join(sorted(unknown))
        )
    return out


def _load_irc35_mark_types(root: str) -> set[str]:
    cat_path = os.path.join(root, "config", "irc35_markings_catalogue.json")
    if not os.path.isfile(cat_path):
        return set()
    try:
        with open(cat_path, "r", encoding="utf-8") as f:
            cat = json.load(f)
        return set((cat.get("mark_types") or {}).keys())
    except Exception:
        return set()


def _validate_markings_schedule_data(root: str, paths: dict) -> list[str]:
    out: list[str] = []
    rel = paths.get("markings_schedule")
    if not rel:
        return out
    full = resolve_path(root, rel)
    if not os.path.isfile(full):
        return out
    valid_types = _load_irc35_mark_types(root)
    if not valid_types:
        out.append("WARN: irc35_markings_catalogue.json missing — cannot validate mark_type codes.")
        return out
    rows = _read_data_rows(full)
    for i, r in enumerate(rows, start=2):
        mt = (r.get("mark_type") or "").strip().upper()
        if mt and mt not in valid_types:
            out.append(
                "ERROR: markings_schedule row %d — mark_type '%s' not in IRC35 catalogue." % (i, mt)
            )
        mat = (r.get("material") or "thermoplastic").strip().lower()
        if mat not in MARKINGS_VALID_MATERIALS:
            out.append(
                "ERROR: markings_schedule row %d — material '%s' must be one of %s."
                % (i, mat, ", ".join(MARKINGS_VALID_MATERIALS))
            )
        try:
            s0 = float(r.get("chainage_from", 0))
            s1 = float(r.get("chainage_to", 0))
            if s1 <= s0:
                out.append(
                    "ERROR: markings_schedule row %d — chainage_to must be greater than chainage_from."
                    % i
                )
        except ValueError:
            out.append("ERROR: markings_schedule row %d — non-numeric chainage." % i)
    if rows and not any(line.startswith("ERROR:") for line in out):
        out.append("OK: markings_schedule — %d row(s), mark types valid." % len(rows))
    return out


def _m3_step_enabled(cfg: dict) -> bool:
    pipeline = cfg.get("pipeline") or {}
    steps = pipeline.get("steps")
    if steps:
        return any(str(s).strip().lower() == "m3" for s in steps)
    if pipeline.get("skip_profile"):
        return True
    return True


def _validate_irc37_lookup(root: str, cfg: dict, irc: dict) -> list[str]:
    out: list[str] = []
    if not _m3_step_enabled(cfg):
        return out
    pydir = os.path.join(root, "python")
    if pydir not in sys.path:
        sys.path.insert(0, pydir)
    try:
        from irc37_engine import irc37_design  # noqa: WPS433
    except ImportError as ex:
        out.append("ERROR: Cannot import irc37_engine for preflight: %s" % ex)
        return out
    try:
        cbr = float(irc.get("cbr_pct", 0))
        msa = float(irc.get("msa", 0))
        climate = str(irc.get("climate", "moderate"))
        result = irc37_design(cbr, msa, climate)
    except (TypeError, ValueError) as ex:
        out.append("ERROR: design.irc37 lookup failed: %s" % ex)
        return out
    if result.get("empty"):
        out.append("ERROR: design.irc37 — no catalogue match for CBR/msa/climate.")
        return out
    layers = result.get("layers_mm") or {}
    out.append(
        "OK: IRC:37 lookup GSB=%s WMM=%s DBM=%s BC=%s mm."
        % (layers.get("GSB"), layers.get("WMM"), layers.get("DBM"), layers.get("BC"))
    )
    snapped = result.get("snapped") or {}
    cbr_s = float(snapped.get("cbr_pct", cbr))
    msa_s = float(snapped.get("msa", msa))
    if abs(cbr - cbr_s) > 1.0:
        out.append(
            "WARN: design.irc37 — CBR %.2f snapped to bin %.0f (delta > 1)."
            % (cbr, cbr_s)
        )
    if abs(msa - msa_s) > 15.0:
        out.append(
            "WARN: design.irc37 — msa %.2f snapped to bin %.0f (delta > 15)."
            % (msa, msa_s)
        )
    if result.get("fallback"):
        out.append("WARN: design.irc37 — nearest catalogue key used: %s." % snapped.get("key"))
    return out


def _boq_core_module(root: str):
    py = os.path.join(root, "python")
    if py not in sys.path:
        sys.path.insert(0, py)
    import boq_core  # noqa: WPS433

    return boq_core


def _validate_payitems_boq(root: str, paths: dict, cfg: dict) -> list[str]:
    out: list[str] = []
    rel = paths.get("payitems")
    if not rel:
        return out
    full = resolve_path(root, rel)
    if not os.path.isfile(full):
        out.append("WARN: payitems CSV not found: %s" % full)
        return out
    headers = read_header_row(full)
    missing_opt = [c for c in PAYITEM_OPTIONAL_COLS if c not in headers]
    if missing_opt:
        out.append(
            "WARN: payitems.csv missing optional BOQ columns: %s (Schedule A / preflight qty_source)."
            % ", ".join(missing_opt)
        )
    else:
        out.append("OK: payitems.csv has qty_source, morh_chapter, rate_key columns.")

    try:
        bc = _boq_core_module(root)
    except Exception as ex:
        out.append("WARN: Cannot import boq_core for payitems validation: %s" % ex)
        return out

    providers = bc.known_qty_providers(paths, root)
    vol_path = paths.get("volumes_csv")
    vol_full = resolve_path(root, vol_path) if vol_path else ""
    has_corrected = bc.volume_summary_has_corrected(vol_full) if vol_full else False

    rows = _read_data_rows(full)
    for r in rows:
        qs = (r.get("qty_source") or "").strip()
        src = r.get("source", "").strip()
        key = r.get("key", "").strip()
        if qs and "." in qs:
            p_src, p_key = qs.split(".", 1)
            pair = (p_src.strip(), p_key.strip())
        else:
            pair = (src, key)
        if pair[0] == "pavement" and not paths.get("irc37_cache") and not paths.get("pavement_irc37"):
            out.append(
                "WARN: payitems %s|%s — pavement qty needs paths.irc37_cache and design.paved_width_m."
                % pair
            )
        elif pair[0] in ("volumes", "pavement") and pair not in providers:
            if pair[0] == "volumes" and pair[1] in ("cut_haul_m3", "fill_borrow_m3"):
                if vol_full and os.path.isfile(vol_full) and not has_corrected:
                    out.append(
                        "WARN: payitems %s — volumes CSV lacks corrected columns %s; re-run M4 swell/shrink."
                        % (qs or "%s.%s" % pair, pair[1])
                    )
                elif not vol_full or not os.path.isfile(vol_full):
                    out.append(
                        "WARN: payitems %s — volumes_csv not found yet; earthwork lines may be empty in BOQ."
                        % (qs or "%s.%s" % pair)
                    )
            else:
                out.append(
                    "WARN: payitems %s — quantity not in static providers (may come from DWG scan at M7 run)."
                    % (qs or "%s.%s" % pair)
                )
        elif pair[0] == "marking" and ("marking_quantities" not in paths or not paths.get("marking_quantities")):
            out.append(
                "INFO: payitems marking.%s — enable M0 / paths.marking_quantities for CSV quantities."
                % pair[1]
            )
    if rows:
        out.append("OK: payitems.csv has %d row(s)." % len(rows))
    return out


def _validate_project_extensions(root: str, cfg: dict) -> list[str]:
    out: list[str] = []
    design = cfg.get("design") or {}
    boq = cfg.get("boq") or {}
    dpr = cfg.get("dpr") or {}

    irc = design.get("irc37")
    if irc is None and design.get("pavement"):
        irc = design.get("pavement")
        out.append("INFO: design.pavement alias used (prefer design.irc37).")
    if irc is not None:
        try:
            cbr = float(irc.get("cbr_pct", 0))
            msa = float(irc.get("msa", 0))
            climate = str(irc.get("climate", "moderate")).strip().lower()
            if cbr < 2 or cbr > 10:
                out.append("WARN: design.irc37 — cbr_pct %.2f outside handbook range 2–10." % cbr)
            if msa < 1 or msa > 150:
                out.append("WARN: design.irc37 — msa %.2f outside handbook range 1–150." % msa)
            if climate not in ("moderate", "rainfall", "desert"):
                out.append(
                    "ERROR: design.irc37 — climate must be moderate, rainfall, or desert (got %s)."
                    % climate
                )
            elif cbr <= 0 or msa < 0:
                out.append("ERROR: design.irc37 — cbr_pct must be > 0 and msa >= 0.")
            else:
                out.append("OK: design.irc37 cbr_pct=%s msa=%s climate=%s." % (cbr, msa, climate))
                out.extend(_validate_irc37_lookup(root, cfg, irc))
        except (TypeError, ValueError):
            out.append("ERROR: design.irc37 — cbr_pct and msa must be numeric.")

    soil = design.get("soil_type")
    if soil is not None:
        key = str(soil).strip().lower().replace(" ", "_")
        if key not in VALID_SOIL_TYPES:
            out.append(
                "WARN: design.soil_type '%s' not in %s — M4 uses ordinary_soil factors."
                % (soil, ", ".join(VALID_SOIL_TYPES))
            )
        else:
            out.append("OK: design.soil_type=%s." % key)

    state_code = boq.get("state_code")
    rate_rel = boq.get("rate_file", "config/state_sor_rates.json")
    sor_path = resolve_path(root, rate_rel)
    if state_code:
        if not os.path.isfile(sor_path):
            out.append("ERROR: boq.state_code set but state_sor_rates.json missing.")
        else:
            try:
                with open(sor_path, "r", encoding="utf-8") as f:
                    sor = json.load(f)
                states = sor.get("states") or {}
                if state_code not in states:
                    out.append(
                        "ERROR: boq.state_code '%s' not in state_sor_rates.json (have: %s)."
                        % (state_code, ", ".join(sorted(states.keys())))
                    )
                else:
                    out.append("OK: boq.state_code=%s (%s)." % (state_code, states[state_code].get("name", "")))
            except Exception as ex:
                out.append("ERROR: Cannot read state_sor_rates.json: " + str(ex))
    if boq.get("rate_file"):
        out.append("OK: boq.rate_file=%s." % rate_rel)

    if dpr.get("package_id"):
        out.append("OK: dpr.package_id=%s." % dpr.get("package_id"))
    if dpr.get("revision"):
        out.append("OK: dpr.revision=%s." % dpr.get("revision"))
    paths_block = cfg.get("paths") or {}
    if paths_block.get("dpr_sheet_manifest"):
        out.append("OK: paths.dpr_sheet_manifest=%s." % paths_block.get("dpr_sheet_manifest"))

    cat_path = os.path.join(root, "config", "irc37_catalogue.json")
    if irc is not None and not os.path.isfile(cat_path):
        out.append("ERROR: design.irc37 set but irc37_catalogue.json missing.")
    elif os.path.isfile(cat_path):
        out.append("OK: irc37_catalogue.json present.")

    irc35_path = os.path.join(root, "config", "irc35_markings_catalogue.json")
    if os.path.isfile(irc35_path):
        out.append("OK: irc35_markings_catalogue.json present.")
    elif (cfg.get("paths") or {}).get("markings_schedule"):
        out.append("ERROR: paths.markings_schedule set but irc35_markings_catalogue.json missing.")

    return out


def _profile_alignment_range_checks(root: str, paths: dict, cfg: dict) -> list[str]:
    """WARN when profile chainage exceeds M1 alignment_meta length."""
    out: list[str] = []
    rel_prof = paths.get("profile_pvis")
    rel_meta = paths.get("alignment_meta")
    if not rel_prof or not rel_meta:
        return out
    prof_full = resolve_path(root, rel_prof)
    meta_full = resolve_path(root, rel_meta)
    if not os.path.isfile(prof_full) or not os.path.isfile(meta_full):
        return out
    try:
        with open(meta_full, "r", encoding="utf-8") as f:
            meta = json.load(f)
        total = meta.get("total_length_m")
        if total is None:
            return out
        rows = _read_data_rows(prof_full)
        stations = []
        for r in rows:
            if r.get("station_m"):
                stations.append(float(r["station_m"]))
        if stations and max(stations) > float(total) + 1e-3:
            out.append(
                "WARN: profile max station %.1f m exceeds alignment_meta total_length_m %.1f."
                % (max(stations), float(total))
            )
        else:
            out.append(
                "OK: profile stations within alignment_meta length (%.1f m)." % float(total)
            )
    except (OSError, ValueError, json.JSONDecodeError) as ex:
        out.append("WARN: Could not compare profile to alignment_meta: %s" % ex)
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
    design = cfg.get("design") or {}
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
        if key == "signage":
            lines.extend(_check_signage_block_names(root, full))

    gen_rel = paths.get("signage_generated")
    if gen_rel:
        gen_full = resolve_path(root, gen_rel)
        if os.path.isfile(gen_full):
            try:
                headers = read_header_row(gen_full)
                required = CSV_PATH_KEYS["signage"]
                missing = [c for c in required if c not in set(headers)]
                if missing:
                    lines.append(
                        "WARN: signage_generated.csv missing column(s): %s"
                        % ", ".join(missing)
                    )
                else:
                    lines.append("OK: signage_generated.csv — columns match.")
                lines.extend(_check_signage_block_names(root, gen_full))
            except Exception as ex:
                lines.append("WARN: Cannot read signage_generated: %s" % ex)

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
            header_set = set(headers)
            missing = [c for c in VOLUMES_HEADERS if c not in header_set]
            if missing:
                lines.append(
                    "ERROR: volumes file has wrong columns (expected M4 output): missing %s"
                    % ", ".join(missing)
                )
            else:
                lines.append("OK: volumes CSV exists and looks like M4 output.")
                swell_missing = [c for c in VOLUMES_HEADERS_SWELL if c not in header_set]
                if swell_missing and design.get("soil_type"):
                    lines.append(
                        "WARN: volumes CSV missing swell columns %s — re-run M4 after Plan 01."
                        % ", ".join(swell_missing[len(VOLUMES_HEADERS) :])
                    )
                elif not swell_missing:
                    lines.append("OK: volumes CSV includes swell/shrink columns.")
        else:
            lines.append(
                "INFO: volumes CSV not created yet (normal before you run M4): %s"
                % vol_full
            )

    mh_rel = paths.get("mass_haul_csv")
    if mh_rel:
        mh_full = resolve_path(root, mh_rel)
        if os.path.isfile(mh_full):
            mh_headers = set(read_header_row(mh_full))
            mh_missing = [c for c in MASS_HAUL_HEADERS if c not in mh_headers]
            if mh_missing:
                lines.append(
                    "WARN: mass haul CSV missing columns %s — re-run M4."
                    % ", ".join(mh_missing)
                )
            else:
                lines.append("OK: mass haul CSV columns match M4 output.")
        else:
            lines.append("INFO: mass haul CSV not created yet: %s" % mh_full)

    interval = design.get("volume_sample_interval_m")
    if interval is not None:
        try:
            iv = float(interval)
            if iv <= 0:
                lines.append("WARN: design.volume_sample_interval_m must be > 0.")
            else:
                lines.append("OK: design.volume_sample_interval_m=%s." % iv)
        except (TypeError, ValueError):
            lines.append("WARN: design.volume_sample_interval_m must be numeric.")

    boq_rel = paths.get("boq_csv")
    if boq_rel:
        boq_full = resolve_path(root, boq_rel)
        bd = os.path.dirname(boq_full)
        if bd and not os.path.isdir(bd):
            lines.append(
                "INFO: BOQ output folder will be created by M7 if missing: %s" % bd
            )

    lines.append("")
    lines.append("--- M0 markings schedule ---")
    lines.extend(_validate_markings_schedule_data(root, paths))

    lines.append("")
    lines.append("--- BOQ payitems ---")
    lines.extend(_validate_payitems_boq(root, paths, cfg))

    lines.append("")
    lines.append("--- Plan 01 extensions (design / boq / dpr) ---")
    lines.extend(_validate_project_extensions(root, cfg))

    try:
        import pipeline_contract as pc  # noqa: WPS433 — same package dir as this module
    except ImportError:
        pc = None
    if pc is not None:
        lines.append("")
        lines.append("--- Pipeline upstream artifacts ---")
        lines.extend(pc.validate_pipeline_artifacts(cfg, root, resolve_path))

    lines.append("")
    lines.append("--- Profile / PVI checks ---")
    lines.extend(_profile_alignment_range_checks(root, paths, cfg))

    if strict:
        lines.append("")
        lines.append("--- Strict data checks ---")
        lines.extend(_strict_data_checks(root, paths))

    lines.append("")
    lines.append("Next: Copy the config path above into Dynamo Player IN[0] for m8_run_all.py (use absolute path).")
    return lines


def validation_failed(lines: list[str]) -> bool:
    return any(line.startswith("ERROR:") for line in lines)
