import os
# Use real embeddings - don't disable services
os.environ.pop('JIMS_CLASSIFICATION_SERVICE_URL', None)
os.environ.pop('JIMS_INTENT_SERVICE_URL', None)
os.environ.pop('JIMS_RENDERER_SERVICE_URL', None)
os.environ.pop('JIMS_REASONING_SERVICE_URL', None)

from prototype.jimsai.semantic_compiler import SemanticCompilerRuntime
import asyncio

async def test():
    compiler = SemanticCompilerRuntime()
    classifier = compiler.classifier
    
    queries = [
        ('My name is Celestine.', 'English'),
        ("Je m'appelle Pierre.", 'French'),
        ('Me llamo María.', 'Spanish'),
        ('Orúkọ mi ni Adé.', 'Yoruba'),
        ('اسمي أحمد.', 'Arabic'),
        ('我的名字是小明。', 'Chinese'),
    ]
    
    for query, lang in queries:
        intent, score = classifier.classify_intent(query)
        is_profile = classifier.is_profile_query(query)
        print(f'{lang}: intent={intent}, score={score:.4f}, is_profile={is_profile}')

asyncio.run(test())