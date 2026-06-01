# Production Stack

The production runtime is opt-in through `JIMS_STORAGE_BACKEND=production`. In that mode the API pipeline keeps the deterministic in-process runtime, then mirrors training data into real providers:

- Cloudflare R2 stores raw multimodal training assets.
- Cloudflare Vectorize receives signature vectors and metadata.
- Supabase/Postgres stores signatures and `training_panel_items` for cursor-paged operator views.
- Neo4j Aura stores entity, relation, and causal graph edges.
- Redis/Celery queues canvas and invention jobs.
- Supabase Auth bearer tokens protect runtime, training, and feedback routes when `JIMS_AUTH_REQUIRED=true`.
- Multimodal encoders run as an external encoder service for public production.

## Cloud-Only Compose

```bash
docker compose up --build
```

`docker-compose.yml` runs the API gateway, a Celery training worker, and the Next frontend against the cloud providers configured in `.env`. It does not start local Redis, Postgres, or Neo4j containers. With `JIMS_STRICT_PROVIDER_STARTUP=true`, missing cloud credentials block startup.

## External Deployment

1. Copy `.env.production.example` into the target secret manager.
2. Replace all credential placeholders and set `CORS_ORIGINS` to the deployed frontend origin.
3. Run the SQL in `infrastructure/postgres/supabase.sql` against Supabase/Postgres.
4. Start the API image with `JIMS_AUTH_PROVIDER=supabase`, `JIMS_AUTH_REQUIRED=true`, and `JIMS_STRICT_PROVIDER_STARTUP=true`.
5. Start at least one Celery worker with `celery -A prototype.jimsai.celery_runtime:celery_app worker --loglevel=INFO`.
6. For media-heavy training, set `JIMS_ENABLE_MULTIMODAL_ENCODERS=true`, `JIMS_MULTIMODAL_ENCODER_MODE=external`, and point `JIMS_MULTIMODAL_ENCODER_URL` at a separate encoder worker that exposes `GET /health` and `POST /v1/encode`.

## Graph Provider Options

The selected day-one graph runtime is Neo4j Aura through `JIMS_GRAPH_PROVIDER=neo4j_aura`. It is the only graph provider currently wired into the API, and it matches the existing Bolt/Cypher adapter.

Neo4j Aura is the right first choice for this repo because AuraDB Free can be used to start, and AuraDB Professional supports pay-as-you-go billing when the graph needs production sizing. Do not keep a Professional trial running past its trial expiry unless the monthly cost is acceptable. Use an AuraDB Free instance for day-one cloud testing, then upgrade only when the graph exceeds Free-tier limits or needs paid production features.

Memgraph is the closest future alternative because it can expose a Bolt/Cypher-compatible endpoint, but it still needs compatibility testing before it should be enabled. ArcadeDB and TigerGraph are valid graph databases, but they are not drop-in replacements for this adapter and should be added as separate provider adapters.

Keep `JIMS_ENABLE_NEO4J=true` in production. If Aura credentials are missing or invalid, strict startup should fail instead of silently falling back.

## Stored Training Views

Each operator panel is a separate route backed by the same paged API:

```text
GET /v1/training/panels/{panel}/items?limit=20&cursor=0
```

Valid panel IDs are `ingestion`, `review`, `ambiguity`, `memory`, `world-model`, `pipeline`, `sessions`, and `feedback`.
