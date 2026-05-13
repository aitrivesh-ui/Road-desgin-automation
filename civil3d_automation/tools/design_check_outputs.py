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


def run_checks(project_json: str) -> list[str]:
    lines: list[str] = []
    if not os.path.isfile(project_json):
        lines.append("ERROR: project.json not found: " + project_json)
        return lines

    root = root_from_project_json(project_json)
    with open(project_json, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    paths = cfg.get("paths") or {}

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
                r = rows[-1]
                lines.append(
                    "OK: Volumes last row — cut_m3=%s fill_m3=%s net_m3=%s"
                    % (r.get("cut_m3", "?"), r.get("fill_m3", "?"), r.get("net_m3", "?"))
                )

    boq = paths.get("boq_csv")
    if boq:
        bp = resolve_path(root, boq)
        if not os.path.isfile(bp):
            lines.append("WARN: BOQ CSV not found yet: " + bp)
        else:
            with open(bp, "r", encoding="utf-8-sig", newline="") as f:
                n = sum(1 for _ in csv.DictReader(f))
            if n == 0:
                lines.append("WARN: BOQ CSV has no quantity rows (check payitems map vs model).")
            else:
                lines.append("OK: BOQ CSV has %d quantity row(s)." % n)

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
