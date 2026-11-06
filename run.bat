@echo off
cd /d "%~dp0"
rem Prefer Python 3.12 if installed (other versions such as 3.14 can stay installed).
set "PY="
for %%V in (3.12 3.13 3.11 3.10) do (
  if not defined PY (
    py -%%V --version >nul 2>nul && set "PY=py -%%V"
  )
)
if not defined PY set "PY=python"
if not exist .venv (
  echo [First run] Installing required packages. This takes a few minutes...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo Python was not found. Please check step 1 of README.
    pause
    exit /b 1
  )
  call .venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  pip install -r requirements.txt
  if errorlevel 1 (
    echo Package install failed. Check your internet connection and run again.
    rmdir /s /q .venv
    pause
    exit /b 1
  )
) else (
  call .venv\Scripts\activate.bat
)
python run.py %*
pause
