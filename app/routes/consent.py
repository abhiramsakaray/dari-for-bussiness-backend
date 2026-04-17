"""
GDPR Consent Management Endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional
import uuid

from app.core.database import get_db
from app.core.audit_logger import AuditLogger
from app.models.consent import ConsentRecord, ConsentType
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/api/consent", tags=["Consent Management"])


class ConsentRequest(BaseModel):
    email: EmailStr
    consent_type: ConsentType
    granted: bool
    consent_text: str
    consent_version: str
    consent_method: str = "api"


class ConsentResponse(BaseModel):
    id: str
    email: str
    consent_type: ConsentType
    granted: bool
    granted_at: Optional[datetime]
    withdrawn_at: Optional[datetime]
    consent_version: str
    created_at: datetime


class ConsentListResponse(BaseModel):
    consents: List[ConsentResponse]
    total: int


@router.post("/grant", response_model=ConsentResponse)
async def grant_consent(
    request_data: ConsentRequest,
    req: Request,
    db: Session = Depends(get_db)
):
    """
    Record user consent for a specific data processing activity.
    
    GDPR Article 7 - Conditions for consent
    """
    email = request_data.email.lower()
    
    # Check if consent already exists
    existing = db.query(ConsentRecord).filter(
        ConsentRecord.email == email,
        ConsentRecord.consent_type == request_data.consent_type
    ).first()
    
    if existing:
        # Update existing consent
        existing.granted = request_data.granted
        existing.consent_text = request_data.consent_text
        existing.consent_version = request_data.consent_version
        existing.consent_method = request_data.consent_method
        existing.ip_address = req.client.host if req.client else None
        existing.user_agent = req.headers.get("user-agent")
        existing.updated_at = datetime.utcnow()
        
        if request_data.granted:
            existing.granted_at = datetime.utcnow()
            existing.withdrawn_at = None
        else:
            existing.withdrawn_at = datetime.utcnow()
        
        consent = existing
    else:
        # Create new consent record
        consent = ConsentRecord(
            email=email,
            consent_type=request_data.consent_type,
            granted=request_data.granted,
            granted_at=datetime.utcnow() if request_data.granted else None,
            consent_text=request_data.consent_text,
            consent_version=request_data.consent_version,
            consent_method=request_data.consent_method,
            ip_address=req.client.host if req.client else None,
            user_agent=req.headers.get("user-agent")
        )
        db.add(consent)
    
    db.commit()
    db.refresh(consent)
    
    # Audit log
    AuditLogger.log_action(
        db=db,
        actor_id="system",
        actor_type="system",
        action=f"consent_{'granted' if request_data.granted else 'withdrawn'}",
        resource_type="consent",
        resource_id=str(consent.id),
        details={
            "email": email,
            "consent_type": request_data.consent_type.value,
            "granted": request_data.granted
        },
        ip_address=req.client.host if req.client else None,
        status="success"
    )
    
    return ConsentResponse(
        id=str(consent.id),
        email=consent.email,
        consent_type=consent.consent_type,
        granted=consent.granted,
        granted_at=consent.granted_at,
        withdrawn_at=consent.withdrawn_at,
        consent_version=consent.consent_version,
        created_at=consent.created_at
    )


@router.get("/user/{email}", response_model=ConsentListResponse)
async def get_user_consents(
    email: EmailStr,
    db: Session = Depends(get_db)
):
    """
    Retrieve all consent records for a user.
    
    GDPR Article 15 - Right of access
    """
    email = email.lower()
    
    consents = db.query(ConsentRecord).filter(
        ConsentRecord.email == email
    ).order_by(ConsentRecord.created_at.desc()).all()
    
    return ConsentListResponse(
        consents=[
            ConsentResponse(
                id=str(c.id),
                email=c.email,
                consent_type=c.consent_type,
                granted=c.granted,
                granted_at=c.granted_at,
                withdrawn_at=c.withdrawn_at,
                consent_version=c.consent_version,
                created_at=c.created_at
            )
            for c in consents
        ],
        total=len(consents)
    )


@router.post("/withdraw")
async def withdraw_consent(
    email: EmailStr,
    consent_type: ConsentType,
    req: Request,
    db: Session = Depends(get_db)
):
    """
    Withdraw consent for a specific data processing activity.
    
    GDPR Article 7.3 - Right to withdraw consent
    """
    email = email.lower()
    
    consent = db.query(ConsentRecord).filter(
        ConsentRecord.email == email,
        ConsentRecord.consent_type == consent_type
    ).first()
    
    if not consent:
        raise HTTPException(status_code=404, detail="Consent record not found")
    
    consent.granted = False
    consent.withdrawn_at = datetime.utcnow()
    consent.updated_at = datetime.utcnow()
    
    db.commit()
    
    # Audit log
    AuditLogger.log_action(
        db=db,
        actor_id="system",
        actor_type="system",
        action="consent_withdrawn",
        resource_type="consent",
        resource_id=str(consent.id),
        details={
            "email": email,
            "consent_type": consent_type.value
        },
        ip_address=req.client.host if req.client else None,
        status="success"
    )
    
    return {"status": "success", "message": "Consent withdrawn"}


@router.get("/check/{email}/{consent_type}")
async def check_consent(
    email: EmailStr,
    consent_type: ConsentType,
    db: Session = Depends(get_db)
):
    """
    Check if user has granted consent for a specific activity.
    """
    email = email.lower()
    
    consent = db.query(ConsentRecord).filter(
        ConsentRecord.email == email,
        ConsentRecord.consent_type == consent_type
    ).first()
    
    if not consent:
        return {"has_consent": False, "message": "No consent record found"}
    
    return {
        "has_consent": consent.granted and consent.withdrawn_at is None,
        "granted_at": consent.granted_at.isoformat() if consent.granted_at else None,
        "consent_version": consent.consent_version
    }
