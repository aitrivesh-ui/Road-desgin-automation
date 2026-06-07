# -*- coding: utf-8 -*-
"""Tests for dpr_sheet_core.py (M6 DPR manifest)."""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import unittest

PY = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'python')
if PY not in sys.path:
    sys.path.insert(0, PY)

import dpr_sheet_core as dsc  # noqa: E402


class TestFormatDrgNo(unittest.TestCase):
    def test_pp_serial(self) -> None:
        self.assertEqual(dsc.format_drg_no('PKG-01', 'PP', 1), 'PKG-01/PP/001')
        self.assertEqual(dsc.format_drg_no('PKG-01', 'PP', 12), 'PKG-01/PP/012')

    def test_gen(self) -> None:
        self.assertEqual(dsc.format_drg_no('PKG-02', 'GEN', 1), 'PKG-02/GEN/001')


class TestSheetCounts(unittest.TestCase):
    def test_pp_count_1400m(self) -> None:
        m = dsc.build_sheet_manifest({'pp_sheet_length_m': 500}, 1400, 71, 0)
        self.assertEqual(m['sheet_counts']['PP'], 3)

    def test_xs_count_71_stations(self) -> None:
        m = dsc.build_sheet_manifest({'xs_per_sheet': 20}, 1400, 71, 0)
        self.assertEqual(m['sheet_counts']['XS'], 4)

    def test_pp_chainage_ranges(self) -> None:
        m = dsc.build_sheet_manifest({'pp_sheet_length_m': 500}, 1400, 0, 0)
        pp = [s for s in m['sheets'] if s['code'] == 'PP']
        self.assertEqual(pp[0]['ch_from'], 0.0)
        self.assertEqual(pp[0]['ch_to'], 500.0)
        self.assertEqual(pp[2]['ch_to'], 1400.0)

    def test_gen_single(self) -> None:
        m = dsc.build_sheet_manifest({}, 100, 10, 0)
        self.assertEqual(m['sheet_counts']['GEN'], 1)
        self.assertEqual(m['sheet_counts']['TCS'], 1)
        self.assertEqual(m['sheet_counts']['PVT'], 1)

    def test_pvt_layers(self) -> None:
        layers = [{'name': 'GSB', 'thickness_mm': 200}]
        m = dsc.build_sheet_manifest({}, 100, 10, 0, layers)
        pvt = [s for s in m['sheets'] if s['code'] == 'PVT'][0]
        self.assertEqual(pvt['pavement_layers'], layers)


class TestResolvers(unittest.TestCase):
    def test_alignment_meta_length(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meta = os.path.join(tmp, 'meta.json')
            with open(meta, 'w', encoding='utf-8') as f:
                json.dump({'total_length_m': 1234.5}, f)
            self.assertEqual(dsc.resolve_total_length_m(meta), 1234.5)

    def test_mass_haul_meta_stations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mh = os.path.join(tmp, 'mh_meta.json')
            with open(mh, 'w', encoding='utf-8') as f:
                json.dump({'sample_count': 71}, f)
            n = dsc.resolve_n_stations(mh, '', 1400, 20)
            self.assertEqual(n, 71)

    def test_xs_validation_warn_no_stations(self) -> None:
        m = dsc.build_sheet_manifest({'xs_per_sheet': 20}, 1400, 0, 0)
        msg = dsc.validate_xs_station_count(m)
        self.assertIsNotNone(msg)


class TestManifestWrite(unittest.TestCase):
    def test_cli_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, 'pkg')
            os.makedirs(os.path.join(root, 'config'))
            os.makedirs(os.path.join(root, 'out'))
            meta = os.path.join(root, 'out', 'alignment_meta.json')
            with open(meta, 'w', encoding='utf-8') as f:
                json.dump({'total_length_m': 1400}, f)
            pj = os.path.join(root, 'config', 'project.json')
            cfg = {
                'paths': {
                    'alignment_meta': 'out/alignment_meta.json',
                    'dpr_sheet_manifest': 'out/dpr_sheet_manifest.json',
                    'mass_haul_meta': 'out/mass_haul_meta.json',
                },
                'design': {'start_station': 0, 'volume_sample_interval_m': 20},
                'dpr': {'package_id': 'PKG-01', 'pp_sheet_length_m': 500, 'xs_per_sheet': 20},
            }
            with open(pj, 'w', encoding='utf-8') as f:
                json.dump(cfg, f)
            mh = os.path.join(root, 'out', 'mass_haul_meta.json')
            with open(mh, 'w', encoding='utf-8') as f:
                json.dump({'sample_count': 71}, f)
            rc = dsc.main(['--project', pj])
            self.assertEqual(rc, 0)
            out = os.path.join(root, 'out', 'dpr_sheet_manifest.json')
            self.assertTrue(os.path.isfile(out))
            with open(out, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.assertEqual(data['sheet_counts']['PP'], 3)
            self.assertEqual(data['sheet_counts']['XS'], 4)


if __name__ == '__main__':
    unittest.main()
