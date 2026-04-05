"""
Quick test to verify scheduler is working
"""
import asyncio
from app.core.config import settings
from app.services.subscription_scheduler import scheduler

async def test():
    print("\n" + "="*80)
    print("SCHEDULER TEST")
    print("="*80)
    
    print(f"\nConfiguration:")
    print(f"  WEB3_SUBSCRIPTIONS_ENABLED: {settings.WEB3_SUBSCRIPTIONS_ENABLED}")
    print(f"  SCHEDULER_INTERVAL_SECONDS: {settings.SCHEDULER_INTERVAL_SECONDS}")
    print(f"  SCHEDULER_BATCH_SIZE: {settings.SCHEDULER_BATCH_SIZE}")
    
    print(f"\nScheduler Status:")
    status = scheduler.get_status()
    for key, value in status.items():
        print(f"  {key}: {value}")
    
    if not scheduler.is_running:
        print("\n⚠️  Scheduler is NOT running!")
        print("\nStarting scheduler...")
        await scheduler.start()
        await asyncio.sleep(2)
        print("✅ Scheduler started")
        
        status = scheduler.get_status()
        print(f"\nNew Status:")
        for key, value in status.items():
            print(f"  {key}: {value}")
    else:
        print("\n✅ Scheduler is running!")
    
    print("\n" + "="*80 + "\n")

if __name__ == "__main__":
    asyncio.run(test())
