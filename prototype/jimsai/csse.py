from __future__ import annotations

import re

from .models import VerifiedCognitiveObject


class ConstrainedSemanticSynthesisEngine:
    def render(self, obj: VerifiedCognitiveObject) -> str:
        sourced_steps = [
            step
            for step in obj.reasoning_chain
            if step.sources and not step.claim.lower().startswith("retrieved signature ")
        ]
        fallback_steps = [
            step
            for step in obj.reasoning_chain
            if step.relation != "HEDGE" and not step.claim.lower().startswith("retrieved signature ")
        ]
        user_facing_steps = sourced_steps or fallback_steps

        lines: list[str] = []
        if user_facing_steps:
            lines.append("Here's what I can verify from memory:")
            summary = self._summary_sentence(user_facing_steps)
            if summary:
                lines.append(summary)
                lines.append("")
            for step in user_facing_steps:
                lines.append(f"- {self._clean_claim(step.claim)}")
        else:
            if obj.sources:
                lines.append("I found related memory, but it does not yet contain a directly answerable verified claim.")
            else:
                lines.append("I do not have verified memory signatures for a factual answer yet.")

        if obj.simulation_results and self._should_show_simulation(obj):
            lines.append("")
            lines.append("Simulation:")
            for sim in obj.simulation_results:
                status = "passed" if sim.passed else "failed"
                lines.append(f"- {sim.scenario} {status} at confidence {sim.confidence:.2f}.")
                for outcome in sim.outcomes[:4]:
                    lines.append(f"  - {outcome}")
        if obj.knowledge_gaps:
            lines.append("")
            lines.append("Explicit gaps:")
            for gap in self._unique(obj.knowledge_gaps):
                lines.append(f"- {gap}")
        lines.append("")
        lines.append(f"Confidence: {obj.confidence:.2f}")
        if obj.sources:
            lines.append("")
            lines.append("Source signatures:")
            for source in obj.sources:
                lines.append(f"- {source}")
        return "\n".join(lines)

    def _summary_sentence(self, steps) -> str:
        claims = [self._clean_claim(step.claim) for step in steps if step.claim]
        if not claims:
            return ""
        causal_path = self._causal_path(claims)
        if causal_path:
            return f"Verified path: {' -> '.join(causal_path)}."
        if len(claims) == 1:
            return claims[0]
        return " ".join(claims[:3])

    def _causal_path(self, claims: list[str]) -> list[str]:
        edges: list[tuple[str, str]] = []
        for claim in claims:
            match = re.fullmatch(r"(.+?) causes (.+?)\.", claim)
            if not match:
                return []
            edges.append((match.group(1), match.group(2)))
        if not edges:
            return []
        path = [edges[0][0], edges[0][1]]
        for source, target in edges[1:]:
            if source != path[-1]:
                return []
            path.append(target)
        return path

    def _clean_claim(self, claim: str) -> str:
        cleaned = claim.strip()
        if not cleaned:
            return ""
        return cleaned if cleaned.endswith((".", "?", "!")) else f"{cleaned}."

    def _should_show_simulation(self, obj: VerifiedCognitiveObject) -> bool:
        if not obj.simulation_results:
            return False
        relations = {step.relation for step in obj.reasoning_chain}
        if relations & {"CAUSES", "DEPENDS_ON"}:
            return True
        return any(not sim.passed for sim in obj.simulation_results)

    def _unique(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        output: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            output.append(value)
        return output
