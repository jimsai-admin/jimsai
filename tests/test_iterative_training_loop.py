from pathlib import Path

from prototype.jimsai.semantic_compiler import SemanticCompilerRuntime
from scripts.iterative_training_loop import (
    EvalOutcome,
    correction_candidates,
    eval_prompts,
    intent_stability_analysis,
    language_variants,
    provider_usage_analysis,
    training_records,
    training_variant_summary,
)


def test_iterative_training_loop_loads_training_and_eval_jsonl(tmp_path):
    training_path = tmp_path / "training.jsonl"
    eval_path = tmp_path / "eval.jsonl"
    training_path.write_text(
        '{"domain_hint":"demo","source_trust":0.91,"content":"A depends on B.","expected_focus":["memory"],"source_url":"https://example.gov/a","license":"public domain"}\n',
        encoding="utf-8",
    )
    eval_path.write_text(
        '{"id":"demo","prompt":"What depends on B?","expected_capability":"memory_chat","must_include":["A"]}\n',
        encoding="utf-8",
    )

    records = training_records([training_path])
    prompts = eval_prompts(eval_path)

    assert records[0].domain_hint == "demo"
    assert records[0].source_trust == 0.91
    assert records[0].expected_focus == ["memory"]
    assert records[0].source_url == "https://example.gov/a"
    assert records[0].payload_content().startswith("Source URL: https://example.gov/a.")
    assert prompts[0].id == "demo"
    assert prompts[0].must_include == ["A"]


def test_iterative_training_loop_creates_review_only_correction_candidates():
    outcomes = [
        EvalOutcome(
            id="case_1",
            passed=False,
            failures=["missing source"],
            prompt="Why?",
            response="No source.",
            confidence=0.2,
            sources=0,
            gaps=1,
            target_ir="WORKSPACE_QUERY",
            capability="memory_chat",
            used_groq=False,
        )
    ]

    candidates = correction_candidates(outcomes)

    assert candidates[0]["domain_hint"] == "iterative_failure_correction"
    assert candidates[0]["source_trust"] < 0.75
    assert "requires human review before promotion" in candidates[0]["content"]


def test_iterative_training_loop_summarizes_provider_usage():
    outcomes = [
        EvalOutcome(
            id="memory",
            passed=True,
            failures=[],
            prompt="What do you remember?",
            response="Memory answer.",
            confidence=0.8,
            sources=1,
            gaps=0,
            target_ir="WORKSPACE_QUERY",
            capability="memory_chat",
            used_groq=False,
        ),
        EvalOutcome(
            id="creative",
            passed=True,
            failures=[],
            prompt="Rewrite this.",
            response="Rendered answer.",
            confidence=0.7,
            sources=1,
            gaps=0,
            target_ir="WORKSPACE_QUERY",
            capability="creative_text",
            used_groq=True,
        ),
    ]

    usage = provider_usage_analysis(outcomes)

    assert usage["provider_model_calls"] == 1
    assert usage["provider_model_bypassed"] == 1
    assert usage["provider_model_call_rate"] == 0.5
    assert usage["by_capability"]["memory_chat"]["provider_model_bypassed"] == 1


def test_language_variants_preserve_compiler_intent_for_public_prompts():
    prompts = eval_prompts(Path("datasets/iterative_eval_prompts.jsonl"))
    sample = [prompt for prompt in prompts if prompt.id in {"code_generation_route", "phishing_safety_public"}]

    analysis = intent_stability_analysis(SemanticCompilerRuntime(), sample)

    assert len(language_variants(sample[0].prompt)) == 6
    assert analysis["intent_stability_score"] >= 0.95
    assert analysis["variant_kind_coverage"] < 1.0
    assert {"pidgin", "mixed_language", "regional_dialect"} <= set(analysis["missing_variant_kinds"])


def test_training_variant_summary_does_not_duplicate_memory_claims(tmp_path):
    training_path = tmp_path / "training.jsonl"
    training_path.write_text('{"content":"How should I test Python code?","domain_hint":"demo"}\n', encoding="utf-8")
    records = training_records([training_path])

    summary = training_variant_summary(records)

    assert summary["record_count"] == 1
    assert summary["generated_total"] == 6
    assert summary["ingested_as_training"] is False
    assert "pidgin" in summary["corpus_required_variant_kinds"]
