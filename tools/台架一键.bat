@echo off
rem One-command bench launcher: X5 bridge + synthetic stream + pc/main.py.
rem ASCII-only on purpose: a .bat with Chinese text must be GBK-encoded or cmd
rem shows mojibake (same rule as the existing pre-annotation launcher). Every
rem Chinese line the user sees is printed by tools/bench_run.py itself.
rem
rem Double-click = default run. For an option, type the python form instead
rem (typing this file name with Chinese characters in cmd is a pain):
rem   python -B tools\bench_run.py --dry-run    print the three commands, launch nothing
rem   python -B tools\bench_run.py --no-fake    bridge + main only (cells that WANT no stream)
rem   python -B tools\bench_run.py --source D:\path\to\img.jpg
set PY=D:\ruanjian\anac\python.exe
if not exist "%PY%" (
  echo [ERROR] interpreter not found: %PY%
  echo         edit the PY= line above to point at the python that has torch+opencv
  pause
  exit /b 1
)
cd /d "%~dp0.."
"%PY%" -X utf8 tools\bench_run.py %*
echo.
echo If the launcher printed a results\... path above, that folder is the evidence
echo to send back. Close the X5 window with Ctrl-C first, then the stream window.
pause
