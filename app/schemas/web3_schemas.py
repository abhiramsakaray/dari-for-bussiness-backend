"""
Web3 Subscription Pydantic Schemas

Request/response schemas for the Web3 subscription API endpoints.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from enum import Enum


# ============= ENUMS =============

class Web3ChainEnum(str, Enum):
    ETHEREUM = "ethereum"
    POLYGON = "polygon"
    BASE = "base"
    ARBITRUM = "arbitrum"


class Web3TokenEnum(str, Enum):
    USDC = "USDC"
    USDT = "USDT"


class IntervalEnum(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


# ============= MANDATE SCHEMAS =============

class MandateSigningRequest(BaseModel):
    """Request to generate EIP-712 signing data for a subscription mandate"""
    subscriber: str = Field(..., description="Subscriber wallet address")
    merchant_id: str = Field(..., description="Dari merchant UUID")
    token_address: str = Field(..., description="ERC20 token contract address")
    amount: int = Field(..., gt=0, description="Amount in token decimals")
    interval: int = Field(..., gt=0, description="Billing interval in seconds")
    max_payments: int = Field(default=0, ge=0, description="Max payments (0 = unlimited)")
    chain: Web3ChainEnum = Field(default=Web3ChainEnum.POLYGON)
    chain_id: int = Field(default=137, description="EVM chain ID")


class MandateSigningResponse(BaseModel):
    """EIP-712 typed data for frontend wallet signing"""
    domain: dict
    types: dict
    primaryType: str
    message: dict
    nonce: int


# ============= SUBSCRIPTION SCHEMAS =============

class CreateWeb3SubscriptionRequest(BaseModel):
    """Request to create a new Web3 subscription"""
    # Mandate authorization
    signature: str = Field(..., description="EIP-712 signature from user's wallet")
    subscriber_address: str = Field(..., description="Subscriber wallet address")
    nonce: int = Field(default=0, description="Mandate nonce")
    merchant_id: Optional[str] = Field(None, description="Dari merchant UUID (required when plan_id is not provided)")

    # Plan or custom billing
    plan_id: Optional[str] = Field(None, description="Subscription plan ID")
    token_address: str = Field(default="", description="ERC20 token contract address")
    token_symbol: Web3TokenEnum = Field(default=Web3TokenEnum.USDC)
    amount: Optional[float] = Field(None, gt=0, description="Payment amount")
    interval: IntervalEnum = Field(default=IntervalEnum.MONTHLY)

    # Chain
    chain: Web3ChainEnum = Field(default=Web3ChainEnum.POLYGON)
    chain_id: int = Field(default=137)
    max_payments: Optional[int] = Field(None, ge=1, description="Max billing cycles")

    # Customer info
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None


class CancelWeb3SubscriptionRequest(BaseModel):
    """Request to cancel a Web3 subscription"""
    reason: Optional[str] = None


class UserCancelRequest(BaseModel):
    """User-initiated cancellation (by subscriber address)"""
    subscription_id: str = Field(..., description="Subscription UUID")
    subscriber_address: str = Field(..., description="Subscriber wallet address")


class Web3SubscriptionResponse(BaseModel):
    """Web3 subscription response"""
    id: str
    onchain_subscription_id: Optional[int] = None
    chain: str
    contract_address: str

    # Parties
    subscriber_address: str
    merchant_address: str
    token_symbol: str

    # Billing
    amount: str
    interval_seconds: int
    next_payment_at: Optional[datetime] = None

    # Status
    status: str
    failed_payment_count: int = 0

    # Payment stats
    total_payments: int = 0
    total_amount_collected: str = "0"

    # Customer info
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None

    # Tx hashes
    created_tx_hash: Optional[str] = None
    cancelled_tx_hash: Optional[str] = None

    # Timestamps
    created_at: datetime
    cancelled_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Web3SubscriptionListResponse(BaseModel):
    """Paginated list of Web3 subscriptions"""
    subscriptions: List[Web3SubscriptionResponse]
    total: int
    page: int
    page_size: int


class Web3PaymentResponse(BaseModel):
    """Individual subscription payment record"""
    id: str
    subscription_id: str
    amount: str
    token_symbol: str
    chain: str
    payment_number: int
    period_start: datetime
    period_end: datetime
    tx_hash: Optional[str] = None
    block_number: Optional[int] = None
    status: str
    created_at: datetime
    confirmed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Web3PaymentListResponse(BaseModel):
    """Paginated list of payments"""
    payments: List[Web3PaymentResponse]
    total: int
    page: int
    page_size: int


# ============= ANALYTICS SCHEMAS =============

class Web3AnalyticsResponse(BaseModel):
    """Merchant Web3 subscription analytics"""
    active_subscriptions: int
    past_due_subscriptions: int
    churned_last_30d: int
    total_revenue: str
    mrr: float  # Monthly Recurring Revenue


# ============= ADMIN SCHEMAS =============

class RelayerStatusResponse(BaseModel):
    """Relayer balance and health status"""
    balances: dict
    address: Optional[str] = None


class SchedulerStatusResponse(BaseModel):
    """Scheduler status and metrics"""
    is_running: bool
    interval_seconds: int
    batch_size: int
    total_cycles: int
    total_payments_executed: int
    total_payments_failed: int
    last_run: Optional[str] = None
    last_error: Optional[str] = None


class HealthCheckResponse(BaseModel):
    """Subscription health check (DB vs on-chain state)"""
    subscription_id: str
    db_active: Optional[bool] = None
    onchain_active: Optional[bool] = None
    state_match: Optional[bool] = None
    db_amount: Optional[str] = None
    onchain_amount: Optional[str] = None
    error: Optional[str] = None
