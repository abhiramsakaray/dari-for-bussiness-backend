require("@nomicfoundation/hardhat-toolbox");
require("@openzeppelin/hardhat-upgrades");
require("dotenv").config({ path: "../.env" });

const DEPLOYER_PRIVATE_KEY = process.env.RELAYER_PRIVATE_KEY || "0x0000000000000000000000000000000000000000000000000000000000000001";

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
    solidity: {
        version: "0.8.24",
        settings: {
            optimizer: {
                enabled: true,
                runs: 200,
            },
            viaIR: true,
        },
    },
    networks: {
        hardhat: {
            chainId: 31337,
        },
        // ========= TESTNETS =========
        sepolia: {
            url: process.env.ETHEREUM_TESTNET_RPC_URL || "https://rpc.sepolia.org",
            chainId: 11155111,
            accounts: [DEPLOYER_PRIVATE_KEY],
        },
        polygonAmoy: {
            url: process.env.POLYGON_TESTNET_RPC_URL || "https://rpc-amoy.polygon.technology",
            chainId: 80002,
            accounts: [DEPLOYER_PRIVATE_KEY],
        },
        baseSepolia: {
            url: process.env.BASE_TESTNET_RPC_URL || "https://sepolia.base.org",
            chainId: 84532,
            accounts: [DEPLOYER_PRIVATE_KEY],
        },
        // ========= MAINNETS =========
        ethereum: {
            url: process.env.ETHEREUM_MAINNET_RPC_URL || "https://eth.llamarpc.com",
            chainId: 1,
            accounts: [DEPLOYER_PRIVATE_KEY],
        },
        polygon: {
            url: process.env.POLYGON_MAINNET_RPC_URL || "https://polygon-rpc.com",
            chainId: 137,
            accounts: [DEPLOYER_PRIVATE_KEY],
        },
        base: {
            url: process.env.BASE_MAINNET_RPC_URL || "https://mainnet.base.org",
            chainId: 8453,
            accounts: [DEPLOYER_PRIVATE_KEY],
        },
        arbitrum: {
            url: process.env.ARBITRUM_MAINNET_RPC_URL || "https://arb1.arbitrum.io/rpc",
            chainId: 42161,
            accounts: [DEPLOYER_PRIVATE_KEY],
        },
        bsc: {
            url: process.env.BSC_MAINNET_RPC_URL || "https://bsc-dataseed.bnbchain.org",
            chainId: 56,
            accounts: [DEPLOYER_PRIVATE_KEY],
        },
        bscTestnet: {
            url: process.env.BSC_TESTNET_RPC_URL || "https://data-seed-prebsc-1-s1.bnbchain.org:8545",
            chainId: 97,
            accounts: [DEPLOYER_PRIVATE_KEY],
        },
        arbitrumSepolia: {
            url: process.env.ARBITRUM_TESTNET_RPC_URL || "https://sepolia-rollup.arbitrum.io/rpc",
            chainId: 421614,
            accounts: [DEPLOYER_PRIVATE_KEY],
        },
        // Avalanche Fuji Testnet
        fuji: {
            url: process.env.AVALANCHE_TESTNET_RPC_URL || "https://api.avax-test.network/ext/bc/C/rpc",
            chainId: 43113,
            accounts: [DEPLOYER_PRIVATE_KEY],
            gasPrice: 25000000000, // 25 gwei
        },
        // Avalanche C-Chain Mainnet
        avalanche: {
            url: process.env.AVALANCHE_MAINNET_RPC_URL || "https://api.avax.network/ext/bc/C/rpc",
            chainId: 43114,
            accounts: [DEPLOYER_PRIVATE_KEY],
            gasPrice: 25000000000, // 25 gwei
        },
    },
    etherscan: {
        apiKey: {
            mainnet: process.env.ETHERSCAN_API_KEY || "",
            polygon: process.env.POLYGONSCAN_API_KEY || "",
            base: process.env.BASESCAN_API_KEY || "",
            arbitrumOne: process.env.ARBISCAN_API_KEY || "",
            bsc: process.env.BSCSCAN_API_KEY || "",
            bscTestnet: process.env.BSCSCAN_API_KEY || "",
            sepolia: process.env.ETHERSCAN_API_KEY || "",
            polygonAmoy: process.env.POLYGONSCAN_API_KEY || "",
            baseSepolia: process.env.BASESCAN_API_KEY || "",
            avalanche: process.env.SNOWTRACE_API_KEY || "",
            avalancheFujiTestnet: process.env.SNOWTRACE_API_KEY || "",
        },
    },
    paths: {
        sources: "./src",
        tests: "./test",
        cache: "./cache",
        artifacts: "./artifacts",
    },
};
