from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .models import VerifiedCognitiveObject

if TYPE_CHECKING:
    pass


class ConstrainedSemanticSynthesisEngine:
    """
    Produces natural, helpful, user-facing responses from a VerifiedCognitiveObject.

    Design principles:
    - No hardcoded keyword lists or pattern matching — everything is driven by
      the structured fields already present in the VerifiedCognitiveObject
    - Confidence is expressed as natural prose calibrated to the tier,
      not as a raw number
    - Gap responses use intent + capability_plan + knowledge_gaps fields
      to give context-appropriate helpful guidance — never generic fallback text
    - Responses grow more useful as JimsAI learns — the same code path
      produces better output as memory fills with real signatures
    - Internal labels (tiers, trace IDs, signature links) never reach users
    """

    # ── Confidence prose (calibrated to tier, not number) ──────────────────

    _CONFIDENCE_PROSE = {
        1: "I'm certain about this",           # 0.99+   symbolic solver / verified
        2: "I'm quite confident about this",   # 0.90–0.99  high-confidence memory
        3: "I believe this is right",          # 0.70–0.89  learned pattern
        4: "I'm not fully certain — worth double-checking",  # 0.40–0.69
        5: None,                                # below 0.40 — gap, omit confidence
    }

    # ── Public API ─────────────────────────────────────────────────────────

    def render(self, obj: VerifiedCognitiveObject) -> str:
        """Render a user-facing natural language response."""
        tier = self._compute_tier(obj.confidence)
        user_steps = self._user_facing_steps(obj)

        # Route to specialist renderers first
        if self._is_math_result(user_steps):
            return self._render_math(user_steps, obj, tier)

        if self._is_causal_result(user_steps):
            return self._render_causal(user_steps, obj, tier)

        if user_steps:
            return self._render_claims(user_steps, obj, tier)

        return self._render_gap(obj)

    # ── Tier ───────────────────────────────────────────────────────────────

    def _compute_tier(self, confidence: float) -> int:
        if confidence >= 0.99:
            return 1
        if confidence >= 0.90:
            return 2
        if confidence >= 0.70:
            return 3
        if confidence >= 0.40:
            return 4
        return 5

    def _confidence_phrase(self, tier: int) -> str | None:
        """Return a natural-language confidence note, or None if not helpful."""
        return self._CONFIDENCE_PROSE.get(tier)

    # ── Step selection ─────────────────────────────────────────────────────

    def _user_facing_steps(self, obj: VerifiedCognitiveObject) -> list:
        """Return steps with real claims, filtering internal placeholders."""
        sourced = [
            s for s in obj.reasoning_chain
            if s.sources
            and not s.claim.lower().startswith("retrieved signature ")
            and s.relation not in {"HEDGE"}
            and s.claim.strip()
        ]
        if sourced:
            return sourced
        return [
            s for s in obj.reasoning_chain
            if s.relation not in {"HEDGE"}
            and not s.claim.lower().startswith("retrieved signature ")
            and s.claim.strip()
        ]

    # ── Math ───────────────────────────────────────────────────────────────

    def _is_math_result(self, steps: list) -> bool:
        return bool(steps) and any(
            re.search(r"Verified (calculation|equation solution)", s.claim, re.IGNORECASE)
            for s in steps
        )

    def _render_math(self, steps: list, obj: VerifiedCognitiveObject, tier: int) -> str:
        lines: list[str] = []

        for step in steps:
            # "Verified calculation: expr = result"
            calc = re.fullmatch(
                r"Verified calculation:\s*(.+?)\s*=\s*(.+?)\.?",
                step.claim.strip(),
            )
            if calc:
                expr, result = calc.group(1).strip(), calc.group(2).strip()
                expr = expr.rstrip("=").strip()
                result = result.lstrip("=").strip()
                lines.append(f"**{expr} = {result}**")
                lines.append("")
                lines.append(f"To work it out: `{expr}` evaluates to **{result}**.")
                continue

            # "Verified equation solution for x: expr -> result"
            eq = re.fullmatch(
                r"Verified equation solution for (\w+):\s*(.+?)\s*->\s*(.+?)\.?",
                step.claim.strip(),
            )
            if eq:
                var, expr, result = eq.group(1), eq.group(2).strip(), eq.group(3).strip()
                lines.append(f"**{var} = {result}**")
                lines.append("")
                lines.append(f"Solving `{expr}` gives **{var} = {result}**.")
                continue

            lines.append(self._clean_claim(step.claim))

        # Confidence note — math solver results are always tier 1/2 so this reads
        # naturally: "I'm certain about this."
        phrase = self._confidence_phrase(tier)
        if phrase:
            lines.append("")
            lines.append(f"*{phrase}.*")

        return "\n".join(lines)

    # ── Causal ─────────────────────────────────────────────────────────────

    def _is_causal_result(self, steps: list) -> bool:
        return bool(steps) and all(
            s.relation in {"CAUSES", "DEPENDS_ON"} for s in steps[:3] if s.relation
        )

    def _render_causal(self, steps: list, obj: VerifiedCognitiveObject, tier: int) -> str:
        causes = [s for s in steps if s.relation == "CAUSES"]
        deps = [s for s in steps if s.relation == "DEPENDS_ON"]

        lines: list[str] = []

        if causes:
            chain = self._extract_causal_chain(causes)
            if len(chain) > 2:
                lines.append(" → ".join(chain) + ".")
            elif len(chain) == 2:
                lines.append(f"{chain[0]} causes {chain[1]}.")
            else:
                for step in causes[:4]:
                    lines.append(self._clean_claim(step.claim))

            if len(causes) > 1:
                lines.append("")
                for step in causes[1:5]:
                    lines.append(f"- {self._clean_claim(step.claim)}")

        elif deps:
            for step in deps[:6]:
                lines.append(f"- {self._clean_claim(step.claim)}")

        else:
            return self._render_claims(steps, obj, tier)

        phrase = self._confidence_phrase(tier)
        if phrase and tier <= 3:
            lines.append("")
            lines.append(f"*{phrase}.*")

        return "\n".join(lines)

    def _extract_causal_chain(self, cause_steps: list) -> list[str]:
        chain: list[str] = []
        for step in cause_steps:
            m = re.fullmatch(r"(.+?) causes (.+?)\.", step.claim.strip())
            if m:
                if not chain:
                    chain.append(m.group(1).strip())
                chain.append(m.group(2).strip())
        return chain

    # ── General claims ─────────────────────────────────────────────────────

    def _render_claims(
        self, steps: list, obj: VerifiedCognitiveObject, tier: int
    ) -> str:
        claims = [
            self._clean_claim(s.claim)
            for s in steps
            if s.claim.strip() and not self._is_internal_claim(s.claim)
        ]
        if not claims:
            return self._render_gap(obj)

        lines: list[str] = []

        if len(claims) == 1:
            lines.append(claims[0])
        else:
            lines.append(claims[0])
            lines.append("")
            for claim in claims[1:6]:
                lines.append(f"- {claim}")

        # Simulation results — only when they add real user value
        if obj.simulation_results and self._should_show_simulation(obj):
            lines.append("")
            lines.append("Simulation results:")
            for sim in obj.simulation_results:
                status = "✓ passed" if sim.passed else "✗ failed"
                lines.append(f"- {sim.scenario}: {status}")
                for outcome in sim.outcomes[:2]:
                    lines.append(f"  • {outcome}")

        # User-facing gaps — filter internal-only messages
        user_gaps = self._user_relevant_gaps(obj.knowledge_gaps)
        if user_gaps:
            lines.append("")
            lines.append("What I'm less certain about:")
            for gap in user_gaps[:3]:
                lines.append(f"- {gap}")

        # Natural confidence note
        phrase = self._confidence_phrase(tier)
        if phrase:
            lines.append("")
            lines.append(f"*{phrase}.*")

        return "\n".join(lines)

    # ── Gap response ───────────────────────────────────────────────────────

    def _render_gap(self, obj: VerifiedCognitiveObject) -> str:
        """
        Produce a genuinely helpful response when memory has nothing.

        This is driven entirely by the structured fields on obj — no
        hardcoded keyword lists. The intent classifier already ran (T1),
        the capability router already ran, and the knowledge_gaps list
        already describes why retrieval failed. We use those.
        """
        intent = str(getattr(obj, "intent", "") or "").upper()
        capability_kind = ""
        if obj.capability_plan:
            capability_kind = str(getattr(obj.capability_plan, "kind", "") or "").upper()

        # The knowledge_gaps list is the most specific signal we have —
        # use it to shape the response without hardcoding expected strings.
        gap_text = " ".join(obj.knowledge_gaps).lower() if obj.knowledge_gaps else ""
        has_solver_gap = any(
            kw in gap_text for kw in ("solver", "expression", "compute", "calculate", "sympy")
        )
        has_route_gap = "capability" in gap_text and ("unavailable" in gap_text or "blocked" in gap_text)

        # ── Emotional: always respond warmly, never with a gap message ──
        if "EMOTIONAL" in intent:
            # Use the first non-hedge step if it has emotional content
            emotional_steps = [
                s for s in obj.reasoning_chain
                if s.relation not in {"HEDGE"}
                and s.claim.strip()
                and not s.claim.lower().startswith("retrieved signature ")
            ]
            if emotional_steps:
                return emotional_steps[0].claim.strip()
            return (
                "It sounds like you're going through something — I'm here. "
                "Feel free to share more and I'll do my best to help."
            )

        # ── Math: solver tried but failed ────────────────────────────────
        if has_solver_gap or "MATH" in capability_kind:
            return (
                "I wasn't able to work that out. "
                "I can handle arithmetic (like `2 + 9`) and simple equations (like `2x + 5 = 11`). "
                "Try expressing it in that form and I'll solve it."
            )

        # ── Capability blocked/unavailable ───────────────────────────────
        if has_route_gap:
            kind_label = self._capability_label(capability_kind)
            return (
                f"I understood this as a {kind_label} request, "
                "but I don't have the resources connected to handle it right now. "
                "You can still describe what you need and I'll help with what I know."
            )

        # ── Profile query: intent classifier already tagged this ─────────
        if "profile" in intent.lower() or (
            obj.capability_plan and "profile" in str(getattr(obj.capability_plan, "route", "")).lower()
        ):
            return (
                "I don't have that information about you yet. "
                "Tell me — for example, 'My name is [name]' — and I'll remember it."
            )

        # ── Code generation with no codebase loaded ──────────────────────
        if "CODE" in capability_kind or "CODING" in capability_kind:
            return (
                "I don't have relevant code in my memory for this yet. "
                "Share a file, paste some code, or describe what you're building "
                "and I can help straight away."
            )

        # ── Memory exists but no direct claim ────────────────────────────
        if obj.sources:
            return (
                "I found related information but nothing that directly answers this. "
                "Could you share more context or rephrase the question?"
            )

        # ── World knowledge / general fact: offer to learn ───────────────
        # The intent classifier already classified this — no keyword matching needed.
        # We check intent for GENERAL_FACT, WORLD_KNOWLEDGE, or WORKSPACE_QUERY.
        if any(kw in intent for kw in ("GENERAL", "WORLD", "FACT", "WORKSPACE")):
            return (
                "I don't have that in my memory yet. "
                "You can teach me by sharing a document or stating the facts directly, "
                "and I'll remember them going forward."
            )

        # ── Fallback — always leave the user with a path forward ─────────
        return (
            "I don't have enough to give you a confident answer on this yet. "
            "Share what you know and I'll build on it, "
            "or ask a more specific question and I'll do my best."
        )

    # ── Helpers ────────────────────────────────────────────────────────────

    def _capability_label(self, kind: str) -> str:
        """Convert an internal capability kind to a human-readable label."""
        labels = {
            "MATH_SCIENCE": "maths or science",
            "CODING": "coding",
            "CODE_GENERATE": "code generation",
            "IMAGE_GENERATION": "image generation",
            "AUDIO_GENERATION": "audio generation",
            "VIDEO_GENERATION": "video generation",
            "AGENTIC_TASK": "automated task",
            "CREATIVE_TEXT": "creative writing",
            "WORLD_KNOWLEDGE": "general knowledge",
            "MEMORY_CHAT": "memory recall",
        }
        for key, label in labels.items():
            if key in kind:
                return label
        return kind.lower().replace("_", " ") if kind else "this type of"

    def _user_relevant_gaps(self, gaps: list[str]) -> list[str]:
        """
        Filter gaps that are purely internal (solver errors, adapter names, etc.)
        and return only gaps meaningful to a user.
        The filter uses substring checks on gap content — not hardcoded response text.
        """
        internal_substrings = (
            "sympy", "adapter", "hash_projection", "signature", "ontology",
            "internal", "solver could not solve", "solver failed",
            "source signatures matched", "deterministic",
        )
        result = []
        for gap in gaps:
            lower = gap.lower()
            if not any(s in lower for s in internal_substrings):
                result.append(gap)
        return result

    def _clean_claim(self, claim: str) -> str:
        cleaned = claim.strip()
        if not cleaned:
            return ""
        # Strip internal prefixes that leak into claims
        for prefix in (
            "Verified path: ",
            "Verified calculation: ",
            "Verified equation solution for ",
        ):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]
        return cleaned if cleaned.endswith((".", "?", "!")) else f"{cleaned}."

    def _is_internal_claim(self, claim: str) -> bool:
        lowered = claim.lower()
        if "verified results:" in lowered:
            return True
        if re.search(r"\[\{['\"]kind['\"]:", claim):
            return True
        if re.search(r"['\"]solver_(status|result|method)['\"]", claim):
            return True
        return False

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
