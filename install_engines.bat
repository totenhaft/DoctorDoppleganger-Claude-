@echo off
cd /d "%~dp0"
echo ============================================================
echo  Doctor Doppelganger - video engine setup (voice + lip-sync)
echo  Downloads about 10GB. Takes 20-60 minutes. Run only once.
echo ============================================================
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Please check step 1 of README.
  pause
  exit /b 1
)
python engines\install.py %*
pause
