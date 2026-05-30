from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "datasets" / "frontier_training_seed.jsonl"


@dataclass(frozen=True)
class FrontierTrainingRecord:
    domain_hint: str
    source_trust: float
    content: str
    expected_focus: list[str]


def training_records() -> list[FrontierTrainingRecord]:
    return [
        FrontierTrainingRecord(
            domain_hint="frontier_memory_chat",
            source_trust=0.94,
            content=(
                "MemoryChat depends on scoped user signatures. "
                "Scoped user signatures cause personalized answers with source traces. "
                "Low source confidence causes explicit gaps and human review. "
                "A fluent answer is a grounded CSSE rendering with visible confidence and no unsupported claims."
            ),
            expected_focus=["fluency", "memory_retention", "gap_reporting"],
        ),
        FrontierTrainingRecord(
            domain_hint="frontier_code_generation",
            source_trust=0.93,
            content=(
                "CodeGeneration depends on project memory, package documentation, sandbox execution, and tests. "
                "Project memory causes context-aware patches. "
                "Sandbox execution causes verified result signatures. "
                "Failed tests cause correction loops instead of confident code claims."
            ),
            expected_focus=["software_engineering", "test_verified_code", "project_context"],
        ),
        FrontierTrainingRecord(
            domain_hint="frontier_reasoning_science",
            source_trust=0.92,
            content=(
                "ScientificReasoning depends on source retrieval, calculation traces, and constraint checks. "
                "Calculation traces cause confidence scores. "
                "Conflicting evidence causes gap reporting and review. "
                "High stakes domains require conservative answers and provenance."
            ),
            expected_focus=["science", "math", "high_stakes_grounding"],
        ),
        FrontierTrainingRecord(
            domain_hint="frontier_business_education",
            source_trust=0.91,
            content=(
                "BusinessPlanning depends on workspace goals, market assumptions, and risk constraints. "
                "EducationTutoring depends on learner memory, examples, and misconception tracking. "
                "Misconception tracking causes adaptive explanations. "
                "Unsupported market assumptions cause explicit caveats."
            ),
            expected_focus=["business", "education", "personalization"],
        ),
        FrontierTrainingRecord(
            domain_hint="frontier_media_generation",
            source_trust=0.9,
            content=(
                "ImageGenerationPrompt depends on scene graph, style constraints, safety policy, and asset provenance. "
                "AudioGenerationPrompt depends on voice rights, script structure, and pronunciation notes. "
                "VideoGenerationPrompt depends on storyboard, shot list, motion constraints, and human approval. "
                "Human approval causes safe execution for risky media generation."
            ),
            expected_focus=["image_generation", "audio_generation", "video_generation", "approval_gates"],
        ),
        FrontierTrainingRecord(
            domain_hint="frontier_agentic_tasks",
            source_trust=0.9,
            content=(
                "AgenticTaskExecution depends on typed plans, permission checks, dry runs, audit events, and rollback metadata. "
                "Irreversible changes cause human approval requirements. "
                "Dry run plans cause safer execution. "
                "Audit events cause replayable operational memory."
            ),
            expected_focus=["agentic_task", "permissions", "auditability"],
        ),
        FrontierTrainingRecord(
            domain_hint="frontier_energy_efficiency",
            source_trust=0.9,
            content=(
                "AdaptiveTransformerThinning depends on deterministic intent confidence and sourced CSSE answers. "
                "High deterministic confidence causes T1 bypass. "
                "High sourced answer confidence causes T2 bypass. "
                "Persistent retrieval causes lower repeated inference cost."
            ),
            expected_focus=["cost", "energy", "transformer_bypass"],
        ),
    ]


def write_records(path: Path = DEFAULT_OUTPUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in training_records():
            handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate JIMS-AI frontier capability training seed records.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    path = write_records(args.output)
    print(path)


if __name__ == "__main__":
    main()
