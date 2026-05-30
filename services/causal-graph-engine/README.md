# causal-graph-engine

## Architecture Mapping

- Layer: L8 World Model and causal graph
- Purpose: Maintain causal links, dependency traces, reinforcement, and bounded causal traversal.
- PDF intent: expose deterministic behavior, traces, logs, metrics, and bounded execution for this module.

## Local Setup

```bash
cd services/causal-graph-engine
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Docker

```bash
docker build -f services/causal-graph-engine/Dockerfile -t jimsai/causal-graph-engine:local .
```

## API

- `GET /health`
- `GET /metrics`
- `GET /trace`
- Service endpoints: /v1/causal/trace, /v1/causal/reinforce

## Tests

```bash
pytest services/causal-graph-engine/tests
```
