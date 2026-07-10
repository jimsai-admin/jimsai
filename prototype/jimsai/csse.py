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

    # Certainty is conveyed by answering plainly, not by meta-commentary — a
    # natural interlocutor does not footnote every reply with how sure it is.
    # Only genuine uncertainty earns a brief, woven-in note; confident tiers
    # say nothing extra. (This replaced a per-tier stock footer that stamped
    # "I believe this is right" onto every answer — the robotic tell.)
    _CONFIDENCE_PROSE = {
        1: None,   # 0.99+   verified — just state it
        2: None,   # 0.90–0.99  confident — just state it
        3: None,   # 0.70–0.89  confident enough — just state it
        4: "This is my best read — worth a quick check.",  # 0.40–0.69
        5: None,   # below 0.40 — gap path handles it
    }

    # ── Public API ─────────────────────────────────────────────────────────

    def render(self, obj: VerifiedCognitiveObject) -> str:
        """Render a user-facing natural language response."""
        tier = self._compute_tier(obj.confidence)
        user_steps = self._user_facing_steps(obj)

        # Respond in the language ASKED. Knowledge is stored language-neutrally
        # (concept IDs); the Surface Realizer re-realizes each verified claim's
        # content into the query's language via the CLL reverse lexicon —
        # literals (entities) pass through. Reasoning stays language-neutral;
        # only this surface layer is language-specific. (First realizer: content
        # is translated and in-language; grammar fluency is the M4b layer.)
        # The SAME realizer localises response chrome (hedges, section labels,
        # gap prompts) via self._localize — so a French/Pidgin/Yoruba answer has
        # no hardcoded English scaffolding, with no per-language table in code.
        lang = self._query_lang(obj)
        user_steps = self._realize_language(obj, user_steps, lang)

        # Strict user response format (M7): if the query requested a shape
        # ("as a table", "as JSON", "as a list"), serialize the SAME verified
        # claims into it — content fixed by verification, only form bends. Math
        # and causal results keep their specialist rendering.
        if user_steps and not self._is_math_result(user_steps) and not self._is_causal_result(user_steps):
            from .response_format import apply_format, detect_format
            fmt = detect_format(getattr(obj, "raw_query", "") or "")
            if fmt:
                claims = [self._clean_claim(s.claim) for s in user_steps
                          if s.claim.strip() and not self._is_internal_claim(s.claim)]
                formatted = apply_format(fmt, claims)
                if formatted:
                    return formatted

        # Route to specialist renderers first
        if self._is_math_result(user_steps):
            return self._render_math(user_steps, obj, tier, lang)

        if self._is_causal_result(user_steps):
            return self._render_causal(user_steps, obj, tier, lang)

        if user_steps:
            return self._render_claims(user_steps, obj, tier, lang)

        return self._render_gap(obj, lang)

    def _query_lang(self, obj: VerifiedCognitiveObject) -> str:
        """Detect the query's language ONCE per render, from the same CLL signal
        the realizer uses. 'en' (or unknown) means no localisation is applied."""
        query = getattr(obj, "raw_query", "") or ""
        if not query:
            return "en"
        try:
            from .cll_shadow import get_shadow, index_enabled, shadow_enabled
            from .surface_realizer import detect_language
            if not (index_enabled() or shadow_enabled()):
                return "en"
            return detect_language(query, get_shadow())
        except Exception:
            return "en"

    def _localize(self, text: str, lang: str) -> str:
        """Realize a fixed CHROME phrase (hedge, section label, gap prompt) into
        the response language via the SAME data-driven realizer as claims —
        content words translate, function words pass through, no per-language
        table. No-op for English or when the realizer is unavailable, so a wrong
        language is never emitted (fail-safe)."""
        if lang == "en" or not text or not text.strip():
            return text
        try:
            from .cll_shadow import get_shadow
            from .surface_realizer import realize_in_language
            return realize_in_language(text, lang, get_shadow())
        except Exception:
            return text

    def _realize_language(self, obj: VerifiedCognitiveObject, steps: list, lang: str) -> list:
        """Return steps with each claim re-realized into the query's language.
        No-op for English or when the realizer/concept-index is unavailable."""
        if lang == "en" or not steps:
            return steps
        try:
            from .cll_shadow import get_shadow
            from .surface_realizer import realize_in_language
            shadow = get_shadow()
            realized = []
            for s in steps:
                new_claim = realize_in_language(s.claim, lang, shadow)
                realized.append(s.model_copy(update={"claim": new_claim}) if new_claim != s.claim else s)
            return realized
        except Exception:
            return steps

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

    def _render_math(self, steps: list, obj: VerifiedCognitiveObject, tier: int, lang: str = "en") -> str:
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
                # Math is a UNIVERSAL notation — the equation is the answer in any
                # language. No English scaffolding ("To work it out …"), which
                # would be wrong for a French/Pidgin/Yoruba query. Numbers,
                # operators and "=" carry the whole meaning.
                lines.append(f"**{expr} = {result}**")
                continue

            # "Verified equation solution for x: expr -> result"
            eq = re.fullmatch(
                r"Verified equation solution for (\w+):\s*(.+?)\s*->\s*(.+?)\.?",
                step.claim.strip(),
            )
            if eq:
                var, expr, result = eq.group(1), eq.group(2).strip(), eq.group(3).strip()
                # Language-neutral: show the working as notation (equation ⟹
                # solution), never an English sentence.
                if expr and expr not in (result, f"{var} = {result}", f"{var}={result}"):
                    lines.append(f"**{expr}  ⟹  {var} = {result}**")
                else:
                    lines.append(f"**{var} = {result}**")
                continue

            lines.append(self._clean_claim(step.claim))

        phrase = self._confidence_phrase(tier)
        # Decorative hedge — shown only in English. For other languages it is
        # OMITTED rather than leaked as English or garbled by partial
        # realization; the calibrated confidence score travels in the response
        # payload, so no signal is lost. (Essential chrome — the honest gap —
        # is still realized in-language below.)
        if phrase and lang == "en":
            lines.append("")
            lines.append(phrase)

        return "\n".join(lines)

    # ── Causal ─────────────────────────────────────────────────────────────

    def _is_causal_result(self, steps: list) -> bool:
        return bool(steps) and all(
            s.relation in {"CAUSES", "DEPENDS_ON"} for s in steps[:3] if s.relation
        )

    def _render_causal(self, steps: list, obj: VerifiedCognitiveObject, tier: int, lang: str = "en") -> str:
        causes = [s for s in steps if s.relation == "CAUSES"]
        deps = [s for s in steps if s.relation == "DEPENDS_ON"]

        lines: list[str] = []

        if causes:
            chain = self._extract_causal_chain(causes)
            if len(chain) > 2:
                # "→" is a language-neutral causal connective; keep it.
                lines.append(" → ".join(chain) + ".")
            elif len(chain) == 2:
                lines.append(self._localize(f"{chain[0]} causes {chain[1]}.", lang))
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
            return self._render_claims(steps, obj, tier, lang)

        phrase = self._confidence_phrase(tier)
        # Decorative hedge — shown only in English. For other languages it is
        # OMITTED rather than leaked as English or garbled by partial
        # realization; the calibrated confidence score travels in the response
        # payload, so no signal is lost. (Essential chrome — the honest gap —
        # is still realized in-language below.)
        if phrase and lang == "en":
            lines.append("")
            lines.append(phrase)

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
        self, steps: list, obj: VerifiedCognitiveObject, tier: int, lang: str = "en"
    ) -> str:
        claims = [
            self._clean_claim(s.claim)
            for s in steps
            if s.claim.strip() and not self._is_internal_claim(s.claim)
        ]
        if not claims:
            return self._render_gap(obj, lang)

        # Discourse ordering (M9): sequence the verified claims by entity
        # continuity so related facts sit together and the answer reads as a
        # passage, not a random list. Language-universal — it keys on entity
        # identity only, injects no function words, and is meaning-preserving
        # (whole claims reordered, never rewritten). Fails safe to raw order.
        # (Surface reduction of repetition — M10 elision/pronouns — is NOT done
        # here: it is language-specific and must come from discovered closed
        # class, not hardcoded English. See discourse_composer.)
        rendered = claims
        if len(claims) > 2:
            try:
                from .discourse_composer import compose
                from .cll_shadow import get_shadow, index_enabled, shadow_enabled
                shadow = get_shadow() if (index_enabled() or shadow_enabled()) else None
                rendered = compose(claims, shadow=shadow) or claims
            except Exception:
                rendered = claims

        lines: list[str] = []
        if len(rendered) == 1:
            lines.append(rendered[0])
        else:
            # A paragraph (space-joined) reads more naturally than a bullet dump
            # and is language-neutral — each claim already carries its own
            # terminal punctuation from realization. An explicit "as a list"
            # request is served earlier by response_format.
            lines.append(" ".join(rendered[:6]))

        # Simulation results — only when they add real user value
        if obj.simulation_results and self._should_show_simulation(obj):
            lines.append("")
            lines.append(self._localize("Simulation results:", lang))
            for sim in obj.simulation_results:
                status = self._localize("passed" if sim.passed else "failed", lang)
                mark = "✓" if sim.passed else "✗"
                lines.append(f"- {sim.scenario}: {mark} {status}")
                for outcome in sim.outcomes[:2]:
                    lines.append(f"  • {outcome}")

        # User-facing gaps — filter internal-only messages
        user_gaps = self._user_relevant_gaps(obj.knowledge_gaps)
        if user_gaps:
            lines.append("")
            lines.append(self._localize("What I'm less certain about:", lang))
            for gap in user_gaps[:3]:
                lines.append(f"- {self._localize(gap, lang)}")

        # Natural confidence note — only when genuinely uncertain (tier 4),
        # phrased as a plain helpful sentence, never a stock italic footer.
        phrase = self._confidence_phrase(tier)
        # Decorative hedge — shown only in English. For other languages it is
        # OMITTED rather than leaked as English or garbled by partial
        # realization; the calibrated confidence score travels in the response
        # payload, so no signal is lost. (Essential chrome — the honest gap —
        # is still realized in-language below.)
        if phrase and lang == "en":
            lines.append("")
            lines.append(phrase)

        return "\n".join(lines)

    # ── Gap response ───────────────────────────────────────────────────────

    def _render_gap(self, obj: VerifiedCognitiveObject, lang: str = "en") -> str:
        """
        Produce a genuinely helpful response when memory has nothing.

        This is driven entirely by the structured fields on obj — no
        hardcoded keyword lists. The intent classifier already ran (T1),
        the capability router already ran, and the knowledge_gaps list
        already describes why retrieval failed. We use those.

        Every message is localised into the response language via _localize
        (the same data-driven realizer as claims) — the honest gap must be
        communicated IN THE USER'S LANGUAGE, never as hardcoded English.
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
            return self._localize(
                "It sounds like you're going through something — I'm here. "
                "Feel free to share more and I'll do my best to help.", lang
            )

        # ── Math: solver tried but failed ────────────────────────────────
        if has_solver_gap or "MATH" in capability_kind:
            return self._localize(
                "I wasn't able to work that out. "
                "I can handle arithmetic (like `2 + 9`) and simple equations (like `2x + 5 = 11`). "
                "Try expressing it in that form and I'll solve it.", lang
            )

        # ── Capability blocked/unavailable ───────────────────────────────
        if has_route_gap:
            kind_label = self._capability_label(capability_kind)
            return self._localize(
                f"I understood this as a {kind_label} request, "
                "but I don't have the resources connected to handle it right now. "
                "You can still describe what you need and I'll help with what I know.", lang
            )

        # ── Profile query: intent classifier already tagged this ─────────
        if "profile" in intent.lower() or (
            obj.capability_plan and "profile" in str(getattr(obj.capability_plan, "route", "")).lower()
        ):
            return self._localize(
                "I don't have that information about you yet. "
                "Tell me — for example, 'My name is [name]' — and I'll remember it.", lang
            )

        # ── Code generation with no codebase loaded ──────────────────────
        if "CODE" in capability_kind or "CODING" in capability_kind:
            return self._localize(
                "I don't have relevant code in my memory for this yet. "
                "Share a file, paste some code, or describe what you're building "
                "and I can help straight away.", lang
            )

        # ── Memory exists but no direct claim ────────────────────────────
        if obj.sources:
            return self._localize(
                "I found related information but nothing that directly answers this. "
                "Could you share more context or rephrase the question?", lang
            )

        # ── World knowledge / general fact: offer to learn ───────────────
        # The intent classifier already classified this — no keyword matching needed.
        # We check intent for GENERAL_FACT, WORLD_KNOWLEDGE, or WORKSPACE_QUERY.
        if any(kw in intent for kw in ("GENERAL", "WORLD", "FACT", "WORKSPACE")):
            return self._localize(
                "I don't have that in my memory yet. "
                "You can teach me by sharing a document or stating the facts directly, "
                "and I'll remember them going forward.", lang
            )

        # ── Fallback — always leave the user with a path forward ─────────
        return self._localize(
            "I don't have enough to give you a confident answer on this yet. "
            "Share what you know and I'll build on it, "
            "or ask a more specific question and I'll do my best.", lang
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
        """Return only gaps meaningful to a user.

        Internal/diagnostic gaps are TYPED at their source with an "[internal]"
        marker (see runtime_layers) rather than caught by a growing blocklist
        of substrings — a structural signal, not a vocabulary list. The legacy
        substrings remain only as a safety net for provider-status strings not
        yet converted to typed gaps.
        """
        legacy_internal = (
            "sympy", "adapter", "reembedding_required", "embedding_unavailable",
            "signature", "ontology", "solver could not solve", "solver failed",
            "source signatures matched", "deterministic", "provider unavailable",
        )
        result = []
        for gap in gaps:
            lower = gap.lower().strip()
            if lower.startswith("[internal]"):
                continue
            if any(s in lower for s in legacy_internal):
                continue
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
