"""
Real Blockchain Relayer Service
Handles actual on-chain refund transactions via relayer APIs
"""
import logging
import httpx
import json
from typing import Optional
from decimal import Decimal
from datetime import datetime
from app.core.config import settings

logger = logging.getLogger(__name__)


class BlockchainRelayerError(Exception):
    """Base exception for relayer errors"""
    pass


class PolygonRelayer:
    """Polygon (EVM) refund relayer via relayer API or Web3 fallback"""
    
    @staticmethod
    async def send_refund(
        token_address: str,
        to_address: str,
        amount: Decimal,
        refund_id: str
    ) -> Optional[str]:
        """
        Send USDC/USDT refund on Polygon via relayer or direct Web3
        
        Args:
            token_address: Token contract address on Polygon
            to_address: Recipient wallet address
            amount: Amount in token decimals (usually 6 for USDC/USDT)
            refund_id: ChainPe refund ID for tracking
            
        Returns:
            tx_hash: Transaction hash on Polygon, or None if failed
        """
        try:
            # Try relayer service first
            if settings.POLYGON_RELAYER_URL and settings.POLYGON_RELAYER_API_KEY:
                logger.info(f"💜 Polygon Refund via RELAYER: {amount} tokens to {to_address}")
                
                payload = {
                    "type": "erc20_transfer",
                    "token": token_address,
                    "to": to_address,
                    "amount": str(amount),
                    "metadata": {
                        "refund_id": refund_id,
                        "platform": "dariforbusiness"
                    }
                }
                
                headers = {
                    "Authorization": f"Bearer {settings.POLYGON_RELAYER_API_KEY}",
                    "Content-Type": "application/json"
                }
                
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(
                        f"{settings.POLYGON_RELAYER_URL}/refund",
                        json=payload,
                        headers=headers
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        tx_hash = data.get("tx_hash") or data.get("transactionHash")
                        logger.info(f"✅ Polygon refund sent via relayer: {tx_hash}")
                        return tx_hash
                    else:
                        logger.error(f"Polygon relayer error: {response.status_code} - {response.text}")
                        return None
            
            # Fallback: Use Web3 direct with relayer key (EVM Gasless approach)
            relayer_key = getattr(settings, 'RELAYER_PRIVATE_KEY', None)
            polygon_rpc = getattr(settings, 'POLYGON_RPC_URL', None)
            
            if polygon_rpc and relayer_key:
                logger.info(f"💜 Polygon Refund via WEB3 (Relayer): {amount} tokens to {to_address}")
                
                from web3 import Web3
                
                w3 = Web3(Web3.HTTPProvider(polygon_rpc))
                if not w3.is_connected():
                    logger.error("Failed to connect to Polygon RPC")
                    return None
                
                # Get account from relayer key
                if not relayer_key.startswith('0x'):
                    relayer_key = '0x' + relayer_key
                account = w3.eth.account.from_key(relayer_key)
                
                # ERC20 transfer ABI
                erc20_abi = [
                    {
                        "constant": False,
                        "inputs": [
                            {"name": "_to", "type": "address"},
                            {"name": "_value", "type": "uint256"}
                        ],
                        "name": "transfer",
                        "outputs": [{"name": "", "type": "bool"}],
                        "type": "function"
                    }
                ]
                
                contract = w3.eth.contract(address=w3.to_checksum_address(token_address), abi=erc20_abi)
                amount_wei = int(amount * 10**6)  # USDC/USDT decimals
                
                # Build transaction
                tx = contract.functions.transfer(
                    w3.to_checksum_address(to_address),
                    amount_wei
                ).build_transaction({
                    'from': account.address,
                    'nonce': w3.eth.get_transaction_count(account.address),
                    'gas': 100000,
                    'gasPrice': w3.eth.gas_price,
                    'chainId': w3.eth.chain_id,
                })
                
                # Sign and send
                signed_tx = w3.eth.account.sign_transaction(tx, relayer_key)
                tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
                tx_hash_str = tx_hash.hex()
                
                logger.info(f"✅ Polygon refund sent via Web3: {tx_hash_str}")
                return tx_hash_str
            
            else:
                logger.error("Polygon not configured (no relayer or RPC)")
                return None
                    
        except Exception as e:
            logger.error(f"❌ Polygon refund failed: {str(e)}", exc_info=True)
            return None


class StellarRelayer:
    """Stellar payment relayer for sending refunds"""
    
    @staticmethod
    async def send_refund(
        to_address: str,
        amount: Decimal,
        token: str,
        issuer: str,
        refund_id: str
    ) -> Optional[str]:
        """
        Send refund on Stellar network via relayer or Stellar SDK fallback
        
        Args:
            to_address: Stellar destination address
            amount: Amount in tokens
            token: Token code (USDC, USDT, etc.)
            issuer: Token issuer address on Stellar
            refund_id: ChainPe refund ID for tracking
            
        Returns:
            tx_hash: Transaction hash, or None if failed
        """
        try:
            # Try relayer service first
            if settings.STELLAR_RELAYER_URL and settings.STELLAR_RELAYER_API_KEY:
                logger.info(f"⭐ Stellar Refund via RELAYER: {amount} {token} to {to_address}")
                
                payload = {
                    "operation": "payment",
                    "destination": to_address,
                    "asset": {
                        "code": token,
                        "issuer": issuer
                    },
                    "amount": str(amount),
                    "memo": f"refund-{refund_id[:20]}",
                    "metadata": {
                        "refund_id": refund_id,
                        "platform": "dariforbusiness"
                    }
                }
                
                headers = {
                    "Authorization": f"Bearer {settings.STELLAR_RELAYER_API_KEY}",
                    "Content-Type": "application/json"
                }
                
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(
                        f"{settings.STELLAR_RELAYER_URL}/submit_transaction",
                        json=payload,
                        headers=headers
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        tx_hash = data.get("hash") or data.get("tx_hash")
                        logger.info(f"✅ Stellar refund sent via relayer: {tx_hash}")
                        return tx_hash
                    else:
                        logger.error(f"Stellar relayer error: {response.status_code} - {response.text}")
                        return None
            
            # Fallback: Use Stellar SDK
            elif settings.STELLAR_SECRET_KEY:
                logger.info(f"⭐ Stellar Refund via SDK: {amount} {token} to {to_address}")
                
                from stellar_sdk import Server, TransactionBuilder, Network, Account as StellarAccount
                from stellar_sdk.exceptions import StellarSDKException
                
                server = Server(settings.STELLAR_SERVER_URL or "https://horizon-testnet.stellar.org")
                secret = settings.STELLAR_SECRET_KEY
                
                # Get source account
                source_keypair = None
                try:
                    from stellar_sdk import Keypair
                    source_keypair = Keypair.random()
                    if secret.startswith("S"):
                        from stellar_sdk import Keypair
                        source_keypair = Keypair.from_secret(secret)
                except:
                    pass
                
                if not source_keypair:
                    logger.error("Failed to parse Stellar secret key")
                    return None
                
                source_account = server.load_account(source_keypair.public_key)
                
                # Build transaction
                network = Network.TESTNET_NETWORK_PASSPHRASE if settings.ENVIRONMENT == "testnet" \
                         else Network.PUBLIC_NETWORK_PASSPHRASE
                
                builder = TransactionBuilder(
                    source_account=source_account,
                    base_fee=100,
                    network_passphrase=network
                )
                
                builder.append_payment_op(
                    destination=to_address,
                    asset_code=token if token != "XLM" else None,
                    asset_issuer=issuer if token != "XLM" else None,
                    amount=str(amount)
                ).set_timeout(30)
                
                transaction = builder.build()
                transaction.sign(secret)
                
                # Submit
                response = server.submit_transaction(transaction)
                tx_hash = response.get('hash')
                
                logger.info(f"✅ Stellar refund sent via SDK: {tx_hash}")
                return tx_hash
                    
            else:
                logger.error("Stellar not configured (no relayer or secret key)")
                return None
                    
        except StellarSDKException as e:
            logger.error(f"❌ Stellar refund failed: {str(e)}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"❌ Stellar refund error: {str(e)}", exc_info=True)
            return None


class SolanaRelayer:
    """Solana token relayer for sending refunds"""
    
    @staticmethod
    async def send_refund(
        to_address: str,
        amount: Decimal,
        mint_address: str,
        refund_id: str
    ) -> Optional[str]:
        """
        Send refund on Solana network
        
        Args:
            to_address: Solana destination address
            amount: Amount in smallest units (lamports * decimals)
            mint_address: SPL token mint address
            refund_id: ChainPe refund ID for tracking
            
        Returns:
            tx_sig: Transaction signature, or None if failed
        """
        try:
            if not settings.SOLANA_RELAYER_URL or not settings.SOLANA_RELAYER_API_KEY:
                logger.warning("Solana relayer not configured - skipping refund")
                return None
            
            logger.info(f"🟣 Solana Refund: {amount} SPL tokens to {to_address}")
            
            payload = {
                "action": "transfer_spl_token",
                "recipient": to_address,
                "mint": mint_address,
                "amount": str(int(amount)),  # Amount in smallest units
                "metadata": {
                    "refund_id": refund_id,
                    "platform": "dariforbusiness"
                }
            }
            
            headers = {
                "Authorization": f"Bearer {settings.SOLANA_RELAYER_API_KEY}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{settings.SOLANA_RELAYER_URL}/refund",
                    json=payload,
                    headers=headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    tx_sig = data.get("signature") or data.get("tx_signature")
                    logger.info(f"✅ Solana refund sent: {tx_sig}")
                    return tx_sig
                else:
                    logger.error(f"Solana relayer error: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"❌ Solana refund failed: {str(e)}", exc_info=True)
            return None


class SorobanRelayer:
    """Stellar Soroban smart contract relayer for refunds"""
    
    @staticmethod
    async def send_refund(
        contract_id: str,
        to_address: str,
        amount: Decimal,
        token: str,
        refund_id: str
    ) -> Optional[str]:
        """
        Send refund on Soroban via smart contract
        
        Args:
            contract_id: Soroban USDC contract address
            to_address: Destination stellar address
            amount: Amount in stroops
            token: Token identifier on Soroban
            refund_id: ChainPe refund ID for tracking
            
        Returns:
            tx_hash: Transaction hash, or None if failed
        """
        try:
            if not settings.SOROBAN_RELAYER_URL or not settings.SOROBAN_RELAYER_API_KEY:
                logger.warning("Soroban relayer not configured - skipping refund")
                return None
            
            logger.info(f"🔷 Soroban Refund: {amount} to {to_address}")
            
            payload = {
                "action": "transfer",
                "contract": contract_id,
                "from": settings.SOROBAN_MERCHANT_ADDRESS or "relay-address",
                "to": to_address,
                "amount": str(int(amount)),
                "token": token,
                "metadata": {
                    "refund_id": refund_id,
                    "platform": "dariforbusiness"
                }
            }
            
            headers = {
                "Authorization": f"Bearer {settings.SOROBAN_RELAYER_API_KEY}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{settings.SOROBAN_RELAYER_URL}/invoke_contract",
                    json=payload,
                    headers=headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    tx_hash = data.get("tx_hash") or data.get("transaction_hash")
                    logger.info(f"✅ Soroban refund sent: {tx_hash}")
                    return tx_hash
                else:
                    logger.error(f"Soroban relayer error: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"❌ Soroban refund failed: {str(e)}", exc_info=True)
            return None


class TronRelayer:
    """TRON (TVM) relayer for sending USDT refunds"""
    
    @staticmethod
    async def send_refund(
        to_address: str,
        amount: Decimal,
        usdt_contract: str,
        refund_id: str
    ) -> Optional[str]:
        """
        Send USDT refund on TRON network
        
        Args:
            to_address: TRON destination address
            amount: Amount in USDT (6 decimals)
            usdt_contract: USDT contract address on TRON
            refund_id: ChainPe refund ID for tracking
            
        Returns:
            tx_hash: Transaction hash, or None if failed
        """
        try:
            if not settings.TRON_RELAYER_URL or not settings.TRON_RELAYER_API_KEY:
                logger.warning("TRON relayer not configured - skipping refund")
                return None
            
            logger.info(f"🔺 TRON Refund: {amount} USDT to {to_address}")
            
            payload = {
                "method": "transfer_trc20",
                "to_address": to_address,
                "contract": usdt_contract,
                "amount": str(int(amount * 10**6)),  # Convert to smallest units
                "metadata": {
                    "refund_id": refund_id,
                    "platform": "dariforbusiness"
                }
            }
            
            headers = {
                "Authorization": f"Bearer {settings.TRON_RELAYER_API_KEY}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{settings.TRON_RELAYER_URL}/call_contract",
                    json=payload,
                    headers=headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    tx_hash = data.get("transaction_id") or data.get("tx_hash")
                    logger.info(f"✅ TRON refund sent: {tx_hash}")
                    return tx_hash
                else:
                    logger.error(f"TRON relayer error: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"❌ TRON refund failed: {str(e)}", exc_info=True)
            return None


class BlockchainRelayerService:
    """Unified blockchain relayer service"""
    
    async def send_refund(
        self,
        chain: str,
        token: str,
        amount: Decimal,
        to_address: str,
        refund_id: str
    ) -> Optional[str]:
        """
        Send refund on specified blockchain
        
        Args:
            chain: Blockchain (polygon, stellar, solana, soroban, tron)
            token: Token symbol (USDC, USDT, etc.)
            amount: Refund amount
            to_address: Recipient address
            refund_id: ChainPe refund ID
            
        Returns:
            tx_hash: On-chain transaction hash, or None if failed
        """
        
        if chain.lower() == "polygon":
            # Token contract addresses on Polygon (Mumbai testnet)
            token_contracts = {
                "USDC": "0x0FACa2Ae54c7F0a0d91ef92B3e928E42f27ba23d",  # USDC.e on Mumbai
                "USDT": "0xeaBc4b91d9375796AA3Dd58624e213cF216580c7",
            }
            token_address = token_contracts.get(token.upper(), token_contracts["USDC"])
            return await PolygonRelayer.send_refund(token_address, to_address, amount, refund_id)
        
        elif chain.lower() == "stellar":
            # Token issuers on Stellar testnet
            stellar_issuers = {
                "USDC": "GBBD47UZQ5PQE4V4IZQ2HA72KYQJD3O5OF7FA6CF2P4RJVVSWHIMNGO7",
                "USDT": "GBBD47UZQ5PQE4V4IZQ2HA72KYQJD3O5OF7FA6CF2P4RJVVSWHIMNGO",
                "XLM": "native"
            }
            issuer = stellar_issuers.get(token.upper(), stellar_issuers["USDC"])
            return await StellarRelayer.send_refund(to_address, amount, token.upper(), issuer, refund_id)
        
        elif chain.lower() == "solana":
            # SPL token mint addresses on Solana devnet
            solana_mints = {
                "USDC": "Gh9ZwEmdLJ8DscKiYP1u3GApZH8Y5iW4j7K7aNeVFXRs",
                "USDT": "J6A6oLKo9CZX8G9QfVK1P8oG5aK5KJ9X8G9QfVK1P8"
            }
            mint = solana_mints.get(token.upper(), solana_mints["USDC"])
            # Convert amount to smallest units (lamports * 6 decimals for USDC)
            amount_small_units = int(amount * 10**6)
            return await SolanaRelayer.send_refund(to_address, amount_small_units, mint, refund_id)
        
        elif chain.lower() == "soroban":
            soroban_contracts = {
                "USDC": settings.SOROBAN_USDC_CONTRACT or "CCF6YCRV6EMQU6TLQQCVF6A7GBCYGYLCJ2DHUIBQTCLXGZ4HA47IOU3",
                "USDT": settings.SOROBAN_USDT_CONTRACT or "CCZJ7V5CLDFNAWZB3JSUWF3GCZQY5A4VFDZ2ZTOKSVVGPEWXVP5KKFX"
            }
            contract = soroban_contracts.get(token.upper(), soroban_contracts["USDC"])
            return await SorobanRelayer.send_refund(contract, to_address, amount, token.upper(), refund_id)
        
        elif chain.lower() == "tron":
            tron_usdt = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"  # USDT contract on TRON
            return await TronRelayer.send_refund(to_address, amount, tron_usdt, refund_id)
        
        else:
            logger.error(f"Unsupported chain for refund: {chain}")
            return None


# Singleton instance
relayer_service = BlockchainRelayerService()
