"""
Autonomous Training Agent for JIMS-AI

Runs indefinitely in a continuous loop:
1. FIND DATA - scan configured sources
2. INGEST - parallel processing of documents  
3. EVALUATE - measure current system state
4. IDENTIFY GAPS - find weak areas
5. TARGET INGESTION - prioritize data by gaps
6. GENERATE TRAINING SIGNAL - SPPE + world models
7. TRAIN - batch and upload to Kaggle
8. HUMAN GATE - approve weight activation
9. DEPLOY - hot-swap new weights
10. MEASURE IMPROVEMENT - report findings
11. REPEAT

Key principle: Autonomous workers handle volume work (extraction, normalization, embedding).
Humans via Training UI handle quality work (review, ambiguity resolution, corrections).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .de_llm_training_loop import (
    TrainResult,
    measurable_languages,
    measure_language,
    train_all,
)
from .event_store import AuditEventStore
from .models import (
    MemorySignature,
    SPPETrainingPair,
    WorldModelCandidate,
    utc_now,
)
from .observability import ExecutionTracer
from .pipeline import JimsAIPipeline


logger = logging.getLogger(__name__)


@dataclass
class AutonomousAgentConfig:
    """Configuration for the autonomous training agent."""

    # Data sources — DE-LLM: only real, provenance-stamped, sourced data. The
    # former "synthetic_generation" (Groq-generated) source is REMOVED: an LLM
    # fabricating training data is exactly what the Independence Policy forbids.
    # Base-model coverage is enriched by the de-LLM training loop (measure gap →
    # ingest from source → re-measure/rollback → promote), see
    # experiments/training/run_train_loop.py and _de_llm_ingest below.
    data_sources: list[str] = field(default_factory=lambda: [
        "common_vocabulary",   # fetch_common_words.py (frequency lists) — messy-input recall
        "lexicon_breadth",     # broaden_lexicon.py (Wikidata QRank concepts)
        "wikipedia",           # real corpus → ELE construction discovery
        "user_interactions",   # real resolved exchanges → SPPE pairs (NOT LLM-generated)
    ])
    
    # Ingestion
    parallel_workers: int = 8
    batch_size: int = 100
    max_documents_per_cycle: int = 5000
    
    # Evaluation thresholds
    intent_stability_min: float = 0.85
    provider_dependency_max: float = 0.15  # Max 15% provider calls
    retrieval_accuracy_min: float = 0.80
    world_model_confidence_min: float = 0.75
    
    # Gap targeting
    language_variant_threshold: float = 0.70
    domain_coverage_threshold: float = 0.65
    capability_coverage_threshold: float = 0.70
    
    # Training
    sppe_quality_threshold: float = 0.80
    auto_accept_confidence: float = 0.90  # Auto-approve if >90%
    human_review_confidence_range: tuple[float, float] = (0.65, 0.90)
    world_model_candidate_threshold: float = 0.75
    
    # Kaggle training
    sppe_batch_min: int = 1000
    training_interval_days: int = 7
    
    # Human gate
    require_human_approval: bool = True
    human_approval_timeout_hours: int = 24


@dataclass
class SystemState:
    """Snapshot of current system performance.

    HONESTY CONTRACT: a field is a real measured number, or it is None
    ("not yet measurable offline") — NEVER a fabricated placeholder. The old
    version returned invented scores (0.88 stability, per-language 0.45/0.52,
    domain 0.62 …); those are gone. `language_variant_scores` are now the CLL's
    real messy-extraction precision; metrics that need a live backend / eval
    harness we do not yet have offline are None, and gap detection skips them
    rather than acting on a made-up value.
    """

    timestamp: datetime
    world_model_confidence_avg: float
    intent_stability_score: float | None = None      # needs live eval harness
    provider_dependency_rate: float | None = None    # measured from real calls
    retrieval_accuracy: float | None = None          # needs live backend eval
    language_variant_scores: dict[str, float] = field(default_factory=dict)  # REAL (CLL)
    language_variant_recall: dict[str, float] = field(default_factory=dict)  # REAL (CLL)
    domain_coverage: dict[str, float] = field(default_factory=dict)      # empty until real eval
    capability_coverage: dict[str, float] = field(default_factory=dict)  # empty until real eval
    review_queue_depth: int = 0
    sppe_pairs_ready: int = 0


@dataclass
class IdentifiedGap:
    """A detected weakness in the system."""

    gap_type: str  # "language", "domain", "capability", "provider_dependency"
    name: str
    current_score: float
    threshold: float
    priority: int  # 1-10 (10 = critical)
    suggested_data_source: str
    estimated_documents_needed: int


class AutonomousTrainingAgent:
    """
    Main autonomous agent that orchestrates continuous training.
    
    Runs in a loop indefinitely:
    - Finds data from multiple sources
    - Ingests in parallel
    - Evaluates system state
    - Identifies gaps
    - Targets data to address gaps
    - Generates training signals
    - Batches for training
    - Waits for human approval
    - Deploys new weights
    - Reports improvements
    """

    def __init__(
        self,
        pipeline: JimsAIPipeline,
        config: AutonomousAgentConfig | None = None,
    ):
        self.pipeline = pipeline
        self.config = config or AutonomousAgentConfig()
        self.event_store = AuditEventStore()
        self.tracer = ExecutionTracer()
        
        # State tracking
        self.current_state: SystemState | None = None
        self.identified_gaps: list[IdentifiedGap] = []
        self.ingestion_history: list[dict[str, Any]] = []
        self.training_cycles: list[dict[str, Any]] = []
        self._last_train_results: list[TrainResult] = []  # real de-LLM loop output
        self.is_running = False

    async def run_continuous_loop(self) -> None:
        """
        Main autonomous loop.
        
        Runs indefinitely, performing one full cycle every iteration.
        Only stops on external signal (shutdown, error, or user intervention).
        """
        self.is_running = True
        cycle_count = 0
        
        logger.info("🚀 Autonomous Training Agent starting continuous loop")
        
        try:
            while self.is_running:
                cycle_count += 1
                logger.info(f"\n{'='*80}")
                logger.info(f"📋 CYCLE #{cycle_count} started at {utc_now()}")
                logger.info(f"{'='*80}")
                
                try:
                    # Main cycle
                    await self._execute_cycle()
                    
                    # Log cycle completion
                    self.event_store.append(
                        "agent_cycle_complete",
                        f"cycle_{cycle_count}",
                        {"cycle_number": cycle_count},
                    )
                    
                    # Wait before next cycle
                    logger.info(f"⏳ Cycle #{cycle_count} complete. Waiting 60 seconds before next cycle...")
                    await asyncio.sleep(60)
                    
                except Exception as cycle_error:
                    logger.error(f"❌ Error in cycle #{cycle_count}: {cycle_error}", exc_info=True)
                    self.event_store.append(
                        "agent_cycle_error",
                        f"cycle_{cycle_count}",
                        {"error": str(cycle_error)},
                    )
                    # Continue running on error
                    await asyncio.sleep(300)  # Wait 5 minutes before retrying
                    
        except KeyboardInterrupt:
            logger.info("⏹️ Autonomous agent stopped by user")
            self.is_running = False
        except Exception as fatal_error:
            logger.error(f"💥 Fatal error in autonomous agent: {fatal_error}", exc_info=True)
            self.is_running = False
            raise

    async def _execute_cycle(self) -> None:
        """Execute one complete training cycle."""
        
        # Step 1: FIND DATA
        logger.info("\n1️⃣ FIND DATA - Scanning data sources...")
        data_sources = await self._find_data_sources()
        logger.info(f"   ✓ Found {len(data_sources)} data sources ready for ingestion")
        
        # Step 2: INGEST
        logger.info("\n2️⃣ INGEST - Processing documents in parallel...")
        ingestion_results = await self._ingest_parallel(data_sources)
        logger.info(f"   ✓ Processed {ingestion_results['total_documents']} documents")
        logger.info(f"   ✓ Generated {ingestion_results['signatures_created']} signatures")
        logger.info(f"   ✓ Created {ingestion_results['sppe_pairs_generated']} SPPE pairs")

        # Step 2b: DE-LLM IMPROVEMENT (common-vocabulary track) — REAL, measured
        # THIS cycle by the loop that ran during ingest, with the gap-honesty
        # guard already applied. Decoupled from the Kaggle neural-weight path
        # (steps 7-10), which legitimately still needs 1000+ SPPE pairs + human
        # approval and does not trigger on a vocabulary hot-update.
        if self._last_train_results:
            imp = await self._measure_improvement({"deployment_id": "de-llm-vocab-hot-update"})
            logger.info("   ✓ de-LLM vocabulary improvement (REAL, measured this cycle):")
            for lang, d in sorted(imp["per_language"].items()):
                logger.info(f"      • {lang}: precision {d['precision_delta']:+.0%} "
                            f"recall {d['recall_delta']:+.0%} "
                            f"{'KEPT' if d['kept'] else 'rolled-back'}, "
                            f"{'promotable' if d['promotable'] else 'gated'}")
            logger.info(f"      • recall never regressed: {imp['recall_never_regressed']} "
                        f"(gap-honesty guard) | promotable: {imp['languages_promotable']}")

        # Step 3: EVALUATE
        logger.info("\n3️⃣ EVALUATE - Measuring current system state...")
        self.current_state = await self._evaluate_system_state()

        def _fmt(v: float | None) -> str:
            return "unmeasured" if v is None else f"{v:.4f}"

        st = self.current_state
        logger.info(f"   ✓ Intent Stability: {_fmt(st.intent_stability_score)}")
        logger.info(f"   ✓ Provider Dependency: {_fmt(st.provider_dependency_rate)}")
        logger.info(f"   ✓ Retrieval Accuracy: {_fmt(st.retrieval_accuracy)}")
        logger.info(f"   ✓ World Model Confidence: {st.world_model_confidence_avg:.4f}")
        for lang in sorted(st.language_variant_scores):
            logger.info(f"   ✓ extraction[{lang}]: precision={st.language_variant_scores[lang]:.0%} "
                        f"recall={st.language_variant_recall.get(lang, 0.0):.0%}  (REAL, CLL offline)")
        
        # Step 4: IDENTIFY GAPS
        logger.info("\n4️⃣ IDENTIFY GAPS - Finding weak areas...")
        self.identified_gaps = await self._identify_gaps(self.current_state)
        logger.info(f"   ✓ Identified {len(self.identified_gaps)} gaps")
        for gap in sorted(self.identified_gaps, key=lambda g: -g.priority)[:5]:
            logger.info(f"      • [{gap.gap_type}] {gap.name}: {gap.current_score:.4f} (need {gap.threshold:.4f})")
        
        # Step 5: TARGET INGESTION
        logger.info("\n5️⃣ TARGET INGESTION - Prioritizing data by gaps...")
        targeted_plan = await self._create_targeting_plan(self.identified_gaps)
        logger.info(f"   ✓ Created targeting plan:")
        for item in targeted_plan[:3]:
            logger.info(f"      • {item['source']}: {item['reason']} ({item['estimated_documents']} docs)")
        
        # Step 6: GENERATE TRAINING SIGNAL
        logger.info("\n6️⃣ GENERATE TRAINING SIGNAL - Creating SPPE pairs and world models...")
        training_signal = await self._generate_training_signal(ingestion_results)
        logger.info(f"   ✓ SPPE pairs ready: {training_signal['sppe_ready']}")
        logger.info(f"      • High confidence (auto-accept): {training_signal['auto_accept']}")
        logger.info(f"      • Medium confidence (review): {training_signal['human_review']}")
        logger.info(f"      • Low confidence (reject): {training_signal['reject']}")
        logger.info(f"   ✓ World model candidates: {training_signal['world_model_candidates']}")
        
        # Step 7: TRAIN
        logger.info("\n7️⃣ TRAIN - Packaging for Kaggle if batch ready...")
        training_decision = await self._check_training_trigger(training_signal)
        if training_decision['should_train']:
            kaggle_result = await self._prepare_kaggle_training(training_signal)
            logger.info(f"   ✓ Training batch ready!")
            logger.info(f"      • SPPE pairs: {kaggle_result['sppe_count']}")
            logger.info(f"      • World model candidates: {kaggle_result['world_model_count']}")
            logger.info(f"      • Average quality: {kaggle_result['avg_quality']:.4f}")
            logger.info(f"      • Kaggle dataset: {kaggle_result['kaggle_dataset_id']}")
            
            # Step 8: HUMAN GATE (only non-autonomous step)
            logger.info("\n8️⃣ HUMAN GATE - Waiting for approval...")
            approval = await self._await_human_approval(kaggle_result)
            if approval['approved']:
                logger.info(f"   ✓ Human approved weight activation")
                
                # Step 9: DEPLOY
                logger.info("\n9️⃣ DEPLOY - Hot-swapping new weights...")
                deploy_result = await self._deploy_weights(kaggle_result)
                logger.info(f"   ✓ Weights deployed: {deploy_result['deployment_id']}")
                
                # Step 10: MEASURE IMPROVEMENT
                logger.info("\n🔟 MEASURE IMPROVEMENT - Comparing metrics...")
                improvement = await self._measure_improvement(deploy_result)
                logger.info(f"   ✓ Improvement summary (real per-language deltas):")
                for lang, d in sorted(improvement["per_language"].items()):
                    logger.info(f"      • {lang}: precision {d['precision_delta']:+.0%}, "
                                f"recall {d['recall_delta']:+.0%}")
                logger.info(f"      • recall never regressed: {improvement['recall_never_regressed']}")
                logger.info("      • NOTE: neural-weight improvement measurement pending a real "
                            "offline eval harness (not fabricated here)")

                # Record training cycle
                self.training_cycles.append({
                    "cycle": len(self.training_cycles) + 1,
                    "timestamp": utc_now(),
                    "sppe_pairs": kaggle_result['sppe_count'],
                    "improvement": improvement,
                })
            else:
                logger.warning(f"   ⏱️ Human approval pending or rejected: {approval['reason']}")
        else:
            logger.info(f"   ⏳ Training not triggered yet: {training_decision['reason']}")

    async def _find_data_sources(self) -> list[dict[str, Any]]:
        """Scan configured data sources for available data."""
        sources = []
        
        for source_type in self.config.data_sources:
            if source_type == "common_vocabulary":
                # De-LLM base-model coverage: frequency lists per language →
                # fixes messy-input recall (the case-independent-name signal).
                sources.append({
                    "source": "common_vocabulary", "type": "sourced_de_llm",
                    "script": "experiments/concept_model/fetch_common_words.py",
                    "priority": 8, "language_variants": ["en", "fr", "zh", "yo", "sw"]})
            elif source_type == "lexicon_breadth":
                sources.append({
                    "source": "lexicon_breadth", "type": "sourced_de_llm",
                    "script": "experiments/concept_model/broaden_lexicon.py",
                    "priority": 6, "language_variants": ["en", "fr", "zh", "yo", "sw"]})
            elif source_type == "wikipedia":
                # Real corpus — feeds ELE construction discovery (lifts relation
                # extraction recall → the traversal reasoner from SAFE to USEFUL).
                sources.append({
                    "source": "wikipedia", "type": "public_dataset",
                    "priority": 5, "estimated_documents": 6000000,
                    "language_variants": ["en", "fr", "de", "es", "zh", "ar", "yo"]})
            elif source_type == "user_interactions":
                # Real resolved exchanges → SPPE pairs. NOT LLM-generated.
                count = len(self.pipeline.feedback_events)
                if count > 0:
                    sources.append({
                        "source": "user_interactions", "type": "real_system",
                        "priority": 10, "estimated_documents": count,
                        "language_variants": ["en", "mixed"]})
            # NOTE: no "synthetic_generation" / groq source — removed. An LLM
            # fabricating training data violates the Independence Policy.
        
        self.event_store.append(
            "agent_find_data_sources",
            "find_data",
            {"sources_found": len(sources), "total_estimated_docs": sum(s.get("estimated_documents", 0) for s in sources)},
        )
        
        return sources

    async def _ingest_parallel(self, data_sources: list[dict[str, Any]]) -> dict[str, Any]:
        """Ingest documents from sources in parallel using worker pool."""
        
        total_documents = 0
        signatures_created = 0
        sppe_pairs_generated = 0
        world_model_candidates_created = 0
        
        # Create parallel ingestion tasks
        tasks = []
        for source in data_sources[:self.config.parallel_workers]:  # Limit parallelism
            task = self._ingest_source(source)
            tasks.append(task)
        
        # Execute in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Ingestion error: {result}")
                continue
            
            total_documents += result.get("documents_processed", 0)
            signatures_created += result.get("signatures_created", 0)
            sppe_pairs_generated += result.get("sppe_pairs_generated", 0)
            world_model_candidates_created += result.get("world_model_candidates", 0)
        
        ingestion_result = {
            "total_documents": total_documents,
            "signatures_created": signatures_created,
            "sppe_pairs_generated": sppe_pairs_generated,
            "world_model_candidates": world_model_candidates_created,
        }
        
        self.event_store.append(
            "agent_ingest_batch",
            "ingest",
            ingestion_result,
        )
        
        self.ingestion_history.append({
            "timestamp": utc_now(),
            "result": ingestion_result,
        })
        
        return ingestion_result

    async def _ingest_source(self, source: dict[str, Any]) -> dict[str, Any]:
        """Ingest a single data source.

        common_vocabulary runs the REAL de-LLM loop (measure→ingest→re-measure→
        keep/rollback), so its numbers are measured, not simulated. Sources not
        yet wired to a real offline ingest return zeros with status
        'not_implemented_offline' — an honest 'nothing happened' rather than a
        fabricated 95% success rate.
        """
        name = source["source"]
        logger.debug(f"🔄 Ingesting from {name}...")

        if name == "common_vocabulary":
            # REAL: run the validated de-LLM training pass and keep its results
            # so _measure_improvement can report the actual before/after deltas.
            results = await asyncio.to_thread(train_all)
            self._last_train_results = results
            kept = [r for r in results if r.kept and r.action != "none"]
            promotable = [r for r in results if r.promotable]
            terms = sum(r.ingested_terms for r in kept)
            for r in results:
                for line in r.log:
                    logger.info("      " + line)
            return {
                "source": name,
                "documents_processed": terms,          # real common-vocab terms ingested
                "signatures_created": terms,           # each term is a real base-artifact entry
                "sppe_pairs_generated": 0,             # SPPE generation is not this source's job
                "world_model_candidates": 0,
                "languages_improved": [r.lang for r in kept],
                "languages_promotable": [r.lang for r in promotable],
                "status": "real",
            }

        # Not yet wired to a real offline ingest — report the honest zero.
        return {
            "source": name,
            "documents_processed": 0,
            "signatures_created": 0,
            "sppe_pairs_generated": 0,
            "world_model_candidates": 0,
            "status": "not_implemented_offline",
        }

    async def _evaluate_system_state(self) -> SystemState:
        """Measure current system performance from REAL signals — no placeholders.

        The only scores populated here are ones we can actually measure offline:
        per-language messy-extraction precision/recall (the CLL, milliseconds, no
        backend) and world-model confidence (the real promotion store). Metrics
        that need a live backend / eval harness we do not yet have are left None,
        and `_identify_gaps` skips them — the agent reports what it knows, and is
        honest about what it does not, rather than inventing a number.
        """

        # REAL per-language extraction quality from the CLL (offline). Runs in a
        # thread because it touches the concept index + reads the source file.
        def _measure_all_langs() -> tuple[dict[str, float], dict[str, float]]:
            prec, rec = {}, {}
            for lang in measurable_languages():
                m = measure_language(lang)
                prec[lang] = m["precision"]
                rec[lang] = m["recall"]
            return prec, rec

        lang_prec, lang_rec = await asyncio.to_thread(_measure_all_langs)

        wm_conf = 0.0
        try:
            wm_conf = self.pipeline.world_model_promotion.stats().get("avg_confidence", 0.0)
        except Exception:
            wm_conf = 0.0

        return SystemState(
            timestamp=utc_now(),
            world_model_confidence_avg=wm_conf,
            # None = not yet measurable offline (honest gap, not a fabricated 0.88).
            intent_stability_score=None,
            provider_dependency_rate=None,
            retrieval_accuracy=None,
            language_variant_scores=lang_prec,   # REAL
            language_variant_recall=lang_rec,    # REAL
            domain_coverage={},                  # no offline domain eval yet
            capability_coverage={},              # no offline capability eval yet
            review_queue_depth=len(self.pipeline.ambiguity_queue),
            sppe_pairs_ready=len(self.pipeline.feedback_history),
        )

    async def _identify_gaps(self, state: SystemState) -> list[IdentifiedGap]:
        """Identify weak areas in the system."""
        
        gaps = []

        # Check intent stability — only if actually measured (None = skip, no fake gate).
        if state.intent_stability_score is not None and state.intent_stability_score < self.config.intent_stability_min:
            gaps.append(IdentifiedGap(
                gap_type="stability",
                name="Intent Classification",
                current_score=state.intent_stability_score,
                threshold=self.config.intent_stability_min,
                priority=8,
                suggested_data_source="user_interactions",  # de-LLM: real SPPE pairs, not generated
                estimated_documents_needed=500,
            ))

        # Check provider dependency — only if measured.
        if state.provider_dependency_rate is not None and state.provider_dependency_rate > self.config.provider_dependency_max:
            gaps.append(IdentifiedGap(
                gap_type="provider_dependency",
                name="Provider Call Rate",
                current_score=1 - state.provider_dependency_rate,  # Lower is worse
                threshold=1 - self.config.provider_dependency_max,
                priority=9,
                suggested_data_source="wikipedia",
                estimated_documents_needed=2000,
            ))

        # Check language variants — REAL CLL extraction precision. The de-LLM
        # remedy is common-vocabulary ingestion (the loop that actually moves this
        # metric); low-resource languages with no source are surfaced as gaps that
        # need LEARNED coverage, not a fabricated dataset.
        for lang, score in state.language_variant_scores.items():
            if score < self.config.language_variant_threshold:
                gaps.append(IdentifiedGap(
                    gap_type="language",
                    name=f"Language Variant: {lang}",
                    current_score=score,
                    threshold=self.config.language_variant_threshold,
                    priority=7,
                    suggested_data_source="common_vocabulary",
                    estimated_documents_needed=int(1000 * (1 - score)),
                ))
        
        # Check domain coverage
        for domain, score in state.domain_coverage.items():
            if score < self.config.domain_coverage_threshold:
                gaps.append(IdentifiedGap(
                    gap_type="domain",
                    name=f"Domain: {domain}",
                    current_score=score,
                    threshold=self.config.domain_coverage_threshold,
                    priority=6,
                    suggested_data_source="wikipedia",
                    estimated_documents_needed=int(1500 * (1 - score)),
                ))
        
        # Check capability coverage
        for capability, score in state.capability_coverage.items():
            if score < self.config.capability_coverage_threshold:
                gaps.append(IdentifiedGap(
                    gap_type="capability",
                    name=f"Capability: {capability}",
                    current_score=score,
                    threshold=self.config.capability_coverage_threshold,
                    priority=5,
                    suggested_data_source="wikipedia",  # de-LLM: real corpus → ELE constructions
                    estimated_documents_needed=int(1000 * (1 - score)),
                ))
        
        self.event_store.append(
            "agent_identify_gaps",
            "gaps",
            {"gaps_identified": len(gaps), "high_priority": sum(1 for g in gaps if g.priority >= 7)},
        )
        
        return gaps

    async def _create_targeting_plan(self, gaps: list[IdentifiedGap]) -> list[dict[str, Any]]:
        """Create a prioritized ingestion plan based on identified gaps."""
        
        # Group by source and aggregate
        by_source = {}
        for gap in gaps:
            source = gap.suggested_data_source
            if source not in by_source:
                by_source[source] = {
                    "source": source,
                    "total_priority": 0,
                    "total_docs": 0,
                    "gap_count": 0,
                    "reasons": [],
                }
            by_source[source]["total_priority"] += gap.priority
            by_source[source]["total_docs"] += gap.estimated_documents_needed
            by_source[source]["gap_count"] += 1
            by_source[source]["reasons"].append(gap.name)
        
        # Convert to list and sort by priority
        plan = list(by_source.values())
        plan.sort(key=lambda x: -x["total_priority"])
        
        # Add reason summary
        for item in plan:
            item["reason"] = f"Address {item['gap_count']} gaps: {', '.join(item['reasons'][:2])}"
            item["estimated_documents"] = item["total_docs"]
        
        return plan

    async def _generate_training_signal(self, ingestion_results: dict[str, Any]) -> dict[str, Any]:
        """Generate SPPE pairs and world model candidates from ingestion.

        NOTE: the quality-band split below is a PLACEHOLDER distribution for the
        neural-weight path, not a real scorer. It is honest today only because
        `sppe_pairs_generated` is 0 offline (0 in → 0 out); a real SPPE quality
        scorer must replace these ratios before this path produces live numbers.
        """
        total_sppe = ingestion_results["sppe_pairs_generated"]

        # PLACEHOLDER quality distribution (see docstring) — safe at 0.
        auto_accept = int(total_sppe * 0.50)  # high confidence
        human_review = int(total_sppe * 0.35)  # medium confidence
        reject = int(total_sppe * 0.15)  # low confidence
        
        return {
            "sppe_ready": total_sppe,
            "auto_accept": auto_accept,
            "human_review": human_review,
            "reject": reject,
            "world_model_candidates": ingestion_results["world_model_candidates"],
        }

    async def _check_training_trigger(self, training_signal: dict[str, Any]) -> dict[str, Any]:
        """Determine if batch is ready for training."""
        
        sppe_ready = training_signal["sppe_ready"]
        should_train = sppe_ready >= self.config.sppe_batch_min
        
        return {
            "should_train": should_train,
            "reason": f"SPPE pairs: {sppe_ready}/{self.config.sppe_batch_min}" if not should_train else f"Batch ready: {sppe_ready} pairs",
            "sppe_pairs": sppe_ready,
        }

    async def _prepare_kaggle_training(self, training_signal: dict[str, Any]) -> dict[str, Any]:
        """Prepare training batch for Kaggle upload.

        Reachable only once ≥1000 REAL SPPE pairs exist (not producible offline
        yet). `avg_quality` is a PLACEHOLDER until a real quality scorer exists.
        """
        return {
            "kaggle_dataset_id": f"jimsai-training-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            "sppe_count": training_signal["sppe_ready"],
            "world_model_count": training_signal["world_model_candidates"],
            "avg_quality": 0.84,  # PLACEHOLDER — pending real SPPE quality scorer
            "auto_accept_count": training_signal["auto_accept"],
            "human_review_count": training_signal["human_review"],
            "reject_count": training_signal["reject"],
            "timestamp": utc_now(),
        }

    async def _await_human_approval(self, kaggle_result: dict[str, Any], timeout_hours: int = 24) -> dict[str, Any]:
        """Wait for human approval at the gate (only non-autonomous step)."""
        
        # In production: would check approval queue and wait
        # For now: return pending
        
        logger.warning(f"⏳ HUMAN APPROVAL GATE: Waiting for approval of Kaggle dataset {kaggle_result['kaggle_dataset_id']}")
        
        return {
            "approved": False,
            "reason": "Awaiting human review (not auto-approved in autonomous mode)",
            "timeout_hours": timeout_hours,
        }

    async def _deploy_weights(self, kaggle_result: dict[str, Any]) -> dict[str, Any]:
        """Deploy new weights via hot-swap."""
        
        return {
            "deployment_id": f"deploy-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            "kaggle_dataset": kaggle_result["kaggle_dataset_id"],
            "timestamp": utc_now(),
        }

    async def _measure_improvement(self, deploy_result: dict[str, Any]) -> dict[str, Any]:
        """Report the REAL improvement from the last de-LLM training pass.

        No hardcoded deltas: each number is the measured before→after precision/
        recall change per language from the loop that was actually run this cycle,
        with the gap-honesty guard already applied (rolled-back passes show 0).
        """
        per_lang = {
            r.lang: {
                "precision_delta": r.precision_delta,
                "recall_delta": r.recall_delta,
                "kept": r.kept,
                "promotable": r.promotable,
            }
            for r in self._last_train_results
        }
        kept = [r for r in self._last_train_results if r.kept and r.action != "none"]
        mean_prec_gain = round(sum(r.precision_delta for r in kept) / len(kept), 3) if kept else 0.0
        # Guarantee: no language's recall regressed (guard enforced in the loop).
        recall_safe = all(r.recall_delta >= 0 for r in self._last_train_results)
        return {
            "per_language": per_lang,
            "mean_precision_gain_kept": mean_prec_gain,
            "languages_promotable": [r.lang for r in self._last_train_results if r.promotable],
            "recall_never_regressed": recall_safe,
            "deployment_id": deploy_result["deployment_id"],
        }

    def stop(self) -> None:
        """Stop the autonomous agent."""
        self.is_running = False
        logger.info("⏹️ Autonomous agent stopping...")


# Entry point for running agent
async def run_agent(pipeline: JimsAIPipeline, config: AutonomousAgentConfig | None = None) -> None:
    """Run the autonomous training agent."""
    agent = AutonomousTrainingAgent(pipeline, config)
    await agent.run_continuous_loop()
