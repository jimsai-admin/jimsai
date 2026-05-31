"""
Metrics and Improvement Reporting

Tracks system improvements after each training cycle and generates
directive-format reports for human consumption.

Reports measure:
- Intent stability across all languages
- Provider dependency reduction
- Retrieval accuracy improvement
- World model confidence growth
- Capability coverage expansion
- Overall system maturity progression
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any

from .autonomous_training_agent import SystemState
from .event_store import AuditEventStore
from .models import utc_now


logger = logging.getLogger(__name__)


@dataclass
class MetricSnapshot:
    """Snapshot of metrics at a point in time."""

    timestamp: str
    intent_stability: float
    provider_dependency: float
    retrieval_accuracy: float
    world_model_confidence: float
    language_coverage: dict[str, float]
    domain_coverage: dict[str, float]
    capability_coverage: dict[str, float]


@dataclass
class ImprovementReport:
    """Report showing improvements after deployment."""

    cycle_number: int
    deployment_id: str
    timestamp: str
    
    # Metrics before and after
    before: MetricSnapshot
    after: MetricSnapshot
    
    # Deltas
    intent_stability_delta: float
    provider_dependency_delta: float
    retrieval_accuracy_delta: float
    world_model_confidence_delta: float
    
    # Overall assessment
    overall_improvement_pct: float
    quality_level: str  # "critical", "low", "good", "excellent"
    
    # Recommendations
    recommendations: list[str]


class MetricsCollector:
    """
    Collects and tracks metrics over time.
    
    Maintains history of system state snapshots and computes
    improvement metrics between deployments.
    """

    def __init__(self):
        self.snapshots: list[MetricSnapshot] = []
        self.event_store = AuditEventStore()

    def record_snapshot(self, state: SystemState) -> None:
        """Record a system state snapshot."""
        
        snapshot = MetricSnapshot(
            timestamp=state.timestamp.isoformat(),
            intent_stability=state.intent_stability_score,
            provider_dependency=state.provider_dependency_rate,
            retrieval_accuracy=state.retrieval_accuracy,
            world_model_confidence=state.world_model_confidence_avg,
            language_coverage=state.language_variant_scores,
            domain_coverage=state.domain_coverage,
            capability_coverage=state.capability_coverage,
        )
        
        self.snapshots.append(snapshot)
        
        self.event_store.append(
            "metrics_snapshot",
            f"snapshot-{len(self.snapshots)}",
            asdict(snapshot),
        )

    def compute_improvement(
        self,
        before: MetricSnapshot,
        after: MetricSnapshot,
        deployment_id: str,
        cycle_number: int,
    ) -> ImprovementReport:
        """Compute improvement metrics between two snapshots."""
        
        # Compute deltas
        intent_delta = after.intent_stability - before.intent_stability
        provider_delta = before.provider_dependency - after.provider_dependency  # Lower is better
        retrieval_delta = after.retrieval_accuracy - before.retrieval_accuracy
        world_model_delta = after.world_model_confidence - before.world_model_confidence
        
        # Overall improvement percentage (weighted)
        weights = {
            "intent_stability": 0.25,
            "provider_dependency": 0.25,
            "retrieval_accuracy": 0.25,
            "world_model": 0.25,
        }
        
        overall_improvement = (
            (intent_delta * 100) * weights["intent_stability"] +
            (provider_delta * 100) * weights["provider_dependency"] +
            (retrieval_delta * 100) * weights["retrieval_accuracy"] +
            (world_model_delta * 100) * weights["world_model"]
        )
        
        # Assess quality level
        if overall_improvement > 5.0:
            quality_level = "excellent"
        elif overall_improvement > 2.0:
            quality_level = "good"
        elif overall_improvement > 0.5:
            quality_level = "low"
        else:
            quality_level = "critical"  # No improvement or regression
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            after=after,
            intent_delta=intent_delta,
            provider_delta=provider_delta,
            retrieval_delta=retrieval_delta,
            world_model_delta=world_model_delta,
        )
        
        report = ImprovementReport(
            cycle_number=cycle_number,
            deployment_id=deployment_id,
            timestamp=utc_now().isoformat(),
            before=before,
            after=after,
            intent_stability_delta=intent_delta,
            provider_dependency_delta=provider_delta,
            retrieval_accuracy_delta=retrieval_delta,
            world_model_confidence_delta=world_model_delta,
            overall_improvement_pct=overall_improvement,
            quality_level=quality_level,
            recommendations=recommendations,
        )
        
        return report

    def _generate_recommendations(
        self,
        after: MetricSnapshot,
        **deltas,
    ) -> list[str]:
        """Generate actionable recommendations based on metrics."""
        
        recommendations = []
        
        # Intent stability recommendations
        if after.intent_stability < 0.85:
            recommendations.append(
                "🔴 Intent stability below 0.85 threshold. Target synthetic generation "
                "to improve intent classifier. Consider edge case dataset collection."
            )
        elif deltas["intent_delta"] < 0:
            recommendations.append(
                "⚠️ Intent stability regressed. Review recent training data for quality issues. "
                "Consider rolling back if delta < -0.02."
            )
        
        # Provider dependency recommendations
        if after.provider_dependency > 0.15:
            recommendations.append(
                "🔴 Provider dependency above 15% threshold. Target world knowledge gaps. "
                "Prioritize Wikipedia ingestion and domain-specific data."
            )
        elif deltas["provider_delta"] < 0.02:
            recommendations.append(
                "⚠️ Provider dependency not improving. World model candidates need review. "
                "Check quality of human approvals in training UI."
            )
        
        # Retrieval accuracy recommendations
        if after.retrieval_accuracy < 0.80:
            recommendations.append(
                "🔴 Retrieval accuracy below 0.80 threshold. Review memory signatures. "
                "Consider re-indexing and re-embedding corpus."
            )
        
        # World model recommendations
        if after.world_model_confidence < 0.75:
            recommendations.append(
                "🔴 World model confidence below 0.75 threshold. Generate more causal data. "
                "Increase human review of medium-confidence candidates."
            )
        
        # Language coverage recommendations
        weak_languages = [
            lang for lang, score in after.language_coverage.items()
            if score < 0.70
        ]
        if weak_languages:
            recommendations.append(
                f"📍 Language coverage gaps: {', '.join(weak_languages)}. "
                f"Prioritize OpenSubtitles ingestion for these languages."
            )
        
        # Domain coverage recommendations
        weak_domains = [
            domain for domain, score in after.domain_coverage.items()
            if score < 0.65
        ]
        if weak_domains:
            recommendations.append(
                f"📍 Domain coverage gaps: {', '.join(weak_domains)}. "
                f"Curate domain-specific Wikipedia articles and literature."
            )
        
        # If no recommendations needed
        if not recommendations:
            recommendations.append(
                "✅ System metrics healthy. Continue current ingestion strategy. "
                "Monitor language variants for coverage expansion."
            )
        
        return recommendations

    def get_metric_history(self, metric_name: str, limit: int | None = None) -> list[tuple[str, float]]:
        """Get history of a specific metric."""
        
        snapshots = self.snapshots[-limit:] if limit else self.snapshots
        
        results = []
        for snapshot in snapshots:
            value = getattr(snapshot, metric_name, None)
            if value is not None:
                results.append((snapshot.timestamp, value))
        
        return results


class ReportFormatter:
    """
    Formats reports in directive format for human consumption.
    """

    @staticmethod
    def format_improvement_report(report: ImprovementReport) -> str:
        """Format improvement report as directive text."""
        
        lines = [
            "",
            "=" * 90,
            f"IMPROVEMENT REPORT — CYCLE #{report.cycle_number}",
            f"Deployment: {report.deployment_id}",
            f"Timestamp: {report.timestamp}",
            "=" * 90,
            "",
            "KEY FINDINGS:",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
        ]
        
        # Quality assessment
        emoji = {
            "excellent": "🌟",
            "good": "✅",
            "low": "⚠️",
            "critical": "🔴",
        }
        
        lines.append(f"{emoji.get(report.quality_level, '❓')} Quality Level: {report.quality_level.upper()}")
        lines.append(f"Overall Improvement: {report.overall_improvement_pct:+.2f}%")
        lines.append("")
        
        # Metric deltas
        lines.append("METRIC CHANGES:")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        def format_delta(label: str, before: float, after: float, delta: float, is_pct: bool = False) -> str:
            fmt = "{:.2%" if is_pct else "{:.4f}"
            arrow = "📈" if delta > 0 else "📉" if delta < 0 else "➡️"
            delta_fmt = "{:+.2%}" if is_pct else "{:+.4f}"
            return f"{label:.<40} {fmt.format(before)} → {fmt.format(after)} {arrow} {delta_fmt.format(delta)}"
        
        lines.append(format_delta(
            "Intent Stability Score",
            report.before.intent_stability,
            report.after.intent_stability,
            report.intent_stability_delta,
        ))
        
        lines.append(format_delta(
            "Provider Dependency Rate",
            report.before.provider_dependency,
            report.after.provider_dependency,
            report.provider_dependency_delta,
            is_pct=True,
        ))
        
        lines.append(format_delta(
            "Retrieval Accuracy",
            report.before.retrieval_accuracy,
            report.after.retrieval_accuracy,
            report.retrieval_accuracy_delta,
            is_pct=True,
        ))
        
        lines.append(format_delta(
            "World Model Confidence",
            report.before.world_model_confidence,
            report.after.world_model_confidence,
            report.world_model_confidence_delta,
        ))
        
        lines.append("")
        
        # Recommendations
        lines.append("DIRECTIVES FOR NEXT CYCLE:")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")
        
        for i, rec in enumerate(report.recommendations, 1):
            lines.append(f"{i}. {rec}")
            lines.append("")
        
        lines.append("=" * 90)
        lines.append("")
        
        return "\n".join(lines)

    @staticmethod
    def format_system_state_report(state: SystemState) -> str:
        """Format current system state as report."""
        
        lines = [
            "",
            "=" * 90,
            "SYSTEM STATE REPORT",
            f"Timestamp: {state.timestamp.isoformat()}",
            "=" * 90,
            "",
            "CORE METRICS:",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"Intent Stability Score ............... {state.intent_stability_score:.4f}",
            f"Provider Dependency Rate ............ {state.provider_dependency_rate:.2%}",
            f"Retrieval Accuracy .................. {state.retrieval_accuracy:.2%}",
            f"World Model Confidence Average ..... {state.world_model_confidence_avg:.4f}",
            f"Review Queue Depth .................. {state.review_queue_depth} items",
            f"SPPE Pairs Ready .................... {state.sppe_pairs_ready}",
            "",
            "LANGUAGE COVERAGE:",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]
        
        for lang, score in sorted(state.language_variant_scores.items(), key=lambda x: -x[1]):
            status = "✅" if score >= 0.70 else "⚠️" if score >= 0.50 else "🔴"
            lines.append(f"{status} {lang:.<10} {score:.2%}")
        
        lines.append("")
        lines.append("DOMAIN COVERAGE:")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        for domain, score in sorted(state.domain_coverage.items(), key=lambda x: -x[1]):
            status = "✅" if score >= 0.65 else "⚠️" if score >= 0.50 else "🔴"
            lines.append(f"{status} {domain:.<30} {score:.2%}")
        
        lines.append("")
        lines.append("CAPABILITY COVERAGE:")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        for capability, score in sorted(state.capability_coverage.items(), key=lambda x: -x[1]):
            status = "✅" if score >= 0.70 else "⚠️" if score >= 0.60 else "🔴"
            lines.append(f"{status} {capability:.<30} {score:.2%}")
        
        lines.append("")
        lines.append("=" * 90)
        lines.append("")
        
        return "\n".join(lines)


def export_report_to_file(report: ImprovementReport, filepath: str) -> None:
    """Export improvement report to file."""
    
    formatter = ReportFormatter()
    text = formatter.format_improvement_report(report)
    
    with open(filepath, "w") as f:
        f.write(text)
        f.write("\n\nJSON EXPORT:\n")
        f.write("=" * 90)
        f.write("\n")
        json.dump(asdict(report), f, indent=2, default=str)
    
    logger.info(f"📄 Report exported to {filepath}")
