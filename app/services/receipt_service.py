"""
Payment Receipt Generation Service

Automatically generates receipts/invoices for paid payment sessions.
Supports PDF generation and email delivery.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any
import secrets

from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.pdfgen import canvas
from io import BytesIO

from app.models.models import (
    PaymentSession, Invoice, InvoiceStatus, Merchant, PaymentStatus
)
from app.core.config import settings

logger = logging.getLogger(__name__)


class ReceiptService:
    """Service for generating payment receipts and invoices"""

    def __init__(self, db: Session):
        self.db = db

    def generate_receipt_for_payment(
        self, 
        payment_session_id: str,
        auto_send_email: bool = False
    ) -> Optional[Invoice]:
        """
        Generate a receipt/invoice for a paid payment session.
        
        Args:
            payment_session_id: Payment session ID
            auto_send_email: Whether to send receipt via email
            
        Returns:
            Invoice object or None if payment not paid
        """
        # Get payment session
        payment = self.db.query(PaymentSession).filter(
            PaymentSession.id == payment_session_id
        ).first()

        if not payment:
            logger.error(f"Payment session {payment_session_id} not found")
            return None

        # Only generate receipt for paid payments
        if payment.status not in (PaymentStatus.PAID, PaymentStatus.CONFIRMED):
            logger.warning(f"Payment {payment_session_id} not paid, status: {payment.status}")
            return None

        # Check if receipt already exists
        existing = self.db.query(Invoice).filter(
            Invoice.payment_session_id == payment_session_id
        ).first()

        if existing:
            logger.info(f"Receipt already exists for payment {payment_session_id}: {existing.id}")
            return existing

        # Get merchant
        merchant = self.db.query(Merchant).filter(
            Merchant.id == payment.merchant_id
        ).first()

        if not merchant:
            logger.error(f"Merchant {payment.merchant_id} not found")
            return None

        # Generate invoice number
        invoice_number = self._generate_invoice_number(merchant.id)

        # Create invoice/receipt
        invoice = Invoice(
            id=f"rcpt_{secrets.token_urlsafe(12)}",
            invoice_number=invoice_number,
            merchant_id=merchant.id,
            payment_session_id=payment_session_id,
            
            # Customer info
            customer_email=payment.payer_email or "customer@example.com",
            customer_name=payment.payer_name or "Customer",
            
            # Invoice details
            description=f"Payment for Order {payment.order_id or payment.id}",
            line_items=[{
                "description": f"Payment via {payment.chain} ({payment.token})",
                "quantity": 1,
                "unit_price": float(payment.amount_fiat),
                "total": float(payment.amount_fiat)
            }],
            
            # Amounts
            subtotal=payment.amount_fiat,
            tax=Decimal("0"),
            discount=payment.discount_amount or Decimal("0"),
            total=payment.amount_fiat,
            fiat_currency=payment.fiat_currency,
            
            # Payment tracking
            amount_paid=payment.amount_fiat,
            
            # Blockchain details
            tx_hash=payment.tx_hash,
            chain=payment.chain,
            token_symbol=payment.token,
            token_amount=payment.amount_token,
            
            # Multi-currency
            payer_currency=payment.payer_currency,
            payer_amount_local=payment.payer_amount_local,
            merchant_currency=payment.merchant_currency,
            merchant_amount_local=payment.merchant_amount_local,
            
            # Status & dates
            status=InvoiceStatus.PAID,
            issue_date=payment.paid_at or datetime.utcnow(),
            due_date=payment.paid_at or datetime.utcnow(),
            paid_at=payment.paid_at,
            
            # Metadata
            notes=f"Receipt for payment session {payment.id}",
            terms="Thank you for your payment!",
            footer=f"Processed via {merchant.name}",
            invoice_metadata={
                "type": "receipt",
                "payment_session_id": payment.id,
                "order_id": payment.order_id,
                "generated_at": datetime.utcnow().isoformat(),
            }
        )

        self.db.add(invoice)
        self.db.commit()
        self.db.refresh(invoice)

        logger.info(f"✅ Receipt generated: {invoice.id} for payment {payment_session_id}")

        # Send email if requested
        if auto_send_email and payment.payer_email:
            try:
                self._send_receipt_email(invoice)
            except Exception as e:
                logger.error(f"Failed to send receipt email: {e}")

        return invoice

    def generate_pdf(self, invoice_id: str) -> Optional[BytesIO]:
        """
        Generate PDF for an invoice/receipt.
        
        Args:
            invoice_id: Invoice ID
            
        Returns:
            BytesIO buffer containing PDF or None
        """
        invoice = self.db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not invoice:
            return None

        merchant = invoice.merchant
        if not merchant:
            return None

        # Create PDF buffer
        buffer = BytesIO()
        
        # Create PDF document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=18,
        )

        # Container for PDF elements
        elements = []
        styles = getSampleStyleSheet()

        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=30,
        )

        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#333333'),
            spaceAfter=12,
        )

        # Title
        is_receipt = invoice.invoice_metadata and invoice.invoice_metadata.get('type') == 'receipt'
        title = "PAYMENT RECEIPT" if is_receipt else "INVOICE"
        elements.append(Paragraph(title, title_style))
        elements.append(Spacer(1, 0.2 * inch))

        # Merchant info
        merchant_info = f"""
        <b>{merchant.name}</b><br/>
        {merchant.business_email or merchant.email}<br/>
        {merchant.country or ''}<br/>
        """
        elements.append(Paragraph(merchant_info, styles['Normal']))
        elements.append(Spacer(1, 0.3 * inch))

        # Invoice details table
        invoice_data = [
            ['Invoice Number:', invoice.invoice_number],
            ['Issue Date:', invoice.issue_date.strftime('%B %d, %Y')],
            ['Status:', invoice.status.value.upper()],
        ]

        if invoice.paid_at:
            invoice_data.append(['Paid Date:', invoice.paid_at.strftime('%B %d, %Y %I:%M %p')])

        if invoice.tx_hash:
            invoice_data.append(['Transaction:', invoice.tx_hash[:16] + '...'])

        invoice_table = Table(invoice_data, colWidths=[2*inch, 4*inch])
        invoice_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#666666')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(invoice_table)
        elements.append(Spacer(1, 0.3 * inch))

        # Customer info
        elements.append(Paragraph('Bill To:', heading_style))
        customer_info = f"""
        <b>{invoice.customer_name or 'Customer'}</b><br/>
        {invoice.customer_email}<br/>
        """
        elements.append(Paragraph(customer_info, styles['Normal']))
        elements.append(Spacer(1, 0.3 * inch))

        # Line items
        elements.append(Paragraph('Items:', heading_style))
        
        line_items_data = [['Description', 'Quantity', 'Unit Price', 'Total']]
        
        if invoice.line_items:
            for item in invoice.line_items:
                line_items_data.append([
                    item.get('description', ''),
                    str(item.get('quantity', 1)),
                    f"${item.get('unit_price', 0):.2f}",
                    f"${item.get('total', 0):.2f}"
                ])

        line_items_table = Table(line_items_data, colWidths=[3*inch, 1*inch, 1.5*inch, 1.5*inch])
        line_items_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f0f0f0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#333333')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e0e0e0')),
        ]))
        elements.append(line_items_table)
        elements.append(Spacer(1, 0.3 * inch))

        # Totals
        totals_data = []
        
        if invoice.discount and invoice.discount > 0:
            totals_data.append(['Subtotal:', f"${float(invoice.subtotal):.2f}"])
            totals_data.append(['Discount:', f"-${float(invoice.discount):.2f}"])
        
        if invoice.tax and invoice.tax > 0:
            totals_data.append(['Tax:', f"${float(invoice.tax):.2f}"])
        
        totals_data.append(['Total:', f"${float(invoice.total):.2f} {invoice.fiat_currency}"])
        
        if invoice.amount_paid:
            totals_data.append(['Amount Paid:', f"${float(invoice.amount_paid):.2f}"])

        totals_table = Table(totals_data, colWidths=[5*inch, 2*inch])
        totals_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, -1), (-1, -1), 12),
            ('LINEABOVE', (0, -1), (-1, -1), 2, colors.HexColor('#333333')),
            ('TOPPADDING', (0, -1), (-1, -1), 12),
        ]))
        elements.append(totals_table)
        elements.append(Spacer(1, 0.5 * inch))

        # Payment details
        if invoice.chain and invoice.token_symbol:
            elements.append(Paragraph('Payment Details:', heading_style))
            payment_details = f"""
            <b>Blockchain:</b> {invoice.chain.upper()}<br/>
            <b>Token:</b> {invoice.token_symbol}<br/>
            <b>Amount:</b> {invoice.token_amount or 'N/A'}<br/>
            """
            if invoice.tx_hash:
                payment_details += f"<b>Transaction Hash:</b> {invoice.tx_hash}<br/>"
            
            elements.append(Paragraph(payment_details, styles['Normal']))
            elements.append(Spacer(1, 0.3 * inch))

        # Footer
        if invoice.footer:
            elements.append(Spacer(1, 0.3 * inch))
            elements.append(Paragraph(invoice.footer, styles['Normal']))

        # Build PDF
        doc.build(elements)
        buffer.seek(0)
        
        return buffer

    def _generate_invoice_number(self, merchant_id) -> str:
        """Generate unique invoice number for merchant"""
        # Count existing invoices for this merchant
        count = self.db.query(Invoice).filter(
            Invoice.merchant_id == merchant_id
        ).count()
        
        # Format: RCPT-YYYYMMDD-XXXX
        date_str = datetime.utcnow().strftime('%Y%m%d')
        number = f"RCPT-{date_str}-{count + 1:04d}"
        
        return number

    def _send_receipt_email(self, invoice: Invoice):
        """Send receipt via email (placeholder for future implementation)"""
        # TODO: Implement email sending
        logger.info(f"Email sending not yet implemented for invoice {invoice.id}")
        pass


def generate_receipt_for_payment(db: Session, payment_session_id: str) -> Optional[Invoice]:
    """
    Convenience function to generate receipt for a payment.
    Can be called from payment confirmation handlers.
    """
    service = ReceiptService(db)
    return service.generate_receipt_for_payment(payment_session_id)
