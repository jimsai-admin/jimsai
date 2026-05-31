import json
from pathlib import Path

import pytest

from prototype.jimsai.kaggle_orchestrator import KaggleGPUOrchestrator
from prototype.jimsai.models import KaggleTrainingRequest, TrainingIngestRequest
from prototype.jimsai.pipeline import JimsAIPipeline


@pytest.mark.asyncio
async def test_sppe_renderer_training_run_prepares_renderer_notebook(monkeypatch, tmp_path):
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    monkeypatch.delenv("KAGGLE_USERNAME", raising=False)
    monkeypatch.delenv("KAGGLE_DATASET_OWNER", raising=False)
    pipeline = JimsAIPipeline()
    await pipeline.ingest_training(
        TrainingIngestRequest(
            user_id="test",
            content="RendererInput depends on SemanticIntentionGraph. SemanticIntentionGraph causes FluentText.",
            source_trust=0.92,
            domain_hint="sppe_renderer",
        )
    )

    orchestrator = KaggleGPUOrchestrator(workspace_root=tmp_path)
    run = orchestrator.submit_training_run(
        KaggleTrainingRequest(user_id="test", task_type="sppe_renderer_finetune"),
        training_history=pipeline.training_history,
        world_model_candidates=pipeline.world_model_candidates,
    )

    run_dir = Path(run.local_path or "")
    assert run.status == "prepared"
    assert (run_dir / "jimsai_sppe_renderer_finetune.ipynb").exists()
    assert not (run_dir / "jimsai_encoder_finetune.ipynb").exists()
    payload = json.loads((run_dir / "training_payload.json").read_text(encoding="utf-8"))
    assert payload["task_type"] == "sppe_renderer_finetune"
    assert payload["sppe_pairs"][0]["accepted"] is True
