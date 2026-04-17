# Manual Backend Restart Guide

Since there's no systemd service, follow these steps:

---

## Step 1: Find Running Process

```bash
# Check if backend is running
ps aux | grep uvicorn

# Or
pgrep -f uvicorn
```

---

## Step 2: Stop Existing Process

```bash
# Kill all uvicorn processes
pkill -f uvicorn

# Or kill specific PID
kill <PID>

# Verify it's stopped
ps aux | grep uvicorn
```

---

## Step 3: Navigate to Backend Directory

```bash
# Try these locations
cd ~/dari-for-bussiness-backend

# Or
cd /opt/dari-backend

# Or
cd /var/www/dari-backend

# Check you're in the right place
ls -la app/
```

---

## Step 4: Activate Virtual Environment (if exists)

```bash
# Check for venv
ls -la | grep venv

# Activate it
source venv/bin/activate

# Or
source .venv/bin/activate

# You should see (venv) in your prompt
```

---

## Step 5: Start Backend

### Option A: Foreground (see logs directly)
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Press `Ctrl+C` to stop

### Option B: Background (runs in background)
```bash
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > dari.log 2>&1 &

# View logs
tail -f dari.log
```

### Option C: Using screen (recommended)
```bash
# Install screen if not available
sudo apt-get install screen

# Start screen session
screen -S dari-backend

# Start backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Detach: Press Ctrl+A then D

# Reattach later
screen -r dari-backend

# Kill screen session
screen -X -S dari-backend quit
```

---

## Step 6: Verify It's Running

```bash
# Check process
ps aux | grep uvicorn

# Test API
curl http://localhost:8000/docs

# Check port
netstat -tlnp | grep 8000
```

---

## Quick Commands

```bash
# One-liner to restart
pkill -f uvicorn && cd ~/dari-for-bussiness-backend && source venv/bin/activate && nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > dari.log 2>&1 &

# View logs
tail -f ~/dari-for-bussiness-backend/dari.log

# Stop
pkill -f uvicorn
```

---

## Troubleshooting

### Port 8000 already in use
```bash
# Find what's using port 8000
sudo lsof -i :8000

# Kill it
sudo kill -9 <PID>
```

### Permission denied
```bash
# Make sure you own the directory
ls -la ~/dari-for-bussiness-backend

# Fix permissions if needed
sudo chown -R $USER:$USER ~/dari-for-bussiness-backend
```

### Module not found errors
```bash
# Reinstall dependencies
cd ~/dari-for-bussiness-backend
source venv/bin/activate
pip install -r requirements.txt
```

---

## Create Systemd Service (Optional)

If you want to create a proper systemd service:

```bash
# Create service file
sudo nano /etc/systemd/system/dari-api.service
```

Paste this:
```ini
[Unit]
Description=Dari Payment Gateway API
After=network.target postgresql.service

[Service]
Type=simple
User=dariwallet
WorkingDirectory=/home/dariwallet/dari-for-bussiness-backend
Environment="PATH=/home/dariwallet/dari-for-bussiness-backend/venv/bin"
ExecStart=/home/dariwallet/dari-for-bussiness-backend/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:
```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable dari-api

# Start service
sudo systemctl start dari-api

# Check status
sudo systemctl status dari-api

# View logs
sudo journalctl -u dari-api -f
```

---

## Next Steps

After restarting:
1. Check logs for errors
2. Test API at http://localhost:8000/docs
3. Deploy contracts (DEPLOY_NOW.md)
4. Go live! 🚀
