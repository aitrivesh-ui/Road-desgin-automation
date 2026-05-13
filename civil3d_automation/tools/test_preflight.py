# -*- coding: utf-8 -*-
"""Unit tests for tools (run from civil3d_automation: python -m unittest discover -s tools -p \"test_*.py\" -v)."""
from __future__ import annotations

import csv
import json
import os
import shutil
import sys
import tempfile
import unittest

TOOLS = os.path.dirname(os.path.abspath(__file__))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import clone_new_job  # noqa: E402
import design_check_outputs  # noqa: E402
import export_workbook_to_csv as ex  # noqa: E402
import preflight_validate as pv  # noqa: E402


class TestPreflightStrict(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="road_auto_test_")
        self.root = os.path.join(self.tmp, "civil3d_automation")
        os.makedirs(os.path.join(self.root, "csv"))
        os.makedirs(os.path.join(self.root, "config"))
        pj = os.path.join(self.root, "config", "project.json")
        cfg = {
            "paths": {
                "alignment_pi": "csv/alignment_pi.csv",
                "profile_pvis": "csv/profile_pvis.csv",
                "section_widths": "csv/section_widths.csv",
                "signage": "csv/signage_schedule.csv",
                "payitems": "csv/payitems.csv",
                "volumes_csv": "out/volumes.csv",
                "boq_csv": "out/boq.csv",
                "qa_log": "out/qa/run_log.txt",
            }
        }
        with open(pj, "w", encoding="utf-8") as f:
            json.dump(cfg, f)

        def write_csv(name: str, rows: list[list[str]]) -> None:
            path = os.path.join(self.root, "csv", name)
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                for r in rows:
                    w.writerow(r)

        write_csv(
            "alignment_pi.csv",
            [
                list(pv.CSV_PATH_KEYS["alignment_pi"]),
                ["A1", "0", "0", "0", "0", "0", "80"],
            ],
        )
        write_csv(
            "profile_pvis.csv",
            [list(pv.CSV_PATH_KEYS["profile_pvis"]), ["0", "100", "0", "0", "0"], ["100", "90", "0", "0", "0"]],
        )
        write_csv(
            "section_widths.csv",
            [
                list(pv.CSV_PATH_KEYS["section_widths"]),
                ["R1", "0", "100", "3.5", "2", "2", "L", "R"],
                ["R2", "100", "200", "3.5", "2", "2", "L", "R"],
            ],
        )
        write_csv(
            "signage_schedule.csv",
            [list(pv.CSV_PATH_KEYS["signage"]), ["1", "10", "4.5", "L", "X", "BLK", ""]],
        )
        write_csv("payitems.csv", [list(pv.CSV_PATH_KEYS["payitems"]), ["volumes", "cut_m3", "1", "c", "m3"]])
        self.pj = pj

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_validate_ok(self) -> None:
        lines = pv.validate_project(self.pj, strict=False)
        self.assertFalse(pv.validation_failed(lines), lines)

    def test_strict_fails_one_pi(self) -> None:
        path = os.path.join(self.root, "csv", "alignment_pi.csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(list(pv.CSV_PATH_KEYS["alignment_pi"]))
            w.writerow(["A1", "0", "0", "0", "0", "0", "80"])
        lines = pv.validate_project(self.pj, strict=True)
        self.assertTrue(any("Strict" in x and "2 PI" in x for x in lines))
        self.assertTrue(pv.validation_failed(lines))

    def test_strict_profile_not_increasing(self) -> None:
        path = os.path.join(self.root, "csv", "profile_pvis.csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(list(pv.CSV_PATH_KEYS["profile_pvis"]))
            w.writerow(["0", "100", "0", "0", "0"])
            w.writerow(["100", "101", "0", "0", "0"])
            w.writerow(["50", "102", "0", "0", "0"])
        lines = pv.validate_project(self.pj, strict=True)
        self.assertTrue(any("strictly increasing" in x.lower() for x in lines))

    def test_strict_region_overlap(self) -> None:
        path = os.path.join(self.root, "csv", "section_widths.csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(list(pv.CSV_PATH_KEYS["section_widths"]))
            w.writerow(["R1", "0", "100", "3.5", "2", "2", "L", "R"])
            w.writerow(["R2", "50", "150", "3.5", "2", "2", "L", "R"])
        lines = pv.validate_project(self.pj, strict=True)
        self.assertTrue(any("overlapping" in x.lower() for x in lines))


class TestCloneJob(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="road_auto_clone_")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_clone_creates_config(self) -> None:
        src = os.path.dirname(TOOLS)
        dest = os.path.join(self.tmp, "newpkg")
        pj = clone_new_job.clone_package(dest, source_root=src, project_number="UNIT-TEST-1", force=False)
        self.assertTrue(os.path.isfile(pj))
        with open(pj, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        self.assertEqual(cfg["project"]["number"], "UNIT-TEST-1")
        self.assertTrue(os.path.isdir(os.path.join(dest, "python")))


class TestDesignCheck(unittest.TestCase):
    def test_missing_project(self) -> None:
        lines = design_check_outputs.run_checks("/no/such/project.json")
        self.assertTrue(any(x.startswith("ERROR:") for x in lines))


class TestExportWorkbook(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="road_auto_xlsx_")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_export_if_workbook_exists(self) -> None:
        xlsx = os.path.join(os.path.dirname(TOOLS), "csv", "templates", "RoadAutomation_DataStarter.xlsx")
        if not os.path.isfile(xlsx):
            self.skipTest("RoadAutomation_DataStarter.xlsx not present")
        outd = os.path.join(self.tmp, "csv_out")
        log = ex.export_workbook(xlsx, outd)
        self.assertTrue(any("OK: Wrote" in x for x in log))
        self.assertTrue(os.path.isfile(os.path.join(outd, "alignment_pi.csv")))


if __name__ == "__main__":
    unittest.main()
