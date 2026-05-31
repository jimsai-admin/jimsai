# JimsAI Completion Roadmap - Phase 5: Production-Grade System

**Objective**: Build production-grade JimsAI with persistence, governance, and creative capabilities while gradually reducing transformer dependency.

**Timeline**: 6-8 weeks to MVP production deployment

---

## Phase 5 Overview

### Architecture Vision
```
User Input
  ↓
T1 (Intent Parser - Groq) - OPTIONAL, skipped when deterministic confidence high
  ↓
Semantic IR (Structured)
  ↓
L1-L4 (Deterministic Layers - Memory, Routing, Sparse Activation)
  ├─ Can now operate WITHOUT transformers for many routes
  ├─ Fallback to T1 only for ambiguous/novel cases
  └─ Specialization reduces T1 calls by 70%+
  ↓
Capability Router
  ├─ Memory Chat → Direct retrieval (no T1)
  ├─ Web Knowledge → Search + retrieval (no T1)
  ├─ Coding → Docs + sandbox (no T1)
  ├─ Math/Science → Z3 + solver (no T1)
  ├─ Creative Writing → CSSE + T2 (only if needed)
  ├─ Image Generation → Stable Diffusion (local or API)
  ├─ Video Generation → Human approval + Runway
  └─ Agentic Tasks → Approval + execution
  ↓
Persistence Layer (New)
  ├─ Event Store (PostgreSQL)
  ├─ Memory Signatures (Supabase)
  ├─ Vectors (Vectorize)
  ├─ Graphs (Neo4j)
  └─ Artifacts (R2)
  ↓
T2 (Fluency Renderer - Groq) - OPTIONAL, skipped when CSSE has high confidence
  ↓
Verified Cognitive Object
  ↓
User Output
```

**Key Innovation**: Layers 1-4 can now operate independently. T1/T2 become optional optimization tools, not required infrastructure.

---

## Phase 5 Implementation Layers

### **Layer 1: Persistence Foundation** (Weeks 1-2)

#### 1.1 Event Sourcing / CQRS Setup
```
prototype/jimsai/
  ├── events.py (Event definitions)
  ├── event_store.py (PostgreSQL append-only log)
  ├── projections.py (Read models from event stream)
  ├── sagas.py (Compensation logic)
  └── handlers.py (Event processing)
```

**Events to model**:
- `UserQueryReceived(query, workspace_id, user_id, timestamp)`
- `SemanticSignatureCreated(signature, confidence, entities, relations, causal_links)`
- `MemoryIngested(signature_id, source, freshness, vector_id)`
- `ProvenanceRecorded(input, output, provider, verification_status)`
- `HumanReviewRequested(item_id, reason, priority)`
- `HumanReviewCompleted(decision, correction, promotion_flag)`
- `SPPEPairGenerated(signal_efficiency, quality_score, training_batch_id)`
- `TrainingTriggered(artifact_type, threshold_reason, batch_size)`
- `ModelActivated(artifact_id, validation_score, rollback_metadata)`
- `CacheInvalidated(scope, reason, affected_queries)`

**Benefits**:
- Complete audit trail
- Event replay for debugging
- Temporal analysis
- Saga compensation

#### 1.2 Supabase Schema Setup
```sql
-- Events table (append-only)
CREATE TABLE events (
  id BIGSERIAL PRIMARY KEY,
  event_type TEXT NOT NULL,
  aggregate_id UUID NOT NULL,
  aggregate_type TEXT NOT NULL,
  data JSONB NOT NULL,
  metadata JSONB,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  version INT NOT NULL
);

-- Memory signatures (indexed)
CREATE TABLE memory_signatures (
  id UUID PRIMARY KEY,
  workspace_id UUID NOT NULL,
  user_id UUID,
  structured_content JSONB NOT NULL,
  vector_id TEXT,  -- Reference to Vectorize
  entities JSONB,
  relations JSONB,
  causal_links JSONB,
  source_url TEXT,
  confidence FLOAT,
  freshness_epoch INT,
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);

-- Verified results cache
CREATE TABLE verified_results (
  id UUID PRIMARY KEY,
  workspace_id UUID NOT NULL,
  query_hash TEXT NOT NULL,
  result_hash TEXT NOT NULL,
  output JSONB NOT NULL,
  confidence FLOAT,
  sources JSONB,
  gaps JSONB,
  verified_at TIMESTAMP,
  cache_hit_count INT DEFAULT 0,
  FOREIGN KEY (workspace_id) REFERENCES workspaces(id),
  UNIQUE(workspace_id, query_hash)
);

-- Human review queue
CREATE TABLE review_queue (
  id UUID PRIMARY KEY,
  workspace_id UUID NOT NULL,
  item_type TEXT,  -- memory, correction, promotion
  item_id UUID,
  priority INT,
  created_at TIMESTAMP,
  completed_at TIMESTAMP,
  reviewer_id UUID,
  decision JSONB,
  FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);

-- Workspace governance
CREATE TABLE workspace_governance (
  id UUID PRIMARY KEY,
  workspace_id UUID UNIQUE NOT NULL,
  provider_quotas JSONB,  -- DuckDuckGo calls, Docker executions, etc.
  training_budget INT,  -- Max Kaggle runs per month
  approval_thresholds JSONB,  -- Risk levels requiring approval
  audit_enabled BOOLEAN,
  data_retention_days INT,
  created_at TIMESTAMP,
  FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);
```

#### 1.3 Cloud Service Integration
**R2 (Artifacts)**:
```python
# prototype/jimsai/cloud/r2_client.py
class R2Client:
    async def store_artifact(self, artifact_type, content, workspace_id):
        """Store in R2 with workspace scoping"""
        key = f"{workspace_id}/{artifact_type}/{uuid.uuid4()}"
        await self.bucket.put(key, content, metadata={
            "workspace": workspace_id,
            "created": datetime.now().isoformat()
        })
        return key
```

**Vectorize (Embeddings)**:
```python
# prototype/jimsai/cloud/vectorize_client.py
class VectorizeClient:
    async def upsert_signature(self, signature_id, vector, metadata):
        """Store embedding with metadata"""
        await self.index.upsert(
            vectors=[{
                "id": signature_id,
                "values": vector,
                "metadata": metadata
            }]
        )
```

**Neo4j (Knowledge Graph)**:
```python
# prototype/jimsai/cloud/neo4j_client.py
class Neo4jClient:
    async def upsert_causal_graph(self, workspace_id, entities, relations):
        """Update workspace knowledge graph"""
        async with self.driver.session() as session:
            await session.run("""
                MERGE (w:Workspace {id: $workspace_id})
                FOREACH (entity IN $entities |
                    MERGE (e:Entity {id: entity.id})
                    CREATE (w)-[:CONTAINS]->(e)
                )
                FOREACH (rel IN $relations |
                    MATCH (e1:Entity {id: rel.from})
                    MATCH (e2:Entity {id: rel.to})
                    CREATE (e1)-[r:RELATION {type: rel.type}]->(e2)
                )
            """, workspace_id=workspace_id, entities=entities, relations=relations)
```

---

### **Layer 2: Full Training Loop Integration** (Weeks 2-3)

#### 2.1 SPPE Pair Pipeline
```python
# prototype/jimsai/training/sppe_generator.py
class SPPEPairGenerator:
    """Generate Structured Preference Pair Examples"""
    
    async def generate_pair(self, query, structured_ir, output, trace):
        """
        Create (Semantic IR, Preference, Output) triple
        
        Args:
            query: User input
            structured_ir: L1 semantic signature
            output: CSSE verified output
            trace: Full execution trace with confidence
        """
        # Extract preference signal
        preference = self._extract_preference(trace)
        
        # Score pair quality
        quality_score = self._score_pair(
            semantic_clarity=trace.semantic_confidence,
            output_verification=trace.verification_status,
            source_grounding=len(trace.sources),
            hallucination_risk=trace.hallucination_gaps
        )
        
        return SPPEPair(
            semantic_ir=structured_ir,
            preference=preference,
            output=output,
            quality_score=quality_score,
            provenance={
                "query": query,
                "trace": trace,
                "timestamp": datetime.now()
            }
        )
    
    def _score_pair(self, semantic_clarity, output_verification, 
                    source_grounding, hallucination_risk):
        """Quality score from 0-1"""
        score = (
            semantic_clarity * 0.3 +  # Clear intent
            output_verification * 0.3 +  # Verified output
            min(source_grounding / 3, 1.0) * 0.25 +  # Sources
            (1 - hallucination_risk) * 0.15  # No hallucinations
        )
        return score
```

#### 2.2 Training Pipeline Orchestration
```python
# prototype/jimsai/training/training_orchestrator.py
class TrainingOrchestrator:
    """Manage SPPE ingestion, batching, and Kaggle training"""
    
    async def ingest_query_result(self, query, result, trace):
        """One-shot ingestion after user query completes"""
        
        # 1. Generate SPPE pair
        pair = await self.sppe_gen.generate_pair(
            query, result.semantic_ir, result.output, trace
        )
        
        # 2. Store to training batch
        batch_id = await self.batch_store.add_pair(pair)
        
        # 3. Check auto-training threshold
        training_decision = await self._check_training_trigger(batch_id)
        if training_decision.should_train:
            await self._trigger_training(batch_id, training_decision.reason)
        
        return training_decision
    
    async def _check_training_trigger(self, batch_id):
        """Determine if model training should start"""
        batch = await self.batch_store.get_batch(batch_id)
        
        thresholds = {
            "pair_count": 1000,  # 1000 SPPE pairs
            "quality_avg": 0.80,  # Avg quality >= 0.80
            "time_window": 7 * 24 * 3600,  # 7 days
            "high_quality_ratio": 0.70,  # 70% high-quality pairs
        }
        
        triggers = []
        if len(batch.pairs) >= thresholds["pair_count"]:
            triggers.append("pair_count_reached")
        if batch.quality_avg >= thresholds["quality_avg"]:
            triggers.append("quality_threshold_met")
        if batch.age_seconds >= thresholds["time_window"]:
            triggers.append("time_window_elapsed")
        
        return TrainingDecision(
            should_train=len(triggers) >= 2,
            reason=triggers,
            requires_approval=True  # Always require human approval
        )
    
    async def _trigger_training(self, batch_id, reason):
        """Queue training job with human approval"""
        job = TrainingJob(
            batch_id=batch_id,
            reason=reason,
            status="awaiting_approval",
            artifacts_to_train=["encoder", "reranker", "world_model"],
            validation_holdout_ratio=0.2
        )
        await self.review_queue.add_item(job)
```

#### 2.3 Artifact Validation & Hot-Swap
```python
# prototype/jimsai/training/artifact_validator.py
class ArtifactValidator:
    """Validate trained artifacts before activation"""
    
    async def validate_artifact(self, artifact_type, new_artifact, holdout_data):
        """
        Test new artifact against held-out test set
        """
        
        if artifact_type == "encoder":
            return await self._validate_encoder(new_artifact, holdout_data)
        elif artifact_type == "reranker":
            return await self._validate_reranker(new_artifact, holdout_data)
        elif artifact_type == "world_model":
            return await self._validate_world_model(new_artifact, holdout_data)
    
    async def _validate_encoder(self, encoder, holdout_data):
        """Test semantic IR quality on held-out signatures"""
        scores = []
        for query, expected_signature in holdout_data:
            actual_sig = await encoder.encode(query)
            similarity = self._vector_similarity(
                actual_sig.vector, 
                expected_signature.vector
            )
            scores.append(similarity)
        
        avg_score = sum(scores) / len(scores)
        return ValidationResult(
            artifact_type="encoder",
            score=avg_score,
            passed=avg_score > 0.85,  # Must exceed 0.85
            breakdown={"vector_similarity": avg_score}
        )
    
    async def activate_artifact(self, artifact_type, artifact, validation_score):
        """Hot-swap with rollback capability"""
        
        if validation_score < 0.85:
            raise ValueError(f"Validation score {validation_score} below threshold")
        
        # Store rollback metadata
        rollback_meta = {
            "timestamp": datetime.now().isoformat(),
            "artifact_version": artifact.version,
            "validation_score": validation_score,
            "prev_artifact_id": self.current[artifact_type].id,
            "revert_command": f"restore_artifact({artifact.id})"
        }
        
        # Activate new artifact
        self.current[artifact_type] = artifact
        
        # Log event
        await self.event_store.append(ArtifactActivated(
            artifact_type=artifact_type,
            artifact_id=artifact.id,
            validation_score=validation_score,
            rollback_metadata=rollback_meta
        ))
```

---

### **Layer 3: Human Approval UI/Gates** (Weeks 3-4)

#### 3.1 Review Queue API
```python
# prototype/app.py - NEW ENDPOINTS
@app.post("/api/review-queue")
async def get_review_queue(workspace_id: str, user_id: str):
    """Paginated review queue for workspace"""
    queue = await db.review_queue.get_items(
        workspace_id=workspace_id,
        status="pending",
        limit=20
    )
    return {
        "items": queue,
        "total_pending": len(queue),
        "high_priority_count": sum(1 for i in queue if i.priority > 7)
    }

@app.post("/api/review-action")
async def submit_review(review_id: str, decision: ReviewDecision):
    """Submit human review decision"""
    # decision = {
    #   "action": "approve" | "reject" | "correct",
    #   "correction": {...}  # If correcting
    #   "feedback": "...",
    #   "reviewer_id": "...",
    #   "timestamp": "..."
    # }
    
    await event_store.append(ReviewCompleted(
        review_id=review_id,
        decision=decision
    ))
    
    # Handle compensation if needed
    if decision.action == "reject":
        await _handle_rejection(review_id)
    elif decision.action == "correct":
        await _handle_correction(review_id, decision.correction)
    
    return {"status": "completed"}

@app.post("/api/training-approval")
async def approve_training(job_id: str, reviewer_id: str):
    """Approve pending training job"""
    job = await training_orchestrator.get_job(job_id)
    await training_orchestrator.start_kaggle_job(job, reviewer_id=reviewer_id)
    return {"status": "training_started"}
```

#### 3.2 Frontend UI Components
```typescript
// frontend/app/review/ReviewQueue.tsx
export function ReviewQueue({ workspace_id }: Props) {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [selected, setSelected] = useState<ReviewItem | null>(null);

  useEffect(() => {
    const pollQueue = setInterval(async () => {
      const data = await fetch(`/api/review-queue?workspace_id=${workspace_id}`);
      setItems(await data.json());
    }, 5000);
    return () => clearInterval(pollQueue);
  }, []);

  const handleDecision = async (item: ReviewItem, decision: ReviewDecision) => {
    await fetch("/api/review-action", {
      method: "POST",
      body: JSON.stringify({ review_id: item.id, decision })
    });
    setItems(items.filter(i => i.id !== item.id));
  };

  return (
    <div className="review-queue">
      <div className="queue-list">
        {items.map(item => (
          <ReviewQueueItem
            key={item.id}
            item={item}
            selected={selected?.id === item.id}
            onClick={() => setSelected(item)}
            priority={item.priority}
          />
        ))}
      </div>
      
      {selected && (
        <div className="review-detail">
          <h3>{selected.item_type}</h3>
          <pre>{JSON.stringify(selected.content, null, 2)}</pre>
          <div className="actions">
            <button onClick={() => handleDecision(selected, { action: "approve" })}>
              ✓ Approve
            </button>
            <button onClick={() => handleDecision(selected, { action: "reject" })}>
              ✗ Reject
            </button>
            <button onClick={() => setShowCorrection(!showCorrection)}>
              ✏ Correct
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// frontend/app/training/TrainingApproval.tsx
export function TrainingApprovalPanel({ job }: Props) {
  return (
    <div className="training-approval">
      <h3>Training Job Awaiting Approval</h3>
      <div className="job-summary">
        <p>SPPE Pairs: {job.pair_count}</p>
        <p>Avg Quality: {job.quality_avg.toFixed(3)}</p>
        <p>Trigger Reasons: {job.reasons.join(", ")}</p>
        <p>Artifacts: {job.artifacts.join(", ")}</p>
      </div>
      <button onClick={() => approveTraining(job.id)}>
        Start Training
      </button>
    </div>
  );
}
```

#### 3.3 Approval Gate Configuration
```python
# prototype/jimsai/governance/approval_gates.py
class ApprovalGates:
    """Route-specific approval requirements"""
    
    APPROVAL_REQUIRED = {
        "video_generation": True,  # Always require approval
        "code_execution": "high_risk_only",  # Only risky code
        "world_model_update": "low_confidence_only",  # <0.70
        "agentic_task": "irreversible_only",  # Irreversible actions
        "training_trigger": True,  # Always manual approval
        "artifact_activation": True,  # Always human review
    }
    
    async def check_approval_required(self, action_type, context):
        """Determine if approval needed"""
        gate = self.APPROVAL_REQUIRED.get(action_type)
        
        if gate is True:
            return True, "action_type_requires_approval"
        elif gate == "high_risk_only":
            risk_score = context.get("risk_score", 0)
            return risk_score > 0.7, f"high_risk_{risk_score}"
        elif gate == "low_confidence_only":
            confidence = context.get("confidence", 1.0)
            return confidence < 0.7, f"low_confidence_{confidence}"
        elif gate == "irreversible_only":
            is_irreversible = context.get("is_irreversible", False)
            return is_irreversible, "irreversible_action"
        
        return False, None
```

---

### **Layer 4: Event Sourcing / CQRS** (Weeks 4-5)

#### 4.1 Event Store Implementation
```python
# prototype/jimsai/eventing/event_store.py
class EventStore:
    """Append-only event log with CQRS projections"""
    
    async def append(self, event: DomainEvent):
        """Write-only append"""
        payload = {
            "event_type": event.__class__.__name__,
            "aggregate_id": event.aggregate_id,
            "aggregate_type": event.aggregate_type,
            "data": event.to_dict(),
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "version": event.version
            }
        }
        
        result = await self.db.execute("""
            INSERT INTO events (
                event_type, aggregate_id, aggregate_type, 
                data, metadata, created_at, version
            ) VALUES (%s, %s, %s, %s, %s, NOW(), %s)
            RETURNING id, created_at
        """, (
            payload["event_type"],
            payload["aggregate_id"],
            payload["aggregate_type"],
            json.dumps(payload["data"]),
            json.dumps(payload["metadata"]),
            event.version
        ))
        
        # Trigger projections
        await self._process_projections(event)
        
        return result
    
    async def get_aggregate_events(self, aggregate_id, from_version=0):
        """Read event stream for aggregate"""
        events = await self.db.fetch("""
            SELECT * FROM events
            WHERE aggregate_id = %s AND version >= %s
            ORDER BY created_at ASC
        """, aggregate_id, from_version)
        
        return events
    
    async def subscribe_to_events(self, event_type, handler):
        """Subscribe handler to event type"""
        self.subscriptions[event_type].append(handler)
```

#### 4.2 Saga Orchestration
```python
# prototype/jimsai/eventing/sagas.py
class TrainingJobSaga:
    """Long-running training job with compensation"""
    
    async def handle_training_triggered(self, event: TrainingTriggered):
        """Start training saga"""
        job_id = event.job_id
        
        try:
            # Step 1: Lock SPPE batch
            await self.event_store.append(SPPEBatchLocked(job_id))
            
            # Step 2: Create training dataset
            dataset_id = await self._create_dataset(event.batch_id)
            await self.event_store.append(DatasetCreated(job_id, dataset_id))
            
            # Step 3: Request human approval
            await self.event_store.append(ApprovalRequested(job_id))
            
            # Wait for approval event
            approval = await self._wait_for_approval(job_id, timeout=48*3600)
            
            if not approval.approved:
                # Compensation: Release batch
                await self.event_store.append(SPPEBatchReleased(job_id))
                return
            
            # Step 4: Start Kaggle training
            run_id = await self._start_kaggle_run(dataset_id)
            await self.event_store.append(KaggleJobStarted(job_id, run_id))
            
            # Step 5: Wait for completion
            result = await self._wait_for_kaggle_completion(run_id)
            
            # Step 6: Validate artifacts
            validation = await self._validate_artifacts(result)
            if not validation.passed:
                # Compensation: Mark as failed
                await self.event_store.append(TrainingFailed(job_id, validation.reason))
                return
            
            # Step 7: Request activation approval
            activation_approval = await self._wait_for_activation_approval(job_id)
            if not activation_approval.approved:
                # Compensation: Keep current artifacts
                await self.event_store.append(TrainingNotActivated(job_id))
                return
            
            # Step 8: Hot-swap artifacts
            await self._activate_artifacts(result.artifacts)
            await self.event_store.append(ArtifactsActivated(job_id, result.artifacts))
            
        except Exception as e:
            await self._compensate(job_id, e)
            await self.event_store.append(SagaFailed(job_id, str(e)))
    
    async def _compensate(self, job_id, error):
        """Rollback saga steps"""
        # Release locks, cancel jobs, revert state
        pass
```

#### 4.3 Projections (Read Models)
```python
# prototype/jimsai/eventing/projections.py
class MemorySignatureProjection:
    """Read model for memory signatures"""
    
    async def project(self, event: DomainEvent):
        """Update read model from event"""
        
        if isinstance(event, SemanticSignatureCreated):
            await self.db.execute("""
                INSERT INTO memory_signatures (
                    id, workspace_id, structured_content, confidence, created_at
                ) VALUES (%s, %s, %s, %s, NOW())
            """, event.signature_id, event.workspace_id, 
                json.dumps(event.structured_ir), event.confidence)
        
        elif isinstance(event, SignatureVectorized):
            await self.db.execute("""
                UPDATE memory_signatures
                SET vector_id = %s
                WHERE id = %s
            """, event.vector_id, event.signature_id)
        
        elif isinstance(event, SignatureInvalidated):
            await self.db.execute("""
                DELETE FROM memory_signatures WHERE id = %s
            """, event.signature_id)
```

---

### **Layer 5: Creative Capabilities** (Weeks 5-6)

#### 5.1 Creative Writing Adapter
```python
# services/creative-writing/
class CreativeWritingAdapter:
    """Nuanced language, style, creative generation"""
    
    async def generate(self, request: CreativeRequest, trace: ExecutionTrace):
        """
        request = {
            "style": "poetic" | "technical" | "conversational" | "academic",
            "length": "short" | "medium" | "long",
            "mood": optional tone specification,
            "constraints": optional style rules
        }
        """
        
        # Check if T2 is actually needed
        if self._can_use_deterministic(request, trace):
            return await self._generate_deterministic(request)
        
        # Fall back to T2 for complex language
        system_prompt = self._build_style_prompt(request)
        response = await self.t2_renderer.call(
            prompt=request.prompt,
            system=system_prompt,
            temperature=0.8,  # Higher for creativity
            max_tokens=request.max_tokens
        )
        
        # CSSE verification (style bounds, no false claims)
        verified = await self.csse.verify_creative(
            response,
            style_constraints=request.constraints,
            allow_speculation=True,
            require_sourced_facts=False
        )
        
        await trace.record_step(
            step="creative_generation",
            input=request,
            output=verified,
            used_t2=True,
            confidence=verified.confidence
        )
        
        return verified
    
    def _can_use_deterministic(self, request, trace):
        """Skip T2 when deterministic confidence is high"""
        # Check if we have high-confidence memory match
        if trace.memory_confidence > 0.9 and request.style == "conversational":
            return True
        return False
    
    async def _generate_deterministic(self, request):
        """Direct memory retrieval for known patterns"""
        # Use CSSE rendering with stored style templates
        return await self.csse.render_with_style(
            request.prompt,
            style=request.style
        )
```

#### 5.2 Image Generation Adapter
```python
# services/image-generation/
class ImageGenerationAdapter:
    """Local Stable Diffusion + Runaway for video"""
    
    async def generate_image(self, prompt: str, approval_status=None):
        """
        Generate image with provenance tracking
        """
        
        # Check approval gates
        requires_approval = await self.approval_gates.check(
            "image_generation",
            context={"prompt": prompt}
        )
        
        if requires_approval and approval_status != "approved":
            await self.review_queue.add_item({
                "type": "image_generation",
                "prompt": prompt,
                "status": "awaiting_approval"
            })
            return {"status": "pending_approval"}
        
        # Generate locally (Stable Diffusion)
        try:
            image = await self.stable_diffusion.generate(
                prompt=prompt,
                steps=30,
                guidance_scale=7.5
            )
        except Exception as e:
            # Fallback to API if local fails
            image = await self.external_api.generate(prompt)
        
        # Store in R2
        image_url = await self.r2.store_artifact(
            artifact_type="image",
            content=image,
            workspace_id=self.workspace_id,
            metadata={"prompt": prompt, "model": "stable_diffusion"}
        )
        
        # Record provenance
        await self.event_store.append(ImageGenerated(
            url=image_url,
            prompt=prompt,
            model="stable_diffusion",
            timestamp=datetime.now()
        ))
        
        return {"url": image_url, "status": "generated"}
    
    async def generate_video(self, prompt: str, reviewer_id: str):
        """
        Video generation REQUIRES human approval
        """
        
        # Always send for review
        job = VideoGenerationJob(
            prompt=prompt,
            status="awaiting_approval",
            reviewer_id=None
        )
        
        await self.review_queue.add_item(job)
        
        # Wait for approval
        approval = await self._wait_for_approval(job.id, timeout=24*3600)
        
        if not approval.approved:
            return {"status": "rejected"}
        
        # Generate via Runway
        video = await self.runway_client.generate(
            prompt=prompt,
            duration=30,
            fps=24
        )
        
        video_url = await self.r2.store_artifact(
            artifact_type="video",
            content=video,
            workspace_id=self.workspace_id,
            metadata={"prompt": prompt, "approved_by": reviewer_id}
        )
        
        return {"url": video_url, "status": "generated"}
```

#### 5.3 Audio Generation Adapter
```python
# services/audio-generation/
class AudioGenerationAdapter:
    """Text-to-speech + voice generation"""
    
    async def generate_speech(self, text: str, voice_id: str):
        """TTS with voice rights verification"""
        
        # Check voice rights
        voice = await self.voice_registry.get(voice_id)
        if not voice.is_authorized:
            raise PermissionError(f"Voice {voice_id} not authorized")
        
        # Generate via ElevenLabs or local
        audio = await self.tts_engine.generate(
            text=text,
            voice_id=voice_id,
            rate=1.0
        )
        
        # Store
        audio_url = await self.r2.store_artifact(
            artifact_type="audio",
            content=audio,
            workspace_id=self.workspace_id,
            metadata={"voice": voice_id, "rights": "verified"}
        )
        
        return {"url": audio_url, "status": "generated"}
```

---

### **Layer 6: Workspace Governance** (Weeks 6-7)

#### 6.1 Provider Quota Management
```python
# prototype/jimsai/governance/quotas.py
class QuotaManager:
    """Track and enforce provider usage"""
    
    async def check_quota(self, workspace_id, provider, action):
        """Check if action exceeds quota"""
        gov = await self.db.workspace_governance.get(workspace_id)
        quota = gov.provider_quotas.get(provider, {})
        
        usage = await self._get_usage(workspace_id, provider, action)
        limit = quota.get(action, float('inf'))
        
        if usage >= limit:
            return False, f"Quota exceeded: {usage}/{limit}"
        
        return True, None
    
    async def record_usage(self, workspace_id, provider, action, cost=0):
        """Record provider usage"""
        await self.db.execute("""
            INSERT INTO provider_usage (
                workspace_id, provider, action, cost, recorded_at
            ) VALUES (%s, %s, %s, %s, NOW())
        """, workspace_id, provider, action, cost)
```

#### 6.2 Workspace Governance Config
```python
# Frontend UI for governance
class WorkspaceGovernancePanel {
  const [gov, setGov] = useState<WorkspaceGovernance | null>(null);

  const updateQuota = async (provider, action, newLimit) => {
    await fetch(`/api/workspace/${workspaceId}/governance`, {
      method: "PATCH",
      body: JSON.stringify({
        provider_quotas: {
          ...gov.provider_quotas,
          [provider]: { ...gov.provider_quotas[provider], [action]: newLimit }
        }
      })
    });
  };

  return (
    <div className="governance">
      <h3>Workspace Governance</h3>
      <div className="quotas">
        <label>DuckDuckGo Calls/Day: 
          <input value={gov?.provider_quotas.duckduckgo.calls_per_day} 
                 onChange={e => updateQuota("duckduckgo", "calls_per_day", e.target.value)} />
        </label>
        <label>Docker Executions/Hour:
          <input value={gov?.provider_quotas.docker.executions_per_hour}
                 onChange={e => updateQuota("docker", "executions_per_hour", e.target.value)} />
        </label>
        <label>Training Budget (runs/month):
          <input value={gov?.training_budget}
                 onChange={e => updateGov({...gov, training_budget: e.target.value})} />
        </label>
      </div>
      <div className="approvals">
        <h4>Approval Requirements</h4>
        <label><input type="checkbox" onChange={...} /> Video Generation</label>
        <label><input type="checkbox" onChange={...} /> Agentic Tasks</label>
        <label><input type="checkbox" onChange={...} /> Model Activation</label>
      </div>
    </div>
  );
}
```

---

### **Layer 7: Transformer Thinning Strategy** (Weeks 7-8)

#### 7.1 Adaptive T1/T2 Skipping
```python
# prototype/jimsai/optimization/transformer_thinning.py
class TransformerThinningStrategy:
    """Progressively reduce T1/T2 usage"""
    
    async def should_skip_t1(self, query, memory_confidence, route_type):
        """
        Skip T1 when deterministic confidence is high
        """
        
        # Never skip for risky/ambiguous routes
        if route_type in ["creative_writing", "novel_problem", "image_generation"]:
            return False
        
        # Skip if memory confidence is very high and not risky
        if memory_confidence > 0.9 and route_type in [
            "memory_chat", "world_knowledge", "coding", "math_science"
        ]:
            return True
        
        # Check if query is highly deterministic
        if self._is_deterministic_query(query):
            return True
        
        return False
    
    async def should_skip_t2(self, output, trace):
        """
        Skip T2 when CSSE has high-confidence sourced answer
        """
        
        # Skip if CSSE confidence is very high
        if output.confidence > 0.95 and output.sources and not output.gaps:
            return True
        
        # Skip if output is already well-formed
        if trace.route_type in ["math_science", "coding"] and output.verified:
            return True
        
        return False
    
    def _is_deterministic_query(self, query):
        """Check if query can be answered deterministically"""
        
        # Known query patterns
        deterministic_patterns = [
            r"what is \d+\s*[\+\-\*/]\s*\d+",  # Simple math
            r"define\s+\w+",  # Definitions
            r"list.*of",  # Lists
        ]
        
        for pattern in deterministic_patterns:
            if re.search(pattern, query.lower()):
                return True
        
        return False
```

#### 7.2 Metrics & Monitoring
```python
# prototype/jimsai/monitoring/metrics.py
class TransformerMetrics:
    """Track T1/T2 usage reduction"""
    
    async def record_query(self, query_id, trace):
        """Record T1/T2 usage for this query"""
        await self.db.execute("""
            INSERT INTO query_metrics (
                query_id, used_t1, used_t2, 
                memory_confidence, output_confidence,
                recorded_at
            ) VALUES (%s, %s, %s, %s, %s, NOW())
        """, query_id, trace.used_t1, trace.used_t2,
            trace.memory_confidence, trace.output_confidence)
    
    async def get_metrics(self, workspace_id, days=30):
        """Get T1/T2 reduction metrics"""
        results = await self.db.fetch("""
            SELECT 
                used_t1, used_t2,
                COUNT(*) as count,
                AVG(memory_confidence) as avg_memory_conf
            FROM query_metrics
            WHERE workspace_id = %s 
              AND recorded_at > NOW() - INTERVAL %s
            GROUP BY used_t1, used_t2
        """, workspace_id, f"{days} days")
        
        total = sum(r['count'] for r in results)
        t1_skipped = sum(r['count'] for r in results if not r['used_t1'])
        t2_skipped = sum(r['count'] for r in results if not r['used_t2'])
        
        return {
            "total_queries": total,
            "t1_skipped_count": t1_skipped,
            "t1_skip_rate": f"{100 * t1_skipped / total:.1f}%",
            "t2_skipped_count": t2_skipped,
            "t2_skip_rate": f"{100 * t2_skipped / total:.1f}%",
            "trend": "increasing" if t1_skipped > 0.7 * total else "decreasing"
        }
```

---

## Implementation Priorities

### **MVP (Weeks 1-4)**: Core Production Readiness
```
Week 1: Event Sourcing + Supabase Schema
Week 2: R2/Vectorize/Neo4j Cloud Integration
Week 3: SPPE Pipeline + Training Orchestration
Week 4: Review Queue API + Basic UI
```

**Success Criteria**:
- ✅ 100% audit trail for all operations
- ✅ SPPE pairs flowing to training
- ✅ Manual approval gates working
- ✅ Zero missing events

### **Phase 2 (Weeks 5-6)**: Creative + Generative
```
Week 5: Creative Writing + Image Generation
Week 6: Video + Audio Generation Adapters
```

**Success Criteria**:
- ✅ Local image gen working
- ✅ Video approval flow working
- ✅ All adapters return provenance

### **Phase 3 (Weeks 7-8)**: Transformer Thinning
```
Week 7: T1/T2 skip logic + metrics
Week 8: Workspace governance + monitoring
```

**Success Criteria**:
- ✅ T1 skipped >50% of queries
- ✅ T2 skipped >70% of queries
- ✅ Quotas enforced per workspace

---

## Technical Stack Summary

### **Database**
- Supabase (PostgreSQL) - Event store, signatures, governance
- Neo4j Aura - Knowledge graph
- Redis - Caching, materialized views

### **Cloud Storage**
- R2 - Artifacts (images, videos, training data)
- Vectorize - Embedding vectors
- Kaggle - Model training

### **AI Services**
- Groq - T1/T2 (boundary models)
- Stable Diffusion - Image generation (local)
- Runway - Video generation (API)
- ElevenLabs - Audio generation (optional)

### **Development**
- Python 3.13 + FastAPI (backend)
- React/TypeScript (frontend)
- Docker (containerization)
- Kubernetes (optional, for scale)

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Event store corruption | Critical | WAL + backup strategy, immutable log design |
| Compensation saga failure | High | Dead-letter queue + manual intervention |
| T1 skip breaks queries | Medium | Graceful fallback + monitoring alerts |
| Model hot-swap causes regression | High | Always maintain rollback metadata |
| Approval queue backlog | Medium | Priority scoring + auto-escalation |

---

## Success Metrics

### **By Week 8**
- ✅ 100% of queries have audit trail
- ✅ 1000+ SPPE pairs per week
- ✅ T1 skipped >60% of queries  
- ✅ T2 skipped >75% of queries
- ✅ Image generation working (local)
- ✅ Video generation working (approved)
- ✅ Zero model drift (hot-swap validates)
- ✅ Workspace quotas enforced
- ✅ Training loop self-sufficient (if it all works)

---

**This roadmap makes JimsAI production-ready while dramatically reducing transformer dependency. Instead of being an "alternative to GPT-4", JimsAI becomes a "trusted layer that uses transformers when beneficial and deterministic infrastructure when sufficient".**

**The key innovation: Transformers become optional optimization tools, not required infrastructure.**
