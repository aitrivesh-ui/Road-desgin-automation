# -*- coding: utf-8 -*-
"""Build RoadAutomation_DataStarter.xlsx from csv/templates headers (requires openpyxl).

Enhancements over the bare version:
- Column notes/tooltips on every header cell.
- Example data row (row 2) to guide first-time users.
- Data validation: signage_schedule.side restricted to L / R.
- Styled README sheet with Method A/B/C export instructions.
- Consistent column widths and frozen header row.
"""
from __future__ import annotations

import csv
import os
import sys

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.comments import Comment
except ImportError:
    print("Install openpyxl: pip install -r civil3d_automation/requirements-tools.txt", file=sys.stderr)
    sys.exit(1)

ROOT  = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
TEMPL = os.path.join(ROOT, "csv", "templates")
OUT   = os.path.join(TEMPL, "RoadAutomation_DataStarter.xlsx")

# ── Styles ──────────────────────────────────────────────────────────────────
_HDR_FILL  = PatternFill("solid", fgColor="1c2030")
_HDR_FONT  = Font(name="Calibri", size=11, bold=True, color="F0A500")
_HDR_ALIGN = Alignment(horizontal="left", vertical="center")
_EX_FILL   = PatternFill("solid", fgColor="f0f4e8")   # light green = "example"
_EX_FONT   = Font(name="Calibri", size=10, italic=True, color="555555")
_BODY_FONT = Font(name="Calibri", size=10)
_THIN      = Side(style="thin", color="cccccc")
_CELL_BDR  = Border(bottom=_THIN)

# ── Column metadata: (header, tooltip_note, example_value) ──────────────────
# Each tuple describes one column: what it means and a realistic example.
SHEET_COLS: dict[str, list[tuple[str, str, object]]] = {
    "alignment_pi": [
        ("pi_id",            "Sequential PI identifier (integer or short label).",                    1),
        ("easting",          "X coordinate in project CRS (metres).",                                 1000.000),
        ("northing",         "Y coordinate in project CRS (metres).",                                 5000.000),
        ("radius_m",         "Horizontal curve radius (m). Use 0 for a tangent PI.",                  300.0),
        ("spiral_in_m",      "Entry spiral (clothoid) length (m). Use 0 for no spiral.",              0.0),
        ("spiral_out_m",     "Exit spiral length (m). Use 0 for no spiral.",                          0.0),
        ("design_speed_kph", "Design speed at this PI (km/h). Used for QA checks only.",              80),
    ],
    "profile_pvis": [
        ("station_m",        "Chainage along alignment (m). Must increase strictly row by row.",       0.000),
        ("elevation_m",      "Finished-grade elevation at this PVI (m AHD or project datum).",        12.500),
        ("k_crest",          "K-value for crest curve (m/%). Enter 0 for a tangent grade change.",    40.0),
        ("k_sag",            "K-value for sag curve (m/%). Enter 0 for a tangent grade change.",      0.0),
        ("curve_length_m",   "Vertical curve length (m). Leave 0 to let Civil derive from K × Dg.",   0.0),
    ],
    "section_widths": [
        ("region_id",        "Unique region identifier. Must not overlap another region's stations.",  1),
        ("start_sta",        "Start chainage of this corridor region (m).",                           0.0),
        ("end_sta",          "End chainage of this corridor region (m). Must be > start_sta.",        500.0),
        ("lane_width_m",     "Single-lane travel-lane width (m). Applied each side of centreline.",   3.5),
        ("shoulder_l_m",     "Left shoulder width (m).",                                              1.5),
        ("shoulder_r_m",     "Right shoulder width (m).",                                             1.5),
        ("target_l",         "Left assembly target: surface name or offset-target name.",             "EG"),
        ("target_r",         "Right assembly target: surface name or offset-target name.",            "EG"),
    ],
    "signage_schedule": [
        ("row",              "Sequential row number (integer). Used as a unique sign ID.",             1),
        ("station_m",        "Chainage along alignment where the sign is placed (m).",                 120.0),
        ("offset_m",         "Lateral offset from centreline (m). Positive = away from centreline.",  4.5),
        ("side",             "Side of road: L (left) or R (right). Dropdown enforced in Excel.",      "R"),
        ("sign_code",        "Sign code from the national sign schedule (e.g. W1-1).",                "W1-1"),
        ("block_name",       "AutoCAD block definition name as it exists in the template DWG.",       "SIGN_W1_1"),
        ("rotation_deg",     "Block rotation in degrees (0=East, CCW positive).",                     90.0),
    ],
    "payitems": [
        ("source",           "Module producing this item: 'volumes', 'markings', or 'signage'.",      "volumes"),
        ("key",              "Output key as written by M4/M7, e.g. 'cut_m3' or 'fill_m3'.",           "cut_m3"),
        ("pay_item",         "Contract pay-item code from the BoQ schedule.",                          "E2.1.1"),
        ("description",      "Full pay-item description as per the contract BoQ.",                     "Roadway excavation"),
        ("unit",             "Unit of measure: m3, m2, m, No., t, etc.",                              "m3"),
    ],
}

SHEETS = [
    ("README",           None),
    ("alignment_pi",     "alignment_pi.csv"),
    ("profile_pvis",     "profile_pvis.csv"),
    ("section_widths",   "section_widths.csv"),
    ("signage_schedule", "signage_schedule.csv"),
    ("payitems",         "payitems.csv"),
]


# ── README sheet content ────────────────────────────────────────────────────

def _readme_lines() -> list[tuple[str, bool]]:
    """Return (text, is_heading) pairs for the README sheet."""
    return [
        ("Road automation — Excel data starter",                                                True),
        ("",                                                                                    False),
        ("HOW TO USE",                                                                          True),
        ("1.  Fill data rows on each coloured sheet (alignment_pi, profile_pvis, etc.).",       False),
        ("    Row 1 is the locked header — do not rename or reorder columns.",                  False),
        ("    Row 2 shows greyed example values — replace or delete before exporting.",         False),
        ("",                                                                                    False),
        ("2.  Export sheets to CSV using ONE of these methods:",                                False),
        ("",                                                                                    False),
        ("    Method A — Python (recommended, cross-platform):",                               False),
        ("      python tools/export_workbook_to_csv.py  \\",                                   False),
        ("             csv/templates/RoadAutomation_DataStarter.xlsx  csv/",                   False),
        ("",                                                                                    False),
        ("    Method B — Windows one-click script:",                                            False),
        ("      Double-click  tools/export_csvs.vbs",                                          False),
        ("      (Opens Excel silently, exports all sheets, shows a summary.)",                  False),
        ("",                                                                                    False),
        ("    Method C — Manual Excel 'Save As':",                                              False),
        ("      File → Save As → CSV UTF-8 (Comma delimited) → save into csv/ folder.",        False),
        ("      Repeat for each sheet using the matching file name.",                           False),
        ("",                                                                                    False),
        ("3.  Confirm paths in config/project.json match the saved CSV file names.",            False),
        ("4.  Run preflight: python tools/road_automation_preflight.py",                        False),
        ("",                                                                                    False),
        ("SHEET → CSV MAP",                                                                     True),
        ("  alignment_pi      →  csv/alignment_pi.csv       →  Dynamo M1",                     False),
        ("  profile_pvis      →  csv/profile_pvis.csv       →  Dynamo M2",                     False),
        ("  section_widths    →  csv/section_widths.csv     →  Dynamo M3",                     False),
        ("  signage_schedule  →  csv/signage_schedule.csv   →  Dynamo M5",                     False),
        ("  payitems          →  csv/payitems.csv            →  Dynamo M7",                     False),
        ("",                                                                                    False),
        ("REGENERATE THIS WORKBOOK",                                                            True),
        ("  python tools/build_starter_workbook.py",                                           False),
        ("  (Run after changing column names in csv/templates/*.csv)",                          False),
    ]


# ── Helpers ─────────────────────────────────────────────────────────────────

def _add_comment(ws, col: int, text: str) -> None:
    cell = ws.cell(row=1, column=col)
    cmt = Comment(text, "Road Automation")
    cmt.width  = 260
    cmt.height = 90
    cell.comment = cmt


def _build_data_sheet(wb: Workbook, sheet_name: str) -> None:
    cols = SHEET_COLS[sheet_name]
    ws   = wb.create_sheet(title=sheet_name[:31])

    headers  = [c[0] for c in cols]
    notes    = [c[1] for c in cols]
    examples = [c[2] for c in cols]

    # Row 1: styled headers
    ws.append(headers)
    for c_idx in range(1, len(cols) + 1):
        cell = ws.cell(row=1, column=c_idx)
        cell.fill      = _HDR_FILL
        cell.font      = _HDR_FONT
        cell.alignment = _HDR_ALIGN
        _add_comment(ws, c_idx, notes[c_idx - 1])
    ws.row_dimensions[1].height = 20

    # Row 2: example values (greyed, italic)
    ws.append(examples)
    for c_idx in range(1, len(cols) + 1):
        cell = ws.cell(row=2, column=c_idx)
        cell.fill   = _EX_FILL
        cell.font   = _EX_FONT
        cell.border = _CELL_BDR

    # Freeze header row; sensible column widths
    ws.freeze_panes = "A2"
    for c_idx, (h, _, ex) in enumerate(cols, start=1):
        width = max(len(str(h)), len(str(ex))) + 4
        ws.column_dimensions[get_column_letter(c_idx)].width = min(width, 32)

    # Data validation: signage_schedule.side → L or R dropdown
    if sheet_name == "signage_schedule":
        side_col_idx = next(
            (i + 1 for i, (h, *_) in enumerate(cols) if h == "side"), None
        )
        if side_col_idx:
            dv = DataValidation(
                type="list",
                formula1='"L,R"',
                allow_blank=True,
                showErrorMessage=True,
                errorTitle="Invalid value",
                error='Enter "L" for left or "R" for right.',
            )
            ws.add_data_validation(dv)
            col_letter = get_column_letter(side_col_idx)
            dv.add(f"{col_letter}3:{col_letter}1048576")


def _build_readme_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet(title="README")
    title_font   = Font(name="Calibri", size=13, bold=True, color="1c2030")
    heading_font = Font(name="Calibri", size=10, bold=True)
    body_font    = Font(name="Calibri", size=10)

    for row_idx, (text, is_heading) in enumerate(_readme_lines(), start=1):
        cell = ws.cell(row=row_idx, column=1, value=text)
        if row_idx == 1:
            cell.font = title_font
        elif is_heading:
            cell.font = heading_font
        else:
            cell.font = body_font

    ws.column_dimensions["A"].width = 76


# ── Entry point ─────────────────────────────────────────────────────────────

def main() -> None:
    wb = Workbook()
    wb.remove(wb.active)  # remove default blank sheet

    for sheet_name, csv_name in SHEETS:
        if sheet_name == "README":
            _build_readme_sheet(wb)
        else:
            _build_data_sheet(wb, sheet_name)

    wb.save(OUT)
    print("Wrote", OUT)
    print("  Sheets     :", ", ".join(s for s, _ in SHEETS))
    print("  Example row: row 2 on each data sheet (greyed, replace with real data).")
    print("  Validation  : signage_schedule.side column has L/R dropdown.")
    print("  Export hint : double-click tools/export_csvs.vbs  OR")
    print("                python tools/export_workbook_to_csv.py <workbook> csv/")


if __name__ == "__main__":
    main()
