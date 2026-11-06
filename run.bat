@echo off
cd /d "%~dp0"
if not exist .venv (
  echo [First run] Installing required packages. This takes a few minutes...
  python -m venv .venv
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
