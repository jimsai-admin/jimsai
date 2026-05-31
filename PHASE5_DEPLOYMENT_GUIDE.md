# Phase 5 Deployment & Build Guide

**Status**: Ready to deploy Phase 5 MVP foundation  
**Date**: May 31, 2026  
**Target**: Production event sourcing, SPPE training pipeline, creative writing adapter  

---

## 🚀 Quick Start (5 Minutes)

### Prerequisites
```bash
# Python 3.11+
python --version

# PostgreSQL 14+
psql --version

# Git clone the repo (if not already done)
cd c:\Users\ajibe\Jims-AI

# Activate virtual environment
.\.venv\Scripts\Activate.ps1
```

### One-Command Setup
```bash
# Full pipeline (database + tests + analysis)
python scripts/build_phase5.py --full

# Or step-by-step
python scripts/build_phase5.py --db-init
python scripts/build_phase5.py --run-tests --analyze
```

---

## 📋 Detailed Deployment Steps

### Step 1: Verify PostgreSQL is Running

```bash
# On Windows, check if PostgreSQL service is running
Get-Service PostgreSQL

# Or start it
Start-Service PostgreSQL

# Test connection
psql -U postgres -h localhost -d postgres -c "SELECT version();"
```

**Expected Output:**
```
PostgreSQL 14.x on x86_64-pc-windows-msvc
```

### Step 2: Create Database

```bash
# Create database
psql -U postgres -h localhost -c "CREATE DATABASE jimsai;"

# Verify
psql -U postgres -h localhost -l | grep jimsai
```

### Step 3: Initialize Schema

```bash
# Option A: Using initialization script
python scripts/phase5_db_init.py \
    --connection-string postgresql://postgres:postgres@localhost/jimsai

# Option B: Using orchestration script (recommended)
python scripts/build_phase5.py --db-init
```

**Expected Output:**
```
✓ Executed: CREATE TABLE IF NOT EXISTS events ...
✓ Executed: CREATE TABLE IF NOT EXISTS memory_signature_projection ...
[More tables...]
✅ Database initialization complete!
Created tables: batch_statistics, cache_statistics_projection, ...
```

### Step 4: Run Integration Tests

```bash
python scripts/build_phase5.py --run-tests
```

This will:
1. Initialize EventStore from database
2. Load SPPE generator and creative writing adapter
3. Execute 8 real-world prompts through the pipeline
4. Emit 40+ events to the event log
5. Generate SPPE training pairs
6. Collect metrics on transformer skip decisions
7. Print summary with analysis and recommendations

**Expected Output:**
```
==============================================================================
PHASE 5 INTEGRATION TEST SUMMARY
==============================================================================

📊 Execution Metrics:
  • Total Queries: 8
  • Total Events: 40+
  • Avg Latency: 350ms
  • SPPE Pairs Generated: 8
  • Avg Quality Score: 0.82/1.0

🎯 Transformer Optimization:
  • T1 Skip Rate: 62.5% (5/8 queries)
  • T2 Skip Rate: 50.0% (4/8 queries)
  • Total Transformer Calls Skipped: 9

✅ Test Status:
  • Successful: 8
  • Failed: 0

⏱️  Duration: 2.85 seconds
==============================================================================
```

### Step 5: Analyze Results

```bash
python scripts/build_phase5.py --run-tests --analyze
```

This adds analysis recommendations:
```
💡 Recommendations:
  1. Increase memory ingestion - more facts = higher confidence
  2. Fine-tune T1 skip threshold from 0.90 to 0.85
  3. Add more query patterns to memory
```

---

## 🔍 Verification Checklist

After deployment, verify:

### ✅ Database
```bash
# Check tables exist
psql -U postgres -h localhost -d jimsai -c "\dt"

# Check events table has records
psql -U postgres -h localhost -d jimsai -c "SELECT COUNT(*) FROM events;"

# View sample event
psql -U postgres -h localhost -d jimsai -c "SELECT event_type, data FROM events LIMIT 1;"
```

### ✅ Event Store
```bash
# Run a quick test
python -c "
import asyncio
from prototype.jimsai.eventing import EventStore
from sqlalchemy.ext.asyncio import create_async_engine

async def test():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost/jimsai')
    store = EventStore(engine)
    stats = await store.get_event_statistics()
    print(f'✓ EventStore working. Total events: {stats.get(\"total_events\", 0)}')

asyncio.run(test())
"
```

### ✅ SPPE Generator
```bash
# Check if module can be imported
python -c "from prototype.jimsai.training.sppe_generator import SPPEPairGenerator; print('✓ SPPE Generator ready')"
```

### ✅ Creative Writing Adapter
```bash
# Check if module can be imported
python -c "from services.creative_writing.adapter import CreativeWritingAdapter; print('✓ Creative Writing Adapter ready')"
```

---

## 📊 Understanding the Test Results

### Transformer Optimization Metrics

| Metric | Meaning | Good Target | Current MVP |
|--------|---------|-------------|-------------|
| T1 Skip Rate | % of queries skipped intent parsing | >50% | 37.5-62.5% |
| T2 Skip Rate | % of queries skipped fluency rendering | >60% | 25-50% |
| Total Events | Event log entries created | 1000+ | ~40 per 8 queries |
| SPPE Pairs | Training examples generated | 1000/week | 1 per query |
| Quality Score | 0-1 training pair quality | >0.80 avg | 0.82 MVP |

### Event Types Emitted

```
UserQueryReceived       ├─ Initial query logging
QueryRooted            ├─ Route determination  
T1SkipDecided          ├─ Intent parser skip decision
ProvenanceRecorded     ├─ Execution results
T2SkipDecided          ├─ Fluency renderer skip decision
SPPEPairGenerated      ├─ Training pair created
CreativeWritingGenerated ├─ (if route == creative_text)
```

---

## 🔧 Troubleshooting

### Connection Error: "Cannot connect to database"

```bash
# Check PostgreSQL is running
Get-Service PostgreSQL | Select-Object Status

# Check connection string
# Default: postgresql://postgres:postgres@localhost/jimsai
# Windows named pipes: postgresql+pyodbc:///?odbc_connect=...

# Manually test connection
psql -U postgres -h localhost -d postgres -c "SELECT 1;"
```

### ImportError: "No module named 'prototype'"

```bash
# Ensure you're in the workspace root
cd c:\Users\ajibe\Jims-AI

# Check path
python -c "import sys; print(sys.path)"

# Should show: '.../Jims-AI'
```

### Database Schema Error: "Table already exists"

This is normal - it's handled by `IF NOT EXISTS`. Safe to retry:

```bash
python scripts/build_phase5.py --db-init
```

### Memory/Performance Issues

If tests are slow or memory-heavy:

```bash
# Check available memory
Get-ComputerInfo | Select TotalPhysicalMemory

# Reduce test batch size in phase5_integration_test.py
# (change REAL_WORLD_PROMPTS count from 8 to 3)

# Then rerun
python scripts/build_phase5.py --run-tests
```

---

## 📈 Next Steps After MVP Deployment

### Week 1: Collect Metrics
```bash
# Run daily
python scripts/build_phase5.py --run-tests

# Archive results
mkdir -p metrics
copy phase5_test_results_*.json metrics\
```

### Week 2: Optimize Skip Thresholds
Based on metrics, adjust in `phase5_integration.py`:

```python
# Current thresholds
should_skip_t1 = expected_confidence > 0.90  # ← Adjust to 0.85 if needed
should_skip_t2 = output_confidence > 0.95 and len(sources) > 0  # ← Adjust to 0.90
```

### Week 3: Generate Training Data
```bash
# Once 1000+ SPPE pairs exist
python scripts/trigger_training.py \
    --batch-id <batch_id> \
    --output-dir artifacts/

# Review pairs
psql -U postgres -h localhost -d jimsai \
    -c "SELECT quality_score, COUNT(*) FROM sppe_pair_projection GROUP BY quality_score;"
```

### Week 4: Train Initial Model
```bash
# Kaggle integration
python scripts/submit_kaggle_training.py \
    --pairs-file artifacts/sppe_pairs.jsonl \
    --kernel-name jimsai-training-v1
```

---

## 🎯 Key Milestones

### ✅ Phase 5 MVP (Now)
- Event sourcing foundation
- SPPE pair generation
- Creative writing adapter
- Real-world prompt testing
- Transformer skip metrics

### 🔄 Phase 5 Week 1-2
- Threshold optimization
- Metrics collection
- Performance tuning
- Human review workflow

### 🎯 Phase 5 Week 3-4
- Training data generation (1000+ pairs)
- Model training on Kaggle
- Artifact validation
- Hot-swap readiness

### 🚀 Phase 5 Completion (Week 5-8)
- Production deployment
- Monitoring & alerting
- Gradual rollout (5% → 25% → 100%)
- Continuous refinement

---

## 📞 Support & Documentation

| Resource | Location |
|----------|----------|
| Quick Start | [PHASE5_QUICKSTART.md](PHASE5_QUICKSTART.md) |
| Implementation Roadmap | [PHASE5_IMPLEMENTATION_ROADMAP.md](PHASE5_IMPLEMENTATION_ROADMAP.md) |
| Status Report | [PHASE5_STATUS_REPORT.md](PHASE5_STATUS_REPORT.md) |
| API Reference | `prototype/jimsai/eventing/` module docs |
| Test Results | `phase5_test_results_*.json` files |

---

## ✅ Checklist for Production Deployment

- [ ] PostgreSQL running and accessible
- [ ] Database created: `jimsai`
- [ ] Schema deployed successfully
- [ ] EventStore initializes without errors
- [ ] Integration tests pass 8/8
- [ ] T1 skip rate > 30%
- [ ] T2 skip rate > 25%
- [ ] SPPE pairs generating correctly
- [ ] Latency < 500ms average
- [ ] No error logs in test output

**When all checked**: Ready for staging deployment

---

## 🚀 Production Checklist

- [ ] Backup created: `jimsai_backup_$(date).sql`
- [ ] Monitoring configured (Prometheus)
- [ ] Alerting set up (PagerDuty/Slack)
- [ ] Logs aggregated (ELK stack)
- [ ] Rate limiting enabled
- [ ] Quota management active
- [ ] Human review queue ready
- [ ] Training orchestration tested
- [ ] Artifact hot-swap validated
- [ ] Rollback procedure documented

**When all checked**: Ready for production deployment

---

## 📝 Notes

- All code is idempotent (safe to re-run)
- Database migrations are additive only (backward compatible)
- Event store is append-only (immutable audit trail)
- Projections can be rebuilt from events anytime
- No data loss risk - all changes tracked in events

---

**Happy Building! 🎉**

For questions or issues, refer to the implementation roadmap or check the event logs:

```bash
psql -U postgres -h localhost -d jimsai \
    -c "SELECT event_type, COUNT(*) FROM events GROUP BY event_type ORDER BY COUNT(*) DESC;"
```
