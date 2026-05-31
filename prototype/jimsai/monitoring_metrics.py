"""
Monitoring and Metrics Dashboard for JimsAI Autonomous Training Agent

Tracks:
- System performance metrics (CPU, memory, disk)
- Application metrics (requests, latency, errors)
- Autonomous agent metrics (cycle time, throughput, gaps)
- Data quality metrics (SPPE confidence, world model quality)
- Training progress metrics (batch size, improvement)

Integrations:
- Prometheus: Metrics collection
- Grafana: Visualization
- AlertManager: Alerting
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Any

from prometheus_client import Counter, Gauge, Histogram, Summary
import psutil


logger = logging.getLogger(__name__)


# ============================================================================
# PROMETHEUS METRICS DEFINITIONS
# ============================================================================

# HTTP Request Metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['endpoint'],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0)
)

http_request_errors_total = Counter(
    'http_request_errors_total',
    'Total HTTP errors',
    ['endpoint', 'error_type']
)

# Autonomous Agent Metrics
agent_cycle_duration_seconds = Gauge(
    'agent_cycle_duration_seconds',
    'Duration of one complete agent cycle'
)

agent_cycle_number = Gauge(
    'agent_cycle_number',
    'Current agent cycle number'
)

agent_sppe_pairs_generated = Gauge(
    'agent_sppe_pairs_generated',
    'Total SPPE pairs generated'
)

agent_sppe_pairs_ready = Gauge(
    'agent_sppe_pairs_ready',
    'SPPE pairs ready for training'
)

agent_world_models_generated = Gauge(
    'agent_world_models_generated',
    'Total world models generated'
)

agent_training_cycles = Gauge(
    'agent_training_cycles',
    'Total training cycles completed'
)

agent_gap_count = Gauge(
    'agent_gap_count',
    'Number of identified gaps',
    ['gap_type']
)

# System Metrics
system_cpu_percent = Gauge(
    'system_cpu_percent',
    'CPU usage percentage'
)

system_memory_percent = Gauge(
    'system_memory_percent',
    'Memory usage percentage'
)

system_disk_percent = Gauge(
    'system_disk_percent',
    'Disk usage percentage',
    ['mount_point']
)

system_network_io_bytes = Counter(
    'system_network_io_bytes',
    'Network I/O bytes',
    ['direction']  # 'sent' or 'recv'
)

# Data Source Connector Metrics
data_source_documents_fetched = Counter(
    'data_source_documents_fetched',
    'Documents fetched from data sources',
    ['source']
)

data_source_fetch_errors = Counter(
    'data_source_fetch_errors',
    'Errors fetching from data sources',
    ['source', 'error_type']
)

data_source_fetch_duration_seconds = Histogram(
    'data_source_fetch_duration_seconds',
    'Time to fetch documents from source',
    ['source'],
    buckets=(0.1, 0.5, 1.0, 5.0, 10.0)
)

# Ingestion Metrics
ingestion_documents_processed = Counter(
    'ingestion_documents_processed',
    'Documents processed by ingestion pipeline',
    ['status']  # 'success' or 'error'
)

ingestion_pipeline_duration_seconds = Histogram(
    'ingestion_pipeline_duration_seconds',
    'Time to process one document',
    buckets=(0.1, 0.5, 1.0, 5.0, 10.0, 30.0)
)

ingestion_worker_pool_utilization = Gauge(
    'ingestion_worker_pool_utilization',
    'Worker pool utilization percentage'
)

# System State Metrics
jimsai_intent_stability_score = Gauge(
    'jimsai_intent_stability_score',
    'JimsAI intent stability score (0-1)'
)

jimsai_provider_dependency_rate = Gauge(
    'jimsai_provider_dependency_rate',
    'JimsAI provider dependency rate (0-1)'
)

jimsai_retrieval_accuracy = Gauge(
    'jimsai_retrieval_accuracy',
    'JimsAI retrieval accuracy (0-1)'
)

jimsai_world_model_confidence = Gauge(
    'jimsai_world_model_confidence',
    'JimsAI world model confidence (0-1)'
)

jimsai_language_variant_score = Gauge(
    'jimsai_language_variant_score',
    'JimsAI language variant scores',
    ['language']
)

jimsai_domain_coverage_score = Gauge(
    'jimsai_domain_coverage_score',
    'JimsAI domain coverage scores',
    ['domain']
)

jimsai_capability_coverage_score = Gauge(
    'jimsai_capability_coverage_score',
    'JimsAI capability coverage scores',
    ['capability']
)

# Training Metrics
training_sppe_confidence_avg = Gauge(
    'training_sppe_confidence_avg',
    'Average SPPE pair confidence'
)

training_world_model_quality_avg = Gauge(
    'training_world_model_quality_avg',
    'Average world model quality'
)

training_human_acceptance_rate = Gauge(
    'training_human_acceptance_rate',
    'Human acceptance rate for review queue items'
)

training_correction_rate = Gauge(
    'training_correction_rate',
    'Rate of corrections submitted by humans'
)

# Database Metrics
database_connection_pool_size = Gauge(
    'database_connection_pool_size',
    'Database connection pool size'
)

database_active_connections = Gauge(
    'database_active_connections',
    'Active database connections'
)

database_query_duration_seconds = Histogram(
    'database_query_duration_seconds',
    'Database query duration',
    ['query_type'],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0)
)

# Cache Metrics
cache_hits_total = Counter(
    'cache_hits_total',
    'Total cache hits'
)

cache_misses_total = Counter(
    'cache_misses_total',
    'Total cache misses'
)

cache_hit_rate = Gauge(
    'cache_hit_rate',
    'Cache hit rate percentage'
)


# ============================================================================
# DATACLASSES FOR METRICS STORAGE
# ============================================================================

@dataclass
class SystemMetrics:
    """System resource utilization metrics."""
    
    timestamp: str
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    network_bytes_sent: int
    network_bytes_recv: int
    process_count: int
    
    @classmethod
    def collect(cls) -> SystemMetrics:
        """Collect current system metrics."""
        cpu = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory().percent
        disk = psutil.disk_usage('/').percent
        
        net = psutil.net_io_counters()
        
        return cls(
            timestamp=datetime.utcnow().isoformat(),
            cpu_percent=cpu,
            memory_percent=memory,
            disk_percent=disk,
            network_bytes_sent=net.bytes_sent,
            network_bytes_recv=net.bytes_recv,
            process_count=len(psutil.pids()),
        )


@dataclass
class AgentMetrics:
    """Autonomous agent performance metrics."""
    
    timestamp: str
    cycle_number: int
    cycle_duration_seconds: float
    sppe_pairs_generated: int
    sppe_pairs_ready: int
    world_models_generated: int
    training_cycles_completed: int
    active_gaps: int
    average_gap_priority: float
    
    @classmethod
    def create_from_agent(cls, agent: Any) -> AgentMetrics:
        """Create metrics snapshot from agent state."""
        gaps = agent.identified_gaps or []
        avg_priority = sum(g.priority for g in gaps) / len(gaps) if gaps else 0
        
        return cls(
            timestamp=datetime.utcnow().isoformat(),
            cycle_number=len(agent.ingestion_history),
            cycle_duration_seconds=0,  # Would be computed from history
            sppe_pairs_generated=agent.current_state.sppe_pairs_ready if agent.current_state else 0,
            sppe_pairs_ready=agent.current_state.sppe_pairs_ready if agent.current_state else 0,
            world_models_generated=0,  # Would track from history
            training_cycles_completed=len(agent.training_cycles),
            active_gaps=len(gaps),
            average_gap_priority=avg_priority,
        )


@dataclass
class DataSourceMetrics:
    """Data source connector metrics."""
    
    timestamp: str
    source: str
    documents_fetched: int
    fetch_errors: int
    average_fetch_time_seconds: float
    availability: float  # 0-1


@dataclass
class IngestionMetrics:
    """Document ingestion pipeline metrics."""
    
    timestamp: str
    documents_processed: int
    documents_failed: int
    average_processing_time_seconds: float
    throughput_docs_per_second: float
    worker_pool_utilization: float


@dataclass
class TrainingMetrics:
    """Training and quality metrics."""
    
    timestamp: str
    sppe_confidence_avg: float
    world_model_quality_avg: float
    human_acceptance_rate: float
    correction_rate: float
    review_queue_depth: int


# ============================================================================
# METRICS COLLECTOR
# ============================================================================

class MetricsCollector:
    """Centralized metrics collection and aggregation."""

    def __init__(self):
        self.system_metrics: list[SystemMetrics] = []
        self.agent_metrics: list[AgentMetrics] = []
        self.data_source_metrics: dict[str, list[DataSourceMetrics]] = {}
        self.ingestion_metrics: list[IngestionMetrics] = []
        self.training_metrics: list[TrainingMetrics] = []
        
        self.max_history = 10000  # Keep last 10k records
        logger.info("📊 Metrics collector initialized")

    def collect_system_metrics(self) -> None:
        """Collect and record system metrics."""
        metrics = SystemMetrics.collect()
        self.system_metrics.append(metrics)
        
        # Update Prometheus gauges
        system_cpu_percent.set(metrics.cpu_percent)
        system_memory_percent.set(metrics.memory_percent)
        system_disk_percent.labels(mount_point='/').set(metrics.disk_percent)
        
        # Keep history under limit
        if len(self.system_metrics) > self.max_history:
            self.system_metrics = self.system_metrics[-self.max_history:]

    def record_agent_metrics(self, agent_metrics: AgentMetrics) -> None:
        """Record agent metrics snapshot."""
        self.agent_metrics.append(agent_metrics)
        
        # Update Prometheus gauges
        agent_cycle_number.set(agent_metrics.cycle_number)
        agent_cycle_duration_seconds.set(agent_metrics.cycle_duration_seconds)
        agent_sppe_pairs_generated.set(agent_metrics.sppe_pairs_generated)
        agent_sppe_pairs_ready.set(agent_metrics.sppe_pairs_ready)
        agent_world_models_generated.set(agent_metrics.world_models_generated)
        agent_training_cycles.set(agent_metrics.training_cycles_completed)
        agent_gap_count.labels(gap_type='total').set(agent_metrics.active_gaps)
        
        # Keep history under limit
        if len(self.agent_metrics) > self.max_history:
            self.agent_metrics = self.agent_metrics[-self.max_history:]

    def record_data_source_metrics(self, metrics: DataSourceMetrics) -> None:
        """Record data source connector metrics."""
        if metrics.source not in self.data_source_metrics:
            self.data_source_metrics[metrics.source] = []
        
        self.data_source_metrics[metrics.source].append(metrics)
        
        # Update Prometheus counters
        data_source_documents_fetched.labels(source=metrics.source).inc(metrics.documents_fetched)
        data_source_fetch_errors.labels(source=metrics.source, error_type='general').inc(metrics.fetch_errors)
        
        # Keep history under limit
        if len(self.data_source_metrics[metrics.source]) > self.max_history:
            self.data_source_metrics[metrics.source] = self.data_source_metrics[metrics.source][-self.max_history:]

    def record_ingestion_metrics(self, metrics: IngestionMetrics) -> None:
        """Record ingestion pipeline metrics."""
        self.ingestion_metrics.append(metrics)
        
        # Update Prometheus metrics
        ingestion_documents_processed.labels(status='success').inc(metrics.documents_processed)
        ingestion_documents_processed.labels(status='error').inc(metrics.documents_failed)
        ingestion_worker_pool_utilization.set(metrics.worker_pool_utilization)
        
        # Keep history under limit
        if len(self.ingestion_metrics) > self.max_history:
            self.ingestion_metrics = self.ingestion_metrics[-self.max_history:]

    def record_training_metrics(self, metrics: TrainingMetrics) -> None:
        """Record training and quality metrics."""
        self.training_metrics.append(metrics)
        
        # Update Prometheus gauges
        training_sppe_confidence_avg.set(metrics.sppe_confidence_avg)
        training_world_model_quality_avg.set(metrics.world_model_quality_avg)
        training_human_acceptance_rate.set(metrics.human_acceptance_rate)
        training_correction_rate.set(metrics.correction_rate)
        
        # Keep history under limit
        if len(self.training_metrics) > self.max_history:
            self.training_metrics = self.training_metrics[-self.max_history:]

    def record_system_state(self, state: Any) -> None:
        """Record JimsAI system state metrics."""
        jimsai_intent_stability_score.set(state.intent_stability_score)
        jimsai_provider_dependency_rate.set(state.provider_dependency_rate)
        jimsai_retrieval_accuracy.set(state.retrieval_accuracy)
        jimsai_world_model_confidence.set(state.world_model_confidence_avg)
        
        # Language variants
        for lang, score in state.language_variant_scores.items():
            jimsai_language_variant_score.labels(language=lang).set(score)
        
        # Domain coverage
        for domain, score in state.domain_coverage.items():
            jimsai_domain_coverage_score.labels(domain=domain).set(score)
        
        # Capability coverage
        for capability, score in state.capability_coverage.items():
            jimsai_capability_coverage_score.labels(capability=capability).set(score)

    def get_metrics_summary(self, minutes: int = 60) -> dict[str, Any]:
        """Get summary of recent metrics."""
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        
        # Filter recent metrics
        recent_system = [
            m for m in self.system_metrics
            if datetime.fromisoformat(m.timestamp) > cutoff_time
        ]
        
        recent_agent = [
            m for m in self.agent_metrics
            if datetime.fromisoformat(m.timestamp) > cutoff_time
        ]
        
        recent_training = [
            m for m in self.training_metrics
            if datetime.fromisoformat(m.timestamp) > cutoff_time
        ]
        
        # Compute aggregates
        summary = {
            "period_minutes": minutes,
            "timestamp": datetime.utcnow().isoformat(),
            "system": {
                "avg_cpu_percent": sum(m.cpu_percent for m in recent_system) / len(recent_system) if recent_system else 0,
                "avg_memory_percent": sum(m.memory_percent for m in recent_system) / len(recent_system) if recent_system else 0,
                "avg_disk_percent": sum(m.disk_percent for m in recent_system) / len(recent_system) if recent_system else 0,
            },
            "agent": {
                "avg_cycle_duration": sum(m.cycle_duration_seconds for m in recent_agent) / len(recent_agent) if recent_agent else 0,
                "total_sppe_generated": sum(m.sppe_pairs_generated for m in recent_agent) if recent_agent else 0,
                "total_training_cycles": recent_agent[-1].training_cycles_completed if recent_agent else 0,
            },
            "training": {
                "avg_sppe_confidence": sum(m.sppe_confidence_avg for m in recent_training) / len(recent_training) if recent_training else 0,
                "avg_human_acceptance_rate": sum(m.human_acceptance_rate for m in recent_training) / len(recent_training) if recent_training else 0,
            },
        }
        
        return summary


# ============================================================================
# ALERTING RULES
# ============================================================================

class AlertRule:
    """Base class for alert rules."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.triggered = False
        self.triggered_at: datetime | None = None

    def check(self, metrics: Any) -> bool:
        """Check if alert should be triggered. Override in subclasses."""
        return False

    def trigger(self) -> None:
        """Trigger alert."""
        if not self.triggered:
            self.triggered = True
            self.triggered_at = datetime.utcnow()
            logger.warning(f"🚨 ALERT TRIGGERED: {self.name} - {self.description}")

    def resolve(self) -> None:
        """Resolve alert."""
        if self.triggered:
            self.triggered = False
            logger.info(f"✅ ALERT RESOLVED: {self.name}")


class HighCPUAlert(AlertRule):
    """Alert when CPU usage exceeds threshold."""

    def __init__(self, threshold: float = 85.0):
        super().__init__("HighCPU", f"CPU usage exceeds {threshold}%")
        self.threshold = threshold

    def check(self, metrics: SystemMetrics) -> bool:
        if metrics.cpu_percent > self.threshold:
            self.trigger()
            return True
        else:
            self.resolve()
            return False


class HighMemoryAlert(AlertRule):
    """Alert when memory usage exceeds threshold."""

    def __init__(self, threshold: float = 90.0):
        super().__init__("HighMemory", f"Memory usage exceeds {threshold}%")
        self.threshold = threshold

    def check(self, metrics: SystemMetrics) -> bool:
        if metrics.memory_percent > self.threshold:
            self.trigger()
            return True
        else:
            self.resolve()
            return False


class LowSystemStateAlert(AlertRule):
    """Alert when system state metrics drop below threshold."""

    def __init__(self, metric_name: str, threshold: float = 0.7):
        super().__init__(f"Low{metric_name}", f"{metric_name} below {threshold}")
        self.metric_name = metric_name
        self.threshold = threshold

    def check(self, state: Any) -> bool:
        value = getattr(state, self.metric_name.lower(), 0)
        if value < self.threshold:
            self.trigger()
            return True
        else:
            self.resolve()
            return False


class HighErrorRateAlert(AlertRule):
    """Alert when error rate exceeds threshold."""

    def __init__(self, threshold: float = 0.05):
        super().__init__("HighErrorRate", f"Error rate exceeds {threshold*100}%")
        self.threshold = threshold

    def check(self, metrics: Any) -> bool:
        # Would compute from HTTP metrics
        if hasattr(metrics, 'error_rate') and metrics.error_rate > self.threshold:
            self.trigger()
            return True
        else:
            self.resolve()
            return False


class AlertManager:
    """Manage alert rules and notifications."""

    def __init__(self):
        self.rules: dict[str, AlertRule] = {}
        self._register_default_rules()

    def _register_default_rules(self) -> None:
        """Register default alert rules."""
        self.rules['high_cpu'] = HighCPUAlert(threshold=85.0)
        self.rules['high_memory'] = HighMemoryAlert(threshold=90.0)
        self.rules['low_intent_stability'] = LowSystemStateAlert('intent_stability_score', 0.7)
        self.rules['low_retrieval_accuracy'] = LowSystemStateAlert('retrieval_accuracy', 0.8)

    def check_all(self, metrics: Any) -> list[str]:
        """Check all alert rules."""
        triggered = []
        for name, rule in self.rules.items():
            if rule.check(metrics):
                triggered.append(name)
        return triggered

    def add_rule(self, name: str, rule: AlertRule) -> None:
        """Add custom alert rule."""
        self.rules[name] = rule
        logger.info(f"Added alert rule: {name}")

    async def send_alert(self, alert_name: str, message: str) -> None:
        """Send alert notification (email, Slack, etc)."""
        logger.error(f"ALERT: {alert_name} - {message}")
        # In production: integrate with email, Slack, PagerDuty, etc.


# ============================================================================
# BACKGROUND COLLECTION TASK
# ============================================================================

async def metrics_collection_background_task(
    collector: MetricsCollector,
    alert_manager: AlertManager,
    agent: Any,
    interval_seconds: int = 60,
) -> None:
    """
    Background task to continuously collect and check metrics.
    
    Usage:
        import asyncio
        
        async def main():
            collector = MetricsCollector()
            alert_manager = AlertManager()
            
            # Run in background
            task = asyncio.create_task(
                metrics_collection_background_task(
                    collector, alert_manager, agent
                )
            )
    """
    logger.info(f"📊 Starting metrics collection task (interval: {interval_seconds}s)")
    
    while True:
        try:
            # Collect system metrics
            collector.collect_system_metrics()
            
            # Collect agent metrics
            if agent and hasattr(agent, 'current_state'):
                agent_metrics = AgentMetrics.create_from_agent(agent)
                collector.record_agent_metrics(agent_metrics)
                
                # Record system state
                if agent.current_state:
                    collector.record_system_state(agent.current_state)
            
            # Check alerts
            recent_system = collector.system_metrics[-1] if collector.system_metrics else None
            if recent_system:
                alert_manager.check_all(recent_system)
            
            await asyncio.sleep(interval_seconds)
            
        except Exception as e:
            logger.error(f"Error in metrics collection task: {e}")
            await asyncio.sleep(interval_seconds)


# ============================================================================
# GRAFANA DASHBOARD EXPORT
# ============================================================================

def generate_grafana_dashboard_json() -> dict[str, Any]:
    """Generate Grafana dashboard JSON for import."""
    
    return {
        "dashboard": {
            "title": "JimsAI Autonomous Training Agent",
            "panels": [
                {
                    "title": "System CPU Usage",
                    "targets": [
                        {
                            "expr": "system_cpu_percent",
                            "legendFormat": "CPU %"
                        }
                    ]
                },
                {
                    "title": "Agent Cycle Progress",
                    "targets": [
                        {
                            "expr": "agent_cycle_number",
                            "legendFormat": "Cycle Number"
                        }
                    ]
                },
                {
                    "title": "SPPE Pairs Ready",
                    "targets": [
                        {
                            "expr": "agent_sppe_pairs_ready",
                            "legendFormat": "Ready for Training"
                        }
                    ]
                },
                {
                    "title": "System Intent Stability",
                    "targets": [
                        {
                            "expr": "jimsai_intent_stability_score",
                            "legendFormat": "Stability Score"
                        }
                    ]
                },
                {
                    "title": "HTTP Request Latency",
                    "targets": [
                        {
                            "expr": "histogram_quantile(0.95, http_request_duration_seconds)",
                            "legendFormat": "p95 latency"
                        }
                    ]
                },
            ]
        }
    }
