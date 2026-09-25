@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\activate.bat (
  echo Run setup.bat first.
  exit /b 1
)
call .venv\Scripts\activate.bat
echo Starting Meshtastic PC Gateway on http://127.0.0.1:8000
uvicorn app.main:app --host 127.0.0.1 --port 8000
endlocal
