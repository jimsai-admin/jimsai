"""
Debug memory write + recall - check what's in memory
"""
import asyncio, os, time
from pathlib import Path
ROOT = Path(__file__).parent.parent
import sys; sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv; load_dotenv()

from prototype.jimsai.pipeline import JimsAIPipeline
from prototype.jimsai.models import PipelineRequest, Modality

async def main():
    print("Initializing pipeline...")
    pipeline = JimsAIPipeline()
    print("Pipeline ready.\n")

    # Check initial memory stats
    print(f"Initial memory stats: {pipeline.memory.stats()}")

    # Manually trace through the pipeline
    request = PipelineRequest(
        user_id="test_user",
        query="My name is Celestine.",
        modality=Modality.TEXT,
        workspace_id="test_ws",
        thread_id="mem_test",
        return_trace=True
    )
    
    # Get IR
    session = pipeline._load_session(request.user_id, request.thread_id)
    ir, intent_layer_result = await pipeline.intent_layer.infer(request, session)
    print(f"IR: {ir.target_ir}, scope_constraints: {ir.scope_constraints}")
    
    # Encode
    input_signature, encoder_layer_result = pipeline.encoder_layer.encode(request, ir)
    print(f"Input signature: {input_signature.id}")
    print(f"Input signature confidence: {input_signature.confidence.score}")
    print(f"Input signature entities: {[e.name for e in input_signature.structured.entities]}")
    print(f"Input signature relations: {[(r.subject, r.predicate, r.object) for r in input_signature.structured.relations]}")
    
    # Learn
    learn_result = pipeline.learning_layer.learn(input_signature)
    print(f"Learn result: {learn_result.summary}")
    print(f"Memory stats after learn: {pipeline.memory.stats()}")
    
    # Check all signatures in all layers
    print(f"Sensory: {list(pipeline.memory.sensory.keys())}")
    print(f"Working: {list(pipeline.memory.working.keys())}")
    print(f"Episodic: {list(pipeline.memory.episodic.keys())}")
    print(f"Semantic: {list(pipeline.memory.semantic.keys())}")

asyncio.run(main())