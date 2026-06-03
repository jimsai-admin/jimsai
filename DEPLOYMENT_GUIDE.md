# JIMS-AI Production Deployment Guide

Status date: June 3, 2026

This is the deployment source of truth for the current codebase. It reflects the production stack that is actually implemented now: Vercel frontend, AWS Lambda FastAPI backend, Hugging Face Space embedding/local-model service, Render autonomous training service, Supabase, Cloudflare Vectorize, Neo4j, Redis, and Kaggle artifact packaging.

## 1. Live Services

```text
Frontend:
https://jimsai.vercel.app

AWS Lambda API:
https://7x27vovhmfnhcymm5ox3qiw4fy0agvcy.lambda-url.us-east-1.on.aws

Hugging Face local model service:
https://jimstechai-jimsai-embedding-service.hf.space

Render autonomous training service:
https://jimsai-training-service.onrender.com
```

## 2. Production Topology

```text
Vercel Next.js UI
  -> AWS Lambda FastAPI API
    -> Supabase Auth/Postgres
    -> Hugging Face Space
       -> intfloat/multilingual-e5-small embeddings
       -> MoritzLaurer/mDeBERTa-v3-base-mnli-xnli capability classifier
       -> Qwen3-1.7B GGUF for bounded T1/routing JSON
       -> Qwen3-4B GGUF for bounded T2/render/ingestion JSON
    -> Cloudflare Vectorize
    -> Neo4j Aura graph memory
    -> Redis cache/session state

External cron
  -> Render autonomous training service
    -> Supabase autonomous state and review queues
    -> Hugging Face embeddings
    -> Cloudflare Vectorize re-embedding/upserts
    -> Kaggle offline artifact packages
```

External Groq is no longer required for runtime. The code still has legacy flag names such as `JIMS_ENABLE_GROQ_T1`, but the model bridge routes those bounded interfaces to the Hugging Face Space when local mode is enabled and `JIMS_ALLOW_EXTERNAL_GROQ=false`.

## 3. Repository Components

```text
frontend/                                      Next.js Vercel UI
services/api-gateway/                          FastAPI Lambda app
services/training-pipeline/                    Render autonomous training service
infrastructure/huggingface-space/jimsai-embedding-service/
                                                Hugging Face embedding/router/Qwen service
infrastructure/postgres/supabase.sql            Supabase schema source of truth
infrastructure/aws-lambda/deploy-lambda-zip.ps1 Lambda build/deploy script
prototype/jimsai/                               Core runtime, routing, memory, training logic
```

## 4. Secret Rules

Do not commit real `.env` files. Only examples are tracked:

```text
.env.example
.env.production.example
```

Rotate any secret that has been pasted into chat, screenshots, logs, or commits. Frontend variables must only be public variables; provider secrets stay in Lambda, Render, Hugging Face Space secrets, or local `.env`.

## 5. Supabase Schema

Run this file manually in Supabase SQL Editor after schema changes:

```text
infrastructure/postgres/supabase.sql
```

The production schema includes:

```text
signatures
execution_traces
training_panel_items
workspaces
workspace_members
jimsai_events
request_audit
sppe_pairs
memory_signatures
memory_chunks
retrieval_events
retrieval_misses
user_feedback
chat_threads
chat_messages
autonomous_runs
autonomous_jobs
ingestion_cursors
training_batches
training_artifacts
evaluation_reports
approval_queue
workspace_metrics
workspace_quotas
query_patterns
user_preferences
workspace_adapters
provider_state
system_metrics
```

`chat_threads` and `chat_messages` are required for ChatGPT/Claude-style persistent multi-thread chat. `user_feedback`, `memory_signatures`, `memory_chunks`, `retrieval_events`, and `retrieval_misses` are required for learn, unlearn, recovery, and training quality loops.

## 6. Vercel Frontend

Vercel deploys the Next.js UI from GitHub.

Required Vercel variables:

```text
NEXT_PUBLIC_API_BASE_URL=https://7x27vovhmfnhcymm5ox3qiw4fy0agvcy.lambda-url.us-east-1.on.aws
NEXT_PUBLIC_SUPABASE_URL=<supabase-url>
NEXT_PUBLIC_SUPABASE_ANON_KEY=<supabase-anon-key>
```

Do not set service keys, Hugging Face tokens, Cloudflare tokens, Neo4j passwords, Redis URLs, Kaggle tokens, or Render agent tokens in public Vercel variables.

Frontend expectations:

```text
login works through Lambda/Supabase
chat thread list loads from Lambda
messages persist in Supabase
thread creation/deletion works
Markdown answers render cleanly
feedback/learn submits to /v1/feedback
unlearn/delete memory calls the Lambda memory endpoint
training panels show Supabase-backed records
```

## 7. AWS Lambda API

Lambda hosts `services/api-gateway` with handler:

```text
app.lambda_handler.handler
```

Recommended configuration:

```text
runtime=Python 3.11
memory=1024 MB
timeout=120 seconds
```

Deploy code:

```powershell
cd C:\Users\ajibe\Jims-AI
.\infrastructure\aws-lambda\deploy-lambda-zip.ps1
```

The deploy script builds `.lambda-build`, installs `services/api-gateway/requirements.lambda.txt`, copies `services/api-gateway/app` and `prototype`, zips the package, uploads to S3, and updates the Lambda function.

Required Lambda variables:

```text
JIMS_STORAGE_BACKEND=production
JIMS_STRICT_PROVIDER_STARTUP=false
JIMS_AUTH_PROVIDER=supabase
JIMS_AUTH_REQUIRED=true
JIMS_SUPABASE_DEFAULT_SCOPES=runtime:query training:read training:write feedback:write
CORS_ORIGINS=https://jimsai.vercel.app

SUPABASE_URL
SUPABASE_SERVICE_KEY
SUPABASE_ANON_KEY

JIMS_EMBEDDING_SERVICE_URL=https://jimstechai-jimsai-embedding-service.hf.space
JIMS_EMBEDDING_SERVICE_TOKEN
JIMS_ENABLE_MULTIMODAL_ENCODERS=true
JIMS_MULTIMODAL_ENCODER_MODE=external
JIMS_MULTIMODAL_ENCODER_URL=https://jimstechai-jimsai-embedding-service.hf.space
JIMS_MULTIMODAL_ENCODER_API_KEY

JIMS_LLM_PROVIDER=local
JIMS_ENABLE_LOCAL_QWEN=true
JIMS_QWEN_SERVICE_URL=https://jimstechai-jimsai-embedding-service.hf.space
JIMS_QWEN_SERVICE_TOKEN
JIMS_QWEN_MODEL=qwen3-1.7b-instruct
JIMS_LOCAL_INFERENCE_URL=https://jimstechai-jimsai-embedding-service.hf.space
JIMS_LOCAL_INFERENCE_API_KEY
JIMS_LOCAL_INFERENCE_MODEL=qwen3-1.7b-instruct
JIMS_LOCAL_INFERENCE_CHAT_PATH=/v1/chat/completions
JIMS_LOCAL_RENDER_MODEL=qwen3-4b-instruct
JIMS_LOCAL_RENDER_CHAT_PATH=/v1/chat/render
JIMS_LOCAL_INFERENCE_TIMEOUT=120
JIMS_LOCAL_RENDER_TIMEOUT=180
JIMS_ALLOW_EXTERNAL_GROQ=false
GROQ_API_KEY=

JIMS_ENABLE_GROQ_T1=false
JIMS_ENABLE_GROQ_T2=true
JIMS_ENABLE_GROQ_INGEST=true
JIMS_ENABLE_GROQ_CANVAS=true
JIMS_ENABLE_GROQ_INVENTION=true
JIMS_ADAPTIVE_TRANSFORMER_THINNING=true

JIMS_ENABLE_SEMANTIC_CAPABILITY_ROUTER=true
JIMS_ENABLE_ZERO_SHOT_CAPABILITY_ROUTER=true
JIMS_ENABLE_LLM_CAPABILITY_ROUTER=true
JIMS_CAPABILITY_EMBEDDING_SERVICE_URL=https://jimstechai-jimsai-embedding-service.hf.space
JIMS_CAPABILITY_EMBEDDING_SERVICE_TOKEN
JIMS_CAPABILITY_CLASSIFIER_URL=https://jimstechai-jimsai-embedding-service.hf.space
JIMS_CAPABILITY_CLASSIFIER_TOKEN

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
```

Direct Lambda health test:

```powershell
$payload = '{"version":"2.0","routeKey":"GET /health","rawPath":"/health","rawQueryString":"","headers":{"host":"localhost"},"requestContext":{"http":{"method":"GET","path":"/health","sourceIp":"127.0.0.1","userAgent":"test"},"accountId":"095931689519","stage":"$default"},"isBase64Encoded":false}'
$payload | Set-Content "$env:TEMP\jimsai-health.json" -Encoding ascii
aws lambda invoke --function-name jimsai-api-gateway --region us-east-1 --cli-binary-format raw-in-base64-out --payload "file://$env:TEMP\jimsai-health.json" "$env:TEMP\jimsai-health-response.json"
Get-Content "$env:TEMP\jimsai-health-response.json"
```

## 8. Hugging Face Space

The Hugging Face Space is deployed from:

```text
infrastructure/huggingface-space/jimsai-embedding-service/
```

Runtime endpoints:

```text
GET  /health
GET  /ready
POST /v1/embed
POST /v1/embed-batch
POST /v1/encode
POST /v1/classify/capability
POST /v1/chat/completions
POST /v1/chat/render
GET  /v1/artifact/current
POST /v1/reload-artifact
GET  /v1/warm
POST /v1/warm
```

Protected endpoints require:

```text
Authorization: Bearer <JIMS_RENDER_AGENT_TOKEN>
```

Required Space secrets:

```text
JIMS_RENDER_AGENT_TOKEN
HF_TOKEN
JIMS_EMBEDDING_MODEL=intfloat/multilingual-e5-small
JIMS_EMBEDDING_DIMENSIONS=768
JIMS_EMBEDDING_DEVICE=cpu
JIMS_EMBEDDING_HASH_FALLBACK_ENABLED=true
JIMS_ACTIVE_ARTIFACT_ID=base_encoder

JIMS_QWEN_ENABLED=true
JIMS_QWEN_MODEL_REPO=ggml-org/Qwen3-1.7B-GGUF
JIMS_QWEN_MODEL_FILE=Qwen3-1.7B-Q4_K_M.gguf
JIMS_QWEN_MODEL=qwen3-1.7b-instruct
JIMS_QWEN_CONTEXT=4096
JIMS_QWEN_MAX_TOKENS=256
JIMS_QWEN_BATCH=64
JIMS_QWEN_THREADS=2

JIMS_RENDER_MODEL_REPO=Qwen/Qwen3-4B-GGUF
JIMS_RENDER_MODEL_FILE=Qwen3-4B-Q4_K_M.gguf
JIMS_RENDER_MODEL_NAME=qwen3-4b-instruct
JIMS_RENDER_CONTEXT=8192
JIMS_RENDER_MAX_TOKENS=1200
JIMS_RENDER_BATCH=128
JIMS_RENDER_THREADS=2
```

Do not duplicate the same key in both public Variables and private Secrets. Hugging Face Spaces reports a configuration collision if a key exists in both places.

Smoke tests:

```powershell
$token = "<JIMS_RENDER_AGENT_TOKEN>"
$headers = @{ Authorization = "Bearer $token" }

Invoke-RestMethod "https://jimstechai-jimsai-embedding-service.hf.space/health"
Invoke-RestMethod "https://jimstechai-jimsai-embedding-service.hf.space/ready"

Invoke-RestMethod -Method Post `
  -Uri "https://jimstechai-jimsai-embedding-service.hf.space/v1/embed" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body '{"texts":["Why did the dashboard show records but no UI?"],"purpose":"query"}'

Invoke-RestMethod -Method Post `
  -Uri "https://jimstechai-jimsai-embedding-service.hf.space/v1/chat/completions" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body '{"messages":[{"role":"system","content":"Return JSON only."},{"role":"user","content":"Classify: calculate 18/3"}],"response_format":{"type":"json_object"},"max_tokens":80}'
```

## 9. Render Training Service

Render deploys from GitHub using `render.yaml`.

Service:

```text
jimsai-training-service
```

Root/runtime:

```text
services/training-pipeline
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Required Render variables:

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
```

Render endpoints:

```text
GET  /health
GET  /metrics
GET  /trace
GET  /v1/contract
POST /v1/execute
POST /v1/autonomous/cycle
POST /v1/autonomous/discover
POST /v1/autonomous/ingest-batch
POST /v1/autonomous/evaluate
POST /v1/autonomous/plan
POST /v1/autonomous/report
POST /v1/autonomous/kaggle/package
POST /v1/autonomous/reembed-hash
```

Protected autonomous calls:

```powershell
$token = "<JIMS_RENDER_AGENT_TOKEN>"
Invoke-RestMethod -Method Post `
  -Uri "https://jimsai-training-service.onrender.com/v1/autonomous/report" `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body '{"workspace_id":"default","limit":25}'
```

## 10. External Cron

Use cron-job.org, Better Stack, UptimeRobot, or similar.

Every 5 minutes:

```text
GET https://jimstechai-jimsai-embedding-service.hf.space/health
GET https://jimstechai-jimsai-embedding-service.hf.space/ready
GET https://jimsai-training-service.onrender.com/health
GET https://7x27vovhmfnhcymm5ox3qiw4fy0agvcy.lambda-url.us-east-1.on.aws/health
```

Every 30 minutes:

```text
POST https://jimsai-training-service.onrender.com/v1/autonomous/ingest-batch
POST https://jimsai-training-service.onrender.com/v1/autonomous/reembed-hash
```

Every 6 hours:

```text
POST https://jimsai-training-service.onrender.com/v1/autonomous/evaluate
```

Daily:

```text
POST https://jimsai-training-service.onrender.com/v1/autonomous/plan
POST https://jimsai-training-service.onrender.com/v1/autonomous/report
```

Weekly or threshold-based:

```text
POST https://jimsai-training-service.onrender.com/v1/autonomous/kaggle/package
```

Protected cron POSTs must include:

```text
Authorization: Bearer <JIMS_RENDER_AGENT_TOKEN>
```

## 11. Validation Checklist

Run these before handoff:

```text
Supabase schema has been applied
Vercel login works
Lambda /health works by direct invoke
Frontend can call Lambda /v1/auth/config
Chat prompt creates/updates a Supabase thread
Markdown answer renders correctly in chat
Feedback submits to /v1/feedback
Learn-this feedback appears in training/feedback panel
Unlearn/delete memory endpoint removes the target memory
HF /v1/embed returns fallback=false and dimension=768
HF /v1/classify/capability returns ranked capability scores
HF /v1/chat/completions returns JSON through Qwen3-1.7B
HF /v1/chat/render returns JSON through Qwen3-4B when warmed
Render /health reports agent token configured
Render autonomous report/plan endpoints write Supabase run records
Vectorize top-k retrieval hydrates Supabase records
Hash fallback records are marked reembedding_required and recover through /v1/autonomous/reembed-hash
```

## 12. Known Operational Notes

Qwen3-1.7B and Qwen3-4B on Hugging Face CPU Basic are useful as bounded local interfaces, not high-throughput frontier replacements. Keep Qwen lazy where possible and use deterministic routing, symbolic math, structured retrieval, and CSSE rendering when confidence is high.

Complex math and physics route to `math_science`. Bounded arithmetic/equation tasks execute through the internal symbolic solver. Broader scientific tasks should use retrieval, validation, and future solver adapters rather than unsupported guessing.

Coding prompts route to `coding` across programming languages, logs, SQL, APIs, tests, deployment, and repository work. Execution still requires approved adapters or sandbox paths; routing alone does not mean unsafe code is executed.
