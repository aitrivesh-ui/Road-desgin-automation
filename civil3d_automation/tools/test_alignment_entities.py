# -*- coding: utf-8 -*-
"""Unit tests for M1 alignment entity helpers (no Civil 3D)."""
from __future__ import annotations

import os
import sys
import unittest

TOOLS = os.path.dirname(os.path.abspath(__file__))
PY = os.path.normpath(os.path.join(TOOLS, "..", "python"))
if PY not in sys.path:
    sys.path.insert(0, PY)

import _alignment_entities as ae  # noqa: E402


class TestAlignmentEntities(unittest.TestCase):
    def test_default_polyline_mode(self) -> None:
        self.assertEqual(ae.geometry_mode({}), "polyline")
        self.assertEqual(ae.geometry_mode({"alignment": {"geometry_mode": "scs"}}), "scs")

    def test_pis_have_curves(self) -> None:
        pis = [
            {"pi_id": "A", "radius_m": "0"},
            {"pi_id": "B", "radius_m": "230"},
            {"pi_id": "C", "radius_m": "0"},
        ]
        self.assertTrue(ae.pis_have_curves(pis))
        self.assertEqual(ae.interior_curve_pis(pis), [1])

    def test_no_interior_curves_on_two_pis(self) -> None:
        pis = [{"radius_m": "230"}, {"radius_m": "230"}]
        self.assertEqual(ae.interior_curve_pis(pis), [])


if __name__ == "__main__":
    unittest.main()
