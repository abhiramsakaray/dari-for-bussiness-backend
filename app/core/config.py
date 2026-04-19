from pydantic_settings import BaseSettings
from pydantic import model_validator, Field
from typing import List, Optional
import logging

_config_logger = logging.getLogger(__name__)

# Known weak/default secrets that MUST be changed
_WEAK_JWT_SECRETS = {
    "your-secret-key-change-this-in-production-minimum-32-characters-long",
    "change-me",
    "secret",
    "jwt-secret",
    "your-secret-key",
}

_WEAK_ADMIN_PASSWORDS = {
    "change-this-password",
    "change-this-password-immediately",
    "admin",
    "password",
    "admin123",
}


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Dari for Business"
    APP_VERSION: str = "2.2.0"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    APP_BASE_URL: str = "http://localhost:8000"
    APP_URL: str = "http://localhost:8000"  # Alias for APP_BASE_URL
    CORS_ORIGINS: str = "*"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "dari_payments.log"
    
    # Database
    DATABASE_URL: str = "sqlite:///./payment_gateway.db"
    
    # JWT
    JWT_SECRET: str = Field(..., min_length=32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    
    # API Keys
    API_KEY_SECRET: str = "your-api-key-secret-change-in-production"
    
    # PII Encryption (GDPR compliance — Fernet key, 32+ chars)
    PII_ENCRYPTION_KEY: str = ""
    
    # Payment Settings
    PAYMENT_EXPIRY_MINUTES: int = 15  # Payment timeout from when user starts (opens checkout page)
    WEBHOOK_RETRY_LIMIT: int = 3
    WEBHOOK_TIMEOUT_SECONDS: int = 10
    
    # Admin
    ADMIN_EMAIL: str = "admin@dari.in"
    ADMIN_PASSWORD: str = "change-this-password"
    
    # ============= NETWORK MODE =============
    USE_MAINNET: bool = False
    
    # ============= STELLAR NETWORK =============
    STELLAR_ENABLED: bool = True
    USDC_ASSET_CODE: str = "USDC"
    
    # Testnet
    STELLAR_TESTNET_NETWORK: str = "testnet"
    STELLAR_TESTNET_HORIZON_URL: str = "https://horizon-testnet.stellar.org"
    STELLAR_TESTNET_USDC_ISSUER: str = "GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5"
    
    # Mainnet
    STELLAR_MAINNET_NETWORK: str = "public"
    STELLAR_MAINNET_HORIZON_URL: str = "https://horizon.stellar.org"
    STELLAR_MAINNET_USDC_ISSUER: str = "GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN"
    
    # Active (resolved by model_validator)
    STELLAR_NETWORK: str = ""
    STELLAR_HORIZON_URL: str = ""
    USDC_ASSET_ISSUER: str = ""
    
    # Soroban Smart Contracts (Optional)
    SOROBAN_RPC_URL: str = "https://soroban-testnet.stellar.org"
    SOROBAN_ESCROW_CONTRACT_ID: str = ""
    SOROBAN_USDC_CONTRACT_ID: str = ""
    PAYMENT_VALIDATOR_CONTRACT_ID: str = ""
    BACKEND_SECRET_KEY: str = ""
    
    # ============= ETHEREUM =============
    ETHEREUM_ENABLED: bool = True
    ETHEREUM_CONFIRMATIONS: int = 12
    
    # Testnet (Sepolia)
    ETHEREUM_TESTNET_RPC_URL: str = "https://rpc.sepolia.org"
    ETHEREUM_TESTNET_CHAIN_ID: int = 11155111
    ETHEREUM_TESTNET_USDC_ADDRESS: str = "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238"
    ETHEREUM_TESTNET_USDT_ADDRESS: str = "0x7169D38820dfd117C3FA1f22a697dBA58d90BA06"
    ETHEREUM_TESTNET_PYUSD_ADDRESS: str = "0xCaC524BcA292aaade2DF8A05cC58F0a65B1B3bB9"
    
    # Mainnet
    ETHEREUM_MAINNET_RPC_URL: str = "https://eth.llamarpc.com"
    ETHEREUM_MAINNET_CHAIN_ID: int = 1
    ETHEREUM_MAINNET_USDC_ADDRESS: str = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    ETHEREUM_MAINNET_USDT_ADDRESS: str = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
    ETHEREUM_MAINNET_PYUSD_ADDRESS: str = "0x6c3ea9036406852006290770BEdFcAbA0e23A0e8"
    
    # Active (resolved by model_validator)
    ETHEREUM_RPC_URL: str = ""
    ETHEREUM_CHAIN_ID: int = 0
    ETHEREUM_USDC_ADDRESS: str = ""
    ETHEREUM_USDT_ADDRESS: str = ""
    ETHEREUM_PYUSD_ADDRESS: str = ""
    
    # ============= POLYGON =============
    POLYGON_ENABLED: bool = True
    POLYGON_CONFIRMATIONS: int = 64
    
    # Testnet (Amoy)
    POLYGON_TESTNET_RPC_URL: str = "https://rpc-amoy.polygon.technology"
    POLYGON_TESTNET_CHAIN_ID: int = 80002
    POLYGON_TESTNET_USDC_ADDRESS: str = "0x8B0180f2101c8260d49339abfEe87927412494B4"
    POLYGON_TESTNET_USDT_ADDRESS: str = "0xcab2F429509bFe666d5524D7268EBee24f55B089"
    
    # Mainnet
    POLYGON_MAINNET_RPC_URL: str = "https://polygon-rpc.com"
    POLYGON_MAINNET_CHAIN_ID: int = 137
    POLYGON_MAINNET_USDC_ADDRESS: str = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
    POLYGON_MAINNET_USDT_ADDRESS: str = "0xc2132D05D31c914a87C6611C10748AEb04B58e8F"
    
    # Active (resolved by model_validator)
    POLYGON_RPC_URL: str = ""
    POLYGON_CHAIN_ID: int = 0
    POLYGON_USDC_ADDRESS: str = ""
    POLYGON_USDT_ADDRESS: str = ""
    
    # ============= BASE =============
    BASE_ENABLED: bool = True
    BASE_CONFIRMATIONS: int = 12
    
    # Testnet (Base Sepolia)
    BASE_TESTNET_RPC_URL: str = "https://sepolia.base.org"
    BASE_TESTNET_CHAIN_ID: int = 84532
    BASE_TESTNET_USDC_ADDRESS: str = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
    
    # Mainnet
    BASE_MAINNET_RPC_URL: str = "https://mainnet.base.org"
    BASE_MAINNET_CHAIN_ID: int = 8453
    BASE_MAINNET_USDC_ADDRESS: str = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    
    # Active (resolved by model_validator)
    BASE_RPC_URL: str = ""
    BASE_CHAIN_ID: int = 0
    BASE_USDC_ADDRESS: str = ""
    
    # ============= BSC (BNB Smart Chain) =============
    BSC_ENABLED: bool = True
    BSC_CONFIRMATIONS: int = 15
    
    # Testnet (BSC Testnet)
    BSC_TESTNET_RPC_URL: str = "https://data-seed-prebsc-1-s1.bnbchain.org:8545"
    BSC_TESTNET_CHAIN_ID: int = 97
    BSC_TESTNET_USDC_ADDRESS: str = "0x64544969ed7EBf5f083679233325356EbE738930"
    BSC_TESTNET_USDT_ADDRESS: str = "0x337610d27c682E347C9cD60BD4b3b107C9d34dDd"
    
    # Mainnet
    BSC_MAINNET_RPC_URL: str = "https://bsc-dataseed.bnbchain.org"
    BSC_MAINNET_CHAIN_ID: int = 56
    BSC_MAINNET_USDC_ADDRESS: str = "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"
    BSC_MAINNET_USDT_ADDRESS: str = "0x55d398326f99059fF775485246999027B3197955"
    
    # Active (resolved by model_validator)
    BSC_RPC_URL: str = ""
    BSC_CHAIN_ID: int = 0
    BSC_USDC_ADDRESS: str = ""
    BSC_USDT_ADDRESS: str = ""
    
    # ============= ARBITRUM =============
    ARBITRUM_ENABLED: bool = True
    ARBITRUM_CONFIRMATIONS: int = 12
    
    # Testnet (Arbitrum Sepolia)
    ARBITRUM_TESTNET_RPC_URL: str = "https://sepolia-rollup.arbitrum.io/rpc"
    ARBITRUM_TESTNET_CHAIN_ID: int = 421614
    ARBITRUM_TESTNET_USDC_ADDRESS: str = "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d"
    ARBITRUM_TESTNET_USDT_ADDRESS: str = "0x3870546cfd600ba87e4726f7B8e3B8bB7E5EE262"
    
    # Mainnet
    ARBITRUM_MAINNET_RPC_URL: str = "https://arb1.arbitrum.io/rpc"
    ARBITRUM_MAINNET_CHAIN_ID: int = 42161
    ARBITRUM_MAINNET_USDC_ADDRESS: str = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
    ARBITRUM_MAINNET_USDT_ADDRESS: str = "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9"
    
    # Active (resolved by model_validator)
    ARBITRUM_RPC_URL: str = ""
    ARBITRUM_CHAIN_ID: int = 0
    ARBITRUM_USDC_ADDRESS: str = ""
    ARBITRUM_USDT_ADDRESS: str = ""
    
    # ============= AVALANCHE C-CHAIN =============
    AVALANCHE_ENABLED: bool = True
    AVALANCHE_CONFIRMATIONS: int = 12
    
    # Testnet (Fuji)
    AVALANCHE_TESTNET_RPC_URL: str = "https://api.avax-test.network/ext/bc/C/rpc"
    AVALANCHE_TESTNET_CHAIN_ID: int = 43113
    AVALANCHE_TESTNET_USDC_ADDRESS: str = "0x5425890298aed601595a70AB815c96711a31Bc65"
    AVALANCHE_TESTNET_USDT_ADDRESS: str = "0xAb231A5744C8E6c45481754928cCfFFFD4aa0732"
    
    # Mainnet
    AVALANCHE_MAINNET_RPC_URL: str = "https://api.avax.network/ext/bc/C/rpc"
    AVALANCHE_MAINNET_CHAIN_ID: int = 43114
    AVALANCHE_MAINNET_USDC_ADDRESS: str = "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E"
    AVALANCHE_MAINNET_USDT_ADDRESS: str = "0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7"
    
    # Active (resolved by model_validator)
    AVALANCHE_RPC_URL: str = ""
    AVALANCHE_CHAIN_ID: int = 0
    AVALANCHE_USDC_ADDRESS: str = ""
    AVALANCHE_USDT_ADDRESS: str = ""
    
    # ============= TRON NETWORK =============
    TRON_ENABLED: bool = True
    TRON_API_KEY: Optional[str] = None
    TRON_CONFIRMATIONS: int = 19
    
    # Testnet (Nile)
    TRON_TESTNET_API_URL: str = "https://nile.trongrid.io"
    TRON_TESTNET_USDT_ADDRESS: str = "TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj"
    TRON_TESTNET_USDC_ADDRESS: str = "TSdZwNqpHofzP6BsBKGQUWdBeJphLmF6id"
    
    # Mainnet
    TRON_MAINNET_API_URL: str = "https://api.trongrid.io"
    TRON_MAINNET_USDT_ADDRESS: str = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    TRON_MAINNET_USDC_ADDRESS: str = "TEkxiTehnzSmSe2XqrBj4w32RUN966rdz8"
    
    # Active (resolved by model_validator)
    TRON_API_URL: str = ""
    TRON_USDT_ADDRESS: str = ""
    TRON_USDC_ADDRESS: str = ""
    
    # ============= SOLANA NETWORK =============
    SOLANA_ENABLED: bool = False
    
    # Testnet (Devnet)
    SOLANA_TESTNET_RPC_URL: str = "https://api.devnet.solana.com"
    SOLANA_TESTNET_USDC_MINT: str = "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU"
    SOLANA_TESTNET_USDT_MINT: str = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
    
    # Mainnet
    SOLANA_MAINNET_RPC_URL: str = "https://api.mainnet-beta.solana.com"
    SOLANA_MAINNET_USDC_MINT: str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    SOLANA_MAINNET_USDT_MINT: str = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
    
    # Active (resolved by model_validator)
    SOLANA_RPC_URL: str = ""
    SOLANA_USDC_MINT: str = ""
    SOLANA_USDT_MINT: str = ""
    
    # ============= HD WALLET (for deposit address generation) =============
    HD_WALLET_MNEMONIC: Optional[str] = None  # BIP39 mnemonic for HD wallet
    HD_WALLET_DERIVATION_PATH: str = "m/44'/60'/0'/0"
    
    # ============= RATE LIMITING =============
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 100  # requests per window
    RATE_LIMIT_WINDOW: int = 60  # seconds
    RATE_LIMIT_PER_MINUTE: int = 60  # Legacy compatibility
    
    # ============= GOOGLE OAUTH =============
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/google/callback"
    
    # ============= PRICE FEEDS =============
    COINGECKO_API_URL: str = "https://api.coingecko.com/api/v3"
    
    # ============= WEBHOOK SECURITY =============
    WEBHOOK_SIGNING_SECRET: Optional[str] = None
    WEBHOOK_HMAC_ALGO: str = "sha256"
    
    # ============= REDIS =============
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_TOKEN_DB: int = 1
    REDIS_ENABLED: bool = False  # Graceful fallback to in-memory when False
    
    # ============= FX RATE PROVIDERS (priority order) =============
    FX_PRIMARY_PROVIDER: str = "exchangerate-api"  # exchangerate-api, openexchangerates, fixer
    OPENEXCHANGERATES_APP_ID: str = ""
    FIXER_API_KEY: str = ""
    
    # ============= AML / COMPLIANCE =============
    AML_ENABLED: bool = True
    AML_THRESHOLD_USD: float = 10000.0  # CTR threshold
    AML_HIGH_RISK_THRESHOLD_USD: float = 3000.0  # Enhanced due diligence
    
    # ============= MONITORING =============
    PROMETHEUS_ENABLED: bool = True
    STRUCTURED_LOGGING: bool = True
    
    # ============= WEB3 SUBSCRIPTIONS =============
    # EVM Gasless Relayer
    RELAYER_PRIVATE_KEY: str = ""
    RELAYER_MAX_GAS_PRICE_GWEI: int = 100
    
    # EVM Subscription Contract Addresses (set per chain after deployment)
    SUBSCRIPTION_CONTRACT_ETHEREUM: str = ""
    SUBSCRIPTION_CONTRACT_POLYGON: str = ""
    SUBSCRIPTION_CONTRACT_BASE: str = ""
    SUBSCRIPTION_CONTRACT_BSC: str = ""
    SUBSCRIPTION_CONTRACT_ARBITRUM: str = ""
    SUBSCRIPTION_CONTRACT_AVALANCHE: str = ""
    
    # Tron Subscription Relayer
    TRON_RELAYER_PRIVATE_KEY: str = ""
    SUBSCRIPTION_CONTRACT_TRON: str = ""
    
    # Solana Subscription Relayer
    SOLANA_RELAYER_PRIVATE_KEY: str = ""  # 64-byte keypair as hex
    SUBSCRIPTION_PROGRAM_SOLANA: str = ""
    
    # Soroban (Stellar) Subscription Relayer
    SOROBAN_RELAYER_SECRET_KEY: str = ""  # Stellar secret key (S...)
    SUBSCRIPTION_CONTRACT_SOROBAN: str = ""
    
    # Scheduler
    SCHEDULER_INTERVAL_SECONDS: int = 60
    SCHEDULER_BATCH_SIZE: int = 100
    SCHEDULER_MAX_RETRIES: int = 6
    SCHEDULER_RETRY_INTERVAL_HOURS: int = 12
    
    # Enable/disable Web3 subscription scheduler
    WEB3_SUBSCRIPTIONS_ENABLED: bool = False
    
    # Refund Scheduler Settings
    REFUND_SCHEDULER_ENABLED: bool = True
    REFUND_SCHEDULER_INTERVAL_MINUTES: int = 60  # Process pending refunds every 60 minutes
    
    # ============= BLOCKCHAIN RELAYERS (Real Refund Processing) =============
    # Polygon Relayer (EVM refunds)
    POLYGON_RELAYER_URL: str = ""  # https://relayer.example.com
    POLYGON_RELAYER_API_KEY: str = ""
    
    # Stellar Relayer
    STELLAR_RELAYER_URL: str = ""  # https://stellar-relayer.example.com
    STELLAR_RELAYER_API_KEY: str = ""
    STELLAR_MERCHANT_ADDRESS: str = ""  # Merchant's Stellar address for refunds
    
    # Solana Relayer
    SOLANA_RELAYER_URL: str = ""  # https://solana-relayer.example.com
    SOLANA_RELAYER_API_KEY: str = ""
    SOLANA_MERCHANT_ADDRESS: str = ""  # Merchant's Solana pubkey for refunds
    
    # Soroban Relayer (Stellar Smart Contracts)
    SOROBAN_RELAYER_URL: str = ""  # https://soroban-relayer.example.com
    SOROBAN_RELAYER_API_KEY: str = ""
    SOROBAN_MERCHANT_ADDRESS: str = ""  # Merchant's Soroban address for refunds
    SOROBAN_USDC_CONTRACT: str = ""  # USDC contract on Soroban
    SOROBAN_USDT_CONTRACT: str = ""  # USDT contract on Soroban
    
    # TRON Relayer
    TRON_RELAYER_URL: str = ""  # https://tron-relayer.example.com
    TRON_RELAYER_API_KEY: str = ""
    TRON_MERCHANT_ADDRESS: str = ""  # Merchant's TRON address for refunds
    
    @model_validator(mode="after")
    def resolve_network_config(self):
        """Set active config fields based on USE_MAINNET toggle."""
        net = "MAINNET" if self.USE_MAINNET else "TESTNET"
        
        # Stellar
        self.STELLAR_NETWORK = getattr(self, f"STELLAR_{net}_NETWORK")
        self.STELLAR_HORIZON_URL = getattr(self, f"STELLAR_{net}_HORIZON_URL")
        self.USDC_ASSET_ISSUER = getattr(self, f"STELLAR_{net}_USDC_ISSUER")
        
        # Ethereum
        self.ETHEREUM_RPC_URL = getattr(self, f"ETHEREUM_{net}_RPC_URL")
        self.ETHEREUM_CHAIN_ID = getattr(self, f"ETHEREUM_{net}_CHAIN_ID")
        self.ETHEREUM_USDC_ADDRESS = getattr(self, f"ETHEREUM_{net}_USDC_ADDRESS")
        self.ETHEREUM_USDT_ADDRESS = getattr(self, f"ETHEREUM_{net}_USDT_ADDRESS")
        self.ETHEREUM_PYUSD_ADDRESS = getattr(self, f"ETHEREUM_{net}_PYUSD_ADDRESS")
        
        # Polygon
        self.POLYGON_RPC_URL = getattr(self, f"POLYGON_{net}_RPC_URL")
        self.POLYGON_CHAIN_ID = getattr(self, f"POLYGON_{net}_CHAIN_ID")
        self.POLYGON_USDC_ADDRESS = getattr(self, f"POLYGON_{net}_USDC_ADDRESS")
        self.POLYGON_USDT_ADDRESS = getattr(self, f"POLYGON_{net}_USDT_ADDRESS")
        
        # Base
        self.BASE_RPC_URL = getattr(self, f"BASE_{net}_RPC_URL")
        self.BASE_CHAIN_ID = getattr(self, f"BASE_{net}_CHAIN_ID")
        self.BASE_USDC_ADDRESS = getattr(self, f"BASE_{net}_USDC_ADDRESS")
        
        # BSC
        self.BSC_RPC_URL = getattr(self, f"BSC_{net}_RPC_URL")
        self.BSC_CHAIN_ID = getattr(self, f"BSC_{net}_CHAIN_ID")
        self.BSC_USDC_ADDRESS = getattr(self, f"BSC_{net}_USDC_ADDRESS")
        self.BSC_USDT_ADDRESS = getattr(self, f"BSC_{net}_USDT_ADDRESS")
        
        # Arbitrum
        self.ARBITRUM_RPC_URL = getattr(self, f"ARBITRUM_{net}_RPC_URL")
        self.ARBITRUM_CHAIN_ID = getattr(self, f"ARBITRUM_{net}_CHAIN_ID")
        self.ARBITRUM_USDC_ADDRESS = getattr(self, f"ARBITRUM_{net}_USDC_ADDRESS")
        self.ARBITRUM_USDT_ADDRESS = getattr(self, f"ARBITRUM_{net}_USDT_ADDRESS")
        
        # Avalanche
        self.AVALANCHE_RPC_URL = getattr(self, f"AVALANCHE_{net}_RPC_URL")
        self.AVALANCHE_CHAIN_ID = getattr(self, f"AVALANCHE_{net}_CHAIN_ID")
        self.AVALANCHE_USDC_ADDRESS = getattr(self, f"AVALANCHE_{net}_USDC_ADDRESS")
        self.AVALANCHE_USDT_ADDRESS = getattr(self, f"AVALANCHE_{net}_USDT_ADDRESS")
        
        # Tron
        self.TRON_API_URL = getattr(self, f"TRON_{net}_API_URL")
        self.TRON_USDT_ADDRESS = getattr(self, f"TRON_{net}_USDT_ADDRESS")
        self.TRON_USDC_ADDRESS = getattr(self, f"TRON_{net}_USDC_ADDRESS")
        
        # Solana
        self.SOLANA_RPC_URL = getattr(self, f"SOLANA_{net}_RPC_URL")
        self.SOLANA_USDC_MINT = getattr(self, f"SOLANA_{net}_USDC_MINT")
        self.SOLANA_USDT_MINT = getattr(self, f"SOLANA_{net}_USDT_MINT")
        
        return self
    
    @model_validator(mode="after")
    def validate_security_settings(self):
        """Validate security-critical settings. Blocks dangerous defaults in production."""
        is_prod = self.ENVIRONMENT == "production"
        
        # ── JWT Secret: reject known weak defaults ──
        if self.JWT_SECRET.lower() in _WEAK_JWT_SECRETS:
            if is_prod:
                raise ValueError(
                    "CRITICAL: JWT_SECRET must be changed from default value! "
                    "Generate one with: openssl rand -hex 32"
                )
            _config_logger.warning(
                "⚠️  JWT_SECRET is set to a weak default. "
                "Change it before deploying to production!"
            )
        
        # ── CORS: reject wildcard in production ──
        if is_prod and "*" in self.CORS_ORIGINS:
            raise ValueError(
                "CRITICAL: CORS_ORIGINS='*' is not allowed in production! "
                "Set specific allowed origins."
            )
        
        # ── Admin password: reject defaults in production ──
        if self.ADMIN_PASSWORD.lower() in _WEAK_ADMIN_PASSWORDS:
            if is_prod:
                raise ValueError(
                    "CRITICAL: ADMIN_PASSWORD must be changed from default! "
                    "Use a strong password (12+ chars, mixed case, digits, symbols)."
                )
            _config_logger.warning(
                "⚠️  ADMIN_PASSWORD is set to a weak default. "
                "Change it before deploying to production!"
            )
        
        # ── Redis: warn if disabled in production ──
        if is_prod and not self.REDIS_ENABLED:
            _config_logger.warning(
                "⚠️  REDIS_ENABLED=false in production. In-memory caches "
                "won't be shared across workers. Enable Redis for production."
            )
        
        # ── PII Encryption Key: warn if empty ──
        if not self.PII_ENCRYPTION_KEY:
            _config_logger.warning(
                "⚠️  PII_ENCRYPTION_KEY is not set. PII fields will be stored "
                "in plaintext. Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )
        
        return self
    
    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
    
    @property
    def enabled_chains(self) -> List[str]:
        """Get list of enabled blockchain networks"""
        chains = ["stellar"]  # Stellar always enabled for backward compatibility
        if self.ETHEREUM_ENABLED:
            chains.append("ethereum")
        if self.POLYGON_ENABLED:
            chains.append("polygon")
        if self.BASE_ENABLED:
            chains.append("base")
        if self.BSC_ENABLED:
            chains.append("bsc")
        if self.ARBITRUM_ENABLED:
            chains.append("arbitrum")
        if self.TRON_ENABLED:
            chains.append("tron")
        if self.SOLANA_ENABLED:
            chains.append("solana")
        return chains
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
