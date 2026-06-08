"""
shared/modal_common.py — Shared types and utilities for all Modal JIMS-AI services.

Covers requirements: 10.3, 10.4, 10.5, 28.1, 28.2, 28.3, 28.4, 30.2, 30.3, 30.5
"""

from __future__ import annotations

import logging
import os
import pathlib
import shutil
import threading
import time
from dataclasses import dataclass

import huggingface_hub

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ModelArtifact dataclass
# ---------------------------------------------------------------------------

@dataclass
class ModelArtifact:
    """Descriptor for a single model stored on the Modal Volume.

    Attributes:
        model_key:    Short identifier, e.g. "multilingual-e5-small".
        hf_repo_id:   HuggingFace repository ID, e.g. "intfloat/multilingual-e5-small".
        hf_filename:  None → full snapshot download; string → single GGUF filename.
        volume_path:  Absolute path on the mounted Modal Volume where the
                      model directory (snapshot) or file (GGUF) lives.
        model_type:   One of "sentence_transformer", "transformers_cls", "gguf".
        dimensions:   Output embedding dimensionality (768) or None for generative models.
    """

    model_key: str
    hf_repo_id: str
    hf_filename: str | None
    volume_path: str
    model_type: str
    dimensions: int | None


# ---------------------------------------------------------------------------
# ARTIFACT_REGISTRY — canonical descriptor for every model
# ---------------------------------------------------------------------------

ARTIFACT_REGISTRY: dict[str, ModelArtifact] = {
    "multilingual-e5-small": ModelArtifact(
        model_key="multilingual-e5-small",
        hf_repo_id="intfloat/multilingual-e5-small",
        hf_filename=None,
        volume_path="/vol/models/embedding/multilingual-e5-small",
        model_type="sentence_transformer",
        dimensions=768,
    ),
    "jina-v3": ModelArtifact(
        model_key="jina-v3",
        hf_repo_id="jinaai/jina-embeddings-v3-hf",  # native transformers, no trust_remote_code needed
        hf_filename=None,
        volume_path="/vol/models/embedding/jina-embeddings-v3",
        model_type="sentence_transformer",
        dimensions=768,
    ),
    "codebert": ModelArtifact(
        model_key="codebert",
        hf_repo_id="microsoft/codebert-base",
        hf_filename=None,
        volume_path="/vol/models/embedding/codebert-base",
        model_type="transformers_cls",
        dimensions=768,
    ),
    "mDeBERTa": ModelArtifact(
        model_key="mDeBERTa",
        hf_repo_id="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",
        hf_filename=None,
        volume_path="/vol/models/classification/mDeBERTa-v3-base-mnli-xnli",
        model_type="transformers_cls",
        dimensions=None,
    ),
    "qwen-1.7b": ModelArtifact(
        model_key="qwen-1.7b",
        hf_repo_id="ggml-org/Qwen3-1.7B-GGUF",
        hf_filename="Qwen3-1.7B-Q4_K_M.gguf",
        volume_path="/vol/models/generation/Qwen3-1.7B-Q4_K_M.gguf",
        model_type="gguf",
        dimensions=None,
    ),
    "qwen-4b": ModelArtifact(
        model_key="qwen-4b",
        hf_repo_id="Qwen/Qwen3-4B-GGUF",
        hf_filename="Qwen3-4B-Q4_K_M.gguf",
        volume_path="/vol/models/generation/Qwen3-4B-Q4_K_M.gguf",
        model_type="gguf",
        dimensions=None,
    ),
    "qwen-8b": ModelArtifact(
        model_key="qwen-8b",
        hf_repo_id="Qwen/Qwen3-8B-GGUF",
        hf_filename="Qwen3-8B-Q4_K_M.gguf",
        volume_path="/vol/models/generation/Qwen3-8B-Q4_K_M.gguf",
        model_type="gguf",
        dimensions=None,
    ),
}

# ---------------------------------------------------------------------------
# validate_model_integrity
# ---------------------------------------------------------------------------

_INTEGRITY_TIMEOUT_SECONDS = 10


def _run_with_timeout(fn, timeout: int):
    """Run *fn* in a thread; return its result or raise TimeoutError."""
    result_box: list = []
    exc_box: list = []

    def _target():
        try:
            result_box.append(fn())
        except Exception as exc:  # noqa: BLE001
            exc_box.append(exc)

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout)

    if t.is_alive():
        raise TimeoutError(f"Integrity check exceeded {timeout} s timeout")
    if exc_box:
        raise exc_box[0]
    return result_box[0]


def validate_model_integrity(artifact: ModelArtifact) -> bool:
    """Check whether *artifact* is present and valid on the Modal Volume.

    For GGUF files  : the file must exist and have a non-zero size.
    For snapshots   : the directory must exist, contain ``config.json``,
                      and ``config.json`` must be non-empty.

    Each check is bounded to :data:`_INTEGRITY_TIMEOUT_SECONDS` seconds.

    Returns ``True`` when the artifact is valid; ``False`` otherwise.
    Logs the outcome at INFO level.
    """

    def _check() -> tuple[bool, str]:
        path = artifact.volume_path

        if artifact.hf_filename is not None:
            # GGUF single-file check
            if not os.path.exists(path):
                return False, f"file not found: {path}"
            size = os.path.getsize(path)
            if size == 0:
                return False, f"file is empty: {path}"
            return True, "ok"
        else:
            # Snapshot directory check
            if not os.path.isdir(path):
                return False, f"directory not found: {path}"
            config_path = os.path.join(path, "config.json")
            if not os.path.exists(config_path):
                return False, f"config.json missing in: {path}"
            if os.path.getsize(config_path) == 0:
                return False, f"config.json is empty in: {path}"
            return True, "ok"

    try:
        valid, reason = _run_with_timeout(_check, _INTEGRITY_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        reason = str(exc)
        valid = False
    except Exception as exc:  # noqa: BLE001
        reason = str(exc)
        valid = False

    if valid:
        logger.info("Integrity OK: %s", artifact.model_key)
    else:
        logger.info("Integrity FAILED: %s — %s", artifact.model_key, reason)

    return valid


# ---------------------------------------------------------------------------
# ensure_model_on_volume
# ---------------------------------------------------------------------------

def ensure_model_on_volume(artifact: ModelArtifact) -> pathlib.Path:
    """Ensure *artifact* is available on the Modal Volume, downloading if needed.

    Idempotent: if :func:`validate_model_integrity` passes, returns immediately
    without any network I/O.

    Args:
        artifact: A :class:`ModelArtifact` from :data:`ARTIFACT_REGISTRY`.

    Returns:
        ``pathlib.Path`` pointing to the model directory or GGUF file.

    Raises:
        RuntimeError: If the model is absent AND cannot be downloaded, or if
                      the post-download integrity check still fails.
    """
    if validate_model_integrity(artifact):
        logger.info("Cache hit — loading from volume: %s", artifact.volume_path)
        return pathlib.Path(artifact.volume_path)

    logger.info("Model not in volume, downloading: %s", artifact.hf_repo_id)

    if artifact.hf_filename is not None:
        # Single GGUF file — download to the parent directory
        parent_dir = str(pathlib.Path(artifact.volume_path).parent)
        os.makedirs(parent_dir, exist_ok=True)
        huggingface_hub.hf_hub_download(
            repo_id=artifact.hf_repo_id,
            filename=artifact.hf_filename,
            local_dir=parent_dir,
        )
    else:
        # Full model snapshot
        volume_path = artifact.volume_path
        os.makedirs(volume_path, exist_ok=True)
        huggingface_hub.snapshot_download(
            repo_id=artifact.hf_repo_id,
            local_dir=volume_path,
        )

    # Post-download integrity check
    if not validate_model_integrity(artifact):
        raise RuntimeError(
            f"Cannot load model {artifact.model_key}: "
            f"download completed but integrity check still failed"
        )

    return pathlib.Path(artifact.volume_path)


# ---------------------------------------------------------------------------
# download_gguf_to_volume
# ---------------------------------------------------------------------------

def download_gguf_to_volume(repo_id: str, filename: str, dest_path: str) -> str:
    """Download a single GGUF file to *dest_path* on the Modal Volume.

    Idempotent: if *dest_path* already exists and has non-zero size, returns
    immediately without downloading.

    Args:
        repo_id:   HuggingFace repository ID containing *filename*.
        filename:  The filename within the repository (e.g. ``"Qwen3-4B-Q4_K_M.gguf"``).
        dest_path: Absolute destination path on the Modal Volume.

    Returns:
        *dest_path* as a string.

    Raises:
        RuntimeError: If the downloaded file has zero size.
    """
    # Idempotency guard
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
        logger.info("GGUF already present, skipping download: %s", dest_path)
        return dest_path

    dest_dir = os.path.dirname(dest_path)
    os.makedirs(dest_dir, exist_ok=True)

    logger.info("Downloading GGUF %s/%s → %s", repo_id, filename, dest_path)
    downloaded_path = huggingface_hub.hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        local_dir=dest_dir,
    )

    # Move to the exact dest_path if the hub placed it under a subdirectory
    downloaded_path = str(downloaded_path)
    if os.path.abspath(downloaded_path) != os.path.abspath(dest_path):
        shutil.move(downloaded_path, dest_path)

    # Validate non-zero size
    if not os.path.exists(dest_path) or os.path.getsize(dest_path) == 0:
        raise RuntimeError(
            f"GGUF download produced a zero-size or missing file at {dest_path}"
        )

    logger.info("GGUF download complete: %s (%.1f MB)", dest_path, os.path.getsize(dest_path) / 1e6)
    return dest_path


# ---------------------------------------------------------------------------
# build_health_payload
# ---------------------------------------------------------------------------

def build_health_payload(
    service_name: str,
    models_loaded: dict | bool,
    gpu_available: bool,
    volume_mounted: bool,
    container_start_time: float,
) -> dict:
    """Build a standardised health-check response payload.

    Args:
        service_name:         Logical service name, e.g. ``"embedding"``.
        models_loaded:        Either a ``bool`` (single model) or a ``dict``
                              mapping model key → bool (multiple models).
        gpu_available:        Whether a CUDA-capable GPU is accessible.
        volume_mounted:       Whether the Modal Volume is reachable.
        container_start_time: ``time.time()`` value recorded at container startup.

    Returns:
        A ``dict`` with keys ``status``, ``service``, ``models_loaded``,
        ``container_uptime``, ``gpu_available``, ``volume_mounted``.
        ``status`` is ``"healthy"`` when *volume_mounted* is ``True`` AND all
        models are loaded; ``"unhealthy"`` otherwise.
    """
    # Determine healthy flag from models_loaded
    if isinstance(models_loaded, bool):
        all_loaded = models_loaded
    else:
        all_loaded = bool(models_loaded) and all(models_loaded.values())

    status = "healthy" if (volume_mounted and all_loaded) else "unhealthy"

    return {
        "status": status,
        "service": service_name,
        "models_loaded": models_loaded,
        "container_uptime": int(time.time() - container_start_time),
        "gpu_available": gpu_available,
        "volume_mounted": volume_mounted,
    }
