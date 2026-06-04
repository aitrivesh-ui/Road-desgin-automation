' export_csvs.vbs
' Road Design Automation — One-click export of all data sheets to CSV files.
'
' USAGE
'   Double-click this file in Windows Explorer, or run from a command prompt:
'     cscript tools\export_csvs.vbs
'
' WHAT IT DOES
'   Opens  csv\templates\RoadAutomation_DataStarter.xlsx  in Excel (hidden),
'   exports each data sheet as a UTF-8 CSV into  csv\,  then closes Excel.
'
' REQUIREMENTS
'   Microsoft Excel must be installed on this machine.
'   Run  tools\build_starter_workbook.py  first if the workbook is missing.

Option Explicit

Const xlCSV = 6   ' Excel constant for CSV format

Dim fso, scriptDir, wbPath, csvDir
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

wbPath = fso.GetAbsolutePathName(fso.BuildPath(scriptDir, "..\csv\templates\RoadAutomation_DataStarter.xlsx"))
csvDir = fso.GetAbsolutePathName(fso.BuildPath(scriptDir, "..\csv"))

' ── Pre-flight ───────────────────────────────────────────────────────────────
If Not fso.FileExists(wbPath) Then
    MsgBox "Workbook not found:" & vbCrLf & wbPath & vbCrLf & vbCrLf & _
           "Run build_starter_workbook.py first:" & vbCrLf & _
           "  python tools\build_starter_workbook.py", _
           vbCritical, "Export CSVs — Road Automation"
    WScript.Quit 1
End If

If Not fso.FolderExists(csvDir) Then
    fso.CreateFolder csvDir
End If

' ── Sheet → CSV mapping ───────────────────────────────────────────────────────
Dim sheetNames(4), csvFiles(4)
sheetNames(0) = "alignment_pi"     : csvFiles(0) = "alignment_pi.csv"
sheetNames(1) = "profile_pvis"     : csvFiles(1) = "profile_pvis.csv"
sheetNames(2) = "section_widths"   : csvFiles(2) = "section_widths.csv"
sheetNames(3) = "signage_schedule" : csvFiles(3) = "signage_schedule.csv"
sheetNames(4) = "payitems"         : csvFiles(4) = "payitems.csv"

' ── Open Excel silently ───────────────────────────────────────────────────────
Dim xl, wb
Set xl = CreateObject("Excel.Application")
xl.Visible        = False
xl.DisplayAlerts  = False
xl.ScreenUpdating = False

Set wb = xl.Workbooks.Open(wbPath)

' ── Export each sheet ─────────────────────────────────────────────────────────
Dim exported, skipped, log, i
exported = 0
skipped  = 0
log      = ""

For i = 0 To 4
    Dim ws, tempWb, csvPath
    csvPath = fso.BuildPath(csvDir, csvFiles(i))

    On Error Resume Next
    Set ws = wb.Sheets(sheetNames(i))

    If Err.Number <> 0 Then
        ' Sheet not found in workbook
        log     = log & vbCrLf & "  SKIP   " & sheetNames(i) & "  (sheet not found)"
        skipped = skipped + 1
        Err.Clear
    Else
        ' Copy sheet to a new temporary workbook and save as CSV
        ws.Copy
        Set tempWb = xl.ActiveWorkbook
        tempWb.SaveAs fso.GetAbsolutePathName(csvPath), xlCSV
        tempWb.Close False
        log      = log & vbCrLf & "  OK     " & csvFiles(i)
        exported = exported + 1
    End If
    On Error GoTo 0
Next

' ── Cleanup ───────────────────────────────────────────────────────────────────
wb.Close False
xl.Quit
Set wb  = Nothing
Set xl  = Nothing
Set fso = Nothing

' ── Summary dialog ───────────────────────────────────────────────────────────
MsgBox "Export complete." & vbCrLf & vbCrLf & _
       "Exported : " & exported & "   Skipped: " & skipped & vbCrLf & _
       "Output   : " & csvDir  & vbCrLf & _
       log, _
       vbInformation, "Export CSVs — Road Automation"
