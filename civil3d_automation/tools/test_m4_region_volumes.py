# -*- coding: utf-8 -*-
"""Offline tests for M4 region volume split (Plan 07 Phase 4)."""
import os
import sys
import unittest

_TOOLS = os.path.dirname(os.path.abspath(__file__))
_PY = os.path.normpath(os.path.join(_TOOLS, '..', 'python'))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

from earthwork_factors import allocate_region_volumes, apply_swell_shrink  # noqa: E402


class TestM4RegionVolumes(unittest.TestCase):
    def test_split_within_one_percent(self):
        regions = [
            {'region_id': 'R1', 'start_sta': '0', 'end_sta': '800'},
            {'region_id': 'R2', 'start_sta': '800', 'end_sta': '1400'},
        ]
        total_cut = 10000.0
        total_fill = 5000.0
        splits = allocate_region_volumes(total_cut, total_fill, regions)
        cut_sum = sum(s['cut_m3'] for s in splits)
        fill_sum = sum(s['fill_m3'] for s in splits)
        self.assertLess(abs(cut_sum - total_cut) / total_cut, 0.01)
        self.assertLess(abs(fill_sum - total_fill) / total_fill, 0.01)

    def test_per_region_swell(self):
        regions = [{'region_id': 'R1', 'start_sta': 0, 'end_sta': 1000}]
        splits = allocate_region_volumes(1000.0, 900.0, regions)
        ss = apply_swell_shrink(splits[0]['cut_m3'], splits[0]['fill_m3'], 'ordinary_soil')
        self.assertAlmostEqual(ss['cut_haul_m3'], 1250.0)


if __name__ == '__main__':
    unittest.main()
