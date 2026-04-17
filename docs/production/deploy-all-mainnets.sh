#!/bin/bash

# Deploy DariSubscriptions to all mainnets
# Usage: bash deploy-all-mainnets.sh
# WARNING: This costs real money!

echo "============================================================"
echo "⚠️  WARNING: MAINNET DEPLOYMENT - THIS COSTS REAL MONEY!"
echo "============================================================"
echo ""
echo "Estimated costs:"
echo "  - Polygon:   ~\$0.50"
echo "  - Base:      ~\$1-5"
echo "  - BSC:       ~\$0.50"
echo "  - Arbitrum:  ~\$1-5"
echo "  - Avalanche: ~\$1-2"
echo "  - Ethereum:  ~\$50-100"
echo ""
echo "Total: ~\$55-115"
echo ""

read -p "Are you sure you want to continue? (yes/no) " -r
echo ""

if [[ ! $REPLY == "yes" ]]
then
    echo "Deployment cancelled."
    exit 0
fi

cd contracts

# Array of mainnet networks (cheapest first)
networks=("polygon" "bsc" "avalanche" "base" "arbitrum" "ethereum")

# Deploy to each network
for network in "${networks[@]}"
do
    echo ""
    echo "------------------------------------------------------------"
    echo "Deploying to $network MAINNET..."
    echo "------------------------------------------------------------"
    
    # Check balance first
    echo "Checking balance..."
    npx hardhat run scripts/check-balance.js --network $network
    
    echo ""
    read -p "Continue with deployment to $network MAINNET? (yes/no) " -r
    echo ""
    
    if [[ $REPLY == "yes" ]]
    then
        npx hardhat run scripts/deploy.js --network $network
        
        if [ $? -eq 0 ]; then
            echo "✅ Successfully deployed to $network"
            echo ""
            echo "⚠️  IMPORTANT: Copy the contract address and add it to .env!"
            echo ""
            read -p "Press Enter to continue to next network..."
        else
            echo "❌ Failed to deploy to $network"
            read -p "Continue with next network? (yes/no) " -r
            echo ""
            if [[ ! $REPLY == "yes" ]]
            then
                exit 1
            fi
        fi
    else
        echo "⏩ Skipping $network"
    fi
    
    echo ""
done

cd ..

echo ""
echo "============================================================"
echo "Mainnet Deployment Complete!"
echo "============================================================"
echo ""
echo "Next steps:"
echo "1. Update .env with mainnet contract addresses"
echo "2. Set USE_MAINNET=true in .env"
echo "3. Verify contracts on block explorers"
echo "4. Test with small amounts first"
echo "5. Monitor for 24 hours before full launch"
echo ""
