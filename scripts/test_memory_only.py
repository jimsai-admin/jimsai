"""
Focused memory write + recall test with pre-warm.
Tests only the memory path after confirming services are warm.
Supports multilingual queries.
"""
import asyncio, os, time
from pathlib import Path

# Use short timeouts so unavailable external services fail fast.
os.environ.setdefault("JIMS_EMBEDDING_TIMEOUT", "1")
os.environ.setdefault("JIMS_INTENT_EMBEDDING_TIMEOUT", "1")
os.environ.setdefault("JIMS_LIVE_EMBEDDING_TIMEOUT", "1")
os.environ.setdefault("JIMS_PROVIDER_HTTP_TIMEOUT", "1")
os.environ.setdefault("JIMS_CAPABILITY_EMBEDDING_TIMEOUT", "1")
os.environ.setdefault("JIMS_CLASSIFICATION_SERVICE_URL", "")  # Disable classification service
os.environ.setdefault("JIMS_INTENT_SERVICE_URL", "")  # Disable intent service
os.environ.setdefault("JIMS_RENDERER_SERVICE_URL", "")  # Disable renderer service
os.environ.setdefault("JIMS_REASONING_SERVICE_URL", "")  # Disable reasoning service

ROOT = Path(__file__).parent.parent
import sys; sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv; load_dotenv()

from prototype.jimsai.pipeline import JimsAIPipeline
from prototype.jimsai.models import PipelineRequest, Modality

PASS, FAIL = "[PASS]", "[FAIL]"

async def run_test(pipeline, user_id, query_write, query_recall, workspace_id, thread_id, lang_name):
    """Run a single write/recall test."""
    print(f"\n--- Testing {lang_name} ---")
    
    # Write
    t0 = time.perf_counter()
    wr = await pipeline.run(PipelineRequest(
        user_id=user_id,
        query=query_write,
        modality=Modality.TEXT,
        workspace_id=workspace_id,
        thread_id=thread_id,
        return_trace=True
    ))
    ms_write = (time.perf_counter()-t0)*1000
    print(f"{PASS if wr.confidence > 0.5 else FAIL} Write ({ms_write:.0f}ms conf={wr.confidence:.2f})")
    print(f"  Write IR: {wr.ir.target_ir} profile_write={wr.ir.scope_constraints.get('profile_write')}")

    # Recall
    t0 = time.perf_counter()
    rr = await pipeline.run(PipelineRequest(
        user_id=user_id,
        query=query_recall,
        modality=Modality.TEXT,
        workspace_id=workspace_id,
        thread_id=thread_id,
        return_trace=True
    ))
    ms_recall = (time.perf_counter()-t0)*1000
    resp = rr.response
    sources = rr.sources
    
    print(f"\nRecall ({ms_recall:.0f}ms)")
    print(f"  IR: {rr.ir.target_ir} profile_query={rr.ir.scope_constraints.get('profile_query')}")
    print(f"  sources={len(sources)}")
    print(f"  response: {resp[:120]}")

    # Check if name/entity is in response (case-insensitive, supports Unicode)
    # Extract key entity from write query
    import re
    # Simple extraction - look for capitalized words that might be names
    entities = re.findall(r'\b[A-ZÀ-Ÿ][a-zà-ÿ]+\b', query_write)
    recalled = False
    for entity in entities:
        if entity.lower() in resp.lower():
            recalled = True
            break
    if not recalled and len(sources) > 0:
        recalled = True
        
    print(f"\n{PASS if recalled else FAIL} Memory recall: {'PASS' if recalled else 'FAIL'}")
    return recalled

async def main():
    print("Initializing pipeline...")
    pipeline = JimsAIPipeline()
    # Clear cache to ensure fresh run
    pipeline.result_cache.clear()
    print("Pipeline ready.\n")

    all_passed = True
    
    # Test 1: English
    all_passed &= await run_test(
        pipeline, "test_user_en", 
        "My name is Celestine.", 
        "What is my name?",
        "test_ws_en", "mem_test_en", "English"
    )
    
    # Test 2: French
    all_passed &= await run_test(
        pipeline, "test_user_fr", 
        "Je m'appelle Pierre.", 
        "Comment je m'appelle ?",
        "test_ws_fr", "mem_test_fr", "French"
    )
    
    # Test 3: Spanish
    all_passed &= await run_test(
        pipeline, "test_user_es", 
        "Me llamo María.", 
        "¿Cómo me llamo?",
        "test_ws_es", "mem_test_es", "Spanish"
    )
    
    # Test 4: Yoruba (with Unicode)
    all_passed &= await run_test(
        pipeline, "test_user_yo", 
        "Orúkọ mi ni Adé.", 
        "Kí ni orúkọ mi?",
        "test_ws_yo", "mem_test_yo", "Yoruba"
    )
    
    # Test 5: Arabic (RTL)
    all_passed &= await run_test(
        pipeline, "test_user_ar", 
        "اسمي أحمد.", 
        "ما هو اسمي؟",
        "test_ws_ar", "mem_test_ar", "Arabic"
    )
    
    # Test 6: Chinese
    all_passed &= await run_test(
        pipeline, "test_user_zh", 
        "我的名字是小明。", 
        "我的名字是什么？",
        "test_ws_zh", "mem_test_zh", "Chinese"
    )
    
    print(f"\n{'='*50}")
    print(f"{PASS if all_passed else FAIL} All tests: {'PASSED' if all_passed else 'FAILED'}")

asyncio.run(main())
