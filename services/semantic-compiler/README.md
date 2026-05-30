# semantic-compiler

## Architecture Mapping

- Layer: Semantic Compiler Runtime / T1 deterministic fallback
- Purpose: Compile human input into typed Semantic IR without allowing raw language to control execution.
- PDF intent: expose deterministic behavior, traces, logs, metrics, and bounded execution for this module.

## Local Setup

```bash
cd services/semantic-compiler
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Docker

```bash
docker build -f services/semantic-compiler/Dockerfile -t jimsai/semantic-compiler:local .
```

## API

- `GET /health`
- `GET /metrics`
- `GET /trace`
- Service endpoints: /v1/compile, /v1/resolve

## Tests

```bash
pytest services/semantic-compiler/tests
```
