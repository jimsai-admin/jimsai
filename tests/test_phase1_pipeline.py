import pytest

from prototype.jimsai.models import (
    CanvasRunRequest,
    InventionRunRequest,
    KaggleTrainingRequest,
    MathSolveRequest,
    MemoryDeleteRequest,
    MemoryUpdateRequest,
    PipelineRequest,
    ReviewActionRequest,
    SandboxRunRequest,
    TrainingIngestRequest,
)
from prototype.jimsai.pipeline import JimsAIPipeline
from prototype.jimsai.encoder import DualRepresentationEncoder
from prototype.jimsai.graph import CausalGraphEngine


async def _fake_ingest_overlay(content, context):
    return {
        "document_type": "academic_project",
        "title": "Project Title",
        "entities": [{"name": "John Doe", "type": "person", "confidence": 0.88}],
        "relations": [{"subject": "Project Title", "predicate": "has_author", "object": "John Doe", "confidence": 0.88}],
        "tags": ["academic_project"],
        "confidence": 0.88,
    }


@pytest.mark.asyncio
async def test_pipeline_returns_grounded_response():
    pipeline = JimsAIPipeline()
    await pipeline.ingest_training(
        TrainingIngestRequest(
            user_id="test",
            content=(
                "AuthService depends on UserModel. "
                "UserModel.id_change causes AuthService.token_invalidation. "
                "AuthService.token_invalidation causes PaymentService.session_refresh."
            ),
            source_trust=0.92,
            domain_hint="code_training",
        )
    )
    result = await pipeline.run(PipelineRequest(user_id="test", query="What services are affected if UserModel.id changes?"))
    assert result.ir.target_ir in {"WORKSPACE_QUERY", "GENERAL_FACT"}
    assert result.sources
    assert "Source signatures" in result.response
    assert result.trace


@pytest.mark.asyncio
async def test_pipeline_is_deterministic_for_same_memory_state():
    query = "Explain the Semantic Compiler deterministic execution"
    pipeline_a = JimsAIPipeline()
    pipeline_b = JimsAIPipeline()
    first = await pipeline_a.run(PipelineRequest(user_id="test", query=query))
    second = await pipeline_b.run(PipelineRequest(user_id="test", query=query))
    assert first.ir.target_ir == second.ir.target_ir
    assert first.response == second.response


@pytest.mark.asyncio
async def test_unknown_query_flags_gap_or_sandbox():
    pipeline = JimsAIPipeline()
    result = await pipeline.run(PipelineRequest(user_id="test", query="zzzz qqqq novalue unrouteable"))
    assert result.ir.target_ir == "OP_ESCAPE_TO_SANDBOX" or result.gaps


def test_encoder_extracts_clean_relations():
    signature = DualRepresentationEncoder().encode_text(
        "AuthService depends on UserModel. UserModel.id_change causes AuthService.token_invalidation."
    )
    relations = {(relation.subject, relation.predicate, relation.object) for relation in signature.structured.relations}
    assert ("AuthService", "depends_on", "UserModel") in relations
    assert ("UserModel.id_change", "causes", "AuthService.token_invalidation") in relations


def test_encoder_extracts_user_profile_memory_with_sentence_case():
    signature = DualRepresentationEncoder().encode_text(
        "User profile: My name is Ajibew Irekanmi. I am a software engineer. I am building JIMS-AI."
    )
    relations = {(relation.subject, relation.predicate, relation.object) for relation in signature.structured.relations}
    assert ("user", "has_name", "Ajibew Irekanmi") in relations
    assert ("user", "has_role", "software engineer") in relations
    assert ("user", "is_building", "JIMS-AI") in relations


def test_graph_deduplicates_relation_and_causal_edges():
    signature = DualRepresentationEncoder().encode_text(
        "UserModel.id_change causes AuthService.token_invalidation."
    )
    graph = CausalGraphEngine()
    graph.add_signature(signature)
    paths = graph.traverse("UserModel.id_change")
    edges = paths["usermodel.id_change"]
    assert len(edges) == 1


@pytest.mark.asyncio
async def test_training_ingest_then_query_uses_new_memory():
    pipeline = JimsAIPipeline()
    ingest = await pipeline.ingest_training(
        TrainingIngestRequest(
            user_id="test",
            content="InventoryService depends on StockLedger. StockLedger.update causes InventoryService.recount.",
            source_trust=0.92,
            domain_hint="workspace_training",
        )
    )
    assert ingest.signature.id
    assert ingest.world_model_candidates
    assert ingest.sppe_training_pair.accepted

    result = await pipeline.run(
        PipelineRequest(user_id="test", query="What happens if StockLedger.update changes?")
    )
    assert ingest.signature.id in result.sources


@pytest.mark.asyncio
async def test_pipeline_exposes_strict_layer_chain():
    pipeline = JimsAIPipeline()
    await pipeline.ingest_training(
        TrainingIngestRequest(
            user_id="test",
            content=(
                "AuthService depends on UserModel. "
                "UserModel.id_change causes AuthService.token_invalidation. "
                "AuthService.token_invalidation causes PaymentService.session_refresh."
            ),
            source_trust=0.92,
            domain_hint="code_training",
        )
    )
    result = await pipeline.run(PipelineRequest(user_id="test", query="What services are affected if UserModel.id changes?"))
    layer_names = [layer.layer for layer in result.layer_results]
    assert layer_names == [
        "input",
        "T1_transformer_intent_interface",
        "L1_full_encoder",
        "L2_real_time_learning",
        "V9_persistent_retrieval_hydration",
        "L3_active_canvas",
        "L4_sparse_activation_meta_controller",
        "V9_capability_router",
        "V9_capability_adapters",
        "L5_invention_engine",
        "L6_multi_index_retrieval",
        "L7_abstraction_engine",
        "L8_latent_world_model",
        "L9_reasoning_bridge",
        "T2_transformer_render_interface",
        "output",
        "feedback",
    ]
    assert result.activation is not None
    assert result.capability_plan is not None
    assert result.capability_plan.kind == "memory_chat"
    assert result.abstraction_result is not None
    assert result.world_model_activations


@pytest.mark.asyncio
async def test_v9_capability_router_gates_unconfigured_generation_provider():
    pipeline = JimsAIPipeline()
    result = await pipeline.run(PipelineRequest(user_id="test", query="Generate an image of a solar powered bakery dashboard"))
    assert result.capability_plan is not None
    assert result.capability_plan.kind == "image_generation"
    assert result.capability_results
    assert result.capability_results[0].status in {"unavailable", "blocked"}
    assert any("image_generation" in gap for gap in result.gaps)


@pytest.mark.asyncio
async def test_training_dashboard_maps_pdf_operator_panels():
    pipeline = JimsAIPipeline()
    await pipeline.ingest_training(
        TrainingIngestRequest(
            user_id="test",
            content="RiskService depends on PolicyGraph. PolicyGraph.drift causes RiskService.review.",
            source_trust=0.62,
            domain_hint="risk_training",
        )
    )
    canvas = await pipeline.schedule_canvas(CanvasRunRequest(user_id="test", dataset_ref="workspace://demo", scope="full_codebase"))
    invention = await pipeline.schedule_invention(InventionRunRequest(user_id="test", goal="Design a rollback-safe policy graph migration.", domain="systems"))
    dashboard = await pipeline.training_dashboard()
    assert dashboard.memory_stats["sensory"] >= 1
    assert dashboard.human_review_queue
    assert dashboard.pipeline_monitor["sppe_pairs_total"] == 1
    assert dashboard.canvas_sessions[-1].canvas_session_id == canvas.canvas_session_id
    assert dashboard.invention_sessions[-1].invention_session_id == invention.invention_session_id
    assert dashboard.production_readiness["bounded_transformer_interfaces"] is True
    assert dashboard.production_readiness["auto_training_detection"] is True


@pytest.mark.asyncio
async def test_canvas_invention_review_sandbox_and_math_write_events_and_result_signatures():
    pipeline = JimsAIPipeline()
    ingest = await pipeline.ingest_training(
        TrainingIngestRequest(
            user_id="test",
            content="PolicyGraph.drift causes RiskService.review.",
            source_trust=0.62,
            domain_hint="risk_training",
        )
    )
    candidate = ingest.world_model_candidates[0]

    canvas = await pipeline.schedule_canvas(CanvasRunRequest(user_id="test", dataset_ref="workspace://demo", scope="full"))
    invention = await pipeline.schedule_invention(InventionRunRequest(user_id="test", goal="Design safer policy graph rollback.", domain="systems"))
    review = await pipeline.review_action(
        ReviewActionRequest(user_id="test", provenance=candidate.provenance, rule=candidate.rule, action="accept")
    )
    sandbox = await pipeline.run_sandbox(
        SandboxRunRequest(user_id="test", code="def add(a, b):\n    return a + b", tests="assert add(2, 3) == 5")
    )
    sandbox_cached = await pipeline.run_sandbox(
        SandboxRunRequest(user_id="test", code="def add(a, b):\n    return a + b", tests="assert add(2, 3) == 5")
    )
    math = await pipeline.solve_math(MathSolveRequest(user_id="test", expression="x + 2 = 5", solve_for="x"))
    math_cached = await pipeline.solve_math(MathSolveRequest(user_id="test", expression="x + 2 = 5", solve_for="x"))
    events = await pipeline.audit_events(limit=100)
    event_types = {event["event_type"] for event in events}

    assert canvas.canvas_session_id
    assert invention.invention_session_id
    assert review.accepted is True
    assert review.result_signature.kind == "review"
    assert sandbox.status == "passed"
    assert sandbox.result_signature.kind == "sandbox"
    assert sandbox_cached.status == "cached"
    assert math.status == "solved"
    assert math.result == "[3]"
    assert math_cached.status == "cached"
    assert {"saga_started", "saga_step_completed", "sandbox_execution_completed", "math_solve_completed", "review_action_recorded"} <= event_types


@pytest.mark.asyncio
async def test_training_panel_pagination_replays_stored_data():
    pipeline = JimsAIPipeline()
    for index in range(3):
        await pipeline.ingest_training(
            TrainingIngestRequest(
                user_id="test",
                content=f"InventoryService{index} depends on StockLedger{index}. StockLedger{index}.update causes InventoryService{index}.recount.",
                source_trust=0.91,
                domain_hint="workspace_training",
            )
        )

    first_page = await pipeline.training_panel_page("ingestion", limit=2)
    assert first_page.panel == "ingestion"
    assert len(first_page.items) == 2
    assert first_page.has_more is True
    assert first_page.next_cursor == "2"
    assert first_page.items[0].kind == "training_ingest"

    second_page = await pipeline.training_panel_page("ingestion", cursor=first_page.next_cursor, limit=2)
    assert len(second_page.items) == 1
    assert second_page.has_more is False

    memory_page = await pipeline.training_panel_page("memory", limit=10)
    assert any(item.kind == "signature" and item.title.startswith("sig_") for item in memory_page.items)


@pytest.mark.asyncio
async def test_kaggle_training_run_prepares_notebook_package_without_local_inference(monkeypatch):
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    monkeypatch.delenv("KAGGLE_USERNAME", raising=False)
    monkeypatch.delenv("KAGGLE_KEY", raising=False)
    pipeline = JimsAIPipeline()
    await pipeline.ingest_training(
        TrainingIngestRequest(
            user_id="test",
            content="RiskService depends on PolicyGraph. PolicyGraph.drift causes RiskService.review.",
            source_trust=0.9,
            domain_hint="risk_training",
        )
    )

    run = await pipeline.schedule_kaggle_training(KaggleTrainingRequest(user_id="test", task_type="encoder_finetune"))

    assert run.status == "prepared"
    assert run.local_path
    sessions = await pipeline.training_panel_page("sessions", limit=10)
    assert any(item.kind == "kaggle_training_run" for item in sessions.items)


@pytest.mark.asyncio
async def test_auto_training_policy_detects_encoder_batch_without_forcing_upload(monkeypatch):
    monkeypatch.setenv("JIMS_AUTO_TRAINING_ENABLED", "false")
    monkeypatch.setenv("JIMS_AUTO_TRAIN_MIN_SPPE_PAIRS", "1")
    pipeline = JimsAIPipeline()
    ingest = await pipeline.ingest_training(
        TrainingIngestRequest(
            user_id="test",
            content="QueueService depends on WorkerPool. WorkerPool.exhaustion causes QueueService.delay.",
            source_trust=0.9,
            domain_hint="systems_training",
        )
    )

    decision = ingest.auto_training_decision
    assert decision is not None
    assert decision.enabled is False
    assert decision.task_type == "encoder_finetune"
    assert decision.should_schedule is False
    assert decision.counters["sppe_pairs"] == 1


@pytest.mark.asyncio
async def test_story_causal_question_answers_from_stored_relation():
    pipeline = JimsAIPipeline()
    await pipeline.ingest_training(
        TrainingIngestRequest(
            user_id="test",
            content=(
                "Maya runs a small bakery called BlueOven. BlueOven depends on FlourMill for flour deliveries. "
                "FlourMill.delay causes BlueOven.production_slowdown. "
                "BlueOven.production_slowdown causes MorningOrders.late_delivery."
            ),
            source_trust=0.92,
            domain_hint="story_training",
        )
    )

    why_result = await pipeline.run(PipelineRequest(user_id="test", query="Why would MorningOrders become late?"))
    assert why_result.ir.target_ir == "WORKSPACE_QUERY"
    assert "BlueOven.production_slowdown causes MorningOrders.late_delivery" in why_result.response
    assert why_result.sources

    depend_result = await pipeline.run(PipelineRequest(user_id="test", query="What does BlueOven depend on?"))
    assert "BlueOven depends on FlourMill" in depend_result.response


@pytest.mark.asyncio
async def test_code_impact_traverses_multihop_and_respects_dependency_direction():
    pipeline = JimsAIPipeline()
    await pipeline.ingest_training(
        TrainingIngestRequest(
            user_id="test",
            content=(
                "AuthService.login uses UserRepository.find_user. "
                "AuthService.login depends on UserRepository.find_user. "
                "UserRepository.find_user depends on Postgres.users_table. "
                "Postgres.users_table.schema_change causes UserRepository.find_user.failure. "
                "UserRepository.find_user.failure causes AuthService.login.failure. "
                "AuthService.login.failure causes PaymentService.checkout.blocked. "
                "TokenService.issue_token depends on AuthService.login."
            ),
            source_trust=0.92,
            domain_hint="code_training",
        )
    )

    impact = await pipeline.run(
        PipelineRequest(user_id="test", query="What happens if Postgres.users_table.schema_change occurs?")
    )
    assert "Postgres.users_table.schema_change causes UserRepository.find_user.failure" in impact.response
    assert "UserRepository.find_user.failure causes AuthService.login.failure" in impact.response
    assert "AuthService.login.failure causes PaymentService.checkout.blocked" in impact.response

    dependencies = await pipeline.run(PipelineRequest(user_id="test", query="What does AuthService.login depend on?"))
    assert "AuthService.login depends on UserRepository.find_user" in dependencies.response
    assert "TokenService.issue_token depends on AuthService.login" not in dependencies.response

    dependents = await pipeline.run(PipelineRequest(user_id="test", query="What depends on AuthService.login?"))
    assert "TokenService.issue_token depends on AuthService.login" in dependents.response
    assert "AuthService.login depends on UserRepository.find_user" not in dependents.response
    assert "what depends on authservice.login" not in dependents.response.lower()


@pytest.mark.asyncio
async def test_final_year_project_document_questions_use_structured_signatures():
    pipeline = JimsAIPipeline()
    report = """
Adventist University of Central Africa

DESIGN AND IMPLEMENTATION OF AN AI-POWERED TECHNICAL
PROPOSAL AND COST ESTIMATION SYSTEM FOR SOFTWARE
DEVELOPMENT FIRMS

Case Study: Jimstech Innovations Nigeria Limited

By
AJIBEWA Johnson Irekanmi

Student ID: 25626

ABSTRACT
TITLE: Design and Implementation of an AI-Powered Technical Proposal and Cost Estimation System for Software Development Firms
Name of the Researcher: AJIBEWA Johnson Irekanmi

TABLE OF CONTENTS
Specific Objectives ................................................................................................ 5
Scope of the Project ............................................................................................. 6
Methodology and Techniques Used ..................................................................... 6
Technologies and Tools Used ............................................................................. 49
Presentation of the New System ........................................................................ 51

LIST OF ABBREVIATIONS
Abbreviation Full Meaning
AUCA Adventist University of Central Africa
AI Artificial Intelligence

DEFINITION OF TERMINOLOGIES

Specific Objectives
- To analyze the existing manual proposal preparation and cost estimation processes at Jimstech Innovations Nigeria Limited and identify key inefficiencies and gaps.
- To design a structured requirement analysis module that captures, categorizes, and processes client project requirements using AI-assisted techniques.
- To implement an intelligent proposal generation engine capable of producing structured and professional technical proposals based on analyzed requirements.

Scope of the Project
- Requirement Analysis Module: Enables project managers and software engineers to capture and analyze client project requirements.
- AI Proposal Generation Module: Automatically generates structured technical proposal documents.
- Cost Estimation Module: Calculates projected development costs using AI-supported models.

Methodology and Techniques Used
Interviews and observation were used.

Technologies and Tools Used
HTML was used for page structure. CSS and Bootstrap were used for styling.
JavaScript enabled dynamic interface behavior. PHP handled server-side requests.
MySQL stored project records. Python implemented AI components with NLTK.

Presentation of the New System
Screens were presented.
"""
    await pipeline.ingest_training(
        TrainingIngestRequest(
            user_id="test",
            content=report,
            source_trust=0.94,
            domain_hint="project_report",
        )
    )

    definition = await pipeline.run(PipelineRequest(user_id="test", query="AUCA means?"))
    assert "AUCA means Adventist University of Central Africa" in definition.response

    overview = await pipeline.run(PipelineRequest(user_id="test", query="Final Year Project ?"))
    assert "The project title is Design and Implementation" in overview.response

    title = await pipeline.run(PipelineRequest(user_id="test", query="What is the title of the project?"))
    assert "The project title is Design and Implementation" in title.response

    case_study = await pipeline.run(PipelineRequest(user_id="test", query="What company is used as the case study?"))
    assert "The case study is Jimstech Innovations Nigeria Limited" in case_study.response

    objectives = await pipeline.run(PipelineRequest(user_id="test", query="What are the specific objectives of the study?"))
    assert "Objective: To analyze the existing manual proposal preparation" in objectives.response
    assert objectives.sources

    modules = await pipeline.run(PipelineRequest(user_id="test", query="What modules are in the scope of the project?"))
    assert "Module: Requirement Analysis Module" in modules.response
    assert "Module: Cost Estimation Module" in modules.response

    technologies = await pipeline.run(PipelineRequest(user_id="test", query="What technologies were used?"))
    assert "Technology used: MySQL" in technologies.response
    assert "Technology used: PHP" in technologies.response
    assert technologies.ir.target_ir == "WORKSPACE_QUERY"


@pytest.mark.asyncio
async def test_groq_ingestion_overlay_creates_structured_memory():
    pipeline = JimsAIPipeline()
    pipeline.bridge.extract_ingestion_memory = _fake_ingest_overlay
    ingest = await pipeline.ingest_training(
        TrainingIngestRequest(
            user_id="test",
            content="Project Title\n\nJohn Doe",
            source_trust=0.9,
            domain_hint="document_training",
        )
    )

    relations = {(relation.subject, relation.predicate, relation.object) for relation in ingest.signature.structured.relations}
    assert ingest.signature.metadata["document_type"] == "academic_project"
    assert ingest.signature.metadata["title"] == "Project Title"
    assert ("Project Title", "has_author", "John Doe") in relations
    assert ingest.signature.metadata["groq_ingestion"]["vectors_are_truth"] is False


@pytest.mark.asyncio
async def test_memory_delete_and_update_remove_old_graph_edges():
    pipeline = JimsAIPipeline()
    ingest = await pipeline.ingest_training(
        TrainingIngestRequest(
            user_id="test",
            content="WrongName causes BadOutcome.",
            source_trust=0.9,
            domain_hint="correction_training",
        )
    )
    signature_id = ingest.signature.id
    assert pipeline.graph.outgoing_edges("WrongName")

    update = await pipeline.update_memory(
        MemoryUpdateRequest(
            user_id="test",
            signature_id=signature_id,
            corrected_content="CorrectName causes GoodOutcome.",
            source_trust=0.95,
        )
    )
    assert update.accepted
    assert update.replacement_signature is not None
    assert pipeline.memory.get(signature_id).metadata["validity"] == "superseded"
    assert not pipeline.graph.outgoing_edges("WrongName")
    assert pipeline.graph.outgoing_edges("CorrectName")

    delete = await pipeline.delete_memory(MemoryDeleteRequest(user_id="test", signature_id=update.replacement_signature.id))
    assert delete.accepted
    assert not pipeline.memory.get(update.replacement_signature.id)
    assert not pipeline.graph.outgoing_edges("CorrectName")


@pytest.mark.asyncio
async def test_memory_delete_removes_signature_from_training_panels():
    pipeline = JimsAIPipeline()
    ingest = await pipeline.ingest_training(
        TrainingIngestRequest(
            user_id="test",
            content="DeletePanelSource depends on DeletePanelTarget. DeletePanelTarget.drift causes DeletePanelSource.review.",
            source_trust=0.62,
            domain_hint="delete_panel_training",
        )
    )
    signature_id = ingest.signature.id
    assert any(item.title == signature_id for item in (await pipeline.training_panel_page("memory", limit=20)).items)
    assert any(
        item.data.get("signature", {}).get("id") == signature_id
        for item in (await pipeline.training_panel_page("ingestion", limit=20)).items
    )
    assert any(
        item.data.get("provenance") == signature_id
        for item in (await pipeline.training_panel_page("world-model", limit=20)).items
    )

    delete = await pipeline.delete_memory(MemoryDeleteRequest(user_id="test", signature_id=signature_id))

    assert delete.accepted
    for panel in ("memory", "ingestion", "review", "world-model"):
        page = await pipeline.training_panel_page(panel, limit=20)
        assert all(item.title != signature_id for item in page.items)
        assert all(item.data.get("provenance") != signature_id for item in page.items)
        assert all(item.data.get("signature", {}).get("id") != signature_id for item in page.items)


@pytest.mark.asyncio
async def test_user_profile_training_answers_back_from_memory():
    pipeline = JimsAIPipeline()
    user_id = "supabase:test-ajibew"
    workspace_id = "workspace:test-ajibew"
    await pipeline.ingest_training(
        TrainingIngestRequest(
            user_id=user_id,
            workspace_id=workspace_id,
            content=(
                "User profile: My name is Ajibew Irekanmi. "
                "I am a software engineer. "
                "I am building JIMS-AI as a memory-centric AI system."
            ),
            source_trust=0.98,
            domain_hint="user_profile_training",
        )
    )

    name = await pipeline.run(PipelineRequest(user_id=user_id, workspace_id=workspace_id, query="What is my name?"))
    profile = await pipeline.run(PipelineRequest(user_id=user_id, workspace_id=workspace_id, query="What do you know about me?"))

    assert "Ajibew Irekanmi" in name.response
    assert "Here's what I can verify from memory" in name.response
    assert name.sources
    assert "software engineer" in profile.response
    assert "JIMS-AI" in profile.response
