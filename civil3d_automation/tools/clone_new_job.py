# -*- coding: utf-8 -*-
"""
Clone a fresh civil3d_automation job folder from the repo package (full copy + clean CSVs).

Usage:
  python clone_new_job.py --dest "D:\\jobs\\MyJob\\civil3d_automation" [--source path] [--number PRJ-2026-X] [--force]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

# Template CSV basenames under csv/templates/
TEMPLATE_CSVS = [
    "alignment_pi.csv",
    "profile_pvis.csv",
    "section_widths.csv",
    "signage_schedule.csv",
    "payitems.csv",
]

IGNORE_NAMES = {".git", "__pycache__"}


def _default_source_root() -> str:
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def clone_package(
    dest_root: str,
    source_root: str | None = None,
    project_number: str | None = None,
    force: bool = False,
) -> str:
    """
    Copy civil3d_automation tree from source_root to dest_root, replace csv/*.csv with
    header-only templates, reset config from project.example.json.
    Returns path to new config/project.json.
    """
    source_root = os.path.abspath(source_root or _default_source_root())
    dest_root = os.path.normpath(os.path.abspath(dest_root))

    if not os.path.isdir(os.path.join(source_root, "python")):
        raise ValueError("Source does not look like civil3d_automation (missing python/).")

    if os.path.exists(dest_root):
        if not force:
            raise FileExistsError("Destination exists: %s (use --force to replace)" % dest_root)
        shutil.rmtree(dest_root)

    def _ignore(_path: str, names: list[str]) -> list[str]:
        skip = []
        for n in names:
            if n in IGNORE_NAMES:
                skip.append(n)
            if n == "out" and _path == source_root:
                skip.append(n)
        return skip

    shutil.copytree(source_root, dest_root, ignore=_ignore)

    # Remove copied out/ if present (ignore may not skip nested out in subdirs — only top-level)
    out_top = os.path.join(dest_root, "out")
    if os.path.isdir(out_top):
        shutil.rmtree(out_top, ignore_errors=True)
    os.makedirs(os.path.join(dest_root, "out", "qa"), exist_ok=True)

    tmpl = os.path.join(source_root, "csv", "templates")
    csv_dir = os.path.join(dest_root, "csv")
    os.makedirs(csv_dir, exist_ok=True)
    for name in TEMPLATE_CSVS:
        src = os.path.join(tmpl, name)
        if not os.path.isfile(src):
            raise FileNotFoundError("Missing template: " + src)
        shutil.copy2(src, os.path.join(csv_dir, name))

    example = os.path.join(source_root, "config", "project.example.json")
    if not os.path.isfile(example):
        raise FileNotFoundError("Missing config/project.example.json")
    cfg_path = os.path.join(dest_root, "config", "project.json")
    with open(example, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    if project_number:
        cfg.setdefault("project", {})["number"] = project_number
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")

    return cfg_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Clone civil3d_automation package for a new job.")
    ap.add_argument("--dest", required=True, help="New civil3d_automation root folder (will be created).")
    ap.add_argument("--source", default=None, help="Existing package root (default: next to this script).")
    ap.add_argument("--number", dest="project_number", default=None, help="Override project.number in project.json.")
    ap.add_argument("--force", action="store_true", help="Delete dest if it already exists.")
    args = ap.parse_args()
    try:
        pj = clone_package(
            args.dest,
            source_root=args.source,
            project_number=args.project_number,
            force=args.force,
        )
        print("OK: Cloned job to:\n  %s\nConfig:\n  %s" % (os.path.normpath(args.dest), pj))
        return 0
    except Exception as ex:
        print("ERROR: %s" % ex, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
