import os
os.environ.pop('JIMS_CLASSIFICATION_SERVICE_URL', None)
os.environ.pop('JIMS_INTENT_SERVICE_URL', None)
os.environ.pop('JIMS_RENDERER_SERVICE_URL', None)
os.environ.pop('JIMS_REASONING_SERVICE_URL', None)

from prototype.jimsai.semantic_compiler import SemanticCompilerRuntime
import asyncio

async def test():
    compiler = SemanticCompilerRuntime()
    classifier = compiler.classifier
    
    # Check profile prototype
    print(f"Profile prototype: {classifier.profile_prototype_text}")
    print(f"Profile embedding: {classifier._get_profile_embedding()[:5]}...")
    
    # Get all intent scores for English
    query = "My name is Celestine."
    scores = classifier.get_intent_scores(query)
    print(f"\nScores for '{query}':")
    for intent, score in sorted(scores.items(), key=lambda x: -x[1]):
        print(f"  {intent}: {score:.4f}")
    
    # Check prototype embeddings
    prototypes = classifier._get_prototype_embeddings()
    print(f"\nPrototype embeddings loaded: {len(prototypes)}")
    for intent, emb in prototypes.items():
        print(f"  {intent}: {emb[:5]}...")

asyncio.run(test())