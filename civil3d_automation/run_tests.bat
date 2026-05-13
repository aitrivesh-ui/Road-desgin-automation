@echo off
setlocal
cd /d "%~dp0.."
echo Running unittest from: %CD%
python -m unittest discover -s tools -p "test_*.py" -v
set ERR=%ERRORLEVEL%
endlocal & exit /b %ERR%
