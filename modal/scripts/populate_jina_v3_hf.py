"""
populate_jina_v3_hf.py
Downloads jinaai/jina-embeddings-v3-hf directly into the Modal volume
from inside a Modal container — no local 4GB download needed.

Usage:
    modal run modal/scripts/populate_jina_v3_hf.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import modal

volume = modal.Volume.from_name("jimsai-models", create_if_missing=True)
secret = modal.Secret.from_name("modal-jimsai-secrets")

app = modal.App("jimsai-populate-jina-v3-hf")

image = modal.Image.debian_slim(python_version="3.11").pip_install([
    "huggingface-hub>=0.23",
])

@app.function(
    image=image,
    volumes={"/vol/models": volume},
    secrets=[secret],
    timeout=3600,  # 1 hour — plenty for a 4GB download inside Modal's network
    memory=4096,
)
def populate_jina_v3():
    """Download jina-embeddings-v3-hf into the volume from inside Modal."""
    import shutil
    from huggingface_hub import snapshot_download

    dest = "/vol/models/embedding/jina-embeddings-v3"
    hf_token = os.environ.get("HF_TOKEN")

    # Remove any partial download
    if os.path.isdir(dest):
        print(f"Removing existing partial directory: {dest}")
        shutil.rmtree(dest)

    os.makedirs(dest, exist_ok=True)

    print(f"Downloading jinaai/jina-embeddings-v3-hf → {dest}")
    snapshot_download(
        repo_id="jinaai/jina-embeddings-v3-hf",
        local_dir=dest,
        token=hf_token or None,
        ignore_patterns=["*.msgpack", "flax_model*", "rust_model*", "tf_model*"],
    )

    # Verify
    config = os.path.join(dest, "config.json")
    if not os.path.exists(config) or os.path.getsize(config) == 0:
        raise RuntimeError("Download failed — config.json missing or empty")

    # Count files and total size
    files = list(Path(dest).rglob("*"))
    file_count = sum(1 for f in files if f.is_file())
    total_mb = sum(f.stat().st_size for f in files if f.is_file()) / 1e6

    print(f"Download complete: {file_count} files, {total_mb:.0f} MB")

    # Commit to volume
    volume.commit()
    print("Volume committed successfully.")
    return {"files": file_count, "size_mb": round(total_mb)}


@app.local_entrypoint()
def main():
    result = populate_jina_v3.remote()
    print(f"\nDone: {result}")
