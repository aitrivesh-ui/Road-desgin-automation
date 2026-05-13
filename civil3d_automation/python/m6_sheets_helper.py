# -*- coding: utf-8 -*-
"""
M6 — Sheet production helper (stubs + safe guidance).

Dynamo inputs:
  IN[0] : str — alignment name for future view-frame creation
  IN[1] : str — optional output directory for publish (informational)

This module does not call undocumented publish APIs. It returns a checklist string.
When your Civil version's ViewFrameGroup API is confirmed, add creation code in _try_view_frames().
"""
import clr
import os

clr.AddReference('AcMgd')
clr.AddReference('AeccDbMgd')

from Autodesk.AutoCAD.ApplicationServices import Application
from Autodesk.Civil.ApplicationServices import CivilApplication
from Autodesk.Civil.DatabaseServices import Alignment


def _try_view_frames(align_name):
    civdoc = CivilApplication.ActiveDocument
    for aid in civdoc.GetAlignmentIds():
        if Alignment.GetAlignmentName(aid) == align_name:
            return True, 'Alignment found — wire ViewFrameGroup.Create from template DWT in a future revision.'
    return False, 'Alignment not found for view frames.'


def run(align_name, out_dir):
    ok, detail = _try_view_frames(align_name)
    lines = [
        'M6 sheet automation (manual + API extension point).',
        '1) Create / update view frames along alignment "%s" in Civil UI or extend this script.' % align_name,
        '2) Populate Sheet Set Manager custom fields from project.json (manual or DataShortcut).',
        '3) Publish: use -PUBLISH with a generated .dsd, or batch plot from SSM.',
        'Status: %s' % detail,
    ]
    if out_dir:
        lines.append('Target folder (create if missing): ' + str(out_dir))
        if not os.path.isdir(out_dir):
            try:
                os.makedirs(out_dir)
                lines.append('Created output directory.')
            except Exception as ex:
                lines.append('Could not create directory: ' + str(ex))
    msg = 'OK: ' + ' | '.join(lines)
    if not ok:
        msg = 'WARN: ' + ' | '.join(lines)
    return msg


align_name = IN[0]
out_dir = IN[1] if len(IN) > 1 else ''

OUT = run(align_name, out_dir)
