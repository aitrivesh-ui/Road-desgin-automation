@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3 is not on PATH. Install Python 3 or add it to PATH, then run:
  echo   python "%~dp0road_automation_preflight.py"
  pause
  exit /b 1
)
python "%~dp0road_automation_preflight.py" %*
endlocal
