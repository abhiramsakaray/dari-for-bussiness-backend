"""
GDPR Compliance Endpoints
Handles data subject rights: deletion, access, portability
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime
from typing import Optional
import uuid
import logging

from app.core.database import get_db
from app.core.security import require_merchant, require_admin
from app.core.audit_logger import AuditLogger
from app.models.models import (
    Merchant, PaymentSession, PayerInfo, Refund, 
    AuditLog, TeamMemberSession
)
from app.models.consent import ConsentRecord
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/api/gdpr", tags=["GDPR Compliance"])
logger = logging.getLogger(__name__)


class DataDeletionRequest(BaseModel):
    email: EmailStr
    reason: Optional[str] = None
    confirm: bool = False


class DataDeletionResponse(BaseModel):
    status: str
    message: str
    records_anonymized: int
    records_deleted: int
    audit_log_id: str


@router.post("/delete-user", response_model=DataDeletionResponse)
async def delete_user_data(
    request: DataDeletionRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_admin),  # Admin only
    db: Session = Depends(get_db)
):
    """
    GDPR Article 17 - Right to Erasure
    
    Deletes or anonymizes all PII for a given email address.
    
    Process:
    1. Find all records associated with email
    2. Anonymize PII in PayerInfo (cannot delete - needed for audit)
    3. Anonymize merchant data if merchant account
    4. Delete consent records
    5. Delete sessions
    6. Log deletion in AuditLog (immutable)
    7. Send confirmation email
    
    Args:
        request: Deletion request with email and confirmation
        current_user: Admin user (only admins can delete data)
        db: Database session
    
    Returns:
        Deletion summary with counts
    """
    if not request.confirm:
        raise HTTPException(
            status_code=400,
            detail="Deletion must be confirmed with confirm=true"
        )
    
    email = request.email.lower()
    records_anonymized = 0
    records_deleted = 0
    
    logger.info(f"GDPR deletion request for email: {email}")
    
    # 1. Anonymize PayerInfo records (keep for financial audit, but remove PII)
    payer_records = db.query(PayerInfo).filter(
        PayerInfo.email == email
    ).all()
    
    for payer in payer_records:
        payer.email = f"deleted_{uuid.uuid4().hex[:8]}@anonymized.local"
        payer.name = "DELETED_USER"
        payer.phone = None
        payer.billing_address_line1 = None
        payer.billing_address_line2 = None
        payer.billing_city = None
        payer.billing_state = None
        payer.billing_postal_code = None
        payer.billing_country = None
        payer.custom_fields = {"gdpr_deleted": True, "deleted_at": datetime.utcnow().isoformat()}
        records_anonymized += 1
    
    # 2. Anonymize PaymentSession payer data
    payment_sessions = db.query(PaymentSession).filter(
        PaymentSession.payer_email == email
    ).all()
    
    for session in payment_sessions:
        session.payer_email = f"deleted_{uuid.uuid4().hex[:8]}@anonymized.local"
        session.payer_name = "DELETED_USER"
        records_anonymized += 1
    
    # 3. Check if email belongs to a merchant account
    merchant = db.query(Merchant).filter(Merchant.email == email).first()
    
    if merchant:
        # Anonymize merchant PII (keep account for financial records)
        merchant.email = f"deleted_merchant_{uuid.uuid4().hex[:8]}@anonymized.local"
        merchant.name = "DELETED_MERCHANT"
        merchant.is_active = False
        merchant.google_id = None
        merchant.avatar_url = None
        records_anonymized += 1
    
    # 4. Delete consent records (no longer needed after deletion)
    consent_records = db.query(ConsentRecord).filter(
        ConsentRecord.email == email
    ).all()
    
    for consent in consent_records:
        db.delete(consent)
        records_deleted += 1
    
    # 5. Delete team member sessions
    if merchant:
        sessions = db.query(TeamMemberSession).filter(
            TeamMemberSession.team_member_id == merchant.id
        ).all()
        
        for session in sessions:
            db.delete(session)
            records_deleted += 1
    
    # 6. Create immutable audit log entry
    audit_log_id = AuditLogger.log_action(
        db=db,
        actor_id=current_user["id"],
        actor_type="admin",
        action="gdpr_data_deletion",
        resource_type="user_data",
        resource_id=email,
        details={
            "email": email,
            "reason": request.reason,
            "records_anonymized": records_anonymized,
            "records_deleted": records_deleted,
            "merchant_account": merchant is not None
        },
        status="success"
    )
    
    db.commit()
    
    # 7. Send confirmation email (background task)
    background_tasks.add_task(
        send_deletion_confirmation_email,
        email=email,
        records_anonymized=records_anonymized,
        records_deleted=records_deleted
    )
    
    logger.info(
        f"GDPR deletion completed for {email}: "
        f"{records_anonymized} anonymized, {records_deleted} deleted"
    )
    
    return DataDeletionResponse(
        status="completed",
        message=f"User data deleted/anonymized successfully",
        records_anonymized=records_anonymized,
        records_deleted=records_deleted,
        audit_log_id=audit_log_id
    )


@router.get("/export-user-data")
async def export_user_data(
    email: EmailStr,
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    GDPR Article 15 - Right of Access
    GDPR Article 20 - Right to Data Portability
    
    Export all data associated with an email address.
    """
    email = email.lower()
    
    # Collect all data
    data = {
        "email": email,
        "export_date": datetime.utcnow().isoformat(),
        "payer_info": [],
        "payment_sessions": [],
        "merchant_account": None,
        "consent_records": []
    }
    
    # PayerInfo
    payer_records = db.query(PayerInfo).filter(PayerInfo.email == email).all()
    for payer in payer_records:
        data["payer_info"].append({
            "name": payer.name,
            "phone": payer.phone,
            "billing_address": {
                "line1": payer.billing_address_line1,
                "city": payer.billing_city,
                "country": payer.billing_country
            },
            "created_at": payer.created_at.isoformat() if payer.created_at else None
        })
    
    # Payment Sessions
    sessions = db.query(PaymentSession).filter(
        PaymentSession.payer_email == email
    ).all()
    
    for session in sessions:
        data["payment_sessions"].append({
            "id": session.id,
            "amount": str(session.amount_fiat),
            "currency": session.fiat_currency,
            "status": session.status.value,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "paid_at": session.paid_at.isoformat() if session.paid_at else None
        })
    
    # Merchant Account
    merchant = db.query(Merchant).filter(Merchant.email == email).first()
    if merchant:
        data["merchant_account"] = {
            "name": merchant.name,
            "created_at": merchant.created_at.isoformat() if merchant.created_at else None,
            "is_active": merchant.is_active
        }
    
    # Consent Records
    consents = db.query(ConsentRecord).filter(ConsentRecord.email == email).all()
    for consent in consents:
        data["consent_records"].append({
            "consent_type": consent.consent_type,
            "granted": consent.granted,
            "granted_at": consent.granted_at.isoformat() if consent.granted_at else None
        })
    
    # Log data export
    AuditLogger.log_action(
        db=db,
        actor_id=current_user["id"],
        actor_type="admin",
        action="gdpr_data_export",
        resource_type="user_data",
        resource_id=email,
        details={"email": email},
        status="success"
    )
    
    return data


def send_deletion_confirmation_email(
    email: str,
    records_anonymized: int,
    records_deleted: int
):
    """
    Send confirmation email after data deletion.
    In production, integrate with email service (SendGrid, SES, etc.)
    """
    logger.info(
        f"Sending deletion confirmation to {email}: "
        f"{records_anonymized} anonymized, {records_deleted} deleted"
    )
    # TODO: Integrate with email service
    pass
