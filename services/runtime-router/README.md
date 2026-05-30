# runtime-router

## Architecture Mapping

- Layer: Conditional transformer and module invocation
- Purpose: Decide when to bypass T1/T2 and which deterministic modules must activate.
- PDF intent: expose deterministic behavior, traces, logs, metrics, and bounded execution for this module.

## Local Setup

```bash
cd services/runtime-router
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Docker

```bash
docker build -f services/runtime-router/Dockerfile -t jimsai/runtime-router:local .
```

## API

- `GET /health`
- `GET /metrics`
- `GET /trace`
- Service endpoints: /v1/runtime/route, /v1/runtime/transformer-decision

## Tests

```bash
pytest services/runtime-router/tests
```
