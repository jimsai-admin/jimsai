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
        # Same single-source-of-truth lexicon as the concept index: loaded from R2
        # (not bundled in code), sharing one cached download via cloud_artifact.
        repo_data = Path(__file__).resolve().parents[2] / "experiments" / "concept_model" / "data"
        explicit = lexicon_path or os.getenv("JIMS_CONCEPT_LEXICON_PATH", "")
        if explicit:
            path = Path(explicit)
        else:
            from .cloud_artifact import artifact_path

            prefix = os.getenv("JIMS_LEXICON_R2_PREFIX", "concept-model")
            path = artifact_path(
                f"{prefix}/lexicon.jsonl",
                local_fallback=repo_data / "lexicon.jsonl",
            ) or (repo_data / "lexicon.jsonl")
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
        # Also vote with the language-tagged COMMON words. The lexicon is noun-only
        # (QRank), so it misses the function words ("quel"/"mon"/"ki"/"mi") that are
        # the STRONGEST language markers — which is why "Quel est mon nom?" fell back
        # to en (only the noun "nom" voted, weakly). The common-words artifact is
        # frequency-sourced per language (data, not a word list in code); adding its
        # surfaces to the language-vote lets bare-Latin queries detect correctly.
        if not explicit:
            try:
                from .cloud_artifact import artifact_path

                prefix = os.getenv("JIMS_LEXICON_R2_PREFIX", "concept-model")
                cw_path = artifact_path(
                    f"{prefix}/common_words.jsonl",
                    local_fallback=repo_data / "common_words.jsonl",
                ) or (repo_data / "common_words.jsonl")
                if cw_path.exists():
                    with cw_path.open(encoding="utf-8") as fh:
                        for line in fh:
                            try:
                                row = json.loads(line)
                            except Exception:
                                continue
                            lang = row.get("lang")
                            key = _surface_key(row.get("surface", ""))
                            if lang and key and " " not in key:
                                self.langs_of_surface[key].add(lang)
            except Exception:
                pass

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


# ── Person-deixis paradigms (grammar.jsonl, Wiktionary-sourced) ─────────────────
class GrammarParadigm:
    """1st/2nd-person possessives + pronouns per language, from grammar.jsonl
    (Wiktionary, CC-BY-SA — the closed-class grammar the noun lexicon lacks). Lets
    the realizer flip a recalled FIRST-person self-fact ("my name is X") into the
    SECOND person JimsAI answers in ("your name is X" / "votre nom …"). Singleton,
    loaded once from R2 — data, not a code-baked table; a language works as soon as
    its paradigm is present, and degrades gracefully when absent (no invention)."""

    def __init__(self) -> None:
        self.second: dict[str, dict[str, dict[str, str]]] = defaultdict(lambda: defaultdict(dict))
        self.first_en: dict[str, tuple[str, str]] = {}
        self.loaded = False
        repo_data = Path(__file__).resolve().parents[2] / "experiments" / "concept_model" / "data"
        try:
            from .cloud_artifact import artifact_path

            prefix = os.getenv("JIMS_LEXICON_R2_PREFIX", "concept-model")
            path = artifact_path(
                f"{prefix}/grammar.jsonl", local_fallback=repo_data / "grammar.jsonl"
            ) or (repo_data / "grammar.jsonl")
        except Exception:
            path = repo_data / "grammar.jsonl"
        if not path.exists():
            return
        try:
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    lang, role = row.get("lang"), row.get("role")
                    person, number = row.get("person"), row.get("number", "") or ""
                    surface = (row.get("surface") or "").strip()
                    if not (lang and role and surface and person in (1, 2)):
                        continue
                    if person == 2:
                        cur = self.second[lang][role].get(number)
                        if cur is None or len(surface) < len(cur):
                            self.second[lang][role][number] = surface
                    if person == 1 and lang == "en":
                        self.first_en[surface.lower()] = (role, number)
            self.loaded = bool(self.first_en)
        except Exception:
            self.loaded = False

    def second_person(self, lang: str, role: str, number: str) -> str | None:
        cands = self.second.get(lang, {}).get(role, {})
        # Prefer the UNMARKED, single-word determiner (modern "your" / "votre") over
        # a number-specific archaic form ("thy") or a multi-word pronominal one
        # ("le tien", "both of yours"). "" is the general form that fits any number.
        for key in ("", number, "s", "p"):
            v = cands.get(key)
            if v and " " not in v:
                return v
        for v in cands.values():
            if " " not in v:
                return v
        return None


_grammar: GrammarParadigm | None = None


def get_grammar() -> GrammarParadigm:
    global _grammar
    if _grammar is None:
        _grammar = GrammarParadigm()
    return _grammar


def _match_case(src: str, repl: str) -> str:
    return repl[:1].upper() + repl[1:] if src[:1].isupper() else repl


def flip_person(text: str, target_lang: str) -> str:
    """Flip English first-person deictics in a recalled self-fact to the target
    language's SECOND person: "My name is X" -> "Your name is X" (en) / "Votre name
    is X" (fr, before content realization). Preposed-possessive languages realize in
    place; postposed ones (e.g. Yoruba, "orúkọ rẹ") get the right word but may need
    reordering — the next grammar layer. No-op when the paradigm is unavailable."""
    g = get_grammar()
    if not g.loaded or not text.strip():
        return text
    toks = _TOKEN.findall(text)
    out: list[str] = []
    changed = False
    for i, tok in enumerate(toks):
        role_num = g.first_en.get(tok.lower()) if tok[:1].isalpha() else None
        if role_num:
            role, number = role_num
            # Possessives only for now ("my name" -> "your name"). Subject-pronoun
            # flips ("I am X" -> "You am X") need verb agreement — the next grammar
            # layer. A possessive DETERMINER is prenominal, so require a following
            # word; a mis-sourced standalone form then cannot be flipped.
            next_word = any(t[:1].isalpha() for t in toks[i + 1 : i + 3])
            if role == "possessive" and next_word:
                repl = g.second_person(target_lang, role, number) or g.second_person("en", role, number)
                if repl:
                    out.append(_match_case(tok, repl))
                    changed = True
                    continue
        out.append(tok)
    return _detokenize(out) if changed else text


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
