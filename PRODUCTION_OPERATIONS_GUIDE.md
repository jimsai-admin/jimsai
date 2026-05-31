# JimsAI v10 Production Operations Guide

**Quick Reference for DevOps & Support Teams**
**Version**: 1.0
**Last Updated**: 2026-05-31

---

## Quick Start

### Pre-Deployment (Do this once)
```bash
# Install dependencies
cd /path/to/jimsai
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Pre-cache the model (required!)
python download_model.py
# Output should show: ✅ Model downloaded and cached successfully
```

### Deploy
```bash
# Replace old files with new ones
cp prototype/jimsai/semantic_compiler.py /prod/
cp prototype/jimsai/intent_classifier.py /prod/
cp scripts/iterative_training_loop.py /prod/

# Restart the service
systemctl restart jimsai-api
```

### Verify
```bash
# Check model is loaded
curl http://localhost:8000/health
# Should return: { "status": "ok", "model": "ready" }

# Check that 11 tests still pass
python -m pytest tests/test_semantic_compiler.py -k "passed" -v
```

---

## Architecture Overview

```
User Input → normalize_language() → classifier.classify_intent() → IR Target + Confidence → Route
     ↓              ↓                        ↓                              ↓
  "h0w d0 i"    "how do i"          Embedding lookup           ("FETCH_DOCUMENT", 0.72)
  (OCR noise)  (normalized)         + cosine similarity         (routed to target)
                                    (multilingual)
```

### Intent Targets (10 total)
```
FETCH_DOCUMENT           - File operations (download, upload)
CODE_GENERATE           - Code/API generation  
WORKSPACE_QUERY         - Analytics, queries
RUN_CANVAS              - Deep codebase analysis
RUN_INVENTION           - Novel architecture design
SYSTEM_DIAGNOSTIC       - Error diagnosis
EMOTIONAL_CATCH         - Support/empathy routing
GENERAL_FACT            - Knowledge lookups
META_INQUIRY            - System introspection
OP_ESCAPE_TO_SANDBOX    - Low-confidence fallback
```

---

## Configuration

### File: `prototype/jimsai/semantic_compiler.py`
```python
# Main configuration
class SemanticCompilerRuntime:
    def __init__(self, confidence_threshold: float = 0.50):
        # threshold: Minimum confidence to accept classification
        # 0.50 = requires 50% semantic match
        # Increase to be stricter, decrease to be lenient
```

### File: `prototype/jimsai/intent_classifier.py`
```python
# IR Prototypes (change these to tune accuracy)
self.ir_prototypes = {
    "FETCH_DOCUMENT": "fetch retrieve download upload attach file...",
    "CODE_GENERATE": "generate code write function method API...",
    # etc...
}
```

### Environment Variables
```bash
# Optional: Change model cache location
export HF_HOME=/custom/cache/path

# Optional: Use different model (more accurate but slower)
export JIMSAI_MODEL=intfloat/multilingual-e5-base
```

---

## Monitoring Checklist

### Every Hour
- [ ] Check average latency: `tail -100 logs/jimsai.log | grep latency`
- [ ] Verify model cache hits: Should be >95%
- [ ] Check error rate: Should be <1%

### Every Day
- [ ] Review confidence distribution (should be 0.5-0.95 range)
- [ ] Verify provider calls: Must NOT trend upward
- [ ] Check for new languages in usage (monitor coverage)
- [ ] Review any OP_ESCAPE_TO_SANDBOX routing (should be <10%)

### Every Week
- [ ] Measure Intent Stability Score
- [ ] Review production accuracy (compare to test results)
- [ ] Plan any prototype refinements
- [ ] Check for security updates (sentence-transformers, dependencies)

---

## Common Operations

### Check Model Status
```bash
python -c "
from prototype.jimsai.intent_classifier import get_classifier
clf = get_classifier()
print('Model loaded:', clf.model_name)
print('Model dimension:', clf.model.get_sentence_embedding_dimension())
print('Languages:', len(clf.ir_prototypes))
"
```

### Test Classification Directly
```bash
python -c "
from prototype.jimsai.semantic_compiler import SemanticCompilerRuntime
compiler = SemanticCompilerRuntime()

# Test a query
ir = compiler.compile('upload my file')
print(f'IR Target: {ir.target_ir}')
print(f'Confidence: {ir.confidence}')
print(f'Execution: {ir.execution_mode}')
"
```

### Verify All 11 Tests Pass
```bash
python -m pytest tests/test_semantic_compiler.py \
  -k "sanitize or normalization or marks_profile or v9_code or v9_media or architecture or agentic or polite or public_memory or finance or code_design" \
  -v
# Should show: 11 passed
```

### Performance Profiling
```bash
python -c "
import time
from prototype.jimsai.semantic_compiler import SemanticCompilerRuntime

compiler = SemanticCompilerRuntime()
queries = [
    'upload file',
    'analyze codebase', 
    'who am i',
    'what is python'
]

for q in queries:
    start = time.time()
    ir = compiler.compile(q)
    elapsed = (time.time() - start) * 1000
    print(f'{q:30s} -> {ir.target_ir:20s} ({elapsed:.1f}ms, conf={ir.confidence:.2f})')
"
```

---

## Troubleshooting Guide

### Issue: Latency High (>500ms)

**Symptom**: Requests taking >500ms

**Check 1: Model Cache**
```bash
# Is model cached?
ls -lh .cache/models/intfloat/multilingual-e5-small/
# Should show: model.safetensors (471M), modules.json, etc.

# If missing, pre-cache:
python download_model.py
```

**Check 2: Disk I/O**
```bash
# Is disk busy?
iostat -x 1 5
# Look for %util close to 100%

# Solution: Move cache to faster disk or add RAM
```

**Check 3: Memory**
```bash
# Is memory available?
free -h
# Need: ~2GB free minimum

# Solution: Increase available RAM or restart service
```

**Check 4: GPU** (if using CUDA)
```bash
# Is GPU available?
nvidia-smi
# If no CUDA, falls back to CPU (slower)

# Solution: Enable CUDA or accept CPU latency
```

---

### Issue: Low Confidence Scores (<0.4)

**Symptom**: Many queries getting confidence <0.4, routing to sandbox

**Check 1: Is it a new language?**
```bash
# Model supports 100+ languages
# If seeing unsupported language, might be limitation

# Solution: Refine prototypes or report as Phase 2 enhancement
```

**Check 2: Are prototypes calibrated?**
```bash
# Review IR_prototypes in intent_classifier.py
# Are they descriptive enough?

# Solution: Add more keywords to matching target
```

**Check 3: Is threshold too high?**
```bash
# Current threshold: 0.50
# Try lowering to 0.45 or raising to 0.55

# Change in semantic_compiler.py:
# def __init__(self, confidence_threshold: float = 0.50)
```

---

### Issue: Provider Calls Increasing

**Symptom**: Provider usage trending up (cost alert)

**Action**: IMMEDIATE - This violates Principle 2!

```bash
# Check provider trend enforcement
grep "check_provider_trend" logs/jimsai.log

# If trending up, the enforcement failed - INVESTIGATE

# Possible causes:
# 1. Provider enforcement not running
# 2. Training loop bypassing check
# 3. Manual provider calls not tracked

# Solution: Run rollback immediately!
git revert HEAD
systemctl restart jimsai-api
```

---

### Issue: Tests Failing in Production

**Symptom**: 11 core tests now failing (were passing in QA)

**Check 1: Is model cached?**
```bash
# Model cache location might be different
# Check HF_HOME environment variable
echo $HF_HOME

# If model not found, download:
python download_model.py
```

**Check 2: Did dependencies change?**
```bash
pip list | grep sentence-transformers
# Should be v5.5.1

# If different, update:
pip install sentence-transformers==5.5.1
```

**Check 3: Did code get corrupted?**
```bash
# Verify syntax
python -m py_compile prototype/jimsai/semantic_compiler.py
python -m py_compile prototype/jimsai/intent_classifier.py

# If errors, check git diff
git diff HEAD~1
```

**Solution**: If all checks pass but tests fail, rollback!

---

## Performance Targets

| Metric | Target | Warning | Critical |
|--------|--------|---------|----------|
| Latency P50 | <50ms | >100ms | >500ms |
| Latency P99 | <100ms | >200ms | >1000ms |
| Confidence Avg | 0.70 | <0.60 | <0.50 |
| Cache Hit Rate | >95% | <90% | <80% |
| Error Rate | <0.1% | >0.5% | >1% |
| Provider Trend | Flat/Down | Any Up | Consistent Up |

---

## Emergency Procedures

### Fast Rollback (if something breaks)
```bash
# Option 1: Switch traffic to old system
# Keep v9 available for 30 days as fallback

# Option 2: Revert code
git revert HEAD
systemctl restart jimsai-api

# Option 3: Restore from backup
# Restore last known good model cache
```

### Escalation Path
1. Check logs: `tail -100 logs/jimsai.log`
2. Verify model cache: `ls -lh .cache/models/`
3. Test directly: `python -c "...test classification..."`
4. If unresolved after 5 minutes: **ROLLBACK**
5. Post-incident: Review root cause before reattempt

---

## Support Contacts

| Component | Owner | Slack |
|-----------|-------|-------|
| SemanticCompiler Code | @engineering | #jimsai-dev |
| Model/Embeddings | @ml-team | #ml-eng |
| DevOps/Deployment | @devops | #ops-platform |
| Product Questions | @product | #product-eng |

---

## Key Files Reference

| File | Purpose | Modify When |
|------|---------|------------|
| `semantic_compiler.py` | Main routing logic | Changing IR targets or routing rules |
| `intent_classifier.py` | Embedding classifier | Tuning prototypes or changing model |
| `iterative_training_loop.py` | Training pipeline | Changing provider enforcement rules |
| `download_model.py` | Model caching | Changing cache location or model |
| `DEPLOYMENT_PLAN.md` | Deployment strategy | Planning major changes |
| `PRODUCTION_READINESS_CHECKLIST.md` | Deployment checklist | Before going live |

---

## Document Info

**File**: PRODUCTION_OPERATIONS_GUIDE.md
**Version**: 1.0
**Created**: 2026-05-31
**Owner**: DevOps Team
**Last Reviewed**: 2026-05-31
