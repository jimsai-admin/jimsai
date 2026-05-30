# api-gateway

## Architecture Mapping

- Layer: External API layer
- Purpose: Expose query, memory, canvas, invention, reasoning, world model, and feedback endpoints.
- PDF intent: expose deterministic behavior, traces, logs, metrics, and bounded execution for this module.

## Local Setup

```bash
cd services/api-gateway
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Docker

```bash
docker build -f services/api-gateway/Dockerfile -t jimsai/api-gateway:local .
```

## API

- `GET /health`
- `GET /metrics`
- `GET /trace`
- Service endpoints: /v1/query, /v1/query/stream, /v1/memory/search

## Tests

```bash
pytest services/api-gateway/tests
```
