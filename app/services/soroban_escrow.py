"""
Soroban Escrow Service - Smart Contract Integration
Handles escrow payments using Soroban smart contracts on Stellar
"""

import logging
from typing import Optional, Dict, Any
from stellar_sdk import (
    SorobanServer,
    Keypair,
    TransactionBuilder,
    Network,
    scval,
    Address as StellarAddress,
)
from stellar_sdk.soroban_rpc import GetTransactionStatus
from stellar_sdk.exceptions import BaseHorizonError
from app.core.config import settings

logger = logging.getLogger(__name__)


class SorobanEscrowService:
    """Service for managing escrow payments via Soroban smart contracts."""
    
    def __init__(self):
        self.server = SorobanServer(settings.SOROBAN_RPC_URL)
        self.contract_id = settings.SOROBAN_ESCROW_CONTRACT_ID
        self.usdc_contract_id = settings.SOROBAN_USDC_CONTRACT_ID
        self.network_passphrase = (
            Network.TESTNET_NETWORK_PASSPHRASE 
            if settings.STELLAR_NETWORK == "testnet" 
            else Network.PUBLIC_NETWORK_PASSPHRASE
        )
    
    async def create_escrow_payment(
        self,
        customer_secret: str,
        merchant_address: str,
        amount: str,
        session_id: str,
        timeout_seconds: int = 86400,  # 24 hours default
    ) -> Dict[str, Any]:
        """
        Create escrow payment via smart contract.
        
        Args:
            customer_secret: Customer's Stellar secret key
            merchant_address: Merchant's Stellar address
            amount: USDC amount (e.g., "50.00")
            session_id: Payment session ID (memo)
            timeout_seconds: Refund timeout in seconds
        
        Returns:
            Dict with tx_hash and status
        """
        try:
            customer_keypair = Keypair.from_secret(customer_secret)
            customer_address = customer_keypair.public_key
            
            # Convert amount to stroops (7 decimals for USDC)
            amount_stroops = int(float(amount) * 10**7)
            
            # Load account
            source_account = self.server.load_account(customer_address)
            
            # Build transaction to invoke create_escrow
            transaction = (
                TransactionBuilder(
                    source_account=source_account,
                    network_passphrase=self.network_passphrase,
                    base_fee=100000,  # Higher fee for Soroban
                )
                .append_invoke_contract_function_op(
                    contract_id=self.contract_id,
                    function_name="create_escrow",
                    parameters=[
                        scval.to_address(customer_address),
                        scval.to_address(merchant_address),
                        scval.to_address(self.usdc_contract_id),
                        scval.to_int128(amount_stroops),
                        scval.to_string(session_id),
                        scval.to_uint64(timeout_seconds),
                    ],
                )
                .set_timeout(30)
                .build()
            )
            
            # Prepare transaction (simulate)
            prepared_tx = self.server.prepare_transaction(transaction)
            
            # Sign
            prepared_tx.sign(customer_keypair)
            
            # Submit
            response = self.server.send_transaction(prepared_tx)
            
            logger.info(f"Escrow created: {session_id}, tx: {response.hash}")
            
            return {
                "tx_hash": response.hash,
                "status": "escrow_created",
                "session_id": session_id,
            }
            
        except Exception as e:
            logger.error(f"Error creating escrow: {str(e)}")
            raise
    
    async def release_escrow(
        self,
        merchant_secret: str,
        session_id: str,
    ) -> Dict[str, Any]:
        """
        Release escrowed funds to merchant.
        
        Args:
            merchant_secret: Merchant's Stellar secret key
            session_id: Payment session ID
        
        Returns:
            Dict with tx_hash and status
        """
        try:
            merchant_keypair = Keypair.from_secret(merchant_secret)
            merchant_address = merchant_keypair.public_key
            
            source_account = self.server.load_account(merchant_address)
            
            transaction = (
                TransactionBuilder(
                    source_account=source_account,
                    network_passphrase=self.network_passphrase,
                    base_fee=100000,
                )
                .append_invoke_contract_function_op(
                    contract_id=self.contract_id,
                    function_name="release_payment",
                    parameters=[
                        scval.to_string(session_id),
                        scval.to_address(self.usdc_contract_id),
                    ],
                )
                .set_timeout(30)
                .build()
            )
            
            prepared_tx = self.server.prepare_transaction(transaction)
            prepared_tx.sign(merchant_keypair)
            response = self.server.send_transaction(prepared_tx)
            
            logger.info(f"Escrow released: {session_id}, tx: {response.hash}")
            
            return {
                "tx_hash": response.hash,
                "status": "released",
                "session_id": session_id,
            }
            
        except Exception as e:
            logger.error(f"Error releasing escrow: {str(e)}")
            raise
    
    async def refund_escrow(
        self,
        customer_secret: str,
        session_id: str,
    ) -> Dict[str, Any]:
        """
        Refund payment to customer after timeout.
        
        Args:
            customer_secret: Customer's Stellar secret key
            session_id: Payment session ID
        
        Returns:
            Dict with tx_hash and status
        """
        try:
            customer_keypair = Keypair.from_secret(customer_secret)
            customer_address = customer_keypair.public_key
            
            source_account = self.server.load_account(customer_address)
            
            transaction = (
                TransactionBuilder(
                    source_account=source_account,
                    network_passphrase=self.network_passphrase,
                    base_fee=100000,
                )
                .append_invoke_contract_function_op(
                    contract_id=self.contract_id,
                    function_name="refund_payment",
                    parameters=[
                        scval.to_string(session_id),
                        scval.to_address(self.usdc_contract_id),
                    ],
                )
                .set_timeout(30)
                .build()
            )
            
            prepared_tx = self.server.prepare_transaction(transaction)
            prepared_tx.sign(customer_keypair)
            response = self.server.send_transaction(prepared_tx)
            
            logger.info(f"Escrow refunded: {session_id}, tx: {response.hash}")
            
            return {
                "tx_hash": response.hash,
                "status": "refunded",
                "session_id": session_id,
            }
            
        except Exception as e:
            logger.error(f"Error refunding escrow: {str(e)}")
            raise
    
    async def admin_refund(
        self,
        admin_secret: str,
        session_id: str,
    ) -> Dict[str, Any]:
        """
        Admin force refund (customer protection).
        
        Args:
            admin_secret: ChainPe admin's Stellar secret key
            session_id: Payment session ID
        
        Returns:
            Dict with tx_hash and status
        """
        try:
            admin_keypair = Keypair.from_secret(admin_secret)
            admin_address = admin_keypair.public_key
            
            source_account = self.server.load_account(admin_address)
            
            transaction = (
                TransactionBuilder(
                    source_account=source_account,
                    network_passphrase=self.network_passphrase,
                    base_fee=100000,
                )
                .append_invoke_contract_function_op(
                    contract_id=self.contract_id,
                    function_name="admin_refund",
                    parameters=[
                        scval.to_string(session_id),
                        scval.to_address(self.usdc_contract_id),
                    ],
                )
                .set_timeout(30)
                .build()
            )
            
            prepared_tx = self.server.prepare_transaction(transaction)
            prepared_tx.sign(admin_keypair)
            response = self.server.send_transaction(prepared_tx)
            
            logger.info(f"Admin refund: {session_id}, tx: {response.hash}")
            
            return {
                "tx_hash": response.hash,
                "status": "admin_refunded",
                "session_id": session_id,
            }
            
        except Exception as e:
            logger.error(f"Error in admin refund: {str(e)}")
            raise
    
    async def get_escrow_status(self, session_id: str) -> Dict[str, Any]:
        """
        Get escrow details from smart contract.
        
        Args:
            session_id: Payment session ID
        
        Returns:
            Dict with escrow details
        """
        try:
            # This would invoke get_escrow function
            # Implementation depends on how you want to query the contract
            # For now, return a placeholder
            logger.info(f"Querying escrow status: {session_id}")
            
            # TODO: Implement contract query
            return {
                "session_id": session_id,
                "status": "pending",
            }
            
        except Exception as e:
            logger.error(f"Error getting escrow status: {str(e)}")
            raise


# Singleton instance
escrow_service = SorobanEscrowService()
