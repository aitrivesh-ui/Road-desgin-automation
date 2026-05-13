@echo off
setlocal
cd /d "%~dp0"

if not exist "%~dp0civil3d_automation\install_tools.bat" (
  echo ERROR: civil3d_automation\install_tools.bat not found.
  echo Run this from the repository root ^(folder that contains civil3d_automation^).
  pause
  exit /b 1
)

call "%~dp0civil3d_automation\install_tools.bat" %*
set "ERR=%ERRORLEVEL%"
endlocal & exit /b %ERR%
