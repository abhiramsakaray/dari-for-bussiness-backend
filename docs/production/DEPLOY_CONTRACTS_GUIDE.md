# Smart Contract Deployment Guide

**Step-by-step guide to deploy DariSubscriptions contracts to all chains**

---

## Prerequisites Checklist

Before deploying, ensure you have:

- [ ] Node.js 18+ installed
- [ ] Relayer wallet with private key
- [ ] Gas tokens in relayer wallet for each chain
- [ ] RPC endpoints configured (optional but recommended)
- [ ] Block explorer API keys (for verification)

---

## Step 1: Install Dependencies

```bash
cd contracts
npm install
cd ..
```

Expected output:
```
added 500+ packages
```

---

## Step 2: Check Your Relayer Wallet

Your relayer private key is already set in `.env`:
```
RELAYER_PRIVATE_KEY=18a8d786ee91a5977cf3b6182ece9fbe7e0865cdaf9dd507290775ec9f829650
```

**Get your wallet address:**
```bash
cd contracts
node -e "const ethers = require('ethers'); const wallet = new ethers.Wallet('18a8d786ee91a5977cf3b6182ece9fbe7e0865cdaf9dd507290775ec9f829650'); console.log('Wallet Address:', wallet.address);"
```

This will show your deployer address. You need to fund this address with gas tokens.

---

## Step 3: Fund Your Relayer Wallet

You need gas tokens on each chain you want to deploy to:

### Testnets (Free - Use Faucets)

| Chain | Token | Faucet URL | Amount Needed |
|-------|-------|------------|---------------|
| Polygon Amoy | MATIC | https://faucet.polygon.technology/ | 0.5 MATIC |
| Ethereum Sepolia | ETH | https://sepoliafaucet.com/ | 0.1 ETH |
| Base Sepolia | ETH | https://www.coinbase.com/faucets/base-ethereum-goerli-faucet | 0.1 ETH |
| BSC Testnet | BNB | https://testnet.bnbchain.org/faucet-smart | 0.5 BNB |
| Arbitrum Sepolia | ETH | https://faucet.quicknode.com/arbitrum/sepolia | 0.1 ETH |
| Avalanche Fuji | AVAX | https://faucet.avax.network/ | 1 AVAX |

### Mainnets (Costs Real Money)

| Chain | Token | Estimated Cost | Where to Buy |
|-------|-------|----------------|--------------|
| Polygon | MATIC | ~$0.50 | Binance, Coinbase |
| Ethereum | ETH | ~$50-100 | Binance, Coinbase |
| Base | ETH | ~$1-5 | Bridge from Ethereum |
| BSC | BNB | ~$0.50 | Binance |
| Arbitrum | ETH | ~$1-5 | Bridge from Ethereum |
| Avalanche | AVAX | ~$1-2 | Binance, Coinbase |

**Check your balance:**
```bash
# For Polygon Amoy testnet
npx hardhat run scripts/check-balance.js --network polygonAmoy
```

---

## Step 4: Deploy to Testnets (Recommended First)

Start with testnets to test the deployment process:

### A. Deploy to Polygon Amoy (Testnet)

```bash
cd contracts
npx hardhat run scripts/deploy.js --network polygonAmoy
```

Expected output:
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

Adding supported token: USDC (0x8B0180f2101c8260d49339abfEe87927412494B4)
✅ USDC added
Adding supported token: USDT (0xcab2F429509bFe666d5524D7268EBee24f55B089)
✅ USDT added

============================================================
DEPLOYMENT COMPLETE
============================================================

Add to your .env file:
SUBSCRIPTION_CONTRACT_POLYGON=0xABC123...
```

**Copy the proxy address and add it to your `.env` file!**

### B. Deploy to Other Testnets

```bash
# Ethereum Sepolia
npx hardhat run scripts/deploy.js --network sepolia

# Base Sepolia
npx hardhat run scripts/deploy.js --network baseSepolia

# BSC Testnet
npx hardhat run scripts/deploy.js --network bscTestnet

# Arbitrum Sepolia
npx hardhat run scripts/deploy.js --network arbitrumSepolia

# Avalanche Fuji
npx hardhat run scripts/deploy.js --network fuji
```

After each deployment, update `.env` with the proxy address.

---

## Step 5: Update .env File

After deploying to testnets, your `.env` should look like:

```bash
# Testnet contracts (for testing)
SUBSCRIPTION_CONTRACT_POLYGON=0xYourPolygonTestnetAddress
SUBSCRIPTION_CONTRACT_ETHEREUM=0xYourEthereumTestnetAddress
SUBSCRIPTION_CONTRACT_BASE=0xYourBaseTestnetAddress
SUBSCRIPTION_CONTRACT_BSC=0xYourBSCTestnetAddress
SUBSCRIPTION_CONTRACT_ARBITRUM=0xYourArbitrumTestnetAddress
SUBSCRIPTION_CONTRACT_AVALANCHE=0xYourAvalancheTestnetAddress
```

---

## Step 6: Test the Contracts

Before deploying to mainnet, test on testnets:

```bash
# Start your API server
cd ..
python app/main.py
```

In another terminal:
```bash
# Create a test merchant and subscription
curl -X POST http://localhost:8000/subscriptions/create \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "chain": "polygon",
    "token": "USDC",
    "amount": "10.00",
    "interval": "monthly"
  }'
```

---

## Step 7: Deploy to Mainnets (Production)

**⚠️ WARNING: This costs real money! Make sure you have gas tokens.**

### A. Update .env for Mainnet

```bash
# Set to mainnet mode
USE_MAINNET=true
```

### B. Deploy to Mainnets

```bash
cd contracts

# Polygon Mainnet (~$0.50)
npx hardhat run scripts/deploy.js --network polygon

# Base Mainnet (~$1-5)
npx hardhat run scripts/deploy.js --network base

# BSC Mainnet (~$0.50)
npx hardhat run scripts/deploy.js --network bsc

# Arbitrum Mainnet (~$1-5)
npx hardhat run scripts/deploy.js --network arbitrum

# Avalanche Mainnet (~$1-2)
npx hardhat run scripts/deploy.js --network avalanche

# Ethereum Mainnet (~$50-100) - Deploy last, most expensive
npx hardhat run scripts/deploy.js --network ethereum
```

### C. Update .env with Mainnet Addresses

```bash
# Mainnet contracts (for production)
SUBSCRIPTION_CONTRACT_POLYGON=0xYourPolygonMainnetAddress
SUBSCRIPTION_CONTRACT_ETHEREUM=0xYourEthereumMainnetAddress
SUBSCRIPTION_CONTRACT_BASE=0xYourBaseMainnetAddress
SUBSCRIPTION_CONTRACT_BSC=0xYourBSCMainnetAddress
SUBSCRIPTION_CONTRACT_ARBITRUM=0xYourArbitrumMainnetAddress
SUBSCRIPTION_CONTRACT_AVALANCHE=0xYourAvalancheMainnetAddress
```

---

## Step 8: Verify Contracts (Optional but Recommended)

Verify your contracts on block explorers for transparency:

### Get API Keys

1. **Etherscan** (Ethereum, Sepolia): https://etherscan.io/apis
2. **Polygonscan** (Polygon): https://polygonscan.com/apis
3. **Basescan** (Base): https://basescan.org/apis
4. **BscScan** (BSC): https://bscscan.com/apis
5. **Arbiscan** (Arbitrum): https://arbiscan.io/apis
6. **Snowtrace** (Avalanche): https://snowtrace.io/apis

Add to `.env`:
```bash
ETHERSCAN_API_KEY=your_etherscan_key
POLYGONSCAN_API_KEY=your_polygonscan_key
BASESCAN_API_KEY=your_basescan_key
BSCSCAN_API_KEY=your_bscscan_key
ARBISCAN_API_KEY=your_arbiscan_key
SNOWTRACE_API_KEY=your_snowtrace_key
```

### Verify Contracts

```bash
# Polygon
npx hardhat verify --network polygon 0xYourProxyAddress

# Ethereum
npx hardhat verify --network ethereum 0xYourProxyAddress

# Base
npx hardhat verify --network base 0xYourProxyAddress

# BSC
npx hardhat verify --network bsc 0xYourProxyAddress

# Arbitrum
npx hardhat verify --network arbitrum 0xYourProxyAddress

# Avalanche
npx hardhat verify --network avalanche 0xYourProxyAddress
```

---

## Step 9: Configure Contracts

After deployment, you need to configure each contract:

### A. Set Relayer Address (if different from deployer)

If you want a different address to execute subscriptions:

```bash
# Using Hardhat console
npx hardhat console --network polygon

# In console:
const contract = await ethers.getContractAt("DariSubscriptions", "0xYourProxyAddress");
await contract.setRelayer("0xYourRelayerAddress");
```

### B. Verify Token Whitelist

Check that USDC and USDT are whitelisted:

```bash
npx hardhat console --network polygon

# In console:
const contract = await ethers.getContractAt("DariSubscriptions", "0xYourProxyAddress");
const usdcSupported = await contract.supportedTokens("0xUSDCAddress");
console.log("USDC supported:", usdcSupported);
```

---

## Step 10: Test Production Deployment

Before going live, test with small amounts:

```bash
# Create a test subscription on mainnet
curl -X POST https://api.daripay.xyz/subscriptions/create \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "chain": "polygon",
    "token": "USDC",
    "amount": "1.00",
    "interval": "monthly"
  }'
```

---

## Troubleshooting

### Error: "insufficient funds for gas"

**Solution:** Fund your relayer wallet with more gas tokens.

```bash
# Check balance
npx hardhat run scripts/check-balance.js --network polygon
```

### Error: "nonce too low"

**Solution:** Reset your nonce or wait a few minutes.

```bash
# Clear Hardhat cache
rm -rf contracts/cache contracts/artifacts
npx hardhat clean
```

### Error: "network does not support ENS"

**Solution:** This is a warning, not an error. Deployment should still work.

### Error: "contract verification failed"

**Solution:** Make sure you're verifying the proxy address, not the implementation address.

### Deployment is very slow

**Solution:** Use a private RPC endpoint (Alchemy, Infura, QuickNode) instead of public RPCs.

---

## Cost Summary

### Testnet Deployments (Free)
- All testnets: $0 (use faucets)

### Mainnet Deployments (Estimated)
- Polygon: ~$0.50
- Base: ~$1-5
- BSC: ~$0.50
- Arbitrum: ~$1-5
- Avalanche: ~$1-2
- Ethereum: ~$50-100

**Total estimated cost: $55-115**

**Recommendation:** Start with Polygon, Base, and BSC (cheapest). Add Ethereum later if needed.

---

## Quick Reference Commands

```bash
# Install dependencies
cd contracts && npm install

# Check deployer address
node -e "const ethers = require('ethers'); const wallet = new ethers.Wallet('YOUR_PRIVATE_KEY'); console.log(wallet.address);"

# Deploy to testnet
npx hardhat run scripts/deploy.js --network polygonAmoy

# Deploy to mainnet
npx hardhat run scripts/deploy.js --network polygon

# Verify contract
npx hardhat verify --network polygon 0xProxyAddress

# Check contract
npx hardhat console --network polygon
```

---

## Final Checklist

Before going live:

- [ ] Contracts deployed to all desired chains
- [ ] Contract addresses added to `.env`
- [ ] Contracts verified on block explorers
- [ ] Relayer address configured
- [ ] USDC/USDT whitelisted
- [ ] Test subscription created and executed
- [ ] Monitoring set up
- [ ] Backup of `.env` file created

---

## Next Steps

After deploying contracts:

1. Start your API server: `python app/main.py`
2. Start blockchain listeners: `python run_listeners.py`
3. Create test merchant account
4. Test payment flow end-to-end
5. Monitor for 24 hours before full launch

---

## Support

If you encounter issues:

1. Check the troubleshooting section above
2. Review Hardhat logs: `contracts/hardhat.log`
3. Check block explorer for transaction status
4. Verify gas prices aren't too high
5. Try deploying to testnet first

**You're ready to deploy! Start with testnets, then move to mainnets.** 🚀
