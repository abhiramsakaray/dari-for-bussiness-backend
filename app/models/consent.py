"""
GDPR Consent Management Models
Tracks user consent for data processing activities
"""
from sqlalchemy import Column, String, Boolean, DateTime, Enum as SQLEnum, Text, Index
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
import enum

from app.core.database import Base


class ConsentType(str, enum.Enum):
    """Types of consent that can be granted"""
    MARKETING_EMAILS = "marketing_emails"
    ANALYTICS = "analytics"
    DATA_PROCESSING = "data_processing"
    THIRD_PARTY_SHARING = "third_party_sharing"
    PROFILING = "profiling"


class ConsentRecord(Base):
    """
    GDPR Article 7 - Conditions for consent
    
    Stores explicit consent records for data processing activities.
    Must be:
    - Freely given
    - Specific
    - Informed
    - Unambiguous
    - Withdrawable
    """
    __tablename__ = "consent_records"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # User identification
    email = Column(String(255), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=True)  # If registered user
    
    # Consent details
    consent_type = Column(SQLEnum(ConsentType), nullable=False)
    granted = Column(Boolean, nullable=False, default=False)
    
    # Consent metadata (GDPR Article 7.1 - burden of proof)
    granted_at = Column(DateTime, nullable=True)
    withdrawn_at = Column(DateTime, nullable=True)
    consent_text = Column(Text, nullable=False)  # Exact text shown to user
    consent_version = Column(String(50), nullable=False)  # Version of privacy policy
    
    # Proof of consent
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    consent_method = Column(String(50), nullable=False)  # "checkbox", "api", "email_link"
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes for efficient querying
    __table_args__ = (
        Index('idx_consent_email_type', 'email', 'consent_type'),
        Index('idx_consent_user_type', 'user_id', 'consent_type'),
        Index('idx_consent_granted_at', 'granted_at'),
    )
