# -*- coding: utf-8 -*-
"""
Pipeline data contract — shared step order, artifacts, and dependencies.
Used by preflight (Python 3) and m8_run_all.py (IronPython 2 via exec).
"""
from __future__ import absolute_import

import os

CONTRACT_VERSION = 1

# Canonical M8 run order (file-based pipeline).
DEFAULT_STEPS_WITH_MARKINGS = ['m1', 'm2', 'm3', 'm4', 'm0', 'm5', 'm6', 'm7']
DEFAULT_STEPS_NO_MARKINGS = ['m1', 'm2', 'm3', 'm4', 'm5', 'm6', 'm7']

# step id -> paths.* keys this step should produce when successful
ARTIFACT_OUTPUTS = {
    'm1': ['curve_table', 'alignment_meta'],
    'm2': ['pvi_table'],
    'm3': ['irc37_cache'],
    'm4': ['volumes_csv', 'mass_haul_csv', 'mass_haul_meta', 'fill_depth_csv'],
    'm0': ['marking_quantities'],
    'm5': [],
    'm6': ['dpr_sheet_manifest'],
    'm7': ['boq_csv'],
}

# step id -> paths.* keys that must exist as files BEFORE the step runs
PIPELINE_UPSTREAM = {
    'm1': ['alignment_pi'],
    'm2': ['profile_pvis'],
    'm3': ['section_widths'],
    'm4': [],
    'm0': ['markings_schedule', 'curve_table'],
    'm5': ['signage'],
    'm6': [],
    'm7': ['payitems'],
}

# Optional upstream (WARN if missing when step enabled)
PIPELINE_UPSTREAM_OPTIONAL = {
    'm5': ['curve_table', 'alignment_meta', 'fill_depth_csv'],
    'm6': ['alignment_meta', 'mass_haul_meta', 'mass_haul_csv', 'irc37_cache'],
    'm7': ['volumes_csv', 'marking_quantities', 'irc37_cache'],
}

# If step X disabled, downstream steps Y may need X's outputs pre-seeded
DOWNSTREAM_NEEDS = {
    'm1': ['m0', 'm5'],
    'm2': [],
    'm3': ['m7'],
    'm4': ['m7', 'm5'],
    'm0': ['m7'],
}

MARKING_QTY_HEADERS = [
    'mark_type',
    'material',
    'length_m',
    'area_m2',
    'chainage_from',
    'chainage_to',
]

CURVE_TABLE_CSV_HEADERS = ['station_m', 'radius_m', 'pi_id', 'design_speed_kph']

# Alias: handbook pavement_irc37.json -> irc37_cache
PAVEMENT_PATH_KEYS = ('irc37_cache', 'pavement_design')


def resolve_pavement_key(paths):
    """Return paths key for IRC:37 cache (canonical irc37_cache)."""
    if not paths:
        return 'irc37_cache'
    for k in PAVEMENT_PATH_KEYS:
        if paths.get(k):
            return k
    return 'irc37_cache'


def default_steps(cfg):
    pipeline = cfg.get('pipeline') or {}
    if pipeline.get('steps'):
        steps = [str(s).strip().lower() for s in pipeline['steps'] if str(s).strip()]
    else:
        run_markings = pipeline.get('run_markings', True)
        if run_markings is False:
            steps = list(DEFAULT_STEPS_NO_MARKINGS)
        else:
            steps = list(DEFAULT_STEPS_WITH_MARKINGS)
    if pipeline.get('skip_profile'):
        steps = [s for s in steps if s != 'm2']
    return steps


def enabled_steps(cfg, step_filter):
    """
    Merge pipeline.steps / defaults with optional Dynamo IN[1] comma filter.
    step_filter wins when non-empty.
    """
    pipeline = cfg.get('pipeline') or {}
    skip_m2 = bool(pipeline.get('skip_profile'))
    base = default_steps(cfg)
    if step_filter:
        requested = [s.strip().lower() for s in step_filter.split(',') if s.strip()]
        order = base + [s for s in requested if s not in base]
        steps = [s for s in order if s in requested]
    else:
        steps = base
    if skip_m2:
        steps = [s for s in steps if s != 'm2']
    return steps


def step_sort_key(step, order_list):
    try:
        return order_list.index(step)
    except ValueError:
        return 999


def ordered_steps(steps, cfg):
    order = default_steps(cfg)
    return sorted(steps, key=lambda s: step_sort_key(s, order))


def verify_step_outputs(step, paths, root, resolve_path_fn):
    """
    Returns list of (severity, message) for missing expected outputs.
    severity: ERROR or WARN
    """
    issues = []
    keys = ARTIFACT_OUTPUTS.get(step) or []
    for key in keys:
        rel = paths.get(key)
        if not rel:
            continue
        full = resolve_path_fn(root, rel)
        if not os.path.isfile(full):
            issues.append(
                (
                    'ERROR',
                    'After %s: expected artifact missing paths.%s -> %s'
                    % (step.upper(), key, full),
                )
            )
        else:
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            issues.append(
                (
                    'INFO',
                    'WROTE paths.%s (%d bytes): %s' % (key, size, full),
                )
            )
    return issues


def validate_pipeline_artifacts(cfg, root, resolve_path_fn):
    """Preflight: check upstream files for enabled steps."""
    lines = []
    paths = cfg.get('paths') or {}
    pipeline = cfg.get('pipeline') or {}
    steps = default_steps(cfg)
    if pipeline.get('steps'):
        steps = [str(s).strip().lower() for s in pipeline['steps'] if str(s).strip()]

    lines.append('Pipeline contract version: %s' % CONTRACT_VERSION)
    lines.append('Enabled steps (config): %s' % ', '.join(steps))
    lines.append('')

    for step in steps:
        for key in PIPELINE_UPSTREAM.get(step) or []:
            rel = paths.get(key)
            if not rel:
                lines.append('WARN: Step %s needs paths.%s but key is missing.' % (step, key))
                continue
            full = resolve_path_fn(root, rel)
            if not os.path.isfile(full):
                lines.append(
                    'ERROR: Pipeline — %s requires paths.%s before run; file missing: %s'
                    % (step.upper(), key, full)
                )
            else:
                lines.append('OK: Pipeline — %s upstream paths.%s present.' % (step.upper(), key))

        for key in PIPELINE_UPSTREAM_OPTIONAL.get(step) or []:
            if key == 'irc37_cache':
                key = resolve_pavement_key(paths)
            rel = paths.get(key)
            if not rel:
                continue
            full = resolve_path_fn(root, rel)
            if not os.path.isfile(full):
                if step == 'm0' and key == 'curve_table':
                    if 'm1' in steps:
                        lines.append(
                            'INFO: paths.curve_table not found yet — M1 will create it when run before M0.'
                        )
                    else:
                        lines.append(
                            'ERROR: Pipeline — M0 enabled but paths.curve_table missing and M1 not in steps: %s'
                            % full
                        )
                elif step == 'm7' and key == 'volumes_csv':
                    if 'm4' in steps:
                        lines.append(
                            'INFO: paths.volumes_csv not found yet — M4 will create it when run before M7.'
                        )
                    else:
                        lines.append(
                            'WARN: Pipeline — M7 enabled but paths.volumes_csv missing (M4 not in steps): %s'
                            % full
                        )
                elif step == 'm7' and key == 'marking_quantities':
                    if 'm0' in steps:
                        lines.append(
                            'WARN: Pipeline — M0 enabled but paths.marking_quantities not found yet: %s'
                            % full
                        )
                    else:
                        lines.append('INFO: paths.marking_quantities optional for M7: %s' % full)
                elif step == 'm5' and key == 'curve_table':
                    lines.append(
                        'WARN: Pipeline — M5: paths.curve_table missing (OSD-aware spacing degraded): %s'
                        % full
                    )
                else:
                    lines.append(
                        'WARN: Pipeline — %s optional paths.%s missing: %s' % (step.upper(), key, full)
                    )
            else:
                lines.append('OK: Pipeline — %s optional paths.%s present.' % (step.upper(), key))

    all_steps = set(DEFAULT_STEPS_WITH_MARKINGS)
    disabled = sorted(all_steps - set(steps))
    for d in disabled:
        for consumer in DOWNSTREAM_NEEDS.get(d) or []:
            if consumer in steps:
                lines.append(
                    'WARN: Pipeline — %s disabled but %s still enabled; ensure %s outputs exist or pre-seed files.'
                    % (d.upper(), consumer.upper(), d.upper())
                )

    mq_rel = paths.get('marking_quantities')
    if mq_rel:
        mq_full = resolve_path_fn(root, mq_rel)
        if os.path.isfile(mq_full):
            try:
                headers = read_header_row(mq_full)
            except Exception as ex:
                lines.append('ERROR: marking_quantities CSV unreadable: %s' % ex)
            else:
                missing = [c for c in MARKING_QTY_HEADERS if c not in set(headers)]
                if missing:
                    lines.append(
                        'WARN: marking_quantities missing columns: %s' % ', '.join(missing)
                    )
                else:
                    lines.append('OK: marking_quantities CSV headers match contract.')

    return lines


def read_header_row(path):
    import csv

    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        row = next(csv.reader(f), [])
    return [h.strip() for h in row]


def example_path_keys():
    """Keys expected in project.example.json for contract tests."""
    return sorted(
        set(
            list(CSV_PATH_KEYS_FOR_CONTRACT())
            + [
                'volumes_csv',
                'boq_csv',
                'qa_log',
                'curve_table',
                'alignment_meta',
                'pvi_table',
                'mass_haul_csv',
                'mass_haul_meta',
                'fill_depth_csv',
                'irc37_cache',
                'marking_quantities',
                'markings_schedule',
                'signage_generated',
                'dpr_sheet_manifest',
            ]
        )
    )


def CSV_PATH_KEYS_FOR_CONTRACT():
    return [
        'alignment_pi',
        'profile_pvis',
        'section_widths',
        'signage',
        'payitems',
    ]
