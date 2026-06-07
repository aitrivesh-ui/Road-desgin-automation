# -*- coding: utf-8 -*-
"""
M0 (legacy entry) — delegates to m0_markings_from_config.py.

Prefer m0_markings_from_config.py via M8. This wrapper accepts the older
IN[] layout for Dynamo graphs built before Plan 03:

  IN[0] alignment name
  IN[1] curve_table.csv path
  IN[2] marking layer (ignored — layers come from IRC35 catalogue + material)
  IN[3] XData app (optional)
  IN[4] marking_quantities CSV (optional)
  IN[5] markings_schedule.csv (optional; if missing, builds a single CL-D span)
"""
import os

_here = os.path.dirname(__file__) if '__file__' in dir() else os.path.join(os.getcwd(), 'python')
_g = {}
exec(compile(open(os.path.join(_here, 'm0_markings_from_config.py')).read(), 'm0_markings_from_config.py', 'exec'), _g)

align_name = IN[0]
curve_table_path = IN[1] if len(IN) > 1 else ''
xdata_app = IN[3] if len(IN) > 3 else 'IRC35_ROAD_MARK_V2'
qty_csv_path = IN[4] if len(IN) > 4 else ''

schedule_path = IN[5] if len(IN) > 5 else ''
if not schedule_path:
    _root = os.path.normpath(os.path.join(_here, '..'))
    schedule_path = os.path.join(_root, 'csv', 'markings_schedule.csv')
    if not os.path.isfile(schedule_path):
        schedule_path = os.path.join(_root, 'csv', 'templates', 'markings_schedule.csv')

OUT = _g['run'](align_name, schedule_path, curve_table_path, qty_csv_path, 80, xdata_app)
