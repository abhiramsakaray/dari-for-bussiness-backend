

# Background task wrapper for processing refunds asynchronously
def process_refund(refund_id: str, merchant_id: str):
    """
    Wrapper function for background refund processing.
    Runs the async refund processor in a new event loop.
    Called by FastAPI BackgroundTasks.
    """
    try:
        logger.info(f"[BACKGROUND] Starting refund processor for refund_id={refund_id}, merchant_id={merchant_id}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(process_refund_on_chain(refund_id, merchant_id))
        loop.close()
        logger.info(f"[BACKGROUND] Refund processor completed with result={result}")
    except Exception as e:
        logger.error(f"[BACKGROUND] Error in refund processor: {str(e)}", exc_info=True)
