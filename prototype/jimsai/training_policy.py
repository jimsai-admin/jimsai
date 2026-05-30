from __future__ import annotations

import os

from .models import AutoTrainingDecision, Modality, TrainingIngestResponse, WorldModelCandidate


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


class AutoTrainingPolicy:
    """Detect when a new Kaggle fine-tuning batch is justified.

    This policy deliberately produces a decision instead of silently training on
    every ingest. v9 keeps humans in the loop for artifact activation and for
    controlling external GPU spend.
    """

    def __init__(self) -> None:
        self.enabled = _env_bool("JIMS_AUTO_TRAINING_ENABLED", False)
        self.min_new_sppe_pairs = _env_int("JIMS_AUTO_TRAIN_MIN_SPPE_PAIRS", 25)
        self.min_media_pending = _env_int("JIMS_AUTO_TRAIN_MIN_MEDIA_PENDING", 5)
        self.min_reviewed_pairs = _env_int("JIMS_AUTO_TRAIN_MIN_REVIEWED_PAIRS", 10)
        self.max_ambiguity_pending = _env_int("JIMS_AUTO_TRAIN_MAX_AMBIGUITY_PENDING", 200)
        self.min_retrieval_misses = _env_int("JIMS_AUTO_TRAIN_MIN_RETRIEVAL_MISSES", 20)

    def evaluate(
        self,
        training_history: list[TrainingIngestResponse],
        world_model_candidates: list[WorldModelCandidate],
        ambiguity_queue: list[dict[str, object]],
        retrieval_misses: int = 0,
    ) -> AutoTrainingDecision:
        media_pending = sum(
            1
            for item in training_history
            if item.signature.modality in {Modality.IMAGE, Modality.AUDIO, Modality.VIDEO}
            and bool(item.signature.metadata.get("queued_for_multimodal_training", False))
        )
        reviewed_pairs = sum(1 for item in training_history if item.sppe_training_pair.accepted)
        pending_reviews = sum(1 for candidate in world_model_candidates if candidate.review_required)
        counters: dict[str, int | float | bool] = {
            "sppe_pairs": len(training_history),
            "accepted_sppe_pairs": reviewed_pairs,
            "media_pending_encoder": media_pending,
            "world_model_review_pending": pending_reviews,
            "ambiguity_pending": len(ambiguity_queue),
            "retrieval_misses": retrieval_misses,
            "kaggle_upload_enabled": self.enabled,
        }
        if len(ambiguity_queue) > self.max_ambiguity_pending:
            return AutoTrainingDecision(
                enabled=self.enabled,
                should_schedule=False,
                task_type="sppe_refiner",
                reason="Human review backlog is too large; resolve ambiguity before training.",
                counters=counters,
            )
        if media_pending >= self.min_media_pending:
            return AutoTrainingDecision(
                enabled=self.enabled,
                should_schedule=self.enabled,
                task_type="encoder_finetune",
                reason="Enough media signatures are queued for multimodal encoder training.",
                counters=counters,
            )
        if retrieval_misses >= self.min_retrieval_misses:
            return AutoTrainingDecision(
                enabled=self.enabled,
                should_schedule=self.enabled,
                task_type="reranker_finetune",
                reason="Retrieval miss count crossed the reranker training threshold.",
                counters=counters,
            )
        if reviewed_pairs >= self.min_reviewed_pairs:
            return AutoTrainingDecision(
                enabled=self.enabled,
                should_schedule=self.enabled,
                task_type="world_model_extractor",
                reason="Enough accepted SPPE pairs are available for world-model extractor improvement.",
                counters=counters,
            )
        if len(training_history) >= self.min_new_sppe_pairs:
            return AutoTrainingDecision(
                enabled=self.enabled,
                should_schedule=self.enabled,
                task_type="encoder_finetune",
                reason="Enough new SPPE pairs are available for encoder fine-tuning.",
                counters=counters,
            )
        return AutoTrainingDecision(
            enabled=self.enabled,
            should_schedule=False,
            reason="Training thresholds not reached yet.",
            counters=counters,
        )
