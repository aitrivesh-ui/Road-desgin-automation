# -*- coding: utf-8 -*-
"""
Structured validation log helpers (IronPython 2.7).
Paste into Dynamo scripts or load via exec from M8 (set __file__ on the host globals).
"""
import time

SEVERITIES = ('INFO', 'WARN', 'ERROR')
CIVIL_VERSION_NOTE = 'Record Civil 3D / Dynamo / IronPython versions in project QA notes after first successful run.'


def log_new(module_id=None):
    return {'module': module_id or '', 'entries': []}


def log_add(log, severity, code, message, **kwargs):
    if log is None:
        log = log_new()
    sev = str(severity).upper()
    if sev not in SEVERITIES:
        sev = 'INFO'
    entry = {
        'severity': sev,
        'code': str(code or ''),
        'message': str(message or ''),
        'ts': time.time(),
    }
    for k, v in kwargs.items():
        if v is not None:
            entry[k] = v
    log.setdefault('entries', []).append(entry)
    return log


def log_counts(log):
    counts = {'INFO': 0, 'WARN': 0, 'ERROR': 0}
    for e in (log or {}).get('entries', []):
        sev = str(e.get('severity', 'INFO')).upper()
        if sev in counts:
            counts[sev] += 1
    return counts


def log_has_errors(log):
    return log_counts(log).get('ERROR', 0) > 0


def log_merge(target, other):
    if target is None:
        target = log_new()
    if other:
        target.setdefault('entries', []).extend((other or {}).get('entries', []))
    return target


def out_wrap(log, data=None, legacy_msg=None):
    counts = log_counts(log)
    payload = {
        'log': (log or {}).get('entries', []),
        'counts': counts,
        'data': data if data is not None else {},
    }
    if legacy_msg:
        payload['legacy'] = str(legacy_msg)
    if log_has_errors(log):
        payload['status'] = 'ERROR'
    elif counts.get('WARN', 0) > 0:
        payload['status'] = 'WARN'
    else:
        payload['status'] = 'OK'
    return payload


def out_legacy_string(out_dict, default=''):
    if isinstance(out_dict, dict):
        leg = out_dict.get('legacy')
        if leg:
            return str(leg)
        st = out_dict.get('status', 'OK')
        data = out_dict.get('data') or {}
        if data:
            return '%s: %s' % (st, data)
        counts = out_dict.get('counts') or {}
        return '%s: log counts %s' % (st, counts)
    return str(out_dict) if out_dict is not None else default


def normalize_out(raw, module_id=None):
    if isinstance(raw, dict) and 'log' in raw:
        if 'counts' not in raw:
            raw['counts'] = log_counts({'entries': raw.get('log', [])})
        return raw
    if isinstance(raw, dict) and 'entries' in raw:
        return out_wrap(raw, raw.get('data'))
    msg = str(raw) if raw is not None else ''
    log = log_new(module_id)
    if msg.startswith('ERROR:'):
        log_add(log, 'ERROR', 'MODULE_FAIL', msg)
    elif msg.startswith('WARN:'):
        log_add(log, 'WARN', 'MODULE_WARN', msg)
    elif msg:
        log_add(log, 'INFO', 'MODULE_OK', msg)
    return out_wrap(log, legacy_msg=msg)


def safe_civil(log, api_name, call, fallback_msg, module_id=None, **ctx):
    try:
        return call(), None
    except Exception as ex:
        log_add(
            log,
            'ERROR',
            'CIVIL_API_FAIL',
            str(ex),
            api=str(api_name),
            fallback=str(fallback_msg),
            module=module_id or (log or {}).get('module'),
            civil_note=CIVIL_VERSION_NOTE,
            **ctx
        )
        return None, ex
