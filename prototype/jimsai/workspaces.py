"""
Multi-Tenant Workspace Architecture

Enables JimsAI to serve as a BASE MODEL where personalization happens
from each workspace's usage patterns.

Key concepts:
- Workspace: Isolated tenant with own configuration, memory, and training data
- Personalization: Comes from workspace-specific queries and SPPE pairs
- Base Model: Shared across all workspaces (inference-only)
- Adaptation: Workspace-specific model fine-tuning from their SPPE pairs
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from uuid import uuid4
import json

logger = logging.getLogger(__name__)


# ============================================================================
# Workspace Configuration & Metadata
# ============================================================================

@dataclass
class WorkspaceConfig:
    """Configuration for a workspace"""
    workspace_id: str
    organization_id: str
    name: str
    description: str = ""
    
    # Provider settings (can override defaults)
    groq_skip_t1_threshold: float = 0.90  # Workspace can customize
    groq_skip_t2_threshold: float = 0.95
    
    # Training settings
    enable_sppe_collection: bool = True
    enable_model_training: bool = True
    training_frequency_days: int = 7
    min_sppe_pairs_for_training: int = 1000
    
    # Personalization settings
    enable_personalization: bool = True
    personalization_model: str = "workspace-adapter"  # Separate from base model
    
    # Governance settings
    max_queries_per_day: int = 100000
    max_cost_per_day: float = 1000.0
    require_human_approval: bool = False
    approval_threshold: float = 0.70  # Flag uncertain decisions
    
    # Data settings
    data_retention_days: int = 90
    enable_analytics: bool = True
    
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class WorkspaceMetrics:
    """Metrics for a workspace"""
    workspace_id: str
    
    # Usage metrics
    total_queries: int = 0
    total_cost: float = 0.0
    avg_latency_ms: float = 0.0
    
    # Quality metrics
    avg_confidence: float = 0.0
    avg_sppe_quality: float = 0.0
    
    # Personalization metrics
    total_sppe_pairs: int = 0
    models_trained: int = 0
    last_training_date: Optional[datetime] = None
    
    # Provider usage
    groq_t1_calls: int = 0
    groq_t1_skipped: int = 0
    groq_t2_calls: int = 0
    groq_t2_skipped: int = 0
    
    # Workspace-specific model performance
    base_model_accuracy: float = 0.0  # Shared base
    workspace_model_accuracy: float = 0.0  # Personalized
    
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class WorkspaceQuota:
    """Usage quotas for workspace"""
    workspace_id: str
    
    # Period quotas
    queries_today: int = 0
    cost_today: float = 0.0
    queries_limit: int = 100000
    cost_limit: float = 1000.0
    
    # Reset time (UTC)
    reset_time: datetime = field(default_factory=datetime.utcnow)
    
    # Overages
    allow_overages: bool = False
    overage_cost_multiplier: float = 1.5


# ============================================================================
# Workspace Manager
# ============================================================================

class WorkspaceManager:
    """Manages multi-tenant workspaces"""
    
    def __init__(self):
        self.workspaces: Dict[str, WorkspaceConfig] = {}
        self.metrics: Dict[str, WorkspaceMetrics] = {}
        self.quotas: Dict[str, WorkspaceQuota] = {}
        self.personalization_models: Dict[str, Dict] = {}  # workspace_id -> model metadata
    
    def create_workspace(
        self,
        organization_id: str,
        name: str,
        description: str = "",
        config_overrides: Optional[Dict[str, Any]] = None
    ) -> WorkspaceConfig:
        """Create new workspace"""
        workspace_id = str(uuid4())
        
        config = WorkspaceConfig(
            workspace_id=workspace_id,
            organization_id=organization_id,
            name=name,
            description=description,
        )
        
        # Apply custom config if provided
        if config_overrides:
            for key, value in config_overrides.items():
                if hasattr(config, key):
                    setattr(config, key, value)
        
        self.workspaces[workspace_id] = config
        self.metrics[workspace_id] = WorkspaceMetrics(workspace_id)
        self.quotas[workspace_id] = WorkspaceQuota(workspace_id)
        
        logger.info(f"✓ Workspace created: {workspace_id} ({name})")
        return config
    
    def get_workspace(self, workspace_id: str) -> Optional[WorkspaceConfig]:
        """Get workspace configuration"""
        return self.workspaces.get(workspace_id)
    
    def get_workspace_metrics(self, workspace_id: str) -> Optional[WorkspaceMetrics]:
        """Get workspace metrics"""
        return self.metrics.get(workspace_id)
    
    def get_workspace_quota(self, workspace_id: str) -> Optional[WorkspaceQuota]:
        """Get workspace quota"""
        return self.quotas.get(workspace_id)
    
    def check_quota(self, workspace_id: str, operation: str = "query", cost: float = 0.01) -> bool:
        """Check if workspace has quota for operation"""
        quota = self.quotas.get(workspace_id)
        if not quota:
            return False
        
        if operation == "query":
            if quota.queries_today >= quota.queries_limit:
                logger.warning(f"Query quota exceeded for {workspace_id}")
                return False
            quota.queries_today += 1
        
        if cost > 0:
            if quota.cost_today + cost > quota.cost_limit:
                if not quota.allow_overages:
                    logger.warning(f"Cost quota exceeded for {workspace_id}")
                    return False
            quota.cost_today += cost
        
        return True
    
    def record_query(
        self,
        workspace_id: str,
        latency_ms: float,
        cost: float,
        confidence: float
    ):
        """Record query execution for workspace metrics"""
        metrics = self.metrics.get(workspace_id)
        if not metrics:
            return
        
        metrics.total_queries += 1
        metrics.total_cost += cost
        metrics.avg_latency_ms = (
            (metrics.avg_latency_ms * (metrics.total_queries - 1) + latency_ms) 
            / metrics.total_queries
        )
        metrics.avg_confidence = (
            (metrics.avg_confidence * (metrics.total_queries - 1) + confidence)
            / metrics.total_queries
        )
        metrics.updated_at = datetime.utcnow()
    
    def record_sppe_pair(self, workspace_id: str, quality_score: float):
        """Record SPPE pair for workspace"""
        metrics = self.metrics.get(workspace_id)
        if not metrics:
            return
        
        metrics.total_sppe_pairs += 1
        metrics.avg_sppe_quality = (
            (metrics.avg_sppe_quality * (metrics.total_sppe_pairs - 1) + quality_score)
            / metrics.total_sppe_pairs
        )
    
    def record_transformer_skip(self, workspace_id: str, t1_skipped: bool, t2_skipped: bool):
        """Record transformer skip decisions"""
        metrics = self.metrics.get(workspace_id)
        if not metrics:
            return
        
        if t1_skipped:
            metrics.groq_t1_skipped += 1
        else:
            metrics.groq_t1_calls += 1
        
        if t2_skipped:
            metrics.groq_t2_skipped += 1
        else:
            metrics.groq_t2_calls += 1
    
    def create_personalization_model(
        self,
        workspace_id: str,
        model_metadata: Dict[str, Any]
    ) -> str:
        """Create personalized model for workspace"""
        model_id = f"wsp_{workspace_id}_{datetime.utcnow().timestamp()}"
        
        self.personalization_models[workspace_id] = {
            "model_id": model_id,
            "workspace_id": workspace_id,
            "created_at": datetime.utcnow().isoformat(),
            "base_model_version": "phase5-base",
            "training_pairs": model_metadata.get("training_pairs", 0),
            "accuracy": model_metadata.get("accuracy", 0.0),
            "metadata": model_metadata,
        }
        
        metrics = self.metrics.get(workspace_id)
        if metrics:
            metrics.models_trained += 1
            metrics.last_training_date = datetime.utcnow()
        
        logger.info(f"✓ Personalized model created: {model_id}")
        return model_id
    
    def get_personalization_model(self, workspace_id: str) -> Optional[Dict]:
        """Get workspace's personalized model info"""
        return self.personalization_models.get(workspace_id)


# ============================================================================
# Workspace-Aware Context
# ============================================================================

class WorkspaceContext:
    """Holds workspace context for request handling"""
    
    def __init__(
        self,
        workspace_id: str,
        workspace_manager: WorkspaceManager,
        user_id: Optional[str] = None,
        org_id: Optional[str] = None
    ):
        self.workspace_id = workspace_id
        self.workspace_manager = workspace_manager
        self.user_id = user_id or f"user_{workspace_id}"
        self.org_id = org_id
        
        self.config = workspace_manager.get_workspace(workspace_id)
        self.metrics = workspace_manager.get_workspace_metrics(workspace_id)
        self.quota = workspace_manager.get_workspace_quota(workspace_id)
        self.personalization_model = workspace_manager.get_personalization_model(workspace_id)
        
        # Per-request state
        self.request_id = str(uuid4())
        self.start_time = datetime.utcnow()
    
    def is_personalized(self) -> bool:
        """Check if workspace has personalized model"""
        return self.personalization_model is not None and self.config.enable_personalization
    
    def get_thresholds(self) -> Dict[str, float]:
        """Get workspace-specific skip thresholds"""
        return {
            "t1_skip": self.config.groq_skip_t1_threshold,
            "t2_skip": self.config.groq_skip_t2_threshold,
        }
    
    def finalize_request(self, latency_ms: float, cost: float, confidence: float):
        """Finalize request tracking"""
        self.workspace_manager.record_query(
            self.workspace_id,
            latency_ms,
            cost,
            confidence
        )


# ============================================================================
# Organization Manager (Multi-Workspace)
# ============================================================================

class OrganizationManager:
    """Manages all workspaces for an organization"""
    
    def __init__(self):
        self.organizations: Dict[str, Dict[str, Any]] = {}
        self.workspace_manager = WorkspaceManager()
        self.organization_workspaces: Dict[str, List[str]] = {}  # org_id -> [workspace_ids]
    
    def create_organization(self, org_name: str, description: str = "") -> str:
        """Create organization"""
        org_id = str(uuid4())
        
        self.organizations[org_id] = {
            "org_id": org_id,
            "name": org_name,
            "description": description,
            "created_at": datetime.utcnow().isoformat(),
        }
        
        self.organization_workspaces[org_id] = []
        logger.info(f"✓ Organization created: {org_id} ({org_name})")
        return org_id
    
    def create_workspace_in_org(
        self,
        org_id: str,
        workspace_name: str,
        config_overrides: Optional[Dict] = None
    ) -> WorkspaceConfig:
        """Create workspace within organization"""
        workspace = self.workspace_manager.create_workspace(
            organization_id=org_id,
            name=workspace_name,
            config_overrides=config_overrides
        )
        
        if org_id not in self.organization_workspaces:
            self.organization_workspaces[org_id] = []
        
        self.organization_workspaces[org_id].append(workspace.workspace_id)
        return workspace
    
    def get_organization_workspaces(self, org_id: str) -> List[WorkspaceConfig]:
        """Get all workspaces for organization"""
        workspace_ids = self.organization_workspaces.get(org_id, [])
        return [
            self.workspace_manager.get_workspace(wid)
            for wid in workspace_ids
        ]
    
    def get_organization_metrics(self, org_id: str) -> Dict[str, Any]:
        """Aggregate metrics across organization"""
        workspace_ids = self.organization_workspaces.get(org_id, [])
        
        total_queries = 0
        total_cost = 0.0
        avg_confidence = 0.0
        workspace_count = 0
        
        for workspace_id in workspace_ids:
            metrics = self.workspace_manager.get_workspace_metrics(workspace_id)
            if metrics:
                total_queries += metrics.total_queries
                total_cost += metrics.total_cost
                avg_confidence += metrics.avg_confidence
                workspace_count += 1
        
        return {
            "org_id": org_id,
            "workspace_count": workspace_count,
            "total_queries": total_queries,
            "total_cost": total_cost,
            "avg_confidence": avg_confidence / max(workspace_count, 1),
        }


# Singleton instances
_workspace_manager: Optional[WorkspaceManager] = None
_organization_manager: Optional[OrganizationManager] = None


def get_workspace_manager() -> WorkspaceManager:
    """Get global workspace manager"""
    global _workspace_manager
    if _workspace_manager is None:
        _workspace_manager = WorkspaceManager()
    return _workspace_manager


def get_organization_manager() -> OrganizationManager:
    """Get global organization manager"""
    global _organization_manager
    if _organization_manager is None:
        _organization_manager = OrganizationManager()
    return _organization_manager
