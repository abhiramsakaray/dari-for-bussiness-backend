#!/bin/bash

echo "============================================================"
echo "🔍 Finding and Restarting Dari Backend"
echo "============================================================"
echo ""

# 1. Check for running processes
echo "1️⃣ Checking for running processes..."
if pgrep -f "uvicorn.*app.main" > /dev/null; then
    echo "✅ Found running uvicorn process:"
    ps aux | grep -E "uvicorn.*app.main" | grep -v grep
    echo ""
    echo "🛑 Killing existing process..."
    pkill -f "uvicorn.*app.main"
    sleep 2
    echo "✅ Process killed"
else
    echo "ℹ️  No running uvicorn process found"
fi

echo ""

# 2. Check for systemd services
echo "2️⃣ Checking for systemd services..."
if systemctl list-units --type=service --all | grep -i dari > /dev/null; then
    echo "✅ Found systemd services:"
    systemctl list-units --type=service --all | grep -i dari
else
    echo "ℹ️  No systemd services found"
fi

echo ""

# 3. Find backend directory
echo "3️⃣ Finding backend directory..."
if [ -d "$HOME/dari-for-bussiness-backend" ]; then
    BACKEND_DIR="$HOME/dari-for-bussiness-backend"
    echo "✅ Found: $BACKEND_DIR"
elif [ -d "/opt/dari-backend" ]; then
    BACKEND_DIR="/opt/dari-backend"
    echo "✅ Found: $BACKEND_DIR"
elif [ -d "/var/www/dari-backend" ]; then
    BACKEND_DIR="/var/www/dari-backend"
    echo "✅ Found: $BACKEND_DIR"
else
    echo "⚠️  Backend directory not found in common locations"
    echo "   Please specify the path manually"
    exit 1
fi

echo ""

# 4. Start backend
echo "4️⃣ Starting backend..."
cd "$BACKEND_DIR"

# Check for virtual environment
if [ -d "venv" ]; then
    echo "✅ Activating virtual environment..."
    source venv/bin/activate
elif [ -d ".venv" ]; then
    echo "✅ Activating virtual environment..."
    source .venv/bin/activate
else
    echo "⚠️  No virtual environment found, using system Python"
fi

# Start uvicorn in background
echo "🚀 Starting uvicorn..."
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > dari.log 2>&1 &

PID=$!
echo "✅ Backend started with PID: $PID"
echo "📋 Log file: $BACKEND_DIR/dari.log"

echo ""
echo "⏳ Waiting 5 seconds for startup..."
sleep 5

echo ""

# 5. Test API
echo "5️⃣ Testing API..."
if curl -s http://localhost:8000/docs > /dev/null 2>&1; then
    echo "✅ API is responding!"
    echo "📖 API Docs: http://localhost:8000/docs"
else
    echo "⚠️  API not responding yet"
    echo "📋 Check logs: tail -f $BACKEND_DIR/dari.log"
fi

echo ""
echo "============================================================"
echo "✅ Done!"
echo "============================================================"
echo ""
echo "Useful commands:"
echo "  View logs:    tail -f $BACKEND_DIR/dari.log"
echo "  Stop backend: pkill -f 'uvicorn.*app.main'"
echo "  Check status: ps aux | grep uvicorn"
echo ""
