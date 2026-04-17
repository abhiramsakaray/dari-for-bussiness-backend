# Incident Response Plan

## 1. SEVERITY LEVELS

### P0 - CRITICAL (Response: Immediate)
- Data breach / unauthorized data access
- Payment processing system down
- Complete service outage
- Active security attack
- **SLA:** Response in 15 minutes, resolution in 4 hours

### P1 - HIGH (Response: 30 minutes)
- Partial service degradation
- Failed authentication spike
- DDoS attack
- Suspicious admin activity
- **SLA:** Response in 30 minutes, resolution in 8 hours

### P2 - MEDIUM (Response: 2 hours)
- Security scan failures
- Policy violations
- Minor service issues
- **SLA:** Response in 2 hours, resolution in 24 hours

### P3 - LOW (Response: Next business day)
- Informational alerts
- Minor configuration issues
- **SLA:** Response in 24 hours, resolution in 5 days

---

## 2. INCIDENT RESPONSE TEAM

**Incident Commander:** CTO / CISO  
**Technical Lead:** Lead Backend Engineer  
**Communications Lead:** Head of Customer Success  
**Legal Counsel:** General Counsel  
**On-Call Rotation:** 24/7 PagerDuty

---

## 3. RESPONSE PROCEDURES

### Phase 1: DETECTION (0-15 min)
1. Alert received (monitoring, user report, security scan)
2. On-call engineer acknowledges
3. Initial triage and severity classification
4. Incident ticket created
5. Incident commander notified (P0/P1)

### Phase 2: CONTAINMENT (15-60 min)
1. Isolate affected systems
2. Preserve forensic evidence
3. Block malicious IPs/accounts
4. Enable additional logging
5. Activate incident response team

### Phase 3: INVESTIGATION (1-4 hours)
1. Root cause analysis
2. Scope determination
3. Impact assessment
4. Evidence collection
5. Timeline reconstruction

### Phase 4: ERADICATION (2-8 hours)
1. Remove threat/vulnerability
2. Apply security patches
3. Reset compromised credentials
4. Update firewall rules
5. Validate remediation

### Phase 5: RECOVERY (4-24 hours)
1. Restore from clean backups
2. Rebuild compromised systems
3. Verify system integrity
4. Gradual service restoration
5. Enhanced monitoring

### Phase 6: POST-INCIDENT (24-120 hours)
1. Post-mortem meeting
2. Root cause documentation
3. Lessons learned
4. Preventive measures
5. Policy updates

---

## 4. COMMUNICATION TEMPLATES

### Internal Alert (P0/P1)
```
INCIDENT ALERT - P0
Time: [timestamp]
System: [affected system]
Impact: [user impact]
Status: [investigating/contained/resolved]
ETA: [estimated resolution]
War Room: [Zoom link]
```

### Customer Notification (Data Breach)
```
Subject: Important Security Notice

Dear [Customer],

We are writing to inform you of a security incident that may have affected your data.

What Happened: [brief description]
What Data: [types of data affected]
What We're Doing: [response actions]
What You Should Do: [customer actions]

We take security seriously and apologize for any concern this may cause.

Contact: security@dari.in
```

### Regulatory Notification (GDPR - 72 hours)
```
To: [Data Protection Authority]
Re: Personal Data Breach Notification

Dari for Business is notifying you of a personal data breach:

Date Discovered: [date]
Nature of Breach: [description]
Data Categories: [types]
Number of Individuals: [count]
Consequences: [impact]
Measures Taken: [response]
Contact: dpo@dari.in
```

---

## 5. ESCALATION PATHS

```
Level 1: On-Call Engineer (0-15 min)
    ↓ (if P0/P1)
Level 2: Incident Commander (15-30 min)
    ↓ (if data breach/major outage)
Level 3: Executive Team (30-60 min)
    ↓ (if regulatory/legal)
Level 4: Board of Directors (1-4 hours)
```

---

## 6. RUNBOOKS

### Data Breach Response
1. Immediately revoke all API keys
2. Force password reset for affected users
3. Enable additional audit logging
4. Preserve database snapshots
5. Engage forensics team
6. Notify legal counsel
7. Prepare customer notification
8. File regulatory reports (72 hours)

### DDoS Attack Response
1. Enable Cloudflare DDoS protection
2. Implement rate limiting (aggressive)
3. Block attacking IP ranges
4. Scale infrastructure
5. Monitor for data exfiltration
6. Document attack patterns

### Ransomware Response
1. Isolate infected systems immediately
2. DO NOT pay ransom
3. Restore from clean backups
4. Scan all systems for malware
5. Reset all credentials
6. Engage law enforcement
7. Review backup integrity

---

## 7. POST-MORTEM TEMPLATE

**Incident:** [ID and title]  
**Date:** [date]  
**Severity:** [P0/P1/P2/P3]  
**Duration:** [time to resolution]  
**Impact:** [users affected, revenue lost]

**Timeline:**
- [HH:MM] Event occurred
- [HH:MM] Alert triggered
- [HH:MM] Response initiated
- [HH:MM] Contained
- [HH:MM] Resolved

**Root Cause:** [technical explanation]

**What Went Well:**
- [positive aspects]

**What Went Wrong:**
- [issues encountered]

**Action Items:**
- [ ] [preventive measure 1] - Owner: [name] - Due: [date]
- [ ] [preventive measure 2] - Owner: [name] - Due: [date]

**Lessons Learned:**
- [key takeaways]

---

## 8. CONTACT INFORMATION

**Emergency Contacts:**
- On-Call: +1-XXX-XXX-XXXX (PagerDuty)
- CISO: ciso@dari.in
- Legal: legal@dari.in
- PR: pr@dari.in

**External Contacts:**
- AWS Support: [account number]
- Cloudflare: [account number]
- Forensics Firm: [contact]
- Cyber Insurance: [policy number]

---

**Last Updated:** April 16, 2026  
**Next Drill:** May 16, 2026
