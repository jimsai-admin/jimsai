from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .models import ModalTrainingRequest, ModalTrainingResponse, TrainingIngestResponse, WorldModelCandidate, utc_now

# Backward-compat aliases for any existing references
KaggleTrainingRequest = ModalTrainingRequest
KaggleTrainingResponse = ModalTrainingResponse


class ModalTrainingOrchestrator:
    """Modal-hosted training orchestrator for JIMS-AI encoder and SPPE renderer fine-tuning."""

    def __init__(self, workspace_root: str | Path = ".modal_training_runs") -> None:
        import os
        default = "/tmp/.modal_training_runs" if os.getenv("AWS_LAMBDA_FUNCTION_NAME") else ".modal_training_runs"
        self.workspace_root = Path(workspace_root if workspace_root != ".modal_training_runs" else default)
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    @property
    def configured(self) -> bool:
        """True when Modal API key is set and training can be dispatched."""
        return bool(os.getenv("JIMS_MODAL_API_KEY", "").strip())

    def submit_training_run(
        self,
        request: KaggleTrainingRequest,
        training_history: list[TrainingIngestResponse],
        world_model_candidates: list[WorldModelCandidate],
    ) -> KaggleTrainingResponse:
        """Dispatch a training job to Modal instead of Kaggle.

        Routes encoder_finetune / reranker_finetune tasks to
        modal_training_service.run_encoder_finetune, and sppe_renderer_finetune
        to modal_training_service.run_sppe_renderer_finetune.
        Falls back to "prepared" status when Modal is not configured.
        """
        run_id = f"modal_{utc_now().strftime('%Y%m%d_%H%M%S')}_{request.task_type}"
        payload = self._training_payload(request, training_history, world_model_candidates)

        # Save payload locally for audit
        run_dir = self.workspace_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "training_payload.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

        # Dispatch to Modal
        modal_api_key = os.getenv("JIMS_MODAL_API_KEY", "").strip()
        if not modal_api_key:
            return KaggleTrainingResponse(
                run_id=run_id,
                status="prepared",
                task_type=request.task_type,
                local_path=str(run_dir),
                detail="JIMS_MODAL_API_KEY not set — training payload prepared but not dispatched to Modal.",
            )

        try:
            import modal as _modal  # only import if Modal is available
            if request.task_type in {"sppe_renderer_finetune", "sppe_refiner"}:
                from modal_training_service import run_sppe_renderer_finetune
                result = run_sppe_renderer_finetune.remote(payload)
            else:
                from modal_training_service import run_encoder_finetune
                result = run_encoder_finetune.remote(payload)

            return KaggleTrainingResponse(
                run_id=run_id,
                status=result.get("status", "completed"),
                task_type=request.task_type,
                local_path=result.get("artifact_path", str(run_dir)),
                detail=json.dumps({
                    "duration_s": result.get("duration_s"),
                    "sppe_pairs_used": result.get("sppe_pairs_used") or result.get("examples_used"),
                    "artifact_path": result.get("artifact_path"),
                }),
                submitted_at=utc_now(),
            )
        except Exception as exc:
            return KaggleTrainingResponse(
                run_id=run_id,
                status="failed",
                task_type=request.task_type,
                local_path=str(run_dir),
                detail=str(exc)[:800],
            )

    def _training_payload(
        self,
        request: KaggleTrainingRequest,
        training_history: list[TrainingIngestResponse],
        world_model_candidates: list[WorldModelCandidate],
    ) -> dict[str, Any]:
        workspace_id = request.workspace_id
        filtered = [
            item
            for item in training_history
            if workspace_id is None or item.signature.workspace_id in {None, workspace_id}
        ]
        return {
            "task_type": request.task_type,
            "title": request.title,
            "notes": request.notes,
            "workspace_id": workspace_id,
            "created_at": utc_now().isoformat(),
            "sppe_pairs": [item.sppe_training_pair.model_dump(mode="json") for item in filtered],
            "signatures": [item.signature.model_dump(mode="json") for item in filtered],
            "world_model_candidates": [candidate.model_dump(mode="json") for candidate in world_model_candidates],
        }

    def _slug(self, value: str) -> str:
        slug = "".join(char.lower() if char.isalnum() else "-" for char in value)
        slug = "-".join(part for part in slug.split("-") if part)
        return slug[:48] or "jimsai-training"


# ---------------------------------------------------------------------------
# Backward-compatibility alias — keeps existing tests and references working
# ---------------------------------------------------------------------------
KaggleGPUOrchestrator = ModalTrainingOrchestrator
