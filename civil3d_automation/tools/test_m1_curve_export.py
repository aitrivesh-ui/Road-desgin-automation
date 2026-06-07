# -*- coding: utf-8 -*-
"""M1 curve table export shape (no Civil 3D — avoids clr import)."""
from __future__ import absolute_import

import csv
import os
import tempfile
import unittest

CURVE_TABLE_HEADERS = [
    'station_m', 'radius_m', 'pi_id', 'design_speed_kph',
    'station_tc', 'station_ec', 'delta_deg', 'L_arc',
    'spiral_in_m', 'spiral_out_m', 'side', 'Ls_calc_m', 'Ls_min_m', 'osd_m',
]


def _write_curve_table(path, curve_rows):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(CURVE_TABLE_HEADERS)
        for r in curve_rows:
            w.writerow([r.get(h, '') for h in CURVE_TABLE_HEADERS])


class TestM1CurveExport(unittest.TestCase):
    def test_write_empty_curve_table_has_header(self) -> None:
        fd, path = tempfile.mkstemp(suffix='.csv')
        os.close(fd)
        try:
            _write_curve_table(path, [])
            with open(path, 'r', encoding='utf-8', newline='') as f:
                rows = list(csv.reader(f))
            self.assertEqual(rows[0], CURVE_TABLE_HEADERS)
            self.assertEqual(len(rows), 1)
        finally:
            os.unlink(path)


if __name__ == '__main__':
    unittest.main()
