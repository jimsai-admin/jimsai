# JIMS-AI Vercel + Lambda + Render Deployment

This is the cloud split for the low-cost deployment path:

- Vercel: Next.js frontend from `frontend/`
- AWS Lambda: FastAPI API gateway from `services/api-gateway/`
- Render: free FastAPI training service from `services/training-pipeline/`
- Kaggle: GPU training only, via private dataset/notebook handoff
- Supabase, Neo4j Aura, Redis Cloud, Cloudflare R2, and Cloudflare Vectorize: managed state providers
- Groq: bounded transformer calls only when the deterministic runtime cannot skip them

## Runtime Contract

The frontend calls:

- `GET /health`
- `GET /v1/auth/config`
- `POST /v1/auth/signin`
- `POST /v1/auth/signup`
- `POST /v1/auth/refresh`
- `POST /v1/query`
- `POST /v1/feedback`
- `POST /v1/training/ingest`
- `GET /v1/training/panels/{panel}/items`
- `POST /v1/review/action`
- `POST /v1/memory/update`
- `POST /v1/memory/delete`
- `POST /v1/training/kaggle/run`
- `POST /v1/training/kaggle/{run_id}/sync`

## Environment Split

Set these on Vercel:

```text
NEXT_PUBLIC_API_BASE_URL=https://your-lambda-api-url
NEXT_PUBLIC_SUPABASE_URL=https://project-ref.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
```

Set these on Lambda and Render:

```text
JIMS_STORAGE_BACKEND=production
JIMS_STRICT_PROVIDER_STARTUP=true
JIMS_AUTH_PROVIDER=supabase
JIMS_AUTH_REQUIRED=true
JIMS_SUPABASE_DEFAULT_SCOPES=runtime:query training:read training:write feedback:write
CORS_ORIGINS=https://your-vercel-app.vercel.app

SUPABASE_URL=...
SUPABASE_SERVICE_KEY=...
SUPABASE_ANON_KEY=...

JIMS_GRAPH_PROVIDER=neo4j_aura
JIMS_ENABLE_NEO4J=true
NEO4J_URI=...
NEO4J_USER=neo4j
NEO4J_PASSWORD=...
NEO4J_DATABASE=neo4j

REDIS_URL=rediss://default:password@host:port/0
JIMS_CELERY_KEY_PREFIX=jimsai_

CF_ACCOUNT_ID=...
CF_R2_BUCKET=jimsai-files
CF_R2_ACCESS_KEY=...
CF_R2_SECRET_KEY=...
CF_VECTORIZE_INDEX=jimsai-embeddings
CF_VECTORIZE_API_TOKEN=...
CF_VECTORIZE_DIMENSIONS=768

KAGGLE_USERNAME=...
KAGGLE_API_TOKEN=...
KAGGLE_DATASET_OWNER=...
JIMS_ENCODER_BASE_MODEL=intfloat/multilingual-e5-small
JIMS_SPPE_RENDERER_BASE_MODEL=TinyLlama/TinyLlama-1.1B-Chat-v1.0
JIMS_AUTO_TRAINING_ENABLED=false
JIMS_AUTO_TRAIN_MIN_RETRIEVAL_MISSES=20
JIMS_AUTO_TRAIN_MIN_SPPE_RENDER_PAIRS=10000

GROQ_API_KEY=...
JIMS_ENABLE_GROQ_T1=true
JIMS_ENABLE_GROQ_T2=true
JIMS_ENABLE_GROQ_CANVAS=true
JIMS_ENABLE_GROQ_INVENTION=true
JIMS_ADAPTIVE_TRANSFORMER_THINNING=true
```

Set this on Render only if you enable autonomous control endpoints:

```text
JIMS_RENDER_AGENT_TOKEN=<long-random-token>
```

Then call Render autonomous endpoints with `Authorization: Bearer <long-random-token>`.

Do not put `SUPABASE_SERVICE_KEY`, Redis, Neo4j, Cloudflare, Kaggle, or Groq secrets in Vercel public variables.

## Deploy

### 1. Commit And Push

```bash
git status --short
git add DEPLOYMENT_STACK_VERCEL_LAMBDA_RENDER.md render.yaml frontend/vercel.json infrastructure/aws-lambda services/api-gateway frontend/app/training/TrainingPanelClient.tsx prototype/jimsai services/multimodal-encoder/app/main.py .env.example .env.production.example tests/test_kaggle_training_packages.py
git commit -m "Prepare cloud deployment stack"
git push origin main
```

Do not commit `.env`. It contains real provider secrets.

### 2. Vercel From GitHub

In Vercel:

1. Add New Project.
2. Import `jimsai-admin/jimsai`.
3. Set Root Directory to `frontend`.
4. Framework preset: Next.js.
5. Add environment variables:
   - `NEXT_PUBLIC_API_BASE_URL`
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
6. Deploy.

For the first deploy, `NEXT_PUBLIC_API_BASE_URL` can be a temporary placeholder. After AWS Lambda is deployed, update it to the Lambda Function URL and redeploy.

### 3. Render From GitHub

In Render:

1. New -> Blueprint.
2. Connect `jimsai-admin/jimsai`.
3. Select the repo root `render.yaml`.
4. Fill every `sync: false` secret in the dashboard.
5. Create the Blueprint.

The Render service uses `autoDeployTrigger: commit`, so every commit to the linked branch triggers a deploy.

For the $0 path, `render.yaml` deploys a web service on `plan: free` and exposes `/health` for Render health checks and external keep-alive pings. Render background workers and cron jobs do not support the free instance type in the current Blueprint spec, so a true Celery worker requires switching the service back to `type: worker` and using a paid plan such as `starter`.

Free Render web services can spin down after inactivity. If you want to keep this service warm, point an external cron/ping service at:

```text
https://<your-render-service>.onrender.com/health
```

Use a 10 to 14 minute interval. The service should not be used as the frontend API base URL; the frontend continues to call AWS Lambda.

The free Render service exposes bounded control endpoints for ingestion/training orchestration:

- `POST /v1/autonomous/ingest-batch`: ingest up to 100 documents into Supabase/Vectorize/Neo4j.
- `POST /v1/autonomous/cycle`: run one bounded autonomous cycle. Use an external cron rather than an infinite loop on the free web service.
- `POST /v1/autonomous/kaggle/run`: package persisted SPPE/signature history for Kaggle GPU training.

Keep `/health` public for uptime pings. Protect the autonomous endpoints with `JIMS_RENDER_AGENT_TOKEN`.

### 4. AWS Lambda With AWS CLI

Install Docker and AWS CLI, then authenticate:

```bash
aws configure
aws sts get-caller-identity
```

After Vercel gives you a URL, deploy the Lambda API with that URL as the CORS origin:

```powershell
.\infrastructure\aws-lambda\deploy-with-aws-cli.ps1 `
  -Region us-east-1 `
  -FunctionName jimsai-api-gateway `
  -CorsAllowOrigin https://your-vercel-app.vercel.app
```

The script prints `Lambda Function URL`. Put that URL into Vercel as `NEXT_PUBLIC_API_BASE_URL`, then trigger a new Vercel production deploy.

SAM is also available through `infrastructure/aws-lambda/template.yaml`, but the PowerShell script is the direct AWS CLI path.

## Provider Verification

After Lambda is deployed:

```bash
curl https://your-lambda-api-url/health
curl https://your-lambda-api-url/v1/auth/config
```

After signing in from the frontend, open the training feedback panel or call:

```bash
curl -H "Authorization: Bearer <supabase-access-token>" \
  https://your-lambda-api-url/v1/providers/readiness
```

All production providers should report `configured=true` and `available=true` before real users rely on the deployment.

## Training Flow

Encoder job:

- Trigger from Training -> Pipeline -> Kaggle Encoder.
- Input: accumulated SPPE pairs, signatures, and world-model candidates.
- Base: `intfloat/multilingual-e5-small`.
- Output: private Kaggle artifact package with optional `sentence_transformer` weights.
- To run the actual SentenceTransformer fine-tune on Kaggle GPU, open the generated `jimsai_encoder_finetune.ipynb`, enable a GPU accelerator, attach the private training dataset, and set `JIMS_RUN_SENTENCE_TRANSFORMER_FINETUNE=1` in the notebook environment before running all cells. Lambda intentionally does not install `sentence-transformers`.

SPPE renderer job:

- Trigger from Training -> Pipeline -> Kaggle Renderer.
- Input: accepted `(SemanticIntentionGraph, original_text)` pairs.
- Base: `TinyLlama/TinyLlama-1.1B-Chat-v1.0` by default, with `microsoft/phi-2` documented as an alternative.
- Output: private Kaggle artifact package with optional renderer model weights.

Kaggle is used only for training artifacts. Runtime query handling, auth, memory writes, retrieval, graph storage, and session/cache state stay in the deployed services and managed providers.
