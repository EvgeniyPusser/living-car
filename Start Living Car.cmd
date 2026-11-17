@echo off
cd /d "%~dp0"
if exist ".venv312\Scripts\python.exe" (
  ".venv312\Scripts\python.exe" -m living_car gui
) else if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m living_car gui
) else (
  echo Python environment not found. See README.md for setup instructions.
  pause
  exit /b 1
)
if errorlevel 1 pause
