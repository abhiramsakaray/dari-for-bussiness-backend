"""
Unified Blockchain Listener Runner

Starts all enabled chain listeners concurrently:
- Stellar (USDC)
- Ethereum (USDC, USDT, PYUSD)
- Polygon (USDC, USDT)
- Base (USDC)
- BSC (USDC, USDT)
- Arbitrum (USDC, USDT)
- Tron (USDT, USDC)
- Solana (USDC) — Requires solders/anchorpy

Usage:
    python run_listeners.py                     # Start all enabled listeners
    python run_listeners.py polygon tron bsc    # Start only specific chains
"""

import asyncio
import logging
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def run(chains=None):
    """Start blockchain listeners for the specified (or all enabled) chains."""
    from app.core.config import settings
    from app.services.blockchains.stellar_listener import create_stellar_listener, process_stellar_payment
    from app.services.blockchains.evm_listener import create_evm_listener, process_evm_payment
    from app.services.blockchains.tron_listener import create_tron_listener, process_tron_payment

    listeners = []

    # Determine which chains to start
    if chains:
        enabled = [c.lower() for c in chains]
    else:
        enabled = settings.enabled_chains

    logger.info(f"Enabled chains: {enabled}")
    net_label = "mainnet" if settings.USE_MAINNET else "testnet"
    logger.info(f"Network mode: {net_label}")

    # Stellar
    if "stellar" in enabled:
        try:
            listener = create_stellar_listener()
            listener.set_payment_callback(process_stellar_payment)
            listeners.append(listener)
            logger.info("Created Stellar listener")
        except Exception as e:
            logger.error(f"Failed to create Stellar listener: {e}")

    # EVM chains
    for chain in ["ethereum", "polygon", "base", "bsc", "arbitrum"]:
        if chain in enabled:
            try:
                listener = create_evm_listener(chain)
                listener.set_payment_callback(process_evm_payment)
                listeners.append(listener)
                logger.info(f"Created {chain.upper()} listener")
            except Exception as e:
                logger.error(f"Failed to create {chain} listener: {e}")

    # Tron
    if "tron" in enabled:
        try:
            listener = create_tron_listener()
            listener.set_payment_callback(process_tron_payment)
            listeners.append(listener)
            logger.info("Created Tron listener")
        except Exception as e:
            logger.error(f"Failed to create Tron listener: {e}")

    if not listeners:
        logger.error("No listeners created, exiting")
        return

    logger.info(f"Starting {len(listeners)} listener(s)...")
    
    # Start each listener
    tasks = []
    for i, listener in enumerate(listeners):
        logger.info(f"[{i+1}/{len(listeners)}] Starting {listener.config.chain}...")
        task = asyncio.create_task(listener.start())
        tasks.append((listener, task))
    
    try:
        # Run all listeners concurrently
        await asyncio.gather(*[task for _, task in tasks])
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, stopping listeners...")
    finally:
        for listener, task in tasks:
            try:
                if not task.done():
                    task.cancel()
                await listener.stop()
            except Exception as e:
                logger.error(f"Error stopping {listener.config.chain} listener: {e}")


if __name__ == "__main__":
    chains = sys.argv[1:] if len(sys.argv) > 1 else None
    try:
        asyncio.run(run(chains))
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
