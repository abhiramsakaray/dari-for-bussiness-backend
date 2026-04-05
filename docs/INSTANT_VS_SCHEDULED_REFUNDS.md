# Instant vs Scheduled Refund Processing - Implementation Complete

## Overview

Refunds now have **two distinct processing modes**:

1. **INSTANT MODE** (Manual Trigger) - Process all PENDING refunds immediately
2. **SCHEDULED MODE** (Fallback) - Only process PENDING refunds stuck for >60 minutes

## Changes Made

### 1. Updated `process_all_pending_refunds()` Function

**File**: `app/services/refund_processor.py`

Added two new parameters:
```python
async def process_all_pending_refunds(mode: str = "instant", stuck_minutes: int = 60) -> dict:
    """
    Process PENDING refunds in the database.
    
    Args:
        mode: "instant" to process all PENDING, or "scheduled" to only process stuck ones
        stuck_minutes: Time threshold (in minutes) for considering a refund "stuck"
    """
```

#### Mode: "INSTANT"
- Processes **all** PENDING refunds immediately
- Logs: `⚡ [INSTANT MODE] Found X pending refunds to process immediately`
- Returns: `'processed': count, 'failed': count`

#### Mode: "SCHEDULED"
- Filters to only process refunds older than `stuck_minutes` (default 60 minutes)
- Skips recent refunds that shouldn't delay scheduler
- Logs:
  - `⏭️  [SCHEDULED] Skipping refund X - only Y.1m pending (threshold: 60m)`
  - `🔧 [SCHEDULED] Processing stuck refund X - Y.1m pending (threshold: 60m)`
- Returns: `'processed': count, 'failed': count, 'skipped': count`

### 2. Updated Manual Trigger Endpoint

**File**: `app/routes/admin.py` - POST `/admin/scheduler/refunds/trigger`

Changed from:
```python
stats = await process_all_pending_refunds()
```

To:
```python
stats = await process_all_pending_refunds(mode="instant")
```

Response now includes `"mode": "instant"`:
```json
{
  "message": "Refund processing completed (INSTANT MODE)",
  "status": "success",
  "mode": "instant",
  "statistics": {
    "total_pending_found": 5,
    "successfully_processed": 4,
    "failed": 1,
    "errors": []
  }
}
```

### 3. Updated Scheduler Job

**File**: `app/services/refund_scheduler.py` - `run_pending_refunds_job()`

Changed from:
```python
stats = loop.run_until_complete(process_all_pending_refunds())
```

To:
```python
stats = loop.run_until_complete(process_all_pending_refunds(mode="scheduled", stuck_minutes=60))
```

- Runs every **60 minutes** (configurable)
- Only processes refunds **older than 60 minutes**
- Acts as a **fallback** for stuck/abandoned refunds

## Behavior Comparison

| Scenario | Manual Trigger | Scheduler | Behavior |
|----------|---|---|---|
| Refund created 5 minutes ago | ✅ Process | ⏭️ Skip | Instant user feedback, no fallback needed |
| Refund created 70 minutes ago | ✅ Process | ✅ Process | Both handle it, but manual is instant |
| No pending refunds | ✅ Complete | ✅ Complete (0 processed) | Graceful, no errors |

##API Endpoint Behavior

### Manual Trigger (Instant)
```bash
POST /admin/scheduler/refunds/trigger
Authorization: Bearer {token}
```

**Response (mode="instant")**:
```json
{
  "message": "Refund processing completed (INSTANT MODE)",
  "status": "success",
  "mode": "instant",
  "statistics": {
    "total_pending_found": 3,
    "successfully_processed": 3,
    "failed": 0,
    "errors": []
  }
}
```

### Scheduler (Scheduled)
- Runs automatically every 60 minutes
- Logs show: `[SCHEDULED MODE] Complete: X processed, Y failed, Z skipped (not stuck yet)`
- Only processes refunds that have been PENDING for >60 minutes

## Log Examples

### Instant Mode Logs
```
⚡ [INSTANT MODE] Found 3 pending refunds to process immediately
⏳ [INSTANT] Processing refund abc123...
✅ Successfully processed refund abc123
✅ [INSTANT MODE] Complete: 3 processed, 0 failed
```

### Scheduled Mode Logs
```
🔄 [SCHEDULED MODE] Found 5 total pending refunds - filtering for stuck ones
⏭️  [SCHEDULED] Skipping refund def456 - only 15.2m pending (threshold: 60m)
🔧 [SCHEDULED] Processing stuck refund ghi789 - 65.5m pending (threshold: 60m)
✅ [SCHEDULED] Complete: 1 processed, 0 failed, 4 skipped (not stuck yet)
```

## Response Statistics

### Instant Mode Response
```python
{
    'total_pending': 5,          # Total pending found
    'processed': 4,               # Successfully sent to blockchain
    'failed': 1,                  # Failed to process
    'skipped': 0,                 # Only in scheduled mode
    'processing_mode': 'instant',
    'errors': []
}
```

### Scheduled Mode Response
```python
{
    'total_pending': 5,           # Total pending found
    'processed': 1,               # Stuck ones that were processed
    'failed': 0,                  # Stuck ones that failed
    'skipped': 4,                 # Recent ones (not stuck yet)
    'processing_mode': 'scheduled',
    'errors': []
}
```

## Configuration

### Threshold for "Stuck"Refunds
```python
# In run_pending_refunds_job() - refund_scheduler.py
stuck_minutes=60  # Default: refunds pending for >60 minutes are "stuck"
```

Can be changed to different thresholds if needed:
```python
# Examples:
stuck_minutes=30   # Process if pending >30 minutes
stuck_minutes=120  # Process if pending >2 hours
```

## Benefits

1. **Instant User Feedback**: Manual trigger processes all PENDING immediately - merchant sees results right away
2. **Scheduler as Safety Net**: Runs every 60 minutes to catch stuck/abandoned refunds
3. **No Redundant Processing**: Recent refunds skip scheduler, reducing load
4. **Clear Logging**: Distinct log messages for instant vs scheduled mode
5. **Monitor-Friendly**: Response includes `mode` field for logging/monitoring

## Testing

### Test Instant Mode
```bash
curl -X POST http://127.0.0.1:8003/admin/scheduler/refunds/trigger \
  -H "Authorization: Bearer {admin_token}" \
  -H "Content-Type: application/json"
```

Expected: All PENDING refunds processed immediately

### Test Scheduled Mode
- Wait for scheduler to run (every 60 minutes)
- Check logs for `[SCHEDULED MODE]` entries
- Verify: Recent refunds are skipped, stuck ones are processed

## Server Startup

On app startup, logs will show:
```
✅ Refund scheduler started - will process refunds every 60 minutes
```

This means the scheduler is running in **SCHEDULED mode** as a fallback, while manual triggers use **INSTANT mode**.

## Deployment Notes

- No database migrations needed
- No API breaking changes
- Backward compatible (default mode="instant" for process_all_pending_refunds())
- Existing code that calls without mode parameter will default to "instant"
- Manual trigger endpoint automatically uses "instant" mode

---

**Status**: ✅ Implementation Complete
- Code changes: Done
- Scheduler updated: Done
- Trigger endpoint updated: Done
- Logging enhanced: Done
- Response format updated: Done
