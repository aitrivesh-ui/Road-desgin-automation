# -*- coding: utf-8 -*-
"""
Harvest XData quantities from a DWG (Python 3 — read-only stub for offline QA).

Scans layer filters and XData apps used by M0/M5/M7. For live BOQ inside Civil 3D,
use m7_boq_rollup.py instead.

Usage:
  python harvest_xdata_quantities.py --project path/to/project.json
  python harvest_xdata_quantities.py --dwg path.dwg --mark-layer X --sign-layer Y
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

MARK_XDATA = "IRC35_ROAD_MARK_V2"
SIGN_XDATA = "ROAD_SIGN_CSV"


def _root_from_project(project_json: str) -> str:
    base = os.path.dirname(os.path.abspath(project_json))
    return os.path.normpath(os.path.join(base, ".."))


def _resolve(root: str, rel: str) -> str:
    return os.path.normpath(os.path.join(root, rel.replace("/", os.sep)))


def _empty_signage_counts() -> dict:
    return {
        "version": 1,
        "source": "harvest_stub",
        "xdata_app": SIGN_XDATA,
        "counts": {
            "SGN_STOP": 0,
            "SGN_SPEED_50": 0,
            "SGN_W1": 0,
            "SGN_W2": 0,
            "SGN_KM_POST": 0,
            "SGN_DELINEATOR": 0,
            "SGN_GUARDRAIL": 0,
        },
    }


def _empty_marking_harvest() -> dict:
    return {
        "version": 1,
        "source": "harvest_stub",
        "xdata_app": MARK_XDATA,
        "by_mark_type": {},
        "note": "Run m7_boq_rollup.py inside Civil 3D for live Solid3d scan.",
    }


def harvest_from_config(project_json: str) -> list[dict[str, str]]:
    with open(project_json, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    root = _root_from_project(project_json)
    paths = cfg.get("paths") or {}
    names = cfg.get("names", {}) or {}
    layers = names.get("layers", {}) or {}

    out_dir = _resolve(root, "out")
    os.makedirs(out_dir, exist_ok=True)

    sign_rel = paths.get("signage_counts", "out/signage_counts.json")
    mark_rel = paths.get("marking_harvest", "out/marking_harvest.json")
    sign_path = _resolve(root, sign_rel)
    mark_path = _resolve(root, mark_rel)

    sign_doc = _empty_signage_counts()
    sign_doc["mark_layer"] = layers.get("marking", "C-ROAD-MARK-THERMO")
    sign_doc["sign_layer"] = layers.get("signage", "C-SGN-FURN")

    with open(sign_path, "w", encoding="utf-8") as f:
        json.dump(sign_doc, f, indent=2)

    mark_doc = _empty_marking_harvest()
    mark_doc["mark_layer"] = sign_doc["mark_layer"]
    with open(mark_path, "w", encoding="utf-8") as f:
        json.dump(mark_doc, f, indent=2)

    xdata_csv = os.path.join(out_dir, "xdata_quantities.csv")
    rows = [
        {
            "source": "config",
            "key": "mark_layer",
            "quantity": sign_doc["mark_layer"],
            "xdata_app": MARK_XDATA,
        },
        {
            "source": "config",
            "key": "sign_layer",
            "quantity": sign_doc["sign_layer"],
            "xdata_app": SIGN_XDATA,
        },
    ]
    with open(xdata_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["source", "key", "quantity", "xdata_app"])
        w.writeheader()
        w.writerows(rows)

    return rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Harvest road automation XData quantities")
    p.add_argument("--project", help="Path to project.json")
    p.add_argument("--dwg", help="DWG path (requires ezdxf or Civil — not bundled)")
    args = p.parse_args(argv)
    if args.project:
        rows = harvest_from_config(args.project)
        print(
            "OK: wrote signage_counts.json, marking_harvest.json, xdata_quantities.csv "
            "(%d config rows). Full DWG scan requires Civil API / m7_boq_rollup.py."
            % len(rows)
        )
        return 0
    if args.dwg:
        print("ERROR: Direct DWG scan not implemented — run m7_boq_rollup.py inside Civil 3D.")
        return 1
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
