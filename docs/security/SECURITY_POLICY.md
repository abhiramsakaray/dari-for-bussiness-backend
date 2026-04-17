# Security Policy - Dari for Business

**Version:** 1.0  
**Effective Date:** April 16, 2026  
**Last Updated:** April 16, 2026  
**Owner:** Chief Information Security Officer (CISO)

---

## 1. PURPOSE

This Security Policy establishes the framework for protecting Dari for Business systems, data, and operations in compliance with SOC 2 Trust Service Criteria, GDPR, and PCI-DSS requirements.

---

## 2. SCOPE

This policy applies to:
- All employees, contractors, and third-party vendors
- All systems, applications, and infrastructure
- All data (customer, payment, merchant, operational)
- All environments (production, staging, development)

---

## 3. ACCESS CONTROL

### 3.1 User Access Management

**Principle of Least Privilege:**
- Users granted minimum access required for job function
- Access reviewed quarterly
- Terminated employees' access revoked within 4 hours

**Authentication Requirements:**
- Multi-factor authentication (MFA) mandatory for all production access
- Password minimum: 12 characters, complexity requirements enforced
- Password rotation: every 90 days
- Failed login lockout: 5 attempts, 15-minute lockout

**Role-Based Access Control (RBAC):**
- Roles: Admin, Merchant, Team Member, Viewer
- Permissions documented in `docs/RBAC_MATRIX.md`
- Role changes require manager approval

### 3.2 Privileged Access

**Administrative Access:**
- Separate admin accounts (no shared credentials)
- All admin actions logged in AuditLog
- Admin access reviewed monthly
- Break-glass procedures documented

**Database Access:**
- Production database access restricted to DBAs
- All queries logged
- Read-only replicas for analytics
- Direct production access requires incident ticket

### 3.3 Third-Party Access

- Vendor access requires signed NDA
- Time-limited access (max 30 days)
- Monitored and logged
- Revoked immediately upon contract termination

---

## 4. ENCRYPTION

### 4.1 Data at Rest

**Database Encryption:**
- PostgreSQL Transparent Data Encryption (TDE) enabled
- AES-256 encryption
- Key rotation every 90 days
- Keys stored in AWS KMS / HashiCorp Vault

**PII Encryption:**
- Email, name, phone encrypted with Fernet (AES-128)
- Encryption keys separate from data
- Key rotation procedure documented

**Backup Encryption:**
- All backups encrypted before storage
- Separate encryption keys from production
- Stored in geographically distributed locations

### 4.2 Data in Transit

**TLS Requirements:**
- TLS 1.3 minimum (TLS 1.2 deprecated)
- Strong cipher suites only
- Certificate pinning for mobile apps
- HSTS enabled (max-age=31536000)

**API Security:**
- All API endpoints HTTPS only
- Certificate auto-renewal (Let's Encrypt)
- Certificate expiry monitoring (30-day alert)

### 4.3 Key Management

**Key Storage:**
- Production keys in AWS Secrets Manager / HashiCorp Vault
- Development keys in environment variables (non-production data only)
- Keys never committed to version control

**Key Rotation:**
- Automatic rotation every 90 days
- Manual rotation on security incident
- Rotation procedure tested quarterly

---

## 5. INCIDENT RESPONSE

### 5.1 Incident Classification

**Severity Levels:**
- **P0 (Critical):** Data breach, system compromise, payment processing down
- **P1 (High):** Unauthorized access attempt, DDoS attack, service degradation
- **P2 (Medium):** Failed security scan, suspicious activity, policy violation
- **P3 (Low):** Minor configuration issue, informational alert

### 5.2 Response Procedures

**Detection:**
- 24/7 monitoring and alerting
- Automated anomaly detection
- Security Information and Event Management (SIEM)

**Response:**
- Incident response team activated within 15 minutes (P0/P1)
- Containment procedures initiated immediately
- Communication plan activated
- Forensic evidence preserved

**Recovery:**
- Systems restored from verified backups
- Security patches applied
- Vulnerability remediated
- Service restored with validation

**Post-Incident:**
- Root cause analysis within 48 hours
- Post-mortem report within 5 business days
- Lessons learned documented
- Preventive measures implemented

### 5.3 Communication

**Internal:**
- Incident commander notified immediately
- Executive team notified within 1 hour (P0/P1)
- All-hands communication for major incidents

**External:**
- Customer notification within 72 hours (GDPR requirement)
- Regulatory notification as required (PCI-DSS, data protection authorities)
- Public disclosure if legally required

---

## 6. CHANGE MANAGEMENT

### 6.1 Change Control Process

**Standard Changes:**
- Code review required (2 approvers)
- Automated testing (unit, integration, security)
- Staging deployment and validation
- Production deployment during maintenance window
- Rollback plan documented

**Emergency Changes:**
- Security patches: expedited approval
- Critical bug fixes: on-call approval
- Post-implementation review within 24 hours

**Change Documentation:**
- Change request ticket (Jira/GitHub)
- Risk assessment
- Rollback procedure
- Deployment checklist

### 6.2 Deployment Process

**Pre-Deployment:**
- Security scan (SAST, DAST)
- Dependency vulnerability check
- Database migration review
- Backup verification

**Deployment:**
- Blue-green deployment (zero downtime)
- Canary deployment for high-risk changes
- Automated health checks
- Monitoring dashboard active

**Post-Deployment:**
- Smoke tests executed
- Error rate monitoring (15 minutes)
- Performance metrics validated
- Rollback if error rate > 1%

---

## 7. AVAILABILITY

### 7.1 Service Level Objectives (SLOs)

**Uptime:**
- Production: 99.9% uptime (43 minutes downtime/month)
- API response time: P95 < 200ms, P99 < 500ms
- Payment processing: 99.95% success rate

**Maintenance Windows:**
- Scheduled: Sundays 2-4 AM UTC
- Advance notice: 7 days
- Emergency maintenance: 4 hours notice

### 7.2 Disaster Recovery

**Recovery Objectives:**
- Recovery Time Objective (RTO): 4 hours
- Recovery Point Objective (RPO): 15 minutes
- Data loss tolerance: < 15 minutes

**Backup Strategy:**
- Database: Continuous replication + hourly snapshots
- Files: Daily incremental, weekly full
- Retention: 30 days online, 1 year archive
- Geographic redundancy: 3 regions

**DR Testing:**
- Quarterly DR drills
- Annual full failover test
- Runbooks updated after each test

### 7.3 Business Continuity

**Critical Functions:**
- Payment processing
- Merchant dashboard
- Webhook delivery
- Customer support

**Continuity Plans:**
- Alternative infrastructure (multi-cloud)
- Vendor redundancy
- Communication channels
- Staff availability (on-call rotation)

---

## 8. MONITORING & LOGGING

### 8.1 Security Monitoring

**Real-Time Monitoring:**
- Failed authentication attempts
- Privilege escalation attempts
- Unusual data access patterns
- API rate limit violations
- Suspicious IP addresses

**Alerting:**
- P0 alerts: PagerDuty (immediate)
- P1 alerts: Slack + Email (5 minutes)
- P2 alerts: Email (1 hour)
- P3 alerts: Daily digest

### 8.2 Audit Logging

**Logged Events:**
- All authentication events
- All data access (PII, payment data)
- All administrative actions
- All configuration changes
- All security events

**Log Retention:**
- Security logs: 1 year
- Audit logs: 7 years (compliance)
- Application logs: 90 days
- Access logs: 180 days

**Log Protection:**
- Immutable audit logs (append-only)
- Centralized log aggregation
- Encrypted log storage
- Access restricted to security team

---

## 9. VULNERABILITY MANAGEMENT

### 9.1 Vulnerability Scanning

**Automated Scanning:**
- Dependency scanning: Daily (CI/CD)
- Container scanning: On build
- Infrastructure scanning: Weekly
- Web application scanning: Monthly

**Manual Testing:**
- Penetration testing: Quarterly
- Security code review: Per release
- Red team exercises: Annually

### 9.2 Patch Management

**Critical Patches:**
- Applied within 24 hours
- Emergency change process
- Tested in staging first

**High Severity:**
- Applied within 7 days
- Standard change process
- Regression testing required

**Medium/Low:**
- Applied within 30 days
- Bundled with regular releases

---

## 10. COMPLIANCE

### 10.1 Regulatory Requirements

**GDPR:**
- Data protection by design
- Privacy impact assessments
- Data processing agreements
- Breach notification procedures

**PCI-DSS:**
- Network segmentation
- Cardholder data protection
- Quarterly vulnerability scans
- Annual compliance audit

**SOC 2:**
- Trust Service Criteria compliance
- Annual SOC 2 Type II audit
- Continuous monitoring
- Control effectiveness testing

### 10.2 Policy Review

**Review Schedule:**
- Annual comprehensive review
- Quarterly updates as needed
- Post-incident updates
- Regulatory change updates

**Approval:**
- CISO approval required
- Executive team review
- Board notification (major changes)

---

## 11. TRAINING & AWARENESS

### 11.1 Security Training

**Mandatory Training:**
- New hire security orientation (within 7 days)
- Annual security awareness training
- Role-specific training (developers, admins)
- Phishing simulation (quarterly)

**Training Topics:**
- Password security
- Social engineering
- Data handling
- Incident reporting
- Secure coding practices

### 11.2 Awareness Programs

**Communications:**
- Monthly security newsletter
- Security tips in Slack
- Incident lessons learned
- Security champions program

---

## 12. ENFORCEMENT

### 12.1 Policy Violations

**Consequences:**
- First violation: Written warning
- Second violation: Suspension
- Third violation: Termination
- Criminal activity: Law enforcement referral

### 12.2 Reporting

**Reporting Channels:**
- Security team: security@dari.in
- Anonymous hotline: 1-800-XXX-XXXX
- Whistleblower protection guaranteed

---

## 13. DOCUMENT CONTROL

**Version History:**
| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-04-16 | CISO | Initial policy |

**Next Review Date:** 2027-04-16

**Distribution:**
- All employees (mandatory reading)
- All contractors
- Executive team
- Board of Directors

---

**Approval:**

________________________  
Chief Information Security Officer  
Date: April 16, 2026

________________________  
Chief Executive Officer  
Date: April 16, 2026
