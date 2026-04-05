"""
Deploy DariSubscriptionsTron to Tron Nile Testnet (or Mainnet)

Usage:
    python contracts/tron/deploy_tron.py --network nile
    python contracts/tron/deploy_tron.py --network mainnet

Prerequisites:
    pip install tronpy
    Set TRON_RELAYER_PRIVATE_KEY in .env (hex-encoded, no 0x prefix)

The script:
    1. Compiles DariSubscriptionsTron.sol using solc (must be installed)
    2. Deploys the contract to the specified Tron network
    3. Adds TRC-20 USDT and USDC as supported tokens
    4. Prints the deployed contract address for .env
"""

import argparse
import json
import os
import sys
import subprocess
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from tronpy import Tron
from tronpy.keys import PrivateKey

# ============= NETWORK CONFIG =============

NETWORKS = {
    "nile": {
        "name": "Nile Testnet",
        "api_url": "https://nile.trongrid.io",
        "network": "nile",
        "usdt": "TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj",   # Nile USDT
        "usdc": "TEMVynQpntMqkPxP6wXTW2K7e4sM3cQnAv",   # Nile USDC
    },
    "shasta": {
        "name": "Shasta Testnet",
        "api_url": "https://api.shasta.trongrid.io",
        "network": "shasta",
        "usdt": "",
        "usdc": "",
    },
    "mainnet": {
        "name": "Mainnet",
        "api_url": "https://api.trongrid.io",
        "network": "mainnet",
        "usdt": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
        "usdc": "TEkxiTehnzSmSe2XqrBj4w32RUN966rdz8",
    },
}

# ============= HELPERS =============

def compile_contract():
    """Compile the Solidity contract and return ABI + bytecode."""
    contract_path = Path(__file__).resolve().parent / "DariSubscriptionsTron.sol"

    if not contract_path.exists():
        print(f"❌ Contract not found: {contract_path}")
        sys.exit(1)

    print(f"📝 Compiling {contract_path.name}...")

    try:
        result = subprocess.run(
            [
                "solc",
                "--combined-json", "abi,bin",
                "--optimize",
                "--optimize-runs", "200",
                "--evm-version", "istanbul",
                str(contract_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        print("❌ solc not found. Install it:")
        print("   npm install -g solc")
        print("   OR download from https://github.com/ethereum/solidity/releases")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"❌ Compilation failed:\n{e.stderr}")
        sys.exit(1)

    compiled = json.loads(result.stdout)
    contracts = compiled.get("contracts", {})

    # Find the main contract
    contract_key = None
    for key in contracts:
        if "DariSubscriptionsTron" in key:
            contract_key = key
            break

    if not contract_key:
        print("❌ DariSubscriptionsTron not found in compiled output")
        print(f"   Available: {list(contracts.keys())}")
        sys.exit(1)

    contract_data = contracts[contract_key]
    abi = json.loads(contract_data["abi"]) if isinstance(contract_data["abi"], str) else contract_data["abi"]
    bytecode = contract_data["bin"]

    print(f"✅ Compiled successfully (bytecode size: {len(bytecode) // 2} bytes)")
    return abi, bytecode


def main():
    parser = argparse.ArgumentParser(description="Deploy DariSubscriptionsTron")
    parser.add_argument(
        "--network", choices=list(NETWORKS.keys()), default="nile",
        help="Target network (default: nile)"
    )
    args = parser.parse_args()

    net_config = NETWORKS[args.network]

    print("=" * 60)
    print("Dari for Business — Tron Subscription Contract Deployment")
    print("=" * 60)
    print(f"Network: {net_config['name']}")

    # Get private key
    pk_hex = os.getenv("TRON_RELAYER_PRIVATE_KEY", "")
    if not pk_hex:
        print("❌ TRON_RELAYER_PRIVATE_KEY not set in .env")
        sys.exit(1)

    private_key = PrivateKey(bytes.fromhex(pk_hex))
    deployer = private_key.public_key.to_base58check_address()
    print(f"Deployer: {deployer}")

    # Connect to Tron
    if args.network == "mainnet":
        client = Tron()
    else:
        client = Tron(network=net_config["network"])

    api_key = os.getenv("TRON_API_KEY", "")
    if api_key:
        client.conf["headers"] = {"TRON-PRO-API-KEY": api_key}

    # Check balance
    try:
        balance = client.get_account_balance(deployer)
        print(f"Balance: {balance} TRX")
    except Exception:
        print("⚠️  Could not fetch balance (account may not exist yet)")

    print("=" * 60)

    # Compile
    abi, bytecode = compile_contract()

    # Deploy
    print("\n🚀 Deploying DariSubscriptionsTron...")
    try:
        txn = (
            client.trx.deploy_contract(
                owner_address=deployer,
                abi=abi,
                bytecode=bytecode,
                # Constructor args: owner, relayer (both set to deployer initially)
                parameters=[
                    {"type": "address", "value": deployer},
                    {"type": "address", "value": deployer},
                ],
            )
            .fee_limit(1_000_000_000)  # 1000 TRX fee limit
            .build()
            .sign(private_key)
        )

        result = txn.broadcast()
        tx_hash = result.get("txid", "")
        print(f"📤 Tx sent: {tx_hash}")

        # Wait for confirmation
        receipt = result.wait(timeout=120)
        contract_address = receipt.get("contract_address", "")

        if not contract_address:
            # Try to parse from transaction info
            tx_info = client.get_transaction_info(tx_hash)
            contract_address = tx_info.get("contract_address", "")

        if contract_address:
            print(f"\n✅ Contract deployed: {contract_address}")
        else:
            print(f"\n⚠️  Tx confirmed but contract address not found in receipt")
            print(f"   Check tx: https://{'nile.' if args.network == 'nile' else ''}tronscan.org/#/transaction/{tx_hash}")
            sys.exit(1)

    except Exception as e:
        print(f"❌ Deployment failed: {e}")
        sys.exit(1)

    # Get contract object
    deployed = client.get_contract(contract_address)

    # Add supported tokens
    tokens = {}
    if net_config["usdt"]:
        tokens["USDT"] = net_config["usdt"]
    if net_config["usdc"]:
        tokens["USDC"] = net_config["usdc"]

    for symbol, addr in tokens.items():
        print(f"\n📌 Adding supported token: {symbol} ({addr})")
        try:
            tx = (
                deployed.functions.addSupportedToken(addr)
                .with_owner(deployer)
                .fee_limit(100_000_000)
                .build()
                .sign(private_key)
            )
            tx_result = tx.broadcast()
            tx_result.wait()
            print(f"   ✅ {symbol} added")
        except Exception as e:
            print(f"   ⚠️  Failed to add {symbol}: {e}")

    # Summary
    print("\n" + "=" * 60)
    print("DEPLOYMENT COMPLETE")
    print("=" * 60)
    print(f"\nAdd to your .env file:")
    print(f"SUBSCRIPTION_CONTRACT_TRON={contract_address}")
    print("")

    # Save deployment info
    deploy_info = {
        "network": args.network,
        "contract_address": contract_address,
        "deployer": deployer,
        "tx_hash": tx_hash,
        "supported_tokens": tokens,
    }

    deploy_file = Path(__file__).resolve().parent / f"deployment_{args.network}.json"
    with open(deploy_file, "w") as f:
        json.dump(deploy_info, f, indent=2)
    print(f"Deployment info saved to: {deploy_file}")


if __name__ == "__main__":
    main()
