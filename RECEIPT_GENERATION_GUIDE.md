# Payment Receipt Generation - Complete Guide

## Overview

Automatic receipt/invoice generation for paid payments with PDF download functionality.

---

## Features

✅ Automatic receipt generation for paid payments  
✅ PDF generation with professional formatting  
✅ Download receipts as PDF  
✅ View receipts in browser  
✅ List all receipts  
✅ Email delivery (ready for future implementation)  
✅ Blockchain transaction details included  
✅ Multi-currency support  

---

## Installation

### 1. Install Dependencies

```bash
pip install reportlab==4.0.7
```

Or install all requirements:

```bash
pip install -r requirements.txt
```

### 2. Restart Application

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## API Endpoints

### Base URL
```
http://localhost:8000/receipts
```

### 1. Generate Receipt for Payment

**Endpoint:** `POST /receipts/payment/{payment_session_id}/generate`

**Description:** Generate a receipt for a paid payment session.

**Request:**
```http
POST /receipts/payment/pay_i0igisp16pbe3416/generate?send_email=false
Authorization: Bearer YOUR_JWT_TOKEN
```

**Response:**
```json
{
  "id": "rcpt_abc123xyz",
  "invoice_number": "RCPT-20260329-0001",
  "payment_session_id": "pay_i0igisp16pbe3416",
  "customer_email": "customer@example.com",
  "customer_name": "John Doe",
  "amount": 1.00,
  "currency": "USD",
  "status": "paid",
  "issue_date": "2026-04-09T13:03:39",
  "paid_at": "2026-04-09T13:03:39",
  "tx_hash": "0x8b944c3c85beeab73a96a25f46e09e6f03fc895e3e7e6c34320843d38d1c4d86",
  "chain": "polygon",
  "token": "USDC",
  "download_url": "/receipts/rcpt_abc123xyz/download",
  "view_url": "/receipts/rcpt_abc123xyz/view"
}
```

---

### 2. Download Receipt PDF

**Endpoint:** `GET /receipts/{receipt_id}/download`

**Description:** Download receipt as PDF file.

**Request:**
```http
GET /receipts/rcpt_abc123xyz/download
Authorization: Bearer YOUR_JWT_TOKEN
```

**Response:** PDF file download

**Headers:**
```
Content-Type: application/pdf
Content-Disposition: attachment; filename=receipt_RCPT-20260329-0001.pdf
```

---

### 3. View Receipt PDF (In Browser)

**Endpoint:** `GET /receipts/{receipt_id}/view`

**Description:** View receipt PDF in browser without downloading.

**Request:**
```http
GET /receipts/rcpt_abc123xyz/view
Authorization: Bearer YOUR_JWT_TOKEN
```

**Response:** PDF displayed inline in browser

---

### 4. Get Receipt Details

**Endpoint:** `GET /receipts/{receipt_id}`

**Description:** Get receipt metadata without PDF.

**Request:**
```http
GET /receipts/rcpt_abc123xyz
Authorization: Bearer YOUR_JWT_TOKEN
```

**Response:** Same as generate response

---

### 5. List All Receipts

**Endpoint:** `GET /receipts`

**Description:** List all receipts for merchant with pagination.

**Request:**
```http
GET /receipts?page=1&page_size=20
Authorization: Bearer YOUR_JWT_TOKEN
```

**Response:**
```json
{
  "receipts": [
    {
      "id": "rcpt_abc123xyz",
      "invoice_number": "RCPT-20260329-0001",
      "payment_session_id": "pay_i0igisp16pbe3416",
      "customer_email": "customer@example.com",
      "customer_name": "John Doe",
      "amount": 1.00,
      "currency": "USD",
      "status": "paid",
      "issue_date": "2026-04-09T13:03:39",
      "paid_at": "2026-04-09T13:03:39",
      "tx_hash": "0x8b944c3c...",
      "chain": "polygon",
      "token": "USDC",
      "download_url": "/receipts/rcpt_abc123xyz/download",
      "view_url": "/receipts/rcpt_abc123xyz/view"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20,
  "pages": 1
}
```

---

## Frontend Integration

### React/Next.js Example

```javascript
// API Client
class ReceiptAPI {
  constructor(baseURL = 'http://localhost:8000') {
    this.baseURL = baseURL;
  }

  getHeaders() {
    const token = localStorage.getItem('token');
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };
  }

  // Generate receipt for payment
  async generateReceipt(paymentSessionId, sendEmail = false) {
    const response = await fetch(
      `${this.baseURL}/receipts/payment/${paymentSessionId}/generate?send_email=${sendEmail}`,
      {
        method: 'POST',
        headers: this.getHeaders()
      }
    );
    
    if (!response.ok) {
      throw new Error(`Failed to generate receipt: ${response.status}`);
    }
    
    return response.json();
  }

  // Download receipt PDF
  async downloadReceipt(receiptId) {
    const response = await fetch(
      `${this.baseURL}/receipts/${receiptId}/download`,
      {
        headers: this.getHeaders()
      }
    );
    
    if (!response.ok) {
      throw new Error(`Failed to download receipt: ${response.status}`);
    }
    
    // Get filename from headers
    const contentDisposition = response.headers.get('Content-Disposition');
    const filename = contentDisposition
      ? contentDisposition.split('filename=')[1].replace(/"/g, '')
      : `receipt_${receiptId}.pdf`;
    
    // Download file
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  }

  // View receipt in new tab
  viewReceipt(receiptId) {
    const token = localStorage.getItem('token');
    const url = `${this.baseURL}/receipts/${receiptId}/view`;
    
    // Open in new tab with auth
    window.open(url, '_blank');
  }

  // List receipts
  async listReceipts(page = 1, pageSize = 20) {
    const response = await fetch(
      `${this.baseURL}/receipts?page=${page}&page_size=${pageSize}`,
      {
        headers: this.getHeaders()
      }
    );
    
    if (!response.ok) {
      throw new Error(`Failed to list receipts: ${response.status}`);
    }
    
    return response.json();
  }
}

// Usage in Component
function PaymentDetails({ paymentSessionId }) {
  const [receipt, setReceipt] = useState(null);
  const [loading, setLoading] = useState(false);
  const receiptAPI = new ReceiptAPI();

  const handleGenerateReceipt = async () => {
    setLoading(true);
    try {
      const result = await receiptAPI.generateReceipt(paymentSessionId);
      setReceipt(result);
      alert('Receipt generated successfully!');
    } catch (error) {
      console.error('Error generating receipt:', error);
      alert('Failed to generate receipt');
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadReceipt = async () => {
    if (!receipt) return;
    
    try {
      await receiptAPI.downloadReceipt(receipt.id);
    } catch (error) {
      console.error('Error downloading receipt:', error);
      alert('Failed to download receipt');
    }
  };

  const handleViewReceipt = () => {
    if (!receipt) return;
    receiptAPI.viewReceipt(receipt.id);
  };

  return (
    <div>
      <h2>Payment Details</h2>
      <p>Session ID: {paymentSessionId}</p>
      
      {!receipt && (
        <button onClick={handleGenerateReceipt} disabled={loading}>
          {loading ? 'Generating...' : 'Generate Receipt'}
        </button>
      )}
      
      {receipt && (
        <div>
          <p>Receipt Number: {receipt.invoice_number}</p>
          <button onClick={handleDownloadReceipt}>
            Download PDF
          </button>
          <button onClick={handleViewReceipt}>
            View PDF
          </button>
        </div>
      )}
    </div>
  );
}
```

---

### Add Button to Payment Details Page

```javascript
// In your Payment Details component
<div className="receipt-section">
  <h3>Receipt</h3>
  {payment.status === 'PAID' && (
    <>
      <button 
        onClick={() => generateReceipt(payment.id)}
        className="btn-primary"
      >
        📄 Generate Receipt
      </button>
      
      {receipt && (
        <div className="receipt-actions">
          <button 
            onClick={() => downloadReceipt(receipt.id)}
            className="btn-secondary"
          >
            ⬇️ Download PDF
          </button>
          
          <button 
            onClick={() => viewReceipt(receipt.id)}
            className="btn-secondary"
          >
            👁️ View PDF
          </button>
        </div>
      )}
    </>
  )}
</div>
```

---

## Automatic Receipt Generation

### Option 1: Generate on Payment Confirmation

Add to your payment confirmation handler:

```python
# In your blockchain listener or payment confirmation handler
from app.services.receipt_service import generate_receipt_for_payment

def on_payment_confirmed(payment_session_id: str, db: Session):
    # ... existing payment confirmation logic ...
    
    # Auto-generate receipt
    try:
        receipt = generate_receipt_for_payment(db, payment_session_id)
        if receipt:
            logger.info(f"✅ Receipt auto-generated: {receipt.id}")
    except Exception as e:
        logger.error(f"Failed to auto-generate receipt: {e}")
```

### Option 2: Generate via Webhook

```python
# In your webhook handler
@router.post("/webhooks/payment-confirmed")
async def payment_confirmed_webhook(
    payload: dict,
    db: Session = Depends(get_db)
):
    payment_session_id = payload.get("payment_session_id")
    
    # Generate receipt
    from app.services.receipt_service import generate_receipt_for_payment
    receipt = generate_receipt_for_payment(db, payment_session_id)
    
    return {"status": "success", "receipt_id": receipt.id if receipt else None}
```

---

## PDF Receipt Format

The generated PDF includes:

1. **Header**
   - "PAYMENT RECEIPT" title
   - Merchant name and contact info

2. **Receipt Details**
   - Receipt number (RCPT-YYYYMMDD-XXXX)
   - Issue date
   - Payment status
   - Paid date
   - Transaction hash (if blockchain payment)

3. **Customer Information**
   - Customer name
   - Customer email

4. **Line Items**
   - Description
   - Quantity
   - Unit price
   - Total

5. **Totals**
   - Subtotal
   - Discount (if applicable)
   - Tax (if applicable)
   - Total amount
   - Amount paid

6. **Payment Details**
   - Blockchain network
   - Token used
   - Token amount
   - Transaction hash

7. **Footer**
   - Merchant message
   - Thank you note

---

## Testing

### 1. Test Receipt Generation

```bash
# Get your JWT token
TOKEN="your_jwt_token_here"

# Generate receipt for a paid payment
curl -X POST "http://localhost:8000/receipts/payment/pay_i0igisp16pbe3416/generate" \
  -H "Authorization: Bearer $TOKEN"
```

### 2. Test PDF Download

```bash
# Download receipt PDF
curl -X GET "http://localhost:8000/receipts/rcpt_abc123xyz/download" \
  -H "Authorization: Bearer $TOKEN" \
  --output receipt.pdf
```

### 3. Test in Browser

1. Login to your dashboard
2. Go to payment details page
3. Click "Generate Receipt" button
4. Click "Download PDF" to save
5. Click "View PDF" to open in browser

---

## Error Handling

### Common Errors

**1. Payment Not Paid**
```json
{
  "detail": "Payment not completed. Current status: pending"
}
```
**Solution:** Only generate receipts for paid payments

**2. Receipt Already Exists**
- The API will return the existing receipt instead of creating a duplicate

**3. Payment Not Found**
```json
{
  "detail": "Payment session not found"
}
```
**Solution:** Verify payment session ID is correct

**4. Unauthorized**
```json
{
  "detail": "Not authenticated"
}
```
**Solution:** Include valid JWT token in Authorization header

---

## Customization

### Custom Receipt Template

To customize the PDF template, edit `app/services/receipt_service.py`:

```python
# Change colors
title_style = ParagraphStyle(
    'CustomTitle',
    fontSize=24,
    textColor=colors.HexColor('#YOUR_COLOR'),  # Change this
)

# Add logo
if merchant.logo_url:
    logo = Image(merchant.logo_url, width=2*inch, height=1*inch)
    elements.append(logo)

# Custom footer
footer_text = f"Thank you for your business! - {merchant.name}"
elements.append(Paragraph(footer_text, styles['Normal']))
```

---

## Future Enhancements

### Email Delivery (Coming Soon)

```python
# Will be implemented
receipt = service.generate_receipt_for_payment(
    payment_session_id=payment_id,
    auto_send_email=True  # Send to customer email
)
```

### Bulk Receipt Generation

```python
# Generate receipts for multiple payments
POST /receipts/bulk-generate
{
  "payment_session_ids": ["pay_1", "pay_2", "pay_3"]
}
```

### Receipt Templates

```python
# Choose from multiple templates
POST /receipts/generate
{
  "payment_session_id": "pay_123",
  "template": "modern" | "classic" | "minimal"
}
```

---

## Support

For issues or questions:
- Check logs: `tail -f dari_payments.log`
- Verify payment is paid before generating receipt
- Ensure reportlab is installed: `pip install reportlab`
- Check JWT token is valid

---

## Quick Reference

| Action | Endpoint | Method |
|--------|----------|--------|
| Generate receipt | `/receipts/payment/{id}/generate` | POST |
| Download PDF | `/receipts/{id}/download` | GET |
| View PDF | `/receipts/{id}/view` | GET |
| Get receipt | `/receipts/{id}` | GET |
| List receipts | `/receipts` | GET |

---

**Last Updated:** 2026-03-29  
**Version:** 1.0  
**Status:** Production Ready ✅
