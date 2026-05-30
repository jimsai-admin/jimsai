from scripts.iterative_training_loop import EvalOutcome, correction_candidates, eval_prompts, training_records


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
