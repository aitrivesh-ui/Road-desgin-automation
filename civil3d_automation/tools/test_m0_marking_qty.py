# -*- coding: utf-8 -*-
"""M0 marking catalogue and quantity CSV contract tests (Python 3, no Civil 3D)."""
from __future__ import annotations

import json
import os
import sys
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_TOOLS = os.path.dirname(__file__)
_PY = os.path.join(_ROOT, "python")
for _p in (_TOOLS, _PY):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pipeline_contract as pc  # noqa: E402

import irc35_marking_core as mcore  # noqa: E402


class TestIRC35Catalogue(unittest.TestCase):
    def test_catalogue_loads(self) -> None:
        cat = mcore.load_catalogue()
        self.assertIn("CL-D", cat["mark_types"])
        self.assertEqual(cat["mark_types"]["CL-D"]["dash_m"], 3.0)
        self.assertEqual(cat["mark_types"]["CL-D"]["gap_m"], 5.0)

    def test_validate_mark_type(self) -> None:
        code, err = mcore.validate_mark_type("cl-d")
        self.assertEqual(code, "CL-D")
        self.assertIsNone(err)
        _, err = mcore.validate_mark_type("INVALID")
        self.assertIsNotNone(err)


class TestMarkingGeometry(unittest.TestCase):
    def test_cl_d_interval_count_500m(self) -> None:
        ivs = mcore.intervals(500.0, 3.0, 5.0, 0.0)
        # 500 m / 8 m cycle ≈ 62 full dashes + partial
        self.assertGreater(len(ivs), 60)
        self.assertAlmostEqual(ivs[0][0], 0.0, places=3)
        self.assertAlmostEqual(ivs[0][1] - ivs[0][0], 3.0, places=2)

    def test_nopassing_when_radius_low(self) -> None:
        rows = [{"station_m": "500", "radius_m": "80", "design_speed_kph": "80"}]
        zones = mcore.build_nopassing_intervals(rows, 2000.0, 80)
        self.assertTrue(len(zones) >= 1)

    def test_overlap_splits_cl_d(self) -> None:
        spans = mcore.overlap_intervals(0, 1000, [(200, 400)])
        types = [s[2] for s in spans]
        self.assertIn("CL-DY", types)


class TestMarkingQtyContract(unittest.TestCase):
    def test_headers_match_pipeline(self) -> None:
        self.assertEqual(
            pc.MARKING_QTY_HEADERS,
            ["mark_type", "material", "length_m", "area_m2", "chainage_from", "chainage_to"],
        )

    def test_write_csv_roundtrip(self) -> None:
        import tempfile

        path = os.path.join(tempfile.gettempdir(), "test_marking_qty.csv")
        try:
            mcore.write_marking_qty_csv(
                path,
                [
                    {
                        "mark_type": "CL-D",
                        "material": "thermoplastic",
                        "length_m": 100.0,
                        "area_m2": 10.0,
                        "chainage_from": 0,
                        "chainage_to": 1000,
                    }
                ],
            )
            with open(path, encoding="utf-8") as f:
                header = f.readline().strip().split(",")
            self.assertEqual(header, pc.MARKING_QTY_HEADERS)
        finally:
            if os.path.isfile(path):
                os.remove(path)


if __name__ == "__main__":
    unittest.main()
