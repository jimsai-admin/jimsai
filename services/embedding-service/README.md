# JIMS-AI Embedding Service

Render-hosted FastAPI service for query and batch embeddings.

Endpoints:

- `GET /health`
- `POST /v1/embed`
- `POST /v1/embed-batch`
- `GET /v1/artifact/current`
- `POST /v1/reload-artifact`

Protected endpoints accept:

```text
Authorization: Bearer <JIMS_RENDER_AGENT_TOKEN>
```

If `sentence-transformers` or the configured model cannot load, the service returns `503`. JIMS-AI does not use hash embeddings as a semantic fallback.
