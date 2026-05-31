"""
Personalization Layer - Adapts Base Model from Workspace Usage

Core concept: JimsAI BASE MODEL is the same for everyone.
Personalization comes from:
1. SPPE pairs generated from workspace-specific queries
2. Workspace-specific model fine-tuning
3. Adaptation of thresholds/routing based on real usage patterns

This layer extracts insights from workspace interactions and creates
workspace-specific adapters without modifying the base model.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from uuid import uuid4
import json

logger = logging.getLogger(__name__)


# ============================================================================
# Workspace Usage Patterns
# ============================================================================

@dataclass
class QueryPattern:
    """Recurring query pattern in workspace"""
    pattern_id: str
    workspace_id: str
    
    # Pattern characteristics
    route: str  # e.g., "world_knowledge", "coding", "creative_text"
    query_keywords: List[str]  # Keywords that trigger this pattern
    avg_confidence: float
    avg_latency_ms: float
    avg_quality_score: float
    
    # Frequency
    occurrence_count: int
    last_occurrence: datetime
    
    # Optimization
    optimal_skip_t1: bool  # Should T1 be skipped for this pattern?
    optimal_skip_t2: bool  # Should T2 be skipped for this pattern?
    
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CapabilityUsage:
    """Usage statistics for each capability route"""
    workspace_id: str
    capability_route: str  # e.g., "world_knowledge", "coding", etc.
    
    total_queries: int = 0
    avg_latency_ms: float = 0.0
    avg_confidence: float = 0.0
    avg_quality_score: float = 0.0
    
    t1_skip_rate: float = 0.0  # What % of queries skipped T1
    t2_skip_rate: float = 0.0  # What % of queries skipped T2
    
    most_used_providers: List[str] = field(default_factory=list)
    
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class UserPreference:
    """Learned user preferences for workspace"""
    workspace_id: str
    user_id: str
    
    # Style preferences
    preferred_style: str  # "concise", "detailed", "technical", "casual"
    preferred_language: str = "english"
    
    # Response preferences
    prefer_sources: bool = True  # Show sources?
    prefer_confidence_scores: bool = True
    max_response_length: int = 1000
    
    # Learning preferences
    prefers_deterministic: bool = False  # Prefer no transformers if possible
    risk_tolerance: float = 0.5  # 0=conservative, 1=aggressive
    
    # Domain expertise
    expertise_areas: List[str] = field(default_factory=list)  # Areas user is expert in
    learning_interests: List[str] = field(default_factory=list)  # Areas they want to learn
    
    learned_from_interactions: int = 0  # How many interactions informed this
    last_updated: datetime = field(default_factory=datetime.utcnow)


# ============================================================================
# Personalization Engine
# ============================================================================

class PersonalizationEngine:
    """Learns from workspace usage and personalizes responses"""
    
    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id
        
        # Usage tracking
        self.query_patterns: Dict[str, QueryPattern] = {}
        self.capability_usage: Dict[str, CapabilityUsage] = {}
        self.user_preferences: Dict[str, UserPreference] = {}
        
        # Time window analysis
        self.analysis_window_days: int = 7  # Learn from past 7 days
        self.update_frequency_minutes: int = 60
        
        logger.info(f"✓ Personalization engine initialized for workspace: {workspace_id}")
    
    async def record_interaction(
        self,
        user_id: str,
        query: str,
        route: str,
        response: str,
        confidence: float,
        latency_ms: float,
        quality_score: float,
        t1_used: bool,
        t2_used: bool,
    ):
        """Record query interaction for learning"""
        
        # Extract keywords from query
        keywords = self._extract_keywords(query)
        
        # Find or create pattern
        pattern_key = f"{route}_{keywords[0]}" if keywords else route
        if pattern_key not in self.query_patterns:
            self.query_patterns[pattern_key] = QueryPattern(
                pattern_id=str(uuid4()),
                workspace_id=self.workspace_id,
                route=route,
                query_keywords=keywords,
                avg_confidence=confidence,
                avg_latency_ms=latency_ms,
                avg_quality_score=quality_score,
                occurrence_count=1,
                last_occurrence=datetime.utcnow(),
                optimal_skip_t1=confidence > 0.90 and quality_score > 0.85,
                optimal_skip_t2=confidence > 0.95 and quality_score > 0.88,
            )
        else:
            # Update pattern stats
            pattern = self.query_patterns[pattern_key]
            n = pattern.occurrence_count
            pattern.avg_confidence = (pattern.avg_confidence * n + confidence) / (n + 1)
            pattern.avg_latency_ms = (pattern.avg_latency_ms * n + latency_ms) / (n + 1)
            pattern.avg_quality_score = (pattern.avg_quality_score * n + quality_score) / (n + 1)
            pattern.occurrence_count += 1
            pattern.last_occurrence = datetime.utcnow()
            
            # Update skip decisions based on pattern
            if pattern.avg_confidence > 0.90 and pattern.avg_quality_score > 0.85:
                pattern.optimal_skip_t1 = True
            if pattern.avg_confidence > 0.95 and pattern.avg_quality_score > 0.88:
                pattern.optimal_skip_t2 = True
        
        # Update capability usage
        if route not in self.capability_usage:
            self.capability_usage[route] = CapabilityUsage(
                workspace_id=self.workspace_id,
                capability_route=route,
                total_queries=1,
                avg_latency_ms=latency_ms,
                avg_confidence=confidence,
                avg_quality_score=quality_score,
                t1_skip_rate=0.0 if t1_used else 1.0,
                t2_skip_rate=0.0 if t2_used else 1.0,
            )
        else:
            # Update usage stats
            usage = self.capability_usage[route]
            n = usage.total_queries
            usage.avg_confidence = (usage.avg_confidence * n + confidence) / (n + 1)
            usage.avg_latency_ms = (usage.avg_latency_ms * n + latency_ms) / (n + 1)
            usage.avg_quality_score = (usage.avg_quality_score * n + quality_score) / (n + 1)
            
            # Update skip rates
            total_skipped = usage.t1_skip_rate * n
            if not t1_used:
                total_skipped += 1
            usage.t1_skip_rate = total_skipped / (n + 1)
            
            total_skipped = usage.t2_skip_rate * n
            if not t2_used:
                total_skipped += 1
            usage.t2_skip_rate = total_skipped / (n + 1)
            
            usage.total_queries = n + 1
        
        # Update user preferences
        self._update_user_preferences(user_id, response, quality_score)
    
    def _extract_keywords(self, query: str, top_k: int = 3) -> List[str]:
        """Extract important keywords from query"""
        # Simple implementation - in production would use NLP
        words = query.lower().split()
        stop_words = {"what", "how", "why", "is", "the", "a", "and", "or", "to", "for"}
        keywords = [w for w in words if w not in stop_words and len(w) > 3]
        return keywords[:top_k]
    
    def _update_user_preferences(self, user_id: str, response: str, quality_score: float):
        """Update learned user preferences"""
        if user_id not in self.user_preferences:
            self.user_preferences[user_id] = UserPreference(
                workspace_id=self.workspace_id,
                user_id=user_id,
            )
        
        pref = self.user_preferences[user_id]
        pref.learned_from_interactions += 1
        
        # Infer style from response length and characteristics
        if len(response) < 100:
            if pref.preferred_style != "detailed":
                pref.preferred_style = "concise"
        elif len(response) > 500:
            if pref.preferred_style != "concise":
                pref.preferred_style = "detailed"
    
    def get_personalized_config(self) -> Dict[str, Any]:
        """Generate personalized configuration for workspace"""
        
        # Calculate aggregate statistics
        patterns = list(self.query_patterns.values())
        if not patterns:
            return {
                "t1_skip_threshold": 0.90,
                "t2_skip_threshold": 0.95,
                "recommendations": []
            }
        
        # Average skip rates across patterns
        avg_t1_skip_quality = sum(p.avg_quality_score for p in patterns if p.optimal_skip_t1) / max(len([p for p in patterns if p.optimal_skip_t1]), 1)
        avg_t2_skip_quality = sum(p.avg_quality_score for p in patterns if p.optimal_skip_t2) / max(len([p for p in patterns if p.optimal_skip_t2]), 1)
        
        # Adaptive thresholds based on workspace patterns
        # If workspace queries are consistently high confidence, lower thresholds
        avg_confidence = sum(p.avg_confidence for p in patterns) / len(patterns)
        
        t1_threshold = 0.90 - (avg_confidence - 0.85) * 0.10  # Lower for high-confidence workspaces
        t2_threshold = 0.95 - (avg_confidence - 0.90) * 0.10
        
        t1_threshold = max(0.70, min(0.95, t1_threshold))  # Clamp to reasonable range
        t2_threshold = max(0.80, min(0.98, t2_threshold))
        
        # Recommendations based on patterns
        recommendations = []
        
        # Find patterns that always skip T1
        always_skip_t1 = [p for p in patterns if p.optimal_skip_t1]
        if len(always_skip_t1) > len(patterns) * 0.7:
            recommendations.append({
                "type": "optimization",
                "suggestion": "Lower T1 skip threshold - most queries are high confidence",
                "impact": "10-20% cost reduction",
            })
        
        # Find slow capabilities
        slow_capabilities = [
            (c, u.avg_latency_ms)
            for c, u in self.capability_usage.items()
            if u.avg_latency_ms > 500
        ]
        if slow_capabilities:
            recommendations.append({
                "type": "performance",
                "suggestion": f"Optimize slow capabilities: {[c for c, _ in slow_capabilities]}",
                "impact": "Faster responses",
            })
        
        # Find low-quality capabilities
        low_quality = [
            (c, u.avg_quality_score)
            for c, u in self.capability_usage.items()
            if u.avg_quality_score < 0.75
        ]
        if low_quality:
            recommendations.append({
                "type": "quality",
                "suggestion": f"Investigate quality issues in: {[c for c, _ in low_quality]}",
                "impact": "Better responses",
            })
        
        return {
            "t1_skip_threshold": t1_threshold,
            "t2_skip_threshold": t2_threshold,
            "avg_confidence": avg_confidence,
            "avg_quality": sum(p.avg_quality_score for p in patterns) / len(patterns),
            "patterns_discovered": len(patterns),
            "recommendations": recommendations,
            "generated_at": datetime.utcnow().isoformat(),
        }
    
    def get_capability_insights(self, route: str) -> Dict[str, Any]:
        """Get detailed insights for specific capability"""
        usage = self.capability_usage.get(route)
        if not usage:
            return {"error": f"No data for route: {route}"}
        
        patterns = [p for p in self.query_patterns.values() if p.route == route]
        
        return {
            "route": route,
            "total_queries": usage.total_queries,
            "avg_latency_ms": usage.avg_latency_ms,
            "avg_confidence": usage.avg_confidence,
            "avg_quality_score": usage.avg_quality_score,
            "t1_skip_rate": usage.t1_skip_rate,
            "t2_skip_rate": usage.t2_skip_rate,
            "patterns": len(patterns),
            "most_common_patterns": sorted(
                [(p.query_keywords, p.occurrence_count) for p in patterns],
                key=lambda x: x[1],
                reverse=True
            )[:5],
        }
    
    def get_user_insights(self, user_id: str) -> Dict[str, Any]:
        """Get user-specific insights"""
        pref = self.user_preferences.get(user_id)
        if not pref:
            return {"error": f"No data for user: {user_id}"}
        
        return {
            "user_id": user_id,
            "preferred_style": pref.preferred_style,
            "preferred_language": pref.preferred_language,
            "expertise_areas": pref.expertise_areas,
            "learning_interests": pref.learning_interests,
            "interactions_analyzed": pref.learned_from_interactions,
            "preferences": {
                "show_sources": pref.prefer_sources,
                "show_confidence": pref.prefer_confidence_scores,
                "prefer_deterministic": pref.prefers_deterministic,
                "risk_tolerance": pref.risk_tolerance,
            }
        }


# ============================================================================
# Workspace Adaptation Layer
# ============================================================================

class WorkspaceAdapterModel:
    """
    Adapter model for workspace-specific customization
    
    Keeps base model frozen, adds lightweight workspace-specific layers:
    - Threshold adjustment based on usage patterns
    - Route-specific routing adjustments
    - Capability weighting
    """
    
    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id
        self.base_model_version = "phase5-base"
        
        # Lightweight adapter parameters (not a full model)
        self.t1_skip_adjustment: float = 0.0  # Can lower thresholds
        self.t2_skip_adjustment: float = 0.0
        
        self.route_weights: Dict[str, float] = {}  # Preference for routes
        self.provider_preferences: Dict[str, float] = {}  # Preference for providers
        
        self.created_at = datetime.utcnow()
        self.training_pairs_used = 0
        self.accuracy_on_workspace_data = 0.0
    
    def update_from_sppe_pairs(self, sppe_pairs: List[Dict[str, Any]]):
        """Update adapter from workspace SPPE pairs (lightweight adjustment)"""
        if not sppe_pairs:
            return
        
        # Analyze pair patterns
        routes = {}
        providers = {}
        quality_scores = []
        
        for pair in sppe_pairs:
            route = pair.get("route", "unknown")
            provider = pair.get("provider", "unknown")
            quality = pair.get("quality_score", 0.0)
            
            routes[route] = routes.get(route, 0) + 1
            providers[provider] = providers.get(provider, 0) + 1
            quality_scores.append(quality)
        
        # Calculate weights based on success
        for route, count in routes.items():
            self.route_weights[route] = count / len(sppe_pairs)
        
        for provider, count in providers.items():
            self.provider_preferences[provider] = count / len(sppe_pairs)
        
        # Adjust thresholds if consistently high quality
        avg_quality = sum(quality_scores) / len(quality_scores)
        if avg_quality > 0.88:
            self.t1_skip_adjustment = -0.05  # Can skip more aggressively
            self.t2_skip_adjustment = -0.05
        elif avg_quality < 0.80:
            self.t1_skip_adjustment = 0.05  # More conservative
            self.t2_skip_adjustment = 0.05
        
        self.training_pairs_used = len(sppe_pairs)
        self.accuracy_on_workspace_data = avg_quality
        
        logger.info(
            f"✓ Adapter updated: {self.workspace_id} "
            f"(pairs={len(sppe_pairs)}, accuracy={avg_quality:.2f})"
        )
    
    def get_adjusted_thresholds(self, base_t1: float, base_t2: float) -> Tuple[float, float]:
        """Get thresholds adjusted for this workspace"""
        adjusted_t1 = max(0.70, min(0.98, base_t1 + self.t1_skip_adjustment))
        adjusted_t2 = max(0.80, min(0.99, base_t2 + self.t2_skip_adjustment))
        return adjusted_t1, adjusted_t2
    
    def get_route_preference(self, route: str) -> float:
        """Get workspace's preference for specific route (0-1)"""
        return self.route_weights.get(route, 0.5)
    
    def get_provider_preference(self, provider: str) -> float:
        """Get workspace's preference for specific provider (0-1)"""
        return self.provider_preferences.get(provider, 0.5)


# Singleton per workspace
_personalization_engines: Dict[str, PersonalizationEngine] = {}
_workspace_adapters: Dict[str, WorkspaceAdapterModel] = {}


def get_personalization_engine(workspace_id: str) -> PersonalizationEngine:
    """Get personalization engine for workspace"""
    if workspace_id not in _personalization_engines:
        _personalization_engines[workspace_id] = PersonalizationEngine(workspace_id)
    return _personalization_engines[workspace_id]


def get_workspace_adapter(workspace_id: str) -> WorkspaceAdapterModel:
    """Get workspace adapter model"""
    if workspace_id not in _workspace_adapters:
        _workspace_adapters[workspace_id] = WorkspaceAdapterModel(workspace_id)
    return _workspace_adapters[workspace_id]
