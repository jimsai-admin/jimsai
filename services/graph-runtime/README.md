# graph-runtime

## Architecture Mapping

- Layer: L6 retrieval and Neo4j-backed graph runtime
- Purpose: Expose graph traversal, relationship lookup, concept lattice reads, and traceable graph writes.
- PDF intent: expose deterministic behavior, traces, logs, metrics, and bounded execution for this module.

## Local Setup

```bash
cd services/graph-runtime
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Docker

```bash
docker build -f services/graph-runtime/Dockerfile -t jimsai/graph-runtime:local .
```

## API

- `GET /health`
- `GET /metrics`
- `GET /trace`
- Service endpoints: /v1/graph/traverse, /v1/graph/signature

## Tests

```bash
pytest services/graph-runtime/tests
```
