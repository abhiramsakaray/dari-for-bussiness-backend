from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_validator
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from enum import Enum


# ============= ENUMS =============

class ChainEnum(str, Enum):
    STELLAR = "stellar"
    ETHEREUM = "ethereum"
    POLYGON = "polygon"
    BASE = "base"
    TRON = "tron"
    SOLANA = "solana"


class TokenEnum(str, Enum):
    USDC = "USDC"
    USDT = "USDT"
    PYUSD = "PYUSD"


# ============= AUTH SCHEMAS =============

class MerchantRegister(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8)
    merchant_category: Optional[str] = "individual"  # individual, startup, small_business, enterprise, ngo


class MerchantLogin(BaseModel):
    email: EmailStr
    password: str


class GoogleAuthRequest(BaseModel):
    """Google OAuth token exchange"""
    token: str = Field(..., description="Google OAuth ID token or access token")


class GoogleAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    api_key: str
    is_new_user: bool = False
    onboarding_completed: bool = False
    onboarding_step: int = 0


# ============= ONBOARDING SCHEMAS =============

class MerchantCategoryEnum(str, Enum):
    INDIVIDUAL = "individual"
    STARTUP = "startup"
    SMALL_BUSINESS = "small_business"
    ENTERPRISE = "enterprise"
    NGO = "ngo"


class OnboardingBusinessDetails(BaseModel):
    """Step 1: Business details"""
    business_name: str = Field(..., min_length=1, max_length=255)
    business_email: Optional[EmailStr] = None
    country: str = Field(..., min_length=2, max_length=100)
    merchant_category: MerchantCategoryEnum = MerchantCategoryEnum.INDIVIDUAL


class WalletConfig(BaseModel):
    """Individual wallet configuration"""
    chain: ChainEnum
    token: TokenEnum
    auto_generate: bool = True


class OnboardingWalletSetup(BaseModel):
    """Step 2: Wallet setup - choose which chains to accept payments on"""
    chains: Optional[List[ChainEnum]] = Field(None, description="Chains to accept payments on")
    tokens: Optional[List[TokenEnum]] = Field(None, description="Tokens to accept")
    auto_generate: Optional[bool] = Field(True, description="Auto-generate wallets for selected chains")
    wallets: Optional[List[WalletConfig]] = Field(None, description="Individual wallet configurations (alternative format)")


class OnboardingCompleteRequest(BaseModel):
    """Complete onboarding request with optional plan and wallet setup"""
    plan: Optional[str] = Field("free", description="Subscription plan (free, growth, business, enterprise)")
    wallets: Optional[List[WalletConfig]] = Field(None, description="Wallet configurations to create")
    chains: Optional[List[ChainEnum]] = Field(None, description="Alternative: chains list")
    tokens: Optional[List[TokenEnum]] = Field(None, description="Alternative: tokens list")
    auto_generate: Optional[bool] = Field(True, description="Auto-generate wallets")


class OnboardingStatusResponse(BaseModel):
    """Current onboarding status"""
    step: int  # 0=signup, 1=business_details, 2=wallets, 3=complete
    onboarding_completed: bool
    merchant_id: str
    name: str
    email: str
    merchant_category: Optional[str] = None
    business_name: Optional[str] = None
    business_email: Optional[str] = None
    country: Optional[str] = None
    has_wallets: bool = False
    wallet_count: int = 0


class OnboardingCompleteResponse(BaseModel):
    """Onboarding completion response"""
    message: str
    merchant_id: str
    api_key: str
    onboarding_completed: bool = True
    wallets: List[dict] = []


# ============= SUBSCRIPTION SCHEMAS =============

class SubscriptionTierEnum(str, Enum):
    FREE = "free"
    GROWTH = "growth"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


class SubscriptionStatusEnum(str, Enum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    TRIALING = "trialing"


class SubscriptionPlanInfo(BaseModel):
    """Public subscription plan information"""
    tier: SubscriptionTierEnum
    name: str
    monthly_price: float
    transaction_fee_min: float
    transaction_fee_max: float
    monthly_volume_limit: Optional[float]
    payment_link_limit: Optional[int]
    invoice_limit: Optional[int]
    team_member_limit: int
    features: List[str]
    
    class Config:
        from_attributes = True


class LocalCurrencyAmount(BaseModel):
    """Dual-currency representation: USDC + merchant's local currency"""
    amount_usdc: float
    amount_local: float
    local_currency: str       # e.g. "INR"
    local_symbol: str         # e.g. "₹"
    exchange_rate: float      # 1 USDC = X local
    display_local: str        # e.g. "₹4,150.00"


class SubscriptionResponse(BaseModel):
    """Merchant's current subscription"""
    tier: str
    status: str
    monthly_price: float
    transaction_fee_percent: float
    monthly_volume_limit: Optional[float]
    payment_link_limit: Optional[int]
    invoice_limit: Optional[int]
    team_member_limit: int
    current_volume: float
    current_payment_links: int
    current_invoices: int
    current_period_start: datetime
    current_period_end: datetime
    trial_ends_at: Optional[datetime]
    # Dual-currency
    monthly_price_local: Optional[LocalCurrencyAmount] = None
    current_volume_local: Optional[LocalCurrencyAmount] = None
    volume_limit_local: Optional[LocalCurrencyAmount] = None
    
    class Config:
        from_attributes = True


class SubscriptionUpgradeRequest(BaseModel):
    """Request to upgrade/downgrade subscription"""
    tier: Optional[SubscriptionTierEnum] = None
    plan: Optional[str] = None  # Alias for 'tier' — accepted for frontend compatibility

    @field_validator("tier", mode="before")
    @classmethod
    def normalize_tier(cls, v):
        if v is None:
            return v
        return str(v).lower()

    def get_tier(self) -> str:
        """Return the resolved tier value, preferring 'tier' over 'plan'."""
        if self.tier is not None:
            return self.tier.value
        if self.plan is not None:
            return self.plan.lower()
        raise ValueError("Either 'tier' or 'plan' must be provided")


class SubscriptionUpgradeResponse(BaseModel):
    """Response after subscription change"""
    message: str
    new_tier: str
    new_monthly_price: float
    effective_date: datetime
    prorated_amount: Optional[float] = None


class SubscriptionUsageResponse(BaseModel):
    """Current billing period usage"""
    tier: str
    current_volume: float
    volume_limit: Optional[float]
    volume_used_percent: Optional[float]
    payment_links_used: int
    payment_links_limit: Optional[int]
    invoices_used: int
    invoices_limit: Optional[int]
    team_members_used: int
    team_members_limit: int
    period_end: datetime
    days_remaining: int
    # Dual-currency
    current_volume_local: Optional[LocalCurrencyAmount] = None
    volume_limit_local: Optional[LocalCurrencyAmount] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    api_key: str  # Merchant's API key for creating payment sessions
    onboarding_completed: bool = False
    onboarding_step: int = 0


# ============= MERCHANT WALLET SCHEMAS =============

class MerchantWalletCreate(BaseModel):
    chain: ChainEnum
    wallet_address: str = Field(..., min_length=10, max_length=100)


class MerchantWalletResponse(BaseModel):
    id: str
    chain: str
    wallet_address: str
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class MerchantWalletUpdate(BaseModel):
    wallet_address: Optional[str] = Field(None, min_length=10, max_length=100)
    is_active: Optional[bool] = None


class MerchantWalletList(BaseModel):
    wallets: List[MerchantWalletResponse]


# ============= MERCHANT SCHEMAS =============

class MerchantProfileUpdate(BaseModel):
    stellar_address: Optional[str] = None
    webhook_url: Optional[HttpUrl] = None
    webhook_secret: Optional[str] = None
    accepted_tokens: Optional[List[str]] = None  # ["USDC", "USDT", "PYUSD"]
    accepted_chains: Optional[List[str]] = None  # ["stellar", "polygon", "ethereum"]


class MerchantProfile(BaseModel):
    id: str
    name: str
    email: str
    stellar_address: Optional[str]
    webhook_url: Optional[str]
    is_active: bool
    accepted_tokens: Optional[List[str]] = None
    accepted_chains: Optional[List[str]] = None
    wallets: Optional[List[MerchantWalletResponse]] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


# ============= PAYMENT SESSION SCHEMAS =============

class PaymentSessionCreate(BaseModel):
    """Create a new payment session (multi-chain support)"""
    amount: Decimal = Field(..., gt=0, description="Amount in fiat currency")
    currency: str = Field(default="USD", description="Fiat currency code")
    
    # Multi-chain options
    accepted_tokens: Optional[List[str]] = Field(
        default=["USDC", "USDT", "PYUSD"],
        description="Accepted token symbols"
    )
    accepted_chains: Optional[List[str]] = Field(
        default=["stellar", "polygon", "ethereum", "tron"],
        description="Accepted blockchain networks"
    )
    
    # Session details
    order_id: Optional[str] = Field(None, max_length=255, description="Your order/transaction ID")
    success_url: Optional[str] = Field(None, description="URL to redirect to after successful payment")
    cancel_url: Optional[str] = Field(None, description="URL to redirect to if payment is cancelled")
    metadata: Optional[dict] = Field(None, description="Optional metadata (customer info, items, etc.)")
    
    # Payer data collection
    collect_payer_data: bool = Field(default=True, description="Collect payer info before payment")

    # Backward compatibility
    amount_usdc: Optional[Decimal] = Field(None, description="[DEPRECATED] Use 'amount' instead")

    @field_validator('accepted_tokens')
    @classmethod
    def validate_tokens(cls, v):
        if v:
            valid = ["USDC", "USDT", "PYUSD"]
            return [t.upper() for t in v if t.upper() in valid]
        return ["USDC"]
    
    @field_validator('accepted_chains')
    @classmethod
    def validate_chains(cls, v):
        if v:
            valid = ["stellar", "ethereum", "polygon", "base", "tron", "solana"]
            return [c.lower() for c in v if c.lower() in valid]
        return ["stellar"]


class PaymentSessionResponse(BaseModel):
    session_id: str
    checkout_url: str
    amount: Decimal
    currency: str
    accepted_tokens: List[str]
    accepted_chains: List[str]
    order_id: Optional[str] = None
    expires_at: datetime
    status: str
    
    # Backward compatibility
    amount_usdc: Optional[Decimal] = None
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class PaymentOption(BaseModel):
    """A single payment option (token on chain)"""
    token: str
    chain: str
    chain_display: str
    wallet_address: str
    amount: str
    label: str
    icon_url: Optional[str] = None
    memo: Optional[str] = None  # For Stellar


class PaymentSessionStatus(BaseModel):
    session_id: str
    status: str
    amount: str
    currency: str
    token: Optional[str] = None
    chain: Optional[str] = None
    tx_hash: Optional[str] = None
    block_number: Optional[int] = None
    confirmations: Optional[int] = None
    order_id: Optional[str] = None
    created_at: datetime
    paid_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    
    # Backward compatibility
    amount_usdc: Optional[str] = None
    metadata: Optional[dict] = None
    
    class Config:
        from_attributes = True


class PaymentSessionDetail(BaseModel):
    """Detailed payment session for checkout page"""
    id: str
    merchant_name: str
    amount_fiat: Decimal
    fiat_currency: str
    status: str
    success_url: str
    cancel_url: str
    tx_hash: Optional[str] = None
    created_at: datetime
    paid_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    
    # Multi-chain fields
    accepted_tokens: Optional[List[str]] = None
    accepted_chains: Optional[List[str]] = None
    payment_options: Optional[List[PaymentOption]] = None
    
    # Selected payment method (after customer chooses)
    selected_token: Optional[str] = None
    selected_chain: Optional[str] = None
    payment_address: Optional[str] = None
    payment_amount: Optional[str] = None
    payment_memo: Optional[str] = None  # For Stellar
    
    # Backward compatibility
    merchant_stellar_address: Optional[str] = None
    amount_usdc: Optional[str] = None
    
    class Config:
        from_attributes = True


class SelectPaymentMethod(BaseModel):
    """Select payment method for a session"""
    token: str = Field(..., description="Token symbol (USDC, USDT, PYUSD)")
    chain: str = Field(..., description="Blockchain network")


# ============= WEBHOOK SCHEMAS =============

class WebhookPayload(BaseModel):
    """Webhook payload sent to merchants"""
    event: str  # payment.succeeded, payment.failed, payment.expired
    session_id: str
    amount: str
    currency: str
    token: Optional[str] = None
    chain: Optional[str] = None
    tx_hash: Optional[str] = None
    block_number: Optional[int] = None
    confirmations: Optional[int] = None
    status: str = "confirmed"
    timestamp: str


# ============= ADMIN SCHEMAS =============

class MerchantListItem(BaseModel):
    id: str
    name: str
    email: str
    stellar_address: Optional[str] = None
    is_active: bool
    wallet_count: int = 0
    created_at: datetime
    
    class Config:
        from_attributes = True


class PaymentListItem(BaseModel):
    id: str
    merchant_id: str
    merchant_name: str
    amount_fiat: Decimal
    fiat_currency: str
    token: Optional[str] = None
    chain: Optional[str] = None
    status: str
    tx_hash: Optional[str] = None
    created_at: datetime
    paid_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    # Payer info (available as soon as the customer fills the form)
    payer_email: Optional[str] = None
    payer_name: Optional[str] = None

    # Backward compatibility
    amount_usdc: Optional[str] = None

    class Config:
        from_attributes = True


class MerchantDisable(BaseModel):
    is_active: bool


# ============= TOKEN SCHEMAS =============

class TokenInfo(BaseModel):
    symbol: str
    name: str
    chain: str
    chain_display: str
    contract_address: str
    decimals: int
    icon_url: Optional[str] = None
    is_active: bool = True


class SupportedTokensResponse(BaseModel):
    tokens: List[TokenInfo]
    chains: List[str]
    symbols: List[str]


# ============= SYSTEM SCHEMAS =============

class HealthCheck(BaseModel):
    status: str
    version: str
    chains: dict
    timestamp: str


# ============= PAYMENT LINK SCHEMAS =============

class PaymentLinkCreate(BaseModel):
    """Create a reusable payment link"""
    name: str = Field(..., min_length=1, max_length=100, description="Internal name for the link")
    description: Optional[str] = Field(None, description="Description shown to customers")
    
    # Amount configuration
    amount_fiat: Optional[Decimal] = Field(None, gt=0, description="Amount in fiat (optional for variable amounts)")
    fiat_currency: str = Field(default="USD", description="Fiat currency")
    is_amount_fixed: bool = Field(default=True, description="If false, customer enters amount")
    min_amount: Optional[Decimal] = Field(None, gt=0, description="Minimum amount if variable")
    max_amount: Optional[Decimal] = Field(None, description="Maximum amount if variable")
    
    # Payment options
    accepted_tokens: Optional[List[str]] = Field(default=["USDC", "USDT"], description="Accepted tokens")
    accepted_chains: Optional[List[str]] = Field(default=["polygon", "stellar"], description="Accepted chains")
    
    # URLs
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None
    
    # Configuration
    is_single_use: bool = Field(default=False, description="Deactivate after first payment")
    expires_at: Optional[datetime] = None
    
    # Metadata
    metadata: Optional[dict] = None


class PaymentLinkUpdate(BaseModel):
    """Update a payment link"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    amount_fiat: Optional[Decimal] = None
    is_active: Optional[bool] = None
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None
    expires_at: Optional[datetime] = None


class PaymentLinkResponse(BaseModel):
    """Payment link response"""
    id: str
    name: str
    description: Optional[str] = None
    
    # Amount
    amount_fiat: Optional[Decimal] = None
    fiat_currency: str
    is_amount_fixed: bool
    
    # Payment options
    accepted_tokens: List[str]
    accepted_chains: List[str]
    
    # URLs
    checkout_url: str  # Full URL to access the payment link
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None
    
    # Status
    is_active: bool
    is_single_use: bool
    expires_at: Optional[datetime] = None
    
    # Analytics
    view_count: int = 0
    payment_count: int = 0
    total_collected_usd: Decimal = Decimal("0")
    
    created_at: datetime
    
    class Config:
        from_attributes = True


class PaymentLinkList(BaseModel):
    """List of payment links"""
    links: List[PaymentLinkResponse]
    total: int
    page: int
    page_size: int


# ============= INVOICE SCHEMAS =============

class InvoiceLineItem(BaseModel):
    """Individual line item on an invoice"""
    description: str
    quantity: int = Field(default=1, ge=1)
    unit_price: Decimal = Field(..., ge=0)
    total: Optional[Decimal] = None  # Calculated


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    VIEWED = "viewed"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class InvoiceCreate(BaseModel):
    """Create a new invoice"""
    invoice_number: Optional[str] = Field(None, max_length=50, description="Invoice number (auto-generated if not provided)")
    
    # Customer info
    customer_email: EmailStr
    customer_name: Optional[str] = None
    customer_address: Optional[str] = None
    
    # Invoice details  
    description: Optional[str] = None
    line_items: List[InvoiceLineItem] = Field(default=[], description="Line items")
    
    # Amounts (calculated from line_items if not provided)
    subtotal: Optional[Decimal] = None
    tax: Decimal = Field(default=Decimal("0"))
    discount: Decimal = Field(default=Decimal("0"))
    fiat_currency: str = Field(default="USD")
    
    # Due date
    due_date: datetime
    
    # Payment options
    accepted_tokens: Optional[List[str]] = None
    accepted_chains: Optional[List[str]] = None
    
    # Notes
    notes: Optional[str] = None
    terms: Optional[str] = None
    footer: Optional[str] = None
    
    # Auto-send
    send_immediately: bool = Field(default=False, description="Send invoice immediately after creation")
    
    # Metadata
    metadata: Optional[dict] = None


class InvoiceUpdate(BaseModel):
    """Update an invoice (only in draft status)"""
    invoice_number: Optional[str] = None
    customer_email: Optional[EmailStr] = None
    customer_name: Optional[str] = None
    customer_address: Optional[str] = None
    description: Optional[str] = None
    line_items: Optional[List[InvoiceLineItem]] = None
    subtotal: Optional[Decimal] = None
    tax: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    due_date: Optional[datetime] = None
    notes: Optional[str] = None
    terms: Optional[str] = None
    footer: Optional[str] = None


class InvoiceResponse(BaseModel):
    """Invoice response"""
    id: str
    invoice_number: str
    
    # Customer
    customer_email: str
    customer_name: Optional[str] = None
    customer_address: Optional[str] = None
    
    # Details
    description: Optional[str] = None
    line_items: List[InvoiceLineItem]
    
    # Amounts
    subtotal: Decimal
    tax: Decimal
    discount: Decimal
    total: Decimal
    fiat_currency: str
    
    # Status
    status: str
    issue_date: datetime
    due_date: datetime
    sent_at: Optional[datetime] = None
    viewed_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    
    # Payment
    payment_url: Optional[str] = None  # URL for customer to pay
    amount_paid: Decimal = Decimal("0")
    
    # Notes
    notes: Optional[str] = None
    terms: Optional[str] = None
    footer: Optional[str] = None
    
    created_at: datetime
    
    class Config:
        from_attributes = True


class InvoiceList(BaseModel):
    """List of invoices"""
    invoices: List[InvoiceResponse]
    total: int
    page: int
    page_size: int


class InvoiceSend(BaseModel):
    """Send invoice to customer"""
    message: Optional[str] = Field(None, description="Custom message to include in email")


# ============= SUBSCRIPTION SCHEMAS =============

class SubscriptionInterval(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    PAST_DUE = "past_due"
    TRIALING = "trialing"


class SubscriptionPlanCreate(BaseModel):
    """Create a subscription plan"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    
    # Pricing
    amount: Decimal = Field(..., gt=0)
    fiat_currency: str = Field(default="USD")
    interval: SubscriptionInterval
    interval_count: int = Field(default=1, ge=1, description="Number of intervals (e.g., 2 for bi-weekly)")
    
    # Trial
    trial_days: int = Field(default=0, ge=0)
    
    # Payment options
    accepted_tokens: Optional[List[str]] = None
    accepted_chains: Optional[List[str]] = None
    
    # Features (for display)
    features: Optional[List[str]] = None
    
    # Metadata
    metadata: Optional[dict] = None


class SubscriptionPlanUpdate(BaseModel):
    """Update a subscription plan"""
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    features: Optional[List[str]] = None


class SubscriptionPlanResponse(BaseModel):
    """Subscription plan response"""
    id: str
    name: str
    description: Optional[str] = None
    
    # Pricing
    amount: Decimal
    fiat_currency: str
    interval: str
    interval_count: int
    
    # Trial
    trial_days: int
    
    # Payment options
    accepted_tokens: List[str]
    accepted_chains: List[str]
    
    # Status
    is_active: bool
    
    # Features
    features: Optional[List[str]] = None
    
    # Stats
    subscriber_count: int = 0
    
    created_at: datetime
    
    class Config:
        from_attributes = True


class SubscriptionCreate(BaseModel):
    """Create a subscription for a customer"""
    plan_id: str
    customer_email: EmailStr
    customer_name: Optional[str] = None
    customer_id: Optional[str] = Field(None, description="Your internal customer ID")
    
    # Trial override
    skip_trial: bool = Field(default=False, description="Skip plan's trial period")
    
    # Metadata
    metadata: Optional[dict] = None


class RecurringSubscriptionResponse(BaseModel):
    """Customer recurring subscription response"""
    id: str
    plan_id: str
    plan_name: str
    
    # Customer
    customer_email: str
    customer_name: Optional[str] = None
    customer_id: Optional[str] = None
    
    # Status
    status: str
    
    # Billing cycle
    current_period_start: datetime
    current_period_end: datetime
    
    # Trial
    trial_start: Optional[datetime] = None
    trial_end: Optional[datetime] = None
    
    # Next payment
    next_payment_at: Optional[datetime] = None
    next_payment_url: Optional[str] = None  # URL for customer to make next payment
    
    # Cancellation
    cancel_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    
    created_at: datetime
    
    class Config:
        from_attributes = True


class SubscriptionList(BaseModel):
    """List of subscriptions"""
    subscriptions: List[RecurringSubscriptionResponse]
    total: int
    page: int
    page_size: int


class SubscriptionCancel(BaseModel):
    """Cancel a subscription"""
    cancel_immediately: bool = Field(default=False, description="Cancel now or at end of period")
    reason: Optional[str] = None


# ============= REFUND SCHEMAS =============

class RefundStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class RefundCreate(BaseModel):
    """Create a refund"""
    payment_session_id: str
    amount: Optional[Decimal] = Field(None, description="Amount to refund (full refund if not specified)")
    refund_address: str = Field(..., description="Customer's wallet address for refund")
    reason: Optional[str] = None


class RefundResponse(BaseModel):
    """Refund response"""
    id: str
    payment_session_id: str
    
    # Amount
    amount: Decimal
    token: str
    chain: str
    
    # Destination
    refund_address: str
    
    # Status
    status: str
    tx_hash: Optional[str] = None
    
    # Reason
    reason: Optional[str] = None
    
    created_at: datetime
    processed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class RefundList(BaseModel):
    """List of refunds"""
    refunds: List[RefundResponse]
    total: int


# ============= TEAM SCHEMAS =============

class MerchantRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    DEVELOPER = "developer"
    FINANCE = "finance"
    VIEWER = "viewer"


class TeamMemberInvite(BaseModel):
    """Invite a team member"""
    email: EmailStr
    name: Optional[str] = None
    role: MerchantRole = Field(default=MerchantRole.VIEWER)


class TeamMemberUpdate(BaseModel):
    """Update a team member"""
    role: Optional[MerchantRole] = None
    is_active: Optional[bool] = None


class TeamMemberResponse(BaseModel):
    """Team member response"""
    id: str
    email: str
    name: Optional[str] = None
    role: str
    is_active: bool
    
    invite_pending: bool = False
    last_login: Optional[datetime] = None
    
    created_at: datetime
    
    class Config:
        from_attributes = True


class TeamList(BaseModel):
    """List of team members"""
    members: List[TeamMemberResponse]
    total: int


# ============= IDEMPOTENCY SCHEMAS =============

class IdempotencyInfo(BaseModel):
    """Idempotency key information"""
    key: str
    endpoint: str
    status: str  # "processing", "completed"
    created_at: datetime
    expires_at: datetime


# ============= ANALYTICS SCHEMAS =============

class AnalyticsPeriod(str, Enum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class PaymentMetrics(BaseModel):
    """Payment metrics for a period"""
    total_payments: int = 0
    successful_payments: int = 0
    failed_payments: int = 0
    total_volume_usd: Decimal = Decimal("0")
    avg_payment_usd: Optional[Decimal] = None
    conversion_rate: Optional[Decimal] = None  # Percentage


class VolumeByToken(BaseModel):
    """Volume breakdown by token"""
    token: str
    volume_usd: Decimal
    payment_count: int


class VolumeByChain(BaseModel):
    """Volume breakdown by chain"""
    chain: str
    volume_usd: Decimal
    payment_count: int


class AnalyticsOverview(BaseModel):
    """Analytics overview for merchant dashboard"""
    # Time range
    period_start: datetime
    period_end: datetime
    period: str  # day, week, month, year
    
    # Payment metrics
    payments: PaymentMetrics
    
    # Breakdowns
    volume_by_token: List[VolumeByToken]
    volume_by_chain: List[VolumeByChain]
    
    # Invoices
    invoices_sent: int = 0
    invoices_paid: int = 0
    invoice_volume_usd: Decimal = Decimal("0")
    
    # Subscriptions
    active_subscriptions: int = 0
    new_subscriptions: int = 0
    churned_subscriptions: int = 0
    subscription_mrr: Decimal = Decimal("0")  # Monthly Recurring Revenue
    
    # Comparison to previous period
    payments_change_pct: Optional[Decimal] = None
    volume_change_pct: Optional[Decimal] = None


class RevenueTimeSeries(BaseModel):
    """Revenue time series data point"""
    date: datetime
    volume_usd: Decimal
    payment_count: int


class AnalyticsTimeSeries(BaseModel):
    """Time series analytics data"""
    period: str
    data: List[RevenueTimeSeries]


# ============= EVENT SCHEMAS =============

class EventType(str, Enum):
    PAYMENT_CREATED = "payment.created"
    PAYMENT_PENDING = "payment.pending"
    PAYMENT_CONFIRMED = "payment.confirmed"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_EXPIRED = "payment.expired"
    INVOICE_CREATED = "invoice.created"
    INVOICE_SENT = "invoice.sent"
    INVOICE_PAID = "invoice.paid"
    INVOICE_OVERDUE = "invoice.overdue"
    SUBSCRIPTION_CREATED = "subscription.created"
    SUBSCRIPTION_RENEWED = "subscription.renewed"
    SUBSCRIPTION_CANCELLED = "subscription.cancelled"
    SUBSCRIPTION_PAYMENT_FAILED = "subscription.payment_failed"
    REFUND_CREATED = "refund.created"
    REFUND_COMPLETED = "refund.completed"
    REFUND_FAILED = "refund.failed"


class EventResponse(BaseModel):
    """Event response"""
    id: str
    event_type: str
    entity_type: str
    entity_id: str
    payload: dict
    status: str
    created_at: datetime
    processed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class EventList(BaseModel):
    """List of events"""
    events: List[EventResponse]
    total: int
    page: int
    page_size: int


# ============= WEBHOOK DELIVERY SCHEMAS =============

class WebhookDeliveryResponse(BaseModel):
    """Webhook delivery response"""
    id: str
    event_type: str
    url: str
    status: str  # pending, success, failed
    http_status: Optional[int] = None
    attempt_count: int
    created_at: datetime
    delivered_at: Optional[datetime] = None
    next_retry: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class WebhookDeliveryList(BaseModel):
    """List of webhook deliveries"""
    deliveries: List[WebhookDeliveryResponse]
    total: int


# ============= RISK & FRAUD SCHEMAS =============

class RiskSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskSignalResponse(BaseModel):
    """Risk signal response"""
    id: str
    signal_type: str
    severity: str
    payment_session_id: Optional[str] = None
    wallet_address: Optional[str] = None
    description: Optional[str] = None
    action_taken: Optional[str] = None
    reviewed: bool = False
    created_at: datetime
    
    class Config:
        from_attributes = True


class RiskSignalList(BaseModel):
    """List of risk signals"""
    signals: List[RiskSignalResponse]
    total: int


# ============= API KEY SCHEMAS =============

class APIKeyCreate(BaseModel):
    """Create an API key"""
    name: Optional[str] = Field(None, max_length=100, description="Label for the API key")
    permissions: Optional[List[str]] = Field(
        None, 
        description="Permissions: payments:read, payments:write, invoices:read, etc."
    )
    expires_in_days: Optional[int] = Field(None, ge=1, le=365, description="Key expires after N days")


class APIKeyResponse(BaseModel):
    """API key response (key shown only on creation)"""
    id: str
    key: Optional[str] = None  # Only shown on creation
    key_prefix: str
    name: Optional[str] = None
    permissions: Optional[List[str]] = None
    is_active: bool
    last_used: Optional[datetime] = None
    created_at: datetime
    expires_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class APIKeyList(BaseModel):
    """List of API keys"""
    keys: List[APIKeyResponse]
    total: int


# ============= WITHDRAWAL SCHEMAS =============

class WithdrawalStatusEnum(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WithdrawalRequest(BaseModel):
    """Request to withdraw funds to an external wallet"""
    amount: float = Field(..., gt=0, description="Amount to withdraw")
    token: str = Field(..., description="Token symbol: USDC, USDT, or PYUSD")
    chain: str = Field(..., description="Blockchain: stellar, ethereum, polygon, base, tron")
    destination_address: str = Field(..., min_length=10, max_length=200, description="External wallet address")
    destination_memo: Optional[str] = Field(None, max_length=100, description="Memo for Stellar transactions")
    notes: Optional[str] = Field(None, max_length=500, description="Optional notes")

    class Config:
        json_schema_extra = {
            "example": {
                "amount": 50.00,
                "token": "USDC",
                "chain": "polygon",
                "destination_address": "0x1234567890abcdef1234567890abcdef12345678",
                "notes": "Monthly withdrawal"
            }
        }


class WithdrawalResponse(BaseModel):
    """Single withdrawal details"""
    id: str
    merchant_id: str
    amount: float
    token: str
    chain: str
    destination_address: str
    destination_memo: Optional[str] = None
    status: str
    tx_hash: Optional[str] = None
    network_fee: Optional[float] = None
    platform_fee: Optional[float] = None
    submitted_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    failed_reason: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    # Dual-currency
    amount_local: Optional[LocalCurrencyAmount] = None
    fee_local: Optional[LocalCurrencyAmount] = None

    class Config:
        from_attributes = True


class WithdrawalListResponse(BaseModel):
    """Paginated list of withdrawals"""
    withdrawals: List[WithdrawalResponse]
    total: int
    page: int
    per_page: int


class WithdrawalBalanceItem(BaseModel):
    """Balance for a specific token"""
    token: str
    available: float
    pending_withdrawals: float
    net_available: float
    # Local currency equivalents
    available_local: Optional[LocalCurrencyAmount] = None
    net_available_local: Optional[LocalCurrencyAmount] = None


class WithdrawalBalanceResponse(BaseModel):
    """Available balances for withdrawal"""
    balances: List[WithdrawalBalanceItem]
    total_available_usd: float
    total_available_local: Optional[LocalCurrencyAmount] = None
    local_currency: Optional[str] = None
    local_symbol: Optional[str] = None


class WithdrawalLimitInfo(BaseModel):
    """Withdrawal limits based on subscription tier"""
    tier: str
    daily_limit: float
    min_withdrawal: float
    max_per_transaction: float
    withdrawal_fee_percent: float
    withdrawal_fee_flat: float
    cooldown_minutes: int
    requires_2fa: bool
    daily_used: float
    daily_remaining: float
    # Local currency equivalents
    daily_limit_local: Optional[LocalCurrencyAmount] = None
    daily_used_local: Optional[LocalCurrencyAmount] = None
    daily_remaining_local: Optional[LocalCurrencyAmount] = None


# ============= BALANCE DASHBOARD SCHEMAS =============

class CoinBalance(BaseModel):
    """Balance for a single token across all chains"""
    token: str                          # USDC, USDT, PYUSD
    balance_usdc: float                 # Amount in token (≈ USD)
    balance_local: Optional[LocalCurrencyAmount] = None


class WalletBalance(BaseModel):
    """A merchant wallet with its chain and address"""
    chain: str                          # stellar, ethereum, polygon, base, tron
    wallet_address: str
    is_active: bool


class BalanceDashboardResponse(BaseModel):
    """
    Full balance dashboard: total balance, per-coin breakdown,
    wallet list — all in USDC + merchant's local currency.
    """
    # Totals
    total_balance_usdc: float
    total_balance_local: Optional[LocalCurrencyAmount] = None

    # Currency info
    local_currency: str                 # e.g. "INR"
    local_symbol: str                   # e.g. "₹"
    exchange_rate: float                # 1 USD → local

    # Per-coin breakdown
    coins: List[CoinBalance]

    # Wallet list
    wallets: List[WalletBalance]

    # Pending withdrawals total
    pending_withdrawals_usdc: float
    pending_withdrawals_local: Optional[LocalCurrencyAmount] = None

    # Net available (total - pending)
    net_available_usdc: float
    net_available_local: Optional[LocalCurrencyAmount] = None


# ============= PAYER DATA COLLECTION SCHEMAS =============

class PayerDataCollect(BaseModel):
    """Payer data submitted on the checkout page before payment."""
    email: Optional[EmailStr] = None
    name: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    billing_address_line1: Optional[str] = Field(None, max_length=255)
    billing_address_line2: Optional[str] = Field(None, max_length=255)
    billing_city: Optional[str] = Field(None, max_length=100)
    billing_state: Optional[str] = Field(None, max_length=100)
    billing_postal_code: Optional[str] = Field(None, max_length=20)
    billing_country: Optional[str] = Field(None, max_length=100)
    shipping_address_line1: Optional[str] = Field(None, max_length=255)
    shipping_city: Optional[str] = Field(None, max_length=100)
    shipping_state: Optional[str] = Field(None, max_length=100)
    shipping_postal_code: Optional[str] = Field(None, max_length=20)
    shipping_country: Optional[str] = Field(None, max_length=100)
    custom_fields: Optional[dict] = None


class PayerDataResponse(BaseModel):
    """Stored payer data returned to merchant."""
    email: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    billing_address_line1: Optional[str] = None
    billing_city: Optional[str] = None
    billing_state: Optional[str] = None
    billing_postal_code: Optional[str] = None
    billing_country: Optional[str] = None
    custom_fields: Optional[dict] = None
    class Config:
        from_attributes = True


# ============= PAYMENT TOKENIZATION SCHEMAS =============

class TokenizeCheckoutRequest(BaseModel):
    """Request to tokenize checkout session for secure transmission."""
    session_id: str


class TokenizeCheckoutResponse(BaseModel):
    """Tokenized checkout reference."""
    payment_token: str
    expires_in_seconds: int
    signature: str  # HMAC signature the frontend can verify


# ============= MRR / ARR ANALYTICS SCHEMAS =============

class MRRARRResponse(BaseModel):
    """Monthly & Annual Recurring Revenue summary."""
    mrr_usd: Decimal = Decimal("0")
    arr_usd: Decimal = Decimal("0")
    mrr_local: Optional[LocalCurrencyAmount] = None
    arr_local: Optional[LocalCurrencyAmount] = None
    active_subscriptions: int = 0
    new_this_period: int = 0
    churned_this_period: int = 0
    net_revenue_change_pct: Optional[Decimal] = None
    period: str = "month"


class MRRTrendPoint(BaseModel):
    """Single data point in MRR trend."""
    date: str  # ISO date
    mrr_usd: float
    subscription_count: int
    new: int = 0
    churned: int = 0


class MRRTrendResponse(BaseModel):
    """MRR trend over time."""
    points: List[MRRTrendPoint]
    period_months: int


# ============= PAYMENT TRACKING SCHEMAS =============

class PaymentTrackingResponse(BaseModel):
    """Extended payment tracking with timeline."""
    session_id: str
    status: str
    amount_fiat: float
    fiat_currency: str
    token: Optional[str] = None
    chain: Optional[str] = None
    tx_hash: Optional[str] = None
    block_number: Optional[int] = None
    confirmations: Optional[int] = None
    payer_email: Optional[str] = None
    payer_name: Optional[str] = None
    created_at: datetime
    paid_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    events: List[dict] = []  # timeline of PaymentEvent records


class SubscriptionTrackingResponse(BaseModel):
    """Extended subscription tracking."""
    id: str
    plan_name: str
    customer_email: str
    customer_name: Optional[str] = None
    status: str
    current_period_start: datetime
    current_period_end: datetime
    next_payment_at: Optional[datetime] = None
    last_payment_at: Optional[datetime] = None
    failed_payment_count: int = 0
    total_paid_usd: float = 0
    payment_count: int = 0
    events: List[dict] = []

