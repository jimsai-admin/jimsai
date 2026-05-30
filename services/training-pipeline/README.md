# training-pipeline

## Architecture Mapping

- Layer: Unified Training Pipeline
- Purpose: Coordinate encoder signals, world model candidates, SPPE pairs, review queues, and feedback.
- PDF intent: expose deterministic behavior, traces, logs, metrics, and bounded execution for this module.

## Local Setup

```bash
cd services/training-pipeline
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Docker

```bash
docker build -f services/training-pipeline/Dockerfile -t jimsai/training-pipeline:local .
```

## API

- `GET /health`
- `GET /metrics`
- `GET /trace`
- Service endpoints: /v1/training/ingest, /v1/training/review-queue

## Tests

```bash
pytest services/training-pipeline/tests
```
