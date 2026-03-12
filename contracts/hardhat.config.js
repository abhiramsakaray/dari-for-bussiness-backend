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
            url: "https://arb1.arbitrum.io/rpc",
            chainId: 42161,
            accounts: [DEPLOYER_PRIVATE_KEY],
        },
    },
    etherscan: {
        apiKey: {
            mainnet: process.env.ETHERSCAN_API_KEY || "",
            polygon: process.env.POLYGONSCAN_API_KEY || "",
            base: process.env.BASESCAN_API_KEY || "",
            arbitrumOne: process.env.ARBISCAN_API_KEY || "",
            sepolia: process.env.ETHERSCAN_API_KEY || "",
            polygonAmoy: process.env.POLYGONSCAN_API_KEY || "",
            baseSepolia: process.env.BASESCAN_API_KEY || "",
        },
    },
    paths: {
        sources: "./src",
        tests: "./test",
        cache: "./cache",
        artifacts: "./artifacts",
    },
};
