"""
Monitoring & Observability

Provides:
  - Prometheus metrics (HTTP request duration, payment counters, etc.)
  - Structured logging via structlog
  - Audit trail utilities
"""

import time
import logging
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Prometheus Metrics ──
# Guarded import — prometheus_client is optional

_metrics_available = False

try:
    from prometheus_client import (
        Counter,
        Histogram,
        Gauge,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )

    # HTTP metrics
    HTTP_REQUESTS_TOTAL = Counter(
        "http_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status"],
    )
    HTTP_REQUEST_DURATION = Histogram(
        "http_request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "endpoint"],
        buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    )

    # Payment metrics
    PAYMENTS_CREATED = Counter(
        "payments_created_total",
        "Total payment sessions created",
        ["currency", "chain"],
    )
    PAYMENTS_COMPLETED = Counter(
        "payments_completed_total",
        "Total payments completed",
        ["currency", "chain", "status"],
    )
    PAYMENT_AMOUNT_USD = Histogram(
        "payment_amount_usd",
        "Payment amounts in USD",
        buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000, 5000, 10000],
    )

    # Compliance metrics
    COMPLIANCE_SCREENINGS = Counter(
        "compliance_screenings_total",
        "Total compliance screenings",
        ["result"],  # pass, flag, block
    )

    # Webhook metrics
    WEBHOOKS_SENT = Counter(
        "webhooks_sent_total",
        "Total webhooks sent",
        ["status"],  # success, failed
    )

    # Active sessions gauge
    ACTIVE_SESSIONS = Gauge(
        "active_payment_sessions",
        "Number of active (non-expired) payment sessions",
    )

    _metrics_available = True
    logger.info("Prometheus metrics initialized")

except ImportError:
    logger.info("prometheus_client not installed, metrics disabled")


def get_metrics_response() -> Optional[Response]:
    """Generate Prometheus metrics response for /metrics endpoint."""
    if not _metrics_available:
        return Response(content="Metrics not available", status_code=503)
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


def record_payment_created(currency: str = "USD", chain: str = "stellar"):
    if _metrics_available:
        PAYMENTS_CREATED.labels(currency=currency, chain=chain).inc()


def record_payment_completed(
    currency: str = "USD", chain: str = "stellar", status: str = "paid"
):
    if _metrics_available:
        PAYMENTS_COMPLETED.labels(currency=currency, chain=chain, status=status).inc()


def record_payment_amount(amount_usd: float):
    if _metrics_available:
        PAYMENT_AMOUNT_USD.observe(amount_usd)


def record_compliance_screening(result: str):
    if _metrics_available:
        COMPLIANCE_SCREENINGS.labels(result=result).inc()


def record_webhook(status: str):
    if _metrics_available:
        WEBHOOKS_SENT.labels(status=status).inc()


# ── Structured Logging Setup ──

def setup_structured_logging():
    """Configure structlog for JSON-formatted structured logging."""
    if not settings.STRUCTURED_LOGGING:
        return

    try:
        import structlog

        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                logging.getLevelName(settings.LOG_LEVEL)
            ),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )
        logger.info("Structured logging configured (JSON)")
    except ImportError:
        logger.info("structlog not installed, using standard logging")


# ── Prometheus Metrics Middleware ──

class MetricsMiddleware(BaseHTTPMiddleware):
    """Collect HTTP request metrics for Prometheus."""

    async def dispatch(self, request: Request, call_next):
        if not _metrics_available:
            return await call_next(request)

        start = time.monotonic()
        response = await call_next(request)
        duration = time.monotonic() - start

        # Normalize path to avoid cardinality explosion
        path = _normalize_path(request.url.path)

        HTTP_REQUESTS_TOTAL.labels(
            method=request.method,
            endpoint=path,
            status=response.status_code,
        ).inc()

        HTTP_REQUEST_DURATION.labels(
            method=request.method,
            endpoint=path,
        ).observe(duration)

        return response


def _normalize_path(path: str) -> str:
    """
    Normalize URL paths to reduce metric cardinality.
    Replace UUIDs and IDs with placeholders.
    """
    import re
    # Replace UUIDs
    path = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "{id}",
        path,
    )
    # Replace pay_xxx, link_xxx, inv_xxx, sub_xxx style IDs
    path = re.sub(r"(pay|link|inv|sub|ref)_[A-Za-z0-9]+", r"\1_{id}", path)
    return path


# ── Audit Trail ──

def log_audit_event(
    event_type: str,
    actor: str,
    resource_type: str,
    resource_id: str,
    details: Optional[dict] = None,
):
    """
    Log a structured audit event.

    These can be consumed by SIEM systems for compliance.
    """
    audit_entry = {
        "audit": True,
        "event_type": event_type,
        "actor": actor,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "details": details or {},
        "timestamp": time.time(),
    }
    logger.info("AUDIT: %s", audit_entry)
