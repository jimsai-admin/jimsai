# auth-service

## Architecture Mapping

- Layer: User and workspace control plane
- Purpose: Integrate Supabase Auth identities, workspaces, API access boundaries, and cloud-only authorization policy.
- PDF intent: expose deterministic behavior, traces, logs, metrics, and bounded execution for this module.

## Local Setup

```bash
cd services/auth-service
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Docker

```bash
docker build -f services/auth-service/Dockerfile -t jimsai/auth-service:local .
```

## API

- `GET /health`
- `GET /metrics`
- `GET /trace`
- Service endpoints: /v1/users, /v1/workspaces

## Tests

```bash
pytest services/auth-service/tests
```
