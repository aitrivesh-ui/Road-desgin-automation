# -*- coding: utf-8 -*-
"""IRC:66 profile core tests (Python 3, no Civil 3D)."""
from __future__ import annotations

import os
import sys
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
_PY = os.path.join(_ROOT, 'python')
if _PY not in sys.path:
    sys.path.insert(0, _PY)

import irc66_profile_core as p66  # noqa: E402


class TestIRC66Table(unittest.TestCase):
    def test_80_kmh_k_values(self) -> None:
        self.assertEqual(p66.k_required('crest', 80), 44.0)
        self.assertEqual(p66.k_required('sag', 80), 20.0)

    def test_k_actual(self) -> None:
        self.assertAlmostEqual(p66.k_actual(80.0, 2.0), 40.0)
        self.assertIsNone(p66.k_actual(0, 2.0))

    def test_formula_values(self) -> None:
        self.assertAlmostEqual(p66.k_crest_formula(120), 21.9, places=0)
        self.assertAlmostEqual(p66.k_sag_formula(120), 26.7, places=0)

    def test_table_enforcement_uses_handbook(self) -> None:
        self.assertEqual(p66.k_required('crest', 80), 44.0)
        self.assertGreater(p66.k_required('crest', 80), p66.k_crest_formula(120))


class TestClassifyPVI(unittest.TestCase):
    def _rows(self, elevs):
        stas = [i * 100.0 for i in range(len(elevs))]
        return [
            {'station_m': str(stas[i]), 'elevation_m': str(elevs[i]), 'curve_length_m': '0'}
            for i in range(len(elevs))
        ]

    def test_crest(self) -> None:
        rows = self._rows([100.0, 110.0, 100.0])
        rows[1]['curve_length_m'] = '80'
        self.assertEqual(p66.classify_pvi(rows, 1), 'crest')

    def test_sag(self) -> None:
        rows = self._rows([110.0, 100.0, 110.0])
        rows[1]['curve_length_m'] = '80'
        self.assertEqual(p66.classify_pvi(rows, 1), 'sag')


class TestValidation(unittest.TestCase):
    def test_short_crest_vc_warns(self) -> None:
        rows = [
            {'station_m': '0', 'elevation_m': '100', 'curve_length_m': '0'},
            {'station_m': '100', 'elevation_m': '110', 'curve_length_m': '80'},
            {'station_m': '200', 'elevation_m': '100', 'curve_length_m': '0'},
        ]
        issues = p66.validate_pvi_row(rows, 1, 80)
        codes = [c for _, c, _, _ in issues]
        self.assertIn('IRC66_K_CREST', codes)

    def test_drainage_low_grade(self) -> None:
        rows = [
            {'station_m': '0', 'elevation_m': '100', 'curve_length_m': '0'},
            {'station_m': '1000', 'elevation_m': '103', 'curve_length_m': '0'},
        ]
        issues = p66.tangent_issues(rows, 8.0, 0.5, kerbed_road=True, vd_kph=80)
        codes = [c for _, c, _, _ in issues]
        self.assertIn('IRC73_DRAINAGE', codes)

    def test_pvi_table_shape(self) -> None:
        rows = [
            {'station_m': '0', 'elevation_m': '100', 'curve_length_m': '0'},
            {'station_m': '100', 'elevation_m': '110', 'curve_length_m': '80'},
            {'station_m': '200', 'elevation_m': '100', 'curve_length_m': '0'},
        ]
        tbl = p66.build_pvi_table_records(rows, 80, 'FG', 'CL', 'plain')
        self.assertEqual(tbl['contract_version'], 1)
        self.assertEqual(len(tbl['pvis']), 3)
        mid = tbl['pvis'][1]
        self.assertEqual(mid['curve_type'], 'crest')
        self.assertIn('IRC66_K_CREST', mid['validation'])


if __name__ == '__main__':
    unittest.main()
