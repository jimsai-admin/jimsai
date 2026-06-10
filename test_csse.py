"""Quick validation of the rewritten CSSE — no pipeline startup needed."""
import sys
import os

# Put prototype on path so package-relative imports work
sys.path.insert(0, r"c:\Users\ajibe\Jims-AI\prototype")

# Stub out provider connections so imports don't try to connect
os.environ["JIMS_STORAGE_BACKEND"] = "memory"
os.environ["JIMS_STRICT_PROVIDER_STARTUP"] = "false"
os.environ["JIMS_ENABLE_NEO4J"] = "false"
os.environ["JIMS_ENABLE_POSTGRES"] = "false"
os.environ["JIMS_ENABLE_VECTORIZE"] = "false"
os.environ["JIMS_ENABLE_R2"] = "false"
os.environ["JIMS_ENABLE_MULTIMODAL_ENCODERS"] = "false"
os.environ["JIMS_ENABLE_LOCAL_QWEN"] = "false"
os.environ["SUPABASE_URL"] = ""
os.environ["NEO4J_URI"] = ""
os.environ["NEO4J_PASSWORD"] = ""
os.environ["REDIS_URL"] = ""

from jimsai.csse import ConstrainedSemanticSynthesisEngine
from jimsai.models import (
    VerifiedCognitiveObject, ReasoningStep, ExecutionPlan, ActivationDecision,
    CanvasResult, InventionResult, AbstractionResult, CapabilityPlan, CapabilityKind,
)

csse = ConstrainedSemanticSynthesisEngine()


def make_obj(
    intent="WORKSPACE_QUERY",
    claims=None,
    relations=None,
    gaps=None,
    confidence=0.85,
    sources=None,
    generation_mode="FACT",
    capability_kind=None,
    style_signature=None,
):
    steps = []
    claims = claims or []
    relations = relations or (["ASSERT"] * len(claims))
    for claim, rel in zip(claims, relations):
        steps.append(ReasoningStep(
            claim=claim,
            confidence=confidence,
            sources=sources or ["sig_abc"],
            relation=rel,
        ))
    plan = None
    if capability_kind:
        plan = CapabilityPlan(
            kind=capability_kind,
            route=str(capability_kind.value).lower().replace("_", "-"),
            routing_signals={},
            confidence=confidence,
        )
    return VerifiedCognitiveObject(
        trace_id="trace_test",
        intent=intent,
        verified_plan=ExecutionPlan(steps=[]),
        simulation_results=[],
        constraint_checks=[],
        semantic_graph={},
        reasoning_chain=steps,
        knowledge_gaps=gaps or [],
        sources=sources or (["sig_abc"] if claims else []),
        confidence=confidence,
        activation=ActivationDecision(route="retrieval", run_retrieval=True, reason="test", confidence=confidence),
        canvas_result=CanvasResult(activated=False, patterns=[]),
        invention_result=InventionResult(activated=False, goal="", candidate_steps=[]),
        abstraction_result=AbstractionResult(concepts=[], analogies=[], confidence=0.0),
        world_model_activations=[],
        layer_results=[],
        generation_mode=generation_mode,
        style_signature=style_signature or {"user_prompt": "test"},
        capability_plan=plan,
    )


PASS = "✅"
FAIL = "❌"
results = []


def check(label, condition, response=""):
    results.append((label, condition))
    icon = PASS if condition else FAIL
    print(f"  {icon} {label}")
    if not condition and response:
        print(f"     got: {response[:150]!r}")


# ── Math ──────────────────────────────────────────────────────────────────────
print("\n── Math results ──")

obj = make_obj(
    intent="MATH_SCIENCE",
    claims=["Verified calculation: 2+9 = 11"],
    confidence=0.99,
    sources=["sig_math"],
    capability_kind=CapabilityKind.MATH_SCIENCE,
)
r = csse.render(obj)
print(f"\n  [Response]\n{r}\n")
check("2+9 shows 11 prominently", "11" in r, r)
check("No [Gap] tier label", "[Gap" not in r, r)
check("No raw tier labels", "[Verified •" not in r and "[High Con" not in r, r)
check("Confidence phrase present (tier 1 = certain)", "certain" in r.lower(), r)

obj2 = make_obj(
    intent="MATH_SCIENCE",
    claims=["Verified equation solution for x: 3*x-7=14 -> [7]"],
    confidence=0.99,
    sources=["sig_eq"],
    capability_kind=CapabilityKind.MATH_SCIENCE,
)
r2 = csse.render(obj2)
print(f"\n  [Equation Response]\n{r2}\n")
check("Equation shows x and 7", "7" in r2 and "x" in r2.lower(), r2)
check("No internal tier labels in equation", "[Verified •" not in r2, r2)

# ── Causal ────────────────────────────────────────────────────────────────────
print("\n── Causal results ──")

obj3 = make_obj(
    intent="WORKSPACE_QUERY",
    claims=["High CPU usage causes slow response times.", "Slow response times causes user frustration."],
    relations=["CAUSES", "CAUSES"],
    confidence=0.82,
    sources=["sig_causal"],
)
r3 = csse.render(obj3)
print(f"\n  [Causal Response]\n{r3}\n")
check("Causal content appears", "cpu" in r3.lower() or "response" in r3.lower(), r3)
check("No tier labels", "[Verified •" not in r3 and "[Plausible" not in r3, r3)
check("Confidence phrase (tier 3 = believe)", "believe" in r3.lower() or "confident" in r3.lower(), r3)

# ── General claims ────────────────────────────────────────────────────────────
print("\n── General claims ──")

obj4 = make_obj(
    intent="WORKSPACE_QUERY",
    claims=["The encoder depends on MultimodalEncoderAdapter."],
    confidence=0.88,
    sources=["sig_dep"],
)
r4 = csse.render(obj4)
print(f"\n  [Claim Response]\n{r4}\n")
check("Claim shown", "encoder" in r4.lower(), r4)
check("No internal labels", "[Gap" not in r4 and "[High Con" not in r4, r4)
check("Confidence phrase present", any(w in r4.lower() for w in ("confident", "believe", "certain")), r4)

# ── Gaps ──────────────────────────────────────────────────────────────────────
print("\n── Gap responses ──")

obj5 = make_obj(
    intent="MATH_SCIENCE",
    claims=[],
    gaps=["Math capability routed correctly, but verified solver could not solve expression: sympy unavailable and fallback solve failed."],
    confidence=0.30,
    sources=[],
    capability_kind=CapabilityKind.MATH_SCIENCE,
)
r5 = csse.render(obj5)
print(f"\n  [Math Gap Response]\n{r5}\n")
check("Math gap helpful (mentions expression/arithmetic)", any(w in r5.lower() for w in ("arithmetic", "expression", "equation", "form")), r5)
check("No '[Gap • Unresolved]' shown", "[Gap • Unresolved]" not in r5, r5)
check("No 'verified memory' phrase", "verified memory" not in r5.lower(), r5)

obj6 = make_obj(
    intent="GENERAL_FACT",
    claims=[],
    gaps=["No source signatures matched the query; factual claims are withheld."],
    confidence=0.28,
    sources=[],
)
r6 = csse.render(obj6)
print(f"\n  [General Fact Gap]\n{r6}\n")
check("General gap suggests teaching", any(w in r6.lower() for w in ("teach", "share", "document", "tell", "learn")), r6)
check("No tier labels in gap", "[Gap •" not in r6, r6)

obj7 = make_obj(
    intent="WORKSPACE_QUERY",
    claims=[],
    gaps=["No direct claim found."],
    confidence=0.35,
    sources=["sig_related"],
)
r7 = csse.render(obj7)
print(f"\n  [Related-not-direct Response]\n{r7}\n")
check("Related response offered", any(w in r7.lower() for w in ("related", "rephrase", "context", "directly")), r7)
check("No tier labels", "[Gap •" not in r7, r7)

# ── No confidence for gap tier ────────────────────────────────────────────────
print("\n── Confidence phrases ──")

obj8 = make_obj(intent="WORKSPACE_QUERY", claims=[], confidence=0.25, sources=[])
r8 = csse.render(obj8)
check("Tier 5 gap: no confidence phrase", "I'm certain" not in r8 and "I'm quite confident" not in r8, r8)
check("Still has content", len(r8.strip()) > 20, r8)

obj9 = make_obj(
    intent="WORKSPACE_QUERY",
    claims=["Your project uses Neo4j for graph storage."],
    confidence=0.72,
    sources=["sig_x"],
)
r9 = csse.render(obj9)
check("Tier 3 has 'I believe' phrasing", "believe" in r9.lower(), r9)

obj10 = make_obj(
    intent="WORKSPACE_QUERY",
    claims=["The pipeline uses DualRepresentationEncoder."],
    confidence=0.92,
    sources=["sig_y"],
)
r10 = csse.render(obj10)
check("Tier 2 has 'quite confident' phrasing", "confident" in r10.lower(), r10)

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{'='*55}")
passed = sum(1 for _, ok in results if ok)
total = len(results)
print(f"CSSE validation: {passed}/{total} checks passed")
if passed < total:
    print("\nFailed:")
    for label, ok in results:
        if not ok:
            print(f"  ❌ {label}")
sys.exit(0 if passed == total else 1)
