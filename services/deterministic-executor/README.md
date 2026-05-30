# deterministic-executor

## Architecture Mapping

- Layer: Immutable execution pass
- Purpose: Execute validated IR against parameterized handlers, never raw user language.
- PDF intent: expose deterministic behavior, traces, logs, metrics, and bounded execution for this module.

## Local Setup

```bash
cd services/deterministic-executor
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Docker

```bash
docker build -f services/deterministic-executor/Dockerfile -t jimsai/deterministic-executor:local .
```

## API

- `GET /health`
- `GET /metrics`
- `GET /trace`
- Service endpoints: /v1/execute, /v1/execution/trace

## Tests

```bash
pytest services/deterministic-executor/tests
```
