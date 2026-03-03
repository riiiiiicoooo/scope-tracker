/**
 * Engagement Scope Tracker — Dashboard
 *
 * Partner-facing view of all active engagements, budget health,
 * drift alerts, and change order history.
 *
 * Designed for a 20-person law firm. Partners glance at this on
 * Monday morning (or in the email digest we didn't build yet)
 * to see which deals need attention.
 *
 * Built with synthetic data for portfolio demonstration.
 */

import { useState } from "react";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

// ============================================================================
// SYNTHETIC DATA
// ============================================================================

const ENGAGEMENTS = [
  {
    id: "ENG-2024-031",
    client: "Meridian Properties LLC",
    matter: "Acquisition of 450 Commerce Street",
    type: "Commercial Real Estate",
    partner: "David Park",
    status: "active",
    fixedFee: 35000,
    budgetedHours: 95,
    actualHours: 86,
    scopedHours: 72.5,
    unscopedHours: 13.5,
    budgetPct: 90.5,
    elapsedPct: 62.5,
    projectedOverrun: 34,
    margin: -2820,
    marginPct: -8.1,
    daysRemaining: 21,
    deliverables: { total: 4, completed: 2, overBudget: 2 },
    changeOrders: { count: 1, value: 5331, status: "draft" },
    alerts: 3,
    alertSeverity: "critical",
    burnData: [
      { week: "W1", budgeted: 12, actual: 11 },
      { week: "W2", budgeted: 24, actual: 26 },
      { week: "W3", budgeted: 36, actual: 42 },
      { week: "W4", budgeted: 48, actual: 58 },
      { week: "W5", budgeted: 60, actual: 74 },
      { week: "W6", budgeted: 72, actual: 86 },
      { week: "W7", budgeted: 84, actual: null },
      { week: "W8", budgeted: 95, actual: null },
    ],
  },
  {
    id: "ENG-2024-028",
    client: "Clearwater Capital Partners",
    matter: "Acquisition of DataFlow Inc.",
    type: "M&A — Buy Side",
    partner: "Sarah Mitchell",
    status: "active",
    fixedFee: 85000,
    budgetedHours: 210,
    actualHours: 118,
    scopedHours: 115,
    unscopedHours: 3,
    budgetPct: 56.2,
    elapsedPct: 55,
    projectedOverrun: 2,
    margin: 33200,
    marginPct: 39.1,
    daysRemaining: 31,
    deliverables: { total: 6, completed: 3, overBudget: 0 },
    changeOrders: { count: 0, value: 0, status: null },
    alerts: 0,
    alertSeverity: null,
    burnData: [
      { week: "W1", budgeted: 26, actual: 24 },
      { week: "W2", budgeted: 52, actual: 48 },
      { week: "W3", budgeted: 78, actual: 72 },
      { week: "W4", budgeted: 105, actual: 98 },
      { week: "W5", budgeted: 131, actual: 118 },
      { week: "W6", budgeted: 157, actual: null },
      { week: "W7", budgeted: 184, actual: null },
      { week: "W8", budgeted: 210, actual: null },
    ],
  },
  {
    id: "ENG-2024-033",
    client: "Northbridge Holdings",
    matter: "Sale of Industrial Portfolio (6 properties)",
    type: "Commercial Real Estate",
    partner: "David Park",
    status: "active",
    fixedFee: 52000,
    budgetedHours: 140,
    actualHours: 48,
    scopedHours: 41,
    unscopedHours: 7,
    budgetPct: 34.3,
    elapsedPct: 25,
    projectedOverrun: 22,
    margin: 32400,
    marginPct: 62.3,
    daysRemaining: 45,
    deliverables: { total: 5, completed: 1, overBudget: 1 },
    changeOrders: { count: 0, value: 0, status: null },
    alerts: 1,
    alertSeverity: "warning",
    burnData: [
      { week: "W1", budgeted: 18, actual: 16 },
      { week: "W2", budgeted: 35, actual: 34 },
      { week: "W3", budgeted: 53, actual: 48 },
      { week: "W4", budgeted: 70, actual: null },
    ],
  },
  {
    id: "ENG-2024-029",
    client: "Apex Ventures",
    matter: "Series B Preferred Stock Purchase",
    type: "General Corporate",
    partner: "Sarah Mitchell",
    status: "closing",
    fixedFee: 18000,
    budgetedHours: 52,
    actualHours: 49,
    scopedHours: 49,
    unscopedHours: 0,
    budgetPct: 94.2,
    elapsedPct: 90,
    projectedOverrun: 5,
    margin: 2850,
    marginPct: 15.8,
    daysRemaining: 5,
    deliverables: { total: 3, completed: 2, overBudget: 1 },
    changeOrders: { count: 0, value: 0, status: null },
    alerts: 0,
    alertSeverity: null,
    burnData: [
      { week: "W1", budgeted: 13, actual: 12 },
      { week: "W2", budgeted: 26, actual: 28 },
      { week: "W3", budgeted: 39, actual: 41 },
      { week: "W4", budgeted: 52, actual: 49 },
    ],
  },
];

const ALERTS = [
  {
    id: "DRIFT-0001",
    engagement: "ENG-2024-031",
    client: "Meridian Properties",
    type: "unscoped_work",
    severity: "critical",
    title: "Significant unscoped work: 13.5 hours",
    description: "Earnout side letter (7.0hrs), lease assignment review (5.0hrs), environmental indemnity (2.0hrs). Consider creating a change order.",
    hoursAtRisk: 13.5,
    costAtRisk: 3956,
    time: "2h ago",
  },
  {
    id: "DRIFT-0002",
    engagement: "ENG-2024-031",
    client: "Meridian Properties",
    type: "budget_overrun",
    severity: "critical",
    title: "Budget exceeded: Purchase Agreement",
    description: "31.5 hours consumed against 28-hour budget (112%). 3.5 hours over budget. Status: delivered.",
    hoursAtRisk: 3.5,
    costAtRisk: 1025,
    time: "2h ago",
  },
  {
    id: "DRIFT-0003",
    engagement: "ENG-2024-031",
    client: "Meridian Properties",
    type: "burn_rate",
    severity: "warning",
    title: "Engagement burning at 1.4x planned rate",
    description: "90% of hours budget consumed with only 62% of timeline elapsed. Projected 34% overrun.",
    hoursAtRisk: 32.3,
    costAtRisk: 0,
    time: "2h ago",
  },
  {
    id: "DRIFT-0004",
    engagement: "ENG-2024-033",
    client: "Northbridge Holdings",
    type: "unscoped_work",
    severity: "warning",
    title: "Unscoped work detected: 7.0 hours",
    description: "3 time entries logged without deliverable tags. Buyer's counsel coordination calls and additional property inspections.",
    hoursAtRisk: 7.0,
    costAtRisk: 2051,
    time: "1d ago",
  },
];

const CHANGE_ORDERS = [
  {
    id: "CO-001",
    engagement: "ENG-2024-031",
    client: "Meridian Properties",
    status: "draft",
    items: 3,
    additionalHours: 18.2,
    additionalCost: 5331,
    generatedAt: "Today",
  },
];

// ============================================================================
// THEME
// ============================================================================

const C = {
  bg: "#fafaf9",
  surface: "#ffffff",
  surfaceMuted: "#f5f5f4",
  border: "#e7e5e4",
  borderStrong: "#d6d3d1",
  text: "#1c1917",
  textMuted: "#78716c",
  textDim: "#a8a29e",

  green: "#16a34a",
  greenBg: "#f0fdf4",
  greenBorder: "#bbf7d0",
  amber: "#d97706",
  amberBg: "#fffbeb",
  amberBorder: "#fde68a",
  red: "#dc2626",
  redBg: "#fef2f2",
  redBorder: "#fecaca",
  blue: "#2563eb",
  blueBg: "#eff6ff",

  budgetLine: "#2563eb",
  actualLine: "#dc2626",
  actualArea: "rgba(220, 38, 38, 0.06)",
};

// ============================================================================
// COMPONENTS
// ============================================================================

const HealthDot = ({ status }) => {
  const color = {
    healthy: C.green,
    warning: C.amber,
    critical: C.red,
    closing: C.blue,
  }[status] || C.textDim;

  return (
    <span
      style={{
        display: "inline-block",
        width: 8,
        height: 8,
        borderRadius: "50%",
        backgroundColor: color,
      }}
    />
  );
};

const Badge = ({ children, variant = "default" }) => {
  const styles = {
    critical: { bg: C.redBg, color: C.red, border: C.redBorder },
    warning: { bg: C.amberBg, color: C.amber, border: C.amberBorder },
    healthy: { bg: C.greenBg, color: C.green, border: C.greenBorder },
    default: { bg: C.surfaceMuted, color: C.textMuted, border: C.border },
    draft: { bg: C.blueBg, color: C.blue, border: "#bfdbfe" },
    closing: { bg: C.blueBg, color: C.blue, border: "#bfdbfe" },
    active: { bg: C.greenBg, color: C.green, border: C.greenBorder },
  };
  const s = styles[variant] || styles.default;

  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: 4,
        fontSize: 11,
        fontWeight: 600,
        backgroundColor: s.bg,
        color: s.color,
        border: `1px solid ${s.border}`,
        letterSpacing: "0.03em",
        textTransform: "uppercase",
        fontFamily: "'IBM Plex Mono', 'SF Mono', monospace",
      }}
    >
      {children}
    </span>
  );
};

const Card = ({ children, style = {}, onClick }) => (
  <div
    onClick={onClick}
    style={{
      backgroundColor: C.surface,
      border: `1px solid ${C.border}`,
      borderRadius: 8,
      padding: 20,
      cursor: onClick ? "pointer" : "default",
      transition: "border-color 0.15s",
      ...style,
    }}
  >
    {children}
  </div>
);

const SectionLabel = ({ children }) => (
  <h2
    style={{
      fontSize: 11,
      fontWeight: 600,
      color: C.textMuted,
      textTransform: "uppercase",
      letterSpacing: "0.08em",
      margin: "0 0 12px 0",
      fontFamily: "'IBM Plex Mono', 'SF Mono', monospace",
    }}
  >
    {children}
  </h2>
);

const Metric = ({ value, label, color }) => (
  <div style={{ textAlign: "center" }}>
    <div
      style={{
        fontSize: 26,
        fontWeight: 700,
        color: color || C.text,
        fontFamily: "'IBM Plex Mono', monospace",
        lineHeight: 1,
      }}
    >
      {value}
    </div>
    <div style={{ fontSize: 11, color: C.textDim, marginTop: 4 }}>{label}</div>
  </div>
);

const ChartTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div
      style={{
        backgroundColor: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: 6,
        padding: "8px 12px",
        fontSize: 12,
        fontFamily: "'IBM Plex Mono', monospace",
        boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
      }}
    >
      <div style={{ color: C.textMuted, marginBottom: 4 }}>{label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color }}>
          {p.name}: {p.value != null ? `${p.value}hrs` : "—"}
        </div>
      ))}
    </div>
  );
};

// ============================================================================
// MAIN DASHBOARD
// ============================================================================

export default function ScopeTrackerDashboard() {
  const [selectedEng, setSelectedEng] = useState(null);
  const [activeTab, setActiveTab] = useState("engagements");

  const totalFees = ENGAGEMENTS.reduce((s, e) => s + e.fixedFee, 0);
  const totalMargin = ENGAGEMENTS.reduce((s, e) => s + e.margin, 0);
  const totalUnscoped = ENGAGEMENTS.reduce((s, e) => s + e.unscopedHours, 0);
  const activeAlerts = ALERTS.length;
  const criticalAlerts = ALERTS.filter((a) => a.severity === "critical").length;

  const engHealth = (e) => {
    if (e.alertSeverity === "critical") return "critical";
    if (e.alertSeverity === "warning") return "warning";
    if (e.status === "closing") return "closing";
    return "healthy";
  };

  return (
    <div
      style={{
        backgroundColor: C.bg,
        color: C.text,
        minHeight: "100vh",
        fontFamily: "'Inter', -apple-system, sans-serif",
        fontSize: 14,
      }}
    >
      <link
        href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap"
        rel="stylesheet"
      />

      {/* Header */}
      <div
        style={{
          borderBottom: `1px solid ${C.border}`,
          padding: "16px 28px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          backgroundColor: C.surface,
        }}
      >
        <div>
          <h1 style={{ fontSize: 16, fontWeight: 700, margin: 0, letterSpacing: "-0.01em" }}>
            Scope Tracker
          </h1>
          <span style={{ fontSize: 11, color: C.textDim }}>
            4 active engagements — 2 partners
          </span>
        </div>
        {criticalAlerts > 0 && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "6px 12px",
              borderRadius: 6,
              backgroundColor: C.redBg,
              border: `1px solid ${C.redBorder}`,
              fontSize: 12,
              fontWeight: 600,
              color: C.red,
            }}
          >
            ● {criticalAlerts} critical alert{criticalAlerts !== 1 ? "s" : ""}
          </div>
        )}
      </div>

      {/* Tabs */}
      <div style={{ borderBottom: `1px solid ${C.border}`, padding: "0 28px", backgroundColor: C.surface }}>
        {["engagements", "alerts", "change orders"].map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: "10px 16px",
              fontSize: 13,
              fontWeight: activeTab === tab ? 600 : 400,
              color: activeTab === tab ? C.text : C.textMuted,
              background: "none",
              border: "none",
              borderBottom: activeTab === tab ? `2px solid ${C.text}` : "2px solid transparent",
              cursor: "pointer",
              fontFamily: "inherit",
              textTransform: "capitalize",
            }}
          >
            {tab}
            {tab === "alerts" && activeAlerts > 0 && (
              <span
                style={{
                  marginLeft: 6,
                  fontSize: 10,
                  fontWeight: 700,
                  padding: "1px 5px",
                  borderRadius: 8,
                  backgroundColor: C.red,
                  color: "#fff",
                }}
              >
                {activeAlerts}
              </span>
            )}
          </button>
        ))}
      </div>

      <div style={{ padding: 28 }}>
        {/* Top Metrics */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12, marginBottom: 24 }}>
          <Card><Metric value={ENGAGEMENTS.length} label="Active Engagements" /></Card>
          <Card><Metric value={`$${(totalFees / 1000).toFixed(0)}k`} label="Total Fixed Fees" /></Card>
          <Card>
            <Metric
              value={`${((totalMargin / totalFees) * 100).toFixed(0)}%`}
              label="Blended Margin"
              color={totalMargin > 0 ? C.green : C.red}
            />
          </Card>
          <Card>
            <Metric value={`${totalUnscoped.toFixed(0)}hrs`} label="Unscoped Hours" color={totalUnscoped > 10 ? C.red : C.amber} />
          </Card>
          <Card>
            <Metric
              value={`$${(CHANGE_ORDERS.reduce((s, co) => s + co.additionalCost, 0) / 1000).toFixed(1)}k`}
              label="Pending Change Orders"
              color={C.blue}
            />
          </Card>
        </div>

        {activeTab === "engagements" && (
          <EngagementsView
            engagements={ENGAGEMENTS}
            selectedEng={selectedEng}
            setSelectedEng={setSelectedEng}
            engHealth={engHealth}
          />
        )}
        {activeTab === "alerts" && <AlertsView />}
        {activeTab === "change orders" && <ChangeOrdersView />}
      </div>
    </div>
  );
}

// ============================================================================
// ENGAGEMENTS VIEW
// ============================================================================

function EngagementsView({ engagements, selectedEng, setSelectedEng, engHealth }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <SectionLabel>Engagement Health</SectionLabel>

      {engagements.map((eng) => {
        const isSelected = selectedEng === eng.id;
        const health = engHealth(eng);
        const budgetColor =
          eng.budgetPct > 90 ? C.red : eng.budgetPct > 70 ? C.amber : C.green;

        return (
          <Card
            key={eng.id}
            onClick={() => setSelectedEng(isSelected ? null : eng.id)}
            style={{
              borderColor: isSelected ? C.borderStrong : C.border,
            }}
          >
            {/* Header */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <HealthDot status={health} />
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>{eng.client}</div>
                  <div style={{ fontSize: 12, color: C.textMuted }}>{eng.matter}</div>
                </div>
              </div>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <Badge variant={eng.status}>{eng.status}</Badge>
                {eng.alerts > 0 && (
                  <Badge variant={eng.alertSeverity}>{eng.alerts} alert{eng.alerts !== 1 ? "s" : ""}</Badge>
                )}
              </div>
            </div>

            {/* Quick Metrics Row */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(6, 1fr)",
                gap: 16,
                padding: "12px 0",
                borderTop: `1px solid ${C.border}`,
              }}
            >
              <div>
                <div style={{ fontSize: 11, color: C.textDim }}>Fixed Fee</div>
                <div style={{ fontSize: 15, fontWeight: 600, fontFamily: "'IBM Plex Mono', monospace" }}>
                  ${(eng.fixedFee / 1000).toFixed(0)}k
                </div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: C.textDim }}>Budget Used</div>
                <div style={{ fontSize: 15, fontWeight: 600, fontFamily: "'IBM Plex Mono', monospace", color: budgetColor }}>
                  {eng.budgetPct}%
                </div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: C.textDim }}>Timeline</div>
                <div style={{ fontSize: 15, fontWeight: 600, fontFamily: "'IBM Plex Mono', monospace" }}>
                  {eng.elapsedPct}%
                </div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: C.textDim }}>Unscoped</div>
                <div style={{ fontSize: 15, fontWeight: 600, fontFamily: "'IBM Plex Mono', monospace", color: eng.unscopedHours > 5 ? C.red : eng.unscopedHours > 0 ? C.amber : C.green }}>
                  {eng.unscopedHours}hrs
                </div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: C.textDim }}>Margin</div>
                <div style={{ fontSize: 15, fontWeight: 600, fontFamily: "'IBM Plex Mono', monospace", color: eng.margin >= 0 ? C.green : C.red }}>
                  {eng.marginPct > 0 ? "+" : ""}{eng.marginPct}%
                </div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: C.textDim }}>Deliverables</div>
                <div style={{ fontSize: 15, fontWeight: 600, fontFamily: "'IBM Plex Mono', monospace" }}>
                  {eng.deliverables.completed}/{eng.deliverables.total}
                </div>
              </div>
            </div>

            {/* Budget Bar */}
            <div style={{ marginTop: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: C.textDim, marginBottom: 4 }}>
                <span>{eng.actualHours}/{eng.budgetedHours} hours</span>
                <span>{eng.daysRemaining} days remaining</span>
              </div>
              <div style={{ height: 6, backgroundColor: C.surfaceMuted, borderRadius: 3, overflow: "hidden", position: "relative" }}>
                {/* Timeline marker */}
                <div
                  style={{
                    position: "absolute",
                    left: `${eng.elapsedPct}%`,
                    top: 0,
                    bottom: 0,
                    width: 2,
                    backgroundColor: C.textDim,
                    zIndex: 2,
                  }}
                />
                {/* Budget fill */}
                <div
                  style={{
                    height: "100%",
                    width: `${Math.min(eng.budgetPct, 100)}%`,
                    backgroundColor: budgetColor,
                    borderRadius: 3,
                    transition: "width 0.4s ease",
                  }}
                />
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: C.textDim, marginTop: 2 }}>
                <span>Budget consumed ━ </span>
                <span>│ Timeline elapsed</span>
              </div>
            </div>

            {/* Expanded: Burn Chart */}
            {isSelected && (
              <div style={{ marginTop: 20, paddingTop: 16, borderTop: `1px solid ${C.border}` }}>
                <SectionLabel>Hours Burn-Down — Planned vs. Actual</SectionLabel>
                <div style={{ height: 200 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={eng.burnData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke={C.border} />
                      <XAxis dataKey="week" tick={{ fontSize: 11, fill: C.textDim }} tickLine={false} axisLine={{ stroke: C.border }} />
                      <YAxis tick={{ fontSize: 11, fill: C.textDim }} tickLine={false} axisLine={false} width={35} />
                      <Tooltip content={<ChartTooltip />} />
                      <Area
                        type="monotone"
                        dataKey="actual"
                        stroke={C.actualLine}
                        fill={C.actualArea}
                        strokeWidth={2}
                        name="Actual"
                        dot={{ r: 3, fill: C.actualLine }}
                        connectNulls={false}
                      />
                      <Area
                        type="monotone"
                        dataKey="budgeted"
                        stroke={C.budgetLine}
                        fill="none"
                        strokeWidth={1.5}
                        strokeDasharray="6 4"
                        name="Budgeted"
                        dot={false}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
                {eng.projectedOverrun > 5 && (
                  <div
                    style={{
                      marginTop: 12,
                      padding: "10px 14px",
                      borderRadius: 6,
                      backgroundColor: C.redBg,
                      border: `1px solid ${C.redBorder}`,
                      fontSize: 12,
                      color: C.red,
                    }}
                  >
                    At current burn rate, this engagement is projected to run <strong>{eng.projectedOverrun}% over budget</strong>.
                    {eng.unscopedHours > 5 &&
                      ` ${eng.unscopedHours} hours of unscoped work identified — change order recommended.`}
                  </div>
                )}
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}

// ============================================================================
// ALERTS VIEW
// ============================================================================

function AlertsView() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <SectionLabel>Active Drift Alerts</SectionLabel>

      {ALERTS.map((alert) => {
        const borderColor =
          alert.severity === "critical" ? C.redBorder : C.amberBorder;
        const bgColor =
          alert.severity === "critical" ? C.redBg : C.amberBg;

        return (
          <Card
            key={alert.id}
            style={{
              borderColor,
              backgroundColor: bgColor,
              borderLeftWidth: 3,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Badge variant={alert.severity}>{alert.severity}</Badge>
                <span style={{ fontWeight: 600, fontSize: 13 }}>{alert.title}</span>
              </div>
              <span style={{ fontSize: 11, color: C.textMuted, fontFamily: "'IBM Plex Mono', monospace" }}>
                {alert.time}
              </span>
            </div>

            <div style={{ fontSize: 12, color: C.textMuted, marginBottom: 10, lineHeight: 1.5 }}>
              {alert.description}
            </div>

            <div style={{ display: "flex", gap: 20, fontSize: 12 }}>
              <span>
                <span style={{ color: C.textDim }}>Engagement: </span>
                <span style={{ fontWeight: 500 }}>{alert.client}</span>
              </span>
              <span>
                <span style={{ color: C.textDim }}>Hours at risk: </span>
                <span style={{ fontWeight: 600, fontFamily: "'IBM Plex Mono', monospace", color: C.red }}>
                  {alert.hoursAtRisk}
                </span>
              </span>
              {alert.costAtRisk > 0 && (
                <span>
                  <span style={{ color: C.textDim }}>Cost at risk: </span>
                  <span style={{ fontWeight: 600, fontFamily: "'IBM Plex Mono', monospace", color: C.red }}>
                    ${alert.costAtRisk.toLocaleString()}
                  </span>
                </span>
              )}
            </div>

            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button
                style={{
                  padding: "6px 14px",
                  fontSize: 12,
                  fontWeight: 500,
                  borderRadius: 4,
                  border: "none",
                  backgroundColor: C.text,
                  color: C.surface,
                  cursor: "pointer",
                  fontFamily: "inherit",
                }}
              >
                Generate Change Order
              </button>
              <button
                style={{
                  padding: "6px 14px",
                  fontSize: 12,
                  fontWeight: 500,
                  borderRadius: 4,
                  border: `1px solid ${C.border}`,
                  backgroundColor: C.surface,
                  color: C.textMuted,
                  cursor: "pointer",
                  fontFamily: "inherit",
                }}
              >
                Dismiss
              </button>
            </div>
          </Card>
        );
      })}

      {/* Summary */}
      <Card style={{ marginTop: 8 }}>
        <SectionLabel>Alert Summary — Last 90 Days</SectionLabel>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16 }}>
          <Metric value="23" label="Total Alerts" />
          <Metric value="8" label="Converted to CO" color={C.green} />
          <Metric value="11" label="Dismissed" />
          <Metric value="$18.4k" label="Revenue Recovered" color={C.green} />
        </div>
      </Card>
    </div>
  );
}

// ============================================================================
// CHANGE ORDERS VIEW
// ============================================================================

function ChangeOrdersView() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <SectionLabel>Change Orders</SectionLabel>

      {/* Pending */}
      {CHANGE_ORDERS.map((co) => (
        <Card key={co.id} style={{ borderColor: "#bfdbfe", borderLeftWidth: 3 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 14 }}>{co.id} — {co.client}</div>
              <div style={{ fontSize: 12, color: C.textMuted }}>{co.engagement}</div>
            </div>
            <Badge variant="draft">{co.status}</Badge>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, padding: "12px 0", borderTop: `1px solid ${C.border}` }}>
            <div>
              <div style={{ fontSize: 11, color: C.textDim }}>Scope Additions</div>
              <div style={{ fontSize: 18, fontWeight: 600, fontFamily: "'IBM Plex Mono', monospace" }}>{co.items}</div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: C.textDim }}>Additional Hours</div>
              <div style={{ fontSize: 18, fontWeight: 600, fontFamily: "'IBM Plex Mono', monospace" }}>{co.additionalHours}</div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: C.textDim }}>Additional Fee</div>
              <div style={{ fontSize: 18, fontWeight: 600, fontFamily: "'IBM Plex Mono', monospace", color: C.green }}>
                +${co.additionalCost.toLocaleString()}
              </div>
            </div>
          </div>

          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <button
              style={{
                padding: "6px 14px",
                fontSize: 12,
                fontWeight: 500,
                borderRadius: 4,
                border: "none",
                backgroundColor: C.text,
                color: C.surface,
                cursor: "pointer",
                fontFamily: "inherit",
              }}
            >
              Review & Send to Client
            </button>
            <button
              style={{
                padding: "6px 14px",
                fontSize: 12,
                fontWeight: 500,
                borderRadius: 4,
                border: `1px solid ${C.border}`,
                backgroundColor: C.surface,
                color: C.textMuted,
                cursor: "pointer",
                fontFamily: "inherit",
              }}
            >
              Edit Draft
            </button>
          </div>
        </Card>
      ))}

      {/* Historical */}
      <Card style={{ marginTop: 8 }}>
        <SectionLabel>Change Order History — Q1 2026</SectionLabel>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 20 }}>
          <Metric value="12" label="Change Orders Sent" />
          <Metric value="9" label="Approved" color={C.green} />
          <Metric value="2" label="Rejected" color={C.red} />
          <Metric value="$127k" label="Revenue Recovered" color={C.green} />
        </div>
        <div style={{ fontSize: 12, color: C.textMuted, lineHeight: 1.6 }}>
          Prior to scope tracking, the firm absorbed an estimated $340k in unrecovered scope creep annually.
          In Q1, 34% of detected scope additions were formalized as change orders, recovering $127k that
          would have been written off. The remaining 66% were either within reasonable scope tolerance
          or the partner chose to absorb as a client relationship investment.
        </div>
      </Card>
    </div>
  );
}
