# Render Auto-Deploy Guide

This repo now defines two Render web services in `render.yaml`:

- `jimsai-embedding-service`
- `jimsai-training-service`

Both are stateless web services. `/health` is public. All work endpoints require:

```text
Authorization: Bearer <JIMS_RENDER_AGENT_TOKEN>
```

## Important Uptime Note

Render Free services can sleep. With external pings they can be usually reachable, but not 99.9% guaranteed. If sentence-transformer embedding must be available 99.9% of the time, use a paid Render instance or another host with minimum instances enabled.

Recommended production stance:

```text
Primary: sentence-transformer embedding service
Fallback: hash embedding only when the service is unavailable
Recovery: /v1/autonomous/reembed-hash converts fallback vectors later
```

## 1. Create The Render Blueprint

1. Go to Render Dashboard.
2. Click **New +**.
3. Select **Blueprint**.
4. Connect the GitHub repo:

```text
https://github.com/jimsai-admin/jimsai
```

5. Choose the branch:

```text
main
```

6. Render should detect `render.yaml`.
7. Approve creation of both web services.

## 2. Embedding Service Environment

Set these on `jimsai-embedding-service` for Render Free:

```text
JIMS_RENDER_AGENT_TOKEN=<same-long-random-token-used-by-training-service>
JIMS_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
JIMS_EMBEDDING_DIMENSIONS=768
JIMS_EMBEDDING_DEVICE=cpu
JIMS_EMBEDDING_PRELOAD_ON_STARTUP=true
JIMS_EMBEDDING_TORCH_DTYPE=auto
JIMS_EMBEDDING_HASH_FALLBACK_ENABLED=true
JIMS_ACTIVE_ARTIFACT_ID=base_encoder
```

`sentence-transformers/all-MiniLM-L6-v2` is the Free-tier-safe default. It is still a SentenceTransformer model, but much smaller than `intfloat/multilingual-e5-small`.

For a paid always-on Render instance with more memory, use the stronger multilingual model:

```text
JIMS_EMBEDDING_MODEL=intfloat/multilingual-e5-small
JIMS_EMBEDDING_TORCH_DTYPE=float16
```

Use `false` for `JIMS_EMBEDDING_HASH_FALLBACK_ENABLED` only if you want embedding calls to fail instead of degrading. For live chat, keep it `true` and rely on re-embedding recovery.

## 3. Training Service Environment

Set these on `jimsai-training-service`:

```text
JIMS_RENDER_AGENT_TOKEN=<same-token>
JIMS_EMBEDDING_SERVICE_URL=https://jimsai-embedding-service.onrender.com
JIMS_EMBEDDING_SERVICE_TOKEN=<same-token>
JIMS_STORAGE_BACKEND=production
JIMS_STRICT_PROVIDER_STARTUP=true
JIMS_AUTH_PROVIDER=supabase
JIMS_AUTH_REQUIRED=true
JIMS_CLOUD_AUTHORITATIVE=true
SUPABASE_URL=<supabase-url>
SUPABASE_SERVICE_KEY=<service-role-key>
SUPABASE_ANON_KEY=<anon-key>
CF_ACCOUNT_ID=<cloudflare-account-id>
CF_VECTORIZE_INDEX=<vectorize-index>
CF_VECTORIZE_API_TOKEN=<vectorize-token>
CF_VECTORIZE_DIMENSIONS=768
NEO4J_URI=<neo4j-uri>
NEO4J_USER=neo4j
NEO4J_PASSWORD=<neo4j-password>
NEO4J_DATABASE=neo4j
KAGGLE_USERNAME=<kaggle-username>
KAGGLE_API_TOKEN=<kaggle-token>
KAGGLE_DATASET_OWNER=<kaggle-username>
GROQ_API_KEY=<groq-key>
```

Optional Redis/Celery:

```text
REDIS_URL=<redis-url>
```

## 4. Lambda Environment After Render Is Live

After `jimsai-embedding-service` responds successfully, add these to Lambda:

```text
JIMS_EMBEDDING_SERVICE_URL=https://jimsai-embedding-service.onrender.com
JIMS_EMBEDDING_SERVICE_TOKEN=<same-token>
JIMS_ENABLE_MULTIMODAL_ENCODERS=true
JIMS_MULTIMODAL_ENCODER_MODE=external
```

Then redeploy/update Lambda env using:

```powershell
.\infrastructure\aws-lambda\deploy-with-aws-cli.ps1
```

## 5. External Cron

Use cron-job.org, Better Stack, UptimeRobot, or a similar external scheduler.

Every 5 minutes:

```text
GET https://jimsai-embedding-service.onrender.com/health
GET https://jimsai-training-service.onrender.com/health
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

## 6. Smoke Tests

Embedding:

```powershell
$token = "<JIMS_RENDER_AGENT_TOKEN>"
Invoke-RestMethod `
  -Method Post `
  -Uri "https://jimsai-embedding-service.onrender.com/v1/embed" `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body '{"texts":["Why did the dashboard show records but no UI?"],"purpose":"query"}'
```

Training:

```powershell
$token = "<JIMS_RENDER_AGENT_TOKEN>"
Invoke-RestMethod `
  -Method Post `
  -Uri "https://jimsai-training-service.onrender.com/v1/autonomous/discover" `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body '{"limit":10}'
```

Recovery re-embedding:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "https://jimsai-training-service.onrender.com/v1/autonomous/reembed-hash" `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body '{"limit":50}'
```

## 7. Auto-Deploy Behavior

With the Blueprint connected to GitHub:

```text
git push origin main
  -> Render deploys both services from render.yaml
  -> Vercel deploys frontend from /frontend
```

Do not commit real `.env` or `.env.local` files. Use Render/Vercel/AWS environment-variable settings for secrets.
