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

        # Compute or read dynamic confidence tier
        tier = getattr(obj, "confidence_tier", 5)
        if tier == 5 and obj.confidence > 0.0:
            if obj.confidence >= 0.99:
                tier = 1
            elif obj.confidence >= 0.90:
                tier = 2
            elif obj.confidence >= 0.70:
                tier = 3
            elif obj.confidence >= 0.40:
                tier = 4
            else:
                tier = 5

        lines: list[str] = []
        
        # Prepend calculated Provenance Label
        provenance_labels = {
            1: "[Verified • Symbolic Solver]",
            2: "[High Confidence • Approved Memory]",
            3: "[Plausible • Learned Pattern]",
            4: "[Unverified • Needs Review]",
            5: "[Gap • Unresolved]"
        }
        lines.append(provenance_labels.get(tier, "[Gap • Unresolved]"))
        lines.append("")

        if user_facing_steps:
            if tier in {1, 2, 3}:
                lines.append("Here's what I can verify from memory:")
            summary = self._summary_sentence(user_facing_steps)
            if summary:
                # Prepend logical hedging qualifiers to Tier 3 claims
                if tier == 3:
                    summary = "Based on workspace patterns, it is likely that " + summary
                # Append warning tags and traceback links directly to Tier 4 outputs
                elif tier == 4:
                    source_id = obj.sources[0] if obj.sources else "unknown"
                    summary = f"{summary} ⚠️ [Unverified Memory] [Fix/Edit](file:///v1/memory/edit/{source_id})"
                
                lines.append(summary)
                lines.append("")
            if len(user_facing_steps) > 1:
                lines.append("Evidence:")
                for step in user_facing_steps[:6]:
                    lines.append(f"- {self._clean_claim(step.claim)}")
        else:
            if obj.sources:
                fallback_msg = "I found related memory, but it does not contain a directly answerable verified claim yet."
                if tier == 4:
                    source_id = obj.sources[0]
                    fallback_msg = f"{fallback_msg} ⚠️ [Unverified Memory] [Fix/Edit](file:///v1/memory/edit/{source_id})"
                lines.append(fallback_msg)
            else:
                lines.append("I do not have enough verified memory to answer that confidently yet.")

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
            lines.append("Gaps:")
            for gap in self._unique(obj.knowledge_gaps):
                lines.append(f"- {gap}")
        lines.append("")
        lines.append(f"Confidence: {obj.confidence:.2f}")
        if obj.sources:
            lines.append("")
            lines.append("Source signatures:")
            for source in obj.sources:
                lines.append(f"- [{source}](file:///v1/memory/edit/{source})")
        return "\n".join(lines)

    def _summary_sentence(self, steps) -> str:
        claims = [self._clean_claim(step.claim) for step in steps if step.claim]
        if not claims:
            return ""
        causal_path = self._causal_path(claims)
        if causal_path:
            return f"Verified path: {' -> '.join(causal_path)}."
        if len(claims) == 1:
            calculation = re.fullmatch(r"Verified calculation:\s*(.+?)\s*=\s*(.+?)\.?", claims[0])
            if calculation:
                expression = calculation.group(1).strip()
                result = calculation.group(2).strip()
                return (
                    f"The answer is **{result}**.\n\n"
                    f"Steps:\n"
                    f"- Start with `{expression}`.\n"
                    f"- Evaluate the expression with the verified symbolic solver.\n"
                    f"- Result: **{result}**.\n\n"
                    f"Calculation: `{expression} = {result}`"
                )
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
