# -*- coding: utf-8 -*-
"""Unit tests for mass haul SVG export."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

TOOLS = os.path.dirname(os.path.abspath(__file__))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import export_mass_haul_chart as mhc  # noqa: E402


class TestMassHaulChart(unittest.TestCase):
    def test_build_svg_nonempty(self) -> None:
        svg = mhc.build_svg([0.0, 100.0, 200.0], [0.0, 50.0, -20.0])
        self.assertIn("<svg", svg)
        self.assertIn("polyline", svg)

    def test_export_roundtrip(self) -> None:
        tmp = tempfile.mkdtemp()
        csv_path = os.path.join(tmp, "mh.csv")
        out_path = os.path.join(tmp, "chart.svg")
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            f.write("station_m,ordinate_m3\n0,0\n20,10\n40,5\n")
        mhc.export_chart(csv_path, out_path)
        self.assertTrue(os.path.isfile(out_path))
        with open(out_path, encoding="utf-8") as f:
            body = f.read()
        self.assertIn("Mass haul", body)


if __name__ == "__main__":
    unittest.main()
