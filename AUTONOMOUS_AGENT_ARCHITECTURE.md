# Autonomous Training Agent - Complete Architecture

## System Overview

The Autonomous Training Agent is a continuous learning system that ingests data at scale, generates training signals, and improves the JimsAI system without human involvement except for quality decisions.

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                    AUTONOMOUS TRAINING AGENT SYSTEM                                 │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                    11-STEP CONTINUOUS LOOP                                  │   │
│  │                                                                             │   │
│  │  1. FIND DATA (Wikipedia, OpenSubtitles, User Interactions, Synthetic)    │   │
│  │     ↓                                                                       │   │
│  │  2. INGEST (Parallel workers: 8 workers × 100 docs/batch)                │   │
│  │     ↓                                                                       │   │
│  │  3. EVALUATE (System state measurement)                                    │   │
│  │     ↓                                                                       │   │
│  │  4. IDENTIFY GAPS (Languages, domains, capabilities, provider deps)      │   │
│  │     ↓                                                                       │   │
│  │  5. TARGET INGESTION (Prioritize data by gaps)                            │   │
│  │     ↓                                                                       │   │
│  │  6. GENERATE TRAINING SIGNAL (SPPE pairs + world models)                 │   │
│  │     ↓                                                                       │   │
│  │  7. TRAIN (Batch when threshold reached)                                   │   │
│  │     ↓                                                                       │   │
│  │  8. HUMAN GATE (Only non-autonomous: human approves weights)              │   │
│  │     ↓                                                                       │   │
│  │  9. DEPLOY (Hot-swap new weights)                                          │   │
│  │     ↓                                                                       │   │
│  │  10. MEASURE IMPROVEMENT (Compare metrics)                                 │   │
│  │     ↓                                                                       │   │
│  │  11. REPEAT                                                                │   │
│  │                                                                             │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  Runs indefinitely. Only stops for human approval gate or external signal.        │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

## Component Architecture

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│                           AUTONOMOU TRAINING AGENT                                 │
│                                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────────┐      │
│  │ agent_orchestrator.py - AgentOrchestrator                              │      │
│  │   • Initializes all components                                         │      │
│  │   • Manages lifecycle                                                  │      │
│  │   • Handles shutdown signals                                           │      │
│  │   • Routes to agent loop                                               │      │
│  └─────────────────────────────────────────────────────────────────────────┘      │
│                                 ↓                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────┐      │
│  │ autonomous_training_agent.py - AutonomousTrainingAgent                 │      │
│  │   • Main loop orchestration (11 steps)                                  │      │
│  │   • Cycle management (continuous/indefinite)                           │      │
│  │   • Gap detection and prioritization logic                             │      │
│  │   • Human gate waiting logic                                           │      │
│  │   • Event logging (AuditEventStore)                                    │      │
│  └─────────────────────────────────────────────────────────────────────────┘      │
│         ↓              ↓              ↓               ↓                ↓            │
│         │              │              │               │                │            │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────┐ ┌──────────┐ ┌─────────────┐  │
│  │   DATA       │ │  INGESTION   │ │ METRICS &  │ │TRAINING  │ │ TRAINING UI │  │
│  │  SOURCE      │ │  WORKER POOL │ │ EVALUATION │ │ SIGNAL   │ │ BRIDGE      │  │
│  │  MANAGER     │ │              │ │ ENGINE     │ │ GENERATOR│ │             │  │
│  └──────────────┘ └──────────────┘ └────────────┘ └──────────┘ └─────────────┘  │
│                                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────────┐      │
│  │                        PIPELINE (JimsAIPipeline)                        │      │
│  │                                                                         │      │
│  │  • 14+ processing layers (T1, L1-L9, T2, V9)                          │      │
│  │  • 4-layer memory system (sensory/working/episodic/semantic)          │      │
│  │  • Multi-index retrieval engine (6+ scoring signals)                  │      │
│  │  • Neo4j causal graph                                                  │      │
│  │  • Redis cache                                                         │      │
│  │  • Encoder (dual representation)                                       │      │
│  │  • Event store (Supabase)                                              │      │
│  └─────────────────────────────────────────────────────────────────────────┘      │
│                                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────────┐      │
│  │                      CLOUD PROVIDERS (All Connected)                    │      │
│  │                                                                         │      │
│  │  • Groq API (llama-3.1-8b-instant, semantic generation)              │      │
│  │  • Supabase (PostgreSQL, event store, auth)                          │      │
│  │  • Neo4j AuraDB (knowledge graph, causal links)                      │      │
│  │  • Redis Cloud (caching, sessions)                                    │      │
│  │  • Cloudflare R2 (object storage, artifacts)                         │      │
│  │  • Vectorize (384-dim embeddings)                                     │      │
│  │  • Kaggle API (training data, datasets)                               │      │
│  │                                                                         │      │
│  └─────────────────────────────────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow in Detail

### Step 1-2: FIND DATA → INGEST

```
DATA SOURCES
    ↓
┌─────────────────────────────────────────────┐
│ Wikipedia Connector                         │
│  • 6M+ articles (en, es, fr, de, ar, yo, zh) │
│  • Random article fetching                   │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ OpenSubtitles Connector                     │
│  • 50M+ subtitle files                       │
│  • Natural dialogue, multilingual            │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ User Interactions Connector                 │
│  • Real system usage (highest priority)      │
│  • Feedback + corrections                    │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ Synthetic Generation Connector              │
│  • Groq-generated fallback data              │
│  • Used when coverage gaps detected          │
└─────────────────────────────────────────────┘
         ↓
┌────────────────────────────────────────────────────────────┐
│            DataSourceManager (async, parallel)            │
│  • Manages all connectors                                 │
│  • Fetches documents asynchronously                       │
│  • Rate limiting and error recovery                       │
└────────────────────────────────────────────────────────────┘
         ↓ (batch of 500 docs)
┌────────────────────────────────────────────────────────────┐
│         IngestionWorkerPool (8 parallel workers)          │
│                                                            │
│  Worker 1  Worker 2  Worker 3 ... Worker 8               │
│     ↓         ↓        ↓              ↓                   │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ Processing Pipeline (per document):                │ │
│  │  1. Unicode normalization (NFKC)                  │ │
│  │  2. Language detection                            │ │
│  │  3. Entity extraction                             │ │
│  │  4. Relation extraction                           │ │
│  │  5. Causal chain extraction                       │ │
│  │  6. Semantic IR compilation                       │ │
│  │  7. Embedding generation (multilingual)           │ │
│  │  8. Signature creation (confidence-scored)        │ │
│  │  9. SPPE pair generation                          │ │
│  │  10. World model candidate generation             │ │
│  └─────────────────────────────────────────────────────┘ │
│                     ↓                                    │
│         IngestionResult (per document):                 │
│  • success: bool                                        │
│  • signature_id: str                                    │
│  • sppe_pair_id: str | None                            │
│  • world_model_candidates: int                         │
│  • processing_time_ms: float                           │
│                     ↓                                    │
│         Results aggregation:                           │
│  • total_documents: int                                │
│  • signatures_created: int                             │
│  • sppe_pairs_generated: int                           │
│  • world_model_candidates: int                         │
└────────────────────────────────────────────────────────────┘
         ↓
PIPELINE STORAGE:
  • Memory system (MemorySignature objects)
  • Neo4j graph (causal links)
  • Training accumulator (SPPE pairs)
```

### Step 3: EVALUATE

```
MEASUREMENT TARGETS
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Intent Stability Score (0-1)                               │
│   • Classification consistency across all languages         │
│   • T1 transformer repeated input tests                     │
│   • Target: ≥ 0.85                                          │
│   • Below: synthetic generation prioritized                 │
│                                                             │
│ Provider Dependency Rate (0-1)                             │
│   • % queries requiring provider calls                      │
│   • Groq latency tracking                                   │
│   • Target: ≤ 0.15 (15%)                                   │
│   • Above: world knowledge gap detected                     │
│                                                             │
│ Retrieval Accuracy (0-1)                                   │
│   • Multi-index retrieval precision                        │
│   • Evidence gating validation                             │
│   • Target: ≥ 0.80                                         │
│   • Impact: memory system quality                          │
│                                                             │
│ World Model Confidence (0-1)                               │
│   • Average confidence of causal links                     │
│   • Distribution across predicates                         │
│   • Target: ≥ 0.75                                         │
│   • Low: more world knowledge needed                       │
│                                                             │
│ Language Variant Scores (dict[str, float])                │
│   • Per-language performance                               │
│   • Target: Each ≥ 0.70                                    │
│   • Below: OpenSubtitles prioritized                       │
│                                                             │
│ Domain Coverage (dict[str, float])                         │
│   • Per-domain model completeness                          │
│   • Target: Each ≥ 0.65                                    │
│   • Below: domain-specific data prioritized                │
│                                                             │
│ Capability Coverage (dict[str, float])                     │
│   • Per-capability task completion                         │
│   • 9 types: MEMORY_CHAT, WORLD_KNOWLEDGE, CODING, etc.  │
│   • Target: Each ≥ 0.70                                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
         ↓
SystemState object created with all metrics
```

### Step 4-5: IDENTIFY GAPS → TARGET INGESTION

```
IDENTIFY GAPS LOGIC
    ↓
┌──────────────────────────────────────────┐
│ For each metric below threshold:         │
│   → Create IdentifiedGap object          │
│   → Assign priority (1-10)               │
│   → Suggest data source                  │
│   → Estimate docs needed                 │
└──────────────────────────────────────────┘
    ↓
EXAMPLE GAPS DETECTED:
    ├─ Language: Yoruba (0.45 < 0.70) → OpenSubtitles, 500 docs, priority 7
    ├─ Domain: Medical (0.62 < 0.65) → Wikipedia, 1000 docs, priority 6
    ├─ Provider Dep: Rate 14.5% < 15% → Wikipedia, 2000 docs, priority 9
    └─ Capability: Creative (0.65 < 0.70) → Synthetic, 500 docs, priority 5
    ↓
TARGETING PLAN CREATION
    ↓
┌────────────────────────────────────────────────────────────┐
│ Aggregate gaps by source, sort by priority                │
│                                                            │
│ 1. OpenSubtitles                                          │
│    • Address: Yoruba, Arabic language gaps               │
│    • Priority: 7                                          │
│    • Estimated docs: 1500                                │
│                                                            │
│ 2. Wikipedia                                              │
│    • Address: Medical domain, provider dependency        │
│    • Priority: 8                                          │
│    • Estimated docs: 3000                                │
│                                                            │
│ 3. Synthetic Generation                                  │
│    • Address: Creative writing capability               │
│    • Priority: 5                                          │
│    • Estimated docs: 500                                 │
│                                                            │
└────────────────────────────────────────────────────────────┘
    ↓
NEXT CYCLE: Fetch from these sources in priority order
```

### Step 6: GENERATE TRAINING SIGNAL

```
DOCUMENT PROCESSING OUTPUT
    ↓
For each SPPE pair:
    ├─ Quality scoring (composite):
    │  ├─ Semantic score (confidence) .... 0.25 weight
    │  ├─ Verification score (entities) . 0.30 weight
    │  ├─ Source score (metadata) ....... 0.20 weight
    │  ├─ Gap score (novelty) ........... 0.15 weight
    │  └─ Efficiency score .............. 0.10 weight
    │     → Quality score (0-1)
    │
    └─ ROUTING:
       ├─ If quality ≥ 0.90 → AUTO-ACCEPT (add to training)
       ├─ If 0.65 ≤ quality < 0.90 → HUMAN REVIEW QUEUE
       └─ If quality < 0.65 → CORRECTION SIGNAL
    ↓
For each World Model Candidate:
    ├─ Confidence scoring based on:
    │  ├─ Causal link evidence
    │  ├─ Entity relationship strength
    │  └─ Historical accuracy
    │
    └─ ROUTING (same thresholds)
    ↓
TRAINING SIGNAL SUMMARY:
    • SPPE pairs ready: 4500
    • Auto-accept (>90%): 2250 (50%)
    • Human review (65-90%): 1575 (35%)
    • Correction signal (<65%): 675 (15%)
    • World model candidates: 1800
```

### Step 7: TRAIN (when batch ready)

```
BATCH THRESHOLD CHECK:
    ├─ SPPE pairs: 4500 ≥ 1000? ✅ YES
    ├─ Quality avg: 0.84 ≥ 0.80? ✅ YES
    ├─ Training interval: 5 days < 7 days → OK
    ├─ High-quality ratio: 0.85 ≥ 0.70? ✅ YES
    └─ → READY TO TRAIN
    ↓
PREPARE FOR KAGGLE:
    ├─ Package SPPE pairs (4500)
    ├─ Calculate quality metrics:
    │  ├─ Average quality: 0.84
    │  ├─ Metadata completeness: 0.95
    │  └─ Entity coverage: 0.92
    ├─ Generate dataset manifest
    ├─ Create training notebook
    └─ Package artifacts
    ↓
KAGGLE TRAINING BATCH:
    • Dataset ID: jimsai-training-20260531-143022
    • SPPE pairs: 4500
    • World model candidates: 1800
    • Average quality: 0.84
    • Auto-accepted: 2250
    • Human-reviewed: 1575
    • Correction signals: 675
    ↓
WAIT FOR HUMAN APPROVAL (Step 8)
```

### Step 8: HUMAN GATE (Only Non-Autonomous Step)

```
HUMAN REVIEW QUEUE (from Training UI)
    ↓
Humans access Training UI:
    ├─ View 1575 items awaiting review
    │  ├─ SPPE pairs (ambiguous)
    │  ├─ World model candidates (uncertain)
    │  └─ Correction signals (flagged)
    │
    └─ For each item:
       ├─ Review content
       ├─ Make decision:
       │  ├─ "accept" → add to training
       │  ├─ "reject" → negative signal
       │  └─ "correct" → corrections as signal
       └─ Inject domain expertise
    ↓
RESULTS FEED BACK:
    ├─ Quality metrics updated
    ├─ Patterns identified
    └─ Training data refined
    ↓
HUMAN APPROVES WEIGHT ACTIVATION:
    • Manual approval of Kaggle training output
    • Check performance gains
    • Accept/reject deployment
    ↓
IF APPROVED:
    → Continue to Step 9 (Deploy)
   
IF REJECTED:
    → Weights staged but not deployed
    → Cycle repeats (find data, ingest, evaluate, ...)
```

### Step 9-10: DEPLOY → MEASURE

```
WEIGHT DEPLOYMENT:
    ├─ Retrieve trained weights from Kaggle
    ├─ Validate weight shapes and ranges
    ├─ Hot-swap into production layers:
    │  ├─ T1 transformer (intent classification)
    │  ├─ Encoder layers (representations)
    │  ├─ Retrieval engine (scoring)
    │  └─ T2 transformer (rendering)
    │
    └─ Zero-downtime update (no service interruption)
    ↓
IMMEDIATE METRICS COLLECTION:
    ├─ Sample 100 queries on new weights
    ├─ Measure:
    │  ├─ Intent stability (consistency)
    │  ├─ Provider dependency (% calls)
    │  ├─ Retrieval accuracy (precision)
    │  ├─ World model confidence (causal)
    │  └─ Response time (latency)
    │
    └─ Create "after" SystemState
    ↓
IMPROVEMENT COMPUTATION:
    ├─ Compare before vs after
    ├─ Calculate deltas for each metric
    ├─ Compute overall improvement %
    ├─ Assess quality level:
    │  ├─ > 5.0% → EXCELLENT 🌟
    │  ├─ > 2.0% → GOOD ✅
    │  ├─ > 0.5% → LOW ⚠️
    │  └─ ≤ 0.5% → CRITICAL 🔴
    │
    └─ Generate recommendations
    ↓
IMPROVEMENT REPORT GENERATED:
    
    ╒═══════════════════════════════════╕
    │ CYCLE #42 IMPROVEMENT REPORT     │
    │                                   │
    │ 🌟 EXCELLENT - 3.45% improvement │
    │                                   │
    │ Intent Stability                 │
    │   0.8742 → 0.9015 📈 +0.0273    │
    │                                   │
    │ Provider Dependency              │
    │   12.50% → 10.20% 📈 +2.30%    │
    │                                   │
    │ Retrieval Accuracy               │
    │   0.8100 → 0.8340 📈 +0.0240   │
    │                                   │
    │ World Model Confidence           │
    │   0.7245 → 0.7612 📈 +0.0367   │
    │                                   │
    │ DIRECTIVES FOR NEXT CYCLE:       │
    │ 1. Language coverage gaps: ar, yo│
    │    Prioritize OpenSubtitles      │
    │ 2. Continue current strategy     │
    │ 3. Focus: Yoruba, Arabic expand. │
    ╒═══════════════════════════════════╛
```

## Human Training UI Integration

The Training UI is where humans handle quality:

```
┌───────────────────────────────────────────────────────────┐
│              HUMAN TRAINING UI                            │
│                                                           │
│  REVIEW QUEUE (populated by autonomous agent)           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ Item 1: SPPE Pair (confidence: 0.78)               │ │
│  │  Query: "What is renewable energy?"                │ │
│  │  Response: "Renewable energy is..."                │ │
│  │  Decision: [Accept] [Reject] [Correct]            │ │
│  │                                                    │ │
│  │ Item 2: World Model (confidence: 0.72)            │ │
│  │  Cause: "High temperature"                        │ │
│  │  Effect: "Faster chemical reaction"               │ │
│  │  Decision: [Accept] [Reject] [Correct]            │ │
│  │                                                    │ │
│  │ Item 3: Correction Signal                         │ │
│  │  Issue: "Wrong domain association"                │ │
│  │  Fix: [Provide correction]                        │ │
│  │                                                    │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                           │
│  HUMAN DECISIONS FEED BACK:                            │
│  ├─ Accepted items → Training data                     │
│  ├─ Rejected items → Negative signals                  │
│  ├─ Corrected items → Learning signals                │
│  └─ All decisions tracked for metrics                  │
│                                                           │
│  WEIGHT APPROVAL:                                       │
│  ├─ Review proposed training results                   │
│  ├─ Check improvement metrics                          │
│  └─ [Approve Weights] [Reject and Retry]              │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

## Quality Metrics from Human Reviews

The system tracks:

```
REVIEW QUEUE STATS:
  • Total pending: 1575 items
  • SPPE pairs: 1200
  • World model candidates: 300
  • Correction signals: 75
  • Average confidence: 0.78

QUALITY METRICS (from human decisions):
  • Total reviewed: 1500
  • Acceptance rate: 85%
  • Rejection rate: 10%
  • Correction rate: 5%
  • Corrections collected: 75
  • Average human processing time: 2 min/item
```

## Event Stream

The system logs all activities:

```
EVENT STORE (AuditEventStore)
    │
    ├─ agent_find_data_sources
    │   └─ Found 4 sources, 56M estimated documents
    │
    ├─ agent_ingest_batch
    │   ├─ Total documents: 500
    │   ├─ Signatures created: 475
    │   ├─ SPPE pairs generated: 425
    │   └─ World model candidates: 200
    │
    ├─ agent_identify_gaps
    │   ├─ Gaps identified: 8
    │   └─ High priority: 2
    │
    ├─ sppe_queued_for_review
    │   └─ 42 items queued (confidence: 0.78 avg)
    │
    ├─ human_review_decision
    │   ├─ Accepted: 35
    │   ├─ Rejected: 4
    │   └─ Corrected: 3
    │
    ├─ agent_cycle_complete
    │   └─ Cycle #42 completed in 45 seconds
    │
    └─ metrics_snapshot
        └─ System state recorded
```

## Deployment Topology

```
                    JIMS-AI DEPLOYED SYSTEM
                            ↑
                            │ HTTP/REST
                            │
        ┌───────────────────┴───────────────────┐
        │                                       │
    ┌─────────┐                         ┌──────────────┐
    │ Frontend│                         │ Training UI  │
    │ (React) │                         │ (Human)      │
    └────┬────┘                         └──────┬───────┘
         │                                     │
         │ Next.js                             │ Reviews,
         │ Authentication                      │ Corrections,
         │ Query input                         │ Approvals
         │                                     │
         └─────────────┬───────────────────────┘
                       │
                   FastAPI
                   Port 8000
                       ↓
        ┌──────────────────────────────────────┐
        │    JimsAIPipeline (14+ layers)       │
        │                                      │
        │  T1 (Intent) → L1-L9 (Reasoning)    │
        │    → T2 (Render) → CSSE Output      │
        │                                      │
        │  4-Layer Memory System               │
        │  Multi-Index Retrieval Engine        │
        │                                      │
        └───────────────┬──────────────────────┘
                        │
        ┌───────────────┼───────────────────────┐
        │               │                       │
    ┌───┴─────┐     ┌───┴────┐         ┌────┴──────┐
    │ Groq    │     │Supabase│         │ Neo4j     │
    │ API     │     │ Postgre│         │ AuraDB    │
    │ (LLM)   │     │ SQL    │         │ (Graph)   │
    └─────────┘     └────┬───┘         └───────────┘
                         │
                    ┌────┴────┐
                    │ R2 + CDN │
                    │(Artifacts│
                    │  Cache)  │
                    └──────────┘

    ┌───────────────────────────────────────────┐
    │  AUTONOMOUS TRAINING AGENT                │
    │                                           │
    │  Runs continuously (separate process)     │
    │  • Finds data from 4 sources             │
    │  • Ingests with 8 parallel workers       │
    │  • Evaluates system state                │
    │  • Identifies gaps                       │
    │  • Targets ingestion                     │
    │  • Generates training signals            │
    │  • Trains via Kaggle                     │
    │  • Waits for human approval              │
    │  • Deploys new weights                   │
    │  • Measures improvement                  │
    │  • Loops indefinitely                    │
    │                                           │
    └───────────────────────────────────────────┘
```

## Key Design Decisions

### 1. Separation of Concerns
- **Automated workers**: No judgment, rule-based processing
- **Human reviewers**: Quality decisions, domain expertise
- **Result**: System scales volume while maintaining quality

### 2. Continuous Loop vs Batch
- **Continuous**: Agent runs indefinitely, no manual triggers
- **Batching**: Documents ingested in parallel batches of 100
- **Result**: Steady state improvement without human intervention

### 3. Confidence-Based Routing
- High confidence (>90%) → Auto-accept immediately
- Medium confidence (65-90%) → Queue for human review
- Low confidence (<65%) → Reject with correction signal
- **Result**: Human effort focused on ambiguous cases, not simple decisions

### 4. Human Approval Gate
- Only non-autonomous step: Weight activation approval
- **Why**: Safety, accountability, human oversight
- **Result**: No unwanted models deployed, humans in control

### 5. Improvement Metrics
- Directive format reports (human-readable)
- Specific recommendations for next cycle
- Tracking of trends over cycles
- **Result**: Humans understand progress and can guide strategy

## Production Readiness

✅ **READY FOR PRODUCTION**
- ✅ Continuous loop implementation
- ✅ Parallel ingestion workers
- ✅ Multiple data sources
- ✅ Automatic gap detection
- ✅ Quality-based routing
- ✅ Human approval gate
- ✅ Metrics tracking
- ✅ Error recovery
- ✅ Comprehensive logging
- ✅ Graceful shutdown

⬜ **FUTURE ENHANCEMENTS**
- Canary deployments
- A/B testing of weights
- Cost optimization
- Advanced ML-based routing
- Multi-deployment support
- ROI analysis per data source

## Getting Started

1. **Launch the agent**:
   ```bash
   python launch_autonomous_agent.py
   ```

2. **Access Training UI**:
   - Review queue of ambiguous cases
   - Make quality decisions
   - Approve weight deployments

3. **Monitor metrics**:
   - Check logs: `autonomous_agent.log`
   - View reports: Generated after each cycle
   - Track improvements: Cycle-by-cycle analysis

4. **Configure for your needs**:
   - Edit `AutonomousAgentConfig`
   - Adjust thresholds for your use case
   - Add custom data sources
   - Customize metrics

## Support

For questions or issues:
1. Check `AUTONOMOUS_TRAINING_AGENT_GUIDE.md`
2. Review event logs and metrics
3. Inspect review queue status
4. Check data source connectivity
5. Consult architecture documentation
