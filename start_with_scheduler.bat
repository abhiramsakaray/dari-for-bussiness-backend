@echo off
echo ================================================================================
echo STARTING DARI FOR BUSINESS WITH WEB3 SUBSCRIPTION SCHEDULER
echo ================================================================================
echo.
echo Configuration:
echo   - WEB3_SUBSCRIPTIONS_ENABLED=true (in .env)
echo   - Scheduler interval: 60 seconds
echo   - Batch size: 100 subscriptions
echo.
echo The scheduler will start automatically and run every 60 seconds.
echo.
echo Watch for this log message:
echo   "Web3 subscription scheduler started"
echo.
echo Press Ctrl+C to stop the application.
echo.
echo ================================================================================
echo.

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
