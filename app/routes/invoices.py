"""
Invoice API Routes
Professional invoice management for merchants
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import secrets
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List

from app.core.database import get_db
from app.core import require_merchant
from app.models.models import (
    Merchant, Invoice, PaymentSession, InvoiceStatus as DBInvoiceStatus
)
from app.schemas.schemas import (
    InvoiceCreate, InvoiceUpdate, InvoiceResponse, InvoiceList,
    InvoiceSend, InvoiceLineItem, InvoiceStatus
)

router = APIRouter(prefix="/invoices", tags=["Invoices"])


def generate_invoice_id() -> str:
    """Generate a unique invoice ID"""
    return f"inv_{secrets.token_urlsafe(16)}"


def generate_invoice_number(merchant_id: str, db: Session) -> str:
    """Generate sequential invoice number for merchant"""
    count = db.query(Invoice).filter(Invoice.merchant_id == merchant_id).count()
    return f"INV-{count + 1:04d}"


def calculate_totals(line_items: List[InvoiceLineItem], tax: Decimal, discount: Decimal):
    """Calculate invoice totals from line items"""
    subtotal = Decimal("0")
    for item in line_items:
        item_total = item.quantity * item.unit_price
        item.total = item_total
        subtotal += item_total
    
    total = subtotal + tax - discount
    return subtotal, total


def get_invoice_payment_url(request: Request, invoice_id: str) -> str:
    """Generate the payment URL for an invoice"""
    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}/invoice/{invoice_id}/pay"


@router.post("", response_model=InvoiceResponse)
async def create_invoice(
    invoice_data: InvoiceCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Create a new invoice.
    
    Invoices can be:
    - Saved as draft for later editing
    - Sent immediately to customer via email
    - Set with custom due dates
    - Support multiple line items
    """
    merchant = db.query(Merchant).filter(Merchant.id == uuid.UUID(current_user["id"])).first()
    invoice_id = generate_invoice_id()
    
    # Generate invoice number if not provided
    invoice_number = invoice_data.invoice_number or generate_invoice_number(
        str(merchant.id), db
    )
    
    # Process line items and calculate totals
    line_items_data = [item.model_dump() for item in invoice_data.line_items]
    
    if invoice_data.subtotal is None:
        subtotal, total = calculate_totals(
            invoice_data.line_items,
            invoice_data.tax,
            invoice_data.discount
        )
        # Update line items with calculated totals
        line_items_data = [item.model_dump() for item in invoice_data.line_items]
    else:
        subtotal = invoice_data.subtotal
        total = subtotal + invoice_data.tax - invoice_data.discount
    
    # Determine initial status
    initial_status = DBInvoiceStatus.DRAFT
    if invoice_data.send_immediately:
        initial_status = DBInvoiceStatus.SENT
    
    invoice = Invoice(
        id=invoice_id,
        invoice_number=invoice_number,
        merchant_id=merchant.id,
        customer_email=invoice_data.customer_email,
        customer_name=invoice_data.customer_name,
        customer_address=invoice_data.customer_address,
        description=invoice_data.description,
        line_items=line_items_data,
        subtotal=subtotal,
        tax=invoice_data.tax,
        discount=invoice_data.discount,
        total=total,
        fiat_currency=(invoice_data.fiat_currency or merchant.base_currency).upper(),
        status=initial_status,
        due_date=invoice_data.due_date,
        sent_at=datetime.utcnow() if invoice_data.send_immediately else None,
        accepted_tokens=invoice_data.accepted_tokens or merchant.accepted_tokens,
        accepted_chains=invoice_data.accepted_chains or merchant.accepted_chains,
        notes=invoice_data.notes,
        terms=invoice_data.terms,
        footer=invoice_data.footer,
        invoice_metadata=invoice_data.metadata
    )
    
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    
    # Send email if requested
    if invoice_data.send_immediately:
        # TODO: background_tasks.add_task(send_invoice_email, invoice)
        pass
    
    return build_invoice_response(invoice, request)


@router.get("", response_model=InvoiceList)
async def list_invoices(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: Optional[InvoiceStatus] = None,
    customer_email: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    List all invoices for the merchant.
    
    Supports filtering by status and customer email.
    """
    # TEMP: Show all data (no auth)
    query = db.query(Invoice)
    
    if status:
        query = query.filter(Invoice.status == status.value)
    
    if customer_email:
        query = query.filter(Invoice.customer_email.ilike(f"%{customer_email}%"))
    
    total = query.count()
    
    invoices = query.order_by(Invoice.created_at.desc())\
        .offset((page - 1) * page_size)\
        .limit(page_size)\
        .all()
    
    return InvoiceList(
        invoices=[build_invoice_response(inv, request) for inv in invoices],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get a specific invoice by ID."""
    # TEMP: Show all data (no auth)
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    return build_invoice_response(invoice, request)


@router.patch("/{invoice_id}", response_model=InvoiceResponse)
async def update_invoice(
    invoice_id: str,
    update_data: InvoiceUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Update an invoice.
    
    Can only update invoices in DRAFT status.
    Line items update replaces all existing items.
    """
    invoice = db.query(Invoice).filter(
        and_(
            Invoice.id == invoice_id,
            Invoice.merchant_id == uuid.UUID(current_user["id"])
        )
    ).first()
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    if invoice.status != DBInvoiceStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail="Can only update invoices in draft status"
        )
    
    update_fields = update_data.model_dump(exclude_unset=True)
    
    # Handle line items specially
    if "line_items" in update_fields and update_fields["line_items"]:
        line_items = [InvoiceLineItem(**item) if isinstance(item, dict) else item 
                      for item in update_fields["line_items"]]
        subtotal, total = calculate_totals(
            line_items,
            update_fields.get("tax", invoice.tax),
            update_fields.get("discount", invoice.discount)
        )
        update_fields["line_items"] = [item.model_dump() for item in line_items]
        update_fields["subtotal"] = subtotal
        update_fields["total"] = total
    elif "tax" in update_fields or "discount" in update_fields:
        # Recalculate total if tax or discount changed
        tax = update_fields.get("tax", invoice.tax)
        discount = update_fields.get("discount", invoice.discount)
        update_fields["total"] = invoice.subtotal + tax - discount
    
    for field, value in update_fields.items():
        setattr(invoice, field, value)
    
    invoice.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(invoice)
    
    return build_invoice_response(invoice, request)


@router.post("/{invoice_id}/send")
async def send_invoice(
    invoice_id: str,
    send_data: InvoiceSend,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Send an invoice to the customer via email.
    
    Updates status from DRAFT to SENT.
    """
    invoice = db.query(Invoice).filter(
        and_(
            Invoice.id == invoice_id,
            Invoice.merchant_id == uuid.UUID(current_user["id"])
        )
    ).first()
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    if invoice.status not in [DBInvoiceStatus.DRAFT, DBInvoiceStatus.SENT]:
        raise HTTPException(
            status_code=400,
            detail="Cannot send invoice in current status"
        )
    
    invoice.status = DBInvoiceStatus.SENT
    invoice.sent_at = datetime.utcnow()
    invoice.updated_at = datetime.utcnow()
    db.commit()
    
    # TODO: Send email in background
    # background_tasks.add_task(
    #     send_invoice_email, 
    #     invoice, 
    #     custom_message=send_data.message
    # )
    
    return {
        "message": "Invoice sent",
        "invoice_id": invoice_id,
        "sent_to": invoice.customer_email
    }


@router.post("/{invoice_id}/remind")
async def send_reminder(
    invoice_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Send a payment reminder for an invoice.
    
    Only works for SENT or OVERDUE invoices.
    """
    invoice = db.query(Invoice).filter(
        and_(
            Invoice.id == invoice_id,
            Invoice.merchant_id == uuid.UUID(current_user["id"])
        )
    ).first()
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    if invoice.status not in [DBInvoiceStatus.SENT, DBInvoiceStatus.OVERDUE]:
        raise HTTPException(
            status_code=400,
            detail="Can only send reminders for sent or overdue invoices"
        )
    
    invoice.reminder_sent = True
    invoice.updated_at = datetime.utcnow()
    db.commit()
    
    # TODO: Send reminder email
    # background_tasks.add_task(send_invoice_reminder, invoice)
    
    return {
        "message": "Reminder sent",
        "invoice_id": invoice_id,
        "sent_to": invoice.customer_email
    }


@router.post("/{invoice_id}/cancel")
async def cancel_invoice(
    invoice_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Cancel an invoice.
    
    Can cancel DRAFT, SENT, or OVERDUE invoices.
    Cannot cancel PAID invoices.
    """
    invoice = db.query(Invoice).filter(
        and_(
            Invoice.id == invoice_id,
            Invoice.merchant_id == uuid.UUID(current_user["id"])
        )
    ).first()
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    if invoice.status == DBInvoiceStatus.PAID:
        raise HTTPException(
            status_code=400,
            detail="Cannot cancel a paid invoice"
        )
    
    if invoice.status == DBInvoiceStatus.CANCELLED:
        raise HTTPException(
            status_code=400,
            detail="Invoice is already cancelled"
        )
    
    invoice.status = DBInvoiceStatus.CANCELLED
    invoice.updated_at = datetime.utcnow()
    db.commit()
    
    return {
        "message": "Invoice cancelled",
        "invoice_id": invoice_id
    }


@router.post("/{invoice_id}/duplicate", response_model=InvoiceResponse)
async def duplicate_invoice(
    invoice_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Create a copy of an existing invoice.
    
    New invoice is created in DRAFT status with a new invoice number.
    """
    original = db.query(Invoice).filter(
        and_(
            Invoice.id == invoice_id,
            Invoice.merchant_id == uuid.UUID(current_user["id"])
        )
    ).first()
    
    if not original:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    new_invoice = Invoice(
        id=generate_invoice_id(),
        invoice_number=generate_invoice_number(current_user["id"], db),
        merchant_id=uuid.UUID(current_user["id"]),
        customer_email=original.customer_email,
        customer_name=original.customer_name,
        customer_address=original.customer_address,
        description=original.description,
        line_items=original.line_items,
        subtotal=original.subtotal,
        tax=original.tax,
        discount=original.discount,
        total=original.total,
        fiat_currency=original.fiat_currency,
        status=DBInvoiceStatus.DRAFT,
        due_date=datetime.utcnow() + timedelta(days=30),  # 30 day default
        accepted_tokens=original.accepted_tokens,
        accepted_chains=original.accepted_chains,
        notes=original.notes,
        terms=original.terms,
        footer=original.footer
    )
    
    db.add(new_invoice)
    db.commit()
    db.refresh(new_invoice)
    
    return build_invoice_response(new_invoice, request)


def build_invoice_response(invoice: Invoice, request: Request) -> InvoiceResponse:
    """Build InvoiceResponse from Invoice model"""
    line_items = []
    if invoice.line_items:
        for item in invoice.line_items:
            line_items.append(InvoiceLineItem(
                description=item.get("description", ""),
                quantity=item.get("quantity", 1),
                unit_price=Decimal(str(item.get("unit_price", 0))),
                total=Decimal(str(item.get("total", 0))) if item.get("total") else None
            ))
    
    # Determine payment URL
    payment_url = None
    if invoice.status in [DBInvoiceStatus.SENT, DBInvoiceStatus.VIEWED, DBInvoiceStatus.OVERDUE]:
        payment_url = get_invoice_payment_url(request, invoice.id)
    
    return InvoiceResponse(
        id=invoice.id,
        invoice_number=invoice.invoice_number,
        customer_email=invoice.customer_email,
        customer_name=invoice.customer_name,
        customer_address=invoice.customer_address,
        description=invoice.description,
        line_items=line_items,
        subtotal=invoice.subtotal,
        tax=invoice.tax,
        discount=invoice.discount,
        total=invoice.total,
        fiat_currency=invoice.fiat_currency,
        status=invoice.status.value if hasattr(invoice.status, 'value') else invoice.status,
        issue_date=invoice.issue_date,
        due_date=invoice.due_date,
        sent_at=invoice.sent_at,
        viewed_at=invoice.viewed_at,
        paid_at=invoice.paid_at,
        payment_url=payment_url,
        amount_paid=invoice.amount_paid or Decimal("0"),
        notes=invoice.notes,
        terms=invoice.terms,
        footer=invoice.footer,
        created_at=invoice.created_at
    )
