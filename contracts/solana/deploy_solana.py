"""
Deploy Dari Subscriptions Anchor Program to Solana Devnet (or Mainnet)

Usage:
    python contracts/solana/deploy_solana.py --network devnet
    python contracts/solana/deploy_solana.py --network mainnet

Prerequisites:
    - Solana CLI: sh -c "$(curl -sSfL https://release.anza.xyz/stable/install)"
    - Anchor CLI: cargo install --git https://github.com/coral-xyz/anchor avm
                  avm install latest && avm use latest
    - Set SOLANA_RELAYER_PRIVATE_KEY in .env (64-byte keypair as hex)
    - Fund the deployer wallet with SOL on the target network

The script:
    1. Writes a temporary keypair file from SOLANA_RELAYER_PRIVATE_KEY
    2. Runs `anchor build` to compile the program
    3. Runs `solana program deploy` to deploy
    4. Initializes the program config account
    5. Prints the program ID for .env

Note: For production, it's recommended to use `anchor deploy` directly
      with proper key management. This script is for development convenience.
"""

import argparse
import json
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

# ============= NETWORK CONFIG =============

NETWORKS = {
    "devnet": {
        "name": "Devnet",
        "url": "https://api.devnet.solana.com",
        "usdc_mint": "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU",
        "usdt_mint": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    },
    "mainnet": {
        "name": "Mainnet Beta",
        "url": "https://api.mainnet-beta.solana.com",
        "usdc_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "usdt_mint": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    },
}

PROGRAM_DIR = Path(__file__).resolve().parent / "dari_subscriptions"


def run_cmd(cmd, cwd=None, check=True):
    """Run a shell command and return output."""
    print(f"  $ {cmd}")
    result = subprocess.run(
        cmd, shell=True, cwd=cwd, capture_output=True, text=True
    )
    if check and result.returncode != 0:
        print(f"❌ Command failed:\n{result.stderr}")
        sys.exit(1)
    return result


def main():
    parser = argparse.ArgumentParser(description="Deploy Dari Subscriptions on Solana")
    parser.add_argument(
        "--network", choices=list(NETWORKS.keys()), default="devnet",
        help="Target network (default: devnet)"
    )
    parser.add_argument(
        "--skip-build", action="store_true",
        help="Skip anchor build step"
    )
    args = parser.parse_args()

    net_config = NETWORKS[args.network]

    print("=" * 60)
    print("Dari for Business — Solana Subscription Program Deployment")
    print("=" * 60)
    print(f"Network: {net_config['name']} ({net_config['url']})")

    # Get relayer key
    pk_hex = os.getenv("SOLANA_RELAYER_PRIVATE_KEY", "")
    if not pk_hex:
        print("❌ SOLANA_RELAYER_PRIVATE_KEY not set in .env")
        sys.exit(1)

    key_bytes = bytes.fromhex(pk_hex)
    if len(key_bytes) != 64:
        print(f"❌ SOLANA_RELAYER_PRIVATE_KEY must be 64 bytes (got {len(key_bytes)})")
        sys.exit(1)

    # Write temporary keypair file (Solana CLI expects JSON array format)
    keypair_array = list(key_bytes)
    keypair_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, prefix="dari_deploy_"
    )
    json.dump(keypair_array, keypair_file)
    keypair_file.close()

    try:
        # Get deployer address
        result = run_cmd(
            f'solana address --keypair "{keypair_file.name}"', check=False
        )
        deployer = result.stdout.strip()
        print(f"Deployer: {deployer}")

        # Set Solana config
        run_cmd(f'solana config set --url {net_config["url"]}')
        run_cmd(f'solana config set --keypair "{keypair_file.name}"')

        # Check balance
        result = run_cmd(f"solana balance {deployer}", check=False)
        print(f"Balance: {result.stdout.strip()}")
        print("=" * 60)

        # Step 1: Build the program
        if not args.skip_build:
            print("\n📦 Building Anchor program...")
            run_cmd("anchor build", cwd=str(PROGRAM_DIR))
            print("✅ Build complete")
        else:
            print("\n⏩ Skipping build (--skip-build)")

        # Step 2: Get the program ID from the built keypair
        program_keypair = PROGRAM_DIR / "target" / "deploy" / "dari_subscriptions-keypair.json"
        if program_keypair.exists():
            result = run_cmd(f'solana address --keypair "{program_keypair}"')
            program_id = result.stdout.strip()
        else:
            # If no keypair exists yet, generate one
            print("\n🔑 Generating program keypair...")
            program_keypair.parent.mkdir(parents=True, exist_ok=True)
            run_cmd(f'solana-keygen new --outfile "{program_keypair}" --no-bip39-passphrase --force')
            result = run_cmd(f'solana address --keypair "{program_keypair}"')
            program_id = result.stdout.strip()

            # Update program ID in lib.rs
            lib_rs = PROGRAM_DIR / "src" / "lib.rs"
            content = lib_rs.read_text()
            content = content.replace(
                'declare_id!("DariSubs11111111111111111111111111111111111")',
                f'declare_id!("{program_id}")',
            )
            lib_rs.write_text(content)
            print(f"   Updated declare_id in lib.rs: {program_id}")

            # Rebuild with correct ID
            print("\n📦 Rebuilding with correct program ID...")
            run_cmd("anchor build", cwd=str(PROGRAM_DIR))

        print(f"\n🆔  Program ID: {program_id}")

        # Step 3: Deploy
        print("\n🚀 Deploying program...")
        so_path = PROGRAM_DIR / "target" / "deploy" / "dari_subscriptions.so"

        if not so_path.exists():
            print(f"❌ Built program not found: {so_path}")
            sys.exit(1)

        run_cmd(
            f'solana program deploy "{so_path}" '
            f'--program-id "{program_keypair}" '
            f'--keypair "{keypair_file.name}"'
        )
        print(f"\n✅ Program deployed: {program_id}")

        # Summary
        print("\n" + "=" * 60)
        print("DEPLOYMENT COMPLETE")
        print("=" * 60)
        print(f"\nAdd to your .env file:")
        print(f"SUBSCRIPTION_PROGRAM_SOLANA={program_id}")
        print("")
        print("Next steps:")
        print("  1. Initialize the program config (run initialize instruction)")
        print(f"  2. Supported mints: USDC={net_config['usdc_mint']}")
        print(f"                       USDT={net_config['usdt_mint']}")
        print("")

        # Save deployment info
        deploy_info = {
            "network": args.network,
            "program_id": program_id,
            "deployer": deployer,
            "supported_mints": {
                "usdc": net_config["usdc_mint"],
                "usdt": net_config["usdt_mint"],
            },
        }

        deploy_file = PROGRAM_DIR.parent / f"deployment_{args.network}.json"
        with open(deploy_file, "w") as f:
            json.dump(deploy_info, f, indent=2)
        print(f"Deployment info saved to: {deploy_file}")

    finally:
        # Cleanup temp keypair
        try:
            os.unlink(keypair_file.name)
        except Exception:
            pass


if __name__ == "__main__":
    main()
