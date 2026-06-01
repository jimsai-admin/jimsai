# JIMS-AI Production Deployment Guide

This is the current production topology for JIMS-AI.

```text
Vercel frontend
  -> AWS Lambda FastAPI backend
    -> Hugging Face Space embedding service
    -> Cloudflare Vectorize
    -> Supabase
    -> Neo4j Aura
    -> Redis
    -> Groq when deterministic runtime needs bounded model help

External cron
  -> Render training service
    -> Supabase state
    -> Hugging Face embedding service
    -> Kaggle GPU artifact packaging
```

## Live Services

```text
Frontend:
https://jimsai.vercel.app

AWS Lambda API:
https://7x27vovhmfnhcymm5ox3qiw4fy0agvcy.lambda-url.us-east-1.on.aws

Render training service:
https://jimsai-training-service.onrender.com

Hugging Face embedding service:
https://jimstechai-jimsai-embedding-service.hf.space
```

## What Runs Where

Vercel hosts only the Next.js UI. Public variables only:

```text
NEXT_PUBLIC_API_BASE_URL
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_ANON_KEY
```

AWS Lambda hosts the production API from `services/api-gateway`. It handles auth, chat, feedback, memory writes/deletes, training panels, provider readiness, deterministic reasoning, Vectorize retrieval, Supabase hydration, Neo4j graph context, Redis session state, and bounded Groq calls. Lambda does not install `sentence-transformers`.

Hugging Face Spaces hosts the sentence-transformer embedding service from:

```text
infrastructure/huggingface-space/jimsai-embedding-service/
```

Render hosts only the bounded training service from:

```text
services/training-pipeline/
```

Kaggle is used only for offline GPU training/evaluation artifacts.

## Required Production Schema

Run this file manually in Supabase SQL Editor after every schema change:

```text
infrastructure/postgres/supabase.sql
```

This schema includes:

```text
signatures
training_panel_items
chat_threads
chat_messages
user_feedback
memory_signatures
memory_chunks
retrieval_events
retrieval_misses
autonomous_runs
autonomous_jobs
ingestion_cursors
training_batches
training_artifacts
evaluation_reports
approval_queue
workspace tables and metrics tables
```

`chat_threads` and `chat_messages` are required for production multi-thread chat history. The frontend keeps a local cache for responsiveness, but Lambda persists thread history through Supabase.

## Environment Rules

Do not commit real `.env` files. The only tracked env files should be:

```text
.env.example
.env.production.example
```

Rotate any secret that has been pasted into chat, logs, screenshots, or commits.

## Lambda Environment

Set these in AWS Lambda from local `.env`:

```text
JIMS_STORAGE_BACKEND=production
JIMS_STRICT_PROVIDER_STARTUP=true
JIMS_AUTH_PROVIDER=supabase
JIMS_AUTH_REQUIRED=true
JIMS_SUPABASE_DEFAULT_SCOPES=runtime:query training:read training:write feedback:write

SUPABASE_URL
SUPABASE_SERVICE_KEY
SUPABASE_ANON_KEY

JIMS_EMBEDDING_SERVICE_URL=https://jimstechai-jimsai-embedding-service.hf.space
JIMS_EMBEDDING_SERVICE_TOKEN
JIMS_ENABLE_MULTIMODAL_ENCODERS=true
JIMS_MULTIMODAL_ENCODER_MODE=external
JIMS_MULTIMODAL_ENCODER_URL=https://jimstechai-jimsai-embedding-service.hf.space
JIMS_MULTIMODAL_ENCODER_API_KEY

CF_ACCOUNT_ID
CF_VECTORIZE_INDEX
CF_VECTORIZE_API_TOKEN
CF_VECTORIZE_DIMENSIONS=768
CF_R2_BUCKET
CF_R2_ACCESS_KEY
CF_R2_SECRET_KEY

NEO4J_URI
NEO4J_USER
NEO4J_PASSWORD
NEO4J_DATABASE

REDIS_URL
GROQ_API_KEY
```

Deploy Lambda zip code with:

```powershell
.\infrastructure\aws-lambda\deploy-lambda-zip.ps1
```

For environment-only changes, use the no-BOM JSON approach documented in:

```text
infrastructure/aws-lambda/LAMBDA_DEPLOYMENT_GUIDE.md
```

## Hugging Face Embedding Service

The Space is public so Lambda and Render can reach it. Work endpoints are protected by bearer token.

Required Space secrets:

```text
JIMS_RENDER_AGENT_TOKEN
JIMS_EMBEDDING_MODEL=intfloat/multilingual-e5-small
JIMS_EMBEDDING_DIMENSIONS=768
JIMS_EMBEDDING_HASH_FALLBACK_ENABLED=true
JIMS_ACTIVE_ARTIFACT_ID=base_encoder
```

Smoke test:

```powershell
$token = "<JIMS_RENDER_AGENT_TOKEN>"
Invoke-RestMethod `
  -Method Post `
  -Uri "https://jimstechai-jimsai-embedding-service.hf.space/v1/embed" `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body '{"texts":["Why did the dashboard show records but no UI?"],"purpose":"query"}'
```

Expected:

```text
fallback=false
dimension=768
model=intfloat/multilingual-e5-small
```

## Render Training Service

`render.yaml` defines `jimsai-training-service` only. The embedding service is no longer deployed on Render.

Required Render secrets:

```text
JIMS_RENDER_AGENT_TOKEN
JIMS_EMBEDDING_SERVICE_URL=https://jimstechai-jimsai-embedding-service.hf.space
JIMS_EMBEDDING_SERVICE_TOKEN
SUPABASE_URL
SUPABASE_SERVICE_KEY
SUPABASE_ANON_KEY
CF_ACCOUNT_ID
CF_VECTORIZE_INDEX
CF_VECTORIZE_API_TOKEN
NEO4J_URI
NEO4J_USER
NEO4J_PASSWORD
KAGGLE_USERNAME
KAGGLE_API_TOKEN
KAGGLE_DATASET_OWNER
GROQ_API_KEY
```

If a protected endpoint returns:

```json
{"detail":"agent token not configured"}
```

then `JIMS_RENDER_AGENT_TOKEN` is missing in Render. Add it and redeploy.

## External Cron

Use cron-job.org, Better Stack, UptimeRobot, or equivalent.

Every 5 minutes:

```text
GET https://jimstechai-jimsai-embedding-service.hf.space/health
GET https://jimsai-training-service.onrender.com/health
GET https://7x27vovhmfnhcymm5ox3qiw4fy0agvcy.lambda-url.us-east-1.on.aws/health
```

Every 30 minutes:

```text
POST https://jimsai-training-service.onrender.com/v1/autonomous/ingest-batch
Authorization: Bearer <JIMS_RENDER_AGENT_TOKEN>
Content-Type: application/json

{"documents":[]}
```

Every 30 minutes:

```text
POST https://jimsai-training-service.onrender.com/v1/autonomous/reembed-hash
Authorization: Bearer <JIMS_RENDER_AGENT_TOKEN>
Content-Type: application/json

{"limit":50}
```

Every 6 hours:

```text
POST https://jimsai-training-service.onrender.com/v1/autonomous/evaluate
Authorization: Bearer <JIMS_RENDER_AGENT_TOKEN>
Content-Type: application/json

{}
```

Daily:

```text
POST /v1/autonomous/plan
POST /v1/autonomous/report
```

Weekly or threshold-based:

```text
POST /v1/autonomous/kaggle/package
```

## Verification

Run after deploy:

```powershell
Invoke-RestMethod "https://7x27vovhmfnhcymm5ox3qiw4fy0agvcy.lambda-url.us-east-1.on.aws/health"
Invoke-RestMethod "https://jimstechai-jimsai-embedding-service.hf.space/health"
Invoke-RestMethod "https://jimsai-training-service.onrender.com/health"
```

Authenticated checks from the frontend:

```text
Sign in
Send chat message
Switch/new/delete chat thread
Click Learn This
Click Unlearn
Open Training -> Feedback
Open Training -> Memory
Open Training -> Autonomous
```

Backend endpoints involved:

```text
POST   /v1/query
POST   /v1/feedback
POST   /v1/training/ingest
POST   /v1/memory/delete
GET    /v1/chat/threads
GET    /v1/chat/threads/{thread_id}/messages
DELETE /v1/chat/threads/{thread_id}
GET    /v1/training/panels/{panel}/items
```

## Availability Note

Hugging Face CPU Basic gives enough RAM for `intfloat/multilingual-e5-small` and sleeps after 48 hours of inactivity on the free tier. For a hard 99.9% sentence-transformer availability target, move the embedding service to paid always-on hardware or a host with minimum instances. Keep hash fallback enabled only for rare degradation and use `/v1/autonomous/reembed-hash` to replace fallback vectors later.
