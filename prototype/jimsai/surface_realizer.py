"""Surface Realizer — render verified content in the language ASKED.

Knowledge is language-agnostic (concept IDs); realization is language-specific.
A fact taught in English, asked about in French, must be ANSWERED in French.
This module is the per-language realizer: it takes a verified claim (English
surface, since that is how facts are stored) and re-realizes its CONTENT words
into the target language via the CLL reverse lexicon (concept → target surface),
keeping literals (named entities / nonce values) as-is. Function words that map
to concepts translate; unknown words pass through (graceful degradation, never
a guess).

This is the E9 mechanism ("Tagupo projet utilise Zotix base de donnees") at
production scale. It is a FIRST realizer: content is faithfully translated and
in the target language, but grammar/agreement/word-order fluency is the job of
the constrained-decode realizer (M4b) layered on top — a roadmap step. The
architecture separation holds: reasoning is language-neutral; only this surface
layer is language-specific, and different languages are different realizers over
the same meaning, never different reasoning.

Anti-hardcoding: no translation table lives here. Every surface comes from the
provenance-stamped CLL lexicon (`experiments/concept_model/data/lexicon.jsonl`),
the same data the concept index uses. A new language is added by pointing the
lexicon builder at that language — zero code change.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

_TOKEN = re.compile(r"[^\W\d_]+|\d+|[^\w\s]", re.UNICODE)

# Character-range language signals (script/diacritic, not word lists).
_CJK = "一", "鿿"


def detect_language(text: str, shadow=None) -> str:
    """Best-effort language of a query. Non-Latin script and language-exclusive
    letters are hard signals; the rest is decided by a lexicon vote (§below).
    Defaults to en — the storage/default language, and the safe choice when
    evidence is weak (a false "fr" would translate an English answer).

    No word list lives here. The only fixed knowledge is orthographic: CJK code
    points ⇒ zh, Yoruba sub-dot letters ⇒ yo, and French-exclusive accents add
    weight to fr. Everything else — including bare-Latin French like "Dans
    quelle ville…" — is resolved by which language's lexicon surfaces the query
    tokens belong to, weighted so a token exclusive to one language (``ville``)
    counts far more than one shared across many (``se``)."""
    if not text:
        return "en"
    if any(_CJK[0] <= ch <= _CJK[1] for ch in text):
        return "zh"
    low = text.lower()
    if any(ch in "ọẹṣ" for ch in low):
        return "yo"  # Yoruba sub-dot letters — exclusive orthography.
    scores = get_reverse().vote_scores(text)
    if any(ch in "àâäçéèêëîïôùûüœ" for ch in low):
        # French-exclusive accents: strong orthographic evidence within the
        # target set. A vote can still name another language, but absent that
        # this alone carries fr (e.g. "Où se trouve…", no lexical content hit).
        scores["fr"] = scores.get("fr", 0.0) + 1.0
    if scores:
        best = max(scores, key=scores.get)
        # Only override the en default when the winner clears en by a margin —
        # one shared function word must not flip an English query to French.
        if best != "en" and scores[best] - scores.get("en", 0.0) >= 0.5:
            return best
    return "en"


class ReverseLexicon:
    """concept-ID → {lang: [surfaces]} and a lang membership set, from the CLL
    lexicon file. Singleton, loaded once."""

    def __init__(self, lexicon_path: str | None = None):
        path = Path(
            lexicon_path
            or os.getenv("JIMS_CONCEPT_LEXICON_PATH", "")
            or Path(__file__).resolve().parents[2] / "experiments" / "concept_model" / "data" / "lexicon.jsonl"
        )
        self.by_concept: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        # Folded single-word surface → set of languages it appears in. This is
        # the evidence for language detection: a token exclusive to one language
        # is diagnostic; one shared across many is not. Multi-word surfaces are
        # not indexed here (a single query token can never match them).
        self.langs_of_surface: dict[str, set[str]] = defaultdict(set)
        self.loaded = False
        if path.exists():
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    row = json.loads(line)
                    surfaces = self.by_concept[row["concept"]][row["lang"]]
                    if row["surface"] not in surfaces:
                        surfaces.append(row["surface"])
                    key = _surface_key(row["surface"])
                    if key and " " not in key:
                        self.langs_of_surface[key].add(row["lang"])
            self.loaded = True

    def vote_scores(self, text: str) -> dict[str, float]:
        """Per-language score for a query's tokens by lexicon membership,
        weighted by inverse language frequency: a token that surfaces in only
        one language contributes 1.0 to it; one shared across k languages
        contributes 1/k to each. Function words (in every language) wash out;
        language-exclusive content words dominate. Data-driven — the surfaces
        and their language tags are the Wikidata-sourced lexicon, no word list."""
        scores: dict[str, float] = defaultdict(float)
        if not self.loaded:
            return scores
        for tok in _TOKEN.findall(text):
            if not tok[0].isalpha() or len(tok) < 4:
                # Short tokens are unreliable signals: many 2–3 char strings are
                # indexed as one language's *code/abbreviation* surface (e.g.
                # "est", "la", "du" as English) and would drown genuine content
                # words. Length ≥ 4 is the same content-word proxy the realizer
                # uses — no word list.
                continue
            langs = self.langs_of_surface.get(_surface_key(tok))
            if not langs:
                continue
            weight = 1.0 / len(langs)
            for lang in langs:
                scores[lang] += weight
        return dict(scores)

    def surface(self, concept: str, lang: str) -> str | None:
        """Preferred target-language surface for a concept: a full-form label,
        not an abbreviation. Rank prefers non-all-caps, length >= 3, then the
        earliest (canonical label precedes aliases in the source)."""
        options = self.by_concept.get(concept, {}).get(lang)
        if not options:
            return None
        def rank(idx_s):
            idx, s = idx_s
            is_abbrev = s.isupper() and len(s) <= 4
            too_short = len(s) < 3
            return (is_abbrev, too_short, idx)
        return min(enumerate(options), key=rank)[1]


_reverse: ReverseLexicon | None = None


def get_reverse() -> ReverseLexicon:
    global _reverse
    if _reverse is None:
        _reverse = ReverseLexicon()
    return _reverse


def realize_in_language(claim: str, target_lang: str, shadow) -> str:
    """Re-realize an English claim's content into target_lang via concept
    round-trip. Literals (entities, numbers) and unknown words pass through.
    Returns the claim unchanged if target_lang is en or nothing could be
    translated (graceful — never invents)."""
    if target_lang == "en" or not claim.strip():
        return claim
    reverse = get_reverse()
    if not reverse.loaded or shadow is None or not getattr(shadow, "loaded", False):
        return claim

    out: list[str] = []
    translated_any = False
    for tok in _TOKEN.findall(claim):
        if not tok[0].isalpha():
            out.append(tok)
            continue
        # Only translate CONTENT words. Short tokens (<=3 chars) are almost all
        # function words ("the", "as", "is", "its") whose concept lookup would
        # mis-fire on polysemous QIDs — length is a content-word proxy that
        # needs no word list. Function-word realization is the M4b layer.
        if len(tok) <= 3:
            out.append(tok)
            continue
        # A capitalized mid-word token or one absent from the lexicon is a
        # literal (named entity / nonce value) — keep as-is.
        concepts = shadow.surfaces.get(_surface_key(tok), [])
        if not concepts:
            out.append(tok)
            continue
        surface = None
        for c in concepts[:3]:
            surface = reverse.surface(c, target_lang)
            if surface:
                break
        if surface:
            out.append(surface)
            translated_any = True
        else:
            out.append(tok)  # concept known but no target surface → keep source
    if not translated_any:
        return claim
    return _detokenize(out)


def _surface_key(token: str) -> str:
    text = unicodedata.normalize("NFD", token.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^\w]+", " ", text).strip()


def _detokenize(tokens: list[str]) -> str:
    text = ""
    for i, tok in enumerate(tokens):
        if i and (tok[0].isalnum() or tok in "([") and not (tokens[i - 1][-1] in "([" if tokens[i - 1] else False):
            text += " "
        elif i and not tok[0].isalnum() and tok not in ".,:;!?)]":
            text += " "
        text += tok
    return text.strip()
