@echo off
rem Pre-annotation launcher. Uses the interpreter that actually has
rem torch / albumentations / opencv. The labelme_env venv under
rem chucao_prj\annotation_tools does NOT have them - do not use it here.
rem Kept ASCII-only on purpose: a .bat with Chinese text must be GBK-encoded
rem or cmd shows mojibake (that is what happened to the old launcher).
set PY=D:\ruanjian\anac\python.exe
if not exist "%PY%" (
  echo [ERROR] interpreter not found: %PY%
  echo         edit the PY= line above to point at a python that has torch+albumentations+opencv
  pause
  exit /b 1
)
cd /d "%~dp0.."
"%PY%" tools\pre_annotate.py %*
echo.
echo Done. If it failed above, read the printed interpreter line - it must match %PY%
pause
