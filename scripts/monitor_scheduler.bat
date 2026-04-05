@echo off
echo ================================================================================
echo MONITORING WEB3 SUBSCRIPTION SCHEDULER
echo ================================================================================
echo.
echo This will show scheduler activity in real-time.
echo Press Ctrl+C to stop monitoring.
echo.
echo ================================================================================
echo.

:loop
timeout /t 5 /nobreak >nul
cls
echo ================================================================================
echo SCHEDULER STATUS - %date% %time%
echo ================================================================================
echo.

curl -s http://localhost:8000/api/v1/web3-subscriptions/scheduler/status 2>nul
if %errorlevel% neq 0 (
    echo ❌ Application not running or scheduler endpoint not available
    echo.
    echo Please start the application first:
    echo   start_with_scheduler.bat
) else (
    echo.
    echo.
    echo Recent subscriptions:
    python scripts\diagnose_subscriptions.py --status past_due 2>nul | findstr /C:"Subscription ID" /C:"Status" /C:"Overdue"
)

echo.
echo ================================================================================
echo Refreshing in 5 seconds... (Press Ctrl+C to stop)
goto loop
