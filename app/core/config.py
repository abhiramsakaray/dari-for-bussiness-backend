from pydantic_settings import BaseSettings
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
    
    # ============= STELLAR NETWORK =============
    STELLAR_ENABLED: bool = True
    STELLAR_NETWORK: str = "testnet"
    STELLAR_HORIZON_URL: str = "https://horizon-testnet.stellar.org"
    USDC_ASSET_CODE: str = "USDC"
    USDC_ASSET_ISSUER: str = "GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5"
    
    # Soroban Smart Contracts (Optional)
    SOROBAN_RPC_URL: str = "https://soroban-testnet.stellar.org"
    SOROBAN_ESCROW_CONTRACT_ID: str = ""
    SOROBAN_USDC_CONTRACT_ID: str = ""
    PAYMENT_VALIDATOR_CONTRACT_ID: str = ""
    BACKEND_SECRET_KEY: str = ""
    
    # ============= EVM NETWORKS =============
    # Ethereum
    ETHEREUM_ENABLED: bool = True
    ETHEREUM_RPC_URL: str = "https://eth.llamarpc.com"
    ETHEREUM_CHAIN_ID: int = 1
    ETHEREUM_CONFIRMATIONS: int = 12
    ETHEREUM_USDC_ADDRESS: str = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    ETHEREUM_USDT_ADDRESS: str = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
    ETHEREUM_PYUSD_ADDRESS: str = "0x6c3ea9036406852006290770BEdFcAbA0e23A0e8"
    
    # Polygon
    POLYGON_ENABLED: bool = True
    POLYGON_RPC_URL: str = "https://polygon-rpc.com"
    POLYGON_CHAIN_ID: int = 137
    POLYGON_CONFIRMATIONS: int = 64
    POLYGON_USDC_ADDRESS: str = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
    POLYGON_USDT_ADDRESS: str = "0xc2132D05D31c914a87C6611C10748AEb04B58e8F"
    
    # Base
    BASE_ENABLED: bool = True
    BASE_RPC_URL: str = "https://mainnet.base.org"
    BASE_CHAIN_ID: int = 8453
    BASE_CONFIRMATIONS: int = 12
    BASE_USDC_ADDRESS: str = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    
    # ============= TRON NETWORK =============
    TRON_ENABLED: bool = True
    TRON_API_URL: str = "https://api.trongrid.io"
    TRON_API_KEY: Optional[str] = None
    TRON_CONFIRMATIONS: int = 19
    TRON_USDT_ADDRESS: str = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    TRON_USDC_ADDRESS: str = "TEkxiTehnzSmSe2XqrBj4w32RUN966rdz8"
    
    # ============= SOLANA NETWORK (Future) =============
    SOLANA_ENABLED: bool = False
    SOLANA_RPC_URL: str = "https://api.mainnet-beta.solana.com"
    SOLANA_USDC_MINT: str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    
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
