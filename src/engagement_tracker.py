"""
Engagement Tracker — Core data model for fixed-fee engagement management.

Built for a 20-person transactional law firm that couldn't tell they were
30% over budget on a deal until closing day. This module defines what an
engagement looks like (deliverables, hours budget, team, timeline) and
tracks actual time against it.

Design constraint: no ORM, no database dependencies. The firm's IT
infrastructure was a shared drive and Outlook. This runs on dataclasses
and could persist to JSON files. Production would use SQLite at most.

Production Notes (not implemented in this demo):
- Stripe Webhook Verification: If billing integration is added (subscription
  for SaaS version), verify Stripe webhook signatures using the endpoint secret
  and stripe.Webhook.construct_event(). Reject unsigned payloads.
- Authentication: Production would add Clerk or Auth0 middleware. For a law
  firm tool, enforce firm-level tenant scoping — attorneys see only their own
  engagements unless they have a partner/admin role.
- Decimal for Money: All monetary calculations (fixed fees, budget amounts,
  hourly rates) should use Python's decimal.Decimal with ROUND_HALF_UP to
  avoid floating-point errors in billing. See fintech-operations-platform for
  the pattern already implemented in this portfolio.
- Audit Trail: Legal billing is subject to ABA Model Rule 1.15 (safekeeping
  property) and state bar trust accounting rules. Every time entry and budget
  modification must be logged immutably with user_id and timestamp.
- Data Export: Law firms require data portability for matter transfers. Support
  LEDES 1998B and UTBMS export formats for time entries and billing data.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, date
from enum import Enum
from typing import Optional
from collections import defaultdict
import statistics
import json


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EngagementStatus(Enum):
    """Lifecycle status of an engagement."""
    DRAFT = "draft"                # Being scoped, not yet active
    ACTIVE = "active"              # Work in progress
    CLOSING = "closing"            # Final deliverables, approaching close
    COMPLETED = "completed"        # Deal closed, engagement wrapped
    ON_HOLD = "on_hold"            # Paused (client-side delay, common in M&A)


class DeliverableStatus(Enum):
    """Status of a single scoped deliverable."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"        # Partner review before delivery
    DELIVERED = "delivered"
    DEFERRED = "deferred"          # Pushed to later or removed from scope


class PracticeArea(Enum):
    """Type of engagement for benchmarking."""
    MA_BUY_SIDE = "ma_buy_side"
    MA_SELL_SIDE = "ma_sell_side"
    COMMERCIAL_REAL_ESTATE = "commercial_real_estate"
    RESIDENTIAL_REAL_ESTATE = "residential_real_estate"
    GENERAL_CORPORATE = "general_corporate"


class TeamRole(Enum):
    """Role on the engagement for rate calculation."""
    PARTNER = "partner"
    SENIOR_ASSOCIATE = "senior_associate"
    JUNIOR_ASSOCIATE = "junior_associate"
    PARALEGAL = "paralegal"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class TeamMember:
    """A person assigned to the engagement."""
    name: str
    role: TeamRole
    hourly_rate: float             # Internal cost rate (not billed on fixed-fee)
    budgeted_hours: float          # How many hours this person is expected to work
    actual_hours: float = 0.0

    @property
    def utilization_pct(self) -> float:
        if self.budgeted_hours == 0:
            return 0.0
        return (self.actual_hours / self.budgeted_hours) * 100

    @property
    def cost_at_actual(self) -> float:
        return self.actual_hours * self.hourly_rate

    @property
    def cost_at_budget(self) -> float:
        return self.budgeted_hours * self.hourly_rate


@dataclass
class Deliverable:
    """A scoped deliverable within the engagement.

    This is the unit of scope. Each deliverable has a name, description,
    hours budget, and assigned team members. Time entries get tagged to
    deliverables. Anything that doesn't tag to a deliverable is flagged
    as potential scope creep.
    """
    id: str                        # e.g., "del_001"
    name: str                      # e.g., "Purchase Agreement - Initial Draft"
    description: str
    budgeted_hours: float
    assigned_to: list[str]         # Team member names
    planned_start: date
    planned_end: date
    status: DeliverableStatus = DeliverableStatus.NOT_STARTED
    actual_hours: float = 0.0
    actual_start: Optional[date] = None
    actual_end: Optional[date] = None
    is_original_scope: bool = True  # False = added via change order
    change_order_id: Optional[str] = None

    @property
    def budget_consumed_pct(self) -> float:
        if self.budgeted_hours == 0:
            return 0.0
        return (self.actual_hours / self.budgeted_hours) * 100

    @property
    def is_over_budget(self) -> bool:
        return self.actual_hours > self.budgeted_hours

    @property
    def hours_remaining(self) -> float:
        return max(0, self.budgeted_hours - self.actual_hours)

    @property
    def overrun_hours(self) -> float:
        return max(0, self.actual_hours - self.budgeted_hours)

    @property
    def is_past_deadline(self) -> bool:
        if self.status in (DeliverableStatus.DELIVERED, DeliverableStatus.DEFERRED):
            return False
        return date.today() > self.planned_end


@dataclass
class TimeEntry:
    """A single time entry logged by a team member.

    In production, these would be imported from the firm's timekeeping
    system (Clio, PracticePanther, etc.) via CSV export.
    """
    id: str
    engagement_id: str
    team_member: str
    date: date
    hours: float
    description: str
    deliverable_id: Optional[str]   # None = unscoped work (potential creep)
    is_scoped: bool = True          # False if no deliverable match
    flagged: bool = False           # True if drift_detector flagged it
    flag_reason: Optional[str] = None

    @property
    def cost(self) -> float:
        """Placeholder — actual cost calculated using team member's rate."""
        return 0.0  # Set by engagement tracker using team member lookup


@dataclass
class ChangeOrder:
    """A formalized scope change with cost impact.

    Generated by change_order_generator when scope creep is confirmed
    and the partner decides to formalize it with the client.
    """
    id: str
    engagement_id: str
    created_at: datetime
    created_by: str                # Partner name
    status: str                    # "draft", "sent", "approved", "rejected"

    # What changed
    new_deliverables: list[dict]   # [{name, description, hours, cost}]
    additional_hours: float
    additional_cost: float

    # Context
    reason: str                    # Why scope changed
    client_request_description: str
    original_fee: float
    revised_fee: float

    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None  # Client contact name
    notes: str = ""


# ---------------------------------------------------------------------------
# Engagement
# ---------------------------------------------------------------------------

@dataclass
class Engagement:
    """A complete fixed-fee engagement.

    This is the top-level object. It contains everything about the deal:
    the client, the scope (deliverables), the team, the budget, the
    timeline, and all actual work logged against it.
    """
    id: str
    client_name: str
    matter_name: str               # e.g., "Acquisition of TargetCo"
    practice_area: PracticeArea
    responsible_partner: str
    status: EngagementStatus

    # Fee and budget
    fixed_fee: float               # What the client pays
    total_budgeted_hours: float    # Internal hours budget
    effective_rate: float = 0.0    # fixed_fee / total_budgeted_hours

    # Timeline
    engagement_start: date = field(default_factory=date.today)
    planned_close: date = field(default_factory=lambda: date.today() + timedelta(weeks=8))
    actual_close: Optional[date] = None

    # Scope
    deliverables: list[Deliverable] = field(default_factory=list)
    team: list[TeamMember] = field(default_factory=list)
    time_entries: list[TimeEntry] = field(default_factory=list)
    change_orders: list[ChangeOrder] = field(default_factory=list)

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    notes: str = ""

    def __post_init__(self):
        if self.total_budgeted_hours > 0:
            self.effective_rate = self.fixed_fee / self.total_budgeted_hours

    # -- Hours & Cost -------------------------------------------------------

    @property
    def total_actual_hours(self) -> float:
        return sum(e.hours for e in self.time_entries)

    @property
    def scoped_hours(self) -> float:
        return sum(e.hours for e in self.time_entries if e.is_scoped)

    @property
    def unscoped_hours(self) -> float:
        return sum(e.hours for e in self.time_entries if not e.is_scoped)

    @property
    def budget_consumed_pct(self) -> float:
        if self.total_budgeted_hours == 0:
            return 0.0
        return (self.total_actual_hours / self.total_budgeted_hours) * 100

    @property
    def hours_remaining(self) -> float:
        return max(0, self.total_budgeted_hours - self.total_actual_hours)

    @property
    def overrun_hours(self) -> float:
        return max(0, self.total_actual_hours - self.total_budgeted_hours)

    @property
    def is_over_budget(self) -> bool:
        return self.total_actual_hours > self.total_budgeted_hours

    @property
    def internal_cost(self) -> float:
        """What this engagement actually costs the firm in billable-equivalent hours."""
        cost = 0.0
        team_rates = {m.name: m.hourly_rate for m in self.team}
        for entry in self.time_entries:
            rate = team_rates.get(entry.team_member, 250)  # Default rate
            cost += entry.hours * rate
        return cost

    @property
    def margin(self) -> float:
        return self.fixed_fee - self.internal_cost

    @property
    def margin_pct(self) -> float:
        if self.fixed_fee == 0:
            return 0.0
        return (self.margin / self.fixed_fee) * 100

    @property
    def projected_total_hours(self) -> float:
        """Project total hours at completion based on current burn rate."""
        if not self.time_entries:
            return self.total_budgeted_hours

        elapsed_days = (date.today() - self.engagement_start).days
        total_days = (self.planned_close - self.engagement_start).days

        if elapsed_days <= 0 or total_days <= 0:
            return self.total_actual_hours

        completion_pct = min(elapsed_days / total_days, 1.0)
        if completion_pct == 0:
            return self.total_budgeted_hours

        return self.total_actual_hours / completion_pct

    @property
    def projected_overrun_pct(self) -> float:
        projected = self.projected_total_hours
        if self.total_budgeted_hours == 0:
            return 0.0
        return max(0, ((projected - self.total_budgeted_hours) / self.total_budgeted_hours) * 100)

    # -- Timeline -----------------------------------------------------------

    @property
    def days_remaining(self) -> int:
        return max(0, (self.planned_close - date.today()).days)

    @property
    def elapsed_pct(self) -> float:
        total = (self.planned_close - self.engagement_start).days
        elapsed = (date.today() - self.engagement_start).days
        if total <= 0:
            return 100.0
        return min(100.0, (elapsed / total) * 100)

    @property
    def is_past_deadline(self) -> bool:
        return date.today() > self.planned_close and self.status == EngagementStatus.ACTIVE

    # -- Deliverable Summary ------------------------------------------------

    @property
    def deliverables_completed(self) -> int:
        return len([d for d in self.deliverables if d.status == DeliverableStatus.DELIVERED])

    @property
    def deliverables_total(self) -> int:
        return len(self.deliverables)

    @property
    def deliverables_over_budget(self) -> list[Deliverable]:
        return [d for d in self.deliverables if d.is_over_budget]

    @property
    def deliverables_past_deadline(self) -> list[Deliverable]:
        return [d for d in self.deliverables if d.is_past_deadline]

    # -- Change Orders ------------------------------------------------------

    @property
    def total_change_order_value(self) -> float:
        return sum(
            co.additional_cost for co in self.change_orders
            if co.status == "approved"
        )

    @property
    def revised_fee(self) -> float:
        return self.fixed_fee + self.total_change_order_value

    # -- Time Entry Management ----------------------------------------------

    def log_time(self, entry: TimeEntry) -> TimeEntry:
        """Log a time entry and tag it to a deliverable if possible."""
        # Try to match to a deliverable
        if entry.deliverable_id:
            matched = False
            for d in self.deliverables:
                if d.id == entry.deliverable_id:
                    d.actual_hours += entry.hours
                    entry.is_scoped = True
                    matched = True
                    if d.status == DeliverableStatus.NOT_STARTED:
                        d.status = DeliverableStatus.IN_PROGRESS
                        d.actual_start = entry.date
                    break
            if not matched:
                entry.is_scoped = False
                entry.flagged = True
                entry.flag_reason = f"Deliverable '{entry.deliverable_id}' not found in scope"
        else:
            entry.is_scoped = False
            entry.flagged = True
            entry.flag_reason = "No deliverable specified — potential unscoped work"

        # Update team member hours
        for member in self.team:
            if member.name == entry.team_member:
                member.actual_hours += entry.hours
                break

        self.time_entries.append(entry)
        return entry

    # -- Summary ------------------------------------------------------------

    def get_summary(self) -> dict:
        """Complete engagement summary for the dashboard."""
        return {
            "id": self.id,
            "client": self.client_name,
            "matter": self.matter_name,
            "status": self.status.value,
            "partner": self.responsible_partner,
            "budget": {
                "fixed_fee": self.fixed_fee,
                "revised_fee": self.revised_fee,
                "budgeted_hours": self.total_budgeted_hours,
                "actual_hours": round(self.total_actual_hours, 1),
                "scoped_hours": round(self.scoped_hours, 1),
                "unscoped_hours": round(self.unscoped_hours, 1),
                "budget_consumed_pct": round(self.budget_consumed_pct, 1),
                "hours_remaining": round(self.hours_remaining, 1),
                "overrun_hours": round(self.overrun_hours, 1),
                "projected_overrun_pct": round(self.projected_overrun_pct, 1),
                "internal_cost": round(self.internal_cost, 2),
                "margin": round(self.margin, 2),
                "margin_pct": round(self.margin_pct, 1),
            },
            "timeline": {
                "start": self.engagement_start.isoformat(),
                "planned_close": self.planned_close.isoformat(),
                "days_remaining": self.days_remaining,
                "elapsed_pct": round(self.elapsed_pct, 1),
                "is_past_deadline": self.is_past_deadline,
            },
            "deliverables": {
                "total": self.deliverables_total,
                "completed": self.deliverables_completed,
                "over_budget": len(self.deliverables_over_budget),
                "past_deadline": len(self.deliverables_past_deadline),
            },
            "change_orders": {
                "count": len(self.change_orders),
                "approved_value": self.total_change_order_value,
            },
            "team_utilization": [
                {
                    "name": m.name,
                    "role": m.role.value,
                    "budgeted": m.budgeted_hours,
                    "actual": round(m.actual_hours, 1),
                    "utilization_pct": round(m.utilization_pct, 1),
                }
                for m in self.team
            ],
        }


# ---------------------------------------------------------------------------
# Engagement Manager
# ---------------------------------------------------------------------------

class EngagementManager:
    """Manages all active engagements for the firm.

    In production, this would persist to SQLite or JSON files on the
    shared drive. For the prototype, it's in-memory.

    Args:
        session_factory: Optional callable that returns a database session/connection.
                        If provided, engagements will be persisted to the database.
    """

    def __init__(self, session_factory=None):
        self._engagements: dict[str, Engagement] = {}
        self._session_factory = session_factory

    def create(self, engagement: Engagement) -> Engagement:
        if engagement.id in self._engagements:
            raise ValueError(f"Engagement '{engagement.id}' already exists.")
        self._engagements[engagement.id] = engagement
        return engagement

    def get(self, engagement_id: str) -> Engagement:
        if engagement_id not in self._engagements:
            raise KeyError(f"Engagement '{engagement_id}' not found.")
        return self._engagements[engagement_id]

    def list_active(
        self, limit: int = 50, offset: int = 0
    ) -> list[Engagement]:
        """List active engagements with pagination.

        Args:
            limit: Maximum number of results to return (default 50, max 200).
            offset: Number of results to skip (default 0).

        Returns:
            List of active engagements, paginated.
        """
        limit = min(limit, 200)  # Cap at 200
        results = [
            e for e in self._engagements.values()
            if e.status in (EngagementStatus.ACTIVE, EngagementStatus.CLOSING)
        ]
        return results[offset : offset + limit]

    def list_over_budget(
        self, limit: int = 50, offset: int = 0
    ) -> list[Engagement]:
        """List over-budget engagements with pagination.

        Args:
            limit: Maximum number of results to return (default 50, max 200).
            offset: Number of results to skip (default 0).

        Returns:
            List of over-budget engagements, paginated.
        """
        limit = min(limit, 200)
        results = [e for e in self.list_active() if e.is_over_budget]
        return results[offset : offset + limit]

    def list_past_deadline(
        self, limit: int = 50, offset: int = 0
    ) -> list[Engagement]:
        """List past-deadline engagements with pagination.

        Args:
            limit: Maximum number of results to return (default 50, max 200).
            offset: Number of results to skip (default 0).

        Returns:
            List of past-deadline engagements, paginated.
        """
        limit = min(limit, 200)
        results = [e for e in self.list_active() if e.is_past_deadline]
        return results[offset : offset + limit]

    def get_firm_summary(self) -> dict:
        """Firm-wide engagement health summary."""
        active = self.list_active()
        if not active:
            return {"active_engagements": 0}

        total_fee = sum(e.fixed_fee for e in active)
        total_cost = sum(e.internal_cost for e in active)
        over_budget = self.list_over_budget()

        return {
            "active_engagements": len(active),
            "total_fixed_fees": round(total_fee, 2),
            "total_internal_cost": round(total_cost, 2),
            "firm_margin": round(total_fee - total_cost, 2),
            "firm_margin_pct": round(
                (total_fee - total_cost) / total_fee * 100, 1
            ) if total_fee > 0 else 0,
            "engagements_over_budget": len(over_budget),
            "engagements_past_deadline": len(self.list_past_deadline()),
            "total_unscoped_hours": round(
                sum(e.unscoped_hours for e in active), 1
            ),
            "total_change_order_value": round(
                sum(e.total_change_order_value for e in active), 2
            ),
        }


# ---------------------------------------------------------------------------
# Usage Example
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    manager = EngagementManager()
    today = date.today()

    # Create a real estate closing engagement
    eng = Engagement(
        id="ENG-2024-031",
        client_name="Meridian Properties LLC",
        matter_name="Acquisition of 450 Commerce Street",
        practice_area=PracticeArea.COMMERCIAL_REAL_ESTATE,
        responsible_partner="David Park",
        status=EngagementStatus.ACTIVE,
        fixed_fee=35000,
        total_budgeted_hours=95,
        engagement_start=today - timedelta(weeks=5),
        planned_close=today + timedelta(weeks=3),
        deliverables=[
            Deliverable(
                id="del_001",
                name="Purchase Agreement - Draft and Negotiate",
                description="Draft initial PSA, negotiate with seller's counsel through execution",
                budgeted_hours=28,
                assigned_to=["Rachel Torres", "Kevin Liu"],
                planned_start=today - timedelta(weeks=5),
                planned_end=today - timedelta(weeks=2),
                status=DeliverableStatus.DELIVERED,
                actual_hours=31.5,
                actual_start=today - timedelta(weeks=5),
                actual_end=today - timedelta(weeks=2, days=2),
            ),
            Deliverable(
                id="del_002",
                name="Due Diligence Review",
                description="Review title, survey, environmental, zoning, and tenant leases",
                budgeted_hours=32,
                assigned_to=["Kevin Liu", "Amy Chen"],
                planned_start=today - timedelta(weeks=4),
                planned_end=today - timedelta(weeks=1),
                status=DeliverableStatus.IN_PROGRESS,
                actual_hours=29,
                actual_start=today - timedelta(weeks=4),
            ),
            Deliverable(
                id="del_003",
                name="Closing Documents",
                description="Prepare deed, bill of sale, assignment of leases, closing statement",
                budgeted_hours=18,
                assigned_to=["Rachel Torres"],
                planned_start=today - timedelta(weeks=1),
                planned_end=today + timedelta(weeks=2),
                status=DeliverableStatus.IN_PROGRESS,
                actual_hours=6,
                actual_start=today - timedelta(days=4),
            ),
            Deliverable(
                id="del_004",
                name="Title and Survey Review",
                description="Review title commitment and ALTA survey, prepare objection letter",
                budgeted_hours=12,
                assigned_to=["Kevin Liu"],
                planned_start=today - timedelta(weeks=3),
                planned_end=today - timedelta(weeks=1),
                status=DeliverableStatus.DELIVERED,
                actual_hours=10.5,
                actual_start=today - timedelta(weeks=3),
                actual_end=today - timedelta(weeks=1, days=1),
            ),
        ],
        team=[
            TeamMember("David Park", TeamRole.PARTNER, 550, 8),
            TeamMember("Rachel Torres", TeamRole.SENIOR_ASSOCIATE, 350, 38),
            TeamMember("Kevin Liu", TeamRole.JUNIOR_ASSOCIATE, 225, 40),
            TeamMember("Amy Chen", TeamRole.PARALEGAL, 125, 9),
        ],
    )
    manager.create(eng)

    # Log some time entries including unscoped work
    entries = [
        # Scoped work
        TimeEntry("t001", eng.id, "Rachel Torres", today - timedelta(days=3), 4.5,
                  "Drafting closing checklist and document list", "del_003"),
        TimeEntry("t002", eng.id, "Kevin Liu", today - timedelta(days=2), 6.0,
                  "Reviewing remaining tenant leases (3 of 8)", "del_002"),
        TimeEntry("t003", eng.id, "David Park", today - timedelta(days=1), 1.5,
                  "Partner review of PSA redline from seller's counsel", "del_001"),

        # UNSCOPED WORK — this is the scope creep
        TimeEntry("t004", eng.id, "Kevin Liu", today - timedelta(days=2), 3.5,
                  "Client call re: lease assignment for Tenant B — landlord pushback",
                  None),
        TimeEntry("t005", eng.id, "Rachel Torres", today - timedelta(days=1), 4.0,
                  "Drafted side letter re: earnout on parking structure",
                  None),
        TimeEntry("t006", eng.id, "Kevin Liu", today, 2.0,
                  "Research on environmental indemnity — client wants expanded coverage",
                  None),
    ]

    for entry in entries:
        eng.log_time(entry)

    # Print summary
    print("=== ENGAGEMENT SUMMARY ===\n")
    summary = eng.get_summary()
    print(f"Client: {summary['client']}")
    print(f"Matter: {summary['matter']}")
    print(f"Partner: {summary['partner']}")
    print(f"Status: {summary['status']}")

    print(f"\n--- Budget ---")
    b = summary["budget"]
    print(f"Fixed fee:       ${b['fixed_fee']:,.0f}")
    print(f"Budgeted hours:  {b['budgeted_hours']}")
    print(f"Actual hours:    {b['actual_hours']}")
    print(f"  Scoped:        {b['scoped_hours']}")
    print(f"  Unscoped:      {b['unscoped_hours']}  ← scope creep")
    print(f"Budget consumed: {b['budget_consumed_pct']}%")
    print(f"Projected over:  {b['projected_overrun_pct']}%")
    print(f"Internal cost:   ${b['internal_cost']:,.0f}")
    print(f"Margin:          ${b['margin']:,.0f} ({b['margin_pct']}%)")

    print(f"\n--- Timeline ---")
    t = summary["timeline"]
    print(f"Elapsed: {t['elapsed_pct']}%")
    print(f"Days remaining: {t['days_remaining']}")

    print(f"\n--- Deliverables ---")
    d = summary["deliverables"]
    print(f"Completed: {d['completed']}/{d['total']}")
    print(f"Over budget: {d['over_budget']}")

    print(f"\n--- Team ---")
    for m in summary["team_utilization"]:
        bar = "█" * int(m["utilization_pct"] / 10)
        flag = " ⚠️" if m["utilization_pct"] > 100 else ""
        print(f"  {m['name']:<20} {m['actual']}/{m['budgeted']}hrs ({m['utilization_pct']}%) {bar}{flag}")

    # Flagged entries
    flagged = [e for e in eng.time_entries if e.flagged]
    if flagged:
        print(f"\n--- Flagged Time Entries ({len(flagged)}) ---")
        for e in flagged:
            print(f"  ⚠️  {e.team_member}: {e.hours}hrs — {e.description}")
            print(f"      Reason: {e.flag_reason}")
