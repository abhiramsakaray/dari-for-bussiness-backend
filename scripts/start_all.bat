@echo off
echo ================================================================================
echo DARI FOR BUSINESS - COMPLETE STARTUP
echo ================================================================================
echo.
echo This will start:
echo   1. FastAPI Server (http://0.0.0.0:8000)
echo   2. Web3 Subscription Scheduler (runs every 60 seconds)
echo   3. Blockchain Listeners (monitoring all chains)
echo.
echo Starting in 3 separate windows...
echo.
timeout /t 2

REM Change to project root
cd /d "%~dp0\.."

REM Start API with Scheduler in new window
echo Starting API with Scheduler...
start "Dari API with Scheduler" cmd /k "set PYTHONPATH=. && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

REM Wait a moment for API to start
timeout /t 3

REM Start Blockchain Listeners in new window
echo Starting Blockchain Listeners...
start "Blockchain Listeners" cmd /k "set PYTHONPATH=. && python scripts/run_listeners.py"

echo.
echo ================================================================================
echo ✅ DARI FOR BUSINESS IS STARTING
echo ================================================================================
echo.
echo 📍 API:       http://localhost:8000
echo 📊 Docs:      http://localhost:8000/docs
echo 🔗 Scheduler: Running (checks subscriptions every 60s)
echo 👂 Listeners: Monitoring blockchain for payments
echo.
echo Press Ctrl+C in any window to stop that service.
echo.
echo ================================================================================
pause
