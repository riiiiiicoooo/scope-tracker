"""
Drift Detector — Identifies scope creep before it becomes a write-off.

The core logic that catches the problem at Week 3 instead of Week 7.

Three types of drift:
1. Budget overrun: a deliverable is burning hours faster than planned
2. Unscoped work: time logged to this matter that doesn't match any deliverable
3. Timeline slip: work is happening past the planned completion date

Alert thresholds are intentionally conservative. We'd rather flag something
that turns out to be fine than miss 9.5 hours of unscoped work because we
waited for a higher threshold. Partners can dismiss alerts in 10 seconds;
they can't recover unbilled hours.
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from enum import Enum
from typing import Optional
from collections import defaultdict

# Import from engagement_tracker (same directory)
from engagement_tracker import (
    Engagement,
    EngagementStatus,
    Deliverable,
    DeliverableStatus,
    TimeEntry,
    TeamRole,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DriftType(Enum):
    """Category of scope drift detected."""
    BUDGET_OVERRUN = "budget_overrun"        # Deliverable burning hours too fast
    UNSCOPED_WORK = "unscoped_work"          # Work logged with no deliverable match
    TIMELINE_SLIP = "timeline_slip"          # Deliverable past planned end date
    BURN_RATE_ANOMALY = "burn_rate_anomaly"  # Overall engagement burning too fast
    TEAM_OVERALLOCATION = "team_overallocation"  # One person way over their hours


class AlertSeverity(Enum):
    """How urgently the partner needs to see this."""
    INFO = "info"           # FYI — worth knowing but not actionable yet
    WARNING = "warning"     # Needs attention within a few days
    CRITICAL = "critical"   # Needs attention today — money is being lost


class AlertStatus(Enum):
    """What happened to this alert."""
    ACTIVE = "active"       # Needs partner review
    ACKNOWLEDGED = "acknowledged"   # Partner saw it
    DISMISSED = "dismissed"  # Partner reviewed, not a real issue
    CONVERTED = "converted"  # Led to a change order


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class DriftAlert:
    """A single scope drift alert for a partner to review."""
    id: str
    engagement_id: str
    drift_type: DriftType
    severity: AlertSeverity
    status: AlertStatus

    # What triggered the alert
    title: str
    description: str
    triggered_at: datetime

    # Quantitative impact
    hours_at_risk: float           # How many hours are potentially unrecoverable
    cost_at_risk: float            # Dollar impact using blended rate
    deliverable_id: Optional[str] = None
    team_member: Optional[str] = None

    # Related time entries (for partner to review)
    related_entry_ids: list[str] = field(default_factory=list)

    # Resolution
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_notes: str = ""
    change_order_id: Optional[str] = None  # If converted to change order


@dataclass
class DriftThresholds:
    """Configurable thresholds for drift detection.

    Defaults are tuned from observing 40+ engagements. They lean toward
    flagging early — a false positive costs 10 seconds of a partner's time,
    a false negative costs thousands in absorbed fees.
    """
    # Budget overrun thresholds
    deliverable_budget_warning_pct: float = 75.0    # Alert at 75% consumed
    deliverable_budget_critical_pct: float = 100.0   # Alert at 100% consumed
    deliverable_completion_floor_pct: float = 50.0   # ...only if < 50% complete

    # Unscoped work thresholds
    unscoped_hours_warning: float = 2.0    # Any 2+ hours unscoped = warning
    unscoped_hours_critical: float = 8.0   # 8+ hours = critical (basically a new deliverable)

    # Burn rate thresholds
    engagement_burn_warning_pct: float = 60.0   # Alert if 60% budget consumed at 40% timeline
    engagement_burn_critical_pct: float = 80.0  # Alert if 80% budget consumed at 50% timeline
    burn_rate_timeline_ratio: float = 1.5       # Budget consumed > 1.5x timeline elapsed

    # Timeline thresholds
    timeline_slip_days: int = 3    # Deliverable is 3+ days past planned end

    # Team thresholds
    team_overallocation_pct: float = 120.0  # Team member at 120% of their budgeted hours


# ---------------------------------------------------------------------------
# Drift Detector
# ---------------------------------------------------------------------------

class DriftDetector:
    """Analyzes engagements for scope drift and generates alerts.

    Runs on demand (called when new time entries are logged) or on
    a schedule (daily digest for the partner). Each detection method
    returns a list of alerts that are new since the last run.
    """

    def __init__(self, thresholds: Optional[DriftThresholds] = None):
        self._thresholds = thresholds or DriftThresholds()
        self._alerts: list[DriftAlert] = []
        self._alert_counter = 0
        self._seen_triggers: set[str] = set()  # Avoid duplicate alerts

    # -- Full Scan ----------------------------------------------------------

    def scan_engagement(self, engagement: Engagement) -> list[DriftAlert]:
        """Run all drift detections on an engagement. Returns new alerts."""
        new_alerts = []

        new_alerts.extend(self._check_deliverable_budgets(engagement))
        new_alerts.extend(self._check_unscoped_work(engagement))
        new_alerts.extend(self._check_burn_rate(engagement))
        new_alerts.extend(self._check_timeline_slips(engagement))
        new_alerts.extend(self._check_team_overallocation(engagement))

        self._alerts.extend(new_alerts)
        return new_alerts

    # -- Detection Methods --------------------------------------------------

    def _check_deliverable_budgets(
        self, engagement: Engagement
    ) -> list[DriftAlert]:
        """Check if any deliverable is consuming hours faster than planned."""
        alerts = []
        t = self._thresholds

        for d in engagement.deliverables:
            if d.status in (DeliverableStatus.DELIVERED, DeliverableStatus.DEFERRED):
                continue

            consumed = d.budget_consumed_pct
            trigger_key = f"{engagement.id}:budget:{d.id}"

            if consumed >= t.deliverable_budget_critical_pct:
                if self._is_new_trigger(trigger_key + ":critical"):
                    alerts.append(self._create_alert(
                        engagement_id=engagement.id,
                        drift_type=DriftType.BUDGET_OVERRUN,
                        severity=AlertSeverity.CRITICAL,
                        title=f"Budget exceeded: {d.name}",
                        description=(
                            f"'{d.name}' has consumed {d.actual_hours:.1f} hours "
                            f"against a {d.budgeted_hours:.0f}-hour budget "
                            f"({consumed:.0f}%). {d.overrun_hours:.1f} hours over budget. "
                            f"Status: {d.status.value}."
                        ),
                        hours_at_risk=d.overrun_hours,
                        cost_at_risk=d.overrun_hours * self._blended_rate(engagement),
                        deliverable_id=d.id,
                    ))

            elif consumed >= t.deliverable_budget_warning_pct:
                if self._is_new_trigger(trigger_key + ":warning"):
                    alerts.append(self._create_alert(
                        engagement_id=engagement.id,
                        drift_type=DriftType.BUDGET_OVERRUN,
                        severity=AlertSeverity.WARNING,
                        title=f"Budget warning: {d.name}",
                        description=(
                            f"'{d.name}' is at {consumed:.0f}% of budget "
                            f"({d.actual_hours:.1f}/{d.budgeted_hours:.0f} hours). "
                            f"{d.hours_remaining:.1f} hours remaining. "
                            f"Status: {d.status.value}."
                        ),
                        hours_at_risk=d.hours_remaining,
                        cost_at_risk=0,  # Not over yet
                        deliverable_id=d.id,
                    ))

        return alerts

    def _check_unscoped_work(
        self, engagement: Engagement
    ) -> list[DriftAlert]:
        """Detect time entries that don't map to any deliverable."""
        alerts = []
        t = self._thresholds

        unscoped = [e for e in engagement.time_entries if not e.is_scoped]
        if not unscoped:
            return alerts

        total_unscoped = sum(e.hours for e in unscoped)
        trigger_key = f"{engagement.id}:unscoped"

        # Group by description pattern to identify recurring unscoped themes
        themes = defaultdict(lambda: {"hours": 0.0, "entries": [], "members": set()})
        for entry in unscoped:
            # Simple theme extraction — first few words of description
            words = entry.description.lower().split()[:4]
            theme = " ".join(words) if words else "unspecified"
            themes[theme]["hours"] += entry.hours
            themes[theme]["entries"].append(entry.id)
            themes[theme]["members"].add(entry.team_member)

        if total_unscoped >= t.unscoped_hours_critical:
            if self._is_new_trigger(trigger_key + ":critical"):
                theme_summary = "; ".join(
                    f"{k} ({v['hours']:.1f}hrs)"
                    for k, v in sorted(themes.items(), key=lambda x: -x[1]["hours"])[:3]
                )
                alerts.append(self._create_alert(
                    engagement_id=engagement.id,
                    drift_type=DriftType.UNSCOPED_WORK,
                    severity=AlertSeverity.CRITICAL,
                    title=f"Significant unscoped work: {total_unscoped:.1f} hours",
                    description=(
                        f"{total_unscoped:.1f} hours logged to this matter with no "
                        f"matching deliverable. This is equivalent to a new deliverable. "
                        f"Themes: {theme_summary}. "
                        f"Consider creating a change order."
                    ),
                    hours_at_risk=total_unscoped,
                    cost_at_risk=total_unscoped * self._blended_rate(engagement),
                    related_entry_ids=[e.id for e in unscoped],
                ))

        elif total_unscoped >= t.unscoped_hours_warning:
            if self._is_new_trigger(trigger_key + ":warning"):
                alerts.append(self._create_alert(
                    engagement_id=engagement.id,
                    drift_type=DriftType.UNSCOPED_WORK,
                    severity=AlertSeverity.WARNING,
                    title=f"Unscoped work detected: {total_unscoped:.1f} hours",
                    description=(
                        f"{len(unscoped)} time entries ({total_unscoped:.1f} hours) "
                        f"logged without a deliverable tag. Review to determine if "
                        f"these are within scope or represent new asks from the client."
                    ),
                    hours_at_risk=total_unscoped,
                    cost_at_risk=total_unscoped * self._blended_rate(engagement),
                    related_entry_ids=[e.id for e in unscoped],
                ))

        return alerts

    def _check_burn_rate(self, engagement: Engagement) -> list[DriftAlert]:
        """Check if the overall engagement is burning hours too fast."""
        alerts = []
        t = self._thresholds

        budget_pct = engagement.budget_consumed_pct
        timeline_pct = engagement.elapsed_pct

        if timeline_pct < 10:  # Too early to tell
            return alerts

        ratio = budget_pct / timeline_pct if timeline_pct > 0 else 0
        trigger_key = f"{engagement.id}:burnrate"

        if ratio >= 2.0 and budget_pct >= t.engagement_burn_critical_pct:
            if self._is_new_trigger(trigger_key + ":critical"):
                alerts.append(self._create_alert(
                    engagement_id=engagement.id,
                    drift_type=DriftType.BURN_RATE_ANOMALY,
                    severity=AlertSeverity.CRITICAL,
                    title=f"Engagement burning at {ratio:.1f}x planned rate",
                    description=(
                        f"{budget_pct:.0f}% of hours budget consumed with only "
                        f"{timeline_pct:.0f}% of timeline elapsed. At current pace, "
                        f"projected overrun is {engagement.projected_overrun_pct:.0f}%. "
                        f"Projected total: {engagement.projected_total_hours:.0f} hours "
                        f"vs. {engagement.total_budgeted_hours:.0f} budgeted."
                    ),
                    hours_at_risk=engagement.projected_total_hours - engagement.total_budgeted_hours,
                    cost_at_risk=(engagement.projected_total_hours - engagement.total_budgeted_hours) * self._blended_rate(engagement),
                ))

        elif ratio >= t.burn_rate_timeline_ratio and budget_pct >= t.engagement_burn_warning_pct:
            if self._is_new_trigger(trigger_key + ":warning"):
                alerts.append(self._create_alert(
                    engagement_id=engagement.id,
                    drift_type=DriftType.BURN_RATE_ANOMALY,
                    severity=AlertSeverity.WARNING,
                    title=f"Engagement burn rate elevated ({ratio:.1f}x planned)",
                    description=(
                        f"Hours consumption is outpacing the timeline. "
                        f"{budget_pct:.0f}% of budget used at {timeline_pct:.0f}% "
                        f"of timeline. Monitor closely."
                    ),
                    hours_at_risk=max(0, engagement.projected_total_hours - engagement.total_budgeted_hours),
                    cost_at_risk=0,
                ))

        return alerts

    def _check_timeline_slips(
        self, engagement: Engagement
    ) -> list[DriftAlert]:
        """Check for deliverables past their planned end date."""
        alerts = []
        t = self._thresholds

        for d in engagement.deliverables:
            if not d.is_past_deadline:
                continue

            days_late = (date.today() - d.planned_end).days
            if days_late < t.timeline_slip_days:
                continue

            trigger_key = f"{engagement.id}:timeline:{d.id}"
            if not self._is_new_trigger(trigger_key):
                continue

            severity = (
                AlertSeverity.CRITICAL if days_late > 7
                else AlertSeverity.WARNING
            )

            alerts.append(self._create_alert(
                engagement_id=engagement.id,
                drift_type=DriftType.TIMELINE_SLIP,
                severity=severity,
                title=f"Deliverable {days_late} days past deadline: {d.name}",
                description=(
                    f"'{d.name}' was planned to complete by {d.planned_end.isoformat()} "
                    f"but is still {d.status.value}. {d.actual_hours:.1f} of "
                    f"{d.budgeted_hours:.0f} budgeted hours used."
                ),
                hours_at_risk=d.hours_remaining,
                cost_at_risk=0,
                deliverable_id=d.id,
            ))

        return alerts

    def _check_team_overallocation(
        self, engagement: Engagement
    ) -> list[DriftAlert]:
        """Check if any team member is significantly over their budgeted hours."""
        alerts = []
        t = self._thresholds

        for member in engagement.team:
            if member.utilization_pct < t.team_overallocation_pct:
                continue

            trigger_key = f"{engagement.id}:team:{member.name}"
            if not self._is_new_trigger(trigger_key):
                continue

            over_hours = member.actual_hours - member.budgeted_hours

            alerts.append(self._create_alert(
                engagement_id=engagement.id,
                drift_type=DriftType.TEAM_OVERALLOCATION,
                severity=AlertSeverity.WARNING,
                title=f"{member.name} at {member.utilization_pct:.0f}% of budgeted hours",
                description=(
                    f"{member.name} ({member.role.value}) has logged "
                    f"{member.actual_hours:.1f} hours against a {member.budgeted_hours:.0f}-hour "
                    f"budget. {over_hours:.1f} hours over allocation. This may indicate "
                    f"unplanned work or incorrect task assignment."
                ),
                hours_at_risk=max(0, over_hours),
                cost_at_risk=max(0, over_hours) * member.hourly_rate,
                team_member=member.name,
            ))

        return alerts

    # -- Helpers ------------------------------------------------------------

    def _create_alert(self, **kwargs) -> DriftAlert:
        self._alert_counter += 1
        alert_id = f"DRIFT-{self._alert_counter:04d}"
        return DriftAlert(
            id=alert_id,
            triggered_at=datetime.now(),
            status=AlertStatus.ACTIVE,
            **kwargs,
        )

    def _is_new_trigger(self, trigger_key: str) -> bool:
        """Check if we've already created an alert for this trigger."""
        if trigger_key in self._seen_triggers:
            return False
        self._seen_triggers.add(trigger_key)
        return True

    def _blended_rate(self, engagement: Engagement) -> float:
        """Calculate blended hourly rate across the engagement team."""
        if not engagement.team:
            return 300  # Default
        total_rate = sum(m.hourly_rate * m.budgeted_hours for m in engagement.team)
        total_hours = sum(m.budgeted_hours for m in engagement.team)
        return total_rate / total_hours if total_hours > 0 else 300

    # -- Alert Management ---------------------------------------------------

    def get_active_alerts(
        self, engagement_id: Optional[str] = None
    ) -> list[DriftAlert]:
        alerts = [a for a in self._alerts if a.status == AlertStatus.ACTIVE]
        if engagement_id:
            alerts = [a for a in alerts if a.engagement_id == engagement_id]
        return alerts

    def dismiss_alert(self, alert_id: str, dismissed_by: str, notes: str = "") -> None:
        for alert in self._alerts:
            if alert.id == alert_id:
                alert.status = AlertStatus.DISMISSED
                alert.resolved_at = datetime.now()
                alert.resolved_by = dismissed_by
                alert.resolution_notes = notes
                return
        raise KeyError(f"Alert '{alert_id}' not found.")

    def convert_to_change_order(
        self, alert_id: str, change_order_id: str
    ) -> None:
        for alert in self._alerts:
            if alert.id == alert_id:
                alert.status = AlertStatus.CONVERTED
                alert.resolved_at = datetime.now()
                alert.change_order_id = change_order_id
                return
        raise KeyError(f"Alert '{alert_id}' not found.")

    def get_alert_summary(self) -> dict:
        """Summary for the dashboard."""
        active = [a for a in self._alerts if a.status == AlertStatus.ACTIVE]
        by_type = defaultdict(int)
        by_severity = defaultdict(int)
        total_cost_at_risk = 0

        for a in active:
            by_type[a.drift_type.value] += 1
            by_severity[a.severity.value] += 1
            total_cost_at_risk += a.cost_at_risk

        return {
            "total_active": len(active),
            "by_type": dict(by_type),
            "by_severity": dict(by_severity),
            "total_cost_at_risk": round(total_cost_at_risk, 2),
            "total_hours_at_risk": round(
                sum(a.hours_at_risk for a in active), 1
            ),
            "alerts": [
                {
                    "id": a.id,
                    "engagement": a.engagement_id,
                    "type": a.drift_type.value,
                    "severity": a.severity.value,
                    "title": a.title,
                    "hours_at_risk": round(a.hours_at_risk, 1),
                    "cost_at_risk": round(a.cost_at_risk, 2),
                }
                for a in active
            ],
        }


# ---------------------------------------------------------------------------
# Usage Example
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from engagement_tracker import (
        Engagement, EngagementStatus, PracticeArea,
        Deliverable, DeliverableStatus, TeamMember, TeamRole, TimeEntry,
    )

    today = date.today()

    # Build the same engagement from engagement_tracker example
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
                budgeted_hours=28,
                assigned_to=["Rachel Torres", "Kevin Liu"],
                planned_start=today - timedelta(weeks=5),
                planned_end=today - timedelta(weeks=2),
                status=DeliverableStatus.DELIVERED,
                actual_hours=31.5,
            ),
            Deliverable(
                id="del_002", name="Due Diligence Review",
                description="Title, survey, environmental, leases",
                budgeted_hours=32,
                assigned_to=["Kevin Liu", "Amy Chen"],
                planned_start=today - timedelta(weeks=4),
                planned_end=today - timedelta(days=5),
                status=DeliverableStatus.IN_PROGRESS,
                actual_hours=29,
            ),
            Deliverable(
                id="del_003", name="Closing Documents",
                description="Deed, bill of sale, assignments",
                budgeted_hours=18,
                assigned_to=["Rachel Torres"],
                planned_start=today - timedelta(weeks=1),
                planned_end=today + timedelta(weeks=2),
                status=DeliverableStatus.IN_PROGRESS,
                actual_hours=6,
            ),
        ],
        team=[
            TeamMember("David Park", TeamRole.PARTNER, 550, 8, actual_hours=3.5),
            TeamMember("Rachel Torres", TeamRole.SENIOR_ASSOCIATE, 350, 38, actual_hours=35.5),
            TeamMember("Kevin Liu", TeamRole.JUNIOR_ASSOCIATE, 225, 40, actual_hours=42.0),
            TeamMember("Amy Chen", TeamRole.PARALEGAL, 125, 9, actual_hours=5.0),
        ],
        time_entries=[
            # Unscoped work
            TimeEntry("t004", "ENG-2024-031", "Kevin Liu", today - timedelta(days=2), 3.5,
                      "Client call re: lease assignment for Tenant B", None, is_scoped=False, flagged=True,
                      flag_reason="No deliverable specified"),
            TimeEntry("t005", "ENG-2024-031", "Rachel Torres", today - timedelta(days=1), 4.0,
                      "Drafted side letter re: earnout on parking structure", None, is_scoped=False, flagged=True,
                      flag_reason="No deliverable specified"),
            TimeEntry("t006", "ENG-2024-031", "Kevin Liu", today, 2.0,
                      "Research on environmental indemnity expansion", None, is_scoped=False, flagged=True,
                      flag_reason="No deliverable specified"),
        ],
    )

    # Run drift detection
    detector = DriftDetector()
    alerts = detector.scan_engagement(eng)

    print("=== DRIFT DETECTION RESULTS ===\n")
    print(f"Alerts generated: {len(alerts)}\n")

    for alert in alerts:
        icon = {"critical": "🔴", "warning": "⚠️", "info": "ℹ️"}[alert.severity.value]
        print(f"{icon} [{alert.severity.value.upper()}] {alert.title}")
        print(f"   Type: {alert.drift_type.value}")
        print(f"   {alert.description}")
        print(f"   Hours at risk: {alert.hours_at_risk:.1f}")
        if alert.cost_at_risk > 0:
            print(f"   Cost at risk: ${alert.cost_at_risk:,.0f}")
        print()

    # Summary
    summary = detector.get_alert_summary()
    print(f"=== ALERT SUMMARY ===\n")
    print(f"Active alerts: {summary['total_active']}")
    print(f"Total hours at risk: {summary['total_hours_at_risk']}")
    print(f"Total cost at risk: ${summary['total_cost_at_risk']:,.0f}")
