"""
modal_training_service.py — Modal-hosted training pipeline for JIMS-AI.

Replaces the Kaggle-hosted training orchestration. Runs encoder fine-tuning
and SPPE renderer fine-tuning on Modal GPU containers, reading training data
from Supabase and writing artifacts to the jimsai-models volume.

Two GPU functions:
  - run_encoder_finetune(payload)        — fine-tunes multilingual-e5-small
  - run_sppe_renderer_finetune(payload)  — fine-tunes TinyLlama renderer

Both are scale-to-zero (min_containers=0) and only activate when a training
job is explicitly dispatched via the training-pipeline service.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import modal

logger = logging.getLogger(__name__)

app = modal.App("jimsai-training")
secret = modal.Secret.from_name("modal-jimsai-secrets")
volume = modal.Volume.from_name("jimsai-models", create_if_missing=True)

# ---------------------------------------------------------------------------
# Training image — GPU-capable with ML stack
# ---------------------------------------------------------------------------
training_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install([
        "modal>=1.0",
        "torch>=2.3",
        "transformers>=4.41",
        "sentence-transformers>=2.7",
        "datasets>=2.19",
        "huggingface-hub>=0.23",
        "pydantic>=2.7",
        "supabase>=2.0",
        "httpx>=0.27",
        "numpy>=1.26",
    ])
)


# ---------------------------------------------------------------------------
# Helper: load training payload from Supabase
# ---------------------------------------------------------------------------
def _fetch_training_payload(run_id: str) -> dict:
    """Fetch the training payload for a given run_id from Supabase."""
    import httpx
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY are required")

    resp = httpx.get(
        f"{url}/rest/v1/training_batches",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
        },
        params={"id": f"eq.{run_id}", "select": "manifest"},
        timeout=30,
    )
    resp.raise_for_status()
    rows = resp.json()
    if not rows:
        raise RuntimeError(f"No training batch found for run_id={run_id}")
    return rows[0].get("manifest", {})


# ---------------------------------------------------------------------------
# Encoder fine-tune (multilingual-e5-small on SPPE pairs)
# ---------------------------------------------------------------------------
@app.function(
    image=training_image,
    volumes={"/vol/models": volume},
    secrets=[secret],
    gpu=modal.gpu.Any(ordered=["A10G", "L4"]),
    min_containers=0,
    max_containers=1,
    memory=16384,
    timeout=3600,  # 1 hour max
)
def run_encoder_finetune(
    payload: dict,
    base_model: str = "intfloat/multilingual-e5-small",
    epochs: int = 1,
) -> dict:
    """Fine-tune the multilingual-e5-small encoder on SPPE pairs.

    Args:
        payload: Training data dict with keys: sppe_pairs, world_model_candidates
        base_model: HuggingFace model ID for the encoder base
        epochs: Number of training epochs (default 1)

    Returns:
        Dict with artifact_path, sppe_pairs_used, duration_s, status
    """
    import torch
    from sentence_transformers import SentenceTransformer, InputExample, losses
    from torch.utils.data import DataLoader

    t0 = time.time()
    pairs = payload.get("sppe_pairs", [])
    task_type = payload.get("task_type", "encoder_finetune")
    logger.info("Encoder finetune: %d SPPE pairs, base=%s", len(pairs), base_model)

    out_dir = Path(f"/vol/models/training/encoder_{int(t0)}")
    out_dir.mkdir(parents=True, exist_ok=True)

    if not pairs:
        manifest = {
            "status": "skipped",
            "reason": "no_sppe_pairs",
            "task_type": task_type,
            "base_model": base_model,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        json.dump(manifest, open(out_dir / "manifest.json", "w"), indent=2)
        return manifest

    # Load base model from volume cache if available, else download
    cached_path = f"/vol/models/embedding/multilingual-e5-small"
    model_path = cached_path if Path(cached_path).exists() else base_model
    model = SentenceTransformer(model_path, trust_remote_code=True)

    examples = [
        InputExample(
            texts=[
                p["original_text"],
                json.dumps(p.get("semantic_intention_graph", {})),
            ]
        )
        for p in pairs
        if p.get("original_text")
    ]

    loader = DataLoader(examples, shuffle=True, batch_size=8)
    loss_fn = losses.MultipleNegativesRankingLoss(model)
    model.fit(
        train_objectives=[(loader, loss_fn)],
        epochs=epochs,
        warmup_steps=max(10, len(examples) // 10),
        show_progress_bar=False,
    )
    model.save(str(out_dir / "sentence_transformer"))

    # Build vocab from pairs
    vocab: dict[str, int] = {}
    for p in pairs:
        for tok in p.get("original_text", "").lower().replace(".", " ").replace(",", " ").split():
            if len(tok) >= 4:
                vocab[tok] = vocab.get(tok, 0) + 1
    json.dump(
        dict(sorted(vocab.items(), key=lambda x: (-x[1], x[0]))[:5000]),
        open(out_dir / "token_weights.json", "w"),
        indent=2,
    )

    duration = round(time.time() - t0, 1)
    manifest = {
        "status": "completed",
        "task_type": task_type,
        "base_model": base_model,
        "sppe_pairs_used": len(examples),
        "epochs": epochs,
        "artifact_path": str(out_dir),
        "duration_s": duration,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    json.dump(manifest, open(out_dir / "manifest.json", "w"), indent=2)
    logger.info("Encoder finetune complete: %s in %.1fs", out_dir, duration)
    volume.commit()
    return manifest


# ---------------------------------------------------------------------------
# SPPE renderer fine-tune (TinyLlama on accepted SPPE render pairs)
# ---------------------------------------------------------------------------
@app.function(
    image=training_image,
    volumes={"/vol/models": volume},
    secrets=[secret],
    gpu=modal.gpu.Any(ordered=["A10G", "L4"]),
    min_containers=0,
    max_containers=1,
    memory=24576,
    timeout=3600,
)
def run_sppe_renderer_finetune(
    payload: dict,
    base_model: str = "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    epochs: int = 1,
) -> dict:
    """Fine-tune the SPPE renderer model on accepted render pairs.

    Args:
        payload: Training data dict with keys: sppe_pairs
        base_model: HuggingFace model ID for the renderer base
        epochs: Number of training epochs (default 1)

    Returns:
        Dict with artifact_path, examples_used, duration_s, status
    """
    from transformers import (
        AutoModelForCausalLM, AutoTokenizer,
        TrainingArguments, Trainer, DataCollatorForLanguageModeling,
    )
    from datasets import Dataset

    t0 = time.time()
    pairs = payload.get("sppe_pairs", [])
    task_type = payload.get("task_type", "sppe_renderer_finetune")
    logger.info("SPPE renderer finetune: %d pairs, base=%s", len(pairs), base_model)

    out_dir = Path(f"/vol/models/training/sppe_renderer_{int(t0)}")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Emit manifest even with no data
    if not pairs:
        manifest = {
            "status": "skipped",
            "reason": "no_sppe_pairs",
            "task_type": task_type,
            "base_model": base_model,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        json.dump(manifest, open(out_dir / "manifest.json", "w"), indent=2)
        return manifest

    tokenizer = AutoTokenizer.from_pretrained(base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(base_model)

    texts = [
        f"Input: {p.get('original_text', '')}\nOutput: {json.dumps(p.get('semantic_intention_graph', {}))}"
        for p in pairs
        if p.get("original_text")
    ]
    ds = Dataset.from_dict({"text": texts})
    tokenized = ds.map(
        lambda x: tokenizer(x["text"], truncation=True, max_length=512),
        batched=True,
        remove_columns=["text"],
    )

    args = TrainingArguments(
        output_dir=str(out_dir / "checkpoints"),
        num_train_epochs=epochs,
        per_device_train_batch_size=4,
        save_steps=500,
        logging_steps=50,
        no_cuda=False,
        report_to="none",
    )
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=tokenized,
        data_collator=DataCollatorForLanguageModeling(tokenizer, mlm=False),
    )
    trainer.train()
    trainer.save_model(str(out_dir / "renderer_model"))
    tokenizer.save_pretrained(str(out_dir / "renderer_model"))

    duration = round(time.time() - t0, 1)
    manifest = {
        "status": "completed",
        "task_type": task_type,
        "base_model": base_model,
        "examples_used": len(texts),
        "epochs": epochs,
        "artifact_path": str(out_dir),
        "duration_s": duration,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    json.dump(manifest, open(out_dir / "manifest.json", "w"), indent=2)
    logger.info("SPPE renderer finetune complete: %s in %.1fs", out_dir, duration)
    volume.commit()
    return manifest
