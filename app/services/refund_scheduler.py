"""
Refund Scheduler Service
Automatically processes pending refunds at regular intervals
"""
import logging
import asyncio
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.services.refund_processor import process_all_pending_refunds

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = BackgroundScheduler()


def start_refund_scheduler(interval_minutes: int = 60):
    """
    Start the automatic refund scheduler.
    
    Args:
        interval_minutes: How often to process pending refunds (default: 60 minutes)
    """
    if scheduler.running:
        logger.warning("Scheduler is already running")
        return
    
    try:
        # Add job to process pending refunds
        scheduler.add_job(
            func=run_pending_refunds_job,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id='process_pending_refunds',
            name='Process Pending Refunds',
            replace_existing=True,
            max_instances=1,
        )
        
        scheduler.start()
        logger.info(f"✅ Refund scheduler started - will process refunds every {interval_minutes} minutes")
        
    except Exception as e:
        logger.error(f"❌ Failed to start refund scheduler: {str(e)}", exc_info=True)


def stop_refund_scheduler():
    """Stop the automatic refund scheduler"""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("⏹️ Refund scheduler stopped")


def run_pending_refunds_job():
    """Job function that runs in the scheduler - processes stuck/pending refunds as fallback"""
    try:
        logger.info(f"🔄 [SCHEDULER] Starting pending refund processor at {datetime.now().isoformat()}")
        
        # Run the async function in a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Process in SCHEDULED mode - only refunds stuck for 60+ minutes
        stats = loop.run_until_complete(process_all_pending_refunds(mode="scheduled", stuck_minutes=60))
        
        loop.close()
        
        logger.info(
            f"✅ [SCHEDULER] Pending refund processor completed: "
            f"{stats['processed']} processed, {stats['failed']} failed, "
            f"{stats['skipped']} skipped (not stuck yet), "
            f"{stats['total_pending']} total pending"
        )
        
        if stats['errors']:
            logger.warning(f"⚠️ [SCHEDULER] Errors encountered: {stats['errors']}")
        
    except Exception as e:
        logger.error(
            f"❌ [SCHEDULER] Error in pending refund processor: {str(e)}", 
            exc_info=True
        )


def add_scheduled_job(
    job_name: str,
    async_func,
    trigger_type: str = 'interval',
    **trigger_kwargs
):
    """
    Add a custom scheduled job.
    
    Args:
        job_name: Unique name for the job
        async_func: Async function to run
        trigger_type: 'interval', 'cron', 'date'
        **trigger_kwargs: Arguments for the trigger (e.g., minutes=60, hour=12)
    
    Example:
        add_scheduled_job(
            'daily_refund_report',
            generate_refund_report,
            trigger_type='cron',
            hour=9,
            minute=0
        )
    """
    try:
        if trigger_type == 'interval':
            trigger = IntervalTrigger(**trigger_kwargs)
        elif trigger_type == 'cron':
            from apscheduler.triggers.cron import CronTrigger
            trigger = CronTrigger(**trigger_kwargs)
        elif trigger_type == 'date':
            from apscheduler.triggers.date import DateTrigger
            trigger = DateTrigger(**trigger_kwargs)
        else:
            raise ValueError(f"Unknown trigger type: {trigger_type}")
        
        def job_wrapper():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(async_func())
            loop.close()
            return result
        
        scheduler.add_job(
            func=job_wrapper,
            trigger=trigger,
            id=job_name,
            name=job_name,
            replace_existing=True,
            max_instances=1,
        )
        
        logger.info(f"✅ Added scheduled job: {job_name}")
        
    except Exception as e:
        logger.error(f"❌ Failed to add scheduled job {job_name}: {str(e)}", exc_info=True)


def list_scheduled_jobs():
    """List all currently scheduled jobs"""
    jobs = scheduler.get_jobs()
    job_list = []
    for job in jobs:
        job_list.append({
            'id': job.id,
            'name': job.name,
            'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
            'trigger': str(job.trigger)
        })
    return job_list
