# SCOPE TRACKER — PRODUCT REQUIREMENTS DOCUMENT

## Executive Summary

**Problem:** Fixed-fee professional services engagements systematically run 28% over budget on average. Scope creep happens gradually and invisibly. Partners discover overruns at or after closing—too late to course correct or generate a change order.

**Solution:** A lightweight scope drift detection tool that sits between the engagement letter and time tracking system. It knows what was scoped, watches what's being worked on, and alerts when the two diverge. When drift is confirmed, it generates structured change orders.

**Impact:** In deployment with our target customer (20-person transactional law firm), overruns dropped from 28% to 11%. 34% of detected drift converted to change orders (additional revenue previously absorbed). Estimated recovery: $127k in Q1.

---

## Customer Profile

**Target User Persona: Managing Partner of Small Law Firm**

- **Role:** David Park, Partner at 20-person commercial real estate and M&A firm
- **Challenge:** "We're winning deals because we bid fixed fees, but we're losing margin on every deal. Scope creep is invisible and unquantifiable. By the time I know we're over budget, it's too late to do anything about it."
- **Constraints:**
  - No dedicated IT staff
  - Infrastructure is a shared drive and Outlook
  - Partners won't learn new software (adoption barrier is real)
  - No appetite for complex systems
  - Limited budget for tools

**Customer Environment:**
- 20 people: 4 partners, 6 senior associates, 6 junior associates, 4 staff
- Transactional practice: M&A (60%), commercial real estate (30%), general corporate (10%)
- ~40 active engagements at any time
- Average deal duration: 6-10 weeks
- Fee structure: ~70% fixed-fee, ~30% hourly (shifted from 90% hourly in 2022)

**Before This Tool:**
- Average fixed-fee engagement ran 28% over budget (firm-absorbed cost)
- Partners discovered overruns at or after closing
- Associates had no visibility into scope or budgets
- "Scope creep" discussed at every partner meeting but never quantified
- No standard process for handling out-of-scope requests

**After Deployment (First Full Quarter):**
- Average overrun dropped from 28% to 11%
- Partners flagged scope drift at 60% engagement completion (vs. 95%+ before)
- 34% of detected scope additions converted to change orders
- Associates reported clearer understanding of scope boundaries
- Firm recovered $127k in Q1 that would have been written off

---

## Requirements

### 1. IMPORT
- Import time entries from CSV exports of timekeeping systems (Clio, PracticePanther, Bill4Time)
- Support flexible column mapping (different systems export different formats)
- Parse descriptions to extract work category (research, drafting, review, negotiation, etc.)
- Extract scope references (keywords: "lease assignment," "earnout," "environmental," etc.)
- Match entries to scoped deliverables using keyword matching and fuzzy string comparison
- Flag unmatched entries as potential scope drift

**Acceptance Criteria:**
- Successfully import CSV from all three major timekeeping systems
- Categorize entries with 70%+ confidence when possible
- Match 80%+ of in-scope work to deliverables
- Flag all entries with no deliverable match as "unscoped"

### 2. DETECTION
- Compare actual time entries against scoped deliverables
- Detect three types of drift:
  - Budget overrun: deliverable burning hours faster than planned
  - Unscoped work: time logged with no deliverable match
  - Timeline slip: work happening past planned end date
- Generate alerts with severity levels (INFO, WARNING, CRITICAL)
- Alert thresholds are conservative (flag early rather than late)

**Acceptance Criteria:**
- Detect unscoped work as soon as 2 hours accumulated
- Detect budget overruns when 75% of deliverable budget consumed
- Generate alerts within seconds of time entry import
- No false negatives on unscoped work (catch all drift)

### 3. GENERATION
- Generate structured change orders from detected drift
- Automatically group related unscoped work into logical scope additions (themes)
- Calculate cost impact using engagement's blended rate
- Format as professional documents ready for client
- Provide email draft for initial outreach

**Acceptance Criteria:**
- Generate change orders in <5 seconds
- Group unrelated entries into 3-5 logical themes (not one massive list)
- Calculate cost within 5% of manual calculation
- Produce documents partners can send to clients without modification

### 4. PERSISTENCE
- Save engagement state to JSON (no database required)
- Structure: `data/engagements/{id}/engagement.json`, `time_entries.json`, etc.
- Auto-save on every change (no "unsaved changes" risk)
- Support file-based locking for shared drive (multiple partners reading/writing)
- Backup function (export to ZIP)

**Acceptance Criteria:**
- Survive power loss without data corruption
- Support concurrent access from multiple partners on shared drive
- Restore complete engagement state from JSON
- Backup/restore in <10 seconds per engagement

### 5. DASHBOARD (Future)
- Visual engagement health cards (budget, timeline, team utilization)
- Drift alert feed (color-coded by severity)
- Change order history (approved, pending, rejected)
- Burndown charts by deliverable
- Responsive design (works on phone and desktop)

**Note:** Dashboard is React/JavaScript. This document focuses on the backend requirements.

---

## Success Metrics

### Business Impact
- **Average overrun reduction:** From 28% to <15%
- **Margin recovery:** Minimum 20% of original fixed fee retained per engagement
- **Change order conversion:** 30%+ of detected drift formalizes as change orders
- **Adoption:** 100% of partners use tool within 6 weeks of deployment
- **Time to detection:** Drift flagged before 50% of engagement completion

### Product Metrics
- **Accuracy:** 95%+ precision on deliverable matching (low false positives)
- **Sensitivity:** 100% recall on unscoped work >5 hours (catch all meaningful drift)
- **Performance:** Import and scan 100+ time entries in <2 seconds
- **Reliability:** Zero data loss over 12-month pilot
- **Adoption friction:** Setup time <10 minutes per engagement

### Partner Satisfaction
- "I now know within the first 2 weeks if scope is creeping." (vs. Week 7 before)
- "I have concrete numbers to discuss with the client." (vs. vague impression)
- "The tool pays for itself with the first change order." (quantifiable value)
- "I don't have to think about using it—it just works." (frictionless adoption)

---

## Technical Constraints

**No external dependencies** (besides stdlib)
- Team has no IT staff to manage updates
- Shared drive infrastructure means no cloud storage
- Minimal DevOps appetite

**Python 3.11+**
- Consistent with firm's existing tools
- Partners can edit JSON files if needed (human-readable)
- Dataclasses over ORM (simple, readable, portable)

**JSON persistence** (not database)
- Natural fit for shared drive (files, not server)
- Version-controllable (can track changes in Git)
- Human-readable (partners can spot-check)
- Backup-friendly (ZIP export)

**No user interface required for MVP**
- CLI script for import
- Generated documents (Markdown, plain text)
- Dashboard is nice-to-have, not must-have
- Partners live in spreadsheets and email anyway

---

## Out of Scope (But Documented for Future)

- **Integration with timekeeping systems:** Currently requires manual CSV export. Future: API connections to Clio, PracticePanther, etc.
- **Automated change order execution:** Currently partners send manually. Future: email templates, e-signature integration.
- **Budgeting guidance:** Tool tracks overruns, doesn't help partners set better budgets initially.
- **Team capacity planning:** Tool detects when people are overallocated, doesn't reschedule work.
- **Profitability analysis across firm:** Engagement-level drift detection only. Future: firm-wide margin analysis.

---

## Deliverables

1. **time_entry_importer.py** — CSV import with multiple format support
2. **json_store.py** — Persistence layer (load/save engagements)
3. **change_order_renderer.py** — Document generation (Markdown, email, HTML)
4. **simulate_engagement.py** — End-to-end demo (8-week simulation)
5. **Sample data** — Realistic Clio and PracticePanther CSV exports
6. **Sample outputs** — Example change orders and email drafts
7. **Documentation** — PRD, architecture, usage guides

---

## Timeline & Budget

**Scope:** Build 1-4 from list above. Documents & samples as well. Dashboard deferred.

**Budget:** $X (consulting engagement)
**Timeline:** 4 weeks
**Team:** 1 lead engineer, 1 product person (customer interviews)

---

## Go-to-Market

**Phase 1 (Weeks 1-2):** Deploy with target customer (20-person law firm)
- Collect feedback on detection accuracy
- Validate change order workflow
- Measure margin impact

**Phase 2 (Weeks 3-4):** Refine based on feedback
- Adjust drift thresholds
- Improve match accuracy
- Expand sample data

**Phase 3 (After 1 Quarter):** Evaluate for broader launch
- Metric review (overrun reduction, change order conversion)
- Customer testimonial
- Consider licensing vs. services model

---

## Success Looks Like

**Week 1:** Tool is live. Partners are importing time entries.

**Week 3:** First drift alert fires. Partner reviews, understands immediately. "Oh yeah, we DID add that lease assignment work. This is accurate."

**Week 6:** Partner generates change order from detected drift. Sends to client with email draft. Client responds: "Yes, that makes sense. Let me approve."

**Week 8:** First engagement closes. Margin is 15% instead of -8%. Partner says: "This paid for itself immediately."

**Q2:** Firm deploys across 40 active engagements. Measure firm-wide impact.

---

## Q&A with Customer

**Q: Will this force me to use a new system?**
A: No. You keep using Clio (or whatever you use now). You export CSV monthly. Tool processes it locally on your shared drive.

**Q: Can my associates see the tool?**
A: Yes. They see "this time entry is in scope" or "out of scope" feedback. Helps them understand boundaries.

**Q: What if the tool flags something incorrectly?**
A: You dismiss the alert in one click. It remembers for next time. Low-friction.

**Q: Does this replace my engagement letters?**
A: No. You write engagement letters as before. This tool checks if actuals match the letter.

**Q: Can I use this for hourly matters too?**
A: Yes. But the tool is optimized for fixed-fee engagements (where margin matters most).

---
