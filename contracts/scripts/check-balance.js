// scripts/check-balance.js
// Check deployer wallet balance on any network

const { ethers } = require("hardhat");

async function main() {
    const [deployer] = await ethers.getSigners();
    const network = await ethers.provider.getNetwork();
    
    console.log("=".repeat(60));
    console.log("Wallet Balance Check");
    console.log("=".repeat(60));
    console.log(`Network:  ${network.name} (chainId: ${network.chainId})`);
    console.log(`Address:  ${deployer.address}`);
    
    const balance = await ethers.provider.getBalance(deployer.address);
    const balanceInEth = ethers.formatEther(balance);
    
    console.log(`Balance:  ${balanceInEth} ${getTokenSymbol(Number(network.chainId))}`);
    console.log("=".repeat(60));
    
    // Check if balance is sufficient for deployment
    const minBalance = getMinBalance(Number(network.chainId));
    if (parseFloat(balanceInEth) < minBalance) {
        console.log(`\n⚠️  WARNING: Balance is low!`);
        console.log(`   Recommended minimum: ${minBalance} ${getTokenSymbol(Number(network.chainId))}`);
        console.log(`   Current balance: ${balanceInEth} ${getTokenSymbol(Number(network.chainId))}`);
        console.log(`\n   Get tokens from:`);
        console.log(`   ${getFaucetUrl(Number(network.chainId))}`);
    } else {
        console.log(`\n✅ Balance is sufficient for deployment`);
    }
}

function getTokenSymbol(chainId) {
    const symbols = {
        1: "ETH",
        11155111: "ETH",
        137: "MATIC",
        80002: "MATIC",
        8453: "ETH",
        84532: "ETH",
        42161: "ETH",
        421614: "ETH",
        56: "BNB",
        97: "BNB",
        43114: "AVAX",
        43113: "AVAX",
        31337: "ETH",
    };
    return symbols[chainId] || "ETH";
}

function getMinBalance(chainId) {
    // Minimum balance needed for deployment (in native token)
    const minimums = {
        1: 0.05,        // Ethereum mainnet
        11155111: 0.05, // Sepolia
        137: 0.5,       // Polygon mainnet
        80002: 0.5,     // Polygon Amoy
        8453: 0.01,     // Base mainnet
        84532: 0.01,    // Base Sepolia
        42161: 0.01,    // Arbitrum mainnet
        421614: 0.01,   // Arbitrum Sepolia
        56: 0.05,       // BSC mainnet
        97: 0.5,        // BSC testnet
        43114: 0.5,     // Avalanche mainnet
        43113: 1.0,     // Avalanche Fuji
        31337: 0,       // Hardhat
    };
    return minimums[chainId] || 0.01;
}

function getFaucetUrl(chainId) {
    const faucets = {
        11155111: "https://sepoliafaucet.com/",
        80002: "https://faucet.polygon.technology/",
        84532: "https://www.coinbase.com/faucets/base-ethereum-goerli-faucet",
        421614: "https://faucet.quicknode.com/arbitrum/sepolia",
        97: "https://testnet.bnbchain.org/faucet-smart",
        43113: "https://faucet.avax.network/",
    };
    return faucets[chainId] || "N/A (mainnet - buy tokens on exchange)";
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error(error);
        process.exit(1);
    });
