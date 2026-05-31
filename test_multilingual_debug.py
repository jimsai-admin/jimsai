from prototype.jimsai.intent_classifier import EmbeddingClassifier

classifier = EmbeddingClassifier()

test_queries = [
    "¿Cómo descargo este archivo?",  # Spanish fetch
    "اكتب دالة بيثون لحساب المتوسط",  # Arabic code
]

for query in test_queries:
    target, confidence = classifier.classify_intent(query)
    scores = classifier.get_intent_scores(query)
    print(f"\nQuery: {query}")
    print(f"Top: {target} [{confidence:.4f}]")
    print("Top 3 scores:")
    for ir_target, score in sorted(scores.items(), key=lambda x: -x[1])[:3]:
        print(f"  {ir_target}: {score:.4f}")
