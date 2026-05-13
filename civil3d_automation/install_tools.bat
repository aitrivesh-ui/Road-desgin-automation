@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if /i "%~1"=="--nopause" set "NOPAUSE=1"

echo.
echo === Road design automation: Python tools setup ===
echo This folder: %CD%
echo.

set "PYEXE="
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -c "import sys; assert sys.version_info[:2] >= (3, 8)" >nul 2>nul
  if not errorlevel 1 set "PYEXE=py -3"
)
if not defined PYEXE (
  where python >nul 2>nul
  if not errorlevel 1 (
    python -c "import sys; assert sys.version_info[:2] >= (3, 8)" >nul 2>nul
    if not errorlevel 1 set "PYEXE=python"
  )
)

if not defined PYEXE (
  echo ERROR: Python 3.8+ not found.
  echo Install from https://www.python.org/downloads/ and enable:
  echo   - "Add python.exe to PATH"
  echo   - Optional: "py launcher" ^(lets this script use: py -3^)
  echo.
  if not defined NOPAUSE pause
  exit /b 1
)

echo Using: %PYEXE%
echo.

if not exist "%~dp0requirements-tools.txt" (
  echo ERROR: requirements-tools.txt not found in %CD%
  if not defined NOPAUSE pause
  exit /b 1
)

%PYEXE% -m pip install -r "%~dp0requirements-tools.txt"
if errorlevel 1 (
  echo.
  echo ERROR: pip install failed. If your network blocks PyPI, install offline or use a mirror.
  if not defined NOPAUSE pause
  exit /b 1
)

if not exist "%~dp0config\project.json" (
  if exist "%~dp0config\project.example.json" (
    echo Creating config\project.json from project.example.json ...
    copy /Y "%~dp0config\project.example.json" "%~dp0config\project.json" >nul
    if errorlevel 1 (
      echo WARNING: Could not copy project.example.json to project.json. Copy manually if needed.
    )
  ) else (
    echo WARNING: config\project.example.json missing; skipped creating project.json.
  )
)

echo.
echo === Setup finished ===
echo Optional tools ^(openpyxl, etc.^) are installed for this Python.
echo Civil 3D / Dynamo / IronPython are separate; see the repo README.
echo.
echo Next steps:
echo   - Edit CSVs under csv\ and paths in config\project.json
echo   - Double-click tools\run_preflight.bat to validate before Dynamo
echo   - M8 in Dynamo Player: use this file as IN[0]:
echo       %~dp0config\project.json
echo.
if not defined NOPAUSE pause
endlocal
exit /b 0
