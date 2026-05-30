# hypothesis-resolver

## Architecture Mapping

- Layer: Multi-Hypothesis Resolver
- Purpose: Rank compound intents, preserve primary goals, overlays, and background warnings.
- PDF intent: expose deterministic behavior, traces, logs, metrics, and bounded execution for this module.

## Local Setup

```bash
cd services/hypothesis-resolver
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Docker

```bash
docker build -f services/hypothesis-resolver/Dockerfile -t jimsai/hypothesis-resolver:local .
```

## API

- `GET /health`
- `GET /metrics`
- `GET /trace`
- Service endpoints: /v1/hypotheses/resolve, /v1/hypotheses/trace

## Tests

```bash
pytest services/hypothesis-resolver/tests
```
