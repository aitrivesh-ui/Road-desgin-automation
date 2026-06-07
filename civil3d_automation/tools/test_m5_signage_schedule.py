# -*- coding: utf-8 -*-
"""Unit tests for m5_build_signage_schedule (no Civil 3D)."""
from __future__ import absolute_import

import csv
import json
import os
import sys
import tempfile
import unittest

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(TOOLS, '..'))
PY = os.path.join(ROOT, 'python')
if PY not in sys.path:
    sys.path.insert(0, PY)

import m5_build_signage_schedule as m5b  # noqa: E402


def _write_csv(path, headers, rows):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in rows:
            w.writerow(r)


class TestM5SignageSchedule(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = self.tmp
        os.makedirs(os.path.join(self.root, 'config'))
        cat_src = os.path.join(ROOT, 'config', 'irc67_signage_catalogue.json')
        if os.path.isfile(cat_src):
            import shutil
            shutil.copy(cat_src, os.path.join(self.root, 'config', 'irc67_signage_catalogue.json'))

    def _cfg(self, **path_overrides):
        paths = {
            'signage': 'csv/manual.csv',
            'curve_table': 'out/curve_table.csv',
            'alignment_meta': 'out/alignment_meta.json',
            'fill_depth_csv': 'out/fill_depth.csv',
            'signage_generated': 'out/signage_generated.csv',
        }
        paths.update(path_overrides)
        return {
            'paths': paths,
            'design': {
                'start_station': 0.0,
                'km_post_spacing_m': 500,
                'road_class': 'nh_sh',
                'signage': {
                    'auto_mode': True,
                    'merge_manual': True,
                    'default_offset_m': 4.5,
                    'guardrail_fill_threshold_m': 3,
                    'warning_advance_m': 60,
                },
            },
        }

    def test_warning_60m_before_tc(self):
        ct = os.path.join(self.tmp, 'out', 'curve_table.csv')
        _write_csv(
            ct,
            ['station_m', 'radius_m', 'pi_id', 'design_speed_kph', 'station_tc', 'station_ec', 'L_arc', 'side'],
            [['550', '200', 'PI2', '80', '500', '600', '100', 'R']],
        )
        meta = os.path.join(self.tmp, 'out', 'alignment_meta.json')
        os.makedirs(os.path.dirname(meta), exist_ok=True)
        with open(meta, 'w', encoding='utf-8') as f:
            json.dump({'total_length_m': 2000}, f)
        cfg = self._cfg()
        rows, _ = m5b.build_schedule(cfg, self.tmp, [])
        warns = [r for r in rows if r.get('sign_code') in ('W-1', 'W-2')]
        self.assertEqual(len(warns), 1)
        self.assertAlmostEqual(float(warns[0]['station_m']), 440.0, places=2)
        self.assertEqual(warns[0]['side'], 'R')

    def test_delineator_spacing_r200(self):
        ct = os.path.join(self.tmp, 'out', 'curve_table.csv')
        _write_csv(
            ct,
            ['station_m', 'radius_m', 'pi_id', 'station_tc', 'station_ec', 'L_arc', 'side'],
            [['550', '200', 'PI2', '500', '600', '100', 'R']],
        )
        meta = os.path.join(self.tmp, 'out', 'alignment_meta.json')
        os.makedirs(os.path.dirname(meta), exist_ok=True)
        with open(meta, 'w', encoding='utf-8') as f:
            json.dump({'total_length_m': 1000}, f)
        cfg = self._cfg()
        rows, _ = m5b.build_schedule(cfg, self.tmp, [])
        dels = [r for r in rows if r.get('sign_code') == 'DELINEATOR']
        # stations 500,508,...,600 inclusive => 14 rows
        import math
        expected = int(math.floor(100 / 8)) + 1
        self.assertEqual(len(dels), expected)
        self.assertTrue(all(r.get('side') == 'BOTH' for r in dels))

    def test_guardrail_threshold(self):
        fd = os.path.join(self.tmp, 'out', 'fill_depth.csv')
        _write_csv(
            fd,
            ['station_m', 'fill_depth_m', 'max_fill_height_m'],
            [['100', '2.5', '2.5'], ['200', '3.5', '3.5'], ['300', '4.0', '4.0']],
        )
        meta = os.path.join(self.tmp, 'out', 'alignment_meta.json')
        os.makedirs(os.path.dirname(meta), exist_ok=True)
        with open(meta, 'w', encoding='utf-8') as f:
            json.dump({'total_length_m': 500}, f)
        cfg = self._cfg()
        rows, _ = m5b.build_schedule(cfg, self.tmp, [])
        gr = [r for r in rows if r.get('sign_code') == 'GUARDRAIL']
        stas = sorted(float(r['station_m']) for r in gr)
        self.assertEqual(stas, [200.0, 300.0])

    def test_km_post_spacing(self):
        meta = os.path.join(self.tmp, 'out', 'alignment_meta.json')
        os.makedirs(os.path.dirname(meta), exist_ok=True)
        with open(meta, 'w', encoding='utf-8') as f:
            json.dump({'total_length_m': 2000}, f)
        cfg = self._cfg()
        rows, _ = m5b.build_schedule(cfg, self.tmp, [])
        km = [r for r in rows if r.get('sign_code') == 'KM']
        stas = [float(r['station_m']) for r in km]
        self.assertEqual(stas, [0.0, 500.0, 1000.0, 1500.0, 2000.0])
        self.assertTrue(all(r.get('side') == 'L' for r in km))

    def test_merge_manual_precedence(self):
        manual = os.path.join(self.tmp, 'csv', 'manual.csv')
        _write_csv(
            manual,
            ['row', 'station_m', 'offset_m', 'side', 'sign_code', 'block_name', 'rotation_deg'],
            [['1', '440.0', '4.5', 'R', 'W-2', 'SGN_W2_CURVE', '']],
        )
        ct = os.path.join(self.tmp, 'out', 'curve_table.csv')
        _write_csv(
            ct,
            ['station_m', 'radius_m', 'station_tc', 'station_ec', 'L_arc', 'side'],
            [['550', '200', '500', '600', '100', 'R']],
        )
        meta = os.path.join(self.tmp, 'out', 'alignment_meta.json')
        os.makedirs(os.path.dirname(meta), exist_ok=True)
        with open(meta, 'w', encoding='utf-8') as f:
            json.dump({'total_length_m': 800}, f)
        cfg = self._cfg(signage='csv/manual.csv')
        rows, _ = m5b.build_schedule(cfg, self.tmp, [])
        at_440 = [r for r in rows if abs(float(r['station_m']) - 440.0) < 0.01]
        w2 = [r for r in at_440 if r.get('block_name') == 'SGN_W2_CURVE' and r.get('side') == 'R']
        self.assertEqual(len(w2), 1)
        self.assertEqual(w2[0].get('source'), 'manual')

    def test_missing_curve_table_warns(self):
        cfg = self._cfg(curve_table='out/missing_curve.csv')
        meta = os.path.join(self.tmp, 'out', 'alignment_meta.json')
        os.makedirs(os.path.dirname(meta), exist_ok=True)
        with open(meta, 'w', encoding='utf-8') as f:
            json.dump({'total_length_m': 1000}, f)
        warnings = []
        rows, wlog = m5b.build_schedule(cfg, self.tmp, warnings)
        self.assertTrue(any('curve_table' in w for w in wlog))
        self.assertTrue(any(r.get('sign_code') == 'KM' for r in rows))
        self.assertFalse(any(r.get('sign_code') in ('W-1', 'W-2') for r in rows))


if __name__ == '__main__':
    unittest.main()
