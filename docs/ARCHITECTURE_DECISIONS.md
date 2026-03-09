# Architecture Decision Records

This document captures the key technical decisions made during the design and implementation of Scope Tracker. Each ADR records the context, the decision, what alternatives were considered, and the trade-offs accepted.

---

## ADR-001: Dataclass-Based Domain Model Without ORM

**Status:** Accepted
**Date:** 2024-01

**Context:** Scope Tracker models a rich domain: engagements contain deliverables, team members, time entries, and change orders, all with computed properties like budget consumption percentages, projected overrun, and margin calculations. The target users are small transactional law firms (roughly 20 people) whose IT infrastructure consists of a shared drive and Outlook. The system needs to be simple enough to run without a database server, debuggable by inspecting data directly, and deployable with zero external dependencies beyond Python 3.11+.

**Decision:** Use Python `dataclasses` for all domain objects (`Engagement`, `Deliverable`, `TimeEntry`, `TeamMember`, `ChangeOrder`, `DriftAlert`). All computed values (e.g., `budget_consumed_pct`, `margin`, `projected_total_hours`) are implemented as `@property` methods that derive values on-the-fly from the underlying data. The `EngagementManager` holds engagements in an in-memory dictionary, with an optional JSON persistence layer (`JSONStore`) that serializes/deserializes via custom `JSONEncoder` and `asdict()`.

**Alternatives Considered:**
- **SQLAlchemy ORM with SQLite:** Would provide query capabilities, transactions, and schema migrations. Rejected because it adds a dependency, introduces a layer of abstraction that obscures the data flow, and is overkill for a system that manages roughly 40 concurrent engagements.
- **Pydantic models:** Would provide built-in JSON serialization and validation. Rejected because it adds an external dependency, violating the zero-dependency constraint for the core modules.
- **Plain dictionaries:** Would be the simplest approach. Rejected because type safety, computed properties, and self-documenting field definitions on dataclasses make the code significantly more maintainable.

**Consequences:**
- All domain logic is transparent and inspectable. A partner (or developer) can read `engagement.margin_pct` and trace exactly how it is computed by following the `@property` chain.
- Serialization requires manual work: a custom `JSONEncoder` for enums and dates, explicit `_serialize_engagement()` and `_deserialize_engagement()` methods in `JSONStore`.
- No automatic relationship management. Adding a time entry to a deliverable requires explicit mutation in `Engagement.log_time()` rather than ORM cascade behavior.
- No migration system. Schema changes to the dataclass fields require updating the JSON serialization layer manually.

---

## ADR-002: JSON File Persistence on Shared Drive

**Status:** Accepted
**Date:** 2024-01

**Context:** The target deployment environment is a small law firm with no database server, no cloud infrastructure, and no IT staff. Data needs to be stored somewhere that is backed up by existing infrastructure, accessible by multiple attorneys, and inspectable without specialized tools.

**Decision:** Persist all engagement data as JSON files in a directory structure on the firm's shared drive:
```
data/
  engagements/
    {engagement_id}/
      engagement.json
      time_entries.json
      drift_history.json
      change_orders/
        {co_id}.json
```
Each engagement is a self-contained directory. The `JSONStore` class provides load/save operations with a `FileLock` mechanism (atomic file creation via `os.O_CREAT | os.O_EXCL`) to handle concurrent access from multiple partners. A `backup()` method creates ZIP archives of the entire data directory.

**Alternatives Considered:**
- **SQLite:** Would provide transactions, indexing, and SQL queries. Rejected because JSON files are human-readable (partners can inspect and manually fix data if needed), trivially backed up (just copy the folder), and require no database driver.
- **Supabase/PostgreSQL:** Used in the SaaS version of the product for multi-tenant deployment. Not suitable for the core on-premise tool because it requires cloud connectivity and introduces infrastructure dependencies.
- **Single monolithic JSON file:** Simpler but creates contention when multiple users access the same file and makes backups/diffs harder.

**Consequences:**
- Human-readable data. Partners can open `engagement.json` in a text editor to verify figures, which builds trust in the system.
- No complex queries or aggregations. Finding "all engagements over budget" requires loading each engagement individually and checking in Python. This is acceptable at the scale of roughly 40 engagements.
- File locking provides basic concurrency safety but is not transactional. A crash during a write could leave partial data, though the lock timeout (30 seconds) and the small write size (single JSON file) make this unlikely in practice.
- The `drift_history.json` file is append-only, providing a basic audit trail of weekly drift snapshots.

---

## ADR-003: Deliverable-Centric Scope Decomposition

**Status:** Accepted
**Date:** 2024-01

**Context:** Fixed-fee engagements in transactional law (M&A, real estate closings) have a natural structure: a set of discrete deliverables (Purchase Agreement, Due Diligence Review, Closing Documents, Title Review), each with its own hours budget, assigned team members, and timeline. Scope creep manifests as work that does not map to any of these deliverables. The system needs a unit of scope that is granular enough to detect drift early but coarse enough that partners can reason about it without getting lost in detail.

**Decision:** Make the `Deliverable` the primary unit of scope tracking. Each deliverable has an `id`, `budgeted_hours`, `actual_hours`, `planned_start`, `planned_end`, `assigned_to`, and `status` (NOT_STARTED, IN_PROGRESS, IN_REVIEW, DELIVERED, DEFERRED). Every `TimeEntry` optionally references a `deliverable_id`. Entries with no deliverable match are flagged as `is_scoped=False` and marked as potential scope creep. The `DriftDetector` checks budget consumption, timeline slippage, and completion status at the deliverable level. Change orders introduce new deliverables with `is_original_scope=False` and a `change_order_id` reference.

**Alternatives Considered:**
- **Task-level tracking:** More granular (e.g., "Draft Section 3 of PSA"). Rejected because law firm time entries are described in natural language, not linked to specific tasks. The matching would be too fragile.
- **Phase-based tracking:** Coarser (e.g., "Pre-Closing Phase"). Rejected because a phase can be on-budget overall while one deliverable within it is severely over. Phase-level tracking would mask early drift signals.
- **No decomposition (engagement-level only):** Simplest but would only detect overrun after the entire engagement exceeds its budget, which is too late.

**Consequences:**
- Early detection: the system catches overrun on a single deliverable (e.g., "Due Diligence at 90% of budget") even when the overall engagement is still within budget.
- The `DeliverableMatcher` in `time_entry_importer.py` uses keyword matching, fuzzy string similarity, and category heuristics to auto-match time entries to deliverables. This works well for structured legal work descriptions but may misclassify creative or ambiguous descriptions. The conservative threshold (0.6 match score) means uncertain matches are flagged as unscoped rather than incorrectly assigned.
- Change orders add new deliverables to the engagement, which naturally extends the scope model rather than requiring a separate tracking mechanism.

---

## ADR-004: Conservative Alert Thresholds Biased Toward False Positives

**Status:** Accepted
**Date:** 2024-02

**Context:** The drift detection system needs to balance two risks: false positives (alerting when there is no real problem) and false negatives (missing real scope creep). In the target environment, the cost of a false positive is roughly 10 seconds of a partner's time to dismiss the alert. The cost of a false negative is thousands of dollars in absorbed fees that cannot be recovered once the engagement closes. Historical data from the target firm showed that unscoped work averaged 9.5 hours per engagement, often undetected until closing day.

**Decision:** Set alert thresholds conservatively:
- Unscoped work WARNING at 2.0 hours (roughly one half-day of unmatched work)
- Unscoped work CRITICAL at 8.0 hours (equivalent to a new deliverable)
- Deliverable budget WARNING at 75% consumed
- Deliverable budget CRITICAL at 100% consumed
- Burn rate alert when budget consumption exceeds 1.5x the timeline elapsed ratio
- Timeline slip after 3 days past planned end date
- Team overallocation at 120% of budgeted hours

All thresholds are configurable via the `DriftThresholds` dataclass to allow per-firm tuning.

**Alternatives Considered:**
- **Higher thresholds (e.g., 5+ hours for unscoped warning):** Would reduce noise but risks missing the critical early window where a partner can still have the scope conversation with the client.
- **ML-based anomaly detection:** Would learn normal patterns and flag deviations. Rejected because it requires training data the firm does not have, introduces a black-box component that partners would not trust, and adds external dependencies.
- **No configurable thresholds:** Simpler but different practice areas have different drift profiles. An M&A deal naturally generates more ad-hoc work than a standard real estate closing.

**Consequences:**
- Partners receive more alerts, especially in the first few weeks of using the system. The expectation is that this is acceptable and that partners will develop quick triage habits (dismiss in 10 seconds vs. investigate further).
- The `_seen_triggers` set in `DriftDetector` prevents duplicate alerts for the same condition, so a deliverable at 80% budget generates one WARNING, not a new one every time drift detection runs.
- Firms with different risk tolerances can adjust thresholds via `DriftThresholds` without modifying detection logic.

---

## ADR-005: Theme-Based Grouping for Change Order Generation

**Status:** Accepted
**Date:** 2024-02

**Context:** When the drift detector identifies significant unscoped work (8+ hours), the partner needs a structured change order document to present to the client. Raw time entries are too granular ("3.5 hours: Client call re: lease assignment for Tenant B") to serve as scope additions in a professional document. The system needs to aggregate related entries into logical work items that make business sense to the client.

**Decision:** The `ChangeOrderGenerator` groups unscoped time entries by theme using keyword extraction from descriptions. A predefined dictionary maps legal work keywords to theme categories (e.g., "lease assignment" and "landlord" both map to `lease_assignment`; "earnout" and "side letter" map to their respective themes). Entries sharing a theme are aggregated into a single `ScopeAddition` with combined hours, a representative description (longest entry description), and an estimated remaining effort calculated as 30% of hours already spent. The generator then calculates cost using the engagement team's blended hourly rate and produces a `ChangeOrderDraft` with document text, fee impact, and original/revised fee breakdown.

**Alternatives Considered:**
- **LLM-based grouping:** Use a language model to cluster entries semantically. Rejected because it adds an external dependency, introduces latency, and the keyword approach works well for the structured vocabulary of legal time entries.
- **Manual grouping by partner:** The partner selects which entries to include. Rejected for the initial version because it creates friction. The auto-generated draft gives the partner a starting point they can edit, which is faster than building from scratch.
- **One scope addition per time entry:** No grouping. Rejected because a change order with 8 individual line items ("3.5 hours of calls," "2.0 hours of research," etc.) is less professional and harder for the client to evaluate than 2-3 logical work items.

**Consequences:**
- The keyword-to-theme mapping is domain-specific to legal work. Extending to other professional services (consulting, accounting) would require updating the keyword dictionary in `_extract_theme()` and `_theme_to_name()`.
- The 30% remaining estimate is a rough heuristic. Partners are expected to review and adjust the draft before sending to the client.
- The `ChangeOrderRenderer` produces three output formats (Markdown, email draft, HTML) from the same `ChangeOrderDraft` data, allowing partners to choose the appropriate communication channel.

---

## ADR-006: Team Allocation Model with Role-Based Rates and Per-Member Budgets

**Status:** Accepted
**Date:** 2024-01

**Context:** Fixed-fee engagements are priced based on expected team composition. A real estate closing budgeted at $35,000 and 95 hours assumes a specific mix: 5 hours of partner time at $550/hr, 40 hours of senior associate time at $350/hr, 40 hours of junior associate time at $225/hr, and 10 hours of paralegal time at $125/hr. If the actual mix shifts toward more expensive resources (e.g., the partner spends 15 hours instead of 5), the engagement's internal cost rises even if total hours stay within budget. The system needs to track not just total hours but the cost impact of who is doing the work.

**Decision:** Each `TeamMember` has a `role` (Partner, Senior Associate, Junior Associate, Paralegal), an `hourly_rate` (internal cost rate, not the client-facing rate since it is a fixed fee), `budgeted_hours`, and `actual_hours`. The `Engagement.internal_cost` property calculates total cost by multiplying each time entry's hours by the corresponding team member's rate. `Engagement.margin` is `fixed_fee - internal_cost`. The `DriftDetector` includes a `TEAM_OVERALLOCATION` check that fires when any team member exceeds 120% of their budgeted hours, which often indicates work being done by the wrong person or unplanned scope expansion.

**Alternatives Considered:**
- **Flat blended rate only:** Simpler. Use a single average rate for all calculations. Rejected because it hides the cost impact of team composition changes. A deal where the partner works 3x their budgeted hours looks fine at a blended rate but is actually destroying margin.
- **No per-member budget:** Track only total hours at the engagement level. Rejected because per-member tracking catches a common pattern: a junior associate gets stuck, escalates to a senior associate, and the senior's time is never budgeted.
- **Billing rate vs. cost rate:** Use the attorney's billing rate instead of cost rate. Rejected because on a fixed-fee engagement, the billing rate is irrelevant. What matters is the firm's internal cost of delivering the work.

**Consequences:**
- The `get_summary()` method includes a `team_utilization` array showing each member's budgeted vs. actual hours and utilization percentage, giving the partner visibility into who is over/under allocated.
- The blended rate (used in change order cost calculations) is computed as a weighted average: `sum(rate * budgeted_hours) / sum(budgeted_hours)`, which accounts for the expected team mix rather than a simple average of rates.
- The engagement's `effective_rate` (`fixed_fee / total_budgeted_hours`) provides a quick sanity check: if the effective rate drops below the blended cost rate, the engagement is projected to be unprofitable before any work begins.

---

## ADR-007: Railway PostgreSQL Over Supabase for Single-Tenant Deployment

**Status:** Accepted
**Date:** 2024-03

**Context:** The initial product was built with Supabase (PostgreSQL + RLS + authentication + realtime) to handle potential multi-tenant expansion. In production with a specific law firm, the single-tenant model is proven and won't change. Supabase's multi-tenant infrastructure (Row-Level Security, authentication providers, realtime subscriptions) adds $500+/month in base costs, imposes complexity on queries and debugging, and is unnecessary for a single deployment. Railway PostgreSQL offers a simple, standard PostgreSQL instance at $15-30/month, direct connection support, automatic backups, and transparent operations.

**Decision:** Migrate from Supabase to Railway-hosted PostgreSQL. Replace Supabase SDK calls with standard database clients:
- **Python:** Use `psycopg2` for synchronous queries and `asyncpg` for async (Trigger.dev background jobs)
- **Node.js/TypeScript:** Use `pg` client library
- Implement application-layer role-based access control (check user roles and permissions in code) instead of relying on RLS
- Connection managed via `DATABASE_URL` environment variable (standard Heroku/Railway convention)
- Queries written as plain SQL with parameterized statements for safety

**Alternatives Considered:**
- **Keep Supabase:** Comfortable with existing setup, handles authentication. Rejected because unnecessary multi-tenant complexity adds $6K+/year for a single-tenant product, introduces debugging indirection (RLS rules are opaque), and ties us to Supabase's SDK rather than standard PostgreSQL clients.
- **SQLite with Litestream:** Simpler database. Rejected because Litestream replication to S3 adds operational overhead; PostgreSQL's stability and feature set (transactions, indexes, backups) are worth the modest additional cost.
- **Amazon RDS:** More features, managed backups, multi-AZ. Rejected because overkill for this scale and significantly more expensive ($100+/month vs. Railway's $15-30).

**Consequences:**
- Lose Supabase's realtime subscriptions (not needed—polling via HTTP works fine for partner dashboard)
- Lose Supabase's built-in authentication (firm has SSO via their corporate directory; we can integrate separately or use JWT tokens issued by our app)
- Must write SQL queries explicitly (instead of SDK convenience methods). This is a feature—queries are transparent and auditable.
- All permission logic moves to application code. Every endpoint must explicitly check `if user.role == "partner" or user.engagement_ids.includes(engagement_id)` before returning data.
- Migration path: Export all data from Supabase, load into Railway PostgreSQL, update environment variables, update SDK imports in Python and Node.

**Trade-offs:**
- Gain: 30% cost reduction ($6K→$1.5K/year), faster query debugging, standard PostgreSQL semantics, simpler operations
- Lose: Multi-tenant infrastructure we don't use, slight convenience functions from Supabase SDK
- Risk mitigation: Railway has excellent backup and restore tooling; we run daily snapshots; Postgres is stable and proven

---

## ADR-008: Pivot Feature – Drift Scoring System Instead of Alert Fatigue

**Status:** Accepted
**Date:** 2024-03

**Context:** The initial MVP launched with real-time scope change alerts. Every time an unscoped time entry was logged, partners received a notification. In the first two weeks, one partner received 27 alerts on a single engagement—most flagging minor clarifications or routine client requests. Partners reported "alert fatigue" and began dismissing notifications reflexively, defeating the system's purpose of surfacing critical scope creep early.

The root cause: the system couldn't distinguish between cosmetic scope changes (client asks for a minor clarification on the PSA that takes 20 minutes to research) and scope-expanding changes (client requests an entirely new deliverable—environmental due diligence—that requires 15+ hours).

**Decision:** Implement a **drift scoring system** that categorizes scope additions by impact before alerting:
- **Cosmetic Changes (Score: 1-3):** Minor clarifications, routine client calls, re-explanations of existing work. Alert rule: log silently, no notification
- **Minor Additions (Score: 4-6):** New small deliverables (4-8 hours). Alert rule: soft alert to lead associate; notify supervising partner only if cumulative score > 10 for the week
- **Significant Additions (Score: 7-9):** Medium scope expansions (8-16 hours). Alert rule: immediate notification to partner with cost impact
- **Major Additions (Score: 10+):** Large scope expansions (16+ hours). Alert rule: critical alert, recommend change order generation

Scoring algorithm:
```
base_score = min(hours_unscoped, 10)  // Cap at 10
keyword_multiplier = 1.0  // Default
if entry_description matches ["specification", "clarification", "existing work"] → keyword_multiplier = 0.5
if entry_description matches ["new deliverable", "change", "expansion"] → keyword_multiplier = 1.5
final_score = base_score * keyword_multiplier
```

Cumulative drift for engagement calculated daily. Only alert when:
1. Single entry pushes engagement's cumulative drift from "safe" to "warning" or "critical", OR
2. Cumulative weekly drift exceeds configurable threshold (default: 15 points)

**Consequences:**
- First-week alert volume dropped from 27 to 3 on the same engagement (alert fatigue solved)
- Partners now trust notifications because they reflect actual scope risk
- The team can handle more nuanced scope changes without reflexive dismissal
- Change detection is still transparent: partners can inspect the scoring model in code and request adjustments per firm culture
- Trade-off: Added complexity to `DriftDetector`. Benefit: Overrun rate dropped from 28% to 11% because partners act on alerts sooner

**Measurement:**
- Before: 28% average overrun, 27 alerts/week/engagement, 15% of alerts acted upon
- After: 11% average overrun, 3 alerts/week/engagement, 92% of alerts acted upon, 34% of detected scope additions converted to change orders
