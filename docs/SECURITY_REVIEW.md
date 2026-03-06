# Scope Tracker -- Security Review

**Review Date:** 2026-03-06
**Reviewer:** Automated Security Audit
**Scope:** All source files in `src/`, `importers/`, `stripe/`, `dashboard/`, `emails/`, `mcp/`, `n8n/`, `trigger-jobs/`, `storage/`, `export/`, configuration files, and infrastructure definitions.

---

## Executive Summary

This review identified **14 findings** across the scope-tracker codebase. The most critical issues involve missing Stripe webhook signature verification at the API routing layer, use of the Supabase anon key for server-side operations that bypass RLS, stored XSS vectors in HTML document rendering, and placeholder credentials committed to the repository in `.replit`. The application's RLS policies in Supabase are well-structured but contain gaps that could allow cross-tenant data access under specific conditions.

| Severity | Count |
|----------|-------|
| CRITICAL | 4     |
| HIGH     | 4     |
| MEDIUM   | 4     |
| LOW      | 2     |

---

## Findings

### FINDING-01: Webhook Endpoint Processes Events Without Signature Verification

**Severity:** CRITICAL
**File:** `F:\Portfolio\Portfolio\scope-tracker\stripe\invoicing.py`, lines 555-566
**Category:** Payment Security / Stripe Webhook Verification

**Description:** The `webhook_endpoint()` function accepts a Stripe event dictionary directly and passes it to `handle_payment_webhook()` without ever calling `verify_stripe_webhook()`. The signature verification function exists (line 504) but is never invoked in the endpoint handler. This means any caller can forge a webhook payload to mark change orders as "paid" without actual payment, trigger refund status updates, or modify payment states in the database.

**Code Evidence:**
```python
# Line 555-566: webhook_endpoint accepts raw event, never verifies signature
def webhook_endpoint(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    API endpoint handler for Stripe webhooks.
    """
    service = StripeInvoicingService()
    return service.handle_payment_webhook(event)  # No signature check

# Line 504-524: verify_stripe_webhook exists but is NEVER called
def verify_stripe_webhook(request_body: str, signature: str) -> bool:
    ...
```

**Fix:** The webhook endpoint must extract the raw request body and the `Stripe-Signature` header, then call `verify_stripe_webhook()` before processing. Reject the request with HTTP 400 if verification fails.

```python
def webhook_endpoint(request_body: str, signature: str) -> Dict[str, Any]:
    if not verify_stripe_webhook(request_body, signature):
        return {"status": "error", "message": "Invalid signature"}, 400
    event = json.loads(request_body)
    service = StripeInvoicingService()
    return service.handle_payment_webhook(event)
```

---

### FINDING-02: Server-Side Operations Use Supabase Anon Key Instead of Service Role Key

**Severity:** CRITICAL
**File:** `F:\Portfolio\Portfolio\scope-tracker\stripe\invoicing.py`, lines 28-31; `trigger-jobs/drift_detection.ts`, lines 58-61; `trigger-jobs/change_order_generation.ts`, lines 35-38; `n8n/time_entry_import.json`; `n8n/weekly_engagement_digest.json`
**Category:** Authentication / Multi-Tenant Isolation

**Description:** All server-side processes (Stripe invoicing service, Trigger.dev background jobs, n8n workflow automations) initialize their Supabase clients using `SUPABASE_ANON_KEY`. The anon key is meant for client-side use and is subject to Row-Level Security (RLS) policies that require `auth.uid()` to be set. When these server-side processes make requests with the anon key but without an authenticated user session, one of two outcomes occurs: (a) RLS blocks the operation entirely, causing silent failures; or (b) if RLS policies have gaps (see FINDING-05), the operations succeed without proper tenant isolation.

**Code Evidence:**
```python
# stripe/invoicing.py lines 28-31
supabase: Client = create_client(
    os.environ.get("SUPABASE_URL", ""),
    os.environ.get("SUPABASE_ANON_KEY", ""),  # Should be SERVICE_ROLE_KEY
)
```
```typescript
// trigger-jobs/drift_detection.ts lines 58-61
const supabase = createClient<Database>(
  process.env.SUPABASE_URL!,
  process.env.SUPABASE_ANON_KEY!  // Should be SUPABASE_SERVICE_ROLE_KEY
);
```

**Fix:** Server-side processes must use `SUPABASE_SERVICE_ROLE_KEY` (which bypasses RLS) and then implement their own authorization checks, or use RLS with an impersonated service-level JWT. Update all backend Supabase client initializations to use the service role key. Ensure the service role key is only available to server-side environments, never exposed to clients.

---

### FINDING-03: Stored XSS in HTML Change Order Renderer

**Severity:** CRITICAL
**File:** `F:\Portfolio\Portfolio\scope-tracker\export\change_order_renderer.py`, lines 287-312
**Category:** Input Validation / XSS

**Description:** The `render_html_change_order()` method interpolates user-controlled data directly into HTML without escaping. The fields `engagement.client_name`, `engagement.matter_name`, `engagement.responsible_partner`, `engagement.id`, deliverable names and descriptions, scope addition names and descriptions, and the `reason` parameter are all injected via f-strings into raw HTML. If any of these fields contain malicious JavaScript (e.g., a client name of `<script>alert(document.cookie)</script>`), it will execute when the HTML is rendered in a browser.

**Code Evidence:**
```python
# Lines 288-291: Direct interpolation into HTML tags
lines.append(f"<p><strong>Client:</strong> {engagement.client_name}</p>")
lines.append(f"<p><strong>Matter:</strong> {engagement.matter_name}</p>")
lines.append(f"<p><strong>Engagement ID:</strong> {engagement.id}</p>")
lines.append(f"<p><strong>Partner:</strong> {engagement.responsible_partner}</p>")

# Line 304: Deliverable data interpolated
lines.append(f"<li><strong>{d.name}</strong><br/>{d.description}</li>")

# Line 312: User-controlled reason parameter
lines.append(f"<p><strong>Reason:</strong> {reason}</p>")

# Lines 320-321: Scope addition names and descriptions
lines.append(f"<h3>{i}. {addition['name']}</h3>")
lines.append(f"<p>{addition['description']}</p>")
```

**Fix:** HTML-escape all user-controlled values before interpolation. Use Python's `html.escape()` on every dynamic value inserted into HTML context:

```python
import html

lines.append(f"<p><strong>Client:</strong> {html.escape(engagement.client_name)}</p>")
```

Apply this to every dynamic value in the entire method. Alternatively, use a template engine (Jinja2 with autoescape) which escapes by default.

---

### FINDING-04: Placeholder Credentials Committed in .replit Configuration

**Severity:** CRITICAL
**File:** `F:\Portfolio\Portfolio\scope-tracker\.replit`, lines 15-23
**Category:** Hardcoded Secrets

**Description:** The `.replit` file is committed to the repository and contains placeholder API keys and credentials in the `[env]` section. While these appear to be placeholder values (`YOUR_STRIPE_TEST_KEY`, `dev-key`, etc.), the file structure encourages developers to replace them with real values in-place. Since `.replit` is not in `.gitignore`, any developer who adds real keys risks committing them. Additionally, the `DATABASE_URL` contains a credential pattern (`user:password`) that establishes a dangerous template.

**Code Evidence:**
```ini
# .replit lines 15-23
[env]
DATABASE_URL = "postgresql://user:password@localhost:5432/scope_tracker"
SUPABASE_URL = "http://localhost:54321"
SUPABASE_ANON_KEY = "dev-key"
STRIPE_API_KEY = "YOUR_STRIPE_TEST_KEY"
CLIO_API_URL = "https://api.clio.com/v4"
PRACTICEPANTHER_API_URL = "https://api.practicepanther.com"
N8N_URL = "http://localhost:5678"
RESEND_API_KEY = "YOUR_RESEND_KEY"
TRIGGER_API_KEY = "tr_dev"
```

**Fix:** Add `.replit` to `.gitignore`. Remove all credential values from the committed file and reference environment secrets via Replit's secrets manager instead. Replace the `[env]` section with comments referencing required secrets.

---

### FINDING-05: RLS Policy Gaps Allow Cross-Tenant Data Leakage

**Severity:** HIGH
**File:** `F:\Portfolio\Portfolio\scope-tracker\supabase\migrations\001_initial_schema.sql`, lines 262-273
**Category:** Multi-Tenant Isolation

**Description:** Several RLS policies have logic gaps that could allow cross-tenant data access:

1. The `engagements_select_partner` policy (line 262) checks that the user's `firm_id` matches the engagement's `firm_id`, but the partner role check (`auth.uid() in (select id from users where role = 'partner')`) is not scoped to the same firm. A partner in Firm A could potentially access engagements in Firm B if this subquery matches any partner in any firm.

2. The `engagements_select_associate` policy (line 269) checks `auth.uid() = any(team_members)` but does NOT verify `firm_id`. An associate whose UUID happens to appear in another firm's `team_members` array would gain access.

3. The `drift_events_select` policy (line 307) checks for partner role globally (`auth.uid() in (select id from users where role = 'partner')`) without a `firm_id` filter, allowing any partner to see any firm's drift events.

**Code Evidence:**
```sql
-- Line 262-266: Partner check not scoped to firm
create policy "engagements_select_partner" on engagements for select
  using (
    firm_id in (select firm_id from users where id = auth.uid()) and
    (owner_id = auth.uid() or auth.uid() in (select id from users where role = 'partner'))
    -- The second condition matches ANY partner, not just partners in the same firm
  );

-- Line 307-314: drift_events partner check not firm-scoped
create policy "drift_events_select" on drift_events for select
  using (
    engagement_id in (
      select id from engagements where
      auth.uid() in (select id from users where role = 'partner') or
      -- This matches ANY partner in ANY firm
      auth.uid() = owner_id
    )
  );
```

**Fix:** Scope all partner-role checks to include `firm_id`:
```sql
auth.uid() in (
  select id from users
  where role = 'partner'
  AND firm_id = engagements.firm_id
)
```

Apply the same firm-scoping fix to all policies that check role without firm context: `engagements_select_partner`, `engagements_update`, `drift_events_select`, `change_orders_select`, `change_orders_update`, and `time_entries_select`.

---

### FINDING-06: No Authentication on API Endpoint Handlers

**Severity:** HIGH
**File:** `F:\Portfolio\Portfolio\scope-tracker\stripe\invoicing.py`, lines 527-566
**Category:** Authentication

**Description:** The standalone API endpoint functions (`create_invoice_endpoint`, `payment_link_endpoint`, `webhook_endpoint`) have no authentication or authorization checks. Any caller who can reach these endpoints can create invoices, generate payment links, and submit webhook events. There is no middleware, no token validation, no session check, and no rate limiting implemented.

**Code Evidence:**
```python
# Line 527-538: No auth check before creating invoice
def create_invoice_endpoint(change_order_id: str) -> Dict[str, Any]:
    service = StripeInvoicingService()
    return service.create_invoice_from_change_order(change_order_id)

# Line 541-552: No auth check before generating payment link
def payment_link_endpoint(change_order_id: str) -> str:
    service = StripeInvoicingService()
    return service.create_payment_link(change_order_id)
```

**Fix:** Implement authentication middleware that validates JWT tokens or Supabase session tokens before any endpoint handler executes. Add authorization checks to verify the caller has permission to operate on the specified `change_order_id` (i.e., they belong to the same firm). Example:

```python
def create_invoice_endpoint(change_order_id: str, user: AuthenticatedUser) -> Dict[str, Any]:
    if not user.can_manage_change_order(change_order_id):
        raise PermissionError("Unauthorized")
    service = StripeInvoicingService()
    return service.create_invoice_from_change_order(change_order_id)
```

---

### FINDING-07: n8n Workflows Use Anon Key for Privileged Operations Without Tenant Scoping

**Severity:** HIGH
**File:** `F:\Portfolio\Portfolio\scope-tracker\n8n\time_entry_import.json`, lines 38-43 and 87-92; `n8n/weekly_engagement_digest.json`, lines 32-37 and 86-98
**Category:** Multi-Tenant Isolation / Authorization

**Description:** Both n8n workflows make direct HTTP requests to the Supabase REST API using the `SUPABASE_ANON_KEY` for authentication. The workflows perform operations across the entire database without any tenant/firm scoping:

1. The time entry import workflow looks up users by email (`users?email=eq.{email}`) across all firms.
2. The weekly digest workflow fetches ALL active engagements (`engagements?is_active=eq.true`) and ALL partners (`users?role=eq.partner`) without firm filtering.
3. These workflows insert data (time entries, email logs) and trigger background jobs without verifying the incoming webhook caller's identity.

Additionally, the time entry import webhook (line 9) uses `headerAuth` but the specific credentials are not defined in the workflow file, which means they may default to weak or no authentication depending on the n8n instance configuration.

**Code Evidence:**
```json
// time_entry_import.json line 80-82: Lookup user across all firms
"url": "={{ $env.SUPABASE_URL }}/rest/v1/users?email=eq.{{ $node['Parse Time Entry'].json.logged_by_email }}&select=id,firm_id"

// weekly_engagement_digest.json line 26: Fetch ALL active engagements
"url": "={{ $env.SUPABASE_URL }}/rest/v1/engagements?is_active=eq.true&select=..."

// weekly_engagement_digest.json line 88: Fetch ALL partners
"url": "={{ $env.SUPABASE_URL }}/rest/v1/users?role=eq.partner&select=id,full_name,email,firm_id"
```

**Fix:** Use the Supabase service role key for server-side n8n workflows, and add explicit firm_id filtering to every query. Implement webhook authentication with a shared secret for the time entry import endpoint. Ensure the weekly digest only sends engagement data to partners within their own firm.

---

### FINDING-08: MCP Server Accepts Tenant ID from Client Without Validation

**Severity:** HIGH
**File:** `F:\Portfolio\Portfolio\scope-tracker\mcp\server.py`, lines 452-541; `mcp/tool_schemas.json`
**Category:** Multi-Tenant Isolation / Authorization

**Description:** All four MCP tool handlers (`_check_scope_drift`, `_generate_change_order`, `_get_time_entries`, `_list_engagements`) accept a `tenant_id` parameter from the caller and pass it directly to the backend API. There is no validation that the caller is authorized to access data for the specified tenant. A user could supply any `tenant_id` to access another firm's engagements, time entries, and drift data.

**Code Evidence:**
```python
# Line 520-526: tenant_id from user input used directly
async def _list_engagements(args: Dict[str, Any]) -> List[TextContent]:
    tenant_id = args["tenant_id"]
    status_filter = args.get("status_filter")
    engagements = await engagement_mgr.list_engagements(tenant_id, status_filter)
```

**Fix:** The MCP server should authenticate the calling user and derive the `tenant_id` from their authenticated session, not from user-supplied input. If multi-tenant access is needed (e.g., for admin tools), validate that the authenticated user has permission to access the requested tenant.

---

### FINDING-09: TLS Certificate Verification Disabled in .env.example

**Severity:** MEDIUM
**File:** `F:\Portfolio\Portfolio\scope-tracker\.env.example`, line 93
**Category:** Infrastructure Misconfiguration

**Description:** The `.env.example` file contains `NODE_TLS_REJECT_UNAUTHORIZED=0`, which disables TLS certificate verification for all HTTPS connections. This is documented as a development setting, but `.env.example` files are commonly copied as-is for quick setup. If this value reaches production, all outbound HTTPS connections (to Stripe, Supabase, Clio, etc.) become vulnerable to man-in-the-middle attacks. An attacker on the network could intercept API keys and payment data.

**Code Evidence:**
```ini
# .env.example line 93
# Disable SSL verification for local dev (NOT for production)
NODE_TLS_REJECT_UNAUTHORIZED=0
```

**Fix:** Remove this line from `.env.example` entirely. If needed for local development, add it only to a `.env.local` file that is gitignored, and add a startup check that rejects `NODE_TLS_REJECT_UNAUTHORIZED=0` when `NODE_ENV=production`.

---

### FINDING-10: Vercel Cron Endpoints Lack Authentication

**Severity:** MEDIUM
**File:** `F:\Portfolio\Portfolio\scope-tracker\vercel.json`, lines 38-47
**Category:** Authentication / Infrastructure

**Description:** Two cron endpoints are defined in `vercel.json`: `/api/cron/weekly-digest` (Monday 8 AM) and `/api/cron/engagement-health-check` (daily 9 AM). These are standard HTTP endpoints that Vercel calls on schedule, but they are also publicly accessible via the deployment URL. Without authentication, anyone can trigger the weekly digest or health check by making an HTTP request to `https://scope-tracker.vercel.app/api/cron/weekly-digest`. This could lead to email spam to partners, excessive database queries, or information disclosure.

**Code Evidence:**
```json
"crons": [
  {
    "path": "/api/cron/weekly-digest",
    "schedule": "0 8 ? * MON"
  },
  {
    "path": "/api/cron/engagement-health-check",
    "schedule": "0 9 ? * * *"
  }
]
```

**Fix:** Validate the `CRON_SECRET` header that Vercel includes with cron invocations (use `VERCEL_CRON_SECRET` environment variable). Reject requests that do not include the correct secret. Example:

```typescript
if (req.headers['authorization'] !== `Bearer ${process.env.CRON_SECRET}`) {
  return res.status(401).json({ error: 'Unauthorized' });
}
```

---

### FINDING-11: Overly Broad SELECT * Queries Expose All Column Data

**Severity:** MEDIUM
**File:** `F:\Portfolio\Portfolio\scope-tracker\trigger-jobs\drift_detection.ts`, line 86; `trigger-jobs/change_order_generation.ts`, lines 52 and 63; `stripe/invoicing.py`, lines 379, 389, 399, 458
**Category:** Data Exposure

**Description:** Multiple database queries use `.select("*")` which returns all columns from the queried table. This means sensitive fields (contact emails, phone numbers, internal notes, financial data) are loaded into memory even when only a few fields are needed. In the Stripe invoicing module, `_fetch_client` returns the entire client record including `contact_email` and `contact_phone`, and `_fetch_engagement` returns the entire engagement record. In the change order generation job, the full engagement and client records are fetched. This increases the attack surface if any of these values are logged, included in error messages, or returned in API responses.

**Code Evidence:**
```typescript
// trigger-jobs/change_order_generation.ts line 52
const { data: engagement, error: engError } = await supabase
    .from("engagements")
    .select("*")  // Returns ALL columns including scope_document, notes, etc.
    .eq("id", payload.engagement_id)
    .single();
```
```python
# stripe/invoicing.py line 399
def _fetch_client(self, client_id: str) -> Dict[str, Any]:
    response = (
        self.supabase.table("clients")
        .select("*")  # Returns contact_email, contact_phone, etc.
        .eq("id", client_id)
        .execute()
    )
```

**Fix:** Replace `.select("*")` with explicit column lists that include only the fields actually needed by each function. For example:
```python
.select("id, name, contact_email")  # Only what's needed
```

---

### FINDING-12: Path Traversal Risk in JSON Store File Operations

**Severity:** MEDIUM
**File:** `F:\Portfolio\Portfolio\scope-tracker\storage\json_store.py`, lines 161-165
**Category:** Input Validation

**Description:** The `_engagement_dir()` method constructs file paths using user-supplied `engagement_id` without sanitization. If an attacker can control the engagement ID (e.g., `../../etc/passwd` or `..\..\Windows\System32`), they could read or write files outside the intended data directory. The `Path` object provides some protection, but `mkdir(parents=True, exist_ok=True)` will create intermediate directories. Combined with `save_engagement()` which writes JSON to this path, this could be exploited to write arbitrary files.

**Code Evidence:**
```python
# Line 161-165
def _engagement_dir(self, engagement_id: str) -> Path:
    """Get directory path for an engagement."""
    path = self.base_dir / "engagements" / engagement_id  # No sanitization
    path.mkdir(parents=True, exist_ok=True)
    return path
```

**Fix:** Validate that `engagement_id` contains only safe characters (alphanumeric, hyphens, underscores) and does not contain path separators or relative path components:

```python
import re

def _engagement_dir(self, engagement_id: str) -> Path:
    if not re.match(r'^[a-zA-Z0-9_\-]+$', engagement_id):
        raise ValueError(f"Invalid engagement ID: {engagement_id}")
    path = self.base_dir / "engagements" / engagement_id
    # Verify the resolved path is under base_dir
    if not path.resolve().is_relative_to(self.base_dir.resolve()):
        raise ValueError("Path traversal detected")
    path.mkdir(parents=True, exist_ok=True)
    return path
```

---

### FINDING-13: Error Messages Leak Internal Implementation Details

**Severity:** LOW
**File:** `F:\Portfolio\Portfolio\scope-tracker\stripe\invoicing.py`, lines 137-139 and 225-227; `mcp/server.py`, lines 460-462
**Category:** Information Disclosure

**Description:** Exception handlers catch broad `Exception` types and either re-raise with the full error message or return the raw error string to the caller. In the Stripe invoicing service, `str(e)` from Stripe API errors could reveal internal Stripe customer IDs, invoice details, or configuration issues. In the MCP server, error details are returned as JSON to the tool caller.

**Code Evidence:**
```python
# stripe/invoicing.py line 137-139
except Exception as e:
    logger.error(f"Failed to create invoice: {str(e)}")
    raise  # Propagates full stack trace to caller

# stripe/invoicing.py line 227
return {"status": "error", "message": str(e)}  # Leaks internal error details

# mcp/server.py line 462
return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
```

**Fix:** Return generic error messages to external callers while logging the full error internally:

```python
except Exception as e:
    logger.error(f"Failed to create invoice: {str(e)}", exc_info=True)
    return {"status": "error", "message": "Invoice creation failed. Contact support."}
```

---

### FINDING-14: Missing .env.production in .gitignore Pattern and Weak JWT Default

**Severity:** LOW
**File:** `F:\Portfolio\Portfolio\scope-tracker\.gitignore`, lines 12-16; `.env.example`, lines 102-104
**Category:** Secrets Management

**Description:** Two minor issues:

1. The `.gitignore` covers `.env` and `.env.local` but does NOT cover `.env.production`. The `.env.example` file explicitly instructs users to "Copy to .env.production for production deployment" (line 3). If a developer follows this instruction, production secrets could be committed.

2. The `.env.example` suggests `JWT_SECRET=your-super-secret-key-change-in-production` as a template. The comment-like value is insufficiently distinct from a real value and developers may forget to change it. The `JWT_EXPIRES_IN=7d` is also notably long for a JWT token in an application handling financial data.

**Code Evidence:**
```ini
# .gitignore lines 12-16 -- missing .env.production
.env
.env.local
.venv/

# .env.example lines 102-104
JWT_SECRET=your-super-secret-key-change-in-production
JWT_EXPIRES_IN=7d
```

**Fix:**
1. Add `.env.production`, `.env.staging`, and `.env*.local` to `.gitignore`.
2. Use a startup check that rejects known placeholder JWT secrets.
3. Reduce `JWT_EXPIRES_IN` to `1h` or `4h` for a financial application, and implement refresh tokens.

---

## Summary Table

| ID | Severity | Category | File | Line(s) | Title |
|----|----------|----------|------|---------|-------|
| FINDING-01 | CRITICAL | Payment Security | `stripe/invoicing.py` | 555-566 | Webhook endpoint processes events without signature verification |
| FINDING-02 | CRITICAL | Auth / Multi-Tenant | `stripe/invoicing.py`, `trigger-jobs/*.ts` | 28-31, 58-61, 35-38 | Server-side operations use anon key instead of service role key |
| FINDING-03 | CRITICAL | XSS | `export/change_order_renderer.py` | 287-312 | Stored XSS in HTML change order renderer |
| FINDING-04 | CRITICAL | Hardcoded Secrets | `.replit` | 15-23 | Placeholder credentials committed in repository |
| FINDING-05 | HIGH | Multi-Tenant | `supabase/migrations/001_initial_schema.sql` | 262-336 | RLS policy gaps allow cross-tenant data leakage |
| FINDING-06 | HIGH | Authentication | `stripe/invoicing.py` | 527-566 | No authentication on API endpoint handlers |
| FINDING-07 | HIGH | Multi-Tenant | `n8n/*.json` | multiple | n8n workflows use anon key without tenant scoping |
| FINDING-08 | HIGH | Multi-Tenant | `mcp/server.py` | 452-541 | MCP server accepts tenant ID from client without validation |
| FINDING-09 | MEDIUM | Infrastructure | `.env.example` | 93 | TLS certificate verification disabled |
| FINDING-10 | MEDIUM | Authentication | `vercel.json` | 38-47 | Cron endpoints lack authentication |
| FINDING-11 | MEDIUM | Data Exposure | `trigger-jobs/*.ts`, `stripe/invoicing.py` | multiple | Overly broad SELECT * queries expose all column data |
| FINDING-12 | MEDIUM | Input Validation | `storage/json_store.py` | 161-165 | Path traversal risk in JSON store file operations |
| FINDING-13 | LOW | Info Disclosure | `stripe/invoicing.py`, `mcp/server.py` | multiple | Error messages leak internal implementation details |
| FINDING-14 | LOW | Secrets Management | `.gitignore`, `.env.example` | multiple | Missing .env.production in gitignore and weak JWT defaults |

---

## Positive Observations

The following security practices were implemented correctly and are worth noting:

1. **Row-Level Security enabled on all tables.** The Supabase migration enables RLS on every table and revokes default public access (`REVOKE ALL ON ALL TABLES IN SCHEMA PUBLIC FROM PUBLIC`). The policy structure is comprehensive even if it has scoping gaps.

2. **No hardcoded production secrets.** No live Stripe keys (`sk_live_*`), real Supabase keys, or actual API tokens were found committed in the codebase. The `.env.example` uses clearly-marked placeholder values.

3. **Stripe webhook signature verification function exists.** The `verify_stripe_webhook()` function at line 504 of `stripe/invoicing.py` correctly uses `stripe.Webhook.construct_event()` to validate signatures. The issue is that it is not called, not that it is absent.

4. **Immutable audit trail.** The `drift_events` table and `audit_log` table in the database schema provide an immutable record of all drift detections and data changes.

5. **Input validation on CSV imports.** The `time_entry_importer.py` validates required fields, parses dates with explicit format strings, and validates numeric values before processing.

6. **React dashboard uses no dangerouslySetInnerHTML.** The JSX dashboard component uses React's built-in escaping for all rendered values, avoiding XSS in the frontend.

7. **Environment variables for all secrets.** Production configuration in `vercel.json` references Vercel environment secrets (`@supabase_url`, `@stripe_api_key`, etc.) rather than inline values.

---

## Remediation Priority

**Immediate (before any production deployment):**
- FINDING-01: Wire up webhook signature verification
- FINDING-02: Switch server-side processes to service role key
- FINDING-04: Add `.replit` to `.gitignore`
- FINDING-06: Add authentication to API endpoints

**Short-term (within 1-2 weeks):**
- FINDING-03: Escape HTML output in change order renderer
- FINDING-05: Fix RLS policy firm-scoping gaps
- FINDING-07: Add tenant filtering to n8n workflows
- FINDING-08: Derive tenant ID from auth context in MCP server

**Medium-term (within 1 month):**
- FINDING-09: Remove TLS disable from .env.example
- FINDING-10: Add cron endpoint authentication
- FINDING-11: Replace SELECT * with explicit column lists
- FINDING-12: Sanitize engagement IDs in JSON store

**Low priority:**
- FINDING-13: Sanitize error messages in responses
- FINDING-14: Expand .gitignore and tighten JWT configuration
