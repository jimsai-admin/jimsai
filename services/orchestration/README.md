# orchestration

## Architecture Mapping

- Layer: L4 Sparse Activation and Meta-Controller
- Purpose: Route IR objects to retrieval, canvas, invention, simulation, and deterministic execution paths.
- PDF intent: expose deterministic behavior, traces, logs, metrics, and bounded execution for this module.

## Local Setup

```bash
cd services/orchestration
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Docker

```bash
docker build -f services/orchestration/Dockerfile -t jimsai/orchestration:local .
```

## API

- `GET /health`
- `GET /metrics`
- `GET /trace`
- Service endpoints: /v1/orchestrate, /v1/activation/decision

## Tests

```bash
pytest services/orchestration/tests
```
