from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import time
import logging
import os

from app.core.config import settings
from app.core.security_middleware import SecurityHeadersMiddleware
from app.core.currency_middleware import MerchantCurrencyMiddleware
from app.core.monitoring import (
    MetricsMiddleware,
    get_metrics_response,
    setup_structured_logging,
)
from app.routes import (
    auth, merchant, payments, checkout, admin, merchant_payments, 
    public, admin_webhooks, escrow, sessions, integrations, wallets,
    # Enterprise features
    payment_links, invoices, subscriptions, refunds, analytics, team,
    # Onboarding & Subscription
    onboarding, subscription_management, billing,
    # Withdrawals
    withdrawals,
    # Promo codes
    promo,
    # Subscription checkout (public)
    subscription_checkout,
    # Web3 subscriptions
    web3_subscriptions,
    # Tax & compliance reports
    tax_reports,
    # Transactions & refund tracking
    transactions,
    # Receipts
    receipts,
    # Team RBAC
    team_auth,
    permissions as permissions_routes,
    activity_logs,
    # GDPR Compliance
    gdpr, consent,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Dari for Business",
    description="Multi-chain payment gateway supporting Stellar, Ethereum, Polygon, Base, Tron, and more",
    version="2.2.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Security middleware — rate limiting + OWASP headers
# NOTE: Added BEFORE CORSMiddleware so CORS wraps it (last-added = outermost in Starlette)
app.add_middleware(SecurityHeadersMiddleware)

# Configure CORS - Use origins from config (not hardcoded)
# MUST be added LAST so it's the outermost middleware and handles preflight/headers on ALL responses
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# Request body size limit — 10MB max (DoS prevention)
@app.middleware("http")
async def limit_request_body_size(request: Request, call_next):
    """Reject requests with excessively large bodies."""
    MAX_BODY_SIZE = 10 * 1024 * 1024  # 10 MB
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_BODY_SIZE:
        return JSONResponse(
            status_code=413,
            content={"detail": "Request body too large. Maximum size is 10MB."}
        )
    return await call_next(request)

# Merchant currency middleware — inject currency preferences into request context
app.add_middleware(MerchantCurrencyMiddleware)

# Prometheus metrics middleware
if settings.PROMETHEUS_ENABLED:
    app.add_middleware(MetricsMiddleware)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests."""
    start_time = time.time()
    
    # Log request
    logger.info(f"→ {request.method} {request.url.path}")
    
    # Process request
    response = await call_next(request)
    
    # Log response
    process_time = time.time() - start_time
    logger.info(
        f"← {request.method} {request.url.path} "
        f"[{response.status_code}] {process_time:.3f}s"
    )
    
    return response


# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions. Never expose internal details."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "message": "An unexpected error occurred. Please try again later."
        }
    )


# Include routers
app.include_router(auth.router)
app.include_router(merchant.router)
app.include_router(merchant_payments.router)
app.include_router(payments.router)
app.include_router(sessions.router)  # Public API for merchant integrations
app.include_router(integrations.router)  # E-commerce platform integrations
app.include_router(checkout.router)
app.include_router(admin.router)
app.include_router(admin_webhooks.router)
app.include_router(public.router)
app.include_router(escrow.router)  # Soroban escrow endpoints
app.include_router(wallets.router)  # Merchant wallet management

# Enterprise feature routers
app.include_router(payment_links.router)  # Reusable payment links (merchant CRUD)
app.include_router(payment_links.pay_router)  # Public payment link checkout
app.include_router(invoices.router)  # Invoice management
app.include_router(subscriptions.router)  # Recurring payments
app.include_router(refunds.router)  # Refund processing
app.include_router(transactions.router)  # Transaction tracking with refund data
app.include_router(analytics.router)  # Merchant analytics
app.include_router(team.router)  # Team management (legacy /team prefix)
app.include_router(team.router_v1)  # Team management (/api/v1/team prefix)
app.include_router(onboarding.router)  # Merchant onboarding flow
app.include_router(subscription_management.router)  # Subscription management
app.include_router(billing.router)  # Billing endpoints (alias for subscription)
app.include_router(withdrawals.router)  # Withdraw to external wallets
app.include_router(subscription_checkout.router)  # Public subscription checkout

# Promo code / coupon routers
app.include_router(promo.merchant_promo_router)  # Merchant promo management
app.include_router(promo.payment_coupon_router)  # Checkout coupon application

# Web3 subscription routers
app.include_router(web3_subscriptions.router)  # Web3 recurring payments

# Tax & compliance reports
app.include_router(tax_reports.router)  # Tax summary, transactions, subscription revenue

# Receipts
app.include_router(receipts.router)  # Payment receipts and PDF generation

# Team RBAC routes
app.include_router(team_auth.router)  # Team member authentication (legacy /auth/team prefix)
app.include_router(team_auth.router_v1)  # Team member authentication (/api/v1/auth/team prefix)
app.include_router(permissions_routes.router)  # Permission management (legacy /team prefix)
app.include_router(permissions_routes.router_v1)  # Permission management (/api/v1/team prefix)
app.include_router(activity_logs.router)  # Activity audit logs (legacy /team prefix)
app.include_router(activity_logs.router_v1)  # Activity audit logs (/api/v1/team prefix)

# GDPR Compliance routes
app.include_router(gdpr.router)  # GDPR data deletion and export
app.include_router(consent.router)  # Consent management

# Serve static files (Dari Payment button SDK and demo)
public_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "public")
if os.path.exists(public_dir):
    app.mount("/public", StaticFiles(directory=public_dir), name="public")
    logger.info(f"✅ Serving static files from {public_dir}")
else:
    logger.warning(f"⚠️  Public directory not found: {public_dir}")


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Dari for Business",
        "version": "2.2.0",
        "status": "operational",
        "network": settings.STELLAR_NETWORK,
        "docs": "/docs"
    }


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint with dependency verification."""
    from app.core.database import SessionLocal
    from sqlalchemy import text
    
    checks = {
        "database": False,
        "version": "2.2.0",
        "network": settings.STELLAR_NETWORK,
    }
    
    # Check database connectivity
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        checks["database"] = True
        db.close()
    except Exception as e:
        logger.error(f"Health check DB failure: {e}")
        checks["database"] = False
    
    # Check Redis if enabled
    if settings.REDIS_ENABLED:
        try:
            from app.core.cache import cache
            checks["redis"] = cache.is_available() if hasattr(cache, 'is_available') else True
        except Exception:
            checks["redis"] = False
    
    all_healthy = checks["database"]
    
    if not all_healthy:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "checks": checks}
        )
    
    return {"status": "healthy", "checks": checks}


# Prometheus metrics endpoint
@app.get("/metrics", include_in_schema=False)
async def metrics():
    """Prometheus metrics scrape endpoint."""
    return get_metrics_response()


# Startup event
@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    from app.core.database import Base, engine, SessionLocal
    from app.models import Admin
    from app.core.security import hash_password
    
    logger.info("=" * 60)
    logger.info("🚀 Dari for Business - Multi-Chain Payment Gateway v2.2.0")
    logger.info("=" * 60)

    # Initialize structured logging
    setup_structured_logging()
    
    # Auto-create database tables if they don't exist
    try:
        logger.info("Initializing database tables...")
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Database tables ready")
        
        # Create admin account if it doesn't exist
        db = SessionLocal()
        try:
            existing_admin = db.query(Admin).filter(Admin.email == settings.ADMIN_EMAIL).first()
            if not existing_admin:
                admin = Admin(
                    email=settings.ADMIN_EMAIL,
                    password_hash=hash_password(settings.ADMIN_PASSWORD)
                )
                db.add(admin)
                db.commit()
                logger.info("✅ Admin account created")
            else:
                logger.info("ℹ️  Admin account exists")
        except Exception as e:
            logger.error(f"Admin account creation error: {e}")
            db.rollback()
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
    
    logger.info(f"🌐 Network: {settings.STELLAR_NETWORK}")
    logger.info(f"🔗 Base URL: {settings.APP_BASE_URL}")
    logger.info("=" * 60)
    logger.info("📍 Supported Blockchains:")
    logger.info("   • Stellar (USDC, USDT, XLM)")
    logger.info("   • Ethereum (USDC, USDT, PYUSD)")
    logger.info("   • Polygon (USDC, USDT)")
    logger.info("   • Base (USDC)")
    logger.info("   • BSC (USDC, USDT)")
    logger.info("   • Arbitrum (USDC, USDT)")
    logger.info("   • Tron (USDT, USDC)")
    logger.info("   • Solana (USDC)")
    logger.info("=" * 60)
    logger.info("")
    logger.info("⚠️  IMPORTANT: Start blockchain listeners separately:")
    logger.info("   python run_listeners.py                     # All enabled chains")
    logger.info("   python run_listeners.py polygon tron bsc    # Specific chains only")
    logger.info("")
    
    # Start Web3 subscription scheduler if enabled
    if settings.WEB3_SUBSCRIPTIONS_ENABLED:
        from app.services.subscription_scheduler import scheduler
        scheduler.interval_seconds = settings.SCHEDULER_INTERVAL_SECONDS
        scheduler.batch_size = settings.SCHEDULER_BATCH_SIZE
        await scheduler.start()
        logger.info("✅ Web3 subscription scheduler started")
    else:
        logger.info("ℹ️  Web3 subscription scheduler disabled (set WEB3_SUBSCRIPTIONS_ENABLED=true to enable)")
    
    # Start refund scheduler if enabled
    try:
        if settings.REFUND_SCHEDULER_ENABLED:
            from app.services.refund_scheduler import start_refund_scheduler
            start_refund_scheduler(interval_minutes=settings.REFUND_SCHEDULER_INTERVAL_MINUTES)
            logger.info(f"✅ Refund scheduler started (processes every {settings.REFUND_SCHEDULER_INTERVAL_MINUTES} minutes)")
        else:
            logger.info("ℹ️  Refund scheduler disabled (set REFUND_SCHEDULER_ENABLED=true to enable)")
    except Exception as e:
        logger.error(f"Failed to start refund scheduler: {e}", exc_info=True)
    
    logger.info("=" * 60)
    
    # Start session cleanup periodic task
    try:
        import asyncio
        from app.core.sessions import cleanup_expired_sessions
        from app.core.database import SessionLocal
        
        async def periodic_session_cleanup():
            """Clean up expired team member sessions every 6 hours."""
            while True:
                try:
                    await asyncio.sleep(6 * 60 * 60)  # 6 hours
                    cleanup_db = SessionLocal()
                    try:
                        count = await cleanup_expired_sessions(cleanup_db)
                        if count > 0:
                            logger.info(f"🧹 Cleaned up {count} expired team member sessions")
                    finally:
                        cleanup_db.close()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Session cleanup error: {e}")
        
        asyncio.create_task(periodic_session_cleanup())
        logger.info("✅ Session cleanup task scheduled (every 6 hours)")
    except Exception as e:
        logger.error(f"Failed to start session cleanup: {e}")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    # Stop subscription scheduler
    if settings.WEB3_SUBSCRIPTIONS_ENABLED:
        from app.services.subscription_scheduler import scheduler
        await scheduler.stop()
    
    # Stop refund scheduler
    try:
        from app.services.refund_scheduler import stop_refund_scheduler
        stop_refund_scheduler()
    except Exception as e:
        logger.error(f"Error stopping refund scheduler: {e}")
    
    logger.info("Shutting down Dari for Business...")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=True
    )
