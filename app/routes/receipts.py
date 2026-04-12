"""
Payment Receipt API Routes

Endpoints for generating and downloading payment receipts/invoices.
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
import logging

from app.core.database import get_db
from app.core.security import require_merchant
from app.models.models import PaymentSession, Invoice, PaymentStatus
from app.services.receipt_service import ReceiptService
from app.schemas.schemas import (
    ReceiptGenerateRequest,
    ReceiptResponse,
    ReceiptListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/receipts", tags=["Receipts"])


@router.post("/generate", response_model=ReceiptResponse)
async def generate_receipt(
    request: ReceiptGenerateRequest,
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db)
):
    """
    Generate a receipt/invoice for a paid payment session.
    
    This endpoint:
    - Checks if payment is paid
    - Generates invoice/receipt record
    - Returns receipt details
    - Can optionally send email
    """
    import uuid as uuid_lib
    merchant_id = uuid_lib.UUID(current_user["id"])
    
    # Verify payment exists and belongs to merchant
    payment = db.query(PaymentSession).filter(
        PaymentSession.id == request.payment_session_id,
        PaymentSession.merchant_id == merchant_id
    ).first()
    
    if not payment:
        raise HTTPException(status_code=404, detail="Payment session not found")
    
    # Check if payment is paid
    if payment.status not in (PaymentStatus.PAID, PaymentStatus.CONFIRMED):
        raise HTTPException(
            status_code=400,
            detail=f"Payment not completed. Current status: {payment.status.value}"
        )
    
    # Generate receipt
    service = ReceiptService(db)
    receipt = service.generate_receipt_for_payment(
        payment_session_id=request.payment_session_id,
        auto_send_email=request.send_email
    )
    
    if not receipt:
        raise HTTPException(status_code=500, detail="Failed to generate receipt")
    
    return {
        "id": receipt.id,
        "invoice_number": receipt.invoice_number,
        "payment_session_id": receipt.payment_session_id,
        "customer_email": receipt.customer_email,
        "customer_name": receipt.customer_name,
        "amount": float(receipt.total),
        "currency": receipt.fiat_currency,
        "status": receipt.status.value,
        "issue_date": receipt.issue_date.isoformat(),
        "paid_at": receipt.paid_at.isoformat() if receipt.paid_at else None,
        "tx_hash": receipt.tx_hash,
        "chain": receipt.chain,
        "token": receipt.token_symbol,
        "download_url": f"/receipts/{receipt.id}/download",
        "view_url": f"/receipts/{receipt.id}",
    }


@router.get("/{receipt_id}/download")
async def download_receipt_pdf(
    receipt_id: str,
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db)
):
    """
    Download receipt as PDF.
    
    Returns a PDF file that can be saved or printed.
    """
    import uuid as uuid_lib
    merchant_id = uuid_lib.UUID(current_user["id"])
    
    # Get receipt
    receipt = db.query(Invoice).filter(
        Invoice.id == receipt_id,
        Invoice.merchant_id == merchant_id
    ).first()
    
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    
    # Generate PDF
    service = ReceiptService(db)
    pdf_buffer = service.generate_pdf(receipt_id)
    
    if not pdf_buffer:
        raise HTTPException(status_code=500, detail="Failed to generate PDF")
    
    # Return PDF as downloadable file
    filename = f"receipt_{receipt.invoice_number}.pdf"
    
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.get("/{receipt_id}/view")
async def view_receipt_pdf(
    receipt_id: str,
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db)
):
    """
    View receipt PDF in browser (inline).
    
    Opens PDF in browser instead of downloading.
    """
    import uuid as uuid_lib
    merchant_id = uuid_lib.UUID(current_user["id"])
    
    # Get receipt
    receipt = db.query(Invoice).filter(
        Invoice.id == receipt_id,
        Invoice.merchant_id == merchant_id
    ).first()
    
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    
    # Generate PDF
    service = ReceiptService(db)
    pdf_buffer = service.generate_pdf(receipt_id)
    
    if not pdf_buffer:
        raise HTTPException(status_code=500, detail="Failed to generate PDF")
    
    # Return PDF for inline viewing
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "inline"
        }
    )


@router.get("/{receipt_id}", response_model=ReceiptResponse)
async def get_receipt(
    receipt_id: str,
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db)
):
    """Get receipt details."""
    import uuid as uuid_lib
    merchant_id = uuid_lib.UUID(current_user["id"])
    
    receipt = db.query(Invoice).filter(
        Invoice.id == receipt_id,
        Invoice.merchant_id == merchant_id
    ).first()
    
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    
    return {
        "id": receipt.id,
        "invoice_number": receipt.invoice_number,
        "payment_session_id": receipt.payment_session_id,
        "customer_email": receipt.customer_email,
        "customer_name": receipt.customer_name,
        "amount": float(receipt.total),
        "currency": receipt.fiat_currency,
        "status": receipt.status.value,
        "issue_date": receipt.issue_date.isoformat(),
        "paid_at": receipt.paid_at.isoformat() if receipt.paid_at else None,
        "tx_hash": receipt.tx_hash,
        "chain": receipt.chain,
        "token": receipt.token_symbol,
        "download_url": f"/receipts/{receipt.id}/download",
        "view_url": f"/receipts/{receipt.id}",
    }


@router.get("", response_model=ReceiptListResponse)
async def list_receipts(
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db)
):
    """List all receipts for merchant."""
    import uuid as uuid_lib
    merchant_id = uuid_lib.UUID(current_user["id"])
    
    # Query receipts
    query = db.query(Invoice).filter(
        Invoice.merchant_id == merchant_id,
        Invoice.invoice_metadata.op('->>')('type') == 'receipt'
    )
    
    total = query.count()
    receipts = query.order_by(Invoice.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    
    return {
        "receipts": [
            {
                "id": r.id,
                "invoice_number": r.invoice_number,
                "payment_session_id": r.payment_session_id,
                "customer_email": r.customer_email,
                "customer_name": r.customer_name,
                "amount": float(r.total),
                "currency": r.fiat_currency,
                "status": r.status.value,
                "issue_date": r.issue_date.isoformat(),
                "paid_at": r.paid_at.isoformat() if r.paid_at else None,
                "tx_hash": r.tx_hash,
                "chain": r.chain,
                "token": r.token_symbol,
                "download_url": f"/receipts/{r.id}/download",
                "view_url": f"/receipts/{r.id}",
            }
            for r in receipts
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size
    }


@router.post("/payment/{payment_session_id}/generate", response_model=ReceiptResponse)
async def generate_receipt_for_payment(
    payment_session_id: str,
    send_email: bool = False,
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db)
):
    """
    Quick endpoint to generate receipt for a specific payment.
    Convenience endpoint that doesn't require request body.
    """
    import uuid as uuid_lib
    merchant_id = uuid_lib.UUID(current_user["id"])
    
    # Verify payment
    payment = db.query(PaymentSession).filter(
        PaymentSession.id == payment_session_id,
        PaymentSession.merchant_id == merchant_id
    ).first()
    
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    if payment.status not in (PaymentStatus.PAID, PaymentStatus.CONFIRMED):
        raise HTTPException(
            status_code=400,
            detail=f"Payment not completed. Status: {payment.status.value}"
        )
    
    # Generate receipt
    service = ReceiptService(db)
    receipt = service.generate_receipt_for_payment(
        payment_session_id=payment_session_id,
        auto_send_email=send_email
    )
    
    if not receipt:
        raise HTTPException(status_code=500, detail="Failed to generate receipt")
    
    return {
        "id": receipt.id,
        "invoice_number": receipt.invoice_number,
        "payment_session_id": receipt.payment_session_id,
        "customer_email": receipt.customer_email,
        "customer_name": receipt.customer_name,
        "amount": float(receipt.total),
        "currency": receipt.fiat_currency,
        "status": receipt.status.value,
        "issue_date": receipt.issue_date.isoformat(),
        "paid_at": receipt.paid_at.isoformat() if receipt.paid_at else None,
        "tx_hash": receipt.tx_hash,
        "chain": receipt.chain,
        "token": receipt.token_symbol,
        "download_url": f"/receipts/{receipt.id}/download",
        "view_url": f"/receipts/{receipt.id}",
    }
