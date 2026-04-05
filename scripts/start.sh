#!/bin/bash
# Quick Start Script for Dari for Business (Linux/Mac)

echo "============================================================"
echo "  Dari for Business - Multi-Chain Payment Gateway"
echo "============================================================"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed"
    echo "Please install Python 3.10 or higher"
    exit 1
fi

echo "[1/6] Python found"
echo ""

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "[2/6] Creating virtual environment..."
    python3 -m venv venv
    echo "Virtual environment created successfully"
else
    echo "[2/6] Virtual environment already exists"
fi
echo ""

# Activate virtual environment
echo "[3/6] Activating virtual environment..."
source venv/bin/activate
echo ""

# Install dependencies
echo "[4/6] Installing dependencies..."
pip install -r requirements.txt
echo "Dependencies installed successfully"
echo ""

# Initialize database if it doesn't exist
if [ ! -f "payment_gateway.db" ]; then
    echo "[5/6] Initializing database..."
    python init_db.py
    echo "Database initialized successfully"
else
    echo "[5/6] Database already exists"
fi
echo ""

echo "[6/6] Starting application..."
echo ""
echo "============================================================"
echo "  API Server will start on: http://localhost:8000"
echo "  API Documentation: http://localhost:8000/docs"
echo "============================================================"
echo ""
echo "IMPORTANT: You need to start blockchain listeners separately!"
echo "Open separate terminals and run:"
echo "   source venv/bin/activate"
echo "   python -m app.services.stellar_listener"
echo ""
echo "   source venv/bin/activate"
echo "   python -m app.services.blockchains.evm_listener"
echo ""
echo "   source venv/bin/activate"
echo "   python -m app.services.blockchains.tron_listener"
echo ""
echo "============================================================"
echo ""

# Start the application
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
