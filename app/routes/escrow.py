"""
Escrow API Routes - Soroban Smart Contract Integration
Endpoints for creating and managing escrow payments
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional
from app.core import require_merchant, require_admin
from app.services.soroban_escrow import escrow_service
from app.models import Merchant, Admin

router = APIRouter(prefix="/api/escrow", tags=["Escrow (Soroban)"])


class CreateEscrowRequest(BaseModel):
    customer_secret: str = Field(..., description="Customer's Stellar secret key (temporary - in production, use wallet signing)")
    amount: str = Field(..., description="USDC amount (e.g., '50.00')")
    session_id: str = Field(..., description="Payment session ID")
    timeout_hours: Optional[int] = Field(24, description="Refund timeout in hours")


class ReleaseEscrowRequest(BaseModel):
    session_id: str = Field(..., description="Payment session ID to release")


class RefundEscrowRequest(BaseModel):
    customer_secret: str = Field(..., description="Customer's Stellar secret key")
    session_id: str = Field(..., description="Payment session ID to refund")


@router.post("/create", summary="Create Escrow Payment")
async def create_escrow_payment(
    request: CreateEscrowRequest,
    merchant: Merchant = Depends(require_merchant)
):
    """
    Create an escrow payment using Soroban smart contract.
    
    Funds are locked in the contract until:
    - Merchant releases (delivery confirmed), OR
    - Customer refunds after timeout (no delivery), OR
    - Admin force refunds (dispute resolution)
    
    **Note:** In production, customer should sign with wallet (Freighter, Lobstr)
    instead of sending secret key.
    """
    try:
        timeout_seconds = request.timeout_hours * 3600
        
        result = await escrow_service.create_escrow_payment(
            customer_secret=request.customer_secret,
            merchant_address=merchant.stellar_address,
            amount=request.amount,
            session_id=request.session_id,
            timeout_seconds=timeout_seconds,
        )
        
        return {
            "success": True,
            "message": "Escrow payment created successfully",
            **result
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create escrow: {str(e)}"
        )


@router.post("/release/{session_id}", summary="Release Escrow to Merchant")
async def release_escrow(
    session_id: str,
    merchant: Merchant = Depends(require_merchant)
):
    """
    Merchant confirms delivery and releases escrowed funds.
    
    This transfers USDC from escrow contract to merchant's wallet.
    Only the merchant who is part of the escrow can release.
    
    **Important:** You need merchant's Stellar secret key configured.
    """
    try:
        # TODO: In production, get merchant secret from secure key management
        # For now, this is a placeholder - you'd need to securely store/retrieve merchant secrets
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Merchant secret key management not implemented. "
                   "Please use Stellar wallet to sign this transaction manually."
        )
        
        # Uncomment when merchant secret is available:
        # result = await escrow_service.release_escrow(
        #     merchant_secret=merchant.stellar_secret,  # Need to add this field
        #     session_id=session_id,
        # )
        # 
        # return {
        #     "success": True,
        #     "message": "Escrow released successfully",
        #     **result
        # }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to release escrow: {str(e)}"
        )


@router.post("/refund", summary="Customer Refund After Timeout")
async def refund_escrow(request: RefundEscrowRequest):
    """
    Customer requests refund after timeout period.
    
    Only works if:
    - Escrow is still in "pending" status
    - Timeout period has passed
    - Customer is the original payer
    """
    try:
        result = await escrow_service.refund_escrow(
            customer_secret=request.customer_secret,
            session_id=request.session_id,
        )
        
        return {
            "success": True,
            "message": "Refund processed successfully",
            **result
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to refund escrow: {str(e)}"
        )


@router.post("/admin/refund/{session_id}", summary="Admin Force Refund")
async def admin_force_refund(
    session_id: str,
    admin: Admin = Depends(require_admin)
):
    """
    ChainPe admin can force refund for customer protection.
    
    Use cases:
    - Merchant dispute
    - Fraudulent merchant
    - Customer service escalation
    
    **Requires:** Admin authorization
    """
    try:
        # TODO: Get admin secret from secure storage
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Admin secret key management not implemented."
        )
        
        # Uncomment when admin secret is available:
        # result = await escrow_service.admin_refund(
        #     admin_secret=settings.ADMIN_STELLAR_SECRET,
        #     session_id=session_id,
        # )
        # 
        # return {
        #     "success": True,
        #     "message": "Admin refund processed",
        #     **result
        # }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to process admin refund: {str(e)}"
        )


@router.get("/status/{session_id}", summary="Get Escrow Status")
async def get_escrow_status(session_id: str):
    """
    Query escrow status from smart contract.
    
    Returns:
    - Escrow amount
    - Current status (pending/completed/refunded)
    - Timeout information
    - Participant addresses
    """
    try:
        result = await escrow_service.get_escrow_status(session_id)
        
        return {
            "success": True,
            **result
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Escrow not found: {str(e)}"
        )
