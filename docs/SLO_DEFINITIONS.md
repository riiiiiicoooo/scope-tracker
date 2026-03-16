# Scope Tracker - SLO Definitions

## SLO 1: Billing Accuracy (Core Revenue Protection)
**Target:** 99.8% accuracy on scope overrun detection and billing adjustments
**Error Budget:** 0.2% (2 hours/month of inaccurate billing)
**Burn Rate Alert:** >20% of monthly error budget consumed in 7 days

### Rationale
Legal ops depend on accurate billing to prevent revenue leakage and maintain client relationships. The 11% reduction in overruns ($127K recovered Q1) demonstrates this is a high-impact metric. False negatives (missed overruns) directly damage revenue; false positives (incorrect charges) damage client trust. A 99.8% target allows ~2 hours/month of inaccuracy while capturing the vast majority of scope drift events that typically cascade through billing cycles.

### Measurement
- Count: Reconciliation audits where detected overruns match actual overages (sample rate: 5% of invoices weekly)
- Success: Billing records match scope variance report within 5% tolerance
- Burn rate threshold: If error budget consumed >20% in 7 days, trigger on-call review

---

## SLO 2: Drift Detection Precision (False Positive Rate)
**Target:** 95% precision on drift alerts (≤5% false positive rate)
**Error Budget:** 5% false positives per week
**Burn Rate Alert:** >50% of weekly false positive budget in 48 hours

### Rationale
Law firms operate on tight timelines. False positives (alerting to overruns that don't exist) create operational noise, erode user trust, and waste partner review cycles. The precision target of 95% is chosen to balance catching real drift (recall) while minimizing alert fatigue. At 5% FP rate, a firm reviewing 100 alerts/week encounters 5 false alarms—manageable but not disruptive. Higher precision improves adoption; lower precision risks users ignoring real warnings.

### Measurement
- Count: Drift alerts in production vs. validation dataset reconciliation (daily)
- Success: <5% of alerts reviewed by partners are deemed incorrect
- Burn rate threshold: If >50% of weekly FP budget consumed in 48 hours, trigger model retraining review

---

## SLO 3: Data Privacy Compliance (Law Firm Data Protection)
**Target:** 100% of PII (client names, case IDs, billing amounts) encrypted at rest and in transit
**Error Budget:** 0% for encryption violations; 99.5% uptime of encryption key service
**Burn rate Alert:** Any unencrypted export or transmission event triggers immediate remediation

### Rationale
Law firms handle highly sensitive client data. HIPAA, GDPR, and state bar regulations require end-to-end encryption. Unlike traditional SLOs with error budgets, data privacy is asymmetric: *any* unencrypted transmission of PII is a compliance breach, regardless of frequency. We set 100% encryption compliance (0% error budget for violations) but allow 0.5% downtime on the encryption key service itself because temporary unavailability triggers safe-fail (denial of service) rather than data exposure. Key rotations and audit logs are part of this SLO's measurement.

### Measurement
- Count: Encryption audit logs (daily) + key service health checks
- Success: 100% of PII fields encrypted with AES-256; zero audit log entries showing unencrypted transmission
- Burn rate threshold: Any failed encryption event triggers immediate incident escalation

---

## SLO 4: System Availability (Operational Continuity)
**Target:** 99.5% uptime (billing system accessible to law firms)
**Error Budget:** 3.6 hours/month of unavailability
**Burn rate Alert:** >50% of monthly error budget consumed in 7 days

### Rationale
Legal billing cycles are time-sensitive (monthly invoicing, quarter-end closes). Even brief unavailability can cause invoice delays, creating cash flow and compliance issues. A 99.5% target (3.6 hours/month) is standard for business-critical SaaS. This allows for planned maintenance windows and incident recovery while maintaining consistent revenue recognition. The higher precision SLOs (#1, #2) protect accuracy; this SLO protects availability.

### Measurement
- Count: Successful scope-tracker API responses / total requests (5-minute intervals)
- Success: >99.5% of billing system requests return in <2s
- Burn rate threshold: If >50% of monthly error budget consumed in 7 days, trigger incident review and capacity planning

---

## Error Budget Governance
- **Review Cadence:** Weekly review of SLO burn rates in engineering stand-up
- **Escalation:** If any SLO burns >40% of monthly budget by day 15, freeze non-critical feature work
- **Postmortem:** Every incident consuming >2% of monthly budget requires RCA and preventive control
- **Forecasting:** Monthly projection of burn rate trend; if on track to exceed budget, allocate remediation sprint
