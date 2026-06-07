# JIMS-AI Modal Deployment

This directory contains all Modal-related files for the JIMS-AI migration from Hugging Face Spaces + AWS Lambda to Modal.

---

## Prerequisites

1. **Python 3.11+** (3.13 works)
2. A **Modal account** — sign up at [modal.com](https://modal.com)
3. Credentials in `.env` at the repo root:

```dotenv
MODAL_TOKEN_ID=<your modal token id>
MODAL_TOKEN_SECRET=<your modal token secret>
HF_TOKEN=<your huggingface token>
```

> `HF_TOKEN` is required for gated models (`jinaai/jina-embeddings-v3`).

---

## Quick Start — Populate the Model Volume

```bash
# 1. Install dependencies
pip install -r modal/requirements.txt

# 2. Populate all 7 model artifacts into the jimsai-models volume
python modal/scripts/populate_modal_volume.py --all

# 3. Populate a single model (idempotent — skips if already present)
python modal/scripts/populate_modal_volume.py --model embedding/multilingual-e5-small
python modal/scripts/populate_modal_volume.py --model generation/Qwen3-4B-Q4_K_M.gguf
```

### Available model keys

| Key | Source | Method |
|-----|--------|--------|
| `embedding/multilingual-e5-small` | `intfloat/multilingual-e5-small` | snapshot |
| `embedding/jina-embeddings-v3` | `jinaai/jina-embeddings-v3` | snapshot |
| `embedding/codebert-base` | `microsoft/codebert-base` | snapshot |
| `classification/mDeBERTa-v3-base-mnli-xnli` | `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` | snapshot |
| `generation/Qwen3-1.7B-Q4_K_M.gguf` | `ggml-org/Qwen3-1.7B-GGUF` | single file |
| `generation/Qwen3-4B-Q4_K_M.gguf` | `Qwen/Qwen3-4B-GGUF` | single file |
| `generation/Qwen3-8B-Q4_K_M.gguf` | `Qwen/Qwen3-8B-GGUF` | single file |

---

## Volume Layout

```
jimsai-models (Modal Volume, mounted at /vol/models)
├── embedding/
│   ├── multilingual-e5-small/
│   ├── jina-embeddings-v3/
│   └── codebert-base/
├── classification/
│   └── mDeBERTa-v3-base-mnli-xnli/
└── generation/
    ├── Qwen3-1.7B-Q4_K_M.gguf
    ├── Qwen3-4B-Q4_K_M.gguf
    └── Qwen3-8B-Q4_K_M.gguf
```

---

## Service Deployment

Once the volume is populated, deploy each service with the Modal CLI.

> **Note**: Modal secrets (`modal-jimsai-secrets`) must be created before deploying services.
> Run `modal secret create modal-jimsai-secrets` and add the required keys listed in `requirements.md`.

### Embedding Service

```bash
modal deploy modal_embedding_service.py
```

URL: `https://<org>--jimsai-embedding-service.modal.run`

### Classification Service

```bash
modal deploy modal_classification_service.py
```

URL: `https://<org>--jimsai-classification-service.modal.run`

### Intent Service (Qwen3-1.7B, CPU)

```bash
modal deploy modal_intent_service.py
```

URL: `https://<org>--jimsai-intent-service.modal.run`

### Renderer Service (Qwen3-4B, GPU)

```bash
modal deploy modal_renderer_service.py
```

URL: `https://<org>--jimsai-renderer-service.modal.run`

### Reasoning Service (Qwen3-8B, GPU, scale-to-zero)

```bash
modal deploy modal_reasoning_service.py
```

URL: `https://<org>--jimsai-reasoning-service.modal.run`

### FastAPI Backend

```bash
modal deploy modal_backend.py
```

URL: `https://<org>--jimsai-backend.modal.run`

---

## Directory Structure

```
modal/
├── README.md                       # this file
├── requirements.txt                # dependencies for local scripts
└── scripts/
    └── populate_modal_volume.py    # volume population script
```

Service implementation files (`modal_embedding_service.py`, etc.) live in the repo root once implemented.

---

## Troubleshooting

**`MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` not found**
Ensure `.env` is at the repo root (`Jims-AI/.env`) and contains both values.

**`HF_TOKEN` not set warning**
Set `HF_TOKEN` in `.env`. Required for `jinaai/jina-embeddings-v3` (gated repo).

**Volume path already exists — skipped**
The script is idempotent. Re-running `--all` skips models that are already on the volume. To force a re-download, delete the path from the volume via the Modal dashboard or `modal volume rm`.

**`modal` package not installed**
Run `pip install -r modal/requirements.txt` from the repo root.
