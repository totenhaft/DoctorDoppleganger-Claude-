@echo off
cd /d "%~dp0"
echo ============================================================
echo  Doctor Doppelganger - video engine setup (voice + lip-sync)
echo  Downloads about 10-12GB. Takes 20-60 minutes. Run only once.
echo ============================================================
rem The AI engines need Python 3.10 - 3.13 (3.12 recommended).
rem Python 3.14 can stay installed; this picks 3.12 through the "py" launcher.
set "PY="
for %%V in (3.12 3.13 3.11 3.10) do (
  if not defined PY (
    py -%%V --version >nul 2>nul && set "PY=py -%%V"
  )
)
if not defined PY (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python was not found. Please check step 1 of README.
    pause
    exit /b 1
  )
  set "PY=python"
)
echo Using: %PY%
%PY% --version
%PY% engines\install.py %*
pause
