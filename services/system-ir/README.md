# system-ir

## Architecture Mapping

- Layer: Typed IR schema registry
- Purpose: Version Semantic IR, Verified Cognitive Object, and shared semantic state schemas.
- PDF intent: expose deterministic behavior, traces, logs, metrics, and bounded execution for this module.

## Local Setup

```bash
cd services/system-ir
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Docker

```bash
docker build -f services/system-ir/Dockerfile -t jimsai/system-ir:local .
```

## API

- `GET /health`
- `GET /metrics`
- `GET /trace`
- Service endpoints: /v1/ir/schema, /v1/ir/validate

## Tests

```bash
pytest services/system-ir/tests
```
