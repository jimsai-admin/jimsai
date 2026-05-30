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


def test_compiler_routes_known_v9_code_generation_without_sandbox():
    compiler = SemanticCompilerRuntime()
    ir = compiler.compile("Write a Python function and tests for a retry wrapper.")
    assert ir.target_ir == "CODE_GENERATE"
    assert ir.scope_constraints["v9_capability_hint"] == "coding"
    assert ir.execution_mode == "DETERMINISTIC_CORE"


def test_compiler_routes_known_v9_media_generation_without_sandbox():
    compiler = SemanticCompilerRuntime()
    ir = compiler.compile("Generate an image of a solar powered bakery dashboard.")
    assert ir.target_ir == "WORKSPACE_QUERY"
    assert ir.scope_constraints["v9_capability_hint"] == "image_generation"
    assert ir.execution_mode == "DETERMINISTIC_CORE"


def test_compiler_routes_jims_architecture_memory_questions_without_sandbox():
    compiler = SemanticCompilerRuntime()
    ir = compiler.compile("How does adaptive transformer thinning reduce repeated inference cost?")
    assert ir.target_ir == "WORKSPACE_QUERY"
    assert ir.scope_constraints["v9_capability_hint"] == "jims_architecture"
    assert ir.execution_mode == "DETERMINISTIC_CORE"


def test_compiler_routes_agentic_safety_tasks_without_sandbox():
    compiler = SemanticCompilerRuntime()
    ir = compiler.compile("Schedule an automated deployment task with rollback checks.")
    assert ir.target_ir == "WORKSPACE_QUERY"
    assert ir.scope_constraints["v9_capability_hint"] == "agentic_task"
    assert ir.execution_mode == "DETERMINISTIC_CORE"


def test_compiler_routes_public_memory_questions_without_sandbox():
    compiler = SemanticCompilerRuntime()
    ir = compiler.compile("What evidence supports climate change?")
    assert ir.target_ir == "WORKSPACE_QUERY"
    assert ir.scope_constraints["v9_capability_hint"] == "public_memory"
    assert ir.execution_mode == "DETERMINISTIC_CORE"


def test_compiler_routes_code_design_questions_without_sandbox():
    compiler = SemanticCompilerRuntime()
    ir = compiler.compile("Show the safe design considerations for JavaScript fetch API calls.")
    assert ir.target_ir == "CODE_GENERATE"
    assert ir.scope_constraints["v9_capability_hint"] == "coding"
    assert ir.execution_mode == "DETERMINISTIC_CORE"
