# Deploy and Test the JIMS-AI Prototype

Date: 2026-05-27

## What Runs Today

The Phase 1 prototype runs the strict JIMS-AI request path:

`input -> T1 transformer intent interface -> L1 full encoder -> L2 real-time learning -> L3 active canvas -> L4 sparse activation/meta-controller -> L5 invention engine -> L6 multi-index retrieval -> L7 abstraction engine -> L8 latent world model -> L9 reasoning bridge -> T2 transformer render interface -> output -> feedback`

Local runtime state is in process unless `JIMS_STORAGE_BACKEND` enables external providers. Production mode mirrors training state into R2, Vectorize, Supabase/Postgres, Neo4j Aura, and Redis/Celery.

## Local API

```powershell
python -m pip install -e ".[dev]"
uvicorn prototype.app:app --reload --host 127.0.0.1 --port 8000
```

Useful endpoints:

- `GET /health`
- `GET /metrics`
- `POST /v1/training/ingest`
- `POST /v1/query`
- `POST /v1/feedback`
- `GET /v1/memory/stats`
- `GET /v1/training/dashboard`
- `GET /v1/training/panels/{panel}/items`
- `POST /v1/canvas/run`
- `GET /v1/canvas/status/{session_id}`
- `POST /v1/invention/run`
- `GET /v1/invention/status/{session_id}`

## Local Frontend

```powershell
cd frontend
npm install
$env:NEXT_PUBLIC_API_BASE_URL="http://localhost:8000"
npm run dev -- --port 3001
```

Open:

- `http://localhost:3001/training` for the routed training console. Panel routes live under `/training/{panel}` and page through stored records with infinite loading.
- `http://localhost:3001/user` or `http://localhost:3001/chat` for persistent chat, source attribution, layer trace, simulation, abstraction, world-model activation, memory controls, and feedback.

If the browser shows `__webpack_modules__[moduleId] is not a function`, stop the Next dev server, delete `frontend/.next`, and restart `npm run dev`. Do not run `next build` against the same `.next` cache while the dev server is running.

## Enable Groq Bounded Interfaces

The prototype uses Groq only at bounded transformer boundaries. It does not replace memory, graph, simulation, validation, planning, or CSSE.

```powershell
$env:GROQ_API_KEY="your_key"
$env:GROQ_INTENT_MODEL="openai/gpt-oss-20b"
$env:GROQ_RENDER_MODEL="openai/gpt-oss-20b"
$env:GROQ_CANVAS_MODEL="openai/gpt-oss-120b"
$env:GROQ_INVENTION_MODEL="openai/gpt-oss-120b"
$env:JIMS_ENABLE_GROQ_T1="true"
$env:JIMS_ENABLE_GROQ_T2="true"
$env:JIMS_ENABLE_GROQ_CANVAS="true"
$env:JIMS_ENABLE_GROQ_INVENTION="true"
```

Groq is called through the OpenAI-compatible chat completions endpoint with JSON mode for bounded T1, Canvas, and Invention outputs.

## Docker Compose

```powershell
copy .env.example .env
docker compose up --build
```

Compose includes Redis, Neo4j, PostgreSQL, API Gateway, a Celery training worker, Semantic Compiler, Graph Runtime, and Frontend. The API and worker run with `JIMS_STORAGE_BACKEND=production` in compose.

## Verification

```powershell
python -m pytest
python -m compileall prototype services/api-gateway
cd frontend
npm run build
npm run test:e2e
npm audit --omit=dev
```

The Playwright test expects the API at `http://localhost:8000` and the frontend at `http://127.0.0.1:3001` unless overridden.

## Provider Stack Notes

- Cloudflare R2: use `infrastructure/deployment/cloudflare_r2.md` and set `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `CF_R2_BUCKET`, `CF_R2_ACCESS_KEY`, and `CF_R2_SECRET_KEY`.
- Cloudflare Vectorize: use `infrastructure/deployment/cloudflare_vectorize.md` and set `CF_VECTORIZE_INDEX` and `CF_VECTORIZE_API_TOKEN`.
- Supabase REST/Auth: use `infrastructure/deployment/supabase.md` and set `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, and `SUPABASE_ANON_KEY`.
- Neo4j AuraDB: use `infrastructure/deployment/neo4j_aura.md` and set `JIMS_GRAPH_PROVIDER=neo4j_aura`, `JIMS_ENABLE_NEO4J=true`, `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD`.
- Redis/Celery: set `REDIS_URL` and run `celery -A prototype.jimsai.celery_runtime:celery_app worker --loglevel=INFO`.
- Vast.ai GPU jobs: use `infrastructure/deployment/vast_ai.md` and set `VAST_API_KEY`.
- Multimodal encoding: set `JIMS_ENABLE_MULTIMODAL_ENCODERS=true`, `JIMS_MULTIMODAL_ENCODER_MODE=external`, and `JIMS_MULTIMODAL_ENCODER_URL` for the encoder worker.
