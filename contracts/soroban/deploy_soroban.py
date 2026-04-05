"""
Deploy Dari Subscriptions Soroban Contract to Stellar Testnet (or Mainnet)

Usage:
    python contracts/soroban/deploy_soroban.py --network testnet
    python contracts/soroban/deploy_soroban.py --network mainnet

Prerequisites:
    - Stellar CLI: cargo install --locked stellar-cli --features opt
    - Rust/Cargo with wasm32-unknown-unknown target:
        rustup target add wasm32-unknown-unknown
    - Set SOROBAN_RELAYER_SECRET_KEY in .env (Stellar S... secret key)
    - Fund the deployer account with XLM on the target network

The script:
    1. Builds the Soroban contract (cargo build --target wasm32-unknown-unknown)
    2. Optimizes the WASM with stellar contract optimize
    3. Deploys the contract
    4. Initializes the contract with admin, relayer, and USDC token
    5. Prints the contract ID for .env
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

# ============= NETWORK CONFIG =============

NETWORKS = {
    "testnet": {
        "name": "Testnet",
        "rpc_url": "https://soroban-testnet.stellar.org",
        "network_passphrase": "Test SDF Network ; September 2015",
        "usdc_contract": "CBIELTK6YBZJU5UP2WWQEUCYKLPU6AUNZ2BQ4WWFEIE3USCIHMXQDAMA",  # Testnet USDC SAC
        "friendbot": "https://friendbot.stellar.org",
    },
    "mainnet": {
        "name": "Mainnet",
        "rpc_url": "https://soroban-rpc.mainnet.stellar.gateway.fm",
        "network_passphrase": "Public Global Stellar Network ; September 2015",
        "usdc_contract": "CCW67TSZV3SSS2HXMBQ5JFGCKJNXKZM7UQUWUZPUTHXSTZLEO7SJMI",  # Mainnet USDC SAC (Centre)
        "friendbot": None,
    },
}

CONTRACT_DIR = Path(__file__).resolve().parent / "dari_subscriptions"


def run_cmd(cmd, cwd=None, check=True):
    """Run a shell command and return output."""
    print(f"  $ {cmd}")
    result = subprocess.run(
        cmd, shell=True, cwd=cwd, capture_output=True, text=True
    )
    if check and result.returncode != 0:
        print(f"❌ Command failed:\n{result.stderr}")
        if not check:
            return result
        sys.exit(1)
    return result


def main():
    parser = argparse.ArgumentParser(description="Deploy Dari Subscriptions on Soroban")
    parser.add_argument(
        "--network", choices=list(NETWORKS.keys()), default="testnet",
        help="Target network (default: testnet)"
    )
    parser.add_argument(
        "--skip-build", action="store_true",
        help="Skip build step"
    )
    args = parser.parse_args()

    net_config = NETWORKS[args.network]

    print("=" * 60)
    print("Dari for Business — Soroban Subscription Contract Deployment")
    print("=" * 60)
    print(f"Network: {net_config['name']}")
    print(f"RPC:     {net_config['rpc_url']}")

    # Get relayer secret key
    secret_key = os.getenv("SOROBAN_RELAYER_SECRET_KEY", "")
    if not secret_key:
        print("❌ SOROBAN_RELAYER_SECRET_KEY not set in .env")
        sys.exit(1)

    if not secret_key.startswith("S"):
        print("❌ SOROBAN_RELAYER_SECRET_KEY must be a Stellar secret key (starts with S)")
        sys.exit(1)

    # Derive public key
    try:
        from stellar_sdk import Keypair
        kp = Keypair.from_secret(secret_key)
        deployer = kp.public_key
    except Exception:
        # Fallback: use stellar CLI
        result = run_cmd(f'stellar keys address --secret-key {secret_key}', check=False)
        deployer = result.stdout.strip() if result.returncode == 0 else "unknown"

    print(f"Deployer: {deployer}")
    print("=" * 60)

    # Step 1: Build the contract
    if not args.skip_build:
        print("\n📦 Building Soroban contract...")
        run_cmd(
            "cargo build --target wasm32-unknown-unknown --release",
            cwd=str(CONTRACT_DIR),
        )

        # Optimize WASM
        wasm_path = CONTRACT_DIR / "target" / "wasm32-unknown-unknown" / "release" / "dari_subscriptions_soroban.wasm"
        if wasm_path.exists():
            print("🔧 Optimizing WASM...")
            run_cmd(f'stellar contract optimize --wasm "{wasm_path}"', check=False)
            optimized = wasm_path.with_suffix(".optimized.wasm")
            if optimized.exists():
                wasm_path = optimized
            print(f"✅ Build complete ({wasm_path.stat().st_size} bytes)")
        else:
            print(f"❌ WASM not found at: {wasm_path}")
            # Try alternative name
            alt_wasm = CONTRACT_DIR / "target" / "wasm32-unknown-unknown" / "release" / "dari_subscriptions_soroban.wasm"
            print(f"   Looking for alternative: {alt_wasm}")
            sys.exit(1)
    else:
        print("\n⏩ Skipping build (--skip-build)")
        wasm_path = CONTRACT_DIR / "target" / "wasm32-unknown-unknown" / "release" / "dari_subscriptions_soroban.wasm"
        optimized = wasm_path.with_suffix(".optimized.wasm")
        if optimized.exists():
            wasm_path = optimized

    # Step 2: Deploy
    print("\n🚀 Deploying contract...")

    # Create identity from secret key for stellar CLI
    identity_name = "dari-deployer"
    run_cmd(
        f'stellar keys add {identity_name} --secret-key',
        check=False  # May already exist
    )

    deploy_result = run_cmd(
        f'stellar contract deploy '
        f'--wasm "{wasm_path}" '
        f'--source {identity_name} '
        f'--rpc-url {net_config["rpc_url"]} '
        f'--network-passphrase "{net_config["network_passphrase"]}"'
    )
    contract_id = deploy_result.stdout.strip()

    if not contract_id:
        print("❌ Deployment failed — no contract ID returned")
        sys.exit(1)

    print(f"\n✅ Contract deployed: {contract_id}")

    # Step 3: Initialize the contract
    print("\n🔧 Initializing contract...")
    usdc_contract = net_config["usdc_contract"]

    init_result = run_cmd(
        f'stellar contract invoke '
        f'--id {contract_id} '
        f'--source {identity_name} '
        f'--rpc-url {net_config["rpc_url"]} '
        f'--network-passphrase "{net_config["network_passphrase"]}" '
        f'-- initialize '
        f'--admin {deployer} '
        f'--relayer {deployer} '
        f'--token {usdc_contract}',
        check=False,
    )

    if init_result.returncode == 0:
        print("✅ Contract initialized")
        print(f"   Admin:   {deployer}")
        print(f"   Relayer: {deployer} (update to dedicated relayer later)")
        print(f"   Token:   {usdc_contract} (USDC)")
    else:
        print(f"⚠️  Initialization may have failed: {init_result.stderr[:200]}")
        print("   You can initialize manually:")
        print(f"   stellar contract invoke --id {contract_id} -- initialize ...")

    # Summary
    print("\n" + "=" * 60)
    print("DEPLOYMENT COMPLETE")
    print("=" * 60)
    print(f"\nAdd to your .env file:")
    print(f"SUBSCRIPTION_CONTRACT_SOROBAN={contract_id}")
    print("")

    # Save deployment info
    deploy_info = {
        "network": args.network,
        "contract_id": contract_id,
        "deployer": deployer,
        "usdc_contract": usdc_contract,
    }

    deploy_file = CONTRACT_DIR.parent / f"deployment_{args.network}.json"
    with open(deploy_file, "w") as f:
        json.dump(deploy_info, f, indent=2)
    print(f"Deployment info saved to: {deploy_file}")


if __name__ == "__main__":
    main()
