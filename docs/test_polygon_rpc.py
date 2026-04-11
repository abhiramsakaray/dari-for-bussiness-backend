#!/usr/bin/env python3
"""Test Polygon RPC connection and block scanning."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web3 import Web3
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Test Polygon Amoy RPC
rpc_url = "https://rpc-amoy.polygon.technology"
logger.info(f"Connecting to {rpc_url}")

try:
    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 10}))
    is_connected = w3.is_connected()
    logger.info(f"Connected: {is_connected}")
    
    if is_connected:
        # Get current block
        current_block = w3.eth.block_number
        logger.info(f"Current block: {current_block}")
        
        # Get a past block for testing
        test_from_block = current_block - 100
        test_to_block = current_block
        logger.info(f"Testing get_logs for blocks {test_from_block}-{test_to_block}")
        
        # USDC token address
        usdc_addr = "0x8B0180f2101c8260d49339abfEe87927412494B4"
        
        # Merchant wallet to watch
        to_address = "0xca95c77f2dd2b6b9313a0e2d5bf0973cd53fcced"
        to_topic = "0x" + to_address[2:].rjust(64, "0")
        
        ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
        
        filter_params = {
            "fromBlock": test_from_block,
            "toBlock": test_to_block,
            "address": w3.to_checksum_address(usdc_addr),
            "topics": [ERC20_TRANSFER_TOPIC, None, [to_topic]]
        }
        
        logger.info(f"Filter params: {filter_params}")
        logs = w3.eth.get_logs(filter_params)
        logger.info(f"Found {len(logs)} logs")
        
        for i, log in enumerate(logs[:5]):  # Show first 5
            logger.info(f"\nLog {i}:")
            logger.info(f"  Address: {log.get('address')}")
            logger.info(f"  Topics: {log.get('topics')}")
            logger.info(f"  Data: {log.get('data')[:20]}..." if log.get('data') else "  Data: None")
            logger.info(f"  BlockNumber: {log.get('blockNumber')}")
            logger.info(f"  TransactionHash: {log.get('transactionHash')}")
            
except Exception as e:
    logger.error(f"Error: {e}", exc_info=True)
