from prototype.jimsai.semantic_compiler import SemanticCompilerRuntime, sanitize


def test_sanitize_is_stable():
    assert sanitize("Yo, send over that layout please!") == ["send", "layout"]


def test_compiler_routes_canvas():
    compiler = SemanticCompilerRuntime()
    ir = compiler.compile("Run deep analysis on the full codebase")
    assert ir.target_ir == "RUN_CANVAS"
    assert ir.execution_mode == "DETERMINISTIC_CORE"


def test_compiler_uses_sandbox_for_unmatched_input():
    compiler = SemanticCompilerRuntime()
    ir = compiler.compile("zzzz qqqq")
    assert ir.target_ir == "OP_ESCAPE_TO_SANDBOX"


def test_compiler_extracts_causal_entity_scope():
    compiler = SemanticCompilerRuntime()
    ir = compiler.compile("What services are affected if UserModel.id changes?")
    assert "What" not in ir.scope_constraints["entities"]
    assert "UserModel.id" in ir.scope_constraints["entities"]
    assert "UserModel.id_change" in ir.scope_constraints["entities"]


def test_compiler_marks_profile_memory_queries():
    compiler = SemanticCompilerRuntime()
    ir = compiler.compile("What do you know about me?")
    assert ir.target_ir == "WORKSPACE_QUERY"
    assert ir.scope_constraints["profile_query"] is True
    assert ir.execution_mode == "DETERMINISTIC_CORE"
