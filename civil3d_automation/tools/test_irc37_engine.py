# -*- coding: utf-8 -*-
"""Unit tests for IRC:37 pavement catalogue (Plan 06)."""
from __future__ import annotations

import os
import sys
import unittest

TOOLS = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.normpath(os.path.join(TOOLS, ".."))
PY = os.path.join(PKG, "python")
if PY not in sys.path:
    sys.path.insert(0, PY)

from irc37_engine import irc37_design, snap_bin  # noqa: E402


class TestIrc37Engine(unittest.TestCase):
    def test_acceptance_cbr5_msa10(self) -> None:
        r = irc37_design(5, 10)
        self.assertFalse(r.get("empty"))
        mm = r["layers_mm"]
        self.assertEqual(mm["GSB"], 200)
        self.assertEqual(mm["WMM"], 250)
        self.assertEqual(mm["DBM"], 50)
        self.assertEqual(mm["BC"], 40)
        self.assertEqual(r["snapped"]["key"], "10|5")

    def test_snap_bins(self) -> None:
        self.assertEqual(snap_bin(4.9, [3, 5, 7, 8, 10]), 5)
        self.assertEqual(snap_bin(12, [2, 5, 10, 20, 30]), 10)

    def test_layers_m_and_contract_layers(self) -> None:
        r = irc37_design(5, 10)
        self.assertAlmostEqual(r["layers_m"]["GSB"], 0.2)
        names = [x["name"] for x in r["layers"]]
        self.assertEqual(names, ["GSB", "WMM", "DBM", "BC"])

    def test_nearest_key_fallback(self) -> None:
        r = irc37_design(9, 15)
        self.assertFalse(r.get("empty"))
        self.assertTrue(r.get("layers_mm"))

    def test_climate_entry_override(self) -> None:
        r = irc37_design(3, 5, "rainfall")
        self.assertFalse(r.get("empty"))
        self.assertEqual(r["layers_mm"]["GSB"], 220)

    def test_missing_catalogue_raises(self) -> None:
        missing = os.path.join(PKG, "config", "no_such_irc37.json")
        with self.assertRaises(FileNotFoundError):
            irc37_design(5, 10, catalogue_path=missing)


if __name__ == "__main__":
    unittest.main()
