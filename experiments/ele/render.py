"""ELE render mode (spec §3.1.4) — the T2-deterministic-share mechanism.

E-Rule 1: no hand-registered templates. Core-shape and adjunct templates are
INDUCED from (frame, sentence) pairs — the same provenance shape as production
SPPE pairs. The verb and article are frame DATA, never baked into a template
(this is what lets a never-trained predicate render via a known shape, row 8).

Gap policy (spec, "do not deviate"): a missing core shape or unknown adjunct
raises typed GapReport — never a silent nearest-template guess.
`render_nearest_naive` exists only to DEMONSTRATE the failure mode the policy
prevents (row 9: silently dropped argument).
"""

from __future__ import annotations

from dataclasses import dataclass


class GapReport(Exception):
    def __init__(self, gap):
        self.gap = gap
        super().__init__(f"GAP_UNRESOLVED: {gap!r}")


@dataclass
class Renderer:
    core_templates: dict[frozenset, list[str]]     # role-set -> template tokens
    adjunct_templates: dict[str, list[str]]        # role -> snippet tokens
    fixed_tokens: set[str]                          # tokens licensed by training data

    @classmethod
    def learn(cls, pairs: list[tuple[dict[str, str], tuple[str, ...], tuple[str, ...], list[str]]]
              ) -> "Renderer":
        """pairs: (frame, core_roles, adjunct_roles, sentence_tokens).

        Core template induction: replace each core-role value with its slot.
        Adjunct induction: the tokens left over after the core template match,
        segmented wherever an adjunct-role value appears (value -> slot, other
        tokens stay fixed). Consistency is asserted — same shape, same template.
        """
        core_templates: dict[frozenset, list[str]] = {}
        adjunct_templates: dict[str, list[str]] = {}
        fixed: set[str] = set()

        for frame, core_roles, adjunct_roles, tokens in pairs:
            value_to_role = {frame[r]: r for r in core_roles}
            n_core = len(core_roles)
            core_tokens, rest = tokens[:n_core], tokens[n_core:]
            template = [f"{{{value_to_role[t]}}}" if t in value_to_role else t
                        for t in core_tokens]
            key = frozenset(core_roles)
            if key in core_templates and core_templates[key] != template:
                raise AssertionError(
                    f"inconsistent template for shape {sorted(key)}: "
                    f"{core_templates[key]} vs {template}")
            core_templates[key] = template
            fixed.update(t for t in template if not t.startswith("{"))

            i = 0
            for role in adjunct_roles:
                value = frame[role]
                snippet: list[str] = []
                while i < len(rest) and rest[i] != ".":
                    if rest[i] == value:
                        snippet.append(f"{{{role}}}")
                        i += 1
                        break
                    snippet.append(rest[i])
                    i += 1
                if snippet:
                    prev = adjunct_templates.get(role)
                    if prev is not None and prev != snippet:
                        raise AssertionError(
                            f"inconsistent adjunct template for {role}: {prev} vs {snippet}")
                    adjunct_templates[role] = snippet
                    fixed.update(t for t in snippet if not t.startswith("{"))
        fixed.add(".")
        return cls(core_templates, adjunct_templates, fixed)

    # ── rendering ──

    def render_monolithic(self, frame: dict[str, str], roles: tuple[str, ...]) -> list[str]:
        """v1 semantics: the whole role set must be a known shape (row 9 setup)."""
        key = frozenset(roles)
        if key not in self.core_templates:
            raise GapReport(tuple(sorted(key)))
        return [frame[t[1:-1]] if t.startswith("{") else t
                for t in self.core_templates[key]] + ["."]

    def render(self, frame: dict[str, str], roles: tuple[str, ...]) -> list[str]:
        """v2 semantics (spec render_v2): known core shape + independently
        learned adjuncts compose; anything else raises GapReport."""
        core = tuple(r for r in roles if r not in self.adjunct_templates)
        adjuncts = [r for r in roles if r in self.adjunct_templates]
        key = frozenset(core)
        if key not in self.core_templates:
            raise GapReport(tuple(sorted(key)))
        out = [frame[t[1:-1]] if t.startswith("{") else t
               for t in self.core_templates[key]]
        for role in adjuncts:
            out += [frame[t[1:-1]] if t.startswith("{") else t
                    for t in self.adjunct_templates[role]]
        return out + ["."]

    def render_nearest_naive(self, frame: dict[str, str], roles: tuple[str, ...]) -> list[str]:
        """The forbidden fallback (row 9): pick the closest known shape by role
        overlap and render only the intersecting roles — silently DROPPING
        everything else. Exists as a demonstration, never as a code path."""
        key = max(self.core_templates, key=lambda k: len(k & set(roles)))
        return [frame[t[1:-1]] if t.startswith("{") else t
                for t in self.core_templates[key]] + ["."]

    def hallucinated_tokens(self, output: list[str], frame: dict[str, str]) -> list[str]:
        """Tokens not licensed by the frame values or training-fixed tokens.
        Zero by construction for template rendering — the row-6 property."""
        licensed = set(frame.values()) | self.fixed_tokens
        return [t for t in output if t not in licensed]
