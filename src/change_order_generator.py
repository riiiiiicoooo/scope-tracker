"""
Change Order Generator — Turns detected scope creep into a client conversation.

This is the module that actually recovers money. Detecting scope creep is
useless if the partner doesn't have something concrete to bring to the
client. Before this existed, the "scope creep conversation" was:

    Partner: "We've been doing some work outside the original scope."
    Client: "Like what?"
    Partner: "Um... some extra lease review and a side letter."
    Client: "How much extra?"
    Partner: "I'm not sure exactly, let me check."
    [Partner never follows up. Firm absorbs the cost.]

After this module, the conversation is:

    Partner: "Here's a summary of three additional work items your team
    has requested. The lease assignment review, the earnout side letter,
    and the expanded environmental indemnity. That's 14.5 hours of
    additional work at a cost of $4,350. I can formalize this as an
    amendment to our engagement letter."

The change order document gives the partner something to hand to the client.
It's professional, specific, and makes the conversation about facts
instead of feelings.
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Optional
from collections import defaultdict

from engagement_tracker import (
    Engagement,
    Deliverable,
    DeliverableStatus,
    TimeEntry,
    ChangeOrder,
    TeamRole,
)
from drift_detector import DriftAlert, DriftType, AlertStatus


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class ScopeAddition:
    """A single piece of work to include in the change order.

    Each addition maps to either:
    - Unscoped time entries (work already done, needs to be formalized)
    - A new deliverable (work the client is requesting going forward)
    """
    name: str
    description: str
    hours_already_spent: float       # Work already done (sunk cost)
    hours_estimated_remaining: float  # Work still needed to complete
    total_hours: float
    assigned_to: list[str]
    hourly_rate: float               # Blended rate for this work
    total_cost: float
    source: str                      # "time_entries" or "client_request"
    related_entry_ids: list[str] = field(default_factory=list)
    related_alert_ids: list[str] = field(default_factory=list)


@dataclass
class ChangeOrderDraft:
    """A complete change order document ready for partner review.

    The partner reviews this, adjusts as needed, then sends to the client.
    """
    engagement_id: str
    client_name: str
    matter_name: str
    generated_at: datetime
    generated_by: str                # "system" or partner name

    # Context
    original_scope_summary: str
    reason_for_change: str

    # Additions
    scope_additions: list[ScopeAddition]
    total_additional_hours: float
    total_additional_cost: float

    # Fee impact
    original_fee: float
    proposed_revised_fee: float
    fee_increase_pct: float

    # Original budget context
    original_budgeted_hours: float
    hours_consumed_to_date: float
    budget_consumed_pct: float

    # Related alerts
    triggered_by_alert_ids: list[str]

    # Document text
    document_text: str               # Formatted change order for client

    # Status tracking
    status: str = "draft"            # draft, partner_review, sent, approved, rejected


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class ChangeOrderGenerator:
    """Generates change order documents from drift alerts and unscoped work.

    Takes the raw data from drift_detector (alerts, unscoped time entries)
    and produces a structured document the partner can review and send
    to the client.

    The generator does three things:
    1. Groups unscoped work into logical scope additions
    2. Calculates cost impact using the engagement's blended rate
    3. Formats everything into a professional change order document
    """

    def __init__(self):
        self._change_order_counter = 0

    def generate_from_alerts(
        self,
        engagement: Engagement,
        alerts: list[DriftAlert],
        additional_context: str = "",
    ) -> ChangeOrderDraft:
        """Generate a change order from one or more drift alerts.

        Typically called when a partner reviews a CRITICAL unscoped work
        alert and decides to formalize it with the client.
        """
        # Collect all unscoped time entries referenced by the alerts
        related_entry_ids = set()
        for alert in alerts:
            related_entry_ids.update(alert.related_entry_ids)

        unscoped_entries = [
            e for e in engagement.time_entries
            if e.id in related_entry_ids or (not e.is_scoped)
        ]

        # Group entries into logical scope additions
        additions = self._group_into_additions(
            unscoped_entries, engagement
        )

        return self._build_draft(
            engagement, additions, alerts, additional_context
        )

    def generate_for_new_request(
        self,
        engagement: Engagement,
        request_name: str,
        request_description: str,
        estimated_hours: float,
        assigned_to: list[str],
        include_existing_unscoped: bool = True,
    ) -> ChangeOrderDraft:
        """Generate a change order for a new client request.

        Called when the client asks for something new and the partner
        wants to formalize it upfront instead of waiting for drift detection.
        """
        blended_rate = self._blended_rate(engagement)

        additions = [
            ScopeAddition(
                name=request_name,
                description=request_description,
                hours_already_spent=0,
                hours_estimated_remaining=estimated_hours,
                total_hours=estimated_hours,
                assigned_to=assigned_to,
                hourly_rate=blended_rate,
                total_cost=estimated_hours * blended_rate,
                source="client_request",
            )
        ]

        # Optionally bundle in any existing unscoped work
        if include_existing_unscoped:
            unscoped = [e for e in engagement.time_entries if not e.is_scoped]
            if unscoped:
                existing = self._group_into_additions(unscoped, engagement)
                additions.extend(existing)

        return self._build_draft(engagement, additions, [], "")

    # -- Grouping Logic -----------------------------------------------------

    def _group_into_additions(
        self,
        entries: list[TimeEntry],
        engagement: Engagement,
    ) -> list[ScopeAddition]:
        """Group related time entries into logical scope additions.

        Uses description similarity to cluster entries. In practice,
        unscoped work on a deal tends to cluster around 2-3 themes
        (e.g., "lease assignment issues," "earnout negotiation,"
        "environmental concerns").
        """
        blended_rate = self._blended_rate(engagement)

        # Group by keyword themes
        themes: dict[str, dict] = {}

        for entry in entries:
            theme_key = self._extract_theme(entry.description)

            if theme_key not in themes:
                themes[theme_key] = {
                    "entries": [],
                    "hours": 0.0,
                    "members": set(),
                    "descriptions": [],
                }

            themes[theme_key]["entries"].append(entry)
            themes[theme_key]["hours"] += entry.hours
            themes[theme_key]["members"].add(entry.team_member)
            themes[theme_key]["descriptions"].append(entry.description)

        additions = []
        for theme_key, data in themes.items():
            # Build a readable name from the theme
            name = self._theme_to_name(theme_key)

            # Use the longest description as the basis
            best_desc = max(data["descriptions"], key=len)

            # Estimate remaining hours (assume 30% more work needed
            # to properly complete what was started ad-hoc)
            remaining_estimate = data["hours"] * 0.3

            additions.append(ScopeAddition(
                name=name,
                description=best_desc,
                hours_already_spent=data["hours"],
                hours_estimated_remaining=round(remaining_estimate, 1),
                total_hours=round(data["hours"] + remaining_estimate, 1),
                assigned_to=list(data["members"]),
                hourly_rate=blended_rate,
                total_cost=round((data["hours"] + remaining_estimate) * blended_rate, 2),
                source="time_entries",
                related_entry_ids=[e.id for e in data["entries"]],
            ))

        return sorted(additions, key=lambda a: -a.total_hours)

    def _extract_theme(self, description: str) -> str:
        """Extract a theme key from a time entry description.

        Simple keyword extraction. Groups entries that share key terms
        like "lease assignment," "earnout," "environmental."
        """
        desc_lower = description.lower()

        # Check for common legal work themes
        theme_keywords = [
            ("lease assignment", "lease_assignment"),
            ("lease", "lease_review"),
            ("earnout", "earnout"),
            ("side letter", "side_letter"),
            ("environmental", "environmental"),
            ("indemnity", "indemnity"),
            ("lender", "lender_coordination"),
            ("financing", "financing"),
            ("title", "title_review"),
            ("survey", "survey_review"),
            ("zoning", "zoning"),
            ("tenant", "tenant_matters"),
            ("landlord", "landlord_matters"),
            ("escrow", "escrow"),
            ("insurance", "insurance"),
        ]

        for keyword, theme in theme_keywords:
            if keyword in desc_lower:
                return theme

        # Fallback: first meaningful words
        words = [w for w in desc_lower.split() if len(w) > 3]
        return "_".join(words[:3]) if words else "general"

    def _theme_to_name(self, theme_key: str) -> str:
        """Convert a theme key to a readable scope addition name."""
        name_map = {
            "lease_assignment": "Lease Assignment Review and Negotiation",
            "lease_review": "Additional Lease Review",
            "earnout": "Earnout Side Letter Drafting",
            "side_letter": "Side Letter Preparation",
            "environmental": "Environmental Indemnity Expansion",
            "indemnity": "Indemnity Provisions Review",
            "lender_coordination": "Lender Coordination and Calls",
            "financing": "Financing Documentation Review",
            "title_review": "Additional Title Review",
            "survey_review": "Survey Review and Objections",
            "zoning": "Zoning Analysis",
            "tenant_matters": "Tenant-Related Matters",
            "landlord_matters": "Landlord Negotiation Support",
            "escrow": "Escrow Arrangement Review",
            "insurance": "Insurance Review",
        }
        return name_map.get(theme_key, theme_key.replace("_", " ").title())

    # -- Document Generation ------------------------------------------------

    def _build_draft(
        self,
        engagement: Engagement,
        additions: list[ScopeAddition],
        alerts: list[DriftAlert],
        additional_context: str,
    ) -> ChangeOrderDraft:
        """Build the complete change order draft."""
        total_hours = sum(a.total_hours for a in additions)
        total_cost = sum(a.total_cost for a in additions)

        # Build original scope summary
        original_deliverables = [
            d for d in engagement.deliverables if d.is_original_scope
        ]
        scope_summary = "; ".join(d.name for d in original_deliverables)

        # Build reason for change
        if alerts:
            reasons = set()
            for alert in alerts:
                if alert.drift_type == DriftType.UNSCOPED_WORK:
                    reasons.add("additional client requests outside original scope")
                elif alert.drift_type == DriftType.BUDGET_OVERRUN:
                    reasons.add("expanded scope on existing deliverables")
            reason = "Scope change due to " + " and ".join(reasons) + "."
        else:
            reason = additional_context or "Client-requested scope expansion."

        # Generate document text
        document = self._format_document(
            engagement, additions, total_hours, total_cost, reason
        )

        return ChangeOrderDraft(
            engagement_id=engagement.id,
            client_name=engagement.client_name,
            matter_name=engagement.matter_name,
            generated_at=datetime.now(),
            generated_by="system",
            original_scope_summary=scope_summary,
            reason_for_change=reason,
            scope_additions=additions,
            total_additional_hours=round(total_hours, 1),
            total_additional_cost=round(total_cost, 2),
            original_fee=engagement.fixed_fee,
            proposed_revised_fee=round(engagement.fixed_fee + total_cost, 2),
            fee_increase_pct=round(total_cost / engagement.fixed_fee * 100, 1),
            original_budgeted_hours=engagement.total_budgeted_hours,
            hours_consumed_to_date=round(engagement.total_actual_hours, 1),
            budget_consumed_pct=round(engagement.budget_consumed_pct, 1),
            triggered_by_alert_ids=[a.id for a in alerts],
            document_text=document,
        )

    def _format_document(
        self,
        engagement: Engagement,
        additions: list[ScopeAddition],
        total_hours: float,
        total_cost: float,
        reason: str,
    ) -> str:
        """Format the change order as a client-facing document.

        Intentionally plain text (not PDF/DOCX) because the firm would
        paste this into their engagement letter template. The tool
        generates the content; the firm handles the formatting.
        """
        lines = []
        lines.append("=" * 60)
        lines.append("ENGAGEMENT AMENDMENT / CHANGE ORDER")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"Date:        {date.today().strftime('%B %d, %Y')}")
        lines.append(f"Client:      {engagement.client_name}")
        lines.append(f"Matter:      {engagement.matter_name}")
        lines.append(f"Engagement:  {engagement.id}")
        lines.append(f"Partner:     {engagement.responsible_partner}")
        lines.append("")
        lines.append("-" * 60)
        lines.append("BACKGROUND")
        lines.append("-" * 60)
        lines.append("")

        original_dels = [d for d in engagement.deliverables if d.is_original_scope]
        lines.append(
            f"Our original engagement letter dated "
            f"{engagement.engagement_start.strftime('%B %d, %Y')} covered "
            f"the following scope of work:"
        )
        lines.append("")
        for i, d in enumerate(original_dels, 1):
            lines.append(f"  {i}. {d.name}")
            lines.append(f"     {d.description}")
        lines.append("")
        lines.append(
            f"The fixed fee for this scope was ${engagement.fixed_fee:,.0f}."
        )
        lines.append("")
        lines.append("-" * 60)
        lines.append("ADDITIONAL SCOPE")
        lines.append("-" * 60)
        lines.append("")
        lines.append(f"Reason: {reason}")
        lines.append("")
        lines.append(
            "During the course of this engagement, the following additional "
            "work items have been identified:"
        )
        lines.append("")

        for i, addition in enumerate(additions, 1):
            lines.append(f"  {i}. {addition.name}")
            lines.append(f"     {addition.description}")
            if addition.hours_already_spent > 0:
                lines.append(
                    f"     Hours completed: {addition.hours_already_spent:.1f}"
                )
            if addition.hours_estimated_remaining > 0:
                lines.append(
                    f"     Hours remaining: {addition.hours_estimated_remaining:.1f}"
                )
            lines.append(f"     Total hours: {addition.total_hours:.1f}")
            lines.append(f"     Cost: ${addition.total_cost:,.0f}")
            lines.append("")

        lines.append("-" * 60)
        lines.append("FEE ADJUSTMENT")
        lines.append("-" * 60)
        lines.append("")
        lines.append(f"  Original fixed fee:     ${engagement.fixed_fee:>10,.0f}")
        lines.append(f"  Additional scope:       ${total_cost:>10,.0f}")
        lines.append(f"                          {'─' * 10}")
        lines.append(f"  Revised fixed fee:      ${engagement.fixed_fee + total_cost:>10,.0f}")
        lines.append("")
        lines.append(
            f"This represents a {total_cost / engagement.fixed_fee * 100:.1f}% "
            f"increase over the original engagement fee."
        )
        lines.append("")
        lines.append("-" * 60)
        lines.append("AUTHORIZATION")
        lines.append("-" * 60)
        lines.append("")
        lines.append(
            "Please sign below to authorize the additional scope and "
            "revised fee. Work on the additional items will continue "
            "upon receipt of this signed amendment."
        )
        lines.append("")
        lines.append("")
        lines.append(f"{'_' * 40}          {'_' * 20}")
        lines.append(f"Client Signature                  Date")
        lines.append("")
        lines.append(f"{'_' * 40}          {'_' * 20}")
        lines.append(f"{engagement.responsible_partner:<40}  Date")
        lines.append(f"{'[Firm Name]'}")
        lines.append("")

        return "\n".join(lines)

    # -- Helpers ------------------------------------------------------------

    def _blended_rate(self, engagement: Engagement) -> float:
        if not engagement.team:
            return 300
        total_rate = sum(m.hourly_rate * m.budgeted_hours for m in engagement.team)
        total_hours = sum(m.budgeted_hours for m in engagement.team)
        return total_rate / total_hours if total_hours > 0 else 300

    # -- Create Formal Change Order -----------------------------------------

    def finalize_change_order(
        self,
        draft: ChangeOrderDraft,
        engagement: Engagement,
        approved_by_partner: str,
    ) -> ChangeOrder:
        """Convert a draft into a formal ChangeOrder on the engagement.

        Called after the partner reviews and approves the draft.
        Creates the ChangeOrder record and adds new deliverables
        to the engagement.
        """
        self._change_order_counter += 1
        co_id = f"CO-{self._change_order_counter:03d}"

        change_order = ChangeOrder(
            id=co_id,
            engagement_id=engagement.id,
            created_at=datetime.now(),
            created_by=approved_by_partner,
            status="draft",
            new_deliverables=[
                {
                    "name": a.name,
                    "description": a.description,
                    "hours": a.total_hours,
                    "cost": a.total_cost,
                }
                for a in draft.scope_additions
            ],
            additional_hours=draft.total_additional_hours,
            additional_cost=draft.total_additional_cost,
            reason=draft.reason_for_change,
            client_request_description=draft.reason_for_change,
            original_fee=draft.original_fee,
            revised_fee=draft.proposed_revised_fee,
        )

        # Add new deliverables to the engagement
        for addition in draft.scope_additions:
            new_del = Deliverable(
                id=f"del_co_{co_id}_{len(engagement.deliverables) + 1}",
                name=addition.name,
                description=addition.description,
                budgeted_hours=addition.total_hours,
                assigned_to=addition.assigned_to,
                planned_start=date.today(),
                planned_end=engagement.planned_close,
                status=DeliverableStatus.IN_PROGRESS if addition.hours_already_spent > 0 else DeliverableStatus.NOT_STARTED,
                actual_hours=addition.hours_already_spent,
                is_original_scope=False,
                change_order_id=co_id,
            )
            engagement.deliverables.append(new_del)

        engagement.change_orders.append(change_order)
        engagement.total_budgeted_hours += draft.total_additional_hours

        return change_order


# ---------------------------------------------------------------------------
# Usage Example
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from engagement_tracker import (
        Engagement, EngagementStatus, PracticeArea,
        Deliverable, DeliverableStatus, TeamMember, TeamRole, TimeEntry,
    )
    from drift_detector import DriftDetector

    today = date.today()

    # Build engagement with unscoped work
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
                id="del_001", name="Purchase Agreement",
                description="Draft and negotiate PSA",
                budgeted_hours=28, assigned_to=["Rachel Torres", "Kevin Liu"],
                planned_start=today - timedelta(weeks=5),
                planned_end=today - timedelta(weeks=2),
                status=DeliverableStatus.DELIVERED, actual_hours=31.5,
            ),
            Deliverable(
                id="del_002", name="Due Diligence Review",
                description="Title, survey, environmental, leases",
                budgeted_hours=32, assigned_to=["Kevin Liu", "Amy Chen"],
                planned_start=today - timedelta(weeks=4),
                planned_end=today + timedelta(weeks=1),
                status=DeliverableStatus.IN_PROGRESS, actual_hours=29,
            ),
            Deliverable(
                id="del_003", name="Closing Documents",
                description="Deed, bill of sale, assignments",
                budgeted_hours=18, assigned_to=["Rachel Torres"],
                planned_start=today - timedelta(weeks=1),
                planned_end=today + timedelta(weeks=2),
                status=DeliverableStatus.IN_PROGRESS, actual_hours=6,
            ),
        ],
        team=[
            TeamMember("David Park", TeamRole.PARTNER, 550, 8),
            TeamMember("Rachel Torres", TeamRole.SENIOR_ASSOCIATE, 350, 38),
            TeamMember("Kevin Liu", TeamRole.JUNIOR_ASSOCIATE, 225, 40),
            TeamMember("Amy Chen", TeamRole.PARALEGAL, 125, 9),
        ],
    )

    # Log unscoped time entries
    unscoped = [
        TimeEntry("t004", eng.id, "Kevin Liu", today - timedelta(days=3), 3.5,
                  "Client call re: lease assignment for Tenant B - landlord pushback on consent", None),
        TimeEntry("t005", eng.id, "Rachel Torres", today - timedelta(days=2), 4.0,
                  "Drafted side letter re: earnout on parking structure", None),
        TimeEntry("t006", eng.id, "Kevin Liu", today - timedelta(days=1), 2.0,
                  "Research on environmental indemnity - client wants expanded coverage", None),
        TimeEntry("t007", eng.id, "Kevin Liu", today, 1.5,
                  "Follow-up call with landlord's counsel re: lease assignment consent", None),
        TimeEntry("t008", eng.id, "Rachel Torres", today, 3.0,
                  "Revised earnout side letter per client comments", None),
    ]

    for entry in unscoped:
        eng.log_time(entry)

    # Detect drift
    detector = DriftDetector()
    alerts = detector.scan_engagement(eng)

    # Generate change order from the unscoped work alert
    unscoped_alert = [a for a in alerts if a.drift_type.value == "unscoped_work"]

    generator = ChangeOrderGenerator()
    draft = generator.generate_from_alerts(eng, unscoped_alert)

    print("=== CHANGE ORDER DRAFT ===\n")
    print(f"Scope additions: {len(draft.scope_additions)}")
    for a in draft.scope_additions:
        print(f"  - {a.name}: {a.total_hours}hrs (${a.total_cost:,.0f})")
        print(f"    Already spent: {a.hours_already_spent}hrs | Remaining: {a.hours_estimated_remaining}hrs")

    print(f"\nFee impact:")
    print(f"  Original: ${draft.original_fee:,.0f}")
    print(f"  Additional: ${draft.total_additional_cost:,.0f}")
    print(f"  Revised: ${draft.proposed_revised_fee:,.0f}")
    print(f"  Increase: {draft.fee_increase_pct}%")

    print(f"\n{'=' * 60}")
    print("CLIENT-FACING DOCUMENT")
    print(f"{'=' * 60}\n")
    print(draft.document_text)
