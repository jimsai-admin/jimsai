# telemetry

## Architecture Mapping

- Layer: Logs, metrics, execution traces
- Purpose: Collect deterministic trace events, Prometheus metrics, and audit logs from every service.
- PDF intent: expose deterministic behavior, traces, logs, metrics, and bounded execution for this module.

## Local Setup

```bash
cd services/telemetry
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Docker

```bash
docker build -f services/telemetry/Dockerfile -t jimsai/telemetry:local .
```

## API

- `GET /health`
- `GET /metrics`
- `GET /trace`
- Service endpoints: /v1/traces, /v1/metrics/snapshot

## Tests

```bash
pytest services/telemetry/tests
```
