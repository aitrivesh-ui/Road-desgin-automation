# -*- coding: utf-8 -*-
"""Unit tests for BOQ core (Plan 09 — M6 handbook / repo M7)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

TOOLS = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.normpath(os.path.join(TOOLS, ".."))
PY = os.path.join(PKG, "python")
if PY not in sys.path:
    sys.path.insert(0, PY)

import boq_core as bc  # noqa: E402


class TestLoadRates(unittest.TestCase):
    def test_hr_multiplier_when_item_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            sor = os.path.join(td, "sor.json")
            with open(sor, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "states": {"HR": {"default_rate_factor": 0.95}},
                        "items": {"HR": {}},
                        "taxes": {},
                    },
                    f,
                )
            rates = bc.load_rates(
                "HR",
                sor,
                ["volumes|cut_m3"],
                base_rates={"volumes|cut_m3": 1000.0},
            )
            self.assertEqual(rates["volumes|cut_m3"], 950.0)

    def test_explicit_state_item_overrides_multiplier(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            sor = os.path.join(td, "sor.json")
            with open(sor, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "states": {"HR": {"default_rate_factor": 0.95}},
                        "items": {"HR": {"volumes|cut_m3": 428.0}},
                        "taxes": {},
                    },
                    f,
                )
            rates = bc.load_rates(
                "HR",
                sor,
                ["volumes|cut_m3"],
                base_rates={"volumes|cut_m3": 1000.0},
            )
            self.assertEqual(rates["volumes|cut_m3"], 428.0)


class TestComputeTaxes(unittest.TestCase):
    def test_handbook_grand_total(self) -> None:
        t = bc.compute_taxes(100000.0, {"contingency_pct": 5.0, "gst_pct": 18.0, "labour_cess_pct": 1.0, "supervision_pct": 2.0})
        self.assertEqual(t["subtotal"], 100000.0)
        self.assertEqual(t["contingency"], 5000.0)
        self.assertEqual(t["total_work"], 105000.0)
        self.assertEqual(t["gst"], 18900.0)
        self.assertEqual(t["labour_cess"], 1050.0)
        self.assertEqual(t["supervision"], 2100.0)
        self.assertEqual(t["grand_total"], 127050.0)


class TestMarkingCsv(unittest.TestCase):
    def test_area_vs_length_by_unit(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write("mark_type,material,length_m,area_m2,chainage_from,chainage_to\n")
            f.write("CL-D,thermoplastic,10.0,25.0,0,100\n")
            path = f.name
        try:
            _, by_len, by_area = bc.load_marking_quantities_csv(path)
            self.assertAlmostEqual(by_len["CL-D"], 10.0)
            self.assertAlmostEqual(by_area["CL-D"], 25.0)
            row_m = {"source": "marking", "key": "CL-D", "unit": "m"}
            row_m2 = {"source": "marking", "key": "CL-D", "unit": "m2"}
            self.assertEqual(bc.marking_qty_for_unit("CL-D", "m", by_len, by_area), 10.0)
            self.assertEqual(bc.marking_qty_for_unit("CL-D", "m2", by_len, by_area), 25.0)
        finally:
            os.unlink(path)


class TestQtySourceResolver(unittest.TestCase):
    def test_resolve_qty_key(self) -> None:
        row = {"source": "volumes", "key": "cut_m3", "qty_source": "volumes.cut_haul_m3", "unit": "m3"}
        self.assertEqual(bc.resolve_qty_key(row), ("volumes", "cut_haul_m3"))

    def test_pavement_volume(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cache = os.path.join(td, "irc37.json")
            with open(cache, "w", encoding="utf-8") as f:
                json.dump({"layers_mm": {"GSB": 200, "WMM": 250, "DBM": 50, "BC": 40}}, f)
            qty = bc.load_pavement_quantities(cache, 1000.0)
            self.assertAlmostEqual(qty[("pavement", "gsb")], 200.0)
            self.assertAlmostEqual(qty[("pavement", "bc")], 40.0)


if __name__ == "__main__":
    unittest.main()
