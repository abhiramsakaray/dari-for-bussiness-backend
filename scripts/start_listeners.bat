@echo off
echo ================================================================================
echo STARTING BLOCKCHAIN LISTENERS (Polygon Focus)
echo ================================================================================
echo.
echo Configuration:
echo   - Listening to Polygon Amoy testnet
echo   - Also monitoring: Ethereum, Base, BSC, Arbitrum, Tron, Stellar
echo   - Detecting payment confirmations in real-time
echo.
echo This window monitors blockchain payments. Keep it running alongside the API.
echo.
echo Press Ctrl+C to stop the listeners.
echo.
echo ================================================================================
echo.

REM Set Python path to current directory
set PYTHONPATH=.

REM Change to project root
cd /d "%~dp0\.."

REM Start blockchain listeners (all chains)
REM To listen to specific chains only, use: python scripts/run_listeners.py polygon tron bsc
python scripts/run_listeners.py
