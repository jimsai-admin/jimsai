from prototype.jimsai.csse import ConstrainedSemanticSynthesisEngine
from prototype.jimsai.models import ExecutionPlan, PlanStep, ReasoningStep, VerifiedCognitiveObject


def _vco(**updates):
    base = {
        "trace_id": "trace_test",
        "intent": "WORKSPACE_QUERY",
        "verified_plan": ExecutionPlan(
            goal="answer from memory",
            steps=[
                PlanStep(
                    order=1,
                    action="render_verified_claims",
                    inputs={},
                    expected_output="bounded answer",
                )
            ],
        ),
        "confidence": 0.81,
    }
    base.update(updates)
    return VerifiedCognitiveObject(**base)


def test_csse_summarizes_verified_chain_without_per_claim_audit_noise():
    obj = _vco(
        reasoning_chain=[
            ReasoningStep(claim="A causes B.", confidence=0.9, sources=["sig_1"], relation="CAUSES"),
            ReasoningStep(claim="B causes C.", confidence=0.86, sources=["sig_1"], relation="CAUSES"),
        ],
        sources=["sig_1"],
    )

    response = ConstrainedSemanticSynthesisEngine().render(obj)

    assert "Here's what I can verify from memory:" in response
    assert "Verified path: A -> B -> C." in response
    assert "- A causes B." in response
    assert "Confidence: 0.81" in response
    assert "Source signatures:" in response
    assert "sources=sig_1" not in response
    assert "Confidence 0.90" not in response


def test_csse_does_not_present_empty_evidence_as_verified_claim():
    obj = _vco(
        reasoning_chain=[
            ReasoningStep(
                claim="No verified claim emitted because retrieval returned no source signatures.",
                confidence=0.3,
                sources=[],
                relation="HEDGE",
            )
        ],
        knowledge_gaps=["No matching source signatures."],
        confidence=0.3,
    )

    response = ConstrainedSemanticSynthesisEngine().render(obj)

    assert "I do not have verified memory signatures for a factual answer yet." in response
    assert "Here's what I can verify from memory:" not in response
    assert "Explicit gaps:" in response
    assert "No matching source signatures." in response
    assert "Confidence: 0.30" in response
