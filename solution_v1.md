# JIMS-AI Solution v1

This is the decided architecture for making JIMS-AI semantically stronger while keeping the production stack low-cost and deployable.

The core decision is:

```text
Do not put sentence-transformers inside AWS Lambda.

Lambda stays lightweight.
Semantic embedding moves to a separate embedding service.
Vector search lives in Cloudflare Vectorize.
Training and ingestion orchestration runs from Render.
GPU training runs offline on Kaggle.
Humans approve quality-sensitive changes before activation.
```

## 1. Final Cloud Roles

### Vercel

Vercel hosts the Next.js frontend.

Responsibilities:

- Login and session UI.
- Chat UI.
- Training console.
- Human review queues.
- Artifact approval UI.
- Calls AWS Lambda as the main API.

Vercel must not hold private provider secrets. It should only use public frontend variables:

```text
NEXT_PUBLIC_API_BASE_URL
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_ANON_KEY
```

### AWS Lambda

Lambda is the production API runtime.

Responsibilities:

- Auth validation.
- `/v1/query`.
- Feedback capture.
- Training panel APIs.
- Review actions.
- Memory update/delete APIs.
- Structured extraction.
- Exact memory lookup.
- Graph-backed reasoning.
- Calling the embedding service when semantic search is needed.
- Calling Vectorize for nearest-neighbor retrieval.
- Hydrating retrieved records from Supabase.
- Calling Groq only when the deterministic runtime cannot answer well enough.

Lambda should not install or load:

- `sentence-transformers`
- PyTorch
- large embedding models
- fine-tuned encoder artifacts
- long-running autonomous workers

Reason: Lambda package size, cold starts, memory limits, and runtime reliability are more important than hosting heavy model inference there.

### Supabase

Supabase is the durable system of record.

Responsibilities:

- Users and auth.
- Training records.
- Memory signatures.
- Human review queues.
- Autonomous agent state.
- Training jobs.
- Kaggle batches.
- Artifact registry.
- Evaluation reports.
- Approval state.

Supabase should store the structured truth. Vectorize stores vectors, but Supabase stores the record content and metadata.

### Cloudflare Vectorize

Cloudflare Vectorize is the persistent vector index.

Responsibilities:

- Store embeddings for signatures, chunks, memories, training records, and approved knowledge.
- Return top-k semantic matches.
- Keep vector search outside Lambda.

The vector ID should map cleanly back to Supabase records.

Example vector metadata:

```json
{
  "workspace_id": "default",
  "record_type": "signature",
  "record_id": "sig_123",
  "source": "human_reviewed",
  "trust": 0.92
}
```

### Neo4j Aura Free

Neo4j stores graph memory.

Responsibilities:

- Entities.
- Relations.
- Causal links.
- Upstream/downstream dependencies.
- World-model candidates.
- Connected context expansion after vector retrieval.

Neo4j should not replace Supabase. It adds graph reasoning on top of durable records.

### Render Free

Render runs bounded web services, not always-on workers.

Use Render for two separate free web services:

1. `jimsai-training-service`
2. `jimsai-embedding-service`

Both should expose `/health` and be kept warm with an external ping service.

Render free services can sleep. Therefore they must be stateless between requests and store progress in Supabase.

### Kaggle Free GPU

Kaggle is the offline training lab.

Use Kaggle for:

- SentenceTransformer fine-tuning.
- Batch document embedding.
- SPPE renderer experiments.
- World-model extractor experiments.
- Reranker experiments.
- Evaluation notebooks.
- Artifact generation.

Do not use Kaggle for:

- Live user prompt handling.
- Production API calls.
- Always-on inference.
- Urgent chat responses.
- Long-running production workers.

### External Cron

Use an external cron/ping provider for free-tier scheduling.

Responsibilities:

- Keep Render services warm.
- Trigger bounded autonomous training jobs.
- Trigger evaluation.
- Trigger Kaggle packaging.
- Avoid infinite loops inside Render.

## 2. Runtime Query Flow

Final `/v1/query` flow:

```text
Frontend
  -> AWS Lambda /v1/query
    -> validate Supabase session
    -> parse user prompt
    -> extract entities, intent, workspace, and constraints
    -> exact/structured lookup in Supabase
    -> call Render embedding service POST /v1/embed
      -> if available, return real query vector
      -> if unavailable, Lambda falls back to hash embedding
    -> query Cloudflare Vectorize top-k
    -> hydrate matching records from Supabase
    -> expand related graph context from Neo4j
    -> score and merge exact + semantic + graph results
    -> produce answer using deterministic rendering
    -> call Groq only when needed
    -> store query, answer, sources, retrieval misses, and feedback hooks
    -> return response to frontend
```

This gives Lambda semantic power without making Lambda heavy.

## 3. Embedding Service

Create a separate Render free web service:

```text
jimsai-embedding-service
```

Required endpoints:

```text
GET  /health
POST /v1/embed
POST /v1/embed-batch
POST /v1/reload-artifact
GET  /v1/artifact/current
```

`POST /v1/embed` request:

```json
{
  "texts": ["Why did the dashboard show records but no UI?"],
  "workspace_id": "default",
  "purpose": "query"
}
```

`POST /v1/embed` response:

```json
{
  "model": "intfloat/multilingual-e5-small",
  "artifact_id": "artifact_active_encoder_001",
  "dimension": 768,
  "vectors": [[0.01, 0.02, 0.03]]
}
```

Model loading order:

```text
1. latest active approved JIMS-AI encoder artifact
2. base encoder model such as intfloat/multilingual-e5-small
3. deterministic hash embedding fallback only if model loading fails
```

Lambda calls this service only when needed. If the service is asleep or unavailable, Lambda should continue with structured/exact retrieval and hash fallback.

## 4. Dual Embedding Path

Use two embedding paths.

### Real-Time Query Embedding

Used for live chat.

```text
Lambda
  -> Render embedding service
  -> Vectorize query
```

This path must be fast, bounded, and optional.

### Bulk Document Embedding

Used for large training ingestion.

```text
Render training service
  -> package batch
  -> Kaggle notebook embeds documents
  -> vector files/artifacts produced
  -> Render syncs results
  -> Vectorize upsert
  -> Supabase metadata update
```

This path can process large volumes and use Kaggle GPU.

## 5. Hybrid Retrieval Strategy

JIMS-AI should use three retrieval layers together.

### Layer 1: Exact And Structured Retrieval

Use for:

- entity match
- relation match
- signature ID
- workspace scope
- user scope
- tags
- provenance
- approved memory
- exact training records

This is the current Lambda strength.

### Layer 2: Fuzzy Semantic Retrieval

Use for:

- query embedding
- Vectorize top-k
- semantically related memories
- paraphrase matching
- multilingual matching
- large-scale nearest-neighbor retrieval

Example:

```text
"Why did the dashboard show records but no UI?"
```

Should retrieve records about:

- training panel records
- Supabase rows
- frontend empty states
- panel item filtering
- Lambda persistence
- review queue hydration
- multimodal ingestion hydration

Even when the exact words do not match.

### Layer 3: Graph Expansion

After exact and semantic retrieval:

```text
matched signature
  -> related entities
  -> causal links
  -> upstream dependencies
  -> downstream effects
  -> world-model candidates
  -> prior fixes
```

This is how JIMS-AI moves from search results to reasoning context.

## 6. Retrieval Scoring

Use hybrid scoring:

```text
final_score =
    semantic_score * 0.55
  + lexical_score  * 0.20
  + graph_score    * 0.15
  + trust_score    * 0.10
```

Definitions:

- `semantic_score`: Vectorize similarity.
- `lexical_score`: keyword, entity, tag, and exact field overlap.
- `graph_score`: causal/entity neighborhood relevance.
- `trust_score`: human approval, source trust, provenance quality, and successful prior usage.

Initial runtime:

```text
Vectorize top 20
  -> hydrate Supabase records
  -> graph expand top 8
  -> send compact context to reasoning/rendering layer
```

Later runtime:

```text
Vectorize top 50
  -> cheap reranker
  -> top 8 to reasoning/rendering layer
```

The reranker can become a Kaggle-trained artifact later.

## 7. Ingestion Flow

When content is ingested:

```text
Render training service or Lambda training endpoint
  -> validate source and workspace
  -> normalize document
  -> chunk document
  -> extract entities and relations
  -> generate memory signatures
  -> request embeddings
  -> write structured records to Supabase
  -> upsert vectors to Vectorize
  -> upsert graph facts to Neo4j
  -> create review items when confidence is uncertain
```

For small user-submitted records, Lambda can handle ingestion.

For large external or autonomous ingestion, Render should handle it in bounded batches.

## 8. Render Autonomous Agent

Render free tier cannot be treated as a real always-on worker.

The decided architecture is:

```text
external cron
  -> calls Render endpoint
  -> Render processes one bounded unit of work
  -> Render saves state to Supabase
  -> Render exits
```

Required Render training endpoints:

```text
GET  /health
POST /v1/autonomous/discover
POST /v1/autonomous/ingest-batch
POST /v1/autonomous/evaluate
POST /v1/autonomous/plan
POST /v1/autonomous/kaggle/package
POST /v1/autonomous/report
```

Each endpoint must be protected with:

```text
Authorization: Bearer <JIMS_RENDER_AGENT_TOKEN>
```

`/health` stays public.

## 9. Cron Schedule

Recommended free-tier cron schedule:

```text
Every 10 minutes:
  GET /health on jimsai-training-service
  GET /health on jimsai-embedding-service

Every 30 minutes:
  POST /v1/autonomous/ingest-batch

Every 6 hours:
  POST /v1/autonomous/evaluate

Daily:
  POST /v1/autonomous/plan
  POST /v1/autonomous/report

Weekly or threshold-based:
  POST /v1/autonomous/kaggle/package
```

Bounded limits per call:

```text
ingest max 50-200 docs
embed max 100 docs
run max 5 minutes
save cursor/checkpoint
exit
```

This prevents Render free-tier jobs from becoming fragile long-running processes.

## 10. Autonomous Agent State

The autonomous agent must not rely on process memory.

Store state in Supabase tables:

```text
autonomous_runs
autonomous_jobs
ingestion_cursors
training_batches
training_artifacts
evaluation_reports
approval_queue
```

Agent cycle:

```text
Render receives cron call
  -> validates bearer token
  -> reads next job from Supabase
  -> loads cursor/checkpoint
  -> processes bounded batch
  -> writes results
  -> updates cursor/checkpoint
  -> writes run log
  -> exits
```

This makes the agent resumable after Render sleeps, restarts, or redeploys.

## 11. Human-In-The-Loop Training

The autonomous agent should do the repetitive work. Humans should approve quality gates.

Autonomous agent does:

- discover candidate data
- normalize data
- chunk data
- embed data
- extract entities
- extract relations
- generate memory signatures
- generate SPPE pairs
- generate world-model candidates
- rank uncertain records
- detect retrieval misses
- package Kaggle batches
- measure evaluation deltas
- prepare reports

Humans do:

- approve or reject world-model candidates
- correct bad memories
- resolve ambiguity queue
- approve Kaggle artifact activation
- mark answers as "learn this"
- reject unsafe or low-quality training data
- review high-impact low-confidence records

The Training UI becomes the human quality console.

Priority review items:

- high-impact low-confidence memories
- world-model rules with confidence from `0.65` to `0.90`
- frequently retrieved but low-confidence signatures
- answers users corrected
- retrieval misses
- domain gaps
- new Kaggle artifacts waiting for approval

## 12. Training Lifecycle

Healthy JIMS-AI training lifecycle:

```text
1. User chats.
2. System records query, answer, sources, confidence, and gaps.
3. User gives feedback or clicks Learn This.
4. Training ingestion stores memory and SPPE examples.
5. Autonomous agent adds external/domain data.
6. Human reviews uncertain memory and rules.
7. Accepted SPPE pairs accumulate.
8. Render packages a Kaggle training batch.
9. Kaggle GPU trains encoder/renderer/reranker artifacts.
10. Evaluation compares old artifact vs new artifact.
11. Human approves or rejects artifact.
12. Embedding service reloads the approved active artifact.
13. Future retrieval improves.
```

This is how JIMS-AI improves without pretending to train a frontier model from scratch.

## 13. Kaggle Usage

Kaggle should be used as a training and evaluation lab.

Good Kaggle jobs:

### Encoder Fine-Tune

Purpose:

- Improve semantic retrieval.
- Improve paraphrase matching.
- Improve domain-specific similarity.
- Improve multilingual retrieval.

Inputs:

- approved SPPE pairs
- query/document pairs
- human-corrected retrieval examples
- domain records
- hard negatives

Outputs:

```text
sentence_transformer/
manifest.json
eval_metrics.json
```

### Batch Document Embedding

Purpose:

- Embed large datasets.
- Avoid doing massive embedding work inside Lambda or Render request windows.

Outputs:

```text
vectors.parquet
metadata.json
manifest.json
```

Render then syncs these into Vectorize and Supabase.

### SPPE Renderer Training

Purpose:

- Improve rendering from Semantic Intention Graphs into fluent text.

Inputs:

- accepted `(SemanticIntentionGraph, original_text)` pairs
- human-corrected answers
- high-quality domain examples

Outputs:

```text
renderer_artifact/
manifest.json
eval_metrics.json
```

### Evaluation

Purpose:

- Check whether the new artifact improves retrieval and answer quality.
- Prevent self-poisoning.

Metrics:

- recall@k
- MRR
- nDCG
- retrieval miss reduction
- human approval rate
- hallucination/error rate
- latency impact

## 14. Artifact Registry

Add a Supabase artifact registry:

```text
training_artifacts
```

Columns:

```text
artifact_id
task_type
kaggle_run_id
model_type
base_model
storage_url
manifest_url
metrics
status
approved_by
approved_at
activated_at
created_at
updated_at
```

Allowed statuses:

```text
candidate
approved
active
rejected
retired
failed
```

Activation must not be automatic.

Correct activation flow:

```text
Kaggle artifact produced
  -> Render syncs metadata
  -> evaluation job runs
  -> human sees metrics in Training UI
  -> human approves artifact
  -> artifact status becomes approved
  -> previous active artifact becomes retired
  -> approved artifact becomes active
  -> embedding service reloads artifact
```

This protects the system from low-quality or poisoned training output.

## 15. Training Tables

Add or confirm these Supabase tables:

```text
autonomous_runs
autonomous_jobs
ingestion_cursors
training_batches
training_artifacts
evaluation_reports
approval_queue
memory_signatures
memory_chunks
sppe_pairs
retrieval_events
retrieval_misses
user_feedback
```

Minimum important fields:

### `memory_signatures`

```text
id
workspace_id
user_id
title
content
entities
relations
tags
source
trust_score
approval_status
created_at
updated_at
```

### `memory_chunks`

```text
id
signature_id
workspace_id
chunk_text
chunk_index
vector_id
embedding_model
artifact_id
created_at
```

### `retrieval_events`

```text
id
workspace_id
user_id
query
query_embedding_model
retrieved_ids
selected_ids
answer_id
confidence
created_at
```

### `retrieval_misses`

```text
id
workspace_id
user_id
query
reason
expected_answer
status
created_at
resolved_at
```

These tables make training measurable rather than vague.

## 16. Frontend Training Console

The Training UI should show:

- ingestion batches
- review queue
- ambiguity queue
- world-model candidates
- retrieval misses
- autonomous runs
- Kaggle runs
- evaluation reports
- artifact approval queue
- active artifact status

The user should be able to:

- approve memory
- reject memory
- edit/correct memory
- approve world-model candidate
- reject world-model candidate
- approve artifact
- reject artifact
- mark a chat answer as useful
- mark a chat answer as wrong
- mark an answer as "learn this"

This converts the UI from only displaying records into a real training quality workflow.

## 17. Failure Behavior

The system must degrade cleanly.

### If Embedding Service Is Down

Lambda should:

```text
use exact retrieval
use structured retrieval
use graph retrieval
use hash embedding fallback if needed
log semantic service unavailable
return an answer instead of failing the chat
```

### If Vectorize Is Down

Lambda should:

```text
skip semantic vector search
use Supabase exact/structured search
use Neo4j graph context
log provider degradation
return an answer with lower retrieval confidence
```

### If Render Is Sleeping

Live chat should still work because Lambda is the production API.

Training jobs wait until the next cron wake-up.

### If Kaggle Is Unavailable

Runtime still works.

New training artifacts wait until the next successful Kaggle run.

## 18. Security Rules

Secrets must stay server-side.

Never expose these in Vercel public variables:

- Supabase service key
- Kaggle token
- Cloudflare API token
- Neo4j password
- Redis URL
- Groq API key
- Render agent token

Protect autonomous endpoints:

```text
Authorization: Bearer <JIMS_RENDER_AGENT_TOKEN>
```

Protect embedding artifact reload endpoints the same way.

`/health` can stay public.

## 19. Implementation Phases

### Phase 1: Stabilize Current Production

Use:

- Vercel frontend
- Lambda query/runtime API
- Supabase durable records
- current training panels
- Render training service
- external cron health pings

Done when:

- frontend login works
- chat works from Vercel to Lambda
- training panel records render actual items
- CORS is clean
- Lambda does not fail when semantic service is unavailable

### Phase 2: Add External Embedding Service

Build:

- Render `jimsai-embedding-service`
- `/health`
- `/v1/embed`
- `/v1/embed-batch`
- `/v1/artifact/current`
- `/v1/reload-artifact`

Integrate:

- Lambda calls `/v1/embed`.
- Lambda falls back when unavailable.
- Vectorize stores real vectors.

Done when:

- a query gets a real embedding outside Lambda
- Vectorize top-k returns relevant records
- Supabase hydration works
- chat still works if the embedding service sleeps

### Phase 3: Add Hybrid Retrieval

Build:

- exact retrieval
- semantic retrieval
- graph expansion
- hybrid scoring
- retrieval event logging
- retrieval miss logging

Done when:

- user questions retrieve semantically related memories
- exact facts still win when appropriate
- graph context improves explanations
- retrieval misses are visible in Training UI

### Phase 4: Add Autonomous Agent State

Build Supabase tables:

- `autonomous_runs`
- `autonomous_jobs`
- `ingestion_cursors`
- `training_batches`
- `evaluation_reports`
- `approval_queue`

Build Render endpoints:

- `/v1/autonomous/discover`
- `/v1/autonomous/ingest-batch`
- `/v1/autonomous/evaluate`
- `/v1/autonomous/plan`
- `/v1/autonomous/report`

Done when:

- cron can trigger bounded jobs
- each job saves progress
- jobs resume after sleep/restart
- Training UI shows autonomous run status

### Phase 5: Kaggle Artifact Pipeline

Build:

- Kaggle batch packaging
- Kaggle notebook execution path
- artifact manifest
- metrics file
- artifact sync
- `training_artifacts` table

Done when:

- Render can package approved data
- Kaggle can train a candidate encoder
- metrics are produced
- artifact metadata syncs back to Supabase

### Phase 6: Human Approval And Activation

Build:

- artifact approval UI
- artifact status transitions
- embedding service reload endpoint
- active artifact tracking

Done when:

- new artifacts are not activated automatically
- humans can approve or reject
- embedding service loads the active approved artifact
- old artifacts can be retired or rolled back

### Phase 7: Reranking And Better Evaluation

Build:

- top-50 retrieval
- reranker artifact
- top-8 context selection
- evaluation dashboards

Done when:

- retrieval quality improves measurably
- latency remains acceptable
- failed artifacts are rejected by metrics before activation

## 20. Final Architecture Diagram

```text
                         +------------------+
                         |      Vercel      |
                         |  Next.js UI      |
                         +---------+--------+
                                   |
                                   v
                         +------------------+
                         |   AWS Lambda     |
                         | auth/query/api   |
                         +----+--------+----+
                              |        |
       exact/records          |        | query vector
                              v        v
                     +-------------+  +------------------------+
                     |  Supabase   |  | Render Embedding Svc   |
                     | durable DB  |  | sentence-transformers  |
                     +------+------+  +-----------+------------+
                            |                     |
                            | hydrate             | vector
                            v                     v
                     +-------------+      +--------------------+
                     | Neo4j Aura  |      | Cloudflare Vectorize|
                     | graph memory|      | vector search       |
                     +-------------+      +--------------------+


 External Cron
      |
      v
 +------------------------+
 | Render Training Svc    |
 | bounded autonomous jobs|
 +-----+------------+-----+
       |            |
       v            v
 +----------+   +----------------+
 |Supabase  |   | Kaggle GPU Lab |
 |state/jobs|   | train artifacts|
 +----------+   +--------+-------+
                         |
                         v
                 +------------------+
                 | Artifact Registry|
                 | human approval   |
                 +--------+---------+
                          |
                          v
                 Render Embedding Svc reloads
                 latest approved active encoder
```

## 21. Direct Answer On Quality

This architecture is good for JIMS-AI's current stage.

It is better than making Lambda heavy because it separates:

- live API reliability
- semantic retrieval
- batch training
- human approval
- durable state

JIMS-AI will not become a frontier foundation model from this. It becomes a stronger memory-centric AI system:

- good exact/domain memory
- better fuzzy semantic retrieval
- graph-based reasoning context
- continuous training data collection
- human-reviewed improvement
- Kaggle-assisted model artifacts

Compared to frontier models, JIMS-AI should not compete on raw general intelligence. It should compete on:

- persistent project memory
- source-backed answers
- domain-specific retrieval
- auditable training records
- user-controlled improvement
- lower-cost deployment
- human-approved knowledge evolution

The right product direction is:

```text
Use frontier models only as bounded assistants.
Let JIMS-AI own memory, retrieval, graph reasoning, provenance, and training workflow.
```

