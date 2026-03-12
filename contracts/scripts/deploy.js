// scripts/deploy.js
// Deploy DariSubscriptions as UUPS proxy to any configured network
//
// Usage:
//   npx hardhat run scripts/deploy.js --network polygonAmoy
//   npx hardhat run scripts/deploy.js --network polygon

const { ethers, upgrades } = require("hardhat");

async function main() {
    const [deployer] = await ethers.getSigners();
    const network = await ethers.provider.getNetwork();

    console.log("=".repeat(60));
    console.log("Dari for Business - Subscription Contract Deployment");
    console.log("=".repeat(60));
    console.log(`Network:  ${network.name} (chainId: ${network.chainId})`);
    console.log(`Deployer: ${deployer.address}`);

    const balance = await ethers.provider.getBalance(deployer.address);
    console.log(`Balance:  ${ethers.formatEther(balance)} ETH/MATIC`);
    console.log("=".repeat(60));

    // Deploy as UUPS proxy
    console.log("\nDeploying DariSubscriptions (UUPS proxy)...");
    const DariSubscriptions = await ethers.getContractFactory("DariSubscriptions");

    const proxy = await upgrades.deployProxy(
        DariSubscriptions,
        [deployer.address, deployer.address], // owner = deployer, relayer = deployer (update later)
        {
            kind: "uups",
            initializer: "initialize",
        }
    );

    await proxy.waitForDeployment();
    const proxyAddress = await proxy.getAddress();
    const implAddress = await upgrades.erc1967.getImplementationAddress(proxyAddress);

    console.log(`\n✅ Proxy deployed to:          ${proxyAddress}`);
    console.log(`✅ Implementation deployed to:  ${implAddress}`);

    // Add common stablecoin addresses as supported tokens
    const tokenAddresses = getTokenAddresses(Number(network.chainId));

    for (const [symbol, address] of Object.entries(tokenAddresses)) {
        if (address) {
            console.log(`\nAdding supported token: ${symbol} (${address})`);
            const tx = await proxy.addSupportedToken(address);
            await tx.wait();
            console.log(`✅ ${symbol} added`);
        }
    }

    console.log("\n" + "=".repeat(60));
    console.log("DEPLOYMENT COMPLETE");
    console.log("=".repeat(60));
    console.log(`\nAdd to your .env file:`);
    console.log(`SUBSCRIPTION_CONTRACT_${getChainEnvName(Number(network.chainId))}=${proxyAddress}`);
    console.log("");
}

function getTokenAddresses(chainId) {
    const tokens = {
        // Ethereum Mainnet
        1: {
            USDC: "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            USDT: "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        },
        // Sepolia testnet
        11155111: {
            USDC: "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238",
            USDT: "0x7169D38820dfd117C3FA1f22a697dBA58d90BA06",
        },
        // Polygon Mainnet
        137: {
            USDC: "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
            USDT: "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
        },
        // Polygon Amoy testnet
        80002: {
            USDC: "0x8B0180f2101c8260d49339abfEe87927412494B4",
            USDT: "0xcab2F429509bFe666d5524D7268EBee24f55B089",
        },
        // Base Mainnet
        8453: {
            USDC: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        },
        // Base Sepolia
        84532: {
            USDC: "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        },
        // Arbitrum One
        42161: {
            USDC: "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
            USDT: "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
        },
        // Hardhat
        31337: {},
    };
    return tokens[chainId] || {};
}

function getChainEnvName(chainId) {
    const names = {
        1: "ETHEREUM",
        11155111: "ETHEREUM",
        137: "POLYGON",
        80002: "POLYGON",
        8453: "BASE",
        84532: "BASE",
        42161: "ARBITRUM",
        31337: "LOCAL",
    };
    return names[chainId] || "UNKNOWN";
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error(error);
        process.exit(1);
    });
