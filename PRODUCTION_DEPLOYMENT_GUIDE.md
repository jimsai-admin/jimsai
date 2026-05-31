"""
PRODUCTION DEPLOYMENT GUIDE

Complete guide to deploying JimsAI with real cloud providers, multi-tenant workspaces,
and workspace-specific personalization.

Architecture Overview:
  - BASE MODEL: JimsAI phase5 (shared, frozen across all workspaces)
  - PERSONALIZATION: Per-workspace adaptation from usage patterns
  - PROVIDERS: 6 real cloud services (Groq, Supabase, Vectorize, Neo4j, R2, Kaggle)
  - MULTI-TENANT: Complete isolation per workspace/organization
  - DEPLOYMENT: Development (local), Staging (limited), Production (full-scale)
"""

# ============================================================================
# QUICK START
# ============================================================================

"""
DEVELOPMENT (Local Machine):
==================================

1. Install dependencies:
   pip install jimsai[dev]

2. Set environment:
   export JIMSAI_ENV=development

3. Run locally:
   from services.production_pipeline import ProductionPipeline, ProductionRequest
   from prototype.jimsai.workspaces import get_workspace_manager
   
   pipeline = ProductionPipeline()
   manager = get_workspace_manager()
   
   ws = manager.create_workspace("org1", "My Workspace")
   request = ProductionRequest(ws.workspace_id, "user1", "What is AI?")
   response = await pipeline.process_request(request)

4. Mocked providers:
   - Groq → Mock responses
   - Supabase → SQLite local
   - Vectorize → In-memory embeddings
   - Neo4j → Disabled
   - R2 → Local files
   - Kaggle → Disabled


STAGING (Limited Real Providers):
==================================

1. Set environment variables:
   export JIMSAI_ENV=staging
   export GROQ_API_KEY_STAGING=sk_...
   export SUPABASE_URL_STAGING=https://...
   export SUPABASE_KEY_STAGING=eyJ...
   export CLOUDFLARE_ACCOUNT_ID=...
   export CLOUDFLARE_API_TOKEN=...
   export NEO4J_USERNAME_STAGING=neo4j
   export NEO4J_PASSWORD_STAGING=password

2. Set database variables:
   export DB_HOST_STAGING=localhost
   export DB_USER_STAGING=jimsai
   export DB_PASSWORD_STAGING=password
   
3. Set Redis (for caching):
   export REDIS_HOST_STAGING=localhost
   export REDIS_PORT_STAGING=6379

4. Run tests:
   python -m pytest tests/production/

5. Monitor:
   - Prometheus: http://localhost:9090
   - Logs: ~/.jimsai/logs/


PRODUCTION (Full-Scale Multi-Tenant):
==================================

1. Deploy infrastructure:
   - PostgreSQL cluster with replicas
   - Redis cluster (3+ nodes)
   - Neo4j cluster
   - Cloudflare R2 buckets

2. Set all production environment variables:
   export JIMSAI_ENV=production
   export GROQ_API_KEY_PROD=sk_...
   export SUPABASE_URL_PROD=https://...
   export SUPABASE_KEY_PROD=eyJ...
   export NEO4J_PROD_ENDPOINT=bolt+s://...
   export DB_HOST_PROD=postgres.prod.example.com
   export DB_USER_PROD=jimsai
   export DB_PASSWORD_PROD=${DB_PROD_PASSWORD}
   export REDIS_CLUSTER_NODES=redis1:6379,redis2:6379,redis3:6379
   export CLOUDFLARE_ACCOUNT_ID=...
   export CLOUDFLARE_API_TOKEN=...

3. Deploy services:
   - API server (Uvicorn, 4+ workers)
   - Event processor (processes SPPE pairs)
   - Model trainer (Kaggle jobs)
   - Monitoring (Prometheus + Grafana)

4. Verify deployment:
   curl https://api.jimsai.prod/health
   
5. Monitor:
   - Grafana dashboards
   - Alert channels (Slack, PagerDuty)
   - Cost tracking
"""


# ============================================================================
# PROVIDER SETUP INSTRUCTIONS
# ============================================================================

"""
1. GROQ (T1/T2 Inference):
   ========================
   
   Setup:
   1. Create account: https://console.groq.com
   2. Create API key
   3. Export: export GROQ_API_KEY_PROD=sk_<your-key>
   
   Models available:
   - T1: mixtral-8x7b-32768 (intent parsing)
   - T2: llama2-70b-4096 (fluency rendering)
   
   Cost: ~$0.0005 per 1k tokens
   Rate limit: 10,000 req/min (production)
   
   Usage in code:
   adapter = GroqAdapter(config, workspace_id)
   intent = await adapter.parse_intent(query)
   response = await adapter.render_fluency(semantic_ir)


2. SUPABASE (PostgreSQL + Auth + Vectors):
   ========================================
   
   Setup:
   1. Create project: https://supabase.com
   2. Copy project URL and API key
   3. Export:
      export SUPABASE_URL_PROD=https://xxxx.supabase.co
      export SUPABASE_KEY_PROD=eyJ...
   
   Database setup:
   - Event store table: events (append-only)
   - Projections: memory_signature, sppe_pairs, etc.
   - Vector storage: pgvector extension
   
   Cost: $25/month base + storage
   
   Usage in code:
   adapter = SupabaseAdapter(config, workspace_id)
   event_id = await adapter.append_event(event)
   metrics = await adapter.get_workspace_metrics()


3. VECTORIZE (Cloudflare Embeddings):
   ===================================
   
   Setup:
   1. Enable Vectorize: https://dash.cloudflare.com
   2. Get Account ID and API Token
   3. Export:
      export CLOUDFLARE_ACCOUNT_ID=<account-id>
      export CLOUDFLARE_API_TOKEN=<token>
   
   Create index:
   curl -X POST https://api.cloudflare.com/client/v4/accounts/YOUR_ID/ai/vectorize/indexes \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -d '{"name":"jimsai-embeddings","dimensions":1536}'
   
   Cost: $0.004 per 1M vectors
   Model: text-embedding-3-large (1536 dims)
   
   Usage in code:
   adapter = VectorizeAdapter(config, workspace_id)
   embedding = await adapter.embed_text(text)
   results = await adapter.semantic_search(query_vector)


4. NEO4J (Knowledge Graph):
   ========================
   
   Setup Option A (Cloud):
   1. Create instance: https://neo4j.com/cloud
   2. Note endpoint, username, password
   3. Export:
      export NEO4J_PROD_ENDPOINT=bolt+s://xxxx.databases.neo4j.io
      export NEO4J_USERNAME_PROD=neo4j
      export NEO4J_PASSWORD_PROD=<password>
   
   Setup Option B (Self-hosted):
   docker run -d \
     -p 7687:7687 \
     -e NEO4J_AUTH=neo4j/password \
     neo4j:5.11
   
   Cost: $9/month (cloud) or self-hosted free
   
   Usage in code:
   adapter = Neo4jAdapter(config, workspace_id)
   entity_id = await adapter.create_entity("Person", {"name": "Alice"})
   await adapter.create_relationship(id1, id2, "KNOWS")


5. R2 (Object Storage):
   ====================
   
   Setup:
   1. Create bucket: https://dash.cloudflare.com
   2. Generate API token
   3. Export:
      export CLOUDFLARE_ACCOUNT_ID=<account-id>
      export CLOUDFLARE_API_TOKEN=<token>
   
   Create bucket:
   aws s3api create-bucket --bucket jimsai-prod \
     --endpoint-url https://<account-id>.r2.cloudflarestorage.com
   
   Cost: $0.015/GB stored, $0.01/1M requests
   
   Usage in code:
   adapter = R2Adapter(config, workspace_id)
   key = await adapter.store_artifact("image", image_bytes)
   image = await adapter.get_artifact(key)


6. KAGGLE (Model Training):
   ========================
   
   Setup:
   1. Create account: https://kaggle.com
   2. Download API token: ~/.kaggle/kaggle.json
   3. Extract username and key
   4. Export:
      export KAGGLE_USERNAME=<username>
      export KAGGLE_API_KEY=<key>
   
   Cost: Free compute (GPU quota), or paid tier
   
   Usage in code:
   adapter = KaggleAdapter(config, workspace_id)
   job_id = await adapter.submit_training_job({...})
   status = await adapter.get_job_status(job_id)
"""


# ============================================================================
# MULTI-TENANT WORKSPACE SETUP
# ============================================================================

"""
Creating Workspaces for Organizations:
========================================

from prototype.jimsai.workspaces import get_organization_manager

org_mgr = get_organization_manager()

# Create organization
org_id = org_mgr.create_organization(
    "Acme Corp",
    "Engineering division"
)

# Create workspaces within organization
workspace1 = org_mgr.create_workspace_in_org(
    org_id,
    "Product Team",
    config_overrides={
        "groq_skip_t1_threshold": 0.88,  # Lower threshold = more aggressive skipping
        "groq_skip_t2_threshold": 0.93,
        "max_queries_per_day": 100000,
        "require_human_approval": False,
    }
)

workspace2 = org_mgr.create_workspace_in_org(
    org_id,
    "Research Team",
    config_overrides={
        "require_human_approval": True,  # Research needs approval
        "approval_threshold": 0.70,
    }
)

# Get metrics across organization
org_metrics = org_mgr.get_organization_metrics(org_id)
print(f"Total queries: {org_metrics['total_queries']}")
print(f"Total cost: ${org_metrics['total_cost']:.2f}")


Workspace Quotas and Governance:
================================

# Check quota before query
quota = workspace_mgr.check_quota(
    workspace_id,
    operation="query",
    cost=0.015
)

# Record metrics
workspace_mgr.record_query(
    workspace_id,
    latency_ms=350,
    cost=0.015,
    confidence=0.92
)

# Record SPPE pair
workspace_mgr.record_sppe_pair(
    workspace_id,
    quality_score=0.88
)
"""


# ============================================================================
# PERSONALIZATION SETUP
# ============================================================================

"""
Workspace-Specific Personalization:
====================================

from prototype.jimsai.personalization import (
    get_personalization_engine,
    get_workspace_adapter
)

# Get personalization engine for workspace
personalization = get_personalization_engine(workspace_id)

# Record user interaction
await personalization.record_interaction(
    user_id="user_123",
    query="How to implement binary search?",
    route="coding",
    response="Binary search works by...",
    confidence=0.92,
    latency_ms=450,
    quality_score=0.88,
    t1_used=True,
    t2_used=False,
)

# Get personalized configuration
config = personalization.get_personalized_config()
print(f"Recommended T1 threshold: {config['t1_skip_threshold']}")
print(f"Recommendations: {config['recommendations']}")

# Get capability insights
insights = personalization.get_capability_insights("coding")
print(f"Coding queries: {insights['total_queries']}")
print(f"Avg latency: {insights['avg_latency_ms']}ms")
print(f"Avg quality: {insights['avg_quality_score']}")

# Get user preferences
user_insights = personalization.get_user_insights("user_123")
print(f"Preferred style: {user_insights['preferred_style']}")


Workspace Adapter Models:
=========================

# Get workspace-specific adapter
adapter = get_workspace_adapter(workspace_id)

# Update from SPPE pairs (after collecting training data)
adapter.update_from_sppe_pairs(sppe_pairs_for_workspace)

# Get personalized thresholds
t1_thresh, t2_thresh = adapter.get_adjusted_thresholds(
    base_t1=0.90,
    base_t2=0.95
)

# Adapter learns from workspace patterns:
# - High quality SPPE pairs → lower thresholds
# - Low quality SPPE pairs → raise thresholds
# - Weights learned routes higher
# - Prefers successful providers
"""


# ============================================================================
# DEPLOYMENT CHECKLIST
# ============================================================================

"""
Pre-Production Checklist:
=========================

Infrastructure:
  ☐ PostgreSQL cluster (3+ nodes with replication)
  ☐ Redis cluster (3+ nodes)
  ☐ Neo4j cluster (3+ nodes)
  ☐ Cloudflare R2 bucket created
  ☐ Groq API keys obtained
  ☐ Supabase project created
  ☐ Kaggle credentials available
  ☐ Monitoring stack (Prometheus + Grafana)
  ☐ Log aggregation (ELK or CloudWatch)
  ☐ Backup system configured

Configuration:
  ☐ All environment variables set
  ☐ Database schemas migrated
  ☐ Redis keys configured
  ☐ Provider health checks passing
  ☐ SSL certificates installed

Testing:
  ☐ Unit tests passing
  ☐ Integration tests passing
  ☐ Load tests with realistic traffic
  ☐ Failover scenarios tested
  ☐ Cost monitoring verified
  ☐ Personalization engine validated

Security:
  ☐ API key rotation strategy
  ☐ Database encryption at rest/transit
  ☐ Rate limiting enabled
  ☐ DDoS protection active
  ☐ Audit logging enabled
  ☐ Data retention policies set

Operations:
  ☐ Runbooks documented
  ☐ Alert thresholds configured
  ☐ On-call rotation established
  ☐ Incident response plan ready


Deployment Steps:
=================

1. Prepare staging environment
   JIMSAI_ENV=staging pytest tests/ -v

2. Load test
   locust -f tests/load/locustfile.py --headless -u 1000 -r 100

3. Deploy to production (canary 10%)
   helm upgrade jimsai ./helm --set canary.enabled=true

4. Monitor metrics
   - Query latency (should be <500ms p99)
   - Provider health (all should be green)
   - Cost tracking (should match estimates)
   - Error rates (should be <0.1%)

5. Scale to 100%
   helm upgrade jimsai ./helm --set canary.enabled=false

6. Verify workspace isolation
   - Query one workspace should not affect others
   - Metrics should be per-workspace isolated
   - Personalization should be per-workspace

7. Enable continuous learning
   - SPPE pairs being collected
   - Personalization engine updating
   - Training jobs scheduled
"""


# ============================================================================
# MONITORING & OPERATIONS
# ============================================================================

"""
Key Metrics to Monitor:
=======================

Per-Workspace Metrics:
  - Queries per minute
  - Average latency (p50, p95, p99)
  - Average confidence
  - Average quality score
  - T1/T2 skip rates
  - Cost per query
  - Error rate

Per-Provider Metrics:
  - Groq: T1/T2 latency, error rate, cost
  - Supabase: Connection pool usage, event append latency
  - Vectorize: Embedding latency, search latency
  - Neo4j: Query latency, graph size
  - R2: Upload/download latency, storage used
  - Kaggle: Training job status, model accuracy

System Metrics:
  - Database connection pool utilization
  - Redis hit rate
  - Memory usage
  - CPU usage
  - Disk I/O

Personalization Metrics:
  - Patterns discovered per workspace
  - Avg thresholds adjusted
  - Model accuracy improvement
  - SPPE pairs collected per day


Alerting Rules:
===============

Critical Alerts:
  - Provider health check failed (any provider)
  - Query latency p99 > 2000ms
  - Error rate > 1%
  - Database connection pool exhausted
  - Workspace quota exceeded

Warning Alerts:
  - Query latency p95 > 1000ms
  - Cost trajectory exceeds budget
  - Low SPPE pair generation
  - Personalization accuracy declining


Common Issues & Solutions:
==========================

Issue: High latency in T2
Solution: Check Groq rate limits, add request queue

Issue: Low quality scores
Solution: Review SPPE scoring algorithm, check provider responses

Issue: Provider health check failures
Solution: Verify API keys, check network connectivity

Issue: Workspace personalization not improving
Solution: Increase SPPE pair collection, check adapter update logic

Issue: Cost overruns
Solution: Lower skip thresholds, reduce retry attempts, batch requests
"""


# ============================================================================
# EXAMPLE PRODUCTION USAGE
# ============================================================================

"""
from services.production_pipeline import ProductionPipeline, ProductionRequest
from prototype.jimsai.workspaces import get_organization_manager
import asyncio

async def main():
    # Initialize
    pipeline = ProductionPipeline()
    org_mgr = get_organization_manager()
    
    # Create organization and workspace
    org_id = org_mgr.create_organization("My Company")
    workspace = org_mgr.create_workspace_in_org(org_id, "Engineering")
    
    # Process query through production pipeline
    request = ProductionRequest(
        workspace_id=workspace.workspace_id,
        user_id="engineer_001",
        query="How do I implement async/await in Python?"
    )
    
    response = await pipeline.process_request(request)
    
    print(f"Response: {response.response}")
    print(f"Confidence: {response.confidence:.2%}")
    print(f"Quality: {response.quality_score:.2f}")
    print(f"T1 Used: {response.t1_used}, T2 Used: {response.t2_used}")
    print(f"Workspace Model: {response.used_workspace_model}")

if __name__ == "__main__":
    asyncio.run(main())
"""

if __name__ == "__main__":
    print(__doc__)
