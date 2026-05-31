from prototype.jimsai.semantic_compiler import SemanticCompilerRuntime, sanitize, normalize_language
from prototype.jimsai.intent_classifier import get_classifier

compiler = SemanticCompilerRuntime()

test_cases = [
    ('h0w d0 i uplod fle', 'FETCH_DOCUMENT'),
    ('Run deep analysis on the full codebase', 'RUN_CANVAS'),
    ('zzzz qqqq', 'OP_ESCAPE_TO_SANDBOX'),
]

for raw_input, expected in test_cases:
    print(f'\n=== Query: {raw_input} ===')
    print(f'Expected: {expected}')
    
    # Step 1: classifier
    target_ir, confidence = compiler.classifier.classify_intent(raw_input)
    print(f'Classifier result: {target_ir} ({confidence:.4f})')
    
    # Step 2: check preprocessing
    normalized_input = normalize_language(raw_input)
    tokens = sanitize(raw_input)
    print(f'Tokens: {tokens}')
    
    # Step 3: scope
    scope = compiler._scope_from_tokens(tokens, normalized_input)
    q_intent = scope.get("question_intent")
    print(f'Scope question_intent: {q_intent}')
    
    # Step 4: profile query
    is_profile = compiler.classifier.is_profile_query(raw_input, threshold=0.70)
    print(f'is_profile_query: {is_profile}')
    
    # Step 5: v9_override
    v9_override = compiler._v9_capability_override(tokens, normalized_input)
    print(f'v9_override: {v9_override}')
    
    # Step 6: Full compile
    ir = compiler.compile(raw_input)
    print(f'Final result: {ir.target_ir} ({ir.confidence:.4f})')
