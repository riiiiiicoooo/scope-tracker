# Scope Tracker - Incident Runbooks

---

## Incident 1: Billing Accuracy Anomaly (False Negatives - Missed Overruns)

### Context
A law firm reports that Scope Tracker failed to detect a $45K overrun on a case that went 300+ hours over budget. Invoice was generated without adjustment, and client is disputing the charge.

### Detection
- **Alert:** Manual discovery via client complaint OR automated weekly reconciliation audit finds discrepancy between scope_events table and actual invoiced amounts
- **Symptoms:**
  - Case's actual hours don't match `scope_adjustments` record
  - Billing query returns outdated adjustment amount
  - Client reports seeing original invoice without overrun adjustment

### Diagnosis (15 minutes)

**Step 1: Validate the claim**
```sql
SELECT
  cases.name,
  cases.budgeted_hours,
  SUM(timesheets.hours) as actual_hours,
  scope_events.detected_overrun_hours,
  billing_adjustments.charged_overrun_hours
FROM cases
LEFT JOIN timesheets ON cases.id = timesheets.case_id
LEFT JOIN scope_events ON cases.id = scope_events.case_id
LEFT JOIN billing_adjustments ON scope_events.id = billing_adjustments.scope_event_id
WHERE cases.id = [CASE_ID]
GROUP BY cases.id;
```

**Step 2: Identify the failure mode**
- **Case A:** `scope_events` has entry but `billing_adjustments` is NULL → Detection worked, billing sync failed
- **Case B:** `scope_events` is missing → ML drift detector failed to fire
- **Case C:** `scope_events` exists but timestamp is AFTER invoice generation → Race condition in pipeline

**Step 3: Check drift detector logs**
```
kubectl logs -f deployment/scope-drift-detector --since=24h | grep case_[CASE_ID]
```
Look for:
- Model inference returned low confidence (<0.5) and alert was suppressed
- Feature extraction failed (e.g., timesheet data missing)
- Drift detector service was in degraded mode

### Remediation

**If failure mode is A (detection worked, billing sync failed):**
1. Trigger manual billing_adjustment insert:
   ```sql
   INSERT INTO billing_adjustments (scope_event_id, overrun_hours, rate, adjustment_amount)
   SELECT id, detected_hours - budgeted, rate, (detected_hours - budgeted) * rate
   FROM scope_events WHERE id = [SCOPE_EVENT_ID];
   ```
2. Regenerate invoice with adjustment
3. Root cause: Check billing_sync service logs for failed queue message (likely RabbitMQ poison pill)

**If failure mode is B (drift detector didn't fire):**
1. Manually run inference on the case:
   ```
   python -m scope_drift_detector.inference --case_id=[CASE_ID] --debug
   ```
2. If confidence <0.5, review feature engineering (is timesheet data complete?)
3. Retrain model on false negatives from past month
4. Update detection threshold from 0.7 → 0.65 confidence

**If failure mode is C (race condition):**
1. Check invoice generation timestamp vs. scope_event creation timestamp
2. Increase billing_sync delay: `BILLING_SYNC_DELAY_SECONDS=300` (5 min grace period)
3. Add database constraint: `ALTER TABLE billing_adjustments ADD CONSTRAINT invoice_adjustment_order CHECK (created_at < invoice_generated_at + INTERVAL 5 MINUTES)`

### Communication Template

**Internal (Slack #incidents)**
```
SCOPE TRACKER INCIDENT: Missed Overrun Detection
Severity: P2 (Revenue Impact: $45K)
Duration: Started [TIME], Detected [TIME]
Affected: [FIRM_NAME], [CASE_ID]

Summary: Scope drift detector failed to alert for 300-hour overrun. Likely root cause: [FAILURE_MODE from diagnosis].

ETA to Resolution: [15 min for manual fix + 2 hours for root cause remediation]
Assigned to: [ONCALL_ENGINEER]
```

**Customer (Email to Law Firm)**
```
Subject: Billing Adjustment on Case [CASE_ID]

We identified that Scope Tracker's drift detection system missed an overrun alert for your case on [DATE]. We've processed the appropriate billing adjustment for $[AMOUNT] in your account and are updating the invoice.

Our engineering team is investigating why the alert didn't trigger and will implement improvements to prevent this in the future.

Best regards,
[SUPPORT_NAME]
```

### Postmortem Questions
1. Was timesheet data being properly synced to drift detector at the time?
2. Did model confidence drift downward over the month? (Drift in drift detector)
3. Should we lower precision SLO (catch more overruns) at cost of false positives?

---

## Incident 2: False Positive Storm (Overzealous Drift Alerts)

### Context
On March 15, 2026, all 45 law firms receive drift alerts for 80+ cases flagged as "overrun detected" when actual overruns are <5%. Firms are overwhelmed with false alarms; partners delay review cycles.

### Detection
- **Alert:** Automated precision monitor detects spike in false positive rate (>15% of alerts in 24 hours)
- **Symptoms:**
  - Alert volume increases 5x without corresponding invoice disputes
  - Alert/week ratio jumps from 5% to 25%
  - Partner feedback: "Too many false alarms; we're ignoring them now"

### Diagnosis (10 minutes)

**Step 1: Check model performance**
```sql
SELECT
  DATE(created_at),
  COUNT(*) as total_alerts,
  SUM(CASE WHEN is_valid_overrun = false THEN 1 ELSE 0 END) as false_positives,
  ROUND(100.0 * SUM(CASE WHEN is_valid_overrun = false THEN 1 ELSE 0 END) / COUNT(*), 2) as fp_rate
FROM scope_events
WHERE created_at >= NOW() - INTERVAL 48 HOURS
GROUP BY DATE(created_at);
```

**Step 2: Identify the root cause**
- Check if model was recently retrained (version mismatch?)
- Look for data quality issue: Are timesheets incomplete/inconsistent?
- Check for feature drift: Did a new billing system push different data format?
- Investigate model confidence distribution

**Step 3: Analyze the spike**
```
kubectl logs deployment/scope-drift-detector --since=24h | grep "confidence\|feature"
```

Common causes:
- New data source integrated without validation (→ garbage in, garbage out)
- Model retrained on biased data (→ systematic overfitting)
- Threshold configuration accidentally lowered (→ catches low-confidence cases)

### Remediation

**Immediate (0-5 min): Suppress noisy alerts**
```sql
UPDATE scope_events
SET alert_status = 'suppressed'
WHERE created_at > NOW() - INTERVAL 24 HOURS
  AND confidence < 0.6
  AND is_valid_overrun = false;
```

**Short-term (5-30 min): Rollback to previous model**
```bash
kubectl set image deployment/scope-drift-detector \
  scope-drift-detector=scope-drift-detector:v1.2.3 \
  --record
```

**Root cause remediation (1-4 hours):**
1. **If data quality issue:** Validate new data source against schema; add automated quality gates
2. **If model retraining:** Run hold-out test set validation before deployment; implement A/B testing for model changes
3. **If threshold config:** Audit configuration history; implement config validation before promotion to prod

**Prevent recurrence:**
- Implement automated precision/recall tests in CI/CD
- Set alert on FP rate >5% to pause drift detector updates
- Require manual approval for model changes affecting alert thresholds

### Communication Template

**Internal (Slack #incidents)**
```
SCOPE TRACKER INCIDENT: False Positive Alert Spike
Severity: P3 (User Experience Impact)
Duration: [START_TIME] - [END_TIME]
Affected: All 45 firms, ~80 false alerts

Root Cause: Drift detector model confidence threshold drifted below 0.6. Suppressing low-confidence alerts and rolling back to v1.2.3.

ETA to Resolution: 10 minutes (rollback) + 2 hours (validation)
Assigned to: [ONCALL_ML_ENGINEER]
```

**Customer (Notification in app + Email)**
```
Alert Volume Notice

You may have received multiple overrun alerts in the past 24 hours. We've identified that some of these alerts had lower confidence than our threshold and are suppressing them.

We're investigating the cause and will ensure future alerts are high-confidence. You can safely deprioritize low-confidence alerts in your pending review queue.

Thank you for your patience.
```

### Postmortem Questions
1. Did A/B testing catch this before production? (If not, why not?)
2. How quickly can we roll back models in production?
3. Should we implement automated precision gates (e.g., freeze updates if FP > 10%)?

---

## Incident 3: Client Data Privacy Breach (Encryption Failure)

### Context
A backup recovery test discovers that scope_events table was briefly exported to an S3 bucket without encryption between 14:32-14:47 UTC on March 10. The export contained client names, case IDs, and billing amounts for 8 law firms. An unauthorized access attempt was detected in CloudTrail, and it's unclear if data was read.

### Detection
- **Alert:** CloudTrail detects s3:GetObject on backup bucket + encryption audit log missing for 15-minute window
- **Symptoms:**
  - Backup script logs show "encryption=false" flag in export
  - KMS key service was briefly unavailable (15 min)
  - S3 bucket policy audit reveals object was world-readable (ACL=PublicRead)

### Diagnosis (30 minutes)

**Step 1: Scope the exposure**
```sql
SELECT
  COUNT(DISTINCT firm_id) as firms_affected,
  COUNT(*) as records_exposed,
  MIN(created_at) as exposure_start,
  MAX(created_at) as exposure_end
FROM scope_events
WHERE exported_at BETWEEN '2026-03-10 14:32:00' AND '2026-03-10 14:47:00';
```
Result: 8 firms, 2,847 records, 15-minute window

**Step 2: Check S3 access logs**
```bash
aws s3api get-object-acl --bucket scope-tracker-backups --key daily-export-2026-03-10.csv
aws s3api get-object-tagging --bucket scope-tracker-backups --key daily-export-2026-03-10.csv
```
Check CloudTrail for unauthorized read attempts:
```bash
aws cloudtrail lookup-events --lookup-attributes AttributeKey=ResourceType,AttributeValue=AWS::S3::Object \
  --start-time 2026-03-10T14:32:00Z --end-time 2026-03-10T14:47:00Z
```

**Step 3: Determine if data was read**
- Check S3 access logs: Did any GET requests come from outside known IPs (deployment servers)?
- Check data exfiltration indicators: Were large downloads attempted?
- If unknown IP accessed the object → ASSUME DATA WAS READ (breach notification required)

### Remediation

**Immediate (5 min): Contain the breach**
1. Delete the unencrypted export:
   ```bash
   aws s3 rm s3://scope-tracker-backups/daily-export-2026-03-10.csv
   ```
2. Rotate all encryption keys:
   ```bash
   aws kms enable-key-rotation --key-id [KMS_KEY_ID]
   ```
3. Update S3 bucket policy to enforce encryption:
   ```json
   {
     "Effect": "Deny",
     "Principal": "*",
     "Action": "s3:PutObject",
     "Resource": "arn:aws:s3:::scope-tracker-backups/*",
     "Condition": {
       "StringNotEquals": {
         "s3:x-amz-server-side-encryption": "AES256"
       }
     }
   }
   ```

**Short-term (30 min): Investigate root cause**
- Why was KMS key service unavailable? Check KMS logs for region failure
- Why was encryption=false flag set in backup script? Audit code changes in past 7 days
- Why was S3 bucket ACL=PublicRead? Check IAM policy changes

**Root cause remediation (1-2 hours):**
1. **Encryption key service failure:** Implement cross-region KMS replication; add backup KMS key
2. **Code flag:** Remove encryption=false option from backup script; implement code review for security-sensitive changes
3. **S3 ACL misconfiguration:** Enforce bucket encryption + private ACL via Terraform; implement pre-deployment security validation

**Notification & Legal (Immediate):**
1. Escalate to Legal & Compliance team within 15 minutes
2. Determine if notification is required under state data breach laws (California, Illinois, etc.)
3. Prepare breach notification letters for affected law firms if required
4. Document timeline for regulatory filings

### Communication Template

**Internal (Slack #security-incidents)**
```
CRITICAL: Data Privacy Incident - Unencrypted Export
Severity: P1 (Regulatory & Legal Risk)
Duration: 2026-03-10 14:32-14:47 UTC (15 minutes)
Affected: 8 law firms, 2,847 records (client names, case IDs, billing data)

Exposure: S3 bucket had world-readable ACL; unauthorized access attempt detected in CloudTrail.

Actions:
- Unencrypted file deleted from S3
- Encryption keys rotated
- S3 bucket policy locked down
- Legal/Compliance notified for breach determination

ETA to Assessment: 30 minutes (did breach occur?)
Assigned to: [SECURITY_LEAD], [LEGAL]
```

**Customer Notification (if breach confirmed - within 24 hours):**
```
Subject: Security Incident Notice - Scope Tracker

We're writing to inform you of a security incident that may have affected your data in Scope Tracker.

Incident: On March 10, 2026, a temporary misconfiguration in our backup system created an unencrypted export of scope tracking data for your cases. The export was accessible for 15 minutes before we identified and remediated the issue.

Potentially Affected Data: Case IDs, client names, and billing amounts for [N] of your cases.

What We Did:
- Immediately deleted the unencrypted file
- Rotated all encryption keys
- Enhanced S3 security policies to prevent recurrence
- Engaged our security team for investigation

What You Should Do:
- Monitor your accounts for suspicious activity
- Update law firm security policies if needed
- Contact us if you have questions: [SECURITY_CONTACT]

We sincerely apologize for this incident and are committed to preventing it from happening again.

Best regards,
[COMPANY_LEGAL]
```

### Postmortem Questions
1. Why didn't encryption enforcement catch the unencrypted export before production?
2. How can we make KMS more resilient (cross-region, fallback keys)?
3. Should we implement immutable audit logs for all data exports?
4. What's our breach notification timeline (legal requirement)?

---

## General Escalation Path
1. **P3 (Operational Impact):** Assign to on-call engineer; notify team in Slack
2. **P2 (Revenue/UX Impact):** Escalate to engineering manager + product manager within 15 min
3. **P1 (Data/Compliance Risk):** Escalate to VP Engineering + Legal + Compliance immediately
4. **All incidents >2% SLO impact:** Require postmortem within 48 hours

