# -*- coding: utf-8 -*-
"""
M8 — Run M1→M7 from a single project.json (IronPython-friendly, no cross-imports).

Dynamo inputs:
  IN[0] : str — absolute path to config/project.json
  IN[1] : str — optional comma list of steps to run (default all), e.g. "m1,m2,m4"

Each step execs the corresponding python file with a synthetic IN list; results are concatenated.
"""
import clr
import json
import codecs
import os
import time

clr.AddReference('AcMgd')
clr.AddReference('AcDbMgd')
clr.AddReference('AecBaseMgd')
clr.AddReference('AeccDbMgd')


def _resolve(base, rel):
    rel = rel.replace('/', os.sep)
    return os.path.normpath(os.path.join(base, rel))


def _exec_py(path, in_list, g_extra):
    g = {'__builtins__': __builtins__, 'clr': clr}
    g.update(g_extra)
    g['IN'] = in_list
    with codecs.open(path, 'r', encoding='utf-8') as fp:
        src = fp.read()
    co = compile(src, path, 'exec')
    try:
        exec(co, g)
    except TypeError:
        exec co in g
    return g.get('OUT', '')


def run(project_json, step_filter):
    if not os.path.isfile(project_json):
        return 'ERROR: project.json not found: ' + str(project_json)

    cfg = json.load(codecs.open(project_json, 'r', encoding='utf-8'))
    base = os.path.dirname(os.path.abspath(project_json))
    root = os.path.normpath(os.path.join(base, '..'))
    pydir = os.path.join(root, 'python')
    paths = cfg.get('paths', {})
    names = cfg.get('names', {})
    styles = cfg.get('styles', {})
    design = cfg.get('design', {})

    def rp(key):
        return _resolve(root, paths[key])

    steps = [s.strip().lower() for s in (step_filter or 'm1,m2,m3,m4,m5,m6,m7').split(',') if s.strip()]
    log = []
    qa_rel = paths.get('qa_log', 'out/qa/run_log.txt')
    qa_path = _resolve(root, qa_rel)
    t_run0 = time.time()
    manifest_steps = []

    g_extra = {}

    if 'm1' in steps:
        t0 = time.time()
        out = _exec_py(
            os.path.join(pydir, 'm1_alignment_from_csv.py'),
            [
                rp('alignment_pi'),
                names.get('alignment', 'ALIGN'),
                styles.get('alignment', 'Standard'),
                styles.get('alignment_label', 'Standard'),
                float(design.get('start_station', 0.0)),
            ],
            g_extra,
        )
        log.append('[M1] ' + str(out))
        manifest_steps.append({'step': 'm1', 'seconds': round(time.time() - t0, 3), 'output_preview': str(out)[:400]})

    if 'm2' in steps:
        t0 = time.time()
        out = _exec_py(
            os.path.join(pydir, 'm2_profile_from_csv.py'),
            [
                rp('profile_pvis'),
                names.get('alignment', 'ALIGN'),
                names.get('profile_fg', 'FG'),
                '0',
                styles.get('profile', 'Standard'),
                styles.get('profile_label', 'Standard'),
                float(design.get('max_grade_pct', 8.0)),
                float(design.get('min_grade_pct', 0.3)),
            ],
            g_extra,
        )
        log.append('[M2] ' + str(out))
        manifest_steps.append({'step': 'm2', 'seconds': round(time.time() - t0, 3), 'output_preview': str(out)[:400]})

    if 'm3' in steps:
        t0 = time.time()
        out = _exec_py(
            os.path.join(pydir, 'm3_corridor_regions_from_csv.py'),
            [
                rp('section_widths'),
                names.get('corridor', 'COR'),
                names.get('assembly', 'BasicLaneAssembly'),
            ],
            g_extra,
        )
        log.append('[M3] ' + str(out))
        manifest_steps.append({'step': 'm3', 'seconds': round(time.time() - t0, 3), 'output_preview': str(out)[:400]})

    if 'm4' in steps:
        t0 = time.time()
        out = _exec_py(
            os.path.join(pydir, 'm4_corridor_rebuild_volumes.py'),
            [
                names.get('corridor', 'COR'),
                names.get('surface_eg', 'EG'),
                names.get('surface_fg', 'FG'),
                rp('volumes_csv'),
                names.get('corridor', 'COR') + '_VOL',
            ],
            g_extra,
        )
        log.append('[M4] ' + str(out))
        manifest_steps.append({'step': 'm4', 'seconds': round(time.time() - t0, 3), 'output_preview': str(out)[:400]})

    if 'm5' in steps:
        t0 = time.time()
        out = _exec_py(
            os.path.join(pydir, 'm5_signage_from_csv.py'),
            [
                rp('signage'),
                names.get('alignment', 'ALIGN'),
                names.get('layers', {}).get('signage', 'C-SGN-FURN'),
                'ROAD_SIGN_CSV',
            ],
            g_extra,
        )
        log.append('[M5] ' + str(out))
        manifest_steps.append({'step': 'm5', 'seconds': round(time.time() - t0, 3), 'output_preview': str(out)[:400]})

    if 'm6' in steps:
        t0 = time.time()
        out_dir = os.path.join(root, 'out', 'sheets')
        out = _exec_py(
            os.path.join(pydir, 'm6_sheets_helper.py'),
            [names.get('alignment', 'ALIGN'), out_dir],
            g_extra,
        )
        log.append('[M6] ' + str(out))
        manifest_steps.append({'step': 'm6', 'seconds': round(time.time() - t0, 3), 'output_preview': str(out)[:400]})

    if 'm7' in steps:
        t0 = time.time()
        volp = rp('volumes_csv') if paths.get('volumes_csv') else ''
        out = _exec_py(
            os.path.join(pydir, 'm7_boq_rollup.py'),
            [
                volp,
                names.get('layers', {}).get('marking', 'C-ROAD-MARK'),
                names.get('layers', {}).get('signage', 'C-SGN-FURN'),
                rp('payitems'),
                rp('boq_csv'),
                names.get('corridor', ''),
            ],
            g_extra,
        )
        log.append('[M7] ' + str(out))
        manifest_steps.append({'step': 'm7', 'seconds': round(time.time() - t0, 3), 'output_preview': str(out)[:400]})

    summary = '\n'.join(log)
    try:
        d = os.path.dirname(qa_path)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with codecs.open(qa_path, 'a', encoding='utf-8') as fq:
            fq.write('\n---\n' + summary + '\n')
    except Exception:
        pass

    try:
        manifest = {
            'project_json': os.path.abspath(project_json),
            'steps': steps,
            'total_seconds': round(time.time() - t_run0, 3),
            'step_details': manifest_steps,
        }
        md = os.path.dirname(qa_path)
        if md and not os.path.isdir(md):
            os.makedirs(md)
        mf = os.path.join(md, 'last_run_manifest.json')
        with codecs.open(mf, 'w', encoding='utf-8') as fm:
            fm.write(json.dumps(manifest, indent=2))
            fm.write('\n')
    except Exception:
        pass

    return 'OK: M8 finished.\n' + summary


project_json = IN[0]
step_filter = IN[1] if len(IN) > 1 else ''

OUT = run(project_json, step_filter)
