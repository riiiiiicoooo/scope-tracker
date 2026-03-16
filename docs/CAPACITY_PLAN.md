# Scope Tracker - Capacity Plan

## Executive Summary
Scope Tracker is a billing-accuracy system serving law firms. This plan quantifies infrastructure, database, and team capacity under current load, 2x growth, and 10x growth scenarios.

---

## Current State (Q1 2026)

### Usage Metrics
- **Active Law Firms:** 45
- **Cases Tracked:** ~12,000 (267 cases/firm average)
- **Scope Change Events/Day:** 2,400
- **Billing Reconciliation Queries/Day:** 18,000
- **API Throughput (p99 latency):** <500ms

### Infrastructure
| Component | Current | Monthly Cost |
|-----------|---------|--------------|
| **Web/API Servers** | 3 instances (t3.large) | $432 |
| **Database (RDS PostgreSQL)** | db.r5.xlarge (4 vCPU, 32 GB RAM) | $2,800 |
| **Object Storage (case docs)** | 250 GB | $5.75 |
| **Redis Cache** | 2 GB cluster | $180 |
| **Networking/CDN** | CloudFront + WAF | $400 |
| **Backup & DR** | Daily snapshots + cross-region | $320 |
| **Monitoring/Logging** | CloudWatch + DataDog | $500 |
| **Total Monthly** | | **$4,638** |

### Database Sizing
- **Table Size:** scope_events: 85 MB, billing_adjustments: 42 MB, audit_logs: 180 MB
- **Daily Ingestion:** ~420 MB (case docs + metadata)
- **WAL/Replication:** ~50 GB/month
- **Backup Retention:** 30 days full + 7 days incremental

### Team Capacity
| Role | Count | Utilization |
|------|-------|-------------|
| **Backend Engineers** | 2 | 85% |
| **SRE/DevOps** | 1 | 70% |
| **QA Analyst** | 1 | 80% |
| **Product Manager** | 1 | 90% |

---

## 2x Growth Scenario (12 months forward)
**Assumption:** 90 law firms, 24,000 cases, 4,800 daily events, 36,000 queries/day

### What Breaks First
1. **Database query performance** — reconciliation queries hitting >2s p99 (alerts triggering 50% slower)
2. **Storage I/O** — WAL growth to 100 GB/month; backup windows extend beyond SLA
3. **Team capacity** — SRE unable to respond to incidents within 15 min SLA; on-call burnout

### Required Infrastructure Changes
| Component | Current → 2x | Incremental Cost |
|-----------|--------------|-----------------|
| **DB Instance** | r5.xlarge → r5.2xlarge (8 vCPU, 64 GB) | +$2,800/month |
| **Read Replicas** | 0 → 2 read replicas for billing reports | +$2,800/month |
| **Web Servers** | 3 × t3.large → 5 × t3.large + ASG | +$720/month |
| **Redis** | 2 GB → 8 GB cluster | +$270/month |
| **Object Storage** | 250 GB → 500 GB | +$5/month |
| **Monitoring** | DataDog increased event volume | +$200/month |
| **Total Monthly @ 2x** | | **$11,433** (+146%) |

### Team Additions
- +1 Backend Engineer (billing system specialization)
- +0.5 SRE (on-call rotation, incident response)
- +1 QA Analyst (expanded test coverage for drift detection)
- **Cost:** ~$280K/year all-in (salary + benefits + tools)

---

## 10x Growth Scenario (24 months forward)
**Assumption:** 450 law firms, 120,000 cases, 24,000 daily events, 180,000 queries/day

### What Breaks First
1. **Schema redesign required** — current normalized schema causes join-heavy reconciliation queries to time out; migration to star schema needed
2. **Regional isolation** — data residency regulations (UK, EU, Canada) force multi-region architecture
3. **Team organization** — monolithic billing service needs decomposition (scope-service, billing-service, audit-service)
4. **Cost explosion** — infrastructure costs exceed revenue if not optimized

### Required Infrastructure Changes
| Component | Current → 10x | Incremental Cost |
|-----------|--------------|-----------------|
| **DB Tier** | r5.2xlarge → r6i.4xlarge + sharding (2 shards) | +$8,500/month |
| **Read Replicas** | 2 → 6 across regions (us-east, eu-west, ca-central) | +$9,600/month |
| **Web/API** | 5 × t3.large → 20 × t3.xlarge + multi-region ALB | +$3,600/month |
| **Cache (Redis)** | 8 GB → 64 GB distributed cache + Redis Cluster | +$1,200/month |
| **Object Storage** | 500 GB → 2.5 TB (multi-region replication) | +$50/month |
| **Elasticsearch** | 0 → dedicated cluster for audit log search | +$1,500/month |
| **Data Warehouse** | 0 → BigQuery/Snowflake for analytics | +$3,000/month |
| **DR/Backup** | Regional snapshots → continuous replication | +$2,000/month |
| **Monitoring/Observability** | DataDog → Datadog Enterprise + custom dashboards | +$500/month |
| **Total Monthly @ 10x** | | **$40,450** (+772%) |

### Database Redesign
**Current Star Schema (Normalized):**
```
scope_events → cases → firms
billing_adjustments → scope_events → contracts
```
**Required @ 10x (Fact-Dimension):**
```
fact_billing_events (date, firm_id, case_id, adjustment_amount, status, shard_key)
dim_firms | dim_cases | dim_contracts
```
- Enables parallel queries across 10 shards
- Reduces join latency from 2s to 200ms
- Estimated migration effort: 6 weeks + 2 weeks validation

### Team Scaling
| Role | Current → 10x | Notes |
|------|---|---|
| **Backend Engineers** | 2 → 8 (3 x billing domain, 2 x audit/compliance, 2 x platform, 1 x data) | Separate teams by domain |
| **SRE/Platform** | 1 → 4 (on-call rotation, regional ops, DR, cost optimization) | Multi-region management |
| **QA** | 1 → 3 (functional, regression, chaos engineering) | 10x growth = higher risk |
| **Product Manager** | 1 → 1.5 (primary + billing ops specialist) | Deeper domain expertise |
| **Data Analytics** | 0 → 2 (billing intelligence, customer success) | Support regional expansion |
| **Compliance Officer** | 0 → 1 (part-time) | Manage multi-region compliance |
| **Total Cost** | ~$400K/year → ~$1.6M/year | +300% headcount, but 900% revenue growth |

---

## Cost Optimization Strategies (All Scenarios)

### Immediate (2-4 weeks)
1. **Query optimization:** Add indexes on (firm_id, case_id, created_at) for billing reconciliation (saves 30% DB CPU)
2. **Cache warming:** Pre-load frequently-accessed cases in Redis (reduces DB reads by 40%)
3. **Log rotation:** Compress audit logs >30 days old to cold storage (saves $200/month @ 2x)

### Medium-term (2-6 months, at 2x scale)
1. **Reserved instances:** Move variable DB costs to 1-year RIs (saves 30-40% DB costs)
2. **Data partitioning:** Partition scope_events by date (monthly); archive >12 months to S3 Glacier (saves 25% DB storage)
3. **Caching strategy:** Implement 24-hour cache for readonly billing reports (reduces query load by 50%)

### Long-term (at 10x scale)
1. **Data tiering:** Hot data (current month) on fast storage; cold data (archive) on Glacier
2. **Multi-tenancy optimization:** Separate databases per region to enable local compliance
3. **API rate limiting:** Implement tiered API pricing to encourage efficient queries (reduces 10% of rogue requests)
4. **Serverless billing:** Use Lambda for async reconciliation jobs (saves 35% compute for variable workloads)

---

## Monitoring & Decision Gates

### Monthly Capacity Reviews
- Database CPU utilization: Alert if >70% sustained
- Memory usage: Alert if >80%
- Query latency (p99): Alert if >1s for billing queries
- Team utilization: Alert if >85% for >2 weeks

### Escalation Triggers → Action
| Metric | Threshold | Action |
|--------|-----------|--------|
| DB CPU | >70% × 2 weeks | Add read replicas or upgrade instance |
| Query latency | p99 >1.5s | Trigger schema optimization sprint |
| Team utilization | >85% × 2 weeks | Hire +1 engineer or reduce scope |
| Storage growth | >80% of allocated | Purchase additional storage or archive |
| Error rate | >0.5% | Incident review + root cause remediation |

