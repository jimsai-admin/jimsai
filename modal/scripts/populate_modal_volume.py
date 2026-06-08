"""
populate_modal_volume.py
Populates the 'jimsai-models' Modal Volume with all model artifacts.

Usage:
    python scripts/populate_modal_volume.py --all
    python scripts/populate_modal_volume.py --model embedding/multilingual-e5-small
    python scripts/populate_modal_volume.py --model generation/Qwen3-1.7B-Q4_K_M.gguf

Prerequisites:
    pip install -r requirements.txt
    Set MODAL_TOKEN_ID, MODAL_TOKEN_SECRET, HF_TOKEN in .env (project root)
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Load .env BEFORE importing modal so that MODAL_TOKEN_ID / MODAL_TOKEN_SECRET
# are visible to the Modal client when it initialises.
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
except ImportError:
    print("ERROR: python-dotenv is not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

# Resolve .env relative to the repo root (two levels up from this script)
_SCRIPT_DIR = Path(__file__).resolve().parent          # modal/scripts/
_REPO_ROOT = _SCRIPT_DIR.parent.parent                 # Jims-AI/
_ENV_PATH = _REPO_ROOT / ".env"

if _ENV_PATH.exists():
    load_dotenv(dotenv_path=_ENV_PATH)
    print(f"[env] Loaded .env from {_ENV_PATH}")
else:
    print(f"[env] WARNING: .env not found at {_ENV_PATH} — relying on shell environment")

# Validate required credentials before touching Modal
_REQUIRED_ENV = ["MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"]
_missing = [k for k in _REQUIRED_ENV if not os.environ.get(k)]
if _missing:
    print(f"ERROR: Missing required environment variables: {', '.join(_missing)}")
    print(f"       Add them to {_ENV_PATH} or export them in your shell.")
    sys.exit(1)

HF_TOKEN: Optional[str] = os.environ.get("HF_TOKEN")
if not HF_TOKEN:
    print("[env] WARNING: HF_TOKEN not set — gated models (e.g. jina-v3) may fail to download")

# ---------------------------------------------------------------------------
# Import modal AFTER credentials are in the environment
# ---------------------------------------------------------------------------
try:
    import modal
except ImportError:
    print("ERROR: modal is not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

try:
    from huggingface_hub import snapshot_download, hf_hub_download
except ImportError:
    print("ERROR: huggingface-hub is not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Volume definition
# ---------------------------------------------------------------------------
VOLUME_NAME = "jimsai-models"
VOLUME_MOUNT = "/vol/models"

volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

# ---------------------------------------------------------------------------
# Model artifact registry
# ---------------------------------------------------------------------------
@dataclass
class ModelArtifact:
    key: str                     # CLI key, e.g. "embedding/multilingual-e5-small"
    volume_path: str             # path inside the volume, e.g. "embedding/multilingual-e5-small"
    hf_repo_id: str
    hf_filename: Optional[str]  # None → snapshot_download; str → hf_hub_download
    description: str


MODEL_ARTIFACTS: list[ModelArtifact] = [
    ModelArtifact(
        key="embedding/multilingual-e5-small",
        volume_path="embedding/multilingual-e5-small",
        hf_repo_id="intfloat/multilingual-e5-small",
        hf_filename=None,
        description="Multilingual E5 Small (snapshot)",
    ),
    ModelArtifact(
        key="embedding/jina-embeddings-v3",
        volume_path="embedding/jina-embeddings-v3",
        hf_repo_id="jinaai/jina-embeddings-v3-hf",
        hf_filename=None,
        description="Jina Embeddings v3 HF-native (snapshot, transformers 5.x compatible)",
    ),
    ModelArtifact(
        key="embedding/codebert-base",
        volume_path="embedding/codebert-base",
        hf_repo_id="microsoft/codebert-base",
        hf_filename=None,
        description="CodeBERT Base (snapshot)",
    ),
    ModelArtifact(
        key="classification/mDeBERTa-v3-base-mnli-xnli",
        volume_path="classification/mDeBERTa-v3-base-mnli-xnli",
        hf_repo_id="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",
        hf_filename=None,
        description="mDeBERTa-v3 MNLI/XNLI classifier (snapshot)",
    ),
    ModelArtifact(
        key="generation/Qwen3-1.7B-Q4_K_M.gguf",
        volume_path="generation/Qwen3-1.7B-Q4_K_M.gguf",
        hf_repo_id="ggml-org/Qwen3-1.7B-GGUF",
        hf_filename="Qwen3-1.7B-Q4_K_M.gguf",
        description="Qwen3-1.7B GGUF Q4_K_M (single file)",
    ),
    ModelArtifact(
        key="generation/Qwen3-4B-Q4_K_M.gguf",
        volume_path="generation/Qwen3-4B-Q4_K_M.gguf",
        hf_repo_id="Qwen/Qwen3-4B-GGUF",
        hf_filename="Qwen3-4B-Q4_K_M.gguf",
        description="Qwen3-4B GGUF Q4_K_M (single file)",
    ),
    ModelArtifact(
        key="generation/Qwen3-8B-Q4_K_M.gguf",
        volume_path="generation/Qwen3-8B-Q4_K_M.gguf",
        hf_repo_id="Qwen/Qwen3-8B-GGUF",
        hf_filename="Qwen3-8B-Q4_K_M.gguf",
        description="Qwen3-8B GGUF Q4_K_M (single file)",
    ),
]

MODEL_MAP: dict[str, ModelArtifact] = {a.key: a for a in MODEL_ARTIFACTS}

# ---------------------------------------------------------------------------
# Volume helpers
# ---------------------------------------------------------------------------

def _volume_path_exists(vol: modal.Volume, remote_path: str) -> bool:
    """Return True if remote_path already exists on the volume."""
    try:
        entries = list(vol.listdir(remote_path, recursive=False))
        return len(entries) > 0
    except Exception:
        # listdir raises if the path doesn't exist
        return False


def _format_size(size_bytes: int) -> str:
    """Human-readable file/directory size."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes //= 1024
    return f"{size_bytes:.1f} TB"


def _local_dir_size(path: Path) -> int:
    """Recursively sum sizes of all files under path."""
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())

# ---------------------------------------------------------------------------
# Core populate logic
# ---------------------------------------------------------------------------

def populate_artifact(artifact: ModelArtifact) -> dict:
    """
    Download a single artifact to the Modal Volume.

    Returns a status dict:
        {key, status: "skipped"|"ok"|"error", size_bytes, message}
    """
    print(f"\n{'='*60}")
    print(f"  Model : {artifact.key}")
    print(f"  Repo  : {artifact.hf_repo_id}")
    print(f"  Type  : {'GGUF single-file' if artifact.hf_filename else 'snapshot'}")
    print(f"{'='*60}")

    result = {
        "key": artifact.key,
        "status": "error",
        "size_bytes": 0,
        "message": "",
    }

    # ------------------------------------------------------------------
    # Idempotency check: skip if already on volume
    # ------------------------------------------------------------------
    if _volume_path_exists(volume, artifact.volume_path):
        print(f"  [SKIP] Already present on volume at {artifact.volume_path}")
        result["status"] = "skipped"
        result["message"] = "Already present — no download needed"
        return result

    # ------------------------------------------------------------------
    # Download to a local temp directory, then push to volume
    # ------------------------------------------------------------------
    t0 = time.monotonic()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        try:
            if artifact.hf_filename is None:
                # Full model snapshot (embedding / classification models)
                print(f"  [DL]   snapshot_download → {artifact.hf_repo_id}")
                local_model_dir = tmp_path / "model"
                snapshot_download(
                    repo_id=artifact.hf_repo_id,
                    local_dir=str(local_model_dir),
                    token=HF_TOKEN or None,
                    ignore_patterns=["*.msgpack", "flax_model*", "rust_model*", "tf_model*"],
                )
                local_src = local_model_dir
            else:
                # Single GGUF file
                print(f"  [DL]   hf_hub_download → {artifact.hf_repo_id}/{artifact.hf_filename}")
                downloaded_path = hf_hub_download(
                    repo_id=artifact.hf_repo_id,
                    filename=artifact.hf_filename,
                    local_dir=str(tmp_path),
                    token=HF_TOKEN or None,
                )
                local_src = Path(downloaded_path)

            # ----------------------------------------------------------
            # Validate non-zero size
            # ----------------------------------------------------------
            size_bytes = _local_dir_size(local_src)
            if size_bytes == 0:
                raise ValueError(f"Downloaded artifact has zero size: {local_src}")

            elapsed_dl = time.monotonic() - t0
            print(f"  [OK]   Downloaded {_format_size(size_bytes)} in {elapsed_dl:.1f}s")

            # ----------------------------------------------------------
            # Push to Modal Volume
            # ----------------------------------------------------------
            t1 = time.monotonic()
            remote_target = artifact.volume_path

            if local_src.is_dir():
                print(f"  [VOL]  Uploading directory → volume:{remote_target}/")
                volume.put_directory(
                    local_path=str(local_src),
                    remote_path=remote_target,
                )
            else:
                print(f"  [VOL]  Uploading file → volume:{remote_target}")
                volume.put_file(
                    local_path=str(local_src),
                    remote_path=remote_target,
                )

            volume.commit()

            elapsed_vol = time.monotonic() - t1
            print(f"  [OK]   Volume write complete in {elapsed_vol:.1f}s")
            print(f"  [SIZE] {_format_size(size_bytes)}")

            result["status"] = "ok"
            result["size_bytes"] = size_bytes
            result["message"] = f"Downloaded + uploaded in {elapsed_dl + elapsed_vol:.1f}s"

        except Exception as exc:
            result["status"] = "error"
            result["message"] = str(exc)
            print(f"  [ERR]  {exc}")

    return result

# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------

def _print_summary(results: list[dict]) -> None:
    col_key  = max(len(r["key"]) for r in results) + 2
    col_stat = 8
    col_size = 12
    col_msg  = 40

    header = (
        f"{'Model Key':<{col_key}}"
        f"{'Status':<{col_stat}}"
        f"{'Size':<{col_size}}"
        f"{'Notes'}"
    )
    sep = "-" * (col_key + col_stat + col_size + col_msg)

    print(f"\n{'='*len(sep)}")
    print("  SUMMARY")
    print(f"{'='*len(sep)}")
    print(header)
    print(sep)

    for r in results:
        size_str = _format_size(r["size_bytes"]) if r["size_bytes"] else "—"
        status_icon = {"ok": "✓ ok", "skipped": "– skip", "error": "✗ err"}.get(r["status"], r["status"])
        print(
            f"{r['key']:<{col_key}}"
            f"{status_icon:<{col_stat}}"
            f"{size_str:<{col_size}}"
            f"{r['message'][:col_msg]}"
        )

    print(sep)
    ok      = sum(1 for r in results if r["status"] == "ok")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    errors  = sum(1 for r in results if r["status"] == "error")
    print(f"  {ok} uploaded  |  {skipped} skipped (already present)  |  {errors} errors")
    print(f"{'='*len(sep)}\n")

# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Populate the jimsai-models Modal Volume with model artifacts."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--all",
        action="store_true",
        help="Populate all 7 model artifacts.",
    )
    group.add_argument(
        "--model",
        metavar="KEY",
        help=(
            "Populate a single model by key, e.g. "
            "'embedding/multilingual-e5-small' or "
            "'generation/Qwen3-4B-Q4_K_M.gguf'."
        ),
    )
    args = parser.parse_args()

    if args.all:
        artifacts_to_run = MODEL_ARTIFACTS
    else:
        if args.model not in MODEL_MAP:
            print(f"ERROR: Unknown model key '{args.model}'")
            print(f"       Valid keys:\n" + "\n".join(f"         {k}" for k in MODEL_MAP))
            sys.exit(1)
        artifacts_to_run = [MODEL_MAP[args.model]]

    print(f"\nTarget volume : {VOLUME_NAME}")
    print(f"Mount path    : {VOLUME_MOUNT}")
    print(f"Models queued : {len(artifacts_to_run)}\n")

    results = [populate_artifact(a) for a in artifacts_to_run]
    _print_summary(results)

    # Exit with non-zero if any artifact failed
    if any(r["status"] == "error" for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
