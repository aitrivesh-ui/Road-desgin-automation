# -*- coding: utf-8 -*-
"""
M8 — Run pipeline steps from a single project.json (IronPython-friendly, no cross-imports).

Dynamo inputs:
  IN[0] : str — absolute path to config/project.json
  IN[1] : str — optional comma list of steps to run (overrides pipeline.steps subset), e.g. "m1,m2,m4"

Default order (pipeline.run_markings true): m1,m2,m3,m4,m0,m5,m6,m7
See civil3d_automation/TESTING.md and tools/pipeline_contract.py
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


def _load_py_helpers(pydir):
    extra = {}
    for name in ('_log_utils',):
        p = os.path.join(pydir, name + '.py')
        if os.path.isfile(p):
            with codecs.open(p, 'r', encoding='utf-8') as fp:
                exec(compile(fp.read(), p, 'exec'), extra)
    return extra


def _load_pipeline_contract(root):
    p = os.path.join(root, 'tools', 'pipeline_contract.py')
    g = {}
    if os.path.isfile(p):
        with codecs.open(p, 'r', encoding='utf-8') as fp:
            exec(compile(fp.read(), p, 'exec'), g)
    return g


def _exec_py(path, in_list, g_extra):
    g = {'__builtins__': __builtins__, 'clr': clr, '__file__': path}
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


def _norm_out(raw, step_id, g_extra):
    if 'normalize_out' in g_extra:
        return g_extra['normalize_out'](raw, step_id.upper())
    return raw


def _out_preview(out):
    if isinstance(out, dict):
        leg = out.get('legacy') or ''
        counts = out.get('counts') or {}
        return (leg or str(counts))[:400]
    return str(out)[:400]


def _pavement_path_key(paths, pc):
    if pc and 'resolve_pavement_key' in pc:
        return pc['resolve_pavement_key'](paths)
    return 'irc37_cache' if paths.get('irc37_cache') else 'pavement_design'


def _run_step_m1(pydir, rp, names, styles, design, paths, g_extra, _record):
    t0 = time.time()
    in_list = [
        rp('alignment_pi'),
        names.get('alignment', 'ALIGN'),
        styles.get('alignment', 'Standard'),
        styles.get('alignment_label', 'Standard'),
        float(design.get('start_station', 0.0)),
        rp('curve_table'),
        float(design.get('design_speed_kph', 80) or 80),
    ]
    meta = rp('alignment_meta')
    if meta:
        in_list.append(meta)
    out = _exec_py(
        os.path.join(pydir, 'm1_alignment_from_csv.py'),
        in_list,
        g_extra,
    )
    return _record('m1', out, t0)


def _run_step_m2(pydir, rp, names, styles, design, g_extra, _record):
    t0 = time.time()
    in_list = [
        rp('profile_pvis'),
        names.get('alignment', 'ALIGN'),
        names.get('profile_fg', 'FG'),
        '0',
        styles.get('profile', 'Standard'),
        styles.get('profile_label', 'Standard'),
        float(design.get('max_grade_pct', 8.0)),
        float(design.get('min_grade_pct', 0.5)),
    ]
    pvi_path = rp('pvi_table')
    if pvi_path:
        in_list.append(pvi_path)
    out = _exec_py(os.path.join(pydir, 'm2_profile_from_csv.py'), in_list, g_extra)
    return _record('m2', out, t0)


def _run_step_m3(pydir, rp, names, design, paths, pc, g_extra, _record):
    t0 = time.time()
    irc = dict(design.get('irc37') or {})
    pave_key = _pavement_path_key(paths, pc)
    in_list = [
        rp('section_widths'),
        names.get('corridor', 'COR'),
        names.get('assembly', 'BasicLaneAssembly'),
        json.dumps(irc) if irc else '',
        rp(pave_key),
    ]
    meta = rp('alignment_meta')
    if meta:
        in_list.append(meta)
    thick = paths.get('assembly_thickness_report')
    if thick:
        in_list.append(rp('assembly_thickness_report'))
    width_rep = paths.get('section_width_report')
    if width_rep:
        in_list.append(rp('section_width_report'))
    out = _exec_py(os.path.join(pydir, 'm3_corridor_regions_from_csv.py'), in_list, g_extra)
    return _record('m3', out, t0)


def _run_step_m4(pydir, rp, paths, names, design, g_extra, _record):
    t0 = time.time()
    in_list = [
        names.get('corridor', 'COR'),
        names.get('surface_eg', 'EG'),
        names.get('surface_fg', 'FG'),
        rp('volumes_csv'),
        names.get('corridor', 'COR') + '_VOL',
        design.get('soil_type', 'ordinary_soil'),
        rp('mass_haul_csv'),
        rp('section_widths'),
        rp('alignment_meta'),
        design.get('volume_sample_interval_m', 20),
    ]
    fill_depth = paths.get('fill_depth_csv')
    if fill_depth:
        in_list.append(rp('fill_depth_csv'))
    else:
        in_list.append('')
    mass_meta = paths.get('mass_haul_meta')
    if mass_meta:
        in_list.append(rp('mass_haul_meta'))
    else:
        in_list.append('')
    out = _exec_py(
        os.path.join(pydir, 'm4_corridor_rebuild_volumes.py'),
        in_list,
        g_extra,
    )
    return _record('m4', out, t0)


def _run_step_m0(pydir, rp, names, design, g_extra, _record):
    t0 = time.time()
    spd = float(design.get('design_speed_kph', 80) or 80)
    in_list = [
        names.get('alignment', 'ALIGN'),
        rp('markings_schedule'),
        rp('curve_table'),
        rp('marking_quantities'),
        spd,
        'IRC35_ROAD_MARK_V2',
    ]
    out = _exec_py(os.path.join(pydir, 'm0_markings_from_config.py'), in_list, g_extra)
    return _record('m0', out, t0)


def _resolve_signage_csv(pydir, root, cfg, rp, g_extra):
    """Build generated schedule when design.signage.auto_mode; else manual paths.signage."""
    design = cfg.get('design') or {}
    signage_cfg = design.get('signage') or {}
    if not signage_cfg.get('auto_mode', False):
        return rp('signage')
    build_script = os.path.join(pydir, 'm5_build_signage_schedule.py')
    out_path = rp('signage_generated')
    if not out_path:
        paths = cfg.get('paths') or {}
        rel = paths.get('signage_generated', 'out/signage_generated.csv')
        out_path = _resolve(root, rel) if rel else ''
    if not os.path.isfile(build_script) or not out_path:
        return rp('signage')
    try:
        g = {'__builtins__': __builtins__}
        with codecs.open(build_script, 'r', encoding='utf-8') as fp:
            exec(compile(fp.read(), build_script, 'exec'), g)
        warnings = []
        g['run_build'](cfg, root, out_path)
        if 'log_add' in g_extra and warnings:
            for w in warnings:
                g_extra['log_add'](
                    g_extra.get('_m8_log') or {'entries': []},
                    'WARN', 'M5_BUILD', w, module='M8',
                )
        if os.path.isfile(out_path):
            return out_path
    except Exception as ex:
        if 'log_add' in g_extra:
            g_extra['log_add'](
                g_extra.get('_m8_log') or {'entries': []},
                'WARN', 'M5_BUILD_FAIL',
                'Signage schedule build failed: %s' % ex,
                module='M8',
            )
    return rp('signage')


def _run_step_m5(pydir, root, cfg, rp, names, g_extra, _record):
    t0 = time.time()
    csv_path = _resolve_signage_csv(pydir, root, cfg, rp, g_extra)
    out = _exec_py(
        os.path.join(pydir, 'm5_signage_from_csv.py'),
        [
            csv_path,
            names.get('alignment', 'ALIGN'),
            names.get('layers', {}).get('signage', 'C-SGN-FURN'),
            'ROAD_SIGN_CSV',
        ],
        g_extra,
    )
    return _record('m5', out, t0)


def _run_step_m6(pydir, root, names, paths, design, dpr_cfg, rp, pc, g_extra, _record):
    t0 = time.time()
    pdf_rel = paths.get('dpr_pdf_dir', 'out/pdf')
    out_dir = _resolve(root, pdf_rel) if pdf_rel else os.path.join(root, 'out', 'sheets')
    pave_key = _pavement_path_key(paths, pc)
    in_list = [
        names.get('alignment', 'ALIGN'),
        out_dir,
        json.dumps(dpr_cfg) if dpr_cfg else '',
        rp('alignment_meta'),
        rp('dpr_sheet_manifest'),
        rp('mass_haul_csv'),
        rp('mass_haul_meta'),
        rp(pave_key),
        str(design.get('start_station', 0.0)),
        str(design.get('volume_sample_interval_m', 20)),
    ]
    out = _exec_py(
        os.path.join(pydir, 'm6_sheets_helper.py'),
        in_list,
        g_extra,
    )
    return _record('m6', out, t0)


def _paved_area_m2(root, paths, design):
    width = float(design.get('paved_width_m', 7.0) or 7.0)
    length = float(design.get('alignment_length_m', 0) or 0)
    meta_rel = paths.get('alignment_meta')
    if meta_rel and not length:
        meta_full = _resolve(root, meta_rel)
        if os.path.isfile(meta_full):
            try:
                meta = json.load(codecs.open(meta_full, 'r', encoding='utf-8'))
                if meta.get('total_length_m') is not None:
                    length = float(meta['total_length_m'])
            except Exception:
                pass
    return width * length if length > 0 else 0.0


def _run_step_m7(pydir, rp, names, boq_cfg, root, paths, pc, g_extra, design, _record):
    t0 = time.time()
    volp = rp('volumes_csv')
    pave_key = _pavement_path_key(paths, pc)
    rate_rel = boq_cfg.get('rate_file', 'config/state_sor_rates.json')
    sor_path = _resolve(root, rate_rel)
    in_list = [
        volp,
        names.get('layers', {}).get('marking', 'C-ROAD-MARK-THERMO'),
        names.get('layers', {}).get('signage', 'C-SGN-FURN'),
        rp('payitems'),
        rp('boq_csv'),
        names.get('corridor', ''),
        boq_cfg.get('state_code', ''),
        sor_path,
    ]
    mq = rp('marking_quantities')
    if mq:
        in_list.append(mq)
    pave = rp(pave_key)
    if pave:
        in_list.append(pave)
    area = _paved_area_m2(root, paths, design)
    in_list.append('%.4f' % area if area > 0 else '')
    sc = rp('signage_counts') if paths.get('signage_counts') else ''
    in_list.append(sc or '')
    if boq_cfg.get('write_abstract_separate'):
        in_list.append(rp('boq_abstract_csv') if paths.get('boq_abstract_csv') else '')
    out = _exec_py(os.path.join(pydir, 'm7_boq_rollup.py'), in_list, g_extra)
    return _record('m7', out, t0)


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
    boq_cfg = cfg.get('boq', {})
    dpr_cfg = cfg.get('dpr', {})
    pipeline = cfg.get('pipeline') or {}
    fail_artifacts = pipeline.get('fail_on_missing_artifact', True)

    pc = _load_pipeline_contract(root)

    def rp(key):
        return _resolve(root, paths[key]) if paths.get(key) else ''

    if pc and 'enabled_steps' in pc:
        steps = pc['enabled_steps'](cfg, step_filter)
        if pc.get('ordered_steps'):
            steps = pc['ordered_steps'](steps, cfg)
    else:
        steps = [s.strip().lower() for s in (step_filter or 'm1,m2,m3,m4,m0,m5,m6,m7,m9,m10,m11,m12,m13,m14,m15').split(',') if s.strip()]

    log_lines = []
    artifact_lines = []
    qa_rel = paths.get('qa_log', 'out/qa/run_log.txt')
    qa_path = _resolve(root, qa_rel)
    t_run0 = time.time()
    manifest_steps = []
    artifacts_written = []
    merged_entries = []
    strict = bool(design.get('strict_log', False))

    g_extra = _load_py_helpers(pydir)
    g_extra['PROJECT_CFG'] = cfg
    g_extra['PROJECT_ROOT'] = root

    def _record(step, out, t0):
        norm = _norm_out(out, step, g_extra)
        log_lines.append('[%s] %s' % (step.upper(), _out_preview(norm)))
        manifest_steps.append({
            'step': step,
            'seconds': round(time.time() - t0, 3),
            'output_preview': _out_preview(norm),
            'counts': norm.get('counts') if isinstance(norm, dict) else None,
        })
        if isinstance(norm, dict):
            for e in norm.get('log', []):
                ent = dict(e)
                ent.setdefault('module', step.upper())
                merged_entries.append(ent)
        step_errors = 0
        if pc and 'verify_step_outputs' in pc:
            for sev, msg in pc['verify_step_outputs'](step, paths, root, _resolve):
                artifact_lines.append('[%s] %s' % (sev, msg))
                if sev == 'INFO' and msg.startswith('WROTE'):
                    artifacts_written.append({'step': step, 'message': msg})
                if sev == 'ERROR':
                    step_errors += 1
                    if 'log_add' in g_extra:
                        g_extra['log_add'](
                            g_extra.get('_m8_log') or {'entries': []},
                            'ERROR',
                            'ARTIFACT_MISSING',
                            msg,
                            module='M8',
                        )
                    merged_entries.append({
                        'severity': 'ERROR',
                        'code': 'ARTIFACT_MISSING',
                        'message': msg,
                        'module': 'M8',
                    })
            if fail_artifacts and step_errors:
                if isinstance(norm, dict):
                    counts = norm.setdefault('counts', {'INFO': 0, 'WARN': 0, 'ERROR': 0})
                    counts['ERROR'] = counts.get('ERROR', 0) + step_errors
        return norm

    runners = {
        'm1': lambda: _run_step_m1(pydir, rp, names, styles, design, paths, g_extra, _record),
        'm2': lambda: _run_step_m2(pydir, rp, names, styles, design, g_extra, _record),
        'm3': lambda: _run_step_m3(pydir, rp, names, design, paths, pc, g_extra, _record),
        'm4': lambda: _run_step_m4(pydir, rp, paths, names, design, g_extra, _record),
        'm0': lambda: _run_step_m0(pydir, rp, names, design, g_extra, _record),
        'm5': lambda: _run_step_m5(pydir, root, cfg, rp, names, g_extra, _record),
        'm6': lambda: _run_step_m6(pydir, root, names, paths, design, dpr_cfg, rp, pc, g_extra, _record),
        'm7': lambda: _run_step_m7(pydir, rp, names, boq_cfg, root, paths, pc, g_extra, design, _record),
        'm9':  lambda: (lambda _t, _o: _record('m9',  _o, _t))(time.time(), _exec_py(os.path.join(pydir, 'm9_road_markings.py'),      [project_json], g_extra)),
        'm10': lambda: (lambda _t, _o: _record('m10', _o, _t))(time.time(), _exec_py(os.path.join(pydir, 'm10_sections.py'),           [project_json], g_extra)),
        'm11': lambda: (lambda _t, _o: _record('m11', _o, _t))(time.time(), _exec_py(os.path.join(pydir, 'm11_superelevation.py'),     [project_json], g_extra)),
        'm12': lambda: (lambda _t, _o: _record('m12', _o, _t))(time.time(), _exec_py(os.path.join(pydir, 'm12_mass_haul.py'),          [project_json], g_extra)),
        'm13': lambda: (lambda _t, _o: _record('m13', _o, _t))(time.time(), _exec_py(os.path.join(pydir, 'm13_plan_sheets.py'),        [project_json], g_extra)),
        'm14': lambda: (lambda _t, _o: _record('m14', _o, _t))(time.time(), _exec_py(os.path.join(pydir, 'm14_longsection_sheets.py'), [project_json], g_extra)),
        'm15': lambda: (lambda _t, _o: _record('m15', _o, _t))(time.time(), _exec_py(os.path.join(pydir, 'm15_standard_details.py'),   [project_json], g_extra)),
    }

    for step in steps:
        runner = runners.get(step)
        if runner:
            runner()

    summary = '\n'.join(log_lines)
    if artifact_lines:
        summary = summary + '\n' + '\n'.join(artifact_lines)
    counts = {'INFO': 0, 'WARN': 0, 'ERROR': 0}
    for e in merged_entries:
        sev = str(e.get('severity', 'INFO')).upper()
        if sev in counts:
            counts[sev] += 1

    qa_dir = os.path.dirname(qa_path)
    if qa_dir and not os.path.isdir(qa_dir):
        os.makedirs(qa_dir)

    contract_ver = pc.get('CONTRACT_VERSION', 1) if pc else 1
    jline = {
        'ts': time.time(),
        'project_json': os.path.abspath(project_json),
        'steps': steps,
        'contract_version': contract_ver,
        'counts': counts,
        'entries': merged_entries,
    }
    try:
        with codecs.open(qa_path, 'a', encoding='utf-8') as fq:
            fq.write('\n---\n' + summary + '\n')
            fq.write(json.dumps(jline) + '\n')
    except Exception:
        pass

    try:
        manifest = {
            'project_json': os.path.abspath(project_json),
            'contract_version': contract_ver,
            'steps': steps,
            'total_seconds': round(time.time() - t_run0, 3),
            'step_details': manifest_steps,
            'artifacts_written': artifacts_written,
            'validation_counts': counts,
        }
        mf = os.path.join(qa_dir, 'last_run_manifest.json')
        with codecs.open(mf, 'w', encoding='utf-8') as fm:
            fm.write(json.dumps(manifest, indent=2))
            fm.write('\n')
        vf = os.path.join(qa_dir, 'last_validation.json')
        with codecs.open(vf, 'w', encoding='utf-8') as fv:
            fv.write(json.dumps({'counts': counts, 'entries': merged_entries}, indent=2))
            fv.write('\n')
    except Exception:
        pass

    if strict and counts.get('ERROR', 0) > 0:
        return 'ERROR: M8 blocked (strict_log) — %d ERROR(s).\n' % counts['ERROR'] + summary

    if fail_artifacts and counts.get('ERROR', 0) > 0:
        return 'ERROR: M8 blocked (fail_on_missing_artifact) — %d ERROR(s).\n' % counts['ERROR'] + summary

    if 'log_new' in g_extra:
        log = g_extra['log_new']('M8')
        g_extra['log_add'](log, 'INFO', 'M8_DONE', 'M8 finished.')
        return g_extra['out_wrap'](log, {'steps': steps, 'counts': counts}, legacy_msg='OK: M8 finished.\n' + summary)

    return 'OK: M8 finished.\n' + summary


project_json = IN[0]
step_filter = IN[1] if len(IN) > 1 else ''

OUT = run(project_json, step_filter)
