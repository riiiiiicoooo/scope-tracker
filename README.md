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

## What This Demonstrates

- **Identifying a non-obvious product opportunity** in a domain where most tools focus on billing, not pre-billing scope management
- **Designing for adoption constraints** — small firm, no IT staff, partners who won't learn new software. The tool had to be simple enough that a partner could set up an engagement in 10 minutes and then mostly forget about it until an alert fires
- **Quantifying business impact** in terms the client cares about (recovered revenue, not "efficiency gains")
- **Scoping to budget** — the firm had a small consulting budget. We built the three things that would have the highest impact and documented what we'd build next. See FUTURE_ENHANCEMENTS.md
