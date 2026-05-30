# semantic-parser

## Architecture Mapping

- Layer: L1 structured extraction
- Purpose: Extract entities, relations, causal chains, modality metadata, and source trust from inputs.
- PDF intent: expose deterministic behavior, traces, logs, metrics, and bounded execution for this module.

## Local Setup

```bash
cd services/semantic-parser
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Docker

```bash
docker build -f services/semantic-parser/Dockerfile -t jimsai/semantic-parser:local .
```

## API

- `GET /health`
- `GET /metrics`
- `GET /trace`
- Service endpoints: /v1/parse/text, /v1/parse/signature

## Tests

```bash
pytest services/semantic-parser/tests
```
