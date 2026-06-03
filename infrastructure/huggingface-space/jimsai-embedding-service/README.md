---
title: jimsai-embedding-service
emoji: 🤖
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
---

# JIMS-AI Hugging Face Service

This Space hosts the production JIMS-AI sentence-transformer embedding service, multilingual capability classifier, Qwen3-1.7B routing endpoint, and Qwen3-4B render endpoint.

Protected endpoints require:

```text
Authorization: Bearer <JIMS_RENDER_AGENT_TOKEN>
```

Endpoints:

```text
GET  /health
GET  /ready
GET  /v1/warm
POST /v1/warm
POST /v1/embed
POST /v1/embed-batch
POST /v1/encode
POST /v1/classify/capability
POST /v1/chat/completions
POST /v1/chat/render
GET  /v1/artifact/current
POST /v1/reload-artifact
```

Recommended Space secrets or variables:

```text
JIMS_RENDER_AGENT_TOKEN
JIMS_EMBEDDING_MODEL=intfloat/multilingual-e5-small
JIMS_EMBEDDING_DIMENSIONS=768
JIMS_EMBEDDING_HASH_FALLBACK_ENABLED=true
JIMS_QWEN_ENABLED=true
JIMS_QWEN_MODEL_REPO=ggml-org/Qwen3-1.7B-GGUF
JIMS_QWEN_MODEL_FILE=Qwen3-1.7B-Q4_K_M.gguf
JIMS_QWEN_MODEL=qwen3-1.7b-instruct
JIMS_QWEN_CONTEXT=4096
JIMS_QWEN_THREADS=2
JIMS_QWEN_MAX_TOKENS=256
JIMS_QWEN_BATCH=64
JIMS_RENDER_MODEL_REPO=Qwen/Qwen3-4B-GGUF
JIMS_RENDER_MODEL_FILE=Qwen3-4B-Q4_K_M.gguf
JIMS_RENDER_MODEL_NAME=qwen3-4b-instruct
JIMS_RENDER_CONTEXT=8192
JIMS_RENDER_THREADS=2
JIMS_RENDER_MAX_TOKENS=1200
JIMS_RENDER_BATCH=128
JIMS_ROUTER_MODEL=MoritzLaurer/mDeBERTa-v3-base-mnli-xnli
```

Use `/v1/warm?load_qwen_model=true` to preload Qwen3-1.7B for ambiguous routing.
Use `/v1/warm?load_render_model=true` to preload Qwen3-4B for natural rendering.
Keep the normal `/health` ping as the cheap wake-up check.

Use `/v1/warm?load_router_model=true` to pre-load the multilingual capability
classifier used for chaotic and non-English prompts.

Lambda should set:

```text
JIMS_LLM_PROVIDER=local
JIMS_ENABLE_LOCAL_QWEN=true
JIMS_LOCAL_INFERENCE_URL=https://jimstechai-jimsai-embedding-service.hf.space
JIMS_LOCAL_INFERENCE_API_KEY=<JIMS_RENDER_AGENT_TOKEN>
JIMS_LOCAL_INFERENCE_MODEL=qwen3-1.7b-instruct
JIMS_LOCAL_INFERENCE_CHAT_PATH=/v1/chat/completions
JIMS_LOCAL_RENDER_MODEL=qwen3-4b-instruct
JIMS_LOCAL_RENDER_CHAT_PATH=/v1/chat/render
JIMS_ALLOW_EXTERNAL_GROQ=false
```

If `JIMS_LOCAL_INFERENCE_URL` is not set, Lambda uses `JIMS_EMBEDDING_SERVICE_URL` for Qwen when local/Hugging Face inference is enabled.
