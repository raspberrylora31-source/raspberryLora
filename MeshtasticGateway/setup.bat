@echo off
setlocal
cd /d "%~dp0"

echo Creating Python virtual environment...
python -m venv .venv
if errorlevel 1 (
  echo Failed to create .venv. Install Python 3.10+ and retry.
  exit /b 1
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo Dependency install failed.
  exit /b 1
)

if not exist .env (
  copy .env.example .env >nul
  echo Created .env from .env.example
)

python -c "from app.database import init_db; init_db(); print('SQLite database initialized')"
if errorlevel 1 (
  echo Database init failed.
  exit /b 1
)

echo.
echo Setup complete. Start the gateway with start_gateway.bat
echo Dashboard: http://127.0.0.1:8000
endlocal
