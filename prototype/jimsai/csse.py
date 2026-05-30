from __future__ import annotations

from .models import VerifiedCognitiveObject


class ConstrainedSemanticSynthesisEngine:
    def render(self, obj: VerifiedCognitiveObject) -> str:
        lines: list[str] = []
        if obj.reasoning_chain:
            lines.append("Here's what I can verify from memory:")
            for step in obj.reasoning_chain:
                source_note = f"; sources={','.join(step.sources)}" if step.sources else "; sources=none"
                lines.append(f"- {step.claim} Confidence {step.confidence:.2f}{source_note}.")
        else:
            lines.append("I do not have verified memory signatures for a factual answer yet.")
        if obj.simulation_results:
            lines.append("")
            lines.append("Simulation:")
            for sim in obj.simulation_results:
                status = "passed" if sim.passed else "failed"
                lines.append(f"- {sim.scenario} {status} at confidence {sim.confidence:.2f}.")
                for outcome in sim.outcomes:
                    lines.append(f"  - {outcome}")
        if obj.knowledge_gaps:
            lines.append("")
            lines.append("Explicit gaps:")
            for gap in obj.knowledge_gaps:
                lines.append(f"- {gap}")
        if obj.sources:
            lines.append("")
            lines.append("Source signatures:")
            for source in obj.sources:
                lines.append(f"- {source}")
        return "\n".join(lines)
