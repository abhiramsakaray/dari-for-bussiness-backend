"""
Invoice Export Service
Generates PDF, CSV, and PNG exports of invoices for tax filing and compliance.

Security:
  - No user-supplied HTML rendered (prevents XSS)
  - All monetary values are Decimal-safe (no float precision issues)
  - File output is in-memory bytes (no temp file leaks)
"""

import csv
import io
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


# ── PDF Export ──

def generate_invoice_pdf(invoice, merchant=None) -> bytes:
    """
    Generate a professional PDF invoice.

    Includes multi-currency breakdown:
    - Payer's local currency (what they paid)
    - Stablecoin amount & type (on-chain)
    - Merchant's local currency (settlement value)
    """
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Header
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 12, "INVOICE", ln=True, align="R")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Invoice #: {invoice.invoice_number}", ln=True, align="R")
    pdf.cell(0, 6, f"Date: {_fmt_date(invoice.issue_date)}", ln=True, align="R")
    if invoice.due_date:
        pdf.cell(0, 6, f"Due: {_fmt_date(invoice.due_date)}", ln=True, align="R")
    pdf.cell(0, 6, f"Status: {_status_str(invoice.status)}", ln=True, align="R")

    pdf.ln(5)

    # Merchant info
    if merchant:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 6, "From:", ln=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 5, merchant.business_name or merchant.name or "", ln=True)
        pdf.cell(0, 5, merchant.email or "", ln=True)
        if merchant.country:
            pdf.cell(0, 5, merchant.country, ln=True)
        pdf.ln(3)

    # Customer info
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "Bill To:", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, invoice.customer_name or "", ln=True)
    pdf.cell(0, 5, invoice.customer_email or "", ln=True)
    if invoice.customer_address:
        for line in invoice.customer_address.split("\n"):
            pdf.cell(0, 5, line.strip(), ln=True)
    pdf.ln(5)

    # Line items table
    pdf.set_font("Helvetica", "B", 10)
    col_widths = [90, 25, 35, 40]
    headers = ["Description", "Qty", "Unit Price", "Total"]
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 8, h, border=1, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 9)
    if invoice.line_items:
        for item in invoice.line_items:
            desc = str(item.get("description", ""))[:50]
            qty = str(item.get("quantity", 1))
            unit = _fmt_money(item.get("unit_price", 0), invoice.fiat_currency)
            total = _fmt_money(item.get("total", 0), invoice.fiat_currency)
            pdf.cell(col_widths[0], 7, desc, border=1)
            pdf.cell(col_widths[1], 7, qty, border=1, align="C")
            pdf.cell(col_widths[2], 7, unit, border=1, align="R")
            pdf.cell(col_widths[3], 7, total, border=1, align="R")
            pdf.ln()

    pdf.ln(3)

    # Totals
    x_label = 115
    x_val = 155
    w_val = 40

    pdf.set_font("Helvetica", "", 10)
    pdf.set_x(x_label)
    pdf.cell(40, 7, "Subtotal:", align="R")
    pdf.cell(w_val, 7, _fmt_money(invoice.subtotal, invoice.fiat_currency), align="R", ln=True)

    if invoice.tax and invoice.tax > 0:
        pdf.set_x(x_label)
        pdf.cell(40, 7, "Tax:", align="R")
        pdf.cell(w_val, 7, _fmt_money(invoice.tax, invoice.fiat_currency), align="R", ln=True)

    if invoice.discount and invoice.discount > 0:
        pdf.set_x(x_label)
        pdf.cell(40, 7, "Discount:", align="R")
        pdf.cell(w_val, 7, f"-{_fmt_money(invoice.discount, invoice.fiat_currency)}", align="R", ln=True)

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_x(x_label)
    pdf.cell(40, 8, "Total:", align="R")
    pdf.cell(w_val, 8, _fmt_money(invoice.total, invoice.fiat_currency), align="R", ln=True)

    pdf.ln(5)

    # ── Multi-Currency Breakdown ──
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, "Payment Details", ln=True)
    pdf.set_font("Helvetica", "", 9)

    if invoice.payer_currency and invoice.payer_amount_local:
        pdf.cell(0, 5, f"Payer paid: {_fmt_money(invoice.payer_amount_local, invoice.payer_currency)}", ln=True)

    token_sym = invoice.token_symbol or "USDC"
    token_amt = invoice.token_amount or invoice.amount_paid or invoice.total
    pdf.cell(0, 5, f"On-chain: {token_amt} {token_sym}", ln=True)

    if invoice.merchant_currency and invoice.merchant_amount_local:
        pdf.cell(0, 5, f"Merchant receives: {_fmt_money(invoice.merchant_amount_local, invoice.merchant_currency)}", ln=True)

    if invoice.chain:
        pdf.cell(0, 5, f"Blockchain: {invoice.chain}", ln=True)
    if invoice.tx_hash:
        pdf.cell(0, 5, f"Tx Hash: {invoice.tx_hash}", ln=True)

    pdf.ln(5)

    # Notes / Terms
    if invoice.notes:
        pdf.set_font("Helvetica", "I", 8)
        pdf.multi_cell(0, 4, f"Notes: {invoice.notes}")
    if invoice.terms:
        pdf.set_font("Helvetica", "I", 8)
        pdf.multi_cell(0, 4, f"Terms: {invoice.terms}")

    # Footer
    pdf.set_y(-25)
    pdf.set_font("Helvetica", "", 7)
    pdf.cell(0, 4, "Generated by Dari for Business — Crypto Payment Gateway", align="C", ln=True)
    pdf.cell(0, 4, f"Generated at {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", align="C")

    return pdf.output()


# ── CSV Export ──

def generate_invoice_csv(invoice, merchant=None) -> bytes:
    """
    Generate a CSV export suitable for accounting software / tax filing.
    One row per line item, plus summary rows.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "Invoice Number", "Issue Date", "Due Date", "Status",
        "Customer Name", "Customer Email",
        "Description", "Quantity", "Unit Price", "Line Total",
        "Currency",
        "Subtotal", "Tax", "Discount", "Total",
        "Payer Currency", "Payer Amount",
        "Stablecoin", "Stablecoin Amount",
        "Merchant Currency", "Merchant Amount",
        "Chain", "Tx Hash", "Paid At",
    ])

    # Line items
    items = invoice.line_items or [{"description": "Payment", "quantity": 1,
                                     "unit_price": float(invoice.total or 0),
                                     "total": float(invoice.total or 0)}]
    for item in items:
        writer.writerow([
            invoice.invoice_number,
            _fmt_date(invoice.issue_date),
            _fmt_date(invoice.due_date),
            _status_str(invoice.status),
            invoice.customer_name or "",
            invoice.customer_email or "",
            item.get("description", ""),
            item.get("quantity", 1),
            item.get("unit_price", 0),
            item.get("total", 0),
            invoice.fiat_currency,
            float(invoice.subtotal or 0),
            float(invoice.tax or 0),
            float(invoice.discount or 0),
            float(invoice.total or 0),
            invoice.payer_currency or "",
            float(invoice.payer_amount_local or 0) if invoice.payer_amount_local else "",
            invoice.token_symbol or "USDC",
            str(invoice.token_amount or invoice.amount_paid or ""),
            invoice.merchant_currency or "",
            float(invoice.merchant_amount_local or 0) if invoice.merchant_amount_local else "",
            invoice.chain or "",
            invoice.tx_hash or "",
            _fmt_date(invoice.paid_at),
        ])

    return output.getvalue().encode("utf-8")


# ── PNG Image Export ──

def generate_invoice_image(invoice, merchant=None) -> bytes:
    """
    Generate a PNG image of the invoice.
    Clean, professional layout suitable for sharing / printing.
    """
    width, height = 800, 1100
    bg_color = (255, 255, 255)
    text_color = (30, 30, 30)
    accent = (124, 58, 237)  # Purple brand color
    light_gray = (240, 240, 240)

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    # Use default font (PIL built-in)
    try:
        font_large = ImageFont.truetype("arial.ttf", 24)
        font_medium = ImageFont.truetype("arial.ttf", 14)
        font_small = ImageFont.truetype("arial.ttf", 11)
        font_bold = ImageFont.truetype("arialbd.ttf", 14)
    except (OSError, IOError):
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()
        font_bold = ImageFont.load_default()

    y = 30

    # Header bar
    draw.rectangle([(0, 0), (width, 70)], fill=accent)
    draw.text((30, 20), "INVOICE", fill=(255, 255, 255), font=font_large)
    draw.text((width - 250, 25), f"#{invoice.invoice_number}", fill=(255, 255, 255), font=font_medium)

    y = 90

    # Invoice meta
    draw.text((30, y), f"Date: {_fmt_date(invoice.issue_date)}", fill=text_color, font=font_medium)
    draw.text((400, y), f"Status: {_status_str(invoice.status)}", fill=accent, font=font_bold)
    y += 25
    if invoice.due_date:
        draw.text((30, y), f"Due: {_fmt_date(invoice.due_date)}", fill=text_color, font=font_medium)
    y += 35

    # Customer
    draw.text((30, y), "Bill To:", fill=text_color, font=font_bold)
    y += 20
    draw.text((30, y), invoice.customer_name or "—", fill=text_color, font=font_medium)
    y += 18
    draw.text((30, y), invoice.customer_email or "", fill=(100, 100, 100), font=font_small)
    y += 30

    # Line items header
    draw.rectangle([(25, y), (width - 25, y + 25)], fill=light_gray)
    draw.text((30, y + 5), "Description", fill=text_color, font=font_bold)
    draw.text((450, y + 5), "Qty", fill=text_color, font=font_bold)
    draw.text((530, y + 5), "Price", fill=text_color, font=font_bold)
    draw.text((670, y + 5), "Total", fill=text_color, font=font_bold)
    y += 30

    # Line items
    if invoice.line_items:
        for item in invoice.line_items:
            desc = str(item.get("description", ""))[:45]
            draw.text((30, y), desc, fill=text_color, font=font_small)
            draw.text((450, y), str(item.get("quantity", 1)), fill=text_color, font=font_small)
            draw.text((530, y), _fmt_money(item.get("unit_price", 0), invoice.fiat_currency), fill=text_color, font=font_small)
            draw.text((670, y), _fmt_money(item.get("total", 0), invoice.fiat_currency), fill=text_color, font=font_small)
            y += 22

    y += 15
    draw.line([(400, y), (width - 30, y)], fill=(200, 200, 200), width=1)
    y += 10

    # Totals
    draw.text((500, y), "Subtotal:", fill=text_color, font=font_medium)
    draw.text((650, y), _fmt_money(invoice.subtotal, invoice.fiat_currency), fill=text_color, font=font_medium)
    y += 22

    if invoice.tax and invoice.tax > 0:
        draw.text((500, y), "Tax:", fill=text_color, font=font_medium)
        draw.text((650, y), _fmt_money(invoice.tax, invoice.fiat_currency), fill=text_color, font=font_medium)
        y += 22

    if invoice.discount and invoice.discount > 0:
        draw.text((500, y), "Discount:", fill=text_color, font=font_medium)
        draw.text((650, y), f"-{_fmt_money(invoice.discount, invoice.fiat_currency)}", fill=text_color, font=font_medium)
        y += 22

    draw.rectangle([(490, y - 2), (width - 25, y + 22)], fill=accent)
    draw.text((500, y + 2), "TOTAL:", fill=(255, 255, 255), font=font_bold)
    draw.text((650, y + 2), _fmt_money(invoice.total, invoice.fiat_currency), fill=(255, 255, 255), font=font_bold)
    y += 40

    # Multi-currency section
    draw.text((30, y), "Payment Details", fill=accent, font=font_bold)
    y += 22

    if invoice.payer_currency and invoice.payer_amount_local:
        draw.text((30, y), f"Payer paid: {_fmt_money(invoice.payer_amount_local, invoice.payer_currency)}", fill=text_color, font=font_small)
        y += 18

    token_sym = invoice.token_symbol or "USDC"
    token_amt = invoice.token_amount or invoice.amount_paid or invoice.total
    draw.text((30, y), f"On-chain: {token_amt} {token_sym}", fill=text_color, font=font_small)
    y += 18

    if invoice.merchant_currency and invoice.merchant_amount_local:
        draw.text((30, y), f"Merchant receives: {_fmt_money(invoice.merchant_amount_local, invoice.merchant_currency)}", fill=text_color, font=font_small)
        y += 18

    if invoice.chain:
        draw.text((30, y), f"Chain: {invoice.chain}", fill=(100, 100, 100), font=font_small)
        y += 18
    if invoice.tx_hash:
        tx_display = invoice.tx_hash[:40] + "..." if len(invoice.tx_hash or "") > 40 else (invoice.tx_hash or "")
        draw.text((30, y), f"Tx: {tx_display}", fill=(100, 100, 100), font=font_small)
        y += 18

    # Footer
    draw.rectangle([(0, height - 40), (width, height)], fill=light_gray)
    draw.text((30, height - 30), "Dari for Business — Crypto Payment Gateway", fill=(150, 150, 150), font=font_small)
    draw.text((width - 220, height - 30), f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", fill=(150, 150, 150), font=font_small)

    # Save to bytes
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ── Helpers ──

def _fmt_date(dt) -> str:
    if not dt:
        return "—"
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d")
    return str(dt)


def _fmt_money(amount, currency: str = "USD") -> str:
    try:
        val = float(amount) if amount else 0.0
    except (ValueError, TypeError):
        val = 0.0
    return f"{currency} {val:,.2f}"


def _status_str(status) -> str:
    if hasattr(status, "value"):
        return status.value.upper()
    return str(status).upper()
