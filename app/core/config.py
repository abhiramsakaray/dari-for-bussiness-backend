from pydantic_settings import BaseSettings
from pydantic import model_validator
from typing import List, Optional


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Dari for Business"
    APP_VERSION: str = "2.0.0"
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
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    
    # API Keys
    API_KEY_SECRET: str = "your-api-key-secret-change-in-production"
    
    # Payment Settings
    PAYMENT_EXPIRY_MINUTES: int = 30
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
    
    # ============= SOLANA NETWORK (Future) =============
    SOLANA_ENABLED: bool = False
    
    # Testnet (Devnet)
    SOLANA_TESTNET_RPC_URL: str = "https://api.devnet.solana.com"
    SOLANA_TESTNET_USDC_MINT: str = "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU"
    
    # Mainnet
    SOLANA_MAINNET_RPC_URL: str = "https://api.mainnet-beta.solana.com"
    SOLANA_MAINNET_USDC_MINT: str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    
    # Active (resolved by model_validator)
    SOLANA_RPC_URL: str = ""
    SOLANA_USDC_MINT: str = ""
    
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
    
    # ============= WEB3 SUBSCRIPTIONS =============
    # Gasless Relayer
    RELAYER_PRIVATE_KEY: str = ""
    RELAYER_MAX_GAS_PRICE_GWEI: int = 100
    
    # Subscription Contract Addresses (set per chain after deployment)
    SUBSCRIPTION_CONTRACT_ETHEREUM: str = ""
    SUBSCRIPTION_CONTRACT_POLYGON: str = ""
    SUBSCRIPTION_CONTRACT_BASE: str = ""
    SUBSCRIPTION_CONTRACT_ARBITRUM: str = ""
    
    # Scheduler
    SCHEDULER_INTERVAL_SECONDS: int = 60
    SCHEDULER_BATCH_SIZE: int = 100
    SCHEDULER_MAX_RETRIES: int = 6
    SCHEDULER_RETRY_INTERVAL_HOURS: int = 12
    
    # Enable/disable Web3 subscription scheduler
    WEB3_SUBSCRIPTIONS_ENABLED: bool = False
    
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
        
        # Tron
        self.TRON_API_URL = getattr(self, f"TRON_{net}_API_URL")
        self.TRON_USDT_ADDRESS = getattr(self, f"TRON_{net}_USDT_ADDRESS")
        self.TRON_USDC_ADDRESS = getattr(self, f"TRON_{net}_USDC_ADDRESS")
        
        # Solana
        self.SOLANA_RPC_URL = getattr(self, f"SOLANA_{net}_RPC_URL")
        self.SOLANA_USDC_MINT = getattr(self, f"SOLANA_{net}_USDC_MINT")
        
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
        if self.TRON_ENABLED:
            chains.append("tron")
        if self.SOLANA_ENABLED:
            chains.append("solana")
        return chains
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
