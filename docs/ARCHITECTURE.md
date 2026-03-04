# SCOPE TRACKER — ARCHITECTURE DOCUMENT

## System Overview

Scope Tracker is a scope drift detection system for fixed-fee professional services engagements. It sits between the engagement letter (planned scope) and time tracking system (actual work) and alerts when the two diverge.

**Design Philosophy:**
- No database, no server, no cloud infrastructure
- JSON files on a shared drive (firm's existing infrastructure)
- Designed for small teams with no IT staff
- Zero external dependencies (pure Python stdlib)
- Simple, auditable, trustworthy

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        ENGAGEMENT CREATED                        │
│  Partner: "We'll draft PSA, review DD, prepare closing docs"     │
│  Budget: $35k, 95 hours, 8 weeks                                 │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ↓
         ┌───────────────────────┐
         │  JSON STORE: SAVE     │
         │ engagement.json       │
         └───────────┬───────────┘
                     │
                     ↓
    ┌────────────────────────────────────┐
    │    TIME ENTRIES LOGGED (Weekly)    │
    │  Clio export.csv → import          │
    │  60+ entries over 8 weeks          │
    │  Each with: date, hours, desc      │
    └──────────┬───────────────────────┘
               │
               ↓
    ┌─────────────────────────────────┐
    │  TIME ENTRY IMPORTER            │
    │  1. Parse CSV (Clio format)     │
    │  2. Extract description text    │
    │  3. Categorize (drafting, etc)  │
    │  4. Try match to deliverable    │
    │  5. Flag if unmatched           │
    └──────────┬────────────────────┘
               │
               ├─→ Matched entries (in-scope)
               │   └─→ Update deliverable.actual_hours
               │
               └─→ Unmatched entries (out-of-scope)
                   └─→ Flag as "potential drift"
                        → Set TimeEntry.is_scoped = False
                        → Set TimeEntry.flag_reason
               │
               ↓
    ┌──────────────────────────────────┐
    │  DRIFT DETECTOR                  │
    │  Continuous monitoring           │
    │  Runs when time entries added    │
    │  Checks:                         │
    │  • Deliverable budget overruns   │
    │  • Unscoped work accumulation    │
    │  • Timeline slips                │
    │  • Team overallocation           │
    │  • Burn rate anomalies           │
    └──────────┬───────────────────────┘
               │
               ├─→ INFO alerts (FYI)
               ├─→ WARNING alerts (2+ hours unscoped, etc)
               └─→ CRITICAL alerts (8+ hours unscoped, etc)
                        Triggers: "Partner, please review"
               │
               ↓
    ┌────────────────────────────────────┐
    │  PARTNER REVIEWS ALERT             │
    │  "Yes, we did add that work"       │
    │  Decision: Absorb or formalize?    │
    └──────────┬─────────────────────────┘
               │
               ├─→ Dismiss (we'll absorb it)
               │
               └─→ Generate Change Order
                        │
                        ↓
        ┌───────────────────────────────┐
        │  CHANGE ORDER GENERATOR       │
        │  1. Group unscoped work       │
        │     (lease assignment,        │
        │      earnout, etc)            │
        │  2. Estimate remaining hours  │
        │  3. Calculate cost            │
        │  4. Create scope additions    │
        └────────┬──────────────────────┘
                 │
                 ↓
        ┌───────────────────────────────┐
        │  CHANGE ORDER RENDERER        │
        │  1. Format as Markdown        │
        │  2. Create email draft        │
        │  3. Create HTML version       │
        └────────┬──────────────────────┘
                 │
                 ↓
        ┌──────────────────────────────┐
        │  PARTNER SENDS TO CLIENT     │
        │  "Here's what we added and   │
        │   what it costs"             │
        └──────────┬───────────────────┘
                   │
                   ├─→ Client approves
                   │   └─→ Change order status = "approved"
                   │   └─→ Update engagement.total_budgeted_hours
                   │   └─→ Continue work with updated scope
                   │
                   └─→ Client rejects
                       └─→ Partner and client negotiate
                       └─→ Update change order
                       └─→ Resubmit
                 │
                 ↓
        ┌────────────────────────────┐
        │  JSON STORE: APPEND        │
        │  change_orders/CO-001.json │
        │  drift_history.json        │
        └────────────────────────────┘
```

---

## Module Breakdown

### 1. **engagement_tracker.py** (Core Data Model)

Defines the engagement object and all relationships.

**Key Classes:**
- `Engagement` — Top-level object. Contains client, deliverables, team, time entries, change orders.
- `Deliverable` — Scoped work. Name, budget, planned end, status, actual hours.
- `TimeEntry` — One time log. Date, hours, description, team member, associated deliverable (or none).
- `TeamMember` — Person on engagement. Role, rate, budgeted hours, actual hours.
- `ChangeOrder` — Formalized scope expansion. Deliverables added, cost, client approval status.

**Computed Properties:**
- `Engagement.total_actual_hours` — Sum of all time entries
- `Engagement.scoped_hours` — Sum of entries with deliverable match
- `Engagement.unscoped_hours` — Sum of entries with no deliverable match
- `Engagement.budget_consumed_pct` — How much of the 95-hour budget we've used
- `Engagement.projected_overrun_pct` — If current pace continues, how much over budget?
- `Engagement.margin` — Fixed fee minus internal cost (what the firm actually makes)
- `Deliverable.is_over_budget` — Did we burn more hours than budgeted for this deliverable?

**Design:**
- Dataclasses (simple, serializable, readable)
- No ORM dependency
- Properties compute on-the-fly from underlying data
- EngagementManager is in-memory for MVP (in production would load from JSON store)

---

### 2. **drift_detector.py** (Scope Drift Analysis)

Watches for deviations between plan and actuals.

**Key Classes:**
- `DriftAlert` — "Partner, something out of the ordinary happened."
  - Type: budget_overrun, unscoped_work, timeline_slip, burn_rate_anomaly, team_overallocation
  - Severity: info, warning, critical
  - Details: hours at risk, cost at risk, related time entries

- `DriftDetector` — Runs detection logic.
  - Input: an Engagement object
  - Output: list of DriftAlerts
  - Configurable thresholds (early flagging vs. late detection)

**Detection Methods:**

1. **Deliverable Budget Overrun**
   - Alert when a deliverable hits 75% of budget and is <50% complete
   - Critical when it hits 100%
   - Example: "Title Review" budgeted for 12 hours, already at 10, not delivered yet

2. **Unscoped Work**
   - Alert when 2+ hours logged with no deliverable match (warning)
   - Critical when 8+ hours accumulated
   - Example: "Client called asking for lease assignment help. That's 3.5 hours not in our scope."

3. **Burn Rate Anomaly**
   - Alert if consumption pace suggests 20%+ overrun at completion
   - Example: "We're 30% done but already burned 60% of hours."

4. **Timeline Slip**
   - Alert if deliverable is 3+ days past planned end and still in progress
   - Example: "Due Diligence Review was supposed to be done last week. Still working."

5. **Team Overallocation**
   - Alert if person exceeds their budgeted hours by 20%
   - Example: "Kevin Liu was budgeted for 40 hours, now at 48."

**Design:**
- Thresholds are conservative (flag early)
- Stores alerts to avoid duplicates (same alert doesn't fire twice)
- Blended rate calculation (average cost per hour across the team)

---

### 3. **time_entry_importer.py** (CSV Import & Parsing)

Takes time entries from external timekeeping systems and prepares them for analysis.

**Key Classes:**

- `TimeEntryImporter` — Main import engine
  - Reads CSV, parses rows, categorizes entries, attempts to match to deliverables
  - Returns ParsedTimeEntry objects (enriched with category and keywords)
  - Returns MatchResults (matched deliverable or flagged as unscoped)

- `ColumnMapping` — Handles different CSV formats
  - Clio (standard 5-column format)
  - PracticePanther (different column names)
  - Bill4Time (different date format)
  - Custom mapping for other systems

- `DescriptionParser` — Extracts meaning from entry text
  - Categorize work: research, drafting, review, negotiation, communication, etc.
  - Extract keywords: "lease assignment," "earnout," "environmental"
  - Confidence score for categorization

- `DeliverableMatcher` — Matches entries to scoped work
  - Strategy 1: Keyword matching (does entry description mention deliverable topics?)
  - Strategy 2: Fuzzy string similarity (how similar is text to deliverable name/desc?)
  - Strategy 3: Heuristics (does work category match deliverable type?)
  - Returns match score 0.0-1.0

**Example Flow:**
```
Raw CSV row:
  Date: 2024-02-16
  Timekeeper: Kevin Liu
  Duration: 3.5
  Description: "Client call re: lease assignment for Tenant B"

↓ Parse
ParsedTimeEntry:
  date: 2024-02-16
  team_member: "Kevin Liu"
  hours: 3.5
  description: "Client call re: lease assignment for Tenant B"
  task_category: COMMUNICATION
  keywords: ["lease assignment", "client requested"]
  confidence_score: 0.85

↓ Match (against deliverables)
MatchResult:
  matched_deliverable_id: None  (no deliverable called "lease assignment")
  match_score: 0.32  (below threshold of 0.6)
  is_unscoped: True
  reasoning: "No strong match. Best match was del_002 (Due Diligence) at 0.32"
```

**Design:**
- Supports multiple timekeeping system formats (extensible)
- No hard dependencies on external APIs
- Simple keyword-based categorization (no ML)
- Conservative matching (would rather flag uncertain matches as unscoped)

---

### 4. **json_store.py** (Persistence Layer)

Saves and loads engagement state to/from JSON files.

**Key Classes:**

- `JSONStore` — File I/O for engagements
  - Directory structure: `data/engagements/{engagement_id}/`
  - `engagement.json` — Main engagement definition
  - `time_entries.json` — List of all time entries
  - `change_orders/{co_id}.json` — Individual change order documents
  - `drift_history.json` — Weekly snapshots of drift alerts

- `FileLock` — Simple file-based lock
  - Used for shared drive support (multiple partners might read/write simultaneously)
  - Create a `.lock` file to indicate writer is active
  - Other processes wait or skip

**API:**

```python
store = JSONStore(data_dir="data")

# Save
store.save_engagement(engagement)           # engagement.json
store.save_time_entries(engagement_id, entries)  # time_entries.json
store.save_change_order(engagement_id, co)  # change_orders/CO-001.json
store.append_drift_history(engagement_id, snapshot)  # append to drift_history.json

# Load
eng = store.load_engagement(engagement_id)  # Reconstructs full object
entries = store.load_time_entries(engagement_id)
cos = store.load_change_orders(engagement_id)
history = store.load_drift_history(engagement_id)

# Utility
all_ids = store.list_engagements()
store.backup("backup.zip")
```

**Design:**
- Human-readable JSON (partners can inspect files)
- Custom JSON encoder for enums and dates
- File locking for shared drive robustness
- Auto-save pattern (save on every change, not "save" button)

---

### 5. **change_order_generator.py** (Scope Expansion Formalization)

Turns detected drift into a document partners can send to clients.

**Key Classes:**

- `ChangeOrderGenerator` — Creates change order drafts
  - Input: Engagement + DriftAlerts (from drift detector)
  - Groups unscoped entries by theme (lease assignment, earnout, etc.)
  - Estimates remaining hours (assume 30% more work needed to "properly" complete ad-hoc work)
  - Calculates cost using blended rate
  - Returns ChangeOrderDraft object

- `ScopeAddition` — One piece of new work
  - name: "Lease Assignment Review"
  - description: (from time entry)
  - hours_already_spent: 3.5 (what we've done)
  - hours_estimated_remaining: 1.0 (rough estimate to complete)
  - total_hours: 4.5
  - total_cost: $1,350

**Example Output:**

```python
draft = generator.generate_from_alerts(eng, alerts)

draft.scope_additions = [
  ScopeAddition(
    name="Lease Assignment Review and Negotiation",
    hours_already_spent=3.5,
    hours_estimated_remaining=1.0,
    total_hours=4.5,
    total_cost=1350,
  ),
  ScopeAddition(
    name="Earnout Side Letter Drafting",
    hours_already_spent=6.0,
    hours_estimated_remaining=2.0,
    total_hours=8.0,
    total_cost=2400,
  ),
]

draft.total_additional_hours = 12.5
draft.total_additional_cost = 3750
draft.original_fee = 35000
draft.proposed_revised_fee = 38750
```

**Design:**
- Groups entries by theme (keyword detection)
- Transparent hour estimation (assume 30% buffer)
- Calculates blended rate from team composition
- Produces documentable output

---

### 6. **change_order_renderer.py** (Document Generation)

Formats change orders as professional documents.

**Outputs:**

1. **Markdown Change Order** — Client-facing amendment
   - Professional formatting
   - Background + scope additions + fee calculation + signature blocks
   - Partners paste into their engagement letter template

2. **Email Draft** — Softer initial outreach
   - Narrative framing (not just a table of additions)
   - Explains why scope expanded
   - References the formal change order

3. **HTML Version** — Web display
   - Styled with CSS
   - Interactive (could add signature capture later)

**Design:**
- Template-based rendering (easy to customize)
- Multiple formats for different audiences
- Plain text / Markdown / HTML (no PDF/DOCX dependency)

---

## Design Decisions

### 1. **No Database**
**Why:** Small firm, no IT staff, shared drive already exists.
**Trade-off:** No complex queries or aggregations, but JSON is fine for 40 engagements.

### 2. **JSON over SQLite**
**Why:** Files are easier to backup, version control, inspect manually.
**Trade-off:** No transactions, but file locking handles shared drive contention.

### 3. **No External Dependencies**
**Why:** Ensures tool works offline, on any Python 3.11+ environment, requires no pip install.
**Trade-off:** Slightly more code (e.g., custom JSON encoder), no fancy features.

### 4. **Dataclasses over ORM**
**Why:** Simple, readable, directly serializable to JSON.
**Trade-off:** Less automatic relationship management, but transparency is a feature here.

### 5. **Keyword Matching over ML**
**Why:** Interpretable, debuggable, no training data required.
**Trade-off:** Won't catch creative descriptions, but good enough for legal work descriptions.

### 6. **Conservative Alert Thresholds**
**Why:** Missing drift (false negative) costs thousands. Catching a false positive costs 10 seconds.
**Trade-off:** More alerts, but partners are okay dismissing non-issues.

### 7. **Auto-Save, No Save Button**
**Why:** Risk of data loss is unacceptable (partners won't remember to save).
**Trade-off:** Every operation writes to disk (slower, but acceptable performance).

---

## Extension Points

**If we wanted to extend:**

1. **Timekeeping API Integration**
   - Replace CSV import with direct API calls to Clio, PracticePanther
   - Same DeliverableMatcher logic applies

2. **Change Order Workflow**
   - Integrate with e-signature platform
   - Track approvals in JSON store
   - Email reminders if client hasn't approved

3. **Analytics**
   - Dashboard (React) that reads JSON files
   - Burndown charts, margin trends, partner performance
   - Firm-wide summary (not just per-engagement)

4. **Machine Learning**
   - Train classifier on matched entries
   - Improve categorization and matching over time
   - Anomaly detection (entry that doesn't fit pattern)

5. **Inventory Management**
   - Track capacity (Kevin Liu has 40 hours budgeted across X engagements)
   - Warn if he's overallocated across all engagements

---

## Data Integrity & Safety

**File Corruption Risk:**
- Mitigated by file locking (only one writer at a time)
- JSON is human-readable (easy to spot and fix corruption)
- Backup function creates ZIP archives

**Concurrent Access:**
- FileLock ensures only one process writes at a time
- Other processes either wait (acquire=True) or skip
- timeout=30 seconds prevents deadlock

**Audit Trail:**
- drift_history.json is append-only (weekly snapshots)
- Never overwrites old data
- Partners can review history

---

## Performance Characteristics

**Typical Operations:**

- Import 60 CSV entries: <1 second
- Run drift detection: <500ms
- Generate change order: <200ms
- Save engagement: <100ms
- Load engagement: <50ms

**Scaling:**
- Design supports 100+ engagements without issue
- Each engagement is independent file
- No global aggregation required for MVP

---
