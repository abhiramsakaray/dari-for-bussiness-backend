#!/bin/bash

# Deploy DariSubscriptions to all testnets
# Usage: bash deploy-all-testnets.sh

echo "============================================================"
echo "Deploying DariSubscriptions to All Testnets"
echo "============================================================"
echo ""

cd contracts

# Array of testnet networks
networks=("polygonAmoy" "sepolia" "baseSepolia" "bscTestnet" "arbitrumSepolia" "fuji")

# Deploy to each network
for network in "${networks[@]}"
do
    echo ""
    echo "------------------------------------------------------------"
    echo "Deploying to $network..."
    echo "------------------------------------------------------------"
    
    # Check balance first
    echo "Checking balance..."
    npx hardhat run scripts/check-balance.js --network $network
    
    echo ""
    read -p "Continue with deployment to $network? (y/n) " -n 1 -r
    echo ""
    
    if [[ $REPLY =~ ^[Yy]$ ]]
    then
        npx hardhat run scripts/deploy.js --network $network
        
        if [ $? -eq 0 ]; then
            echo "✅ Successfully deployed to $network"
        else
            echo "❌ Failed to deploy to $network"
            read -p "Continue with next network? (y/n) " -n 1 -r
            echo ""
            if [[ ! $REPLY =~ ^[Yy]$ ]]
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
echo "Deployment Complete!"
echo "============================================================"
echo ""
echo "Next steps:"
echo "1. Update .env with contract addresses"
echo "2. Test subscriptions on testnets"
echo "3. Deploy to mainnets when ready"
echo ""
