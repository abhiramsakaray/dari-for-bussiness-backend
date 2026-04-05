# Refund Scheduler

Automatically processes pending refunds at regular intervals to ensure they are sent to the blockchain without manual intervention.

## Overview

The Refund Scheduler is a background task system that:
- ✅ Automatically processes all **PENDING** refunds at regular intervals
- ✅ Supports 5 blockchains: Polygon, Stellar, Solana, Soroban, and TRON
- ✅ Tracks refund status: PENDING → PROCESSING → COMPLETED/FAILED
- ✅ Provides admin endpoints to control and monitor the scheduler
- ✅ Logs all operations for audit trails

## Configuration

### Environment Variables

Add to `.env` file to control scheduler behavior:

```bash
# Enable/disable the refund scheduler (default: True)
REFUND_SCHEDULER_ENABLED=true

# Interval in minutes between refund processing runs (default: 60)
REFUND_SCHEDULER_INTERVAL_MINUTES=60
```

### Configuration via Settings

In `app/core/config.py`:

```python
REFUND_SCHEDULER_ENABLED: bool = True
REFUND_SCHEDULER_INTERVAL_MINUTES: int = 60  # Process every 60 minutes
```

## How It Works

### Startup Flow

1. **Application starts** (uvicorn, FastAPI)
2. **startup_event()** runs in `app/main.py`
3. **Scheduler initialized** if `REFUND_SCHEDULER_ENABLED=true`
4. **Background job registered** to run every `REFUND_SCHEDULER_INTERVAL_MINUTES`
5. **Logs confirm** scheduler is active

### Processing Flow

1. **Scheduler triggers** at configured interval
2. **Query database** for all Refund records with status=PENDING
3. **For each pending refund:**
   - Get refund details (amount, recipient wallet, blockchain)
   - Call appropriate blockchain handler (Polygon, Stellar, Solana, etc.)
   - Update status: PENDING → PROCESSING → COMPLETED/FAILED
   - Store transaction hash from blockchain
4. **Return statistics** (total processed, failed, errors)

### Example Flow

```
PENDING Refund (1 USDC, Polygon, wallet: 0x123...)
    ↓
Scheduler triggers (hourly)
    ↓
process_all_pending_refunds()
    ↓
Polygon blockchain handler
    ↓
Transaction sent: 0xabc...
    ↓
Refund status updated: COMPLETED
    ↓
Logs: "✅ [SCHEDULER] Pending refund processor completed: 1 processed"
```

## Admin Endpoints

All endpoints require **Admin authentication** (Bearer token).

### Check Scheduler Status

```bash
GET /admin/scheduler/status
```

**Response:**
```json
{
  "status": "running",
  "jobs": [
    {
      "id": "process_pending_refunds",
      "name": "Process Pending Refunds",
      "next_run": "2026-04-05T15:30:00.123456",
      "trigger": "interval[0:01:00]"
    }
  ],
  "total_jobs": 1
}
```

### Manually Trigger Refund Processing

```bash
POST /admin/scheduler/refunds/trigger
```

**Response:**
```json
{
  "message": "Refund processing completed",
  "status": "success",
  "statistics": {
    "total_pending_found": 1,
    "successfully_processed": 1,
    "failed": 0,
    "errors": []
  }
}
```

### Start the Scheduler

```bash
POST /admin/scheduler/refunds/start?interval_minutes=60
```

**Response:**
```json
{
  "message": "Refund scheduler started (interval: 60 minutes)",
  "status": "started",
  "interval_minutes": 60
}
```

### Stop the Scheduler

```bash
POST /admin/scheduler/refunds/stop
```

**Response:**
```json
{
  "message": "Refund scheduler stopped",
  "status": "stopped"
}
```

## API Examples

### Using cURL

**Trigger manual processing:**
```bash
curl -X POST http://127.0.0.1:8000/admin/scheduler/refunds/trigger \
  -H "Authorization: Bearer YOUR_ADMIN_JWT_TOKEN" \
  -H "Content-Type: application/json"
```

**Check status:**
```bash
curl -X GET http://127.0.0.1:8000/admin/scheduler/status \
  -H "Authorization: Bearer YOUR_ADMIN_JWT_TOKEN"
```

**Start scheduler:**
```bash
curl -X POST "http://127.0.0.1:8000/admin/scheduler/refunds/start?interval_minutes=30" \
  -H "Authorization: Bearer YOUR_ADMIN_JWT_TOKEN"
```

### Using Python

```python
import requests

# Get admin token first (or use existing token)
admin_token = "your_admin_jwt_token"

headers = {
    "Authorization": f"Bearer {admin_token}",
    "Content-Type": "application/json"
}

# Trigger manual processing
response = requests.post(
    "http://127.0.0.1:8000/admin/scheduler/refunds/trigger",
    headers=headers
)
print(response.json())
```

### Using Postman

1. **Create new request**: POST
2. **URL**: `http://127.0.0.1:8000/admin/scheduler/refunds/trigger`
3. **Headers**:
   - Key: `Authorization`
   - Value: `Bearer YOUR_ADMIN_JWT_TOKEN`
4. **Send**

## Monitoring

### Log Output

When scheduler processes refunds, you'll see logs like:

```
🔄 [SCHEDULER] Starting pending refund processor at 2026-04-05T14:30:00.123456
✅ [SCHEDULER] Pending refund processor completed: 5 processed, 0 failed, 5 total found
```

### Status Transitions

Track refunds through the system:

```
Refund Database View:
| ID            | Amount | Status     | Chain   | Updated At           |
|---------------|--------|------------|---------|----------------------|
| ref_xyz123    | 1.0    | PENDING    | polygon | 2026-04-05 10:00:00  |
| ref_abc456    | 50.0   | PROCESSING | stellar | 2026-04-05 14:31:00  |
| ref_def789    | 25.0   | COMPLETED  | polygon | 2026-04-05 14:31:30  |
```

### Database Query Pending Refunds

```sql
SELECT id, amount, status, blockchain, created_at, updated_at
FROM refunds
WHERE status = 'PENDING'
ORDER BY created_at ASC;
```

## Deployment Scenarios

### Development (Local)

```bash
# Start with default settings (scheduler enabled, 60-min interval)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Logs show:
```
✅ Refund scheduler started (processes every 60 minutes)
```

### Testing (Faster Processing)

Set 1-minute interval to test quickly:

```bash
export REFUND_SCHEDULER_INTERVAL_MINUTES=1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Production (Manual Control)

Start with scheduler disabled, trigger via admin endpoint:

```bash
export REFUND_SCHEDULER_ENABLED=false
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then trigger processing on-demand via admin API.

### Production (Automated, Every 30 Minutes)

```bash
export REFUND_SCHEDULER_INTERVAL_MINUTES=30
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Troubleshooting

### Scheduler Not Running

**Problem**: Logs show `ℹ️  Refund scheduler disabled`

**Solution**:
```bash
export REFUND_SCHEDULER_ENABLED=true
# Restart application
```

### No Refunds Being Processed

**Problem**: Scheduler runs but no refunds processed

**Check**:
1. Are there PENDING refunds in database?
   ```sql
   SELECT COUNT(*) FROM refunds WHERE status = 'PENDING';
   ```
2. Check logs for errors (look for ❌ [SCHEDULER])
3. Verify blockchain handlers are configured correctly
4. Manually trigger: `POST /admin/scheduler/refunds/trigger`

### Refunds Stuck in PROCESSING

**Problem**: Refunds stuck in PROCESSING status

**Causes**:
- Blockchain call failed but status wasn't reverted
- Database connection error
- Blockchain network issue

**Solution**:
1. Manually update status back to PENDING:
   ```sql
   UPDATE refunds SET status = 'PENDING' WHERE status = 'PROCESSING';
   ```
2. Manually trigger processing again
3. Check blockchain logs for actual transaction status

### High Error Rate

**Problem**: Many refunds failing

**Debug**:
1. Check blockchain connectivity
2. Verify wallet balances for each chain
3. Review blockchain handler logs
4. Check if blockchain RPC URL is configured correctly

## Advanced Configuration

### Custom Scheduled Job

Add a custom scheduled task:

```python
from app.services.refund_scheduler import add_scheduled_job

async def daily_refund_report():
    """Generate daily refund report"""
    # Your code here
    return {"message": "Report generated"}

# Add job that runs daily at 9 AM
add_scheduled_job(
    'daily_refund_report',
    daily_refund_report,
    trigger_type='cron',
    hour=9,
    minute=0
)
```

### Integration with Webhook Notifications

When refund processing completes, send webhook:

```python
# In refund_processor.py
async def process_all_pending_refunds():
    stats = {...}
    
    # Send webhook
    await send_webhook(
        url="https://your-app.com/webhooks/refunds",
        data=stats
    )
    
    return stats
```

## Performance Considerations

### Default Settings

- **Interval**: 60 minutes
- **Processing Time**: ~5-10 seconds per refund (varies by blockchain)
- **Database Queries**: ✅ Optimized (single query for all PENDING)

### For High Volume

If processing 100+ refunds:

1. **Increase interval**: `REFUND_SCHEDULER_INTERVAL_MINUTES=30` (process every 30 min)
2. **Monitor logs** for processing duration
3. **Consider database indexing** on refund status column:
   ```sql
   CREATE INDEX idx_refund_status ON refunds(status);
   ```

## Testing

### Manual Integration Test

```bash
# 1. Create a refund and verify it's PENDING
curl -X POST http://127.0.0.1:8000/refunds \
  -H "Authorization: Bearer MERCHANT_TOKEN" \
  -d '{"amount": 1.0, "blockchain": "polygon", ...}'

# Response should have status: "PENDING"

# 2. Trigger scheduler
curl -X POST http://127.0.0.1:8000/admin/scheduler/refunds/trigger \
  -H "Authorization: Bearer ADMIN_TOKEN"

# 3. Check refund status
curl -X GET http://127.0.0.1:8000/refunds/ref_xyz123 \
  -H "Authorization: Bearer MERCHANT_TOKEN"

# Status should be: "COMPLETED" or "FAILED"
```

## Summary

| Feature | Details |
|---------|---------|
| **Automatic Processing** | ✅ Every 60 minutes (configurable) |
| **Manual Trigger** | ✅ POST /admin/scheduler/refunds/trigger |
| **Status Tracking** | ✅ PENDING → PROCESSING → COMPLETED/FAILED |
| **Blockchain Support** | ✅ Polygon, Stellar, Solana, Soroban, TRON |
| **Admin Control** | ✅ Start, stop, status endpoints |
| **Error Handling** | ✅ Logs & returns error details |
| **Production Ready** | ✅ Configurable, monitorable, scalable |
