from prototype.jimsai.intent_classifier import EmbeddingClassifier
classifier = EmbeddingClassifier()

query = 'how xqz'
target, confidence = classifier.classify_intent(query)
scores = classifier.get_intent_scores(query)
print(f'Query: "{query}"')
print(f'Top: {target} [{confidence:.4f}]')
print(f'EMOTIONAL_CATCH: {scores.get("EMOTIONAL_CATCH", 0):.4f}')
print(f'OP_ESCAPE_TO_SANDBOX: {scores.get("OP_ESCAPE_TO_SANDBOX", 0):.4f}')
print(f'Gap: {scores.get("OP_ESCAPE_TO_SANDBOX", 0) - scores.get("EMOTIONAL_CATCH", 0):.4f}')
