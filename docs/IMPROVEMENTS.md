# SCOPE TRACKER -- IMPROVEMENTS & TECHNOLOGY ROADMAP

## Product Overview

Scope Tracker is a scope drift detection and change order management system purpose-built for fixed-fee professional services engagements at small law firms (approximately 20 people). The product sits between an engagement letter (planned scope) and a timekeeping system (actual work performed), surfacing discrepancies before they become write-offs.

The core value proposition: detect scope creep at Week 3 instead of Week 7, giving the responsible partner a concrete, client-ready document to formalize the additional work rather than absorbing the cost.

**Key capabilities:**
- **Engagement tracking** with deliverable-level budgeting, team allocation, and timeline management
- **Automated scope drift detection** across five dimensions: budget overrun, unscoped work, burn rate anomaly, timeline slip, and team overallocation
- **Change order generation** that groups unscoped time entries into logical scope additions and produces client-facing amendment documents
- **CSV import** from Clio, PracticePanther, and Bill4Time with keyword-based categorization and fuzzy deliverable matching
- **Dashboard** (React/JSX) displaying engagement health, drift alerts, and change order history with burn-down charts
- **Email notifications** (React Email + Resend) for drift alerts and change order readiness
- **Stripe invoicing** for approved change orders with webhook-based payment tracking
- **Background jobs** (Trigger.dev) for drift detection and change order generation
- **Workflow automation** (n8n) for time entry webhook ingestion and weekly digests
- **MCP server** for AI assistant integration
- **Supabase backend** with PostgreSQL schema, RLS policies, and multi-tenant support

---

## Current Architecture

### Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Core Logic** | Python 3.11+ (stdlib only) | Engagement tracking, drift detection, change order generation |
| **Data Models** | Python dataclasses | Engagement, Deliverable, TimeEntry, ChangeOrder, TeamMember |
| **Persistence (MVP)** | JSON files on shared drive | `storage/json_store.py` with file locking |
| **Persistence (Prod)** | Supabase (PostgreSQL) | `supabase/migrations/001_initial_schema.sql` |
| **Dashboard** | React + Recharts | `dashboard/dashboard.jsx` -- partner-facing engagement health view |
| **Email Templates** | React Email + Tailwind | `emails/drift_alert.tsx`, `emails/change_order_ready.tsx` |
| **Payments** | Stripe (Python SDK) | `stripe/invoicing.py` -- invoice creation, payment links, webhooks |
| **Background Jobs** | Trigger.dev (TypeScript) | `trigger-jobs/drift_detection.ts`, `trigger-jobs/change_order_generation.ts` |
| **Workflows** | n8n | `n8n/time_entry_import.json`, `n8n/weekly_engagement_digest.json` |
| **AI Integration** | MCP (Model Context Protocol) | `mcp/server.py` -- 4 tools for AI assistants |
| **Deployment** | Vercel | `vercel.json` with cron jobs for weekly digest and daily health checks |
| **Testing** | pytest, pytest-cov, ruff, mypy | Dev dependencies in `requirements.txt` |

### Key Components

1. **`src/engagement_tracker.py`** (663 lines) -- Core data model. `Engagement` is the top-level object containing deliverables, team members, time entries, and change orders. `EngagementManager` is in-memory for MVP. Computed properties handle budget/margin/timeline calculations.

2. **`src/drift_detector.py`** (595 lines) -- `DriftDetector` class with five detection methods. Uses `DriftThresholds` dataclass for configurable thresholds. Maintains `_seen_triggers` set to avoid duplicate alerts. Returns `DriftAlert` objects with severity, cost-at-risk, and related entry IDs.

3. **`src/change_order_generator.py`** (655 lines) -- `ChangeOrderGenerator` groups unscoped time entries by theme using keyword extraction (`_extract_theme`), estimates remaining hours at 30% buffer, and produces formatted change order documents.

4. **`importers/time_entry_importer.py`** (547 lines) -- CSV import with `ColumnMapping` for multi-system support. `DescriptionParser` uses keyword matching for categorization. `DeliverableMatcher` uses three strategies: keyword match (0.4 weight), name similarity (0.3), description similarity (0.2), and category heuristic (0.1).

5. **`storage/json_store.py`** (610 lines) -- File-based persistence with `FileLock` for shared drive concurrency. Custom JSON encoder/decoder for dates and enums.

6. **`export/change_order_renderer.py`** (390 lines) -- Three output formats: Markdown, plain-text email draft, and styled HTML.

7. **`dashboard/dashboard.jsx`** (923 lines) -- Single-file React component with synthetic data. Uses Recharts for burn-down visualization. Tabs for engagements, alerts, and change orders.

### Architecture Gaps Identified

- The dashboard uses **hardcoded synthetic data** with no API integration
- The Python core and the TypeScript/Supabase backend are **not connected** -- they are parallel implementations
- No test files exist despite pytest being in requirements
- The MCP server duplicates logic from `src/` rather than importing it
- No authentication or user management in the Python core
- The `sys.path.insert(0, ...)` pattern used in several files indicates missing proper package configuration

---

## Recommended Improvements

### 1. Unify the Dual Architecture (Python Core vs. TypeScript/Supabase)

**Problem:** The project has two parallel implementations that do not share code or data. The Python core (`src/`) operates on in-memory dataclasses and JSON files. The TypeScript backend (`trigger-jobs/`) operates on Supabase. Neither calls the other.

**Recommendation:** Choose one path and commit:

**Option A -- Python-first with FastAPI:**
- Wrap the existing Python core in a FastAPI application
- Replace `json_store.py` with SQLAlchemy or direct `asyncpg` calls to Supabase PostgreSQL
- Rewrite Trigger.dev jobs as Celery/ARQ tasks or FastAPI background tasks
- Keep React dashboard, point it at FastAPI endpoints

**Option B -- TypeScript-first with Next.js:**
- Port the Python drift detection logic to TypeScript
- Use Supabase client SDK directly in Next.js API routes
- Keep Trigger.dev jobs as-is
- Build dashboard with Next.js + shadcn/ui

**Code reference:** The disconnect is visible in `trigger-jobs/drift_detection.ts` (lines 58-61) where it instantiates its own Supabase client and reimplements drift calculation, while `src/drift_detector.py` has the more sophisticated version with five detection methods.

### 2. Replace Keyword Matching with Semantic Similarity for Deliverable Matching

**Problem:** `DeliverableMatcher` in `importers/time_entry_importer.py` (line 250) uses `difflib.SequenceMatcher` for fuzzy string matching. This fails when descriptions use different vocabulary than deliverable names (e.g., "client call re: lease assignment" does not fuzzy-match well against "Due Diligence Review").

**Recommendation:** Use sentence embeddings for semantic similarity:

```python
# Replace difflib.SequenceMatcher with sentence-transformers
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')  # 80MB, fast inference

def match_entry_to_deliverable(entry_desc: str, deliverables: list[dict]) -> tuple[str, float]:
    entry_embedding = model.encode(entry_desc)
    deliverable_texts = [f"{d['name']} {d['description']}" for d in deliverables]
    deliverable_embeddings = model.encode(deliverable_texts)

    similarities = util.cos_sim(entry_embedding, deliverable_embeddings)[0]
    best_idx = similarities.argmax().item()
    return deliverables[best_idx]['id'], similarities[best_idx].item()
```

**Why:** Sentence-transformers `all-MiniLM-L6-v2` is only 80MB, runs in <10ms per inference on CPU, and handles semantic equivalence (e.g., "drafted side letter" matching "Additional Documentation" deliverable). This is a direct upgrade over the keyword + fuzzy matching approach in `_score_match` (line 318).

**Library:** [sentence-transformers](https://github.com/UKPLab/sentence-transformers) v3.4+ (latest stable). Apache 2.0 license. 15k+ GitHub stars.

### 3. Add a Proper REST API Layer

**Problem:** The Python core has no HTTP interface. The dashboard has no way to fetch real data. The MCP server (`mcp/server.py`) uses `httpx` to call an external API that does not exist yet.

**Recommendation:** Add FastAPI with Pydantic models:

```python
# api/main.py
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from src import DriftDetector, EngagementManager

app = FastAPI(title="Scope Tracker API", version="0.1.0")

@app.get("/api/engagements/{engagement_id}/drift")
async def check_drift(engagement_id: str):
    engagement = manager.get(engagement_id)
    detector = DriftDetector()
    alerts = detector.scan_engagement(engagement)
    return detector.get_alert_summary()
```

**Why:** FastAPI provides automatic OpenAPI docs, Pydantic validation, async support, and dependency injection. The MCP server at `mcp/server.py` already assumes an HTTP API exists (line 59: `self.analytics_api_url`). Building it makes the MCP server functional.

**Libraries:**
- [FastAPI](https://github.com/fastapi/fastapi) v0.115+ -- async Python web framework. 80k+ GitHub stars.
- [Pydantic](https://github.com/pydantic/pydantic) v2.10+ -- data validation using Python type hints
- [uvicorn](https://github.com/encode/uvicorn) v0.34+ -- ASGI server

### 4. Replace Hardcoded Dashboard Data with Live API Calls

**Problem:** `dashboard/dashboard.jsx` (lines 32-157) contains hardcoded `ENGAGEMENTS`, `ALERTS`, and `CHANGE_ORDERS` arrays. The dashboard is a static demo, not a functional application.

**Recommendation:**
- Add React Query (TanStack Query) for data fetching with caching and real-time refetching
- Replace synthetic data constants with API calls to the FastAPI backend
- Add loading states, error boundaries, and optimistic updates

```jsx
import { useQuery } from '@tanstack/react-query';

function useEngagements() {
  return useQuery({
    queryKey: ['engagements'],
    queryFn: () => fetch('/api/engagements').then(r => r.json()),
    refetchInterval: 30000, // Poll every 30s for new drift alerts
  });
}
```

**Libraries:**
- [TanStack Query](https://github.com/TanStack/query) v5.68+ -- server state management for React. 43k+ GitHub stars.
- [shadcn/ui](https://github.com/shadcn-ui/ui) -- accessible component library built on Radix primitives. Would replace the inline-styled components.

### 5. Add a Proper Test Suite

**Problem:** `requirements.txt` lists pytest and pytest-cov, but no test files exist in the project. The core drift detection logic handles financial calculations where bugs directly translate to lost revenue.

**Recommendation:** Add tests at three levels:

```
tests/
  test_engagement_tracker.py    # Unit tests for computed properties
  test_drift_detector.py        # Unit tests for all 5 detection methods
  test_change_order_generator.py # Unit tests for theme grouping and cost calculation
  test_time_entry_importer.py   # Unit tests for CSV parsing and matching
  test_json_store.py            # Integration tests for persistence
  test_api.py                   # API integration tests (if FastAPI added)
  conftest.py                   # Shared fixtures (sample engagements, entries)
```

**Priority test cases:**
- `DriftDetector._check_deliverable_budgets` with edge cases (0 hours, exactly at threshold, deliverable already delivered)
- `ChangeOrderGenerator._blended_rate` with empty team list (currently returns hardcoded 300)
- `Engagement.projected_total_hours` with elapsed_days=0 and total_days=0 (division edge cases)
- `DeliverableMatcher.match` with empty deliverables list
- `FileLock` timeout and concurrent access scenarios

### 6. Add Proper Python Packaging

**Problem:** Multiple files use `sys.path.insert(0, ...)` to find sibling modules (e.g., `storage/json_store.py` line 38, `export/change_order_renderer.py` line 17, `demo/simulate_engagement.py` line 30). This is fragile and breaks in many deployment scenarios.

**Recommendation:** Add `pyproject.toml` with proper package configuration:

```toml
[project]
name = "scope-tracker"
version = "0.1.0"
requires-python = ">=3.11"

[tool.setuptools.packages.find]
include = ["src*", "storage*", "importers*", "export*", "demo*"]
```

Then replace all `sys.path.insert` calls with proper relative imports. Install in development mode with `pip install -e .`.

### 7. Implement Real-Time Webhook Integration with Clio/PracticePanther APIs

**Problem:** The current CSV import (`importers/time_entry_importer.py`) requires manual file export/import. The n8n webhook (`n8n/time_entry_import.json`) is configured but the actual Clio/PracticePanther API integration is not implemented.

**Recommendation:** Implement OAuth2 flows and webhook receivers for real-time time entry ingestion:

```python
# Clio API integration
@app.post("/webhooks/clio/time-entry")
async def clio_webhook(payload: ClioWebhookPayload):
    entry = transform_clio_entry(payload)
    engagement = manager.get(entry.engagement_id)
    engagement.log_time(entry)

    # Run drift detection immediately
    detector = DriftDetector()
    alerts = detector.scan_engagement(engagement)
    if any(a.severity == AlertSeverity.CRITICAL for a in alerts):
        await send_drift_alert(engagement, alerts)
```

**APIs:**
- [Clio API v4](https://docs.developers.clio.com/) -- OAuth2, webhooks for activity creation events
- [PracticePanther API](https://www.practicepanther.com/api/) -- REST API with time entry endpoints

### 8. Add PDF Generation for Change Orders

**Problem:** `export/change_order_renderer.py` produces Markdown, plain text, and HTML. Partners at law firms typically need PDF documents for formal client communication and record-keeping.

**Recommendation:** Add PDF rendering using WeasyPrint or ReportLab:

```python
from weasyprint import HTML

def render_pdf(html_content: str) -> bytes:
    return HTML(string=html_content).write_pdf()
```

**Libraries:**
- [WeasyPrint](https://github.com/Kozea/WeasyPrint) v63+ -- HTML/CSS to PDF renderer. Leverages the existing `render_html_change_order` method.
- [ReportLab](https://pypi.org/project/reportlab/) v4.2+ -- Already listed in `requirements.txt` as optional. Lower-level but more control.

### 9. Add LLM-Powered Description Enhancement for Change Orders

**Problem:** `ChangeOrderGenerator._extract_theme` (line 261) uses simple keyword matching to group time entries into themes. The resulting scope addition names are from a hardcoded lookup table (`_theme_to_name`, line 296). This produces generic names like "Lease Assignment Review and Negotiation" regardless of context.

**Recommendation:** Use an LLM to generate contextual scope addition descriptions:

```python
from anthropic import Anthropic

async def enhance_scope_description(
    entries: list[TimeEntry],
    engagement: Engagement
) -> str:
    client = Anthropic()
    prompt = f"""Given these time entries for {engagement.matter_name}:
    {[e.description for e in entries]}

    Write a 2-sentence professional description of this scope addition
    suitable for a client-facing change order document."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text
```

**Why:** The change order is the revenue-recovery document. Better descriptions lead to higher client approval rates. The Anthropic API at ~$3/million input tokens makes this negligible cost per change order.

### 10. Add Database Migration Support

**Problem:** `supabase/migrations/001_initial_schema.sql` is a single monolithic migration. No migration tooling is configured for iterative schema changes.

**Recommendation:** Use Supabase CLI or Alembic for proper migration management:

```bash
# Supabase CLI
supabase migration new add_engagement_tags
supabase db push
supabase db reset
```

Or for the Python-first path:
```bash
# Alembic with SQLAlchemy
alembic init migrations
alembic revision --autogenerate -m "add engagement tags"
alembic upgrade head
```

**Libraries:**
- [Supabase CLI](https://supabase.com/docs/guides/cli) v2+ -- managed migrations for Supabase
- [Alembic](https://github.com/sqlalchemy/alembic) v1.14+ -- database migration tool for SQLAlchemy

---

## New Technologies & Trends

### 1. LLM-Powered Scope Analysis (Anthropic Claude / OpenAI)

The current keyword-based approach in `DescriptionParser` (line 141 of `time_entry_importer.py`) and `_extract_theme` (line 261 of `change_order_generator.py`) could be augmented with LLM classification. Modern APIs support structured output, making it reliable for production use.

**Specific application:** Use Claude's tool_use capability to classify time entries into scope/out-of-scope with reasoning, replacing the confidence_score heuristic in `ParsedTimeEntry.is_ambiguous` (line 67).

**Libraries:**
- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) v0.43+ -- Claude API with tool use and structured outputs
- [Instructor](https://github.com/jxnl/instructor) v1.7+ -- structured LLM outputs using Pydantic models. 9k+ GitHub stars.
- [LiteLLM](https://github.com/BerriAI/litellm) v1.58+ -- unified interface for 100+ LLM providers

**Link:** https://github.com/anthropics/anthropic-sdk-python

### 2. Predictive Scope Drift Using Time Series Forecasting

The current `_check_burn_rate` in `drift_detector.py` (line 277) uses a simple ratio of budget consumed to timeline elapsed. This is reactive, not predictive.

**Recommendation:** Implement lightweight time series forecasting to predict when budget will be exhausted:

```python
from statsforecast import StatsForecast
from statsforecast.models import AutoETS

# Predict weekly hours consumption
sf = StatsForecast(models=[AutoETS(season_length=1)], freq='W')
forecast = sf.forecast(df=weekly_hours_data, h=4)  # 4-week forecast
projected_exhaustion_date = calculate_exhaustion(forecast)
```

**Libraries:**
- [statsforecast](https://github.com/Nixtla/statsforecast) v2.0+ -- fast time series forecasting. 4k+ GitHub stars.
- [Prophet](https://github.com/facebook/prophet) v1.1+ -- Meta's forecasting library, good for weekly patterns.

**Link:** https://github.com/Nixtla/statsforecast

### 3. Real-Time Collaboration with Supabase Realtime

Supabase Realtime enables WebSocket-based subscriptions to database changes. This would allow the dashboard to update instantly when time entries are logged or drift alerts are triggered, rather than polling.

```typescript
const channel = supabase
  .channel('drift-alerts')
  .on('postgres_changes',
    { event: 'INSERT', schema: 'public', table: 'drift_events' },
    (payload) => {
      showAlertNotification(payload.new);
    }
  )
  .subscribe();
```

**Link:** https://supabase.com/docs/guides/realtime

### 4. shadcn/ui + Tailwind CSS for Dashboard Modernization

The current dashboard (`dashboard/dashboard.jsx`) uses inline styles extensively (900+ lines of JSX with inline style objects). This makes theming, responsive design, and maintenance difficult.

**Recommendation:** Migrate to shadcn/ui with Tailwind CSS:
- Pre-built accessible components (Card, Badge, Table, Chart)
- Dark mode support out of the box
- Consistent design system
- Radix UI primitives for accessibility
- Copy-paste component model (no dependency lock-in)

**Link:** https://ui.shadcn.com/

### 5. Temporal or Inngest for Durable Workflow Orchestration

The current architecture uses Trigger.dev for background jobs and n8n for workflow automation. For the critical path of "detect drift -> generate change order -> send email -> track payment," a durable workflow engine would provide better reliability guarantees.

**Libraries:**
- [Inngest](https://github.com/inngest/inngest) v3.0+ -- event-driven durable functions. Handles retries, fan-out, and step functions. TypeScript-first. 5k+ GitHub stars.
- [Temporal](https://github.com/temporalio/temporal) v1.25+ -- production-grade workflow orchestration. Supports Python and TypeScript SDKs. 12k+ GitHub stars.

**Why:** The 5-minute delay in `drift_detection.ts` (line 156: `await wait.for({ delay: 5 * 60 })`) before triggering change order generation is a brittle pattern. A durable workflow would handle this as a proper step function with automatic retries and state persistence.

**Link:** https://www.inngest.com/, https://temporal.io/

### 6. Clio Manage API v4 with Webhooks

Clio is the most widely used legal practice management platform. Their v4 API supports real-time webhooks for time entry events, which would replace the CSV import workflow entirely.

**Key endpoints:**
- `POST /api/v4/webhooks` -- register for `activity.created` events
- `GET /api/v4/activities` -- fetch time entries with matter and user details
- `GET /api/v4/matters` -- fetch engagement/matter details

**Link:** https://docs.developers.clio.com/

### 7. DocuSign or PandaDoc for E-Signature on Change Orders

The current change order documents include placeholder signature blocks (plain text lines in `change_order_generator.py`, line 471: `f"{'_' * 40}    {'_' * 20}"`). Integrating e-signature would close the loop from detection to client approval.

**Libraries:**
- [DocuSign eSignature API](https://developers.docusign.com/) -- industry standard for legal documents
- [PandaDoc API](https://developers.pandadoc.com/) -- document automation with built-in e-signature. Better API developer experience than DocuSign.

**Why:** The entire value chain is: detect drift -> generate change order -> **get client signature** -> invoice via Stripe. The signature step is currently manual. Automating it directly increases the conversion rate from "change order generated" to "revenue recovered."

### 8. Observability with OpenTelemetry

For production deployment, the system needs proper observability. The current logging is basic (`logging.basicConfig` in `stripe/invoicing.py` and `mcp/server.py`).

**Recommendation:**
- [OpenTelemetry Python SDK](https://github.com/open-telemetry/opentelemetry-python) v1.29+ -- distributed tracing, metrics, and logs
- [Sentry](https://sentry.io/) -- already configured in `.env.example` (line 84: `SENTRY_DSN`), just needs implementation
- [PostHog](https://posthog.com/) -- already configured in `.env.example` (line 88: `POSTHOG_API_KEY`), for product analytics

### 9. AI-Powered Smart Alerts with Context Enrichment

Instead of threshold-based alerts (the current approach in `DriftThresholds`, line 97 of `drift_detector.py`), implement context-aware alerting that considers historical engagement data:

- "This engagement is 20% over budget, but similar CRE closings at this firm average 15% over at this stage"
- "Kevin Liu has logged 5 unscoped hours, but 80% of his unscoped hours on past deals were eventually within scope"

This requires building a historical data layer and using it to contextualize alerts, reducing false positives.

### 10. Multi-Tenant SaaS Architecture

The Supabase schema (`001_initial_schema.sql`) already includes `firm_id` on all tables and RLS policies, but the Python core has no concept of tenancy. For SaaS deployment:

- Add `firm_id` to all Python data models
- Implement API key authentication per firm
- Add Stripe Connect for per-firm billing
- Use Supabase RLS as the authorization layer

---

## Priority Roadmap

### P0 -- Critical Path (Do First)

| # | Improvement | Effort | Impact | Reference |
|---|-------------|--------|--------|-----------|
| 1 | **Add test suite** for core drift detection and change order logic | 2-3 days | Prevents financial calculation bugs; enables safe refactoring | `src/drift_detector.py`, `src/change_order_generator.py` |
| 2 | **Add proper Python packaging** (`pyproject.toml`) and remove all `sys.path.insert` hacks | 1 day | Fixes import reliability; enables `pip install -e .` | `storage/json_store.py:38`, `export/change_order_renderer.py:17` |
| 3 | **Build FastAPI REST API layer** wrapping the Python core | 3-4 days | Enables dashboard integration, MCP server functionality, and webhook receivers | `mcp/server.py` assumes API exists |
| 4 | **Connect dashboard to live API** replacing hardcoded synthetic data | 2-3 days | Makes the dashboard functional rather than a static demo | `dashboard/dashboard.jsx:32-157` |

### P1 -- High Value (Do Next)

| # | Improvement | Effort | Impact | Reference |
|---|-------------|--------|--------|-----------|
| 5 | **Semantic deliverable matching** with sentence-transformers | 2-3 days | Significantly improves scope detection accuracy over keyword/fuzzy matching | `importers/time_entry_importer.py:318` |
| 6 | **Clio API webhook integration** for real-time time entry ingestion | 3-5 days | Eliminates manual CSV export/import workflow; enables real-time drift detection | `importers/time_entry_importer.py` |
| 7 | **PDF generation** for change orders using WeasyPrint | 1-2 days | Partners need PDF documents for formal client communication | `export/change_order_renderer.py` |
| 8 | **Supabase Realtime** for live dashboard updates | 1-2 days | Dashboard reflects drift alerts within seconds, not on manual refresh | `dashboard/dashboard.jsx` |

### P2 -- Medium Value (Plan For)

| # | Improvement | Effort | Impact | Reference |
|---|-------------|--------|--------|-----------|
| 9 | **LLM-enhanced change order descriptions** | 2-3 days | Better client-facing documents increase approval rates | `src/change_order_generator.py:261` |
| 10 | **Predictive burn rate forecasting** with statsforecast | 3-5 days | Shift from reactive ("you're over budget") to proactive ("you will be over budget in 2 weeks") | `src/drift_detector.py:277` |
| 11 | **E-signature integration** (PandaDoc) for change order approval | 3-5 days | Closes the loop from detection to signed amendment | `export/change_order_renderer.py` signature blocks |
| 12 | **Dashboard modernization** with shadcn/ui + Tailwind | 3-5 days | Replaces 900+ lines of inline styles; adds dark mode, responsive design, accessibility | `dashboard/dashboard.jsx` |
| 13 | **Database migration tooling** with Alembic or Supabase CLI | 1 day | Enables safe iterative schema changes | `supabase/migrations/` |
| 14 | **Durable workflows** with Inngest replacing Trigger.dev wait patterns | 3-5 days | Reliable multi-step orchestration with automatic retries | `trigger-jobs/drift_detection.ts:156` |

### P3 -- Future Enhancements (Backlog)

| # | Improvement | Effort | Impact | Reference |
|---|-------------|--------|--------|-----------|
| 15 | **AI-powered smart alerts** with historical context and anomaly detection | 1-2 weeks | Reduces false positive alerts by contextualizing against firm benchmarks | `src/drift_detector.py:97` thresholds |
| 16 | **Multi-tenant SaaS deployment** with Stripe Connect billing | 2-3 weeks | Enables selling to multiple firms | `supabase/migrations/001_initial_schema.sql` already has `firm_id` |
| 17 | **Cross-engagement capacity planning** | 1-2 weeks | "Kevin Liu is budgeted for 120 hours across 3 active engagements this month" | `src/engagement_tracker.py` TeamMember |
| 18 | **OpenTelemetry observability** with Sentry + PostHog | 2-3 days | Production monitoring and product analytics | `.env.example` already has config placeholders |
| 19 | **PracticePanther and Bill4Time API integrations** | 1-2 weeks each | Expand beyond Clio to other practice management platforms | `importers/time_entry_importer.py` ColumnMapping |
| 20 | **Mobile-responsive dashboard** or native mobile app | 2-4 weeks | Partners check engagement health on phones during client meetings | `dashboard/dashboard.jsx` |
| 21 | **Historical analytics dashboard** with trend analysis across completed engagements | 1-2 weeks | "CRE closings over $30k average 18% scope creep" -- informs future pricing | Requires completed engagement data |
| 22 | **Client portal** for self-service change order review and approval | 2-3 weeks | Reduces back-and-forth between partner and client | New feature |

---

## Summary

The Scope Tracker has a solid core architecture with well-designed domain models and business logic. The Python `src/` modules demonstrate strong domain knowledge of fixed-fee legal engagement management. The most impactful improvements are:

1. **Connecting the pieces** -- the FastAPI layer, live dashboard, and proper packaging turn this from a set of independent modules into a working product
2. **Semantic matching** -- upgrading from keyword/fuzzy matching to sentence embeddings is the single highest-impact improvement to detection accuracy
3. **Closing the revenue loop** -- PDF generation + e-signature + Stripe integration means scope creep detection actually converts to recovered revenue
4. **Testing** -- the financial calculations in drift detection and change order generation are too important to run without test coverage
