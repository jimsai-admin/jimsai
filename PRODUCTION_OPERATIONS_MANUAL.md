# JimsAI Production Operations Guide

## Table of Contents
1. [Deployment Procedures](#deployment-procedures)
2. [Day-to-Day Operations](#day-to-day-operations)
3. [Monitoring & Alerting](#monitoring--alerting)
4. [Incident Response](#incident-response)
5. [Training Cycle Management](#training-cycle-management)
6. [Scaling Strategies](#scaling-strategies)
7. [Troubleshooting](#troubleshooting)

---

## Deployment Procedures

### Pre-Deployment Checklist

```bash
# 1. Run production readiness validation
python scripts/production_readiness.py

Expected output: ✅ PRODUCTION READY
Pass rate should be ≥95%

# 2. Run training readiness validation
python scripts/training_readiness.py

Expected output: 🚀 TRAINING READY
Pass rate should be ≥90%

# 3. Verify all providers are healthy
python scripts/check_provider_health.py

Expected: 6/7 providers ✅ (Vectorize can be ⚠️)

# 4. Run integration tests
python scripts/test_production_integration.py

Expected: All real providers verified and operational

# 5. Database schema check
python scripts/apply_phase5_migration.py --validate

Expected: All tables exist and indexed

# 6. Load test
python scripts/load_test.py --users 50 --duration 600 --ramp-up 60

Expected: 
- P95 latency <3s
- Error rate <1%
- Throughput >10 QPS
```

### Staging Deployment

```bash
# Set environment
export JIMSAI_ENV=staging
export JIMSAI_LOG_LEVEL=INFO

# Deploy
python scripts/build_phase5.py --full

# Seed test data
python scripts/seed_staging_data.py --workspaces 3 --queries-per-workspace 100

# Warm up cache
python scripts/warmup_cache.py --workspace all

# Smoke test
curl -H "Authorization: Bearer $TEST_TOKEN" \
  http://api.staging.jimsai.local:8000/api/health

# Monitor for 24 hours
# - Check metrics dashboard
# - Monitor error logs
# - Track latencies
# - Verify no data corruption
```

### Production Deployment

```bash
# 1. Pre-deployment
export JIMSAI_ENV=production
export JIMSAI_LOG_LEVEL=WARN

# 2. Database backup
python scripts/backup_database.py --full

# 3. Health check
python scripts/check_provider_health.py --timeout 30

# 4. Deploy
python scripts/build_phase5.py --full --scale 10

# 5. Smoke test
curl -H "Authorization: Bearer $PROD_TOKEN" \
  http://api.jimsai.local:8000/api/health

# 6. Gradual rollout
python scripts/gradual_rollout.py --initial-users 100 --ramp-rate 1.5 --duration 3600

# 7. Monitor
python scripts/monitor_production.py --dashboard-port 8001
```

### Rollback Procedure

```bash
# If critical issue detected:
python scripts/rollback.py --to-version previous

# Verify rollback
python scripts/check_provider_health.py --timeout 10
curl http://api.jimsai.local:8000/api/health

# Notify users
python scripts/send_notification.py \
  --type MAINTENANCE_COMPLETE \
  --message "Service restored. Investigation ongoing."
```

---

## Day-to-Day Operations

### Daily Morning Checklist

```bash
#!/bin/bash
# run at 6:00 AM daily

# 1. Check all systems
python scripts/system_health.py --full

# 2. Review error logs from previous 24h
python scripts/analyze_logs.py \
  --filter ERROR \
  --time-range 24h \
  --top-errors 10

# 3. Check provider health
python scripts/check_provider_health.py

# 4. Verify backup completed
ls -lh logs/backups/ | tail -5

# 5. Check quota status
python scripts/quota_status.py --show-high-usage

# 6. Review cost metrics
python scripts/cost_analysis.py --period daily

# 7. Send daily report
python scripts/send_daily_report.py
```

### Weekly Operations

```bash
# Monday morning

# 1. Review week metrics
python scripts/metrics_report.py --period weekly --save

# 2. Analyze training data quality
python scripts/sppe_quality_report.py

# 3. Check workspace personalization progress
python scripts/personalization_report.py

# 4. Review user feedback
python scripts/feedback_report.py --top-issues 20

# 5. Plan next training cycle
python scripts/plan_training_cycle.py --workspace all

# 6. Update documentation
# - Note any new patterns
# - Document workarounds
# - Update runbooks
```

### Monthly Operations

```bash
# 1st of month

# 1. Generate monthly metrics
python scripts/metrics_report.py --period monthly

# 2. Review cost breakdown
python scripts/cost_analysis.py --period monthly --by-provider

# 3. Archive old data
python scripts/archive_logs.py --older-than 30d

# 4. Validate compliance
python scripts/compliance_check.py

# 5. Plan capacity for next month
python scripts/capacity_planning.py --forecast 30d

# 6. Executive summary
python scripts/executive_summary.py --send-email
```

---

## Monitoring & Alerting

### Key Metrics to Monitor

**Availability:**
```
Target: 99.9% uptime
Alert if: <99% over 1 hour
```

**Latency:**
```
Target: P95 < 3s
Alert if: P95 > 5s or P99 > 10s
```

**Errors:**
```
Target: <0.1% error rate
Alert if: >1% errors over 5 minutes
```

**Providers:**
```
Target: 6/7 healthy
Alert if: Any provider unhealthy for >5 min
```

**Cache Hit Rate:**
```
Target: >60%
Alert if: <50% (indicates retrieval degradation)
```

**Costs:**
```
Target: <$0.01 per query avg
Alert if: >$0.02 per query (runaway costs)
```

### Setting Up Prometheus Monitoring

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: jimsai
    static_configs:
      - targets: ['localhost:8000']

  - job_name: postgres
    static_configs:
      - targets: ['localhost:5432']

  - job_name: redis
    static_configs:
      - targets: ['localhost:6379']
```

### Alert Rules

```yaml
# alerts.yml
groups:
  - name: jimsai
    interval: 5s
    rules:
      - alert: HighErrorRate
        expr: rate(requests_total{status="error"}[5m]) > 0.01
        for: 5m
        annotations:
          summary: "High error rate: {{ $value }}"
      
      - alert: HighLatency
        expr: histogram_quantile(0.95, latency_seconds) > 5
        for: 5m
        annotations:
          summary: "P95 latency > 5s: {{ $value }}"
      
      - alert: ProviderDown
        expr: provider_health{status="down"} == 1
        for: 5m
        annotations:
          summary: "Provider {{ $labels.provider }} is down"
      
      - alert: LowCacheHitRate
        expr: cache_hit_rate < 0.5
        for: 30m
        annotations:
          summary: "Cache hit rate dropped to {{ $value }}"
```

### Dashboard Setup

```bash
# Import Grafana dashboard
python scripts/setup_grafana_dashboards.py

Dashboards created:
- System Health Overview
- Provider Status
- Query Performance
- Training Progress
- Cost Analysis
- User Activity
- Error Tracking
```

---

## Incident Response

### 1. Provider Outage

**Detection:**
```
Alert: ProviderDown for Groq
```

**Response:**
```bash
# 1. Assess impact
python scripts/assess_outage.py --provider groq

# 2. Notify team
python scripts/send_alert.py \
  --type CRITICAL \
  --channel slack \
  --message "Groq provider down - fallback to cache"

# 3. Switch to fallback
python scripts/failover_to_memory.py

# 4. Monitor fallback performance
python scripts/monitor_fallback.py

# 5. Update status page
python scripts/update_status_page.py \
  --status DEGRADED \
  --message "Using cache-only mode"

# 6. Contact provider
# - Check status page
# - Submit support ticket
# - Wait for restoration

# 7. Recovery
# Monitor until restored, then:
python scripts/validate_provider_recovery.py --provider groq
```

### 2. High Error Rate

**Detection:**
```
Alert: Error rate > 1% for 5 minutes
```

**Response:**
```bash
# 1. Get error details
python scripts/analyze_errors.py --last-hour --group-by type | head -20

# 2. Check provider health
python scripts/check_provider_health.py

# 3. Check resource usage
python scripts/check_resources.py

# 4. Check recent deployments
git log --oneline -5

# 5. Identify root cause
python scripts/root_cause_analysis.py

Possible causes:
- Provider rate limit hit → implement backoff
- Memory shortage → increase resources
- Query parsing failure → check T1 model
- Database connection pool exhausted → check connections

# 6. Fix and validate
python scripts/validate_fix.py
```

### 3. Data Integrity Issue

**Detection:**
```
Alert: Workspace data inconsistency detected
```

**Response:**
```bash
# 1. Isolate affected workspace
python scripts/isolate_workspace.py --id ws_affected

# 2. Assess scope
python scripts/audit_workspace.py --id ws_affected

# 3. Notify user
python scripts/notify_user.py \
  --workspace ws_affected \
  --message "Investigating data inconsistency"

# 4. Review event log
python scripts/replay_events.py \
  --workspace ws_affected \
  --since "2026-05-31 14:00:00" \
  --until "2026-05-31 15:30:00"

# 5. Determine if recovery needed
# If no critical data lost, continue monitoring
# If data lost, restore from backup:

python scripts/restore_backup.py \
  --workspace ws_affected \
  --timestamp "2026-05-31 13:00:00"

# 6. Validate restoration
python scripts/validate_workspace.py --id ws_affected

# 7. Enable workspace
python scripts/enable_workspace.py --id ws_affected
```

### 4. Runaway Costs

**Detection:**
```
Alert: Daily cost exceeds budget
```

**Response:**
```bash
# 1. Identify cost spike source
python scripts/analyze_costs.py --period last-24h --detail

# 2. Find high-usage queries
python scripts/find_expensive_queries.py --top 50

# 3. Identify culprit
python scripts/trace_query.py --request-id $REQUEST_ID

# 4. Possible causes and fixes:
# - Provider rate limit issue → check provider logs
# - Query loop → implement rate limiting
# - Inefficient retrieval → optimize indexes
# - Cascade failures → implement circuit breaker

# 5. Apply temporary fix
# E.g., rate limit aggressive workspace:
python scripts/apply_rate_limit.py \
  --workspace ws_expensive \
  --limit 100-per-hour

# 6. Implement permanent fix
# - Optimize retrieval (add cache)
# - Improve skip logic (raise thresholds)
# - Fix bug (deploy patch)

# 7. Monitor cost recovery
python scripts/monitor_costs.py --threshold $BUDGET
```

---

## Training Cycle Management

### Initiating a Training Cycle

```bash
# Check readiness
python scripts/training_readiness.py

# If ready:
python scripts/initiate_training_cycle.py

Steps:
1. Collect SPPE pairs (last 7 days)
2. Validate quality (must be >0.80 average)
3. Create Kaggle dataset
4. Upload to Kaggle
5. Trigger community training
6. Monitor training progress
7. Evaluate new model
8. If better: schedule hot-swap
9. If worse: investigate and retry
```

### Monitoring Training Progress

```bash
# Check Kaggle notebook status
python scripts/check_kaggle_status.py

# Monitor training metrics
python scripts/monitor_training.py \
  --metric accuracy \
  --metric loss \
  --metric precision \
  --metric recall

# Expected improvements (per cycle):
# - Accuracy: +0.5-2%
# - SPPE quality: +0.01-0.03
# - Skip rate: +2-5%
```

### Hot-Swapping New Models

```bash
# 1. Validate new model on held-out test set
python scripts/validate_model.py --model new --threshold 0.05

# 2. Compare against production
python scripts/compare_models.py \
  --baseline production \
  --candidate new

Expected results (must be true for hot-swap):
- Accuracy improvement > 0%
- Latency impact < 10%
- Error rate not increased

# 3. If validation passes, hot-swap
python scripts/hot_swap_model.py \
  --from production \
  --to new \
  --gradual-rollout 20%

# 4. Monitor after swap
python scripts/monitor_swap.py --duration 3600

# 5. If issues detected, automatic rollback
# OR
python scripts/manual_rollback.py --to production

# 6. Analysis
python scripts/analyze_swap.py
```

---

## Scaling Strategies

### Vertical Scaling (Single Machine)

**When to scale up:**
- CPU utilization >80% sustained
- Memory >75% sustained
- Latency degradation

**How to scale:**
```bash
# 1. Determine resource needs
python scripts/resource_calculator.py --users 500 --qps 50

# 2. Resize server
# (cloud provider specific)

# 3. Restart with new limits
python scripts/restart_with_resources.py \
  --cpu 8 \
  --memory 32g \
  --connections 500

# 4. Verify
python scripts/verify_scaling.py
```

### Horizontal Scaling (Multiple Machines)

**When to scale out:**
- Single machine approach not meeting SLA
- Need for rolling updates
- Geographic distribution needed

**How to scale:**
```bash
# 1. Set up load balancer
python scripts/setup_load_balancer.py \
  --algorithm round-robin \
  --health-check-interval 5s

# 2. Deploy API servers
python scripts/deploy_api_servers.py \
  --count 3 \
  --region us-east-1

# 3. Set up database replication
python scripts/setup_db_replication.py \
  --primary db1 \
  --replicas db2,db3

# 4. Set up Redis cluster
python scripts/setup_redis_cluster.py --nodes 3

# 5. Verify
python scripts/verify_cluster.py

# 6. Test failover
python scripts/test_failover.py
```

### Database Scaling

**For retrieval performance:**
```bash
# 1. Add indexes on hot queries
python scripts/optimize_indexes.py

# 2. Set up materialized views
python scripts/create_materialized_views.py

# 3. Enable query caching
python scripts/enable_query_cache.py

# 4. Monitor query performance
python scripts/monitor_query_perf.py
```

---

## Troubleshooting

### Common Issues and Fixes

**Issue: High Latency**
```bash
# 1. Check CPU/Memory
python scripts/check_resources.py

# 2. Check database connections
python scripts/check_db_connections.py

# 3. Check provider latency
python scripts/check_provider_health.py

# 4. Check cache hit rate
SELECT COUNT(*) as total_queries,
       SUM(CASE WHEN cache_hit THEN 1 ELSE 0 END) as cache_hits,
       100.0 * SUM(CASE WHEN cache_hit THEN 1 ELSE 0 END) / COUNT(*) as hit_rate
FROM request_audit
WHERE created_at > NOW() - INTERVAL '1 hour';

# 5. If cache hit rate low, investigate retrieval quality
python scripts/analyze_retrieval_misses.py
```

**Issue: High Error Rate**
```bash
# 1. Get error breakdown
SELECT error_type, COUNT(*) as count
FROM error_log
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY error_type
ORDER BY count DESC;

# 2. Check specific error
SELECT * FROM error_log
WHERE error_type = 'specific_error'
LIMIT 5;

# 3. Fix based on error type
# - ValidationError → check input validation
# - DatabaseError → check database connection
# - ProviderError → check provider status
# - TimeoutError → check resource usage
```

**Issue: Provider Failures**
```bash
# 1. Check provider status page
curl https://status.provider.com/api/status

# 2. Check provider health from our side
python scripts/check_provider_health.py --verbose

# 3. Check recent API calls
python scripts/trace_provider_calls.py --provider groq --last-hour

# 4. If provider rate limited
# - Implement exponential backoff
# - Reduce request rate
# - Batch requests

# 5. If provider down
# - Fall back to cache
# - Fall back to other providers
# - Degrade gracefully
```

**Issue: Memory Leaks**
```bash
# 1. Monitor memory usage
python scripts/monitor_memory.py --interval 60

# 2. Generate memory profile
python scripts/profile_memory.py --duration 3600

# 3. Analyze top memory consumers
python scripts/analyze_memory_profile.py

# 4. Fix and verify
# - Check for unclosed connections
# - Check for unbounded caches
# - Check for circular references

python scripts/verify_memory_fix.py
```

---

## Backup and Disaster Recovery

### Daily Backup

```bash
# Automated 1 AM daily
python scripts/backup_database.py --full --compress

Backups kept:
- Last 7 days: daily
- Last 30 days: weekly
- Last 365 days: monthly
```

### Restore Procedure

```bash
# For full workspace restore
python scripts/restore_backup.py \
  --workspace ws_affected \
  --timestamp "2026-05-31 12:00:00"

# For specific table restore
python scripts/restore_table.py \
  --table workspace_metrics \
  --timestamp "2026-05-31 12:00:00"

# Verify after restore
python scripts/validate_restore.py --workspace ws_affected
```

---

## Performance Tuning

### Query Performance Optimization

```bash
# Analyze slow queries
SELECT query, count, mean_time, max_time
FROM pg_stat_statements
WHERE mean_time > 100  -- queries taking >100ms
ORDER BY mean_time DESC
LIMIT 20;

# Create indexes on frequently filtered columns
CREATE INDEX idx_sppe_workspace_quality 
  ON sppe_pairs(workspace_id, sppe_quality DESC);

# Analyze and reindex
ANALYZE;
REINDEX;
```

### Memory Optimization

```bash
# Reduce workspace adapter memory
python scripts/optimize_adapter_memory.py

# Limit cache size
python scripts/configure_cache.py --max-size 1gb

# Implement LRU eviction
python scripts/configure_cache_eviction.py --strategy lru
```

---

## Conclusion

JimsAI production operations require:
1. ✅ Daily monitoring and alerting
2. ✅ Weekly metric reviews
3. ✅ Monthly capacity planning
4. ✅ Quarterly training cycles
5. ✅ Clear incident response procedures
6. ✅ Continuous optimization

**On-Call Playbook:**
- [Incident Response](#incident-response)
- [Troubleshooting](#troubleshooting)
- [Common Operations](#day-to-day-operations)

---

**Version:** 1.0  
**Last Updated:** May 31, 2026  
**Status:** Production Ready
