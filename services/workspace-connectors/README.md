# workspace-connectors

## Architecture Mapping

- Layer: Workspace and data ingestion
- Purpose: Connect local files, codebases, object storage, and workspace assets to the ingestion pipeline.
- PDF intent: expose deterministic behavior, traces, logs, metrics, and bounded execution for this module.

## Local Setup

```bash
cd services/workspace-connectors
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Docker

```bash
docker build -f services/workspace-connectors/Dockerfile -t jimsai/workspace-connectors:local .
```

## API

- `GET /health`
- `GET /metrics`
- `GET /trace`
- Service endpoints: /v1/connectors/register, /v1/connectors/ingest

## Tests

```bash
pytest services/workspace-connectors/tests
```
