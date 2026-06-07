# -*- coding: utf-8 -*-
"""Unit tests for IRC:38 geometry helpers (Python 3, no Civil 3D)."""
from __future__ import absolute_import

import os
import sys
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
_PY = os.path.join(_ROOT, 'python')
if _PY not in sys.path:
    sys.path.insert(0, _PY)

import irc38_geometry as g  # noqa: E402


class TestIrc38Geometry(unittest.TestCase):
    def test_r_min_80_kph(self):
        r_min = g.r_min_formula(80, superelevation_pct=7.0, friction_override=0.14)
        self.assertAlmostEqual(r_min, 6400.0 / (127.0 * 0.21), places=1)
        self.assertGreater(r_min, 220.0)
        self.assertLess(r_min, 250.0)

    def test_friction_table_bucket(self):
        self.assertEqual(g.friction_coefficient(78), 0.14)
        self.assertEqual(g.friction_coefficient(62), 0.15)

    def test_validate_warn_below_r_min(self):
        r_min = g.r_min_formula(80)
        sev, code, _, _ = g.validate_radius(150, 80)
        self.assertEqual(sev, 'WARN')
        self.assertEqual(code, 'IRC38_R_MIN')
        self.assertGreater(r_min, 150)

    def test_validate_error_critical(self):
        r_min = g.r_min_formula(80)
        sev, code, _, crit = g.validate_radius(r_min * 0.4, 80, critical_factor=0.5)
        self.assertEqual(sev, 'ERROR')
        self.assertEqual(code, 'IRC38_R_CRITICAL')
        self.assertAlmostEqual(crit, r_min * 0.5, places=3)

    def test_spiral_length_positive(self):
        ls = g.spiral_length(80, 230, rate_c=0.5)
        self.assertGreater(ls, 0)

    def test_osd_80(self):
        self.assertEqual(g.osd_table(80), 370.0)


if __name__ == '__main__':
    unittest.main()
