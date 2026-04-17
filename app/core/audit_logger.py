"""
Audit Logging System
Provides immutable audit trail for all sensitive operations
"""
import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import Request

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Centralized audit logging for compliance and security.
    Logs all sensitive operations to an immutable audit trail.
    """
    
    @staticmethod
    def log_action(
        db: Session,
        actor_id: str,
        actor_type: str,  # "merchant", "admin", "team_member", "system"
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
        status: str = "success",  # "success", "failure", "error"
    ) -> str:
        """
        Log an audit event.
        
        Args:
            db: Database session
            actor_id: ID of the user/system performing the action
            actor_type: Type of actor (merchant, admin, team_member, system)
            action: Action performed (e.g., "refund_created", "payment_confirmed")
            resource_type: Type of resource affected (e.g., "payment", "refund")
            resource_id: ID of the resource
            details: Additional context (JSON serializable)
            ip_address: Client IP address
            user_agent: Client user agent
            request_id: Request correlation ID
            status: Operation status
        
        Returns:
            Audit log entry ID
        """
        from app.models.models import AuditLog
        
        try:
            audit_entry = AuditLog(
                id=uuid.uuid4(),
                actor_id=uuid.UUID(actor_id) if actor_id and actor_id != "system" else None,
                actor_type=actor_type,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details or {},
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
                status=status,
                timestamp=datetime.utcnow()
            )
            
            db.add(audit_entry)
            db.commit()
            
            logger.info(
                f"AUDIT: {actor_type}:{actor_id} performed {action} on "
                f"{resource_type}:{resource_id} - {status}"
            )
            
            return str(audit_entry.id)
            
        except Exception as e:
            logger.error(f"Failed to create audit log: {e}", exc_info=True)
            # Don't fail the operation if audit logging fails
            return ""
    
    @staticmethod
    def log_from_request(
        db: Session,
        request: Request,
        current_user: Dict[str, Any],
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        status: str = "success"
    ) -> str:
        """
        Convenience method to log from a FastAPI request context.
        
        Args:
            db: Database session
            request: FastAPI Request object
            current_user: Current user dict from JWT ({"id": "...", "role": "..."})
            action: Action performed
            resource_type: Type of resource
            resource_id: Resource ID
            details: Additional details
            status: Operation status
        
        Returns:
            Audit log entry ID
        """
        # Extract IP address
        ip_address = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip_address = forwarded.split(",")[0].strip()
        
        # Extract user agent
        user_agent = request.headers.get("User-Agent", "unknown")
        
        # Extract request ID (if set by middleware)
        request_id = request.headers.get("X-Request-ID")
        
        return AuditLogger.log_action(
            db=db,
            actor_id=current_user.get("id", "unknown"),
            actor_type=current_user.get("role", "unknown"),
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            status=status
        )
    
    @staticmethod
    def log_payment_event(
        db: Session,
        payment_session_id: str,
        event_type: str,
        actor_id: Optional[str] = None,
        actor_type: str = "system",
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> str:
        """
        Log a payment-related event.
        
        Args:
            db: Database session
            payment_session_id: Payment session ID
            event_type: Event type (e.g., "payment_created", "payment_confirmed")
            actor_id: Actor ID (optional, defaults to system)
            actor_type: Actor type
            details: Additional details
            ip_address: Client IP
        
        Returns:
            Audit log entry ID
        """
        return AuditLogger.log_action(
            db=db,
            actor_id=actor_id or "system",
            actor_type=actor_type,
            action=event_type,
            resource_type="payment_session",
            resource_id=payment_session_id,
            details=details,
            ip_address=ip_address
        )
    
    @staticmethod
    def log_refund_event(
        db: Session,
        refund_id: str,
        event_type: str,
        actor_id: str,
        actor_type: str = "merchant",
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> str:
        """
        Log a refund-related event.
        
        Args:
            db: Database session
            refund_id: Refund ID
            event_type: Event type (e.g., "refund_created", "refund_completed")
            actor_id: Actor ID
            actor_type: Actor type
            details: Additional details
            ip_address: Client IP
        
        Returns:
            Audit log entry ID
        """
        return AuditLogger.log_action(
            db=db,
            actor_id=actor_id,
            actor_type=actor_type,
            action=event_type,
            resource_type="refund",
            resource_id=refund_id,
            details=details,
            ip_address=ip_address
        )
    
    @staticmethod
    def log_auth_event(
        db: Session,
        event_type: str,
        actor_id: Optional[str] = None,
        actor_type: str = "merchant",
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        status: str = "success"
    ) -> str:
        """
        Log an authentication-related event.
        
        Args:
            db: Database session
            event_type: Event type (e.g., "login_success", "login_failed")
            actor_id: Actor ID (optional for failed logins)
            actor_type: Actor type
            details: Additional details (e.g., email attempted)
            ip_address: Client IP
            user_agent: Client user agent
            status: Event status
        
        Returns:
            Audit log entry ID
        """
        return AuditLogger.log_action(
            db=db,
            actor_id=actor_id or "anonymous",
            actor_type=actor_type,
            action=event_type,
            resource_type="authentication",
            resource_id=None,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            status=status
        )


# Convenience function for dependency injection
def get_audit_logger() -> AuditLogger:
    """Dependency to get audit logger instance"""
    return AuditLogger()
