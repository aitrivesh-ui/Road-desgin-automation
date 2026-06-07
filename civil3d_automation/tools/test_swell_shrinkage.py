# -*- coding: utf-8 -*-
"""Unit tests for earthwork_factors (Plan 07 M4)."""
import os
import sys
import unittest

_TOOLS = os.path.dirname(os.path.abspath(__file__))
_PY = os.path.normpath(os.path.join(_TOOLS, '..', 'python'))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

from earthwork_factors import (  # noqa: E402
    apply_swell_shrink,
    allocate_region_volumes,
    factors_for_soil,
    mass_haul_ordinates,
)


class TestSwellShrinkage(unittest.TestCase):
    def test_ordinary_soil_handbook(self):
        r = apply_swell_shrink(1000.0, 900.0, 'ordinary_soil')
        self.assertAlmostEqual(r['cut_haul_m3'], 1250.0)
        self.assertAlmostEqual(r['fill_borrow_m3'], 1000.0)
        self.assertAlmostEqual(r['cut_loose_m3'], 1250.0)
        self.assertAlmostEqual(r['net_haul_m3'], 250.0)
        self.assertAlmostEqual(r['spoil_m3'], 250.0)
        self.assertAlmostEqual(r['borrow_req_m3'], 0.0)

    def test_borrow_required(self):
        r = apply_swell_shrink(100.0, 500.0, 'ordinary_soil')
        self.assertGreater(r['borrow_req_m3'], 0.0)
        self.assertAlmostEqual(r['spoil_m3'], 0.0)

    def test_soft_rock(self):
        r = apply_swell_shrink(1000.0, 880.0, 'soft_rock')
        self.assertAlmostEqual(r['cut_haul_m3'], 1150.0)
        self.assertAlmostEqual(r['fill_borrow_m3'], 1000.0)

    def test_loose_rock(self):
        r = apply_swell_shrink(1000.0, 850.0, 'loose_rock')
        self.assertAlmostEqual(r['cut_haul_m3'], 1300.0)
        self.assertAlmostEqual(r['fill_borrow_m3'], 1000.0)

    def test_hard_rock_no_shrink(self):
        r = apply_swell_shrink(1000.0, 800.0, 'hard_rock')
        self.assertAlmostEqual(r['swell_factor'], 1.35)
        self.assertAlmostEqual(r['fill_borrow_m3'], 800.0)

    def test_unknown_soil_fallback(self):
        f = factors_for_soil('unknown_terrain')
        self.assertEqual(f['soil_type'], 'ordinary_soil')

    def test_murrum_moorum(self):
        r = apply_swell_shrink(1000.0, 920.0, 'murrum')
        self.assertAlmostEqual(r['cut_haul_m3'], 1100.0)
        self.assertAlmostEqual(r['fill_borrow_m3'], 1000.0)


class TestRegionSplit(unittest.TestCase):
    def test_two_region_proportional(self):
        regions = [
            {'region_id': 'R1', 'start_sta': 0, 'end_sta': 800, 'assembly_name': 'A1'},
            {'region_id': 'R2', 'start_sta': 800, 'end_sta': 1400, 'assembly_name': 'A2'},
        ]
        splits = allocate_region_volumes(1400.0, 700.0, regions)
        self.assertEqual(len(splits), 2)
        cut_sum = sum(s['cut_m3'] for s in splits)
        fill_sum = sum(s['fill_m3'] for s in splits)
        self.assertAlmostEqual(cut_sum, 1400.0, places=3)
        self.assertAlmostEqual(fill_sum, 700.0, places=3)


class TestMassHaul(unittest.TestCase):
    def test_row_count_interval(self):
        rows, meta = mass_haul_ordinates(1000.0, 800.0, interval_m=20.0, length_m=1000.0)
        self.assertEqual(len(rows), 51)
        self.assertEqual(meta['sample_count'], 51)

    def test_haul_direction(self):
        rows, _ = mass_haul_ordinates(500.0, 100.0, interval_m=100.0, length_m=500.0)
        self.assertEqual(rows[-1]['haul_direction'], 'export')


if __name__ == '__main__':
    unittest.main()
