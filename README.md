# Engagement Scope Creep Tracker

**Scope drift detection for fixed-fee professional services engagements.**

Built for a 20-person transactional law firm that was hemorrhaging margin on fixed-fee M&A and real estate deals. Partners would sign a deal at $35k fixed fee, and by closing, the firm had burned $48k in billable-equivalent hours. Nobody flagged it because the scope crept gradually, each individual client ask seemed small.

---

## The Problem

The firm shifted from hourly billing to fixed-fee engagements in 2023 to win more competitive deals. Revenue went up. Margin went off a cliff.

The pattern was the same on every deal:

1. **Partner scopes the engagement.** "We'll handle the purchase agreement, due diligence review, and closing." Clear deliverables, clear fee.

2. **Client starts asking for extras.** "Can you also review the lease assignment?" "Can someone from your team join the lender's call?" "We need a side letter for the earnout." Each ask is 2-4 hours. Nobody says no because the client relationship matters.

3. **Associates don't flag it.** They're junior. They don't know what was in the original scope. They just do the work and log time.

4. **Partner finds out at closing.** The bill would have been $48k at hourly rates. They charged $35k. The firm just worked 3 weeks for free across the team.

5. **Post-mortem goes nowhere.** "We need to be better about tracking scope." Nothing changes. Next deal, same problem.

The firm tried spreadsheets. Partners didn't update them. They tried telling associates to "flag anything that feels out of scope." Associates couldn't tell — they didn't see the engagement letter.

---

## What We Built

A lightweight tracking tool that sits between the engagement letter and the timekeeping system. It knows what was scoped, watches what's being worked on, and alerts when the two diverge.

**Not a billing system.** Not a practice management platform. Just the scope-to-actuals comparison that was missing.

### How It Works

1. **Engagement setup:** Partner defines the engagement — client, matter, deliverables, hours budget per deliverable, team members, timeline. Takes 10 minutes. Mirrors the engagement letter.

2. **Time entry tagging:** When associates log time (they were already doing this in their existing system), entries get tagged against engagement deliverables. Entries that don't match any deliverable are flagged as potential scope additions.

3. **Drift detection:** The system continuously compares actuals against the original scope. It detects three types of drift:
   - **Budget overrun:** A deliverable is consuming more hours than planned
   - **Unscoped work:** Time is being logged to this matter that doesn't map to any deliverable
   - **Timeline slip:** Work is happening past the planned completion date

4. **Alerts:** When drift crosses configurable thresholds (default: 75% of budget consumed with < 50% of deliverable complete, or any unscoped work logged), the responsible partner gets a notification.

5. **Change order generation:** When scope creep is confirmed, the tool generates a structured change order document — new deliverables, additional hours, cost impact, revised timeline. Gives the partner something concrete to bring to the client conversation instead of an awkward "we need to talk about fees."

---

## Modules

| File | Purpose |
|---|---|
| `engagement_tracker.py` | Core data model. Defines engagements, deliverables, budgets, team assignments. Tracks planned vs. actual hours. Calculates burn rate and projected overrun. |
| `drift_detector.py` | Compares time entries against scoped deliverables. Detects unscoped work, budget overruns, and timeline slippage. Generates alerts with severity and recommended actions. |
| `change_order_generator.py` | Produces structured change order documents when scope expansion is confirmed. Calculates cost impact, proposes revised budget, and formats for client presentation. |
| `dashboard.jsx` | React dashboard with engagement health cards, budget burn-down charts, drift alert feed, and change order history. |
| `FUTURE_ENHANCEMENTS.md` | Enhancements we scoped but didn't build due to timeline and budget constraints. |

---

## Client Context

**Firm profile:**
- 20 people: 4 partners, 6 senior associates, 6 junior associates, 4 staff
- Transactional practice: M&A (60%), commercial real estate (30%), general corporate (10%)
- ~40 active engagements at any time
- Average deal duration: 6-10 weeks
- Fee structure: ~70% fixed-fee, ~30% hourly (shifted from 90% hourly in 2022)

**Before this tool:**
- Average fixed-fee engagement ran 28% over budget (firm-absorbed cost)
- Partners discovered overruns at or after closing — too late to course correct
- Associates had no visibility into engagement budgets or scope boundaries
- "Scope creep" was discussed at every partner meeting but never quantified
- No standard process for handling out-of-scope client requests

**After deployment (first full quarter):**
- Average overrun dropped from 28% to 11%
- Partners flagged scope drift at 60% engagement completion (vs. 95%+ before)
- 34% of detected scope additions converted to change orders (additional revenue that was previously absorbed)
- Associates reported clearer understanding of what was and wasn't in scope
- Firm recovered an estimated $127k in Q1 that would have been written off

---

## How Scope Creep Actually Happens on a Deal

This is the pattern we saw across 40+ engagements during the observation period:

**Week 1-2: Clean.** Work matches scope. Associates are drafting the purchase agreement, reviewing the target company's org docs. Everything maps to deliverables in the engagement letter.

**Week 3-4: The asks start.** Client calls: "Can you review this lease? The landlord is being difficult about the assignment." Partner says "sure, we'll take a look." That's 4 hours of associate time on something not in the original scope. Nobody logs it as out-of-scope because there's no mechanism to flag it.

**Week 5-6: Compounding.** Three more asks have come in. "Can you draft a side letter for the earnout?" "We need someone on the lender's call Thursday." "Can you review the seller's disclosure schedules?" Each one is 2-6 hours. Total unscoped work is now 18-25 hours.

**Week 7-8: Partner notices.** "Why is this deal at 140 hours? We budgeted 95." But it's two weeks from closing. The client relationship is deep. Bringing up fees now feels adversarial. Partner absorbs the cost.

**Week 9-10: Closing and write-off.** Deal closes. Firm bills the fixed fee. Partner quietly writes off the overage. Tells the team "let's be tighter on scope next time."

The tracker breaks this cycle at Week 3, not Week 7.

---

## Technical Notes

- Python 3.11+, React with Recharts
- No external dependencies beyond standard library (by design — this needed to run without IT support)
- Data model uses dataclasses, not an ORM. The firm's "database" was going to be JSON files on a shared drive. Production would use SQLite at most.
- Dashboard uses synthetic data for portfolio demonstration
- In production, time entries would be imported via CSV export from the firm's existing timekeeping software (most small firms use Clio, PracticePanther, or similar)

---

## Modern Stack Infrastructure

The Scope Tracker now includes production-ready infrastructure for deployment and scaling:

### 1. **Cursor Configuration (`.cursorrules`)**
- Embedded AI context for feature consistency
- Scope creep detection patterns and business logic
- Fixed-fee engagement economics reference
- Drift detection and change order workflows

### 2. **Database & Schema** (`migrations/001_initial_schema.sql`)
- **PostgreSQL hosted on Railway** with:
  - Engagements, deliverables, time entries, drift events, change orders
  - Simple schema with role-based access control at the application layer
  - Single-tenant deployment: no multi-tenancy complexity, no Row-Level Security overhead
  - Immutable audit trail for all scope decisions
  - Indexes on engagement, deliverable, and time entry queries
  - Direct `psycopg2`/`asyncpg` connections for Python; `pg` client for Node

### 3. **Automation Workflows** (n8n)

**Time Entry Import** (`n8n/time_entry_import.json`):
- Webhook listener for Clio/PracticePanther time entry events
- Parses entries, matches to scoped deliverables
- Auto-tags unscoped work (confidence-based keyword matching)
- Triggers Trigger.dev drift detection job
- Returns processed entry status to caller

**Weekly Engagement Digest** (`n8n/weekly_engagement_digest.json`):
- Monday 8 AM cron job
- Fetches all active engagements, calculates metrics (burn rate, drift %, remaining budget)
- Groups by partner owner
- Ranks by risk (critical drift, then high unscoped %, then budget exposure)
- Sends summary emails to partners with engagement health dashboard

### 4. **Drift Detection & Change Orders** (Trigger.dev)

**Drift Detection Job** (`trigger-jobs/drift_detection.ts`):
- Analyzes time entries for engagement
- Categorizes scoped vs. unscoped hours
- Calculates drift metrics:
  - Budget consumed percent
  - Unscoped hours (and cost at blended rate)
  - Deliverable overruns (% over estimated hours)
  - Trend acceleration (drift rate increasing)
- Detects severity tiers:
  - **Warning**: >75% budget, <50% completion OR >2 hours unscoped
  - **Critical**: >90% budget, <25% completion OR >10% unscoped hours
- Saves immutable drift event to Supabase
- Triggers alerts if thresholds crossed

**Change Order Generation** (`trigger-jobs/change_order_generation.ts`):
- Auto-generates change order drafts from drift events
- Calculates scope additions (hours + cost at blended rate)
- Proposes revised timeline (+days based on hours)
- Creates change order with line items
- Saves to database with "Draft" status (awaiting partner review)

### 5. **Payment & Invoicing** (`stripe/invoicing.py`)

Production-grade Stripe integration:
- **Create Invoice**: Converts approved change order to Stripe invoice
  - Line items from change_order_items table
  - Auto-finalize for partner review
  - Metadata links invoice → change order → engagement

- **Payment Links**: Generate customer-facing payment links
  - 30-hour default expiration
  - Metadata tracking for webhook handlers

- **Webhook Handlers**:
  - `invoice.paid`: Update change order status, log payment
  - `invoice.payment_failed`: Flag for follow-up
  - `invoice.payment_action_required`: Handle 3D Secure, alternative methods
  - `charge.refunded`: Record refund in change order audit trail

- **Status Tracking**: Get current invoice status, payment history

### 6. **Email Templates** (React Email)

**Drift Alert** (`emails/drift_alert.tsx`):
- Alert: warning or critical severity badge
- Metrics: unscoped hours, cost impact, budget remaining
- Specific entries table (top 10 unscoped entries)
- Action buttons: Review engagement, Generate change order
- Recommendations for handling (change order, write-off, admin)

**Change Order Ready** (`emails/change_order_ready.tsx`):
- Success notification when change order generated
- Summary: additional hours, cost, revised budget
- Scope additions list
- Review checklist
- Status & next steps

### 7. **Deployment Configuration**

**Vercel** (`vercel.json`):
- Node.js routes for API endpoints
- Python runtime for Stripe webhook handlers
- Cron jobs:
  - Weekly digest (Monday 8 AM)
  - Engagement health check (daily 9 AM)
- Environment variables for all secrets (Railway PostgreSQL credentials, Stripe, etc.)

**Railway PostgreSQL** (Production Database):
- Single-tenant PostgreSQL 15 instance
- Direct connection via `DATABASE_URL` connection string
- No RLS overhead—role-based access handled at application layer
- Automated backups and daily snapshots
- Simple deployment: zero infrastructure complexity

**Replit Dev Environment** (`.replit`, `replit.nix`):
- PostgreSQL 15 auto-setup (mirrors Railway config)
- Node.js 20 + Python 3.11
- Automatic database initialization
- Local development server

**Environment Variables** (`.env.example`):
- Railway PostgreSQL connection string (`DATABASE_URL`)
- Stripe, Clio, PracticePanther, Resend API keys
- Trigger.dev, n8n credentials
- Configurable thresholds (drift warning: 75% budget, etc.)
- Feature flags for optional integrations
- Security settings (JWT, CSRF, rate limiting)

### Integration Points

```
Clio / PracticePanther
        ↓ (time entry webhook)
   n8n Listener
        ↓
   Parse & Match
        ↓
   Trigger.dev: Drift Detection
        ↓
   ├─ Save drift event → Railway PostgreSQL
   ├─ Trigger alerts (email)
   └─ Auto-generate change order (draft)
        ↓
   Trigger.dev: Change Order Generation
        ↓
   Create Stripe Invoice
        ↓
   Send payment link → Client
        ↓
   Stripe Webhook → Payment Status
        ↓
   Update change order + audit log
```

---

## Engagement & Budget

### Team & Timeline

| Role | Allocation | Duration |
|------|-----------|----------|
| Lead PM (Jacob) | 15 hrs/week | 10 weeks |
| Lead Developer (US) | 35 hrs/week | 10 weeks |
| Offshore Developer(s) | 1 × 30 hrs/week | 10 weeks |
| QA Engineer | 10 hrs/week | 10 weeks |

**Timeline:** 10 weeks total across 3 phases
- **Phase 1: Discovery & Design** (2 weeks) — Engagement workflow mapping, scope definition framework, billing integration requirements, change order template design
- **Phase 2: Core Build** (6 weeks) — Scope tracking engine, drift detection algorithms, change order generator, Stripe billing integration, partner dashboard
- **Phase 3: Integration & Launch** (2 weeks) — Practice management system integration, partner training, threshold calibration, pilot with 5 active matters

### Budget Summary

| Category | Cost | Notes |
|----------|------|-------|
| PM & Strategy | $27,750 | Discovery, specs, stakeholder management |
| Development (Lead + Offshore) | $72,150 | Core platform build |
| QA Engineer | $3,500 | Testing and quality assurance |
| **Total Engagement** | **$103,400** | Fixed-price, phases billed at milestones |
| **Ongoing Run Rate** | **$450/month** | Infrastructure + AI tokens + support |

---

## Business Context

### Market Size
~47,000 law firms in the US doing fixed-fee or alternative fee arrangements (AFA). Average overrun on fixed-fee matters is 15-25% (Thomson Reuters Legal Tracker). Firms managing $5M+ in annual fixed-fee work lose $750K-$1.25M/year to untracked scope creep.

### Unit Economics

| Metric | Value |
|--------|-------|
| **Before** | |
| Annual fixed-fee revenue | $3.6M |
| Avg overrun rate | 28% |
| Lost margin to scope creep | $1.01M/year |
| **After** | |
| Annual fixed-fee revenue | $3.6M (same) |
| Avg overrun rate | 11% |
| Lost margin to scope creep | $396K/year |
| Recovered via change orders | $508K/year |
| **Net Improvement** | **$1.12M/year** |
| Platform build cost | $103,400 |
| Monthly run rate | $450 |
| **Payback period** | **5 weeks** |
| **3-year ROI** | **31x** |

### Pricing Model
If productized for law firms: $800-2,500/month based on attorney count and matter volume, targeting $4-8M ARR at 500 firms.

---

## PM Perspective

The hardest decision I had to make was calibrating the scope drift alert sensitivity. Partners didn't want associates getting "scope creep alerts" on every minor task deviation — it would create alert fatigue and slow down work. But waiting until 80% budget consumption (the original threshold) was too late for meaningful course correction.

I settled on a two-tier system: soft alerts at 40% consumption with projected overrun > 15%, hard alerts at 60% with any projected overrun. Soft alerts go to the lead associate; hard alerts go to the supervising partner. This caught scope additions at 60% completion vs. the previous 95%, giving partners time to either adjust scope or generate a change order.

The biggest surprise was learning that 34% of detected scope additions converted into additional revenue via change orders. The firm assumed clients would push back on change orders, but the data told a different story — when you can show a client "here's what was originally agreed, here's what was actually delivered, and here's the delta" with clear documentation, most clients accept the additional charge. The firm had been leaving $500K+/year on the table by not tracking scope changes rigorously enough to justify the ask.

What I'd do differently: I would have integrated with the firm's practice management system from day one instead of building a standalone time entry interface. Associates had to dual-enter time (once in the existing system, once in scope tracker) for the first 6 weeks until we finished the integration. Dual entry killed early adoption — went from 90% first-week usage to 40% by week three. Once the integration shipped, adoption recovered to 95%.

---

## About This Project

Built as a product management engagement for a 20-person transactional law firm bleeding margin on fixed-fee engagements due to undetected scope creep. I led discovery with managing partners and associates to map engagement lifecycle and identify scope drift patterns. Designed the scope tracking framework connecting time entries, deliverables, and fee agreements. Made technology decisions on drift detection algorithms and change order automation. Established metrics tracking overrun reduction, change order conversion rates, and recovered revenue.

**Note:** Client-identifying details have been anonymized. Code represents the architecture and design decisions I drove; production deployments were managed by client engineering teams.
