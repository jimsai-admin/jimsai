"""Debug profile write/recall in-process to trace the exact failure."""
from __future__ import annotations
import asyncio, sys, os

# Force short timeouts so unavailable Modal calls fail fast during local debugging.
os.environ.setdefault("JIMS_INTENT_EMBEDDING_TIMEOUT", "2")
os.environ.setdefault("JIMS_GENERATION_TIMEOUT", "4")
os.environ.setdefault("JIMS_CAPABILITY_EMBEDDING_TIMEOUT", "2")
os.environ.setdefault("JIMS_CAPABILITY_CLASSIFIER_TIMEOUT", "2")

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)
try:
    from dotenv import load_dotenv; load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except Exception:
    pass

from prototype.jimsai.pipeline import JimsAIPipeline
from prototype.jimsai.models import PipelineRequest, Modality


async def main() -> None:
    p = JimsAIPipeline()

    test_cases = [
        ("My name is Celestine.", "What is my name?",       "celestine", "ws_prof_en", "u_celes"),
        ("Je m'appelle Kofi.",    "Comment je m'appelle?",  "kofi",      "ws_prof_fr", "u_kofi"),
        ("اسمي عمر.",             "ما اسمي؟",               "omar",      "ws_prof_ar", "u_omar"),
    ]

    for write_q, recall_q, expect, ws, user in test_cases:
        print(f"\n{'='*60}")
        print(f"WRITE: {write_q!r}  user={user}  ws={ws}")

        wr = await p.run(PipelineRequest(
            user_id=user, workspace_id=ws,
            query=write_q, modality=Modality.TEXT,
        ))
        pq_write = wr.ir.scope_constraints.get("profile_query")
        promo = next((l for l in wr.layer_results if l.layer == "V9_user_fact_promotion"), None)
        promo_count = promo.data.get("promoted", 0) if promo else 0
        print(f"  ir={wr.ir.target_ir}  pq={pq_write}  conf={wr.confidence:.2f}  promoted={promo_count}")

        # Inspect memory directly
        sigs = p.memory.visible_signatures(workspace_id=ws, user_id=user)
        print(f"  memory: total_visible={len(sigs)}  total_in_sensory={len(p.memory.sensory)}")
        # Check all sensory signatures regardless of scope
        for sid, s in list(p.memory.sensory.items()):
            print(f"    sensory sig: id={sid[:12]}  ws={s.workspace_id!r}  user={s.user_id!r}  tags={s.abstraction_tags[:3]}")
            for r in (s.structured.relations or []):
                if r.subject.lower() == "user":
                    print(f"      relation: {r.subject}.{r.predicate}={r.object!r}  conf={r.confidence:.2f}")
        profile_sigs = [
            s for s in sigs
            if any(
                r.subject.lower() == "user" and (r.predicate.startswith("has_") or r.predicate.startswith("is_"))
                for r in (s.structured.relations or [])
            )
        ]
        print(f"  profile_sigs_in_scope={len(profile_sigs)}")

        print(f"\nRECALL: {recall_q!r}")
        rr = await p.run(PipelineRequest(
            user_id=user, workspace_id=ws,
            query=recall_q, modality=Modality.TEXT,
        ))
        pq_recall = rr.ir.scope_constraints.get("profile_query")
        print(f"  ir={rr.ir.target_ir}  pq={pq_recall}  conf={rr.confidence:.2f}  srcs={len(rr.sources)}")
        cap = rr.capability_plan.kind.value if rr.capability_plan else "?"
        print(f"  cap={cap}")
        print(f"  response: {rr.response[:120]}")
        recalled = expect.lower() in rr.response.lower() or len(rr.sources) > 0
        print(f"  RESULT: {'PASS' if recalled else 'FAIL'}  (expect {expect!r} in response)")


if __name__ == "__main__":
    asyncio.run(main())
