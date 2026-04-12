import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Numeric, Enum as SQLEnum, Integer, Text, JSON, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum
from app.core.database import Base


# ============= ENUMS =============

class PaymentStatus(str, enum.Enum):
    CREATED = "CREATED"
    PENDING = "PENDING"  # Payment detected, waiting confirmations
    PROCESSING = "PROCESSING"  # Payment being verified on-chain
    CONFIRMED = "CONFIRMED"  # Fully confirmed (alias kept for clarity)
    PAID = "PAID"  # Legacy alias for CONFIRMED — kept for backward compat
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"


class BlockchainNetwork(str, enum.Enum):
    """Supported blockchain networks"""
    STELLAR = "stellar"
    ETHEREUM = "ethereum"
    POLYGON = "polygon"
    BASE = "base"
    TRON = "tron"
    SOLANA = "solana"


class TokenSymbol(str, enum.Enum):
    """Supported stablecoin tokens"""
    USDC = "USDC"
    USDT = "USDT"
    PYUSD = "PYUSD"


class InvoiceStatus(str, enum.Enum):
    """Invoice status"""
    DRAFT = "draft"
    SENT = "sent"
    VIEWED = "viewed"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class SubscriptionStatus(str, enum.Enum):
    """Subscription status"""
    ACTIVE = "ACTIVE"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"
    PAST_DUE = "PAST_DUE"
    TRIALING = "TRIALING"


class SubscriptionInterval(str, enum.Enum):
    """Billing interval"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class RefundStatus(str, enum.Enum):
    """Refund status"""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    QUEUED = "QUEUED"  # Waiting for merchant to have sufficient funds
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"  # Blocked due to low balance


class WithdrawalStatus(str, enum.Enum):
    """Withdrawal request status"""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class MerchantCategory(str, enum.Enum):
    """Merchant business categories"""
    INDIVIDUAL = "individual"
    STARTUP = "startup"
    SMALL_BUSINESS = "small_business"
    ENTERPRISE = "enterprise"
    NGO = "ngo"


class MerchantRole(str, enum.Enum):
    """Merchant team roles"""
    OWNER = "owner"
    ADMIN = "admin"
    DEVELOPER = "developer"
    FINANCE = "finance"
    VIEWER = "viewer"


class SubscriptionTier(str, enum.Enum):
    """Subscription tier levels"""
    FREE = "free"
    GROWTH = "growth"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


class MerchantSubscriptionStatus(str, enum.Enum):
    """Merchant subscription status"""
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    TRIALING = "trialing"


class EventType(str, enum.Enum):
    """Event types for event queue"""
    PAYMENT_CREATED = "payment.created"
    PAYMENT_PENDING = "payment.pending"
    PAYMENT_CONFIRMED = "payment.confirmed"
    PAYMENT_FAILED = "payment.failed"
    INVOICE_CREATED = "invoice.created"
    INVOICE_SENT = "invoice.sent"
    INVOICE_PAID = "invoice.paid"
    INVOICE_OVERDUE = "invoice.overdue"
    SUBSCRIPTION_CREATED = "subscription.created"
    SUBSCRIPTION_RENEWED = "subscription.renewed"
    SUBSCRIPTION_CANCELLED = "subscription.cancelled"
    REFUND_INITIATED = "refund.initiated"
    REFUND_COMPLETED = "refund.completed"
    WEBHOOK_SENT = "webhook.sent"
    WEBHOOK_FAILED = "webhook.failed"


# ============= TOKEN REGISTRY =============

class Token(Base):
    """Registry of supported tokens across all chains"""
    __tablename__ = "tokens"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(10), nullable=False, index=True)  # USDC, USDT, PYUSD
    name = Column(String(50), nullable=False)  # Full name
    chain = Column(SQLEnum(BlockchainNetwork), nullable=False, index=True)
    contract_address = Column(String(100), nullable=False)  # Token contract address
    decimals = Column(Integer, nullable=False, default=6)
    is_active = Column(Boolean, default=True, nullable=False)
    icon_url = Column(String, nullable=True)  # Token icon
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Unique constraint: one token per chain
    __table_args__ = (
        # UniqueConstraint('symbol', 'chain', name='uq_token_chain'),
    )


# ============= MERCHANT =============

class Merchant(Base):
    __tablename__ = "merchants"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=True)  # Nullable for Google OAuth users
    api_key = Column(String, unique=True, nullable=True, index=True)
    
    # Google OAuth
    google_id = Column(String(255), unique=True, nullable=True, index=True)
    avatar_url = Column(String(500), nullable=True)
    
    # Onboarding
    merchant_category = Column(String(50), default="individual")
    business_name = Column(String(255), nullable=True)
    business_email = Column(String(255), nullable=True)
    country = Column(String(100), nullable=True)
    onboarding_completed = Column(Boolean, default=False)
    onboarding_step = Column(Integer, default=0)  # 0=signup, 1=business_details, 2=wallets, 3=complete
    
    # Legacy Stellar address (kept for backward compatibility)
    stellar_address = Column(String, nullable=True)
    
    webhook_url = Column(String, nullable=True)
    webhook_secret = Column(String, nullable=True)  # For webhook signature verification
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Default accepted tokens/chains (can be overridden per session)
    accepted_tokens = Column(JSON, nullable=True)  # ["USDC", "USDT"]
    accepted_chains = Column(JSON, nullable=True)  # ["polygon", "ethereum"]
    
    # Subscription tier
    subscription_tier = Column(String(20), default="free", nullable=False)  # free, growth, business, enterprise
    
    # Currency preferences (derived from country during onboarding)
    base_currency = Column(String(10), default="USD", nullable=False)
    currency_symbol = Column(String(10), default="$", nullable=False)
    currency_name = Column(String(50), default="US Dollar", nullable=False)
    
    # Currency formatting preferences (for backend-driven currency handling)
    currency_preference = Column(String(10), default="USD", nullable=False, index=True)  # ISO 4217 code
    currency_locale = Column(String(10), default="en_US", nullable=False)  # Locale for formatting
    currency_decimal_places = Column(Integer, default=2, nullable=False)  # Decimal precision
    
    # Balance tracking
    balance_usdc = Column(Numeric(precision=20, scale=8), default=0, nullable=False)
    balance_usdt = Column(Numeric(precision=20, scale=8), default=0, nullable=False)
    balance_pyusd = Column(Numeric(precision=20, scale=8), default=0, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    payment_sessions = relationship("PaymentSession", back_populates="merchant")
    wallets = relationship("MerchantWallet", back_populates="merchant", cascade="all, delete-orphan")
    subscription = relationship("MerchantSubscription", back_populates="merchant", uselist=False)
    withdrawals = relationship("Withdrawal", back_populates="merchant", cascade="all, delete-orphan")


class MerchantWallet(Base):
    """Merchant wallets per blockchain"""
    __tablename__ = "merchant_wallets"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    chain = Column(SQLEnum(BlockchainNetwork), nullable=False)
    wallet_address = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    merchant = relationship("Merchant", back_populates="wallets")
    
    # Unique constraint: one wallet per chain per merchant
    __table_args__ = (
        # UniqueConstraint('merchant_id', 'chain', name='uq_merchant_chain'),
    )


# ============= MERCHANT SUBSCRIPTION =============

class MerchantSubscription(Base):
    """Merchant subscription plans and billing"""
    __tablename__ = "merchant_subscriptions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False, unique=True)
    
    # Subscription details
    tier = Column(String(20), default="free", nullable=False)
    status = Column(String(20), default="active", nullable=False)
    
    # Billing
    monthly_price = Column(Numeric(precision=10, scale=2), default=0, nullable=False)  # USD
    transaction_fee_percent = Column(Numeric(precision=4, scale=2), default=1.5, nullable=False)  # 1.5%
    
    # Limits
    monthly_volume_limit = Column(Numeric(precision=14, scale=2), nullable=True)  # null = unlimited
    payment_link_limit = Column(Integer, nullable=True)  # null = unlimited
    invoice_limit = Column(Integer, nullable=True)  # null = unlimited
    team_member_limit = Column(Integer, default=1, nullable=False)
    
    # Usage this billing period
    current_volume = Column(Numeric(precision=14, scale=2), default=0, nullable=False)
    current_payment_links = Column(Integer, default=0, nullable=False)
    current_invoices = Column(Integer, default=0, nullable=False)
    
    # Dates
    trial_ends_at = Column(DateTime, nullable=True)
    current_period_start = Column(DateTime, default=datetime.utcnow, nullable=False)
    current_period_end = Column(DateTime, nullable=False)
    cancelled_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    merchant = relationship("Merchant", back_populates="subscription")


# ============= PAYMENT SESSION =============

class PaymentSession(Base):
    __tablename__ = "payment_sessions"
    
    id = Column(String, primary_key=True)  # pay_xxx format
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    
    # Amount information
    amount_fiat = Column(Numeric(precision=10, scale=2), nullable=False)
    fiat_currency = Column(String(10), nullable=False, default="USD")
    amount_token = Column(String, nullable=False)  # Renamed from amount_usdc
    
    # Legacy field (kept for backward compatibility)
    amount_usdc = Column(String, nullable=True)
    
    # Multi-chain fields
    token = Column(String(10), nullable=True, default="USDC")  # USDC, USDT, PYUSD
    chain = Column(String(20), nullable=True, default="stellar")  # Selected chain
    accepted_tokens = Column(JSON, nullable=True)  # ["USDC", "USDT", "PYUSD"]
    accepted_chains = Column(JSON, nullable=True)  # ["stellar", "polygon", "ethereum"]
    
    # Payment destination
    merchant_wallet = Column(String(100), nullable=True)  # Destination wallet for selected chain
    deposit_address = Column(String(100), nullable=True)  # Generated deposit address (for EVM HD wallets)
    
    # Status
    status = Column(SQLEnum(PaymentStatus), default=PaymentStatus.CREATED, nullable=False)
    
    # URLs
    success_url = Column(String, nullable=False)
    cancel_url = Column(String, nullable=False)
    
    # Transaction details
    tx_hash = Column(String, nullable=True)
    block_number = Column(Integer, nullable=True)
    confirmations = Column(Integer, nullable=True, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    payment_started_at = Column(DateTime, nullable=True)  # When user starts payment (opens checkout page or initiates payment)
    expires_at = Column(DateTime, nullable=True)  # Calculated as payment_started_at + 15 minutes
    paid_at = Column(DateTime, nullable=True)
    
    # Metadata
    order_id = Column(String, nullable=True)  # Merchant's order ID
    session_metadata = Column(JSON, nullable=True)  # Additional metadata
    
    # Payer data collection
    collect_payer_data = Column(Boolean, default=True)  # Require payer info before payment
    payer_email = Column(String(255), nullable=True)
    payer_name = Column(String(255), nullable=True)
    
    # Tokenization
    payment_token = Column(String(100), nullable=True, index=True)  # ptok_xxx
    is_tokenized = Column(Boolean, default=False, nullable=False)  # Whether session has been tokenized
    token_created_at = Column(DateTime, nullable=True)  # When payment token was generated
    
    # Coupon / Promo code tracking
    coupon_code = Column(String(50), nullable=True)
    discount_amount = Column(Numeric(precision=14, scale=2), nullable=True)
    
    # ── Dual Currency (payer + merchant) ──
    payer_currency = Column(String(10), nullable=True)  # Payer's local currency (e.g. "EUR")
    payer_currency_symbol = Column(String(10), nullable=True)  # e.g. "€"
    payer_amount_local = Column(Numeric(precision=14, scale=2), nullable=True)  # Amount in payer's currency
    payer_exchange_rate = Column(Numeric(precision=18, scale=8), nullable=True)  # payer currency to USD rate
    merchant_currency = Column(String(10), nullable=True)  # Merchant's base currency (e.g. "INR")
    merchant_currency_symbol = Column(String(10), nullable=True)  # e.g. "₹"
    merchant_amount_local = Column(Numeric(precision=14, scale=2), nullable=True)  # Amount in merchant's currency
    merchant_exchange_rate = Column(Numeric(precision=18, scale=8), nullable=True)  # merchant currency to USD rate
    
    # ── Cross-border / Compliance ──
    is_cross_border = Column(Boolean, default=False, nullable=False)  # Payer and merchant in different countries
    payer_country = Column(String(100), nullable=True)  # Payer's country (from billing address)
    risk_score = Column(Numeric(precision=5, scale=2), nullable=True)  # Fraud risk score (0-100)
    risk_flags = Column(JSON, nullable=True)  # List of risk flags triggered
    
    # Relationships
    merchant = relationship("Merchant", back_populates="payment_sessions")


# ============= ADMIN =============

class Admin(Base):
    __tablename__ = "admins"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# ============= PAYMENT EVENTS (Audit Log) =============

class PaymentEvent(Base):
    """Audit log for payment events"""
    __tablename__ = "payment_events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String, ForeignKey("payment_sessions.id"), nullable=False)
    event_type = Column(String(50), nullable=False)  # created, pending, paid, expired, webhook_sent
    chain = Column(String(20), nullable=True)
    tx_hash = Column(String, nullable=True)
    details = Column(JSON, nullable=True)  # Event-specific details
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# ============= PAYMENT LINKS =============

class PaymentLink(Base):
    """Reusable payment links for merchants"""
    __tablename__ = "payment_links"
    
    id = Column(String, primary_key=True)  # link_xxx format
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    
    # Link details
    name = Column(String(100), nullable=False)  # Internal name
    description = Column(Text, nullable=True)
    
    # Amount (optional - can be fixed or customer-entered)
    amount_fiat = Column(Numeric(precision=10, scale=2), nullable=True)
    fiat_currency = Column(String(10), nullable=False, default="USD")
    is_amount_fixed = Column(Boolean, default=True)  # If False, customer enters amount
    min_amount = Column(Numeric(precision=10, scale=2), nullable=True)
    max_amount = Column(Numeric(precision=10, scale=2), nullable=True)
    
    # Payment options
    accepted_tokens = Column(JSON, nullable=True)  # ["USDC", "USDT"]
    accepted_chains = Column(JSON, nullable=True)  # ["polygon", "ethereum"]
    
    # URLs
    success_url = Column(String, nullable=True)
    cancel_url = Column(String, nullable=True)
    
    # Configuration
    is_active = Column(Boolean, default=True, nullable=False)
    is_single_use = Column(Boolean, default=False)  # Deactivate after first use
    expires_at = Column(DateTime, nullable=True)
    
    # Analytics
    view_count = Column(Integer, default=0)
    payment_count = Column(Integer, default=0)
    total_collected_usd = Column(Numeric(precision=14, scale=2), default=0)
    
    # Metadata
    link_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    merchant = relationship("Merchant")
    payments = relationship("PaymentSession", secondary="payment_link_sessions")


# Junction table for payment links and sessions
class PaymentLinkSession(Base):
    """Links payment sessions to payment links"""
    __tablename__ = "payment_link_sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_link_id = Column(String, ForeignKey("payment_links.id"), nullable=False)
    session_id = Column(String, ForeignKey("payment_sessions.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# ============= INVOICES =============

class Invoice(Base):
    """Invoice system for merchants"""
    __tablename__ = "invoices"
    
    id = Column(String, primary_key=True)  # inv_xxx format
    invoice_number = Column(String(50), nullable=False)  # INV-001, merchant's numbering
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    
    # Customer info
    customer_email = Column(String, nullable=False)
    customer_name = Column(String, nullable=True)
    customer_address = Column(Text, nullable=True)
    
    # Invoice details
    description = Column(Text, nullable=True)
    line_items = Column(JSON, nullable=True)  # [{description, quantity, unit_price, total}]
    
    # Amounts
    subtotal = Column(Numeric(precision=14, scale=2), nullable=False)
    tax = Column(Numeric(precision=14, scale=2), default=0)
    discount = Column(Numeric(precision=14, scale=2), default=0)
    total = Column(Numeric(precision=14, scale=2), nullable=False)
    fiat_currency = Column(String(10), default="USD")
    
    # Payment options
    accepted_tokens = Column(JSON, nullable=True)
    accepted_chains = Column(JSON, nullable=True)
    
    # Status & Dates
    status = Column(SQLEnum(InvoiceStatus), default=InvoiceStatus.DRAFT, nullable=False)
    issue_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    due_date = Column(DateTime, nullable=False)
    sent_at = Column(DateTime, nullable=True)
    viewed_at = Column(DateTime, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    
    # Payment tracking
    payment_session_id = Column(String, ForeignKey("payment_sessions.id"), nullable=True)
    amount_paid = Column(Numeric(precision=14, scale=2), default=0)
    
    # ── Blockchain / On-chain details ──
    tx_hash = Column(String, nullable=True)  # Blockchain transaction hash
    chain = Column(String(20), nullable=True)  # e.g. polygon, ethereum
    token_symbol = Column(String(10), nullable=True)  # USDC, USDT, PYUSD
    token_amount = Column(String, nullable=True)  # On-chain token amount
    
    # ── Multi-currency (payer + merchant) ──
    payer_currency = Column(String(10), nullable=True)  # e.g. EUR
    payer_amount_local = Column(Numeric(precision=14, scale=2), nullable=True)
    merchant_currency = Column(String(10), nullable=True)  # e.g. INR
    merchant_amount_local = Column(Numeric(precision=14, scale=2), nullable=True)
    
    # Notifications
    reminder_sent = Column(Boolean, default=False)
    overdue_sent = Column(Boolean, default=False)
    
    # Metadata
    notes = Column(Text, nullable=True)  # Private notes
    terms = Column(Text, nullable=True)  # Payment terms
    footer = Column(Text, nullable=True)  # Invoice footer
    invoice_metadata = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    merchant = relationship("Merchant")
    payment_session = relationship("PaymentSession")


# ============= SUBSCRIPTIONS =============

class SubscriptionPlan(Base):
    """Subscription plans defined by merchants"""
    __tablename__ = "subscription_plans"
    
    id = Column(String, primary_key=True)  # plan_xxx format
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    
    # Plan details
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    
    # Pricing
    amount = Column(Numeric(precision=10, scale=2), nullable=False)
    fiat_currency = Column(String(10), default="USD")
    interval = Column(SQLEnum(SubscriptionInterval), nullable=False)
    interval_count = Column(Integer, default=1)  # e.g., 2 for bi-weekly
    
    # Trial
    trial_days = Column(Integer, default=0)
    trial_type = Column(String(20), default="free")  # free, reduced_price
    trial_price = Column(Numeric(precision=10, scale=2), nullable=True)  # Price during trial (for reduced_price type)
    
    # Setup fee (one-time charge at subscription start)
    setup_fee = Column(Numeric(precision=10, scale=2), default=0)
    
    # Payment options
    accepted_tokens = Column(JSON, nullable=True)
    accepted_chains = Column(JSON, nullable=True)
    
    # Configuration
    is_active = Column(Boolean, default=True, nullable=False)
    max_billing_cycles = Column(Integer, nullable=True)  # null = unlimited
    
    # Metadata
    features = Column(JSON, nullable=True)  # ["Feature 1", "Feature 2"]
    plan_metadata = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    merchant = relationship("Merchant")
    subscriptions = relationship("Subscription", back_populates="plan")


class Subscription(Base):
    """Active subscriptions"""
    __tablename__ = "subscriptions"
    
    id = Column(String, primary_key=True)  # sub_xxx format
    plan_id = Column(String, ForeignKey("subscription_plans.id"), nullable=False)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    
    # Subscriber info
    customer_email = Column(String, nullable=False)
    customer_name = Column(String, nullable=True)
    customer_id = Column(String, nullable=True)  # Merchant's customer ID
    
    # Status
    status = Column(
        SQLEnum(
            SubscriptionStatus,
            name="subscription_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            validate_strings=True,
        ),
        default=SubscriptionStatus.ACTIVE.value,
    )
    
    # Billing cycle
    current_period_start = Column(DateTime, nullable=False)
    current_period_end = Column(DateTime, nullable=False)
    billing_anchor = Column(DateTime, nullable=False)  # Reference date for billing
    
    # Trial
    trial_start = Column(DateTime, nullable=True)
    trial_end = Column(DateTime, nullable=True)
    trial_reminder_sent = Column(Boolean, default=False)  # Reminder before trial ends
    trial_converted_at = Column(DateTime, nullable=True)  # When trial converted to paid
    
    # Payment tracking
    last_payment_at = Column(DateTime, nullable=True)
    next_payment_at = Column(DateTime, nullable=True)
    failed_payment_count = Column(Integer, default=0)
    total_payments_collected = Column(Integer, default=0)  # Total successful billing cycles
    total_revenue = Column(Numeric(precision=14, scale=2), default=0)  # Total revenue from this subscription
    
    # Customer payment method
    customer_wallet_address = Column(String(200), nullable=True)  # Customer's wallet for auto-billing
    customer_chain = Column(String(20), nullable=True)  # Customer's preferred chain
    customer_token = Column(String(10), nullable=True)  # Customer's preferred token
    
    # Cancellation
    cancel_at = Column(DateTime, nullable=True)  # Future cancellation date
    cancelled_at = Column(DateTime, nullable=True)  # When cancellation was requested
    cancel_reason = Column(String, nullable=True)
    
    # Billing config
    max_payment_retries = Column(Integer, default=3)  # Max retries for failed payments
    grace_period_days = Column(Integer, default=3)  # Days before marking past_due
    
    # Metadata
    subscription_metadata = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    plan = relationship("SubscriptionPlan", back_populates="subscriptions")
    merchant = relationship("Merchant")
    payments = relationship("SubscriptionPayment", back_populates="subscription")


class SubscriptionPayment(Base):
    """Individual subscription payment records"""
    __tablename__ = "subscription_payments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id = Column(String, ForeignKey("subscriptions.id"), nullable=False)
    payment_session_id = Column(String, ForeignKey("payment_sessions.id"), nullable=True)
    invoice_id = Column(String, ForeignKey("invoices.id"), nullable=True)
    
    # Payment period
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    
    # Amount
    amount = Column(Numeric(precision=10, scale=2), nullable=False)
    fiat_currency = Column(String(10), default="USD")
    
    # Status
    status = Column(SQLEnum(PaymentStatus), default=PaymentStatus.CREATED)
    paid_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    subscription = relationship("Subscription", back_populates="payments")
    payment_session = relationship("PaymentSession")
    invoice = relationship("Invoice")


# ============= REFUNDS =============

class Refund(Base):
    """Refund records"""
    __tablename__ = "refunds"
    
    id = Column(String, primary_key=True)  # ref_xxx format
    payment_session_id = Column(String, ForeignKey("payment_sessions.id"), nullable=False)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    
    # Refund details
    amount = Column(Numeric(precision=14, scale=6), nullable=False)  # In token amount
    token = Column(String(10), nullable=False)
    chain = Column(String(20), nullable=False)
    
    # Destination
    refund_address = Column(String(100), nullable=False)  # Customer's refund address
    
    # Status
    status = Column(SQLEnum(RefundStatus), default=RefundStatus.PENDING)
    
    # Transaction
    tx_hash = Column(String, nullable=True)
    
    # Reason
    reason = Column(Text, nullable=True)
    
    # Refund source & balance tracking
    refund_source = Column(String(30), default="platform_balance")  # platform_balance, external_wallet
    merchant_balance_at_request = Column(Numeric(precision=20, scale=8), nullable=True)  # Snapshot of balance when requested
    settlement_status = Column(String(30), nullable=True)  # in_platform, settled_external, partially_settled
    insufficient_funds_at = Column(DateTime, nullable=True)  # When insufficient funds was detected
    queued_until = Column(DateTime, nullable=True)  # Auto-cancel queued refund after this date
    failure_reason = Column(String(500), nullable=True)  # Detailed failure reason
    
    # Initiated by
    initiated_by = Column(UUID(as_uuid=True), nullable=True)  # MerchantUser ID
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    payment_session = relationship("PaymentSession")
    merchant = relationship("Merchant")


# ============= MERCHANT TEAM =============

class MerchantUser(Base):
    """Team members for merchant accounts"""
    __tablename__ = "merchant_users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    
    # User info
    email = Column(String, nullable=False)
    name = Column(String, nullable=True)
    password_hash = Column(String, nullable=True)  # Null if invite pending
    
    # Role
    role = Column(SQLEnum(MerchantRole), default=MerchantRole.VIEWER)
    
    # Status
    is_active = Column(Boolean, default=True)
    invite_token = Column(String, nullable=True)
    invite_expires = Column(DateTime, nullable=True)
    last_login = Column(DateTime, nullable=True)
    
    # Password reset
    password_reset_token = Column(String(255), nullable=True)
    password_reset_expires_at = Column(DateTime, nullable=True)
    
    # Security
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)
    
    # Audit
    created_by = Column(UUID(as_uuid=True), ForeignKey("merchant_users.id"), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    merchant = relationship("Merchant")
    creator = relationship("MerchantUser", remote_side=[id], foreign_keys=[created_by])
    sessions = relationship("TeamMemberSession", back_populates="team_member", cascade="all, delete-orphan")
    custom_permissions = relationship("TeamMemberPermission", foreign_keys="TeamMemberPermission.team_member_id", cascade="all, delete-orphan")
    activity_logs = relationship("ActivityLog", back_populates="team_member")
    
    __table_args__ = (
        UniqueConstraint('merchant_id', 'email', name='uq_merchant_user_email'),
        Index('idx_merchant_users_reset_token', 'password_reset_token'),
    )


# ============= IDEMPOTENCY =============

class IdempotencyKey(Base):
    """Idempotency keys for preventing duplicate operations"""
    __tablename__ = "idempotency_keys"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(100), nullable=False, unique=True, index=True)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    
    # Request info
    endpoint = Column(String(200), nullable=False)
    request_hash = Column(String(64), nullable=True)  # SHA256 of request body
    
    # Response
    response_code = Column(Integer, nullable=True)
    response_body = Column(JSON, nullable=True)
    
    # Status
    is_processing = Column(Boolean, default=False)
    completed = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)  # Keys expire after 24 hours
    
    # Relationships
    merchant = relationship("Merchant")
    
    __table_args__ = (
        Index('ix_idempotency_merchant_key', 'merchant_id', 'key'),
    )


# ============= EVENT QUEUE =============

class Event(Base):
    """Event queue for async processing"""
    __tablename__ = "events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=True)
    
    # Event info
    event_type = Column(String(50), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False)  # payment, invoice, subscription
    entity_id = Column(String, nullable=False)
    
    # Payload
    payload = Column(JSON, nullable=False)
    
    # Processing status
    status = Column(String(20), default="pending")  # pending, processing, completed, failed
    attempts = Column(Integer, default=0)
    last_attempt = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Timing
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    processed_at = Column(DateTime, nullable=True)
    scheduled_for = Column(DateTime, nullable=True)  # For delayed processing
    
    __table_args__ = (
        Index('ix_events_status_created', 'status', 'created_at'),
    )


# ============= WEBHOOK DELIVERIES =============

class WebhookDelivery(Base):
    """Track webhook delivery attempts"""
    __tablename__ = "webhook_deliveries"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=True)
    
    # Webhook details
    url = Column(String, nullable=False)
    event_type = Column(String(50), nullable=False)
    payload = Column(JSON, nullable=False)
    
    # Delivery status
    status = Column(String(20), default="pending")  # pending, success, failed
    http_status = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    
    # Attempts
    attempt_count = Column(Integer, default=0)
    next_retry = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    delivered_at = Column(DateTime, nullable=True)
    
    # Relationships
    merchant = relationship("Merchant")


# ============= MERCHANT ANALYTICS =============

class AnalyticsSnapshot(Base):
    """Daily analytics snapshots for merchants"""
    __tablename__ = "analytics_snapshots"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    
    # Time period
    date = Column(DateTime, nullable=False)  # Date of snapshot
    period = Column(String(20), default="daily")  # daily, weekly, monthly
    
    # Payment metrics
    total_payments = Column(Integer, default=0)
    successful_payments = Column(Integer, default=0)
    failed_payments = Column(Integer, default=0)
    
    # Volume
    total_volume_usd = Column(Numeric(precision=14, scale=2), default=0)
    
    # By token
    volume_by_token = Column(JSON, nullable=True)  # {"USDC": 1000, "USDT": 500}
    payments_by_token = Column(JSON, nullable=True)
    
    # By chain
    volume_by_chain = Column(JSON, nullable=True)  # {"polygon": 800, "ethereum": 700}
    payments_by_chain = Column(JSON, nullable=True)
    
    # Conversions
    sessions_created = Column(Integer, default=0)
    conversion_rate = Column(Numeric(precision=5, scale=2), nullable=True)  # Percentage
    
    # Averages
    avg_payment_usd = Column(Numeric(precision=10, scale=2), nullable=True)
    avg_confirmation_time = Column(Integer, nullable=True)  # Seconds
    
    # Invoices
    invoices_sent = Column(Integer, default=0)
    invoices_paid = Column(Integer, default=0)
    invoice_volume_usd = Column(Numeric(precision=14, scale=2), default=0)
    
    # Subscriptions
    active_subscriptions = Column(Integer, default=0)
    new_subscriptions = Column(Integer, default=0)
    churned_subscriptions = Column(Integer, default=0)
    subscription_revenue_usd = Column(Numeric(precision=14, scale=2), default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    merchant = relationship("Merchant")
    
    __table_args__ = (
        UniqueConstraint('merchant_id', 'date', 'period', name='uq_analytics_merchant_date'),
        Index('ix_analytics_merchant_date', 'merchant_id', 'date'),
    )


# ============= FRAUD & RISK =============

class RiskSignal(Base):
    """Risk signals for fraud detection"""
    __tablename__ = "risk_signals"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=True)
    payment_session_id = Column(String, ForeignKey("payment_sessions.id"), nullable=True)
    
    # Signal details
    signal_type = Column(String(50), nullable=False)  # high_frequency, suspicious_wallet, duplicate_attempt
    severity = Column(String(20), default="low")  # low, medium, high, critical
    
    # Context
    wallet_address = Column(String(100), nullable=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String, nullable=True)
    
    # Details
    description = Column(Text, nullable=True)
    details = Column(JSON, nullable=True)
    
    # Action taken
    action_taken = Column(String(50), nullable=True)  # blocked, flagged, allowed
    reviewed = Column(Boolean, default=False)
    reviewed_by = Column(UUID(as_uuid=True), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# ============= WITHDRAWALS =============

class Withdrawal(Base):
    """Withdrawal requests to external wallets"""
    __tablename__ = "withdrawals"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    
    # Amount
    amount = Column(Numeric(precision=20, scale=8), nullable=False)
    token = Column(String(10), nullable=False)  # USDC, USDT, PYUSD
    chain = Column(String(20), nullable=False)  # stellar, ethereum, polygon, base, tron
    
    # Destination
    destination_address = Column(String(200), nullable=False)
    destination_memo = Column(String(100), nullable=True)  # For Stellar
    
    # Status
    status = Column(String(20), default="pending", nullable=False)  # pending, processing, completed, failed, cancelled
    
    # Transaction details
    tx_hash = Column(String(200), nullable=True)
    network_fee = Column(Numeric(precision=20, scale=8), nullable=True)
    platform_fee = Column(Numeric(precision=20, scale=8), default=0)
    
    # Processing
    submitted_at = Column(DateTime, nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    failed_reason = Column(String(500), nullable=True)
    
    # Metadata
    notes = Column(String(500), nullable=True)
    ip_address = Column(String(45), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    merchant = relationship("Merchant", back_populates="withdrawals")
    
    # Indexes
    __table_args__ = (
        Index('idx_withdrawals_merchant_id', 'merchant_id'),
        Index('idx_withdrawals_status', 'status'),
        Index('idx_withdrawals_chain', 'chain'),
        Index('idx_withdrawals_created_at', 'created_at'),
    )


class WithdrawalLimit(Base):
    """Withdrawal limits per subscription tier"""
    __tablename__ = "withdrawal_limits"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tier = Column(String(20), nullable=False, unique=True)  # free, growth, business, enterprise
    daily_limit = Column(Numeric(precision=20, scale=8), nullable=False)
    min_withdrawal = Column(Numeric(precision=20, scale=8), nullable=False)
    max_per_transaction = Column(Numeric(precision=20, scale=8), nullable=False)
    withdrawal_fee_percent = Column(Numeric(precision=5, scale=2), default=0)
    withdrawal_fee_flat = Column(Numeric(precision=10, scale=2), default=0)
    cooldown_minutes = Column(Integer, default=0)
    requires_2fa = Column(Boolean, default=False)


# ============= API KEYS =============

class APIKey(Base):
    """API keys for merchant access"""
    __tablename__ = "api_keys"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    
    # Key details
    key_prefix = Column(String(10), nullable=False)  # pk_live_, pk_test_
    key_hash = Column(String, nullable=False)  # Hashed key for validation
    name = Column(String(100), nullable=True)  # Optional label
    
    # Permissions
    permissions = Column(JSON, nullable=True)  # ["payments:read", "payments:write"]
    
    # Status
    is_active = Column(Boolean, default=True)
    last_used = Column(DateTime, nullable=True)
    
    # Rate limiting
    rate_limit = Column(Integer, default=100)  # Requests per minute
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    
    # Relationships
    merchant = relationship("Merchant")


# ============= PAYER INFO =============

class PayerInfo(Base):
    """Collected payer/customer data for a payment session"""
    __tablename__ = "payer_info"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String, ForeignKey("payment_sessions.id"), nullable=False, index=True)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False, index=True)

    # Contact
    email = Column(String(255), nullable=True)
    name = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)

    # Billing address
    billing_address_line1 = Column(String(255), nullable=True)
    billing_address_line2 = Column(String(255), nullable=True)
    billing_city = Column(String(100), nullable=True)
    billing_state = Column(String(100), nullable=True)
    billing_postal_code = Column(String(20), nullable=True)
    billing_country = Column(String(100), nullable=True)

    # Shipping address (optional)
    shipping_address_line1 = Column(String(255), nullable=True)
    shipping_city = Column(String(100), nullable=True)
    shipping_state = Column(String(100), nullable=True)
    shipping_postal_code = Column(String(20), nullable=True)
    shipping_country = Column(String(100), nullable=True)

    # Metadata
    custom_fields = Column(JSON, nullable=True)  # merchant-defined extra fields

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    payment_session = relationship("PaymentSession", backref="payer_info_rel")
    merchant = relationship("Merchant")


# ============= PROMO CODES =============

class PromoCodeType(str, enum.Enum):
    PERCENTAGE = "percentage"
    FIXED = "fixed"


class PromoCodeStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DELETED = "deleted"


class PromoCode(Base):
    """Merchant promo/coupon codes"""
    __tablename__ = "promo_codes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)

    code = Column(String(50), nullable=False)
    type = Column(String(20), nullable=False)  # percentage, fixed
    discount_value = Column(Numeric(precision=14, scale=2), nullable=False)
    max_discount_amount = Column(Numeric(precision=14, scale=2), nullable=True)
    min_order_amount = Column(Numeric(precision=14, scale=2), default=0)

    usage_limit_total = Column(Integer, nullable=True)
    usage_limit_per_user = Column(Integer, nullable=True)
    used_count = Column(Integer, default=0, nullable=False)

    start_date = Column(DateTime, nullable=False)
    expiry_date = Column(DateTime, nullable=False)
    status = Column(String(20), default="active", nullable=False)  # active, inactive, deleted

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    merchant = relationship("Merchant")
    usage_records = relationship("PromoCodeUsage", back_populates="promo_code", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('merchant_id', 'code', name='uq_promo_merchant_code'),
        Index('idx_promo_codes_merchant_id', 'merchant_id'),
        Index('idx_promo_codes_code', 'code'),
        Index('idx_promo_codes_status', 'status'),
    )


class PromoCodeUsage(Base):
    """Tracks individual coupon usage"""
    __tablename__ = "promo_code_usage"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    promo_code_id = Column(UUID(as_uuid=True), ForeignKey("promo_codes.id"), nullable=False)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    customer_id = Column(String(255), nullable=False)
    payment_id = Column(String(255), nullable=True)
    discount_applied = Column(Numeric(precision=14, scale=2), nullable=False)
    used_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    promo_code = relationship("PromoCode", back_populates="usage_records")
    merchant = relationship("Merchant")

    __table_args__ = (
        Index('idx_promo_usage_code_id', 'promo_code_id'),
        Index('idx_promo_usage_customer', 'promo_code_id', 'customer_id'),
        Index('idx_promo_usage_merchant', 'merchant_id'),
    )


# ============= WEB3 SUBSCRIPTION ENUMS =============

class Web3SubscriptionStatus(str, enum.Enum):
    PENDING_PAYMENT = "pending_payment"  # Awaiting first payment before activation
    ACTIVE = "active"
    PAST_DUE = "past_due"
    PAUSED = "paused"           # Suspended after grace period exceeded
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class MandateStatus(str, enum.Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


class RelayerTxStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REVERTED = "reverted"
    FAILED = "failed"


# ============= WEB3 SUBSCRIPTION MODELS =============

class SubscriptionMandate(Base):
    """EIP-712 signed authorization from a subscriber for recurring payments"""
    __tablename__ = "subscription_mandates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscriber_address = Column(String(42), nullable=False, index=True)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    signature = Column(Text, nullable=False)
    nonce = Column(Integer, nullable=False, default=0)
    chain = Column(String(50), nullable=False)
    token_address = Column(String(42), nullable=False)
    token_symbol = Column(String(20), nullable=False)
    amount = Column(Numeric(precision=18, scale=8), nullable=False)
    interval_seconds = Column(Integer, nullable=False)
    max_payments = Column(Integer, nullable=True)
    approved_total = Column(Numeric(precision=18, scale=8), nullable=True)
    status = Column(SQLEnum(MandateStatus), nullable=False, default=MandateStatus.ACTIVE)
    activated_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant")

    __table_args__ = (
        Index('idx_mandates_subscriber', 'subscriber_address'),
        Index('idx_mandates_merchant', 'merchant_id'),
        Index('idx_mandates_status', 'status'),
    )


class Web3Subscription(Base):
    """On-chain recurring payment subscription"""
    __tablename__ = "web3_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    onchain_subscription_id = Column(Integer, nullable=True)
    chain = Column(String(50), nullable=False)
    contract_address = Column(String(42), nullable=False)
    subscriber_address = Column(String(42), nullable=False, index=True)
    merchant_address = Column(String(42), nullable=False)
    token_address = Column(String(42), nullable=False)
    token_symbol = Column(String(20), nullable=False)
    amount = Column(Numeric(precision=18, scale=8), nullable=False)
    interval_seconds = Column(Integer, nullable=False)
    next_payment_at = Column(DateTime, nullable=True)
    status = Column(SQLEnum(Web3SubscriptionStatus), nullable=False, default=Web3SubscriptionStatus.ACTIVE)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("subscription_plans.id"), nullable=True)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    mandate_id = Column(UUID(as_uuid=True), ForeignKey("subscription_mandates.id"), nullable=True)
    created_tx_hash = Column(String(66), nullable=True)
    cancelled_tx_hash = Column(String(66), nullable=True)
    customer_email = Column(String(255), nullable=True)
    customer_name = Column(String(255), nullable=True)
    failed_payment_count = Column(Integer, nullable=False, default=0)
    first_failed_at = Column(DateTime, nullable=True)  # Track when first payment failure occurred
    max_retries = Column(Integer, nullable=False, default=0)
    retry_interval_hours = Column(Integer, nullable=False, default=24)
    grace_period_days = Column(Integer, nullable=True, default=3)  # Days to stay alive after payment failure before auto-pause
    total_payments = Column(Integer, nullable=False, default=0)
    total_amount_collected = Column(Numeric(precision=18, scale=8), nullable=False, default=0)
    cancelled_at = Column(DateTime, nullable=True)
    paused_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant")
    plan = relationship("SubscriptionPlan")
    mandate = relationship("SubscriptionMandate")
    payments = relationship("Web3SubscriptionPayment", back_populates="subscription")

    __table_args__ = (
        Index('idx_web3_subs_merchant', 'merchant_id'),
        Index('idx_web3_subs_subscriber', 'subscriber_address'),
        Index('idx_web3_subs_status', 'status'),
        Index('idx_web3_subs_next_payment', 'next_payment_at'),
    )


class Web3SubscriptionPayment(Base):
    """Individual payment execution for a Web3 subscription"""
    __tablename__ = "web3_subscription_payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("web3_subscriptions.id"), nullable=False)
    amount = Column(Numeric(precision=18, scale=8), nullable=False)
    token_symbol = Column(String(20), nullable=False)
    chain = Column(String(50), nullable=False)
    payment_number = Column(Integer, nullable=False, default=1)
    period_start = Column(DateTime, nullable=True)
    period_end = Column(DateTime, nullable=True)
    tx_hash = Column(String(66), nullable=True)
    block_number = Column(Integer, nullable=True)
    status = Column(SQLEnum(PaymentStatus), nullable=False, default=PaymentStatus.PENDING)
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    subscription = relationship("Web3Subscription", back_populates="payments")

    __table_args__ = (
        Index('idx_web3_payments_sub', 'subscription_id'),
        Index('idx_web3_payments_status', 'status'),
    )


class RelayerTransaction(Base):
    """Tracks every transaction submitted by the gasless relayer"""
    __tablename__ = "relayer_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chain = Column(String(50), nullable=False)
    function_name = Column(String(100), nullable=False)
    relayer_address = Column(String(42), nullable=False)
    nonce = Column(Integer, nullable=False)
    status = Column(SQLEnum(RelayerTxStatus), nullable=False, default=RelayerTxStatus.PENDING)
    tx_hash = Column(String(66), nullable=True)
    gas_used = Column(Integer, nullable=True)
    gas_price = Column(Numeric(precision=30, scale=0), nullable=True)
    gas_cost_native = Column(Numeric(precision=18, scale=10), nullable=True)
    error_message = Column(String(500), nullable=True)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("web3_subscriptions.id"), nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('idx_relayer_tx_chain', 'chain'),
        Index('idx_relayer_tx_status', 'status'),
        Index('idx_relayer_tx_sub', 'subscription_id'),
    )


# ============= LEDGER =============

class LedgerEntryType(str, enum.Enum):
    DEBIT = "debit"
    CREDIT = "credit"
    CONVERSION = "conversion"
    SETTLEMENT = "settlement"
    FEE = "fee"
    REFUND_DEBIT = "refund_debit"
    REFUND_CREDIT = "refund_credit"


class LedgerEntry(Base):
    """Immutable double-entry ledger for every financial event."""
    __tablename__ = "ledger_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    session_id = Column(String, ForeignKey("payment_sessions.id"), nullable=True)

    entry_type = Column(SQLEnum(LedgerEntryType), nullable=False)
    amount = Column(Numeric(precision=20, scale=8), nullable=False)
    currency = Column(String(10), nullable=False)  # USD, USDC, EUR, etc.
    direction = Column(String(6), nullable=False)  # "debit" or "credit"

    # Conversion-specific
    counter_amount = Column(Numeric(precision=20, scale=8), nullable=True)
    counter_currency = Column(String(10), nullable=True)
    exchange_rate = Column(Numeric(precision=18, scale=8), nullable=True)

    # Reference
    reference_type = Column(String(50), nullable=True)  # payment, refund, withdrawal, fee
    reference_id = Column(String, nullable=True)
    description = Column(String(500), nullable=True)

    # Balances after this entry
    balance_after = Column(Numeric(precision=20, scale=8), nullable=True)

    # Immutability hash — sha256(prev_hash + entry data)
    entry_hash = Column(String(64), nullable=False)
    prev_hash = Column(String(64), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant")

    __table_args__ = (
        Index('ix_ledger_merchant', 'merchant_id'),
        Index('ix_ledger_session', 'session_id'),
        Index('ix_ledger_type', 'entry_type'),
        Index('ix_ledger_created', 'created_at'),
    )


# ============= PAYMENT STATE TRANSITIONS =============

class PaymentStateTransition(Base):
    """Audit log of every payment status change with validation."""
    __tablename__ = "payment_state_transitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String, ForeignKey("payment_sessions.id"), nullable=False)
    from_state = Column(String(30), nullable=False)
    to_state = Column(String(30), nullable=False)
    trigger = Column(String(100), nullable=True)  # What caused the transition
    actor = Column(String(200), nullable=True)  # system, merchant_id, admin, listener
    transition_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('ix_transitions_session', 'session_id'),
        Index('ix_transitions_created', 'created_at'),
    )


# ============= COMPLIANCE SCREENING =============

class ComplianceScreening(Base):
    """Log of AML/sanctions screening results."""
    __tablename__ = "compliance_screenings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String, ForeignKey("payment_sessions.id"), nullable=True)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=True)

    screening_type = Column(String(50), nullable=False)  # ofac, jurisdiction, threshold, velocity
    result = Column(String(20), nullable=False)  # pass, flag, block
    risk_level = Column(String(20), nullable=True)  # low, medium, high, critical

    # Screened entity
    entity_type = Column(String(50), nullable=True)  # payer, merchant, wallet
    entity_value = Column(String(255), nullable=True)
    country = Column(String(100), nullable=True)

    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('ix_compliance_session', 'session_id'),
        Index('ix_compliance_result', 'result'),
        Index('ix_compliance_created', 'created_at'),
    )



# ============= TEAM RBAC MODELS =============

class Permission(Base):
    """Permission definitions for RBAC system"""
    __tablename__ = "permissions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RolePermission(Base):
    """Maps permissions to roles"""
    __tablename__ = "role_permissions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role = Column(String(50), nullable=False, index=True)
    permission_id = Column(UUID(as_uuid=True), ForeignKey("permissions.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    permission = relationship("Permission")
    
    __table_args__ = (
        UniqueConstraint('role', 'permission_id', name='uq_role_permission'),
        Index('idx_role_permissions_role', 'role'),
    )


class TeamMemberPermission(Base):
    """Custom permission grants/revokes per team member"""
    __tablename__ = "team_member_permissions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_member_id = Column(UUID(as_uuid=True), ForeignKey("merchant_users.id"), nullable=False)
    permission_id = Column(UUID(as_uuid=True), ForeignKey("permissions.id"), nullable=False)
    granted = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("merchant_users.id"), nullable=True)
    
    team_member = relationship("MerchantUser", foreign_keys=[team_member_id])
    permission = relationship("Permission")
    creator = relationship("MerchantUser", foreign_keys=[created_by])
    
    __table_args__ = (
        UniqueConstraint('team_member_id', 'permission_id', name='uq_member_permission'),
        Index('idx_member_permissions_member', 'team_member_id'),
    )


class ActivityLog(Base):
    """Audit trail for team member actions"""
    __tablename__ = "activity_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    team_member_id = Column(UUID(as_uuid=True), ForeignKey("merchant_users.id"), nullable=True)
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(String(255), nullable=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    merchant = relationship("Merchant")
    team_member = relationship("MerchantUser", back_populates="activity_logs")
    
    __table_args__ = (
        Index('idx_activity_merchant_member', 'merchant_id', 'team_member_id'),
        Index('idx_activity_action_created', 'action', 'created_at'),
    )


class TeamMemberSession(Base):
    """Track active team member sessions"""
    __tablename__ = "team_member_sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_member_id = Column(UUID(as_uuid=True), ForeignKey("merchant_users.id"), nullable=False)
    token_hash = Column(String(255), nullable=False, index=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    last_activity = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    
    team_member = relationship("MerchantUser", back_populates="sessions")
    
    __table_args__ = (
        Index('idx_session_member_active', 'team_member_id', 'revoked_at'),
    )
