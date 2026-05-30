# Multimodal Encoder Service

This service is the external encoder process used by the public JIMS-AI API. It runs text, code, image, audio, and video encoders outside the API server so training traffic can scale independently.

API contract:

```text
GET /health
POST /v1/encode
Authorization: Bearer <JIMS_MULTIMODAL_ENCODER_API_KEY>
```

Request:

```json
{
  "content": "text, URL, base64, or data URL",
  "modality": "text",
  "dimensions": 768
}
```

Response:

```json
{
  "embedding": [0.1, 0.2],
  "modality": "text",
  "dimensions": 768,
  "model": "nomic-ai/nomic-embed-text-v1.5"
}
```

Build and push an image for Vast.ai:

```bash
docker build -f services/multimodal-encoder/Dockerfile -t ghcr.io/YOUR_ORG/jimsai-multimodal-encoder:latest .
docker push ghcr.io/YOUR_ORG/jimsai-multimodal-encoder:latest
```

The main API should point to the deployed encoder:

```text
JIMS_ENABLE_MULTIMODAL_ENCODERS=true
JIMS_MULTIMODAL_ENCODER_MODE=external
JIMS_MULTIMODAL_ENCODER_URL=https://your-encoder-host
JIMS_MULTIMODAL_ENCODER_API_KEY=...
```
