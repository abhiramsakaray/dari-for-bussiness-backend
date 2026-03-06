@echo off
REM Quick Start Script for Dari for Business (Windows)

echo ============================================================
echo   Dari for Business - Multi-Chain Payment Gateway
echo ============================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.10 or higher
    pause
    exit /b 1
)

echo [1/6] Python found
echo.

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo [2/6] Creating virtual environment...
    python -m venv venv
    echo Virtual environment created successfully
) else (
    echo [2/6] Virtual environment already exists
)
echo.

REM Activate virtual environment
echo [3/6] Activating virtual environment...
call venv\Scripts\activate.bat
echo.

REM Install dependencies
echo [4/6] Installing dependencies...
pip install -r requirements.txt
echo Dependencies installed successfully
echo.

REM Initialize database if it doesn't exist
if not exist "payment_gateway.db" (
    echo [5/6] Initializing database...
    python init_db.py
    echo Database initialized successfully
) else (
    echo [5/6] Database already exists
)
echo.

echo [6/6] Starting application...
echo.
echo ============================================================
echo   API Server will start on: http://localhost:8000
echo   API Documentation: http://localhost:8000/docs
echo ============================================================
echo.
echo IMPORTANT: You need to start blockchain listeners separately!
echo Open separate terminals and run:
echo    venv\Scripts\activate.bat
echo    python -m app.services.stellar_listener
echo.
echo    venv\Scripts\activate.bat
echo    python -m app.services.blockchains.evm_listener
echo.
echo    venv\Scripts\activate.bat
echo    python -m app.services.blockchains.tron_listener
echo.
echo ============================================================
echo.

REM Start the application
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
