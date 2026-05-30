# memory-runtime

## Architecture Mapping

- Layer: L2 real-time learning and four-layer memory
- Purpose: Store signatures across sensory, working, episodic, and semantic memory with promotion rules.
- PDF intent: expose deterministic behavior, traces, logs, metrics, and bounded execution for this module.

## Local Setup

```bash
cd services/memory-runtime
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Docker

```bash
docker build -f services/memory-runtime/Dockerfile -t jimsai/memory-runtime:local .
```

## API

- `GET /health`
- `GET /metrics`
- `GET /trace`
- Service endpoints: /v1/memory/insert, /v1/memory/search

## Tests

```bash
pytest services/memory-runtime/tests
```
