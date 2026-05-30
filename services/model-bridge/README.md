# model-bridge

## Architecture Mapping

- Layer: Bounded transformer interfaces
- Purpose: Provide controlled adapters for T1/T2, canvas, invention, cloud model providers, and strict bypass.
- PDF intent: expose deterministic behavior, traces, logs, metrics, and bounded execution for this module.

## Local Setup

```bash
cd services/model-bridge
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Docker

```bash
docker build -f services/model-bridge/Dockerfile -t jimsai/model-bridge:local .
```

## API

- `GET /health`
- `GET /metrics`
- `GET /trace`
- Service endpoints: /v1/model/render, /v1/model/intent

## Tests

```bash
pytest services/model-bridge/tests
```

