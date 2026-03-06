# Production Readiness Checklist

This checklist evaluates the production readiness of Scope Tracker across six categories. Items marked `[x]` are implemented in the current codebase. Items marked `[ ]` are not yet implemented and would need to be addressed before a production deployment handling real client billing data.

---

## Security

### Authentication & Authorization
- [ ] Implement authentication middleware (Clerk, Auth0, or Supabase Auth) for all API endpoints
- [ ] Enforce firm-level tenant scoping so attorneys see only their own firm's engagements
- [ ] Add role-based access control (partner vs. associate vs. paralegal permission levels)
- [ ] Validate tenant ID from authenticated session, not from client-supplied input (MCP server currently accepts tenant_id directly from caller)
- [ ] Add authentication to Stripe API endpoint handlers (`create_invoice_endpoint`, `payment_link_endpoint`)
- [ ] Authenticate Vercel cron endpoints using `VERCEL_CRON_SECRET` header validation
- [ ] Add webhook authentication (shared secret) for n8n time entry import endpoint

### Secrets Management
- [x] Environment variables used for all secrets (Stripe keys, Supabase keys, API tokens) via `.env.example` pattern
- [x] Vercel deployment references secrets through Vercel environment secret store (`@supabase_url`, `@stripe_api_key`, etc.)
- [ ] Add `.replit` to `.gitignore` to prevent placeholder credentials from being committed
- [ ] Add `.env.production` and `.env.staging` to `.gitignore` (currently only `.env` and `.env.local` are covered)
- [ ] Replace placeholder JWT secret with a startup check that rejects known weak values
- [ ] Rotate all placeholder API keys and tokens before production deployment

### Transport Security
- [ ] Remove `NODE_TLS_REJECT_UNAUTHORIZED=0` from `.env.example` to prevent accidental TLS bypass in production
- [ ] Add startup guard that rejects disabled TLS verification when `NODE_ENV=production`
- [ ] Enable HTTPS-only cookies for session tokens (`CSRF_COOKIE_SECURE=true` is configured in `.env.example` but not enforced in code)

### Input Validation & Injection Prevention
- [x] CSV importer validates required fields, parses dates with explicit format strings, and validates numeric values before processing
- [ ] Sanitize `engagement_id` in `JSONStore._engagement_dir()` to prevent path traversal (currently accepts unsanitized input to construct file paths)
- [ ] HTML-escape all user-controlled values in `ChangeOrderRenderer.render_html_change_order()` to prevent stored XSS (currently uses raw f-string interpolation)
- [ ] Validate and sanitize all fields used in change order document generation (client name, matter name, descriptions)

### Payment Security
- [x] Stripe webhook signature verification function exists (`verify_stripe_webhook()` using `stripe.Webhook.construct_event()`)
- [ ] Wire up the webhook signature verification in the actual `webhook_endpoint()` handler (function exists but is never called)
- [ ] Use Supabase service role key instead of anon key for server-side Stripe invoicing operations

### Data Encryption
- [ ] Encrypt sensitive client data at rest (contact information, financial details)
- [ ] Encrypt JSON engagement files on the shared drive (or restrict file-system permissions)

---

## Reliability

### High Availability & Failover
- [ ] Deploy API tier across multiple availability zones (currently single-region Vercel `iad1`)
- [ ] Implement health check endpoint with dependency verification (Supabase, Stripe connectivity)
- [ ] Add circuit breaker pattern for external API calls (Stripe, Clio, PracticePanther)
- [ ] Implement retry logic with exponential backoff for transient failures in Stripe invoice creation

### Data Backup & Recovery
- [x] `JSONStore.backup()` creates ZIP archives of all engagement data
- [x] `Makefile` includes a `backup` target for creating timestamped backups
- [ ] Automate periodic backups (daily) with retention policy
- [ ] Test and document restore procedure from ZIP backup
- [ ] Implement point-in-time recovery for Supabase database (SaaS version)
- [ ] Add backup verification (checksum validation, restore dry-run)

### Data Integrity
- [x] File-based locking (`FileLock`) for shared drive concurrent access using atomic `os.O_CREAT | os.O_EXCL` file creation
- [x] Lock timeout of 30 seconds to prevent deadlocks
- [x] `drift_history.json` is append-only, preserving historical snapshots
- [x] Change orders are stored as individual JSON files, preventing accidental overwrite of unrelated orders
- [ ] Add write-ahead logging or journaling for JSON file updates to prevent corruption on crash
- [ ] Validate JSON schema on load to detect and report corrupted files
- [ ] Use `decimal.Decimal` with `ROUND_HALF_UP` for all monetary calculations (currently uses `float`, which risks floating-point rounding errors in billing)

### Graceful Degradation
- [ ] Handle Stripe API unavailability gracefully (queue invoice creation for retry)
- [ ] Allow core scope tracking to function without Stripe, Supabase, or external API connectivity
- [ ] Add offline mode for JSON-only operation when network is unavailable

---

## Observability

### Logging
- [x] Python `logging` module configured in MCP server (`logging.basicConfig(level=logging.INFO)`)
- [x] Stripe invoicing service logs invoice creation, payment link generation, and webhook processing events
- [x] MCP server logs errors for all tool handler failures
- [ ] Add structured logging (JSON format) with consistent fields (timestamp, engagement_id, user_id, action)
- [ ] Implement request-level correlation IDs for tracing operations across modules
- [ ] Add audit logging for all state changes (time entry additions, change order status transitions, alert dismissals)
- [ ] Log all authentication and authorization decisions

### Metrics
- [ ] Track engagement-level metrics: budget consumption rate, unscoped hours accumulated, margin trends
- [ ] Track system-level metrics: API response times, drift detection scan duration, CSV import throughput
- [ ] Export metrics to a time-series store (Prometheus, Datadog, or PostHog)
- [ ] Monitor drift detection false positive rate to tune alert thresholds over time

### Error Tracking
- [x] Sentry DSN configured in `.env.example` for error tracking
- [ ] Integrate Sentry SDK in application code (DSN is configured but SDK is not imported or initialized)
- [ ] Sanitize error messages returned to clients to prevent internal implementation details from leaking (currently returns raw `str(e)` in MCP server and Stripe handlers)
- [ ] Add error classification and alerting rules (payment failures vs. data errors vs. infrastructure)

### Alerting
- [x] Email alert recipients configurable via `ALERT_EMAIL_RECIPIENTS` and `ALERT_EMAIL_CC` environment variables
- [x] Drift detection generates categorized alerts (INFO, WARNING, CRITICAL) with severity-based routing
- [ ] Implement real-time alert delivery (email, Slack) when CRITICAL drift alerts are generated
- [ ] Add on-call escalation for payment processing failures
- [ ] Monitor and alert on cron job failures (weekly digest, health check)

---

## Performance

### Caching
- [ ] Cache engagement summaries to avoid recomputing `get_summary()` on every dashboard load
- [ ] Cache team blended rate calculations (recalculate only when team composition changes)
- [ ] Implement HTTP caching headers for dashboard API responses

### Connection Management
- [ ] Implement connection pooling for Supabase database connections (SaaS version)
- [ ] Reuse `httpx.AsyncClient` instances in MCP server instead of creating per-request (clients are already stored as class attributes)
- [ ] Set appropriate timeouts on all external HTTP clients (Stripe, Supabase, Clio)

### Load Testing
- [ ] Benchmark drift detection scan performance at 100+ engagements with 500+ time entries each
- [ ] Load test CSV import with 1000+ row files from each supported timekeeping system
- [ ] Profile change order generation performance with complex theme grouping scenarios
- [ ] Measure and optimize JSON serialization/deserialization for large engagement files

### Optimization
- [x] Each engagement is stored as an independent file, allowing parallel I/O without contention between engagements
- [x] `DriftDetector` uses `_seen_triggers` set to avoid redundant alert computation
- [ ] Index time entries by deliverable_id for O(1) lookup instead of linear scan in `log_time()`
- [ ] Implement incremental drift detection (scan only new entries since last scan, not full engagement)

---

## Compliance

### Legal Billing Standards
- [ ] Implement ABA Model Rule 1.15 compliance: immutable audit trail for all time entries and budget modifications with user_id and timestamp
- [ ] Support LEDES 1998B export format for time entries and billing data (required for matter transfers)
- [ ] Support UTBMS (Uniform Task-Based Management System) activity codes for time entry categorization
- [ ] Implement trust accounting separation if handling client funds alongside billing

### Audit Trail
- [x] `drift_history.json` provides weekly snapshots of drift detection results (append-only)
- [x] Change orders record `created_at`, `created_by`, `approved_at`, `approved_by` timestamps
- [x] Time entries track `flagged` status and `flag_reason` for scope drift annotations
- [x] Supabase schema includes `audit_log` and `drift_events` tables (per security review)
- [ ] Log all user actions (view, create, update, dismiss) with user identity and timestamp
- [ ] Make audit log entries immutable (append-only table with no UPDATE or DELETE permissions)
- [ ] Record all change order status transitions (draft, partner_review, sent, approved, rejected) with timestamps

### Data Retention & Privacy
- [ ] Define and implement data retention policy (how long to keep closed engagement data, time entries, alerts)
- [ ] Implement data export for client portability (engagement transfer to another firm)
- [ ] Support data deletion requests (right to erasure) while preserving audit trail integrity
- [ ] Classify data sensitivity levels (PII in client names/contacts vs. billing data vs. engagement metadata)

### Multi-Tenant Isolation
- [x] Supabase Row-Level Security (RLS) enabled on all tables with policies for firm-based access control
- [ ] Fix RLS policy scoping gaps: partner role checks must include `firm_id` constraint to prevent cross-tenant data access
- [ ] Add firm_id filtering to all n8n workflow database queries
- [ ] Scope all MCP server queries to the authenticated user's firm

### Financial Compliance
- [ ] Use `decimal.Decimal` for all monetary calculations to avoid floating-point rounding in billing amounts
- [ ] Validate invoice amounts match change order amounts before sending to Stripe
- [ ] Implement payment reconciliation (verify Stripe payment amounts match expected change order values)
- [ ] Generate IRS-compatible billing records if required by jurisdiction

---

## Deployment

### CI/CD Pipeline
- [x] `Makefile` provides targets for test, lint, format, and demo execution
- [x] `requirements.txt` specifies development/testing dependencies (pytest, pytest-cov, ruff, mypy)
- [ ] Set up automated CI pipeline (GitHub Actions or equivalent) to run tests, linting, and type checking on every pull request
- [ ] Add integration tests that verify end-to-end flow: CSV import, drift detection, change order generation
- [ ] Enforce minimum code coverage threshold before merge
- [ ] Automate dependency vulnerability scanning (Dependabot, Snyk)

### Deployment Strategy
- [x] Vercel deployment configured with `vercel.json` (routes, builds, cron jobs, environment secrets)
- [ ] Implement blue-green or canary deployment strategy for zero-downtime releases
- [ ] Add rollback mechanism (Vercel provides instant rollback to previous deployment)
- [ ] Create staging environment that mirrors production for pre-release validation
- [ ] Document deployment runbook with step-by-step procedures

### Configuration Management
- [x] `.env.example` documents all required environment variables with descriptions and placeholder values
- [x] Feature flags for optional integrations (`ENABLE_CLIO_IMPORT`, `ENABLE_STRIPE_INVOICING`, `ENABLE_WEEKLY_DIGEST`, etc.)
- [x] Configurable drift detection thresholds via environment variables (`DRIFT_WARNING_BUDGET_PERCENT`, `UNSCOPED_WORK_THRESHOLD_HOURS`, etc.)
- [ ] Validate all required environment variables at startup and fail fast with clear error messages if any are missing
- [ ] Separate configuration for development, staging, and production environments with validation

### Database Migrations
- [ ] Version-control Supabase migration files and apply them as part of the deployment pipeline
- [ ] Test migrations against a staging database before applying to production
- [ ] Implement rollback migrations for every forward migration
- [ ] Document the JSON-to-Supabase migration path for firms transitioning from shared drive to SaaS

### Monitoring Post-Deployment
- [ ] Set up uptime monitoring for API endpoints and cron jobs
- [ ] Monitor Vercel function invocation counts and cold start latency
- [ ] Track deployment success/failure metrics
- [ ] Set up alerts for elevated error rates after deployment (canary analysis)
