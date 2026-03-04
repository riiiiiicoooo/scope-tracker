-- Scope Tracker Initial Schema
-- Handles engagements, deliverables, time entries, drift detection, and change orders

-- Enable UUID extension
create extension if not exists "uuid-ossp";

-- Enable JSON schema validation
create extension if not exists "jsonschema";

-- Enum types
create type engagement_type as enum ('fixed_fee', 'hourly', 'mixed');
create type fee_structure as enum ('flat_rate', 'milestone', 'phase_based');
create type deliverable_status as enum ('not_started', 'in_progress', 'completed', 'on_hold');
create type time_entry_category as enum (
  'deliverable_work',
  'client_management',
  'unscoped_work',
  'admin',
  'other'
);
create type drift_severity as enum ('info', 'warning', 'critical');
create type change_order_status as enum (
  'draft',
  'sent_to_client',
  'client_review',
  'approved',
  'rejected',
  'billed',
  'complete'
);

-- Firms table (multi-tenant support)
create table firms (
  id uuid primary key default uuid_generate_v4(),
  name text not null,
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now(),
  blended_hourly_rate numeric(10, 2) default 250.00
);

-- Users table with role-based access
create table users (
  id uuid primary key default uuid_generate_v4(),
  firm_id uuid not null references firms(id) on delete cascade,
  email text not null,
  full_name text not null,
  role text not null check (role in ('partner', 'associate', 'staff', 'admin')),
  created_at timestamp with time zone default now(),
  is_active boolean default true,
  unique(firm_id, email)
);

-- Clients table
create table clients (
  id uuid primary key default uuid_generate_v4(),
  firm_id uuid not null references firms(id) on delete cascade,
  name text not null,
  contact_email text,
  contact_phone text,
  industry text,
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now()
);

-- Engagements table
create table engagements (
  id uuid primary key default uuid_generate_v4(),
  firm_id uuid not null references firms(id) on delete cascade,
  client_id uuid not null references clients(id) on delete cascade,
  matter_name text not null,
  matter_type text,
  engagement_type engagement_type not null,
  fee_structure fee_structure,
  total_budget numeric(12, 2) not null,
  estimated_hours integer not null,
  blended_hourly_rate numeric(10, 2),
  owner_id uuid not null references users(id),
  team_members uuid[] default array[]::uuid[],
  start_date date not null,
  estimated_completion_date date not null,
  actual_completion_date date,
  scope_document text, -- engagement letter or scope description
  notes text,
  is_active boolean default true,
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now(),
  check (total_budget > 0),
  check (estimated_hours > 0)
);

-- Scoped Deliverables table
create table scoped_deliverables (
  id uuid primary key default uuid_generate_v4(),
  engagement_id uuid not null references engagements(id) on delete cascade,
  title text not null,
  description text,
  estimated_hours integer not null,
  assigned_to uuid references users(id),
  status deliverable_status default 'not_started',
  start_date date,
  estimated_completion_date date not null,
  actual_completion_date date,
  notes text,
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now(),
  check (estimated_hours > 0)
);

-- Time Entries table (from external systems)
create table time_entries (
  id uuid primary key default uuid_generate_v4(),
  engagement_id uuid not null references engagements(id) on delete cascade,
  deliverable_id uuid references scoped_deliverables(id) on delete set null,
  logged_by_id uuid not null references users(id),
  entry_date date not null,
  hours numeric(5, 2) not null,
  description text,
  category time_entry_category,
  is_billable boolean default true,
  -- External system tracking
  source_system text, -- 'clio', 'practicepanther', 'manual'
  source_id text, -- external system ID
  source_data jsonb, -- raw entry data from external system
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now(),
  check (hours > 0 and hours <= 24),
  unique(engagement_id, source_system, source_id)
);

-- Drift Events table (immutable audit trail)
create table drift_events (
  id uuid primary key default uuid_generate_v4(),
  engagement_id uuid not null references engagements(id) on delete cascade,
  drift_type text not null check (drift_type in ('budget_overrun', 'unscoped_work', 'timeline_slip', 'trend_acceleration')),
  severity drift_severity not null,
  detected_at timestamp with time zone default now(),
  unscoped_hours numeric(8, 2),
  unscoped_amount numeric(12, 2),
  budget_consumed_percent numeric(5, 2),
  deliverable_ids uuid[],
  related_time_entries uuid[],
  alert_sent_to uuid[], -- array of user IDs
  notes text,
  created_at timestamp with time zone default now()
);

-- Change Orders table
create table change_orders (
  id uuid primary key default uuid_generate_v4(),
  engagement_id uuid not null references engagements(id) on delete cascade,
  drift_event_id uuid references drift_events(id) on delete set null,
  created_by_id uuid not null references users(id),
  status change_order_status default 'draft',
  title text not null,
  description text,
  scope_additions text, -- markdown formatted list of new scope
  estimated_additional_hours integer not null,
  estimated_additional_cost numeric(12, 2) not null,
  revised_total_budget numeric(12, 2) not null,
  revised_completion_date date,
  client_approval_date timestamp with time zone,
  approved_by_id uuid references users(id),
  rejection_reason text,
  stripe_invoice_id text, -- linked to Stripe invoice
  payment_status text check (payment_status in ('unpaid', 'draft', 'open', 'paid', 'failed')),
  sent_to_client_at timestamp with time zone,
  notes text,
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now(),
  check (estimated_additional_hours > 0),
  check (estimated_additional_cost > 0),
  check (revised_total_budget > 0)
);

-- Change Order Line Items (for detailed invoicing)
create table change_order_items (
  id uuid primary key default uuid_generate_v4(),
  change_order_id uuid not null references change_orders(id) on delete cascade,
  description text not null,
  quantity numeric(8, 2) not null,
  unit_cost numeric(10, 2) not null,
  amount numeric(12, 2) not null,
  created_at timestamp with time zone default now()
);

-- Email delivery log
create table email_logs (
  id uuid primary key default uuid_generate_v4(),
  engagement_id uuid references engagements(id) on delete set null,
  drift_event_id uuid references drift_events(id) on delete set null,
  change_order_id uuid references change_orders(id) on delete set null,
  email_type text not null, -- 'drift_alert', 'change_order_ready', 'weekly_digest'
  recipient_emails text[] not null,
  subject text not null,
  status text not null check (status in ('queued', 'sent', 'failed')),
  error_message text,
  sent_at timestamp with time zone,
  created_at timestamp with time zone default now()
);

-- Audit log for change tracking
create table audit_log (
  id uuid primary key default uuid_generate_v4(),
  table_name text not null,
  record_id uuid not null,
  action text not null check (action in ('INSERT', 'UPDATE', 'DELETE')),
  changed_by_id uuid references users(id),
  old_values jsonb,
  new_values jsonb,
  created_at timestamp with time zone default now()
);

-- Create indexes for performance
create index idx_engagements_firm_id on engagements(firm_id);
create index idx_engagements_owner_id on engagements(owner_id);
create index idx_engagements_client_id on engagements(client_id);
create index idx_engagements_is_active on engagements(is_active);
create index idx_scoped_deliverables_engagement_id on scoped_deliverables(engagement_id);
create index idx_scoped_deliverables_status on scoped_deliverables(status);
create index idx_time_entries_engagement_id on time_entries(engagement_id);
create index idx_time_entries_deliverable_id on time_entries(deliverable_id);
create index idx_time_entries_entry_date on time_entries(entry_date);
create index idx_time_entries_source on time_entries(source_system, source_id);
create index idx_drift_events_engagement_id on drift_events(engagement_id);
create index idx_drift_events_severity on drift_events(severity);
create index idx_drift_events_detected_at on drift_events(detected_at);
create index idx_change_orders_engagement_id on change_orders(engagement_id);
create index idx_change_orders_status on change_orders(status);
create index idx_change_orders_stripe_invoice_id on change_orders(stripe_invoice_id);
create index idx_users_firm_id on users(firm_id);
create index idx_clients_firm_id on clients(firm_id);

-- Row-Level Security Policies
alter table firms enable row level security;
alter table users enable row level security;
alter table clients enable row level security;
alter table engagements enable row level security;
alter table scoped_deliverables enable row level security;
alter table time_entries enable row level security;
alter table drift_events enable row level security;
alter table change_orders enable row level security;
alter table change_order_items enable row level security;

-- Firms: Only admins can view/edit their own firm
create policy "firms_select_own" on firms for select
  using (id in (select firm_id from users where id = auth.uid()));

create policy "firms_update_own" on firms for update
  using (id in (select firm_id from users where id = auth.uid()));

-- Users: Can view own profile, partners see all firm members
create policy "users_select_self" on users for select
  using (id = auth.uid() or firm_id in (
    select firm_id from users where id = auth.uid() and role = 'partner'
  ));

-- Clients: Partners see all, others see assigned
create policy "clients_select" on clients for select
  using (firm_id in (select firm_id from users where id = auth.uid()));

-- Engagements: Partners see all, associates see assigned
create policy "engagements_select_partner" on engagements for select
  using (
    firm_id in (select firm_id from users where id = auth.uid()) and
    (owner_id = auth.uid() or auth.uid() in (select id from users where role = 'partner'))
  );

create policy "engagements_select_associate" on engagements for select
  using (
    auth.uid() = any(team_members) or
    owner_id = auth.uid()
  );

create policy "engagements_insert" on engagements for insert
  with check (owner_id in (select id from users where id = auth.uid()));

create policy "engagements_update" on engagements for update
  using (owner_id = auth.uid() or auth.uid() in (
    select id from users where firm_id = engagements.firm_id and role = 'partner'
  ));

-- Scoped Deliverables: Same as engagement access
create policy "deliverables_select" on scoped_deliverables for select
  using (engagement_id in (select id from engagements));

create policy "deliverables_insert" on scoped_deliverables for insert
  with check (engagement_id in (
    select id from engagements where owner_id = auth.uid()
  ));

-- Time Entries: Logged by associates, visible to partners
create policy "time_entries_insert_own" on time_entries for insert
  with check (logged_by_id = auth.uid());

create policy "time_entries_select" on time_entries for select
  using (
    engagement_id in (
      select id from engagements where auth.uid() = any(team_members)
    ) or
    engagement_id in (
      select id from engagements where owner_id = auth.uid() or
      auth.uid() in (select id from users where role = 'partner')
    )
  );

-- Drift Events: Partners see all in their firm, associates see related
create policy "drift_events_select" on drift_events for select
  using (
    engagement_id in (
      select id from engagements where
      auth.uid() in (select id from users where role = 'partner') or
      auth.uid() = owner_id
    )
  );

-- Change Orders: Partners see all, associates see assigned
create policy "change_orders_select" on change_orders for select
  using (
    engagement_id in (
      select id from engagements where
      auth.uid() in (select id from users where role = 'partner') or
      auth.uid() = owner_id
    )
  );

create policy "change_orders_insert" on change_orders for insert
  with check (created_by_id = auth.uid());

create policy "change_orders_update" on change_orders for update
  using (
    created_by_id = auth.uid() or
    approved_by_id = auth.uid() or
    engagement_id in (
      select id from engagements where
      auth.uid() in (select id from users where role = 'partner')
    )
  );

-- Revoke default public access
revoke all on all tables in schema public from public;

-- Grant appropriate roles (to be configured per deployment)
grant usage on schema public to postgres, authenticated;
grant all on all tables in schema public to postgres;
grant all on all sequences in schema public to postgres;
grant all on all functions in schema public to postgres;
