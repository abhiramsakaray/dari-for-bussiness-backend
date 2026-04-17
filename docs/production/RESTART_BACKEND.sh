#!/bin/bash

# ============================================================
# Restart Dari Backend After Database Migration
# ============================================================

echo "============================================================"
echo "🔄 Restarting Dari for Business Backend"
echo "============================================================"
echo ""

# Check if running as systemd service
if systemctl list-units --type=service | grep -q "dari-api"; then
    echo "📍 Found systemd service: dari-api"
    echo ""
    
    echo "🛑 Stopping service..."
    sudo systemctl stop dari-api
    
    echo "🔄 Restarting service..."
    sudo systemctl start dari-api
    
    echo "⏳ Waiting 3 seconds..."
    sleep 3
    
    echo "✅ Checking status..."
    sudo systemctl status dari-api --no-pager
    
    echo ""
    echo "📋 View logs:"
    echo "   sudo journalctl -u dari-api -f"
    
elif systemctl list-units --type=service | grep -q "dari"; then
    echo "📍 Found systemd service with 'dari' in name"
    echo ""
    echo "Available services:"
    systemctl list-units --type=service | grep dari
    echo ""
    echo "Please restart manually:"
    echo "   sudo systemctl restart <service-name>"
    
else
    echo "⚠️  No systemd service found"
    echo ""
    echo "Checking for running processes..."
    
    if pgrep -f "uvicorn.*dari" > /dev/null; then
        echo "📍 Found uvicorn process"
        echo ""
        echo "Killing existing process..."
        pkill -f "uvicorn.*dari"
        sleep 2
    fi
    
    echo "🚀 Starting backend manually..."
    cd ~/dari-for-bussiness-backend
    
    # Check if virtual environment exists
    if [ -d "venv" ]; then
        source venv/bin/activate
    fi
    
    # Start in background
    nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > dari.log 2>&1 &
    
    echo "✅ Backend started in background"
    echo "📋 View logs: tail -f ~/dari-for-bussiness-backend/dari.log"
fi

echo ""
echo "============================================================"
echo "🧪 Testing API"
echo "============================================================"
sleep 2

# Test API
if curl -s http://localhost:8000/docs > /dev/null; then
    echo "✅ API is responding!"
    echo "📖 API Docs: http://localhost:8000/docs"
else
    echo "⚠️  API not responding yet, give it a few more seconds"
    echo "   Check logs for errors"
fi

echo ""
echo "============================================================"
echo "✅ Done!"
echo "============================================================"
