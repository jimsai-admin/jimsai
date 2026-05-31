"""
Training UI Backend - FastAPI endpoints for autonomous agent management

Provides:
- Review queue management
- Human decision processing
- Real-time metrics dashboard
- Agent status and monitoring
- Weight approval workflow
- Error handling and logging
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from .autonomous_training_agent import AutonomousTrainingAgent, SystemState, IdentifiedGap
from .training_ui_bridge import TrainingUIBridge, ReviewQueueItem
from .metrics_reporter import MetricsCollector, ReportFormatter


logger = logging.getLogger(__name__)


# ============================================================================
# PYDANTIC MODELS FOR API
# ============================================================================

class ReviewQueueItemResponse(BaseModel):
    """API response for a review queue item."""
    
    item_id: str
    item_type: str
    content: dict[str, Any]
    confidence: float
    priority: int
    created_at: str
    human_decision: str | None = None
    correction: dict[str, Any] | None = None
    processed_at: str | None = None


class SystemStateResponse(BaseModel):
    """API response for system state."""
    
    timestamp: str
    intent_stability_score: float
    provider_dependency_rate: float
    retrieval_accuracy: float
    world_model_confidence_avg: float
    language_variant_scores: dict[str, float]
    domain_coverage: dict[str, float]
    capability_coverage: dict[str, float]
    review_queue_depth: int
    sppe_pairs_ready: int


class IdentifiedGapResponse(BaseModel):
    """API response for identified gap."""
    
    gap_type: str
    name: str
    current_score: float
    threshold: float
    priority: int
    suggested_data_source: str
    estimated_documents_needed: int


class AgentStatusResponse(BaseModel):
    """API response for agent status."""
    
    is_running: bool
    current_cycle: int
    system_state: SystemStateResponse | None
    identified_gaps: list[IdentifiedGapResponse] = Field(default_factory=list)
    ingestion_history_count: int
    training_cycles_count: int


class HumanDecisionRequest(BaseModel):
    """Request to process human decision."""
    
    review_item_id: str
    decision: str  # "accept", "reject", "correct"
    correction: dict[str, Any] | None = None


class WeightApprovalRequest(BaseModel):
    """Request to approve or reject weights."""
    
    deployment_id: str
    approved: bool
    reason: str | None = None
    reviewer_name: str


class ReviewQueueStatsResponse(BaseModel):
    """Statistics about the review queue."""
    
    total_pending: int
    by_type: dict[str, int]
    auto_accepted: int
    corrections_collected: int
    avg_confidence: float


class MetricsSnapshotResponse(BaseModel):
    """Metrics snapshot for dashboard."""
    
    timestamp: str
    intent_stability: float
    provider_dependency: float
    retrieval_accuracy: float
    world_model_confidence: float


class HealthCheckResponse(BaseModel):
    """Health check response."""
    
    status: str
    agent_running: bool
    timestamp: str


# ============================================================================
# FASTAPI ROUTER
# ============================================================================

class TrainingUIRouter:
    """FastAPI router for Training UI endpoints."""

    def __init__(self, agent: AutonomousTrainingAgent, ui_bridge: TrainingUIBridge):
        self.agent = agent
        self.ui_bridge = ui_bridge
        self.metrics_collector = MetricsCollector()
        self.router = self._create_router()

    def _create_router(self) -> APIRouter:
        """Create FastAPI router with all endpoints."""
        router = APIRouter(prefix="/api/training", tags=["training"])

        @router.get("/health", response_model=HealthCheckResponse)
        async def health_check() -> HealthCheckResponse:
            """Health check endpoint."""
            return HealthCheckResponse(
                status="healthy" if self.agent.is_running else "idle",
                agent_running=self.agent.is_running,
                timestamp=datetime.utcnow().isoformat(),
            )

        @router.get("/status", response_model=AgentStatusResponse)
        async def get_agent_status() -> AgentStatusResponse:
            """Get current agent status."""
            gaps_response = []
            if self.agent.identified_gaps:
                gaps_response = [
                    IdentifiedGapResponse(
                        gap_type=gap.gap_type,
                        name=gap.name,
                        current_score=gap.current_score,
                        threshold=gap.threshold,
                        priority=gap.priority,
                        suggested_data_source=gap.suggested_data_source,
                        estimated_documents_needed=gap.estimated_documents_needed,
                    )
                    for gap in sorted(self.agent.identified_gaps, key=lambda g: -g.priority)[:10]
                ]

            state_response = None
            if self.agent.current_state:
                state_response = SystemStateResponse(
                    timestamp=self.agent.current_state.timestamp.isoformat(),
                    intent_stability_score=self.agent.current_state.intent_stability_score,
                    provider_dependency_rate=self.agent.current_state.provider_dependency_rate,
                    retrieval_accuracy=self.agent.current_state.retrieval_accuracy,
                    world_model_confidence_avg=self.agent.current_state.world_model_confidence_avg,
                    language_variant_scores=self.agent.current_state.language_variant_scores,
                    domain_coverage=self.agent.current_state.domain_coverage,
                    capability_coverage=self.agent.current_state.capability_coverage,
                    review_queue_depth=self.agent.current_state.review_queue_depth,
                    sppe_pairs_ready=self.agent.current_state.sppe_pairs_ready,
                )

            return AgentStatusResponse(
                is_running=self.agent.is_running,
                current_cycle=len(self.agent.ingestion_history),
                system_state=state_response,
                identified_gaps=gaps_response,
                ingestion_history_count=len(self.agent.ingestion_history),
                training_cycles_count=len(self.agent.training_cycles),
            )

        @router.get("/system-state", response_model=SystemStateResponse)
        async def get_system_state() -> SystemStateResponse:
            """Get current system state."""
            if not self.agent.current_state:
                raise HTTPException(status_code=503, detail="System state not yet evaluated")

            return SystemStateResponse(
                timestamp=self.agent.current_state.timestamp.isoformat(),
                intent_stability_score=self.agent.current_state.intent_stability_score,
                provider_dependency_rate=self.agent.current_state.provider_dependency_rate,
                retrieval_accuracy=self.agent.current_state.retrieval_accuracy,
                world_model_confidence_avg=self.agent.current_state.world_model_confidence_avg,
                language_variant_scores=self.agent.current_state.language_variant_scores,
                domain_coverage=self.agent.current_state.domain_coverage,
                capability_coverage=self.agent.current_state.capability_coverage,
                review_queue_depth=self.agent.current_state.review_queue_depth,
                sppe_pairs_ready=self.agent.current_state.sppe_pairs_ready,
            )

        @router.get("/gaps", response_model=list[IdentifiedGapResponse])
        async def get_identified_gaps() -> list[IdentifiedGapResponse]:
            """Get identified gaps."""
            sorted_gaps = sorted(self.agent.identified_gaps, key=lambda g: -g.priority)
            return [
                IdentifiedGapResponse(
                    gap_type=gap.gap_type,
                    name=gap.name,
                    current_score=gap.current_score,
                    threshold=gap.threshold,
                    priority=gap.priority,
                    suggested_data_source=gap.suggested_data_source,
                    estimated_documents_needed=gap.estimated_documents_needed,
                )
                for gap in sorted_gaps
            ]

        @router.get("/review-queue", response_model=list[ReviewQueueItemResponse])
        async def get_review_queue(limit: int = 20) -> list[ReviewQueueItemResponse]:
            """Get items awaiting human review."""
            items = self.ui_bridge.get_review_queue(limit=limit)
            return [
                ReviewQueueItemResponse(
                    item_id=item.item_id,
                    item_type=item.item_type,
                    content=item.content,
                    confidence=item.confidence,
                    priority=item.priority,
                    created_at=item.created_at,
                    human_decision=item.human_decision,
                    correction=item.correction,
                    processed_at=item.processed_at,
                )
                for item in items
            ]

        @router.get("/review-queue/stats", response_model=ReviewQueueStatsResponse)
        async def get_review_queue_stats() -> ReviewQueueStatsResponse:
            """Get review queue statistics."""
            stats = self.ui_bridge.get_review_queue_stats()
            return ReviewQueueStatsResponse(
                total_pending=stats["total_pending"],
                by_type=stats["by_type"],
                auto_accepted=stats["auto_accepted"],
                corrections_collected=stats["corrections_collected"],
                avg_confidence=stats["avg_confidence"],
            )

        @router.post("/review-queue/decision")
        async def process_human_decision(request: HumanDecisionRequest) -> dict[str, Any]:
            """Process human decision on review item."""
            try:
                await self.ui_bridge.process_human_decision(
                    request.review_item_id,
                    request.decision,
                    request.correction,
                )
                return {
                    "status": "success",
                    "message": f"Decision '{request.decision}' recorded",
                }
            except Exception as e:
                logger.error(f"Error processing decision: {e}")
                raise HTTPException(status_code=400, detail=str(e))

        @router.post("/weight-approval")
        async def approve_or_reject_weights(request: WeightApprovalRequest) -> dict[str, Any]:
            """Approve or reject weight deployment."""
            try:
                logger.info(
                    f"Weight approval: {request.deployment_id} - "
                    f"Approved: {request.approved} by {request.reviewer_name}"
                )
                
                # In production: would update weight deployment status
                return {
                    "status": "success",
                    "message": f"Weights {'approved' if request.approved else 'rejected'}",
                    "deployment_id": request.deployment_id,
                    "reviewer": request.reviewer_name,
                }
            except Exception as e:
                logger.error(f"Error processing weight approval: {e}")
                raise HTTPException(status_code=400, detail=str(e))

        @router.get("/metrics/history", response_model=list[MetricsSnapshotResponse])
        async def get_metrics_history(limit: int = 100) -> list[MetricsSnapshotResponse]:
            """Get metrics history for dashboard."""
            snapshots = self.metrics_collector.snapshots[-limit:]
            return [
                MetricsSnapshotResponse(
                    timestamp=s.timestamp,
                    intent_stability=s.intent_stability,
                    provider_dependency=s.provider_dependency,
                    retrieval_accuracy=s.retrieval_accuracy,
                    world_model_confidence=s.world_model_confidence,
                )
                for s in snapshots
            ]

        @router.get("/improvement-report")
        async def get_latest_improvement_report() -> dict[str, Any]:
            """Get latest improvement report."""
            if not self.agent.training_cycles:
                raise HTTPException(status_code=404, detail="No training cycles yet")

            latest = self.agent.training_cycles[-1]
            formatter = ReportFormatter()
            
            # Would normally fetch full report from storage
            return {
                "cycle": latest.get("cycle"),
                "timestamp": latest.get("timestamp"),
                "improvement": latest.get("improvement"),
            }

        @router.post("/agent/start")
        async def start_agent() -> dict[str, str]:
            """Start the agent (for manual control)."""
            if self.agent.is_running:
                raise HTTPException(status_code=400, detail="Agent already running")
            
            logger.info("Starting agent from UI...")
            # In production: would start agent in background task
            
            return {"status": "started", "message": "Agent starting..."}

        @router.post("/agent/stop")
        async def stop_agent() -> dict[str, str]:
            """Stop the agent (for manual control)."""
            if not self.agent.is_running:
                raise HTTPException(status_code=400, detail="Agent not running")
            
            logger.info("Stopping agent from UI...")
            self.agent.stop()
            
            return {"status": "stopped", "message": "Agent stopped"}

        @router.get("/quality-metrics")
        async def get_quality_metrics() -> dict[str, Any]:
            """Get quality metrics from human review decisions."""
            return self.ui_bridge.get_quality_metrics()

        return router


# ============================================================================
# WEBSOCKET CONNECTION MANAGER
# ============================================================================

class ConnectionManager:
    """Manage WebSocket connections for real-time updates."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and track connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"🔌 WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove connection."""
        self.active_connections.remove(websocket)
        logger.info(f"🔌 WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send message to all connected clients."""
        disconnected = []
        
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to connection: {e}")
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)


# ============================================================================
# INTEGRATION WITH FASTAPI APP
# ============================================================================

def setup_training_ui_routes(
    app: Any,
    agent: AutonomousTrainingAgent,
    ui_bridge: TrainingUIBridge,
) -> TrainingUIRouter:
    """
    Setup Training UI routes on FastAPI app.
    
    Usage:
        from fastapi import FastAPI
        from prototype.jimsai.autonomous_training_agent import AutonomousTrainingAgent
        from prototype.jimsai.training_ui_bridge import TrainingUIBridge
        from prototype.jimsai.training_ui_backend import setup_training_ui_routes
        
        app = FastAPI()
        agent = AutonomousTrainingAgent(pipeline, config)
        ui_bridge = TrainingUIBridge(pipeline)
        
        router = setup_training_ui_routes(app, agent, ui_bridge)
        app.include_router(router.router)
    """
    ui_router = TrainingUIRouter(agent, ui_bridge)
    app.include_router(ui_router.router)
    
    logger.info("✅ Training UI routes registered")
    
    return ui_router


# ============================================================================
# BACKGROUND TASKS
# ============================================================================

async def metrics_update_background_task(
    metrics_collector: MetricsCollector,
    agent: AutonomousTrainingAgent,
    connection_manager: ConnectionManager,
) -> None:
    """
    Background task to periodically update metrics and notify clients.
    
    Usage:
        from fastapi import BackgroundTasks
        
        @app.on_event("startup")
        async def startup():
            background_tasks = BackgroundTasks()
            background_tasks.add_task(
                metrics_update_background_task,
                metrics_collector,
                agent,
                connection_manager
            )
    """
    while True:
        try:
            # Record current state
            if agent.current_state:
                metrics_collector.record_snapshot(agent.current_state)
            
            # Notify connected clients
            message = {
                "event": "metrics_update",
                "timestamp": datetime.utcnow().isoformat(),
                "system_running": agent.is_running,
            }
            
            await connection_manager.broadcast(message)
            
            # Update every 30 seconds
            import asyncio
            await asyncio.sleep(30)
            
        except Exception as e:
            logger.error(f"Error in metrics background task: {e}")
