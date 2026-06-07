# -*- coding: utf-8 -*-
"""Tests for pipeline_contract.py and example project keys."""
from __future__ import annotations

import json
import os
import sys
import unittest

TOOLS = os.path.dirname(os.path.abspath(__file__))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import pipeline_contract as pc  # noqa: E402
import preflight_validate as pv  # noqa: E402


class TestPipelineContract(unittest.TestCase):
    def test_default_steps_with_markings(self) -> None:
        steps = pc.default_steps({})
        self.assertEqual(steps[0], 'm1')
        self.assertIn('m0', steps)
        self.assertLess(steps.index('m0'), steps.index('m5'))
        self.assertLess(steps.index('m1'), steps.index('m0'))

    def test_default_steps_no_markings(self) -> None:
        steps = pc.default_steps({'pipeline': {'run_markings': False}})
        self.assertNotIn('m0', steps)

    def test_skip_profile_omits_m2(self) -> None:
        steps = pc.default_steps({'pipeline': {'skip_profile': True}})
        self.assertNotIn('m2', steps)
        enabled = pc.enabled_steps({'pipeline': {'skip_profile': True}}, 'm1,m2,m3')
        self.assertNotIn('m2', enabled)

    def test_enabled_steps_filter(self) -> None:
        cfg = {'pipeline': {'run_markings': True}}
        steps = pc.enabled_steps(cfg, 'm1,m7')
        self.assertEqual(steps, ['m1', 'm7'])

    def test_pavement_key_canonical(self) -> None:
        self.assertEqual(pc.resolve_pavement_key({'irc37_cache': 'out/x.json'}), 'irc37_cache')
        self.assertEqual(pc.resolve_pavement_key({'pavement_design': 'out/x.json'}), 'pavement_design')

    def test_m1_artifact_outputs(self) -> None:
        self.assertIn('curve_table', pc.ARTIFACT_OUTPUTS['m1'])
        self.assertIn('alignment_meta', pc.ARTIFACT_OUTPUTS['m1'])

    def test_m6_artifact_outputs(self) -> None:
        self.assertIn('dpr_sheet_manifest', pc.ARTIFACT_OUTPUTS['m6'])

    def test_example_json_has_contract_keys(self) -> None:
        example = os.path.join(os.path.dirname(TOOLS), 'config', 'project.example.json')
        with open(example, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        paths = cfg.get('paths') or {}
        for key in pc.example_path_keys():
            self.assertIn(key, paths, 'missing paths.%s in project.example.json' % key)
        self.assertIn('pipeline', cfg)
        self.assertTrue(cfg['pipeline'].get('run_markings'))


class TestPipelinePreflight(unittest.TestCase):
    def test_m0_missing_curve_table_errors_without_m1(self) -> None:
        import shutil
        import tempfile

        tmp = tempfile.mkdtemp(prefix='road_pipe_')
        try:
            root = os.path.join(tmp, 'civil3d_automation')
            os.makedirs(os.path.join(root, 'config'))
            os.makedirs(os.path.join(root, 'csv'))
            pj = os.path.join(root, 'config', 'project.json')
            cfg = {
                'paths': {
                    'alignment_pi': 'csv/alignment_pi.csv',
                    'profile_pvis': 'csv/profile_pvis.csv',
                    'section_widths': 'csv/section_widths.csv',
                    'signage': 'csv/signage_schedule.csv',
                    'payitems': 'csv/payitems.csv',
                    'curve_table': 'out/curve_table.csv',
                    'volumes_csv': 'out/volumes.csv',
                    'boq_csv': 'out/boq.csv',
                },
                'pipeline': {'steps': ['m0'], 'run_markings': True},
            }
            with open(pj, 'w', encoding='utf-8') as f:
                json.dump(cfg, f)
            lines = pc.validate_pipeline_artifacts(cfg, root, pv.resolve_path)
            self.assertTrue(any('M0' in x and 'curve_table' in x and 'ERROR' in x for x in lines))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_disabled_m4_warns_m7(self) -> None:
        cfg = {
            'paths': {'volumes_csv': 'out/volumes.csv'},
            'pipeline': {'steps': ['m1', 'm2', 'm3', 'm7']},
        }
        root = os.path.dirname(TOOLS)
        lines = pc.validate_pipeline_artifacts(cfg, root, pv.resolve_path)
        self.assertTrue(any('m4 disabled' in x.lower() or 'M4 disabled' in x for x in lines))


if __name__ == '__main__':
    unittest.main()
