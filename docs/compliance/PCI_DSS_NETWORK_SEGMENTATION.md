# PCI-DSS Network Segmentation

## Overview

This document describes the network segmentation strategy for Dari for Business to comply with PCI-DSS Requirement 1.2.1 - Network segmentation of cardholder data environment (CDE) from non-CDE.

## Environment Classification

### Cardholder Data Environment (CDE)
Components that store, process, or transmit cardholder data:
- Payment processing API endpoints (`/api/payments/*`, `/checkout/*`)
- Payment session database tables
- Blockchain listeners (receive payment confirmations)
- Webhook delivery system (transmits payment status)

### Non-CDE
Components that do NOT handle cardholder data:
- Merchant dashboard (`/api/merchant/*`)
- Analytics endpoints (`/api/analytics/*`)
- Team management (`/api/team/*`)
- Public marketing pages

## Implementation

### 1. Database Schema Separation

**CDE Schema:** `cde_schema`
- `payment_sessions`
- `payer_info`
- `refunds`
- `payment_events`

**Non-CDE Schema:** `public`
- `merchants`
- `merchant_users`
- `audit_logs`
- `consent_records`

### 2. Connection String Separation

```bash
# CDE Database (restricted access)
CDE_DATABASE_URL=postgresql://cde_user:***@cde-db.internal:5432/dari_cde

# Non-CDE Database (standard access)
DATABASE_URL=postgresql://app_user:***@app-db.internal:5432/dari_app
```

### 3. Network Firewall Rules

```
# CDE Network: 10.0.1.0/24
# Non-CDE Network: 10.0.2.0/24

# Allow CDE → Non-CDE (read-only)
iptables -A FORWARD -s 10.0.1.0/24 -d 10.0.2.0/24 -p tcp --dport 5432 -j ACCEPT

# Block Non-CDE → CDE (except API gateway)
iptables -A FORWARD -s 10.0.2.0/24 -d 10.0.1.0/24 -j DROP
iptables -A FORWARD -s 10.0.2.10 -d 10.0.1.0/24 -p tcp --dport 443 -j ACCEPT
```

### 4. Application-Level Enforcement

See `app/core/pci_dss.py` for runtime enforcement.

## Compliance Checklist

- [x] CDE components identified and documented
- [x] Network segmentation implemented
- [x] Firewall rules configured
- [x] Database schema separation
- [x] Connection string separation
- [x] Runtime environment tagging
- [ ] Quarterly penetration testing
- [ ] Annual PCI-DSS audit

## Monitoring

- Monitor cross-environment access attempts
- Alert on unauthorized CDE access
- Log all CDE database connections
- Track payment data flow

## References

- PCI-DSS v4.0 Requirement 1.2.1
- PCI-DSS v4.0 Requirement 2.2.3
