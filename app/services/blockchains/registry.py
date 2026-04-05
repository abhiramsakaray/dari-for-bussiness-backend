"""
Blockchain Registry - Manages all blockchain listeners

Central registry for managing blockchain listeners and routing payments.
Wires DB-backed payment callbacks for each chain.
"""

import asyncio
import logging
from typing import Dict, Optional, List, Callable, Any
from datetime import datetime

from .base import BlockchainListener, BlockchainConfig, TokenConfig, PaymentInfo, ListenerStatus

logger = logging.getLogger(__name__)

# Singleton instance
_registry_instance: Optional["BlockchainRegistry"] = None


class BlockchainRegistry:
    """
    Central registry for all blockchain listeners.

    Manages lifecycle of listeners and routes payments to handlers.
    """

    def __init__(self):
        self._listeners: Dict[str, BlockchainListener] = {}
        self._payment_handlers: List[Callable[[PaymentInfo], Any]] = []
        self._is_running = False

    def register_listener(self, listener: BlockchainListener):
        """Register a blockchain listener"""
        chain = listener.chain
        if chain in self._listeners:
            logger.warning(f"Replacing existing listener for {chain}")

        self._listeners[chain] = listener
        listener.set_payment_callback(self._on_payment_detected)
        listener.set_error_callback(self._on_listener_error)
        logger.info(f"Registered listener for {chain}")

    def unregister_listener(self, chain: str):
        """Unregister a blockchain listener"""
        if chain in self._listeners:
            del self._listeners[chain]
            logger.info(f"Unregistered listener for {chain}")

    def get_listener(self, chain: str) -> Optional[BlockchainListener]:
        """Get listener for a specific chain"""
        return self._listeners.get(chain)

    def get_all_chains(self) -> List[str]:
        """Get all registered chain identifiers"""
        return list(self._listeners.keys())

    def add_payment_handler(self, handler: Callable[[PaymentInfo], Any]):
        """Add a payment handler callback"""
        self._payment_handlers.append(handler)

    async def _on_payment_detected(self, payment: PaymentInfo):
        """Called when any listener detects a confirmed payment"""
        logger.info(f"Payment detected on {payment.chain}: {payment.amount} {payment.token_symbol}")

        for handler in self._payment_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(payment)
                else:
                    handler(payment)
            except Exception as e:
                logger.error(f"Error in payment handler: {e}")

    async def _on_listener_error(self, error: Exception):
        """Called when a listener encounters an error"""
        logger.error(f"Listener error: {error}")

    async def start_all(self):
        """Start all registered listeners"""
        if self._is_running:
            logger.warning("Registry already running")
            return

        self._is_running = True
        logger.info(f"Starting {len(self._listeners)} blockchain listeners...")

        tasks = []
        for chain, listener in self._listeners.items():
            tasks.append(self._start_listener(chain, listener))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _start_listener(self, chain: str, listener: BlockchainListener):
        """Start a single listener with error handling"""
        try:
            await listener.start()
        except Exception as e:
            logger.error(f"Failed to start {chain} listener: {e}")

    async def stop_all(self):
        """Stop all registered listeners"""
        self._is_running = False
        logger.info("Stopping all blockchain listeners...")

        tasks = []
        for chain, listener in self._listeners.items():
            tasks.append(listener.stop())

        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("All listeners stopped")

    async def verify_payment(
        self,
        chain: str,
        tx_hash: str,
        expected_to: str,
        expected_amount: str,
        expected_token: str,
        memo: Optional[str] = None
    ) -> bool:
        """Verify a payment on a specific chain."""
        listener = self.get_listener(chain)
        if not listener:
            logger.error(f"No listener for chain: {chain}")
            return False

        return await listener.verify_payment(
            tx_hash=tx_hash,
            expected_to=expected_to,
            expected_amount=expected_amount,
            expected_token=expected_token,
            memo=memo
        )

    def get_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all listeners"""
        status = {}
        for chain, listener in self._listeners.items():
            status[chain] = {
                "status": listener.status.value,
                "is_running": listener.is_running,
                "tokens": len(listener.tokens),
                "config": {
                    "rpc_url": listener.config.rpc_url[:50] + "..." if len(listener.config.rpc_url) > 50 else listener.config.rpc_url,
                    "confirmations_required": listener.config.confirmations_required,
                    "poll_interval": listener.config.poll_interval_seconds
                }
            }
        return status


def get_registry() -> BlockchainRegistry:
    """Get singleton registry instance"""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = BlockchainRegistry()
    return _registry_instance


def create_registry_with_listeners(config: Dict[str, Any] = None) -> BlockchainRegistry:
    """
    Create a registry with listeners based on enabled chains in settings.
    Wires DB-backed payment callbacks (process_*_payment) for each chain.
    """
    from app.core.config import settings
    from .stellar_listener import create_stellar_listener, process_stellar_payment
    from .evm_listener import create_evm_listener, process_evm_payment
    from .tron_listener import create_tron_listener, process_tron_payment

    config = config or {}
    registry = get_registry()

    # Stellar
    if config.get("stellar", {}).get("enabled", settings.STELLAR_ENABLED):
        try:
            stellar_listener = create_stellar_listener(config.get("stellar", {}))
            stellar_listener.set_payment_callback(process_stellar_payment)
            registry.register_listener(stellar_listener)
            logger.info("✅ Stellar listener registered")
        except Exception as e:
            logger.error(f"Failed to create Stellar listener: {e}")

    # EVM chains (Ethereum, Polygon, Base, BSC, Arbitrum)
    for chain in ["ethereum", "polygon", "base", "bsc", "arbitrum"]:
        chain_upper = chain.upper()
        enabled = config.get(chain, {}).get("enabled", getattr(settings, f"{chain_upper}_ENABLED", False))
        if enabled:
            try:
                evm_listener = create_evm_listener(chain, config.get(chain, {}))
                evm_listener.set_payment_callback(process_evm_payment)
                registry.register_listener(evm_listener)
                logger.info(f"✅ {chain.title()} listener registered")
            except Exception as e:
                logger.error(f"Failed to create {chain} listener: {e}")

    # Tron
    if config.get("tron", {}).get("enabled", settings.TRON_ENABLED):
        try:
            tron_listener = create_tron_listener(config.get("tron", {}))
            tron_listener.set_payment_callback(process_tron_payment)
            registry.register_listener(tron_listener)
            logger.info("✅ Tron listener registered")
        except Exception as e:
            logger.error(f"Failed to create Tron listener: {e}")

    return registry
