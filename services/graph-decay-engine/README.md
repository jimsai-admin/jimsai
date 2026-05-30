# graph-decay-engine

## Architecture Mapping

- Layer: Graph optimization
- Purpose: Run contraction shortcuts, A* frontier optimization, bitmap refresh, and generational edge decay.
- PDF intent: expose deterministic behavior, traces, logs, metrics, and bounded execution for this module.

## Local Setup

```bash
cd services/graph-decay-engine
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Docker

```bash
docker build -f services/graph-decay-engine/Dockerfile -t jimsai/graph-decay-engine:local .
```

## API

- `GET /health`
- `GET /metrics`
- `GET /trace`
- Service endpoints: /v1/decay/run, /v1/decay/report

## Tests

```bash
pytest services/graph-decay-engine/tests
```
