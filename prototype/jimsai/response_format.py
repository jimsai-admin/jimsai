"""Response-format faculty (M7 slice) — strict user output format without an LLM.

A user may ask for a specific OUTPUT SHAPE — "as a table", "as JSON", "in bullet
points", "list them". The content is fixed by verification (the VCO's voiced
claims); only its SERIALIZATION bends to the requested format. This is the
architecture's principle (docs §2.9): format is a constraint on the document
plan applied deterministically to the same verified content, never a
re-generation and never an invention.

Format detection uses a small OPERATION vocabulary (like the 9-capability
taxonomy — an enumerated set of system operations, not answer data), resolved
by concept where possible. Unknown format requests are NOT guessed: they fall
through to prose (the honest default) and log a coverage gap. Each format is a
deterministic emitter over structured claim tuples — zero content invention.
"""

from __future__ import annotations

import json
import re

# Operation vocabulary: format directive → canonical format id. Growable; a
# format not present here falls through to prose (no guess). Multilingual
# synonyms are added as data, never as code branches.
_FORMAT_MARKERS: dict[str, tuple[str, ...]] = {
    "table":   ("as a table", "in a table", "tabular", "table form", "en tableau",
                "表格", "as table"),
    "json":    ("as json", "in json", "json format", "as a json", "json object"),
    "bullets": ("bullet point", "bullet list", "as bullets", "in bullets",
                "as a list", "list them", "point form", "en liste"),
}


def detect_format(query: str) -> str | None:
    """Return a canonical format id if the query requests one, else None.
    Longest-marker-first so 'as a json table' resolves deterministically."""
    if not query:
        return None
    low = query.lower()
    best: tuple[int, str] | None = None
    for fmt, markers in _FORMAT_MARKERS.items():
        for m in markers:
            if m in low and (best is None or len(m) > best[0]):
                best = (len(m), fmt)
    return best[1] if best else None


# ── claim → structured tuple ────────────────────────────────────────────────

_SUBJ_REL_VAL = re.compile(
    r"^(?:the\s+)?(?P<subject>.+?)\s+(?P<rel>uses|is|are|has|means|is based in|"
    r"is codenamed|is led by|was|will be)\s+(?P<value>.+?)\.?$",
    re.IGNORECASE,
)


def _structure_claim(claim: str) -> tuple[str, str, str]:
    """Best-effort (subject, attribute, value) split of a declarative claim for
    tabular/JSON rendering. Purely structural (a copula/verb pivot), no domain
    vocabulary; falls back to ('', '', whole-claim) when it doesn't split."""
    text = claim.strip()
    m = _SUBJ_REL_VAL.match(text)
    if m:
        return (m.group("subject").strip(), m.group("rel").strip().lower(),
                m.group("value").strip().rstrip("."))
    return ("", "", text.rstrip("."))


# ── emitters (deterministic serializers of the SAME claims) ─────────────────

def _md_escape(cell: str) -> str:
    return cell.replace("|", "\\|").replace("\n", " ")


def emit_table(claims: list[str]) -> str:
    rows = [_structure_claim(c) for c in claims]
    if any(s and v for s, _r, v in rows):
        lines = ["| Subject | Attribute | Value |", "| --- | --- | --- |"]
        for s, r, v in rows:
            lines.append(f"| {_md_escape(s) or '—'} | {_md_escape(r) or '—'} | {_md_escape(v)} |")
        return "\n".join(lines)
    # No subject/value structure — a single-column fact table.
    lines = ["| Fact |", "| --- |"] + [f"| {_md_escape(c.rstrip('.'))} |" for c in claims]
    return "\n".join(lines)


def emit_json(claims: list[str]) -> str:
    items = []
    for c in claims:
        s, r, v = _structure_claim(c)
        items.append({"subject": s, "attribute": r, "value": v} if s and v
                     else {"statement": c.rstrip(".")})
    return "```json\n" + json.dumps(items, ensure_ascii=False, indent=2) + "\n```"


def emit_bullets(claims: list[str]) -> str:
    return "\n".join(f"- {c.rstrip('.')}." for c in claims)


_EMITTERS = {"table": emit_table, "json": emit_json, "bullets": emit_bullets}


def apply_format(fmt: str | None, claims: list[str]) -> str | None:
    """Render claims in the requested format, or None to defer to prose.
    Content is exactly the input claims — no addition, no invention."""
    if not fmt or not claims:
        return None
    emitter = _EMITTERS.get(fmt)
    return emitter(claims) if emitter else None
