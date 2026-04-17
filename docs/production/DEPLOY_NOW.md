# Deploy Contracts NOW - Quick Guide

**Follow these steps to deploy your contracts in the next 30 minutes**

---

## Step 1: Check Your Setup (2 minutes)

```bash
# Check if Node.js is installed
node --version
# Should show v18 or higher

# Check if dependencies are installed
cd contracts
npm list hardhat
# Should show hardhat@2.22.0 or similar

# If not installed:
npm install
```

---

## Step 2: Get Your Wallet Address (1 minute)

```bash
# Still in contracts directory
node -e "const ethers = require('ethers'); const wallet = new ethers.Wallet('18a8d786ee91a5977cf3b6182ece9fbe7e0865cdaf9dd507290775ec9f829650'); console.log('Your Wallet Address:', wallet.address);"
```

**Copy this address - you'll need it to get testnet tokens!**

---

## Step 3: Get Testnet Tokens (10-15 minutes)

Visit these faucets and request tokens for your wallet address:

### Polygon Amoy (Recommended - Start Here)
1. Go to: https://faucet.polygon.technology/
2. Select "Polygon Amoy"
3. Paste your wallet address
4. Click "Submit"
5. Wait 1-2 minutes

### Avalanche Fuji
1. Go to: https://faucet.avax.network/
2. Paste your wallet address
3. Select "Fuji Testnet"
4. Complete CAPTCHA
5. Click "Request"

### Base Sepolia
1. Go to: https://www.coinbase.com/faucets/base-ethereum-goerli-faucet
2. Sign in with Coinbase (or create account)
3. Paste your wallet address
4. Request tokens

### Others (Optional)
- Ethereum Sepolia: https://sepoliafaucet.com/
- BSC Testnet: https://testnet.bnbchain.org/faucet-smart
- Arbitrum Sepolia: https://faucet.quicknode.com/arbitrum/sepolia

---

## Step 4: Check Your Balance (1 minute)

```bash
# Check Polygon Amoy balance
npx hardhat run scripts/check-balance.js --network polygonAmoy

# Check Avalanche Fuji balance
npx hardhat run scripts/check-balance.js --network fuji

# Check Base Sepolia balance
npx hardhat run scripts/check-balance.js --network baseSepolia
```

You should see:
```
✅ Balance is sufficient for deployment
```

---

## Step 5: Deploy to Polygon Amoy (5 minutes)

```bash
# Deploy to Polygon Amoy testnet
npx hardhat run scripts/deploy.js --network polygonAmoy
```

**Expected output:**
```
============================================================
Dari for Business - Subscription Contract Deployment
============================================================
Network:  polygonAmoy (chainId: 80002)
Deployer: 0xYourAddress
Balance:  0.5 MATIC
============================================================

Deploying DariSubscriptions (UUPS proxy)...

✅ Proxy deployed to:          0xABC123...
✅ Implementation deployed to:  0xDEF456...

Adding supported token: USDC (0x8B0180...)
✅ USDC added
Adding supported token: USDT (0xcab2F4...)
✅ USDT added

============================================================
DEPLOYMENT COMPLETE
============================================================

Add to your .env file:
SUBSCRIPTION_CONTRACT_POLYGON=0xABC123...
```

**IMPORTANT: Copy the proxy address (0xABC123...)**

---

## Step 6: Update .env File (2 minutes)

Open your `.env` file and update:

```bash
# Find this line:
SUBSCRIPTION_CONTRACT_POLYGON=0xf6dE451A98764a5f08389e72F83AC7594E4e3045

# Replace with your new address:
SUBSCRIPTION_CONTRACT_POLYGON=0xYourNewProxyAddress
```

Save the file!

---

## Step 7: Deploy to More Testnets (Optional, 10 minutes)

```bash
# Avalanche Fuji
npx hardhat run scripts/deploy.js --network fuji

# Base Sepolia
npx hardhat run scripts/deploy.js --network baseSepolia

# BSC Testnet
npx hardhat run scripts/deploy.js --network bscTestnet

# Arbitrum Sepolia
npx hardhat run scripts/deploy.js --network arbitrumSepolia

# Ethereum Sepolia
npx hardhat run scripts/deploy.js --network sepolia
```

After each deployment, update `.env` with the contract address.

---

## Step 8: Test Your Deployment (5 minutes)

```bash
# Go back to root directory
cd ..

# Start your API server
python app/main.py
```

In another terminal:

```bash
# Create a test merchant
curl -X POST http://localhost:8000/merchant/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "Test123!@#",
    "business_name": "Test Store",
    "country": "US"
  }'

# Login
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "Test123!@#"
  }'

# Copy the access_token from response

# Complete onboarding
curl -X POST http://localhost:8000/onboarding/complete \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "business_name": "Test Store",
    "chains": ["polygon"],
    "tokens": ["USDC"]
  }'
```

You should see real wallet addresses generated!

---

## Automated Deployment (Alternative)

If you want to deploy to all testnets at once:

```bash
# Make scripts executable (Linux/Mac)
chmod +x deploy-all-testnets.sh

# Run automated deployment
bash deploy-all-testnets.sh
```

This will:
1. Check balance on each network
2. Ask for confirmation before deploying
3. Deploy to all testnets one by one
4. Show you the contract addresses

---

## Troubleshooting

### "insufficient funds for gas"
**Solution:** Get more testnet tokens from faucets above.

### "network does not support ENS"
**Solution:** This is just a warning, ignore it. Deployment should still work.

### "nonce too low"
**Solution:** Wait 2-3 minutes and try again.

### "timeout waiting for transaction"
**Solution:** The transaction might still be processing. Check the block explorer:
- Polygon Amoy: https://amoy.polygonscan.com/
- Avalanche Fuji: https://testnet.snowtrace.io/

### Deployment script not found
**Solution:** Make sure you're in the `contracts` directory:
```bash
cd contracts
```

---

## What's Next?

After deploying to testnets:

1. ✅ Test payment creation
2. ✅ Test subscription creation
3. ✅ Test refunds
4. ✅ Monitor for 24 hours
5. 🚀 Deploy to mainnets when ready

---

## Deploy to Mainnets (When Ready)

**⚠️ WARNING: This costs real money!**

```bash
# Polygon Mainnet (~$0.50)
npx hardhat run scripts/deploy.js --network polygon

# Avalanche Mainnet (~$1-2)
npx hardhat run scripts/deploy.js --network avalanche

# Base Mainnet (~$1-5)
npx hardhat run scripts/deploy.js --network base

# BSC Mainnet (~$0.50)
npx hardhat run scripts/deploy.js --network bsc

# Arbitrum Mainnet (~$1-5)
npx hardhat run scripts/deploy.js --network arbitrum

# Ethereum Mainnet (~$50-100) - Most expensive, deploy last
npx hardhat run scripts/deploy.js --network ethereum
```

Or use the automated script:
```bash
bash deploy-all-mainnets.sh
```

---

## Quick Reference

```bash
# Check balance
npx hardhat run scripts/check-balance.js --network polygonAmoy

# Deploy
npx hardhat run scripts/deploy.js --network polygonAmoy

# Verify (after deployment)
npx hardhat verify --network polygonAmoy 0xYourProxyAddress

# Check contract
npx hardhat console --network polygonAmoy
```

---

## Summary

**Time to complete:** 30-45 minutes

**Steps:**
1. ✅ Check setup (2 min)
2. ✅ Get wallet address (1 min)
3. ✅ Get testnet tokens (10-15 min)
4. ✅ Check balance (1 min)
5. ✅ Deploy to Polygon Amoy (5 min)
6. ✅ Update .env (2 min)
7. ✅ Deploy to more testnets (10 min)
8. ✅ Test deployment (5 min)

**You're ready to deploy! Start with Polygon Amoy.** 🚀
