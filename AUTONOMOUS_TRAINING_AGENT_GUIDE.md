# Autonomous Training Agent System

## Overview

The Autonomous Training Agent is a production-ready system for massive data ingestion at scale, with automatic quality management and continuous improvement.

**Key Principle**: Automated workers handle volume work (mechanical, rule-based processing). Human reviewers handle quality work (judgment, expertise, corrections). They complement each other perfectly.

## Architecture

### Core Components

1. **Autonomous Agent Loop** (`autonomous_training_agent.py`)
   - Runs continuous cycle indefinitely
   - Only stops for human approval gate
   - Orchestrates 11-step training loop

2. **Data Source Manager** (`data_source_connectors.py`)
   - Wikipedia (6M+ articles, 7 languages)
   - OpenSubtitles (50M+ multilingual subtitles)
   - User Interactions (real system usage)
   - Synthetic Generation (Groq-generated fallback)

3. **Ingestion Worker Pool** (`ingestion_worker_pool.py`)
   - Parallel document processing (8 workers default)
   - Mechanical, deterministic operations:
     - Unicode normalization (NFKC)
     - Multilingual embedding generation
     - Entity and relation extraction
     - Semantic IR construction
     - Signature creation
     - SPPE pair generation
     - World model candidate creation

4. **Training UI Bridge** (`training_ui_bridge.py`)
   - Routes work: auto-accept vs. human review
   - High confidence (>90%) → auto-accepted
   - Medium confidence (65-90%) → human review queue
   - Low confidence (<65%) → correction signals
   - Collects human decisions as training signals

5. **Metrics Reporter** (`metrics_reporter.py`)
   - Tracks system metrics across cycles
   - Generates improvement reports (directive format)
   - Identifies trends and recommendations

6. **Agent Orchestrator** (`agent_orchestrator.py`)
   - Initializes all components
   - Manages lifecycle
   - Handles graceful shutdown

## The Continuous Loop

```
FIND DATA
    ↓
Agent scans configured data sources:
- Public datasets (Wikipedia, OpenSubtitles)
- Web crawl (approved domains)
- User interactions (deployed system)
- Synthetic generation (Groq when needed)
    ↓
INGEST
    ↓
Parallel workers process documents:
- Unicode normalization
- Multilingual embedding
- Entity/relation extraction
- IR construction
- Graph updates
- Signature storage
    ↓
EVALUATE
    ↓
Agent measures current state:
- Intent Stability Scores (per language)
- Provider dependency rate
- Retrieval accuracy
- World model confidence distribution
- Review queue depth
    ↓
IDENTIFY GAPS
    ↓
Agent finds what is weak:
- Which domains have thin world models?
- Which language variants below threshold?
- Which capability classes low completion?
- Which intent paths still require providers?
    ↓
TARGET INGESTION
    ↓
Agent prioritizes data addressing gaps:
- Thin on Yoruba → source Yoruba text
- Thin on medical → ingest medical literature
- Thin on creative → ingest diverse fiction
    ↓
GENERATE TRAINING SIGNAL
    ↓
From every ingestion:
- SPPE training pairs generated automatically
- World model candidates with confidence scores
- High confidence → auto-accept
- Medium confidence → human review queue
- Low confidence → reject with correction signal
    ↓
TRAIN
    ↓
When batch thresholds reached:
- Package SPPE training pairs for Kaggle
- Upload dataset
- Trigger training run
- Validate output weights
- Stage for human approval
    ↓
HUMAN GATE (the only non-autonomous step)
    ↓
Human approves weight activation
- This gate never goes away
- Everything else fully autonomous
- Requires human judgment
    ↓
DEPLOY
    ↓
New weights hot-swapped into production
    ↓
MEASURE IMPROVEMENT
    ↓
Compare metrics before and after
Report findings in directive format
    ↓
REPEAT
```

## Separation of Concerns

### Automated Workers (Volume Work)

**What they do** (deterministic, rule-based):
- Bulk ingestion of public datasets
- Format conversion and normalization
- Entity extraction at scale
- Embedding generation (multilingual)
- Routine signature creation
- High-confidence SPPE acceptance

**What they DON'T do** (no judgment):
- Recognize subtle wrongness
- Contribute domain expertise
- Make context-dependent corrections
- Resolve ambiguities
- Approve weight activation

### Human Training UI (Quality Work)

**What they do** (requires judgment):
- Review queue processing
- Ambiguity resolution
- Quality flagging
- Domain expertise injection
- Correction of wrong signatures
- Every review decision = training signal
- Final approval of weight activation

**Benefit of this model**:
- Volume from automated workers
- Quality from human reviewers
- They complement perfectly
- System improves from both sources

## Running the Agent

### Quickstart

```bash
# Start the continuous autonomous agent
python -m prototype.jimsai.agent_orchestrator

# Run demonstration (no full loop, shows architecture)
python prototype/jimsai/agent_demo.py
```

### Configuration

```python
from prototype.jimsai.autonomous_training_agent import AutonomousAgentConfig, AutonomousTrainingAgent

config = AutonomousAgentConfig(
    # Data sources
    data_sources=["wikipedia", "opensubtitles", "user_interactions", "synthetic_generation"],
    
    # Ingestion
    parallel_workers=8,
    batch_size=100,
    max_documents_per_cycle=5000,
    
    # Evaluation thresholds
    intent_stability_min=0.85,
    provider_dependency_max=0.15,  # Max 15% provider calls
    retrieval_accuracy_min=0.80,
    world_model_confidence_min=0.75,
    
    # Gap targeting
    language_variant_threshold=0.70,
    domain_coverage_threshold=0.65,
    capability_coverage_threshold=0.70,
    
    # Training
    sppe_quality_threshold=0.80,
    auto_accept_confidence=0.90,
    human_review_confidence_range=(0.65, 0.90),
    
    # Kaggle
    sppe_batch_min=1000,
    training_interval_days=7,
    
    # Human gate
    require_human_approval=True,
    human_approval_timeout_hours=24,
)

agent = AutonomousTrainingAgent(pipeline, config)
await agent.run_continuous_loop()
```

## System State Measurement

### Core Metrics

1. **Intent Stability Score** (0-1)
   - Measures classification consistency across all languages
   - Target: ≥ 0.85
   - Below threshold → synthetic generation prioritized

2. **Provider Dependency Rate** (0-1)
   - Percentage of queries requiring provider calls
   - Target: ≤ 0.15 (15%)
   - Above threshold → world knowledge gap detected

3. **Retrieval Accuracy** (0-1)
   - Multi-index retrieval precision
   - Target: ≥ 0.80
   - Includes evidence gating validation

4. **World Model Confidence** (0-1)
   - Average confidence of causal links and relations
   - Target: ≥ 0.75
   - Low → needs more world knowledge ingestion

5. **Language Variant Scores** (dict[str, float])
   - Per-language performance
   - Target: Each ≥ 0.70
   - Weak languages → OpenSubtitles prioritized

6. **Domain Coverage** (dict[str, float])
   - Per-domain model completeness
   - Target: Each ≥ 0.65
   - Weak domains → domain-specific data prioritized

7. **Capability Coverage** (dict[str, float])
   - Per-capability task completion rates
   - Target: Each ≥ 0.70

## Training Signal Generation

### SPPE Pairs (Semantic-Phrase-Pair-Evaluation)

Quality scoring factors:
- **Semantic score** (0.25 weight): Signature confidence
- **Verification score** (0.30 weight): Entity extraction success
- **Source score** (0.20 weight): Metadata completeness
- **Gap score** (0.15 weight): Coverage of new areas
- **Efficiency score** (0.10 weight): Processing efficiency

Routing:
- Quality ≥ 0.90 → auto-accept
- Quality 0.65-0.90 → human review
- Quality < 0.65 → correction signal

### World Model Candidates

Generated from:
- Extracted causal chains (IF A THEN B)
- Entity relationships (N-way relations)
- Confidence-scored predictions

Routing: Same confidence levels as SPPE

## Integration with Training UI

The Training UI is where humans contribute quality:

```python
from prototype.jimsai.training_ui_bridge import integrate_with_training_ui

bridge = integrate_with_training_ui(pipeline)

# Get items for human review
review_queue = bridge.get_review_queue(limit=20)

# Process human decisions
await bridge.process_human_decision(
    review_item_id="sppe-xyz",
    decision="correct",
    correction={"corrected_response": "..."}
)

# Track quality metrics
stats = bridge.get_review_queue_stats()
metrics = bridge.get_quality_metrics()
```

## Improvement Reporting

Reports are generated in directive format after each deployment:

```
╒══════════════════════════════════════════════════════════════════════════════════════╕
│ IMPROVEMENT REPORT — CYCLE #42                                                       │
│ Deployment: deploy-20260531-143022                                                   │
│ Timestamp: 2026-05-31T14:30:22.123456+00:00                                          │
╚══════════════════════════════════════════════════════════════════════════════════════╛

KEY FINDINGS:
🌟 Quality Level: EXCELLENT
Overall Improvement: +3.45%

METRIC CHANGES:
Intent Stability Score ........... 0.8742 → 0.9015 📈 +0.0273
Provider Dependency Rate ........ 12.50% → 10.20% 📈 +0.0230
Retrieval Accuracy .............. 0.8100 → 0.8340 📈 +0.0240
World Model Confidence .......... 0.7245 → 0.7612 📈 +0.0367

DIRECTIVES FOR NEXT CYCLE:
1. 📍 Language coverage gaps: ar, yo. Prioritize OpenSubtitles ingestion for these languages.
2. ✅ System metrics healthy. Continue current ingestion strategy.
3. 🎯 Focus: Yoruba and Arabic expansion (currently <50% coverage).
```

## Data Source Details

### Wikipedia Connector
- Fetches random Wikipedia articles
- Supports 7 languages: en, es, fr, de, ar, yo, zh
- Rate-limited to prevent abuse
- 6M+ articles available

### OpenSubtitles Connector
- Multilingual subtitle content
- 50M+ subtitle files
- Natural dialogue and conversational patterns
- 6 languages: en, es, fr, de, ar, yo

### User Interactions Connector
- Real usage from deployed system
- Highest priority (user-validated)
- Includes feedback and corrections
- Automatic error signals

### Synthetic Generation Connector
- Groq API integration
- Fallback when coverage gaps detected
- Configurable prompt templates
- Safety-reviewed generation

## Performance Characteristics

- **Processing latency**: ~100-150ms per document (with parallelization)
- **Ingestion throughput**: 50-100 docs/second (with 8 workers)
- **Memory overhead**: Minimal (streaming + batching)
- **Scalability**: Linear with worker count (up to 64 recommended)
- **Storage**: Supabase signatures + R2 artifacts + Neo4j graph

## Monitoring and Logging

Agent logs to:
- Console (INFO level)
- File: `autonomous_agent.log`
- Event store (via AuditEventStore)

Key event types:
- `agent_cycle_complete` - Cycle finished successfully
- `agent_cycle_error` - Error during cycle (continues)
- `agent_find_data_sources` - Data sources located
- `agent_ingest_batch` - Batch ingestion complete
- `agent_identify_gaps` - Gaps detected
- `sppe_queued_for_review` - Item queued for human review
- `human_review_decision` - Human made decision
- `metrics_snapshot` - System state recorded

## Failure Recovery

The agent is designed for resilience:

1. **Per-cycle error handling**
   - Document processing errors don't stop the cycle
   - Failed documents logged with retry flag
   - Cycle continues with partial results

2. **Connector failures**
   - Individual data source failures don't stop agent
   - Connector marked inactive
   - Agent continues with other sources

3. **Deployment failures**
   - New weights don't deploy if validation fails
   - Previous weights remain active
   - Cycle completes with error logged

4. **Human gate timeout**
   - If human doesn't approve within timeout
   - Agent cycles but doesn't deploy
   - Weights staged and ready

## Future Enhancements

1. **Adaptive ingestion**
   - Dynamic worker allocation based on throughput
   - Priority-based queue management
   - Real-time gap detection

2. **Multi-deployment**
   - Canary deployments with traffic splitting
   - A/B testing of weights
   - Gradual rollout strategy

3. **Advanced metrics**
   - Per-user language variant tracking
   - Domain-specific accuracy metrics
   - Capability maturity scoring

4. **Human feedback integration**
   - Direct correction UI
   - Explanation interface
   - Domain expert certification

5. **Cost optimization**
   - Kaggle training cost tracking
   - Data source efficiency metrics
   - ROI analysis per data source

## Troubleshooting

### Agent not finding data sources

```python
# Check data source connectivity
manager = orchestrator.data_source_manager
for name, active in manager.active.items():
    print(f"{name}: {'✅ Connected' if active else '❌ Not connected'}")
```

### SPPE pairs not being generated

Check:
- Ingestion worker output (logs should show "Processed X docs")
- Confidence thresholds in config
- Memory system for storage issues

### Human gate timeout

Check:
- Training UI for pending approvals
- Review queue status: `bridge.get_review_queue_stats()`
- Timeout setting in AutonomousAgentConfig

### Provider dependency not decreasing

Indicates:
- World model too sparse
- Need more domain-specific data
- Causal chain extraction needs tuning

Strategy:
- Increase Wikipedia ingestion
- Target specific weak domains
- Review human corrections for patterns

## Integration with Existing Systems

The agent integrates seamlessly:

```python
# From main pipeline
pipeline = JimsAIPipeline()

# Create agent
agent = AutonomousTrainingAgent(pipeline, config)

# Or use orchestrator
orchestrator = AgentOrchestrator(config)
await orchestrator.initialize()

# Agent uses pipeline's:
# - Memory system (4-layer architecture)
# - Retrieval engine (multi-index)
# - Encoder (dual representation)
# - Graph (Neo4j causal links)
# - Event store (audit trail)

# Agent produces:
# - Memory signatures (stored in pipeline.memory)
# - SPPE pairs (for training)
# - Training batches (for Kaggle)
# - Metrics (for dashboards)
```

## Production Readiness Checklist

- ✅ Continuous loop implementation
- ✅ Parallel ingestion with worker pool
- ✅ Multiple data sources (4 types)
- ✅ Automatic gap detection
- ✅ Quality-based routing (auto/review/reject)
- ✅ Human approval gate
- ✅ Metrics collection and reporting
- ✅ Error recovery and resilience
- ✅ Graceful shutdown
- ✅ Comprehensive logging
- ⬜ Canary deployment (future)
- ⬜ A/B testing (future)
- ⬜ Cost tracking dashboard (future)
- ⬜ Advanced ML-based routing (future)

## Support

For issues or questions:
1. Check logs: `autonomous_agent.log`
2. Review event store: `AuditEventStore` records
3. Check metrics: `MetricsCollector.snapshots`
4. Inspect review queue: `TrainingUIBridge.review_queue`
5. Consult Architecture Guide: `docs/Jims_AI_v9.md`
