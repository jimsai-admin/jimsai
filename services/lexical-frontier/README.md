# lexical-frontier

## Architecture Mapping

- Layer: Semantic Expansion Graph / ontology staging
- Purpose: Manage synonym expansion, lexical frontier candidates, staging promotion, and edge decay.
- PDF intent: expose deterministic behavior, traces, logs, metrics, and bounded execution for this module.

## Local Setup

```bash
cd services/lexical-frontier
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Docker

```bash
docker build -f services/lexical-frontier/Dockerfile -t jimsai/lexical-frontier:local .
```

## API

- `GET /health`
- `GET /metrics`
- `GET /trace`
- Service endpoints: /v1/frontier/candidates, /v1/frontier/promote

## Tests

```bash
pytest services/lexical-frontier/tests
```
