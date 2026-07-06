"""
Concept-Native Language Layer — v0 mini-prototype.

Pure Python, no services, no network. Tests the *index-level* claims of the CNL
design (docs/concept_native_language_layer.md):

  - words resolve to language-neutral concept IDs before storage
  - unknown terms (named entities, nonces) pass through as literals
  - memory is an inverted concept index; retrieval is IDF-weighted intersection
  - records form a graph, intersecting at shared concepts
  - queries naming literals require literal overlap (gap honesty at the index)

The seed lexicon below is DEMO DATA — a few dozen lemmas per language, just
enough to falsify or support the mechanism. Production seeding comes from
Wikidata lexemes / Open Multilingual WordNet / PanLex, and grows via the
human-reviewed loop described in the design doc.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field


# ── Normalization ─────────────────────────────────────────────────────────────

def normalize(surface: str) -> str:
    """Case-fold and strip combining marks so 'iṣẹ́' → 'ise', 'données' → 'donnees'.

    Tone/diacritic stripping loses real distinctions in Yoruba — acceptable for
    v0 lookup keys, flagged in the design doc as a hard truth for v1.
    """
    decomposed = unicodedata.normalize("NFD", surface.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def surface_key(surface: str) -> str:
    """Canonical lookup key for a lexicon surface form.

    Punctuation inside real-world labels must not break matching:
    'Georgia (country)' → 'georgia country'; '唐纳德·特朗普' → '唐纳德特朗普'
    (CJK runs re-joined across separators — CJK has no word spaces to preserve).
    Same transform is applied to input text at segmentation time, so keys and
    queries can never drift apart.
    """
    text = normalize(surface)
    text = re.sub(r"[^\w一-鿿]+", " ", text).strip()
    text = re.sub(r"(?<=[一-鿿]) (?=[一-鿿])", "", text)
    return re.sub(r"\s+", " ", text)


# ── Seed lexicon (demo data) ─────────────────────────────────────────────────
# (lang, normalized surface or space-joined phrase) → list of senses.
# A sense is (concept_id, context_concepts) — context is used for polysemy voting.

Sense = tuple[str, frozenset[str]]

_EN: dict[str, list[Sense]] = {
    # function / common words
    "the": [("C:the", frozenset())], "a": [("C:a", frozenset())],
    "my": [("C:my", frozenset())], "me": [("C:me", frozenset())],
    "i": [("C:i", frozenset())], "we": [("C:we", frozenset())],
    "is": [("C:be", frozenset())], "are": [("C:be", frozenset())],
    "was": [("C:be", frozenset())], "and": [("C:and", frozenset())],
    "of": [("C:of", frozenset())], "in": [("C:in", frozenset())],
    "at": [("C:at", frozenset())], "on": [("C:on", frozenset())],
    "as": [("C:as", frozenset())], "its": [("C:its", frozenset())],
    "our": [("C:our", frozenset())], "she": [("C:she", frozenset())],
    "when": [("C:when", frozenset())], "which": [("C:which", frozenset())],
    "what": [("C:what", frozenset())], "who": [("C:who", frozenset())],
    "does": [("C:do", frozenset())], "do": [("C:do", frozenset())],
    # content words
    "dog": [("C:dog", frozenset())], "cat": [("C:cat", frozenset())],
    "big": [("C:big", frozenset())], "small": [("C:small", frozenset())],
    "father": [("C:father", frozenset())],
    "bought": [("C:buy", frozenset())], "buy": [("C:buy", frozenset())],
    "lost": [("C:lose", frozenset())], "lose": [("C:lose", frozenset())],
    "project": [("C:project", frozenset())],
    "uses": [("C:use", frozenset())], "use": [("C:use", frozenset())],
    "primary": [("C:primary", frozenset())],
    "database": [("C:database", frozenset())],
    "lead": [("C:lead", frozenset())], "engineer": [("C:engineer", frozenset())],
    "based": [("C:located", frozenset())], "located": [("C:located", frozenset())],
    "city": [("C:city", frozenset())],
    "next": [("C:next", frozenset())], "hardware": [("C:hardware", frozenset())],
    "device": [("C:device", frozenset())],
    "codenamed": [("C:codename", frozenset())], "codename": [("C:codename", frozenset())],
    "replacing": [("C:replace", frozenset())], "replace": [("C:replace", frozenset())],
    "replaces": [("C:replace", frozenset())],
    "line": [("C:product_line", frozenset())],
    "man": [("C:man", frozenset())],
    "bites": [("C:bite", frozenset())], "bite": [("C:bite", frozenset())],
    # polysemy demo
    "bank": [
        ("C:bank_finance", frozenset({"C:money", "C:deposit", "C:account"})),
        ("C:riverbank", frozenset({"C:river", "C:water", "C:sit"})),
    ],
    "money": [("C:money", frozenset())],
    "deposited": [("C:deposit", frozenset())], "deposit": [("C:deposit", frozenset())],
    "sat": [("C:sit", frozenset())], "sit": [("C:sit", frozenset())],
    "river": [("C:river", frozenset())],
    # creative-intent vocabulary
    "write": [("C:write", frozenset())], "writes": [("C:write", frozenset())],
    "poem": [("C:poem", frozenset())], "story": [("C:story", frozenset())],
    "about": [("C:about", frozenset())],
    "please": [], "remember": [("C:remember", frozenset())],
}

_FR: dict[str, list[Sense]] = {
    "le": [("C:the", frozenset())], "la": [("C:the", frozenset())], "l": [("C:the", frozenset())],
    "quelle": [("C:which", frozenset())], "quel": [("C:which", frozenset())],
    "est": [("C:be", frozenset())], "et": [("C:and", frozenset())],
    "dans": [("C:in", frozenset())], "de": [("C:of", frozenset())],
    "qui": [("C:which", frozenset())], "se": [("C:se", frozenset())],
    "il": [("C:he", frozenset())], "t": [],
    "projet": [("C:project", frozenset())],
    "base de donnees": [("C:database", frozenset())],
    "utilise": [("C:use", frozenset())], "utiliser": [("C:use", frozenset())],
    "ville": [("C:city", frozenset())],
    "trouve": [("C:located", frozenset())],
    "nom de code": [("C:codename", frozenset())],
    "appareil": [("C:device", frozenset())],
    "remplace": [("C:replace", frozenset())],
    "gamme": [("C:product_line", frozenset())],
    "ecris": [("C:write", frozenset())], "ecrire": [("C:write", frozenset())],
    "poeme": [("C:poem", frozenset())], "histoire": [("C:story", frozenset())],
    "sur": [("C:about", frozenset())],
}

_YO: dict[str, list[Sense]] = {
    "ki ni": [("C:what", frozenset())], "ni": [("C:be", frozenset())],
    "wo": [("C:which", frozenset())], "ti": [("C:that_rel", frozenset())],
    "n": [], "yoo": [],
    "ilu": [("C:city", frozenset())],
    "ise akanse": [("C:project", frozenset())],
    "lo": [("C:use", frozenset())],
    "database": [("C:database", frozenset())],  # loanword in tech register
    "wa": [("C:located", frozenset())],
    "oruko": [("C:codename", frozenset())],  # name; codename in device context (v0 shortcut)
    "ero": [("C:device", frozenset())],
    "ropo": [("C:replace", frozenset())],
    "aja": [("C:dog", frozenset())],
    "ko": [("C:write", frozenset())],
    "ewi": [("C:poem", frozenset())],
    "itan": [("C:story", frozenset())],
    "nipa": [("C:about", frozenset())],
}

_ZH: dict[str, list[Sense]] = {
    "项目": [("C:project", frozenset())],
    "使用": [("C:use", frozenset())],
    "什么": [("C:what", frozenset())],
    "数据库": [("C:database", frozenset())],
    "城市": [("C:city", frozenset())],
    "在": [("C:in", frozenset())],
    "哪个": [("C:which", frozenset())],
    "代号": [("C:codename", frozenset())],
    "设备": [("C:device", frozenset())],
    "取代": [("C:replace", frozenset())],
    "系列": [("C:product_line", frozenset())],
    "是": [("C:be", frozenset())],
    "的": [],
    "狗": [("C:dog", frozenset())],
    "写": [("C:write", frozenset())],
    "诗": [("C:poem", frozenset())],
    "故事": [("C:story", frozenset())],
    "关于": [("C:about", frozenset())],
}

SEED_LEXICON: dict[str, dict[str, list[Sense]]] = {"en": _EN, "fr": _FR, "yo": _YO, "zh": _ZH}

# Function-word concepts carry no retrieval weight (they index nothing useful).
STOP_CONCEPTS = {
    "C:the", "C:a", "C:of", "C:in", "C:at", "C:on", "C:as", "C:and", "C:be",
    "C:do", "C:se", "C:he", "C:she", "C:its", "C:that_rel", "C:when",
    "C:which", "C:what", "C:who", "C:i", "C:we", "C:me",
}


# ── Encoder ───────────────────────────────────────────────────────────────────

_LATIN_TOKEN = re.compile(r"[^\W_]+")  # word chars only: hyphens/apostrophes split, matching surface_key
_CJK_RUN = re.compile(r"[一-鿿]+")


def strip_marks(text: str) -> str:
    """Remove combining marks but PRESERVE case (unlike normalize) — combining
    marks fragment tokenization (Yoruba 'Dọ́là' breaks mid-word otherwise),
    while case is needed downstream for hard-literal detection."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


@dataclass
class Encoded:
    concepts: list[str]           # resolved concept IDs, in order
    literals: list[str]           # name-like unknowns ("L:rovuku") — these GATE
    soft_literals: list[str] = field(default_factory=list)  # ordinary OOV words — index only
    trace: list[tuple[str, str]] = field(default_factory=list)  # (surface, resolution)


class ConceptEncoder:
    def __init__(self, lexicon: dict[str, dict[str, list[Sense]]] | None = None):
        self.lexicon = lexicon or SEED_LEXICON
        # Segmentation windows derive from the DATA, never from language rules:
        # longest multi-word phrase and longest CJK surface actually present.
        self._max_phrase = max(
            (key.count(" ") + 1 for entries in self.lexicon.values() for key in entries),
            default=1,
        )
        self._max_cjk = max(
            (len(key) for entries in self.lexicon.values() for key in entries
             if _CJK_RUN.fullmatch(key)),
            default=4,
        )

    def encode(self, text: str, lang: str) -> Encoded:
        lex = self.lexicon.get(lang, {})
        segments = self._segment(text, lang)
        # First pass: resolve unambiguous tokens; queue ambiguous ones
        resolved: list[tuple[str, str, list[Sense] | None, str | None]] = []
        for raw, surface in segments:
            senses = lex.get(surface)
            if senses is None and lang != "en":
                # Loanwords / code-switching: fall back to the English lexicon
                # before declaring a literal. Real per-token language ID is v1.
                senses = self.lexicon["en"].get(surface)
            if senses is None:
                resolved.append((raw, surface, None, f"L:{surface}"))
            elif len(senses) == 0:
                resolved.append((raw, surface, None, None))  # known but meaningless (particle)
            elif len(senses) == 1:
                resolved.append((raw, surface, None, senses[0][0]))
            else:
                resolved.append((raw, surface, senses, None))  # ambiguous, second pass
        context = {c for _, _, _, c in resolved if c and c.startswith("C:")}
        out = Encoded(concepts=[], literals=[])
        for raw, surface, senses, direct in resolved:
            if senses is not None:  # polysemous: vote by context overlap
                overlaps = [(len(s[1] & context), s[0]) for s in senses]
                best_overlap = max(score for score, _ in overlaps)
                if best_overlap > 0:
                    best = max(overlaps)[1]
                    out.concepts.append(best)
                    out.trace.append((surface, f"{best} (context vote)"))
                else:
                    # No contextual evidence to choose a sense — recall-first:
                    # emit the top candidates (source order = popularity order)
                    # and let retrieval intersection resolve which one the
                    # memory actually supports.
                    for _, candidate in overlaps[:3]:
                        out.concepts.append(candidate)
                    out.trace.append((surface, f"{[c for _, c in overlaps[:3]]} (ambiguous, candidates kept)"))
            elif direct is None:
                out.trace.append((surface, "particle (dropped)"))
            elif direct.startswith("L:"):
                # Only name-like unknowns gate retrieval (capitalized surface or
                # digits — how proper nouns and codenames look in any Latin-script
                # language). Ordinary words merely missing from the lexicon index
                # softly but must never veto a match — discovered via E6, where
                # OOV "by" in "a dog by the river" wrongly gated out an image.
                if any(ch.isupper() or ch.isdigit() for ch in raw):
                    out.literals.append(direct)
                    out.trace.append((surface, f"{direct} (hard literal)"))
                else:
                    out.soft_literals.append(direct)
                    out.trace.append((surface, f"{direct} (soft literal)"))
            else:
                out.concepts.append(direct)
                out.trace.append((surface, direct))
        return out

    def _segment(self, text: str, lang: str) -> list[tuple[str, str]]:
        """Split into lexicon-ready (raw, normalized) surfaces: latin words with
        greedy MWE grouping, CJK runs with greedy longest-match against the lexicon."""
        lex = self.lexicon.get(lang, {})
        # Re-join CJK runs split only by separators (·, spaces, dashes) so
        # multi-run surfaces like 唐纳德·特朗普 match their lexicon keys.
        text = re.sub(r"(?<=[一-鿿])[^\w一-鿿]+(?=[一-鿿])", "", text)
        surfaces: list[tuple[str, str]] = []
        for match in re.finditer(r"[一-鿿]+|[^一-鿿]+", text):
            chunk = match.group(0)
            if _CJK_RUN.fullmatch(chunk):
                surfaces.extend(self._segment_cjk(chunk, lex))
            else:
                stripped = strip_marks(chunk)
                words = [(w, w.lower()) for w in _LATIN_TOKEN.findall(stripped)]
                surfaces.extend(self._group_mwes(words, lex))
        return surfaces

    def _group_mwes(self, words: list[tuple[str, str]], lex: dict[str, list[Sense]]) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        i = 0
        while i < len(words):
            for size in range(self._max_phrase, 0, -1):
                phrase = " ".join(norm for _, norm in words[i : i + size])
                if size > 1 and phrase in lex:
                    out.append((" ".join(raw for raw, _ in words[i : i + size]), phrase))
                    i += size
                    break
            else:
                out.append(words[i])
                i += 1
        return out

    def _segment_cjk(self, run: str, lex: dict[str, list[Sense]]) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        i = 0
        while i < len(run):
            for size in range(self._max_cjk, 0, -1):
                piece = run[i : i + size]
                if len(piece) == size and (piece in lex or size == 1):
                    out.append((piece, piece))
                    i += size
                    break
        return out


# ── Concept memory: inverted index + record graph ─────────────────────────────

@dataclass
class Record:
    record_id: str
    text: str
    lang: str
    concepts: frozenset[str]
    literals: frozenset[str]
    sequence: tuple[str, ...]  # order preserved — needed by E5's honesty check
    modality: str = "text"
    provenance: dict[str, dict] = field(default_factory=dict)  # concept → region/confidence


@dataclass
class Detection:
    """What a bounded perception interface emits: a concept candidate with
    confidence and a source region — never free-form text."""
    concept: str
    confidence: float
    region: str  # bounding box "x,y,w,h" for images; "t0-t1" for video


class MockPerceptionInterface:
    """Stand-in for a CLIP/detector-class vision encoder (v1 uses a real one).

    It does NOT do computer vision — it replays detections supplied by the
    test. Its purpose is to pin down the CONTRACT: perception is a bounded
    interface emitting (concept, confidence, region) records, and everything
    downstream (indexing, retrieval, provenance, correction) treats those
    records identically to text-derived concepts.
    """

    def __init__(self, min_confidence: float = 0.5):
        self.min_confidence = min_confidence

    def perceive(self, detections: list[Detection]) -> list[Detection]:
        return [d for d in detections if d.confidence >= self.min_confidence]


@dataclass
class RelationEdge:
    subject: str
    predicate: str
    obj: str
    confidence: float
    source: str  # record id — every hop keeps provenance


class ConceptGraph:
    """Typed relations between concepts, with bounded multi-hop inference.

    Composition is PER-PREDICATE DATA, not code: a predicate composes across
    hops only if it appears in `transitive` (with a per-hop decay factor).
    "causes" chains; "chases" does not. In production these declarations come
    from the relation schema / source ontologies (Wikidata property metadata),
    never from a developer deciding per query. Inference that finds no path
    returns nothing — the honest gap — rather than a plausible guess.
    """

    def __init__(self, transitive: dict[str, float] | None = None):
        self.transitive = transitive or {}
        self._out: dict[tuple[str, str], list[RelationEdge]] = defaultdict(list)

    def add(self, subject: str, predicate: str, obj: str, confidence: float, source: str) -> None:
        self._out[(subject, predicate)].append(
            RelationEdge(subject, predicate, obj, confidence, source)
        )

    def remove(self, subject: str, predicate: str, obj: str) -> list[RelationEdge]:
        """Remove direct edges subject—predicate→obj; returns them so callers
        (e.g. masked-edge evaluation) can restore afterwards."""
        key = (subject, predicate)
        removed = [e for e in self._out.get(key, []) if e.obj == obj]
        if removed:
            self._out[key] = [e for e in self._out[key] if e.obj != obj]
        return removed

    def restore(self, edges: list[RelationEdge]) -> None:
        for edge in edges:
            self._out[(edge.subject, edge.predicate)].append(edge)

    def infer(self, subject: str, predicate: str, obj: str, max_hops: int = 4) -> list[tuple[list[RelationEdge], float]]:
        """All paths subject —predicate*→ obj with joint confidence + provenance.
        Single hops are always valid; multi-hop only for declared-transitive
        predicates, confidence = Π(hop confidences) × decay^(hops−1)."""
        decay = self.transitive.get(predicate)
        results: list[tuple[list[RelationEdge], float]] = []
        frontier: list[tuple[str, list[RelationEdge], float]] = [(subject, [], 1.0)]
        for hop in range(max_hops):
            if hop > 0 and decay is None:
                break  # non-composable predicate: single-hop only
            next_frontier: list[tuple[str, list[RelationEdge], float]] = []
            for node, path, conf in frontier:
                for edge in self._out.get((node, predicate), []):
                    if any(e.obj == edge.obj for e in path):
                        continue  # cycle guard
                    new_conf = conf * edge.confidence * (decay if hop > 0 else 1.0)
                    new_path = [*path, edge]
                    if edge.obj == obj:
                        results.append((new_path, round(new_conf, 4)))
                    else:
                        next_frontier.append((edge.obj, new_path, new_conf))
            frontier = next_frontier
        results.sort(key=lambda item: -item[1])
        return results


class TinyIntentClassifier:
    """T1-mini: intent classification over concept sequences, not raw text.

    A multinomial naive Bayes over concept-ID features — a few KB of counts,
    microsecond inference, trainable from the SPPE loop. The bet under test:
    because features are language-neutral concept IDs, a classifier trained on
    ENGLISH examples generalizes to any lexicon-covered language with zero
    per-language code or training data. Literals collapse to placeholder
    features (#L name-like / #l ordinary) so unseen entities don't perturb it.
    """

    def __init__(self):
        self.counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.class_feature_totals: dict[str, int] = defaultdict(int)
        self.class_examples: dict[str, int] = defaultdict(int)
        self.vocab: set[str] = set()

    @staticmethod
    def features(enc: Encoded) -> list[str]:
        return [
            *enc.concepts,
            *(["#L"] * len(enc.literals)),
            *(["#l"] * len(enc.soft_literals)),
        ]

    def train(self, enc: Encoded, label: str) -> None:
        for feat in self.features(enc):
            self.counts[label][feat] += 1
            self.class_feature_totals[label] += 1
            self.vocab.add(feat)
        self.class_examples[label] += 1

    def classify(self, enc: Encoded) -> tuple[str, float]:
        feats = self.features(enc)
        total_examples = sum(self.class_examples.values()) or 1
        v = len(self.vocab) or 1
        best_label, best_lp, second_lp = "", -1e18, -1e18
        for label in self.counts:
            lp = math.log(self.class_examples[label] / total_examples)
            denom = self.class_feature_totals[label] + v
            for feat in feats:
                lp += math.log((self.counts[label].get(feat, 0) + 1) / denom)
            if lp > best_lp:
                best_label, second_lp, best_lp = label, best_lp, lp
            elif lp > second_lp:
                second_lp = lp
        margin = best_lp - second_lp if second_lp > -1e18 else 0.0
        return best_label, margin


# T2-mini realization: concept → preferred surface form per language.
# Built by REVERSING the lexicon (first-listed sense wins) — it is derived
# data, never a hand-maintained table.

def build_reverse_lexicon(lexicon: dict[str, dict[str, list[Sense]]]) -> dict[str, dict[str, str]]:
    reverse: dict[str, dict[str, str]] = {}
    for lang, entries in lexicon.items():
        table: dict[str, str] = {}
        for surface, senses in entries.items():
            for concept, _ in senses:
                table.setdefault(concept, surface)
        reverse[lang] = table
    return reverse


def realize(items: list[str], lang: str, lexicon: dict[str, dict[str, list[Sense]]] | None = None) -> str:
    """T2-mini v0: structural realization of a concept/literal sequence in the
    target language. Knowledge-free by construction — it can only voice the
    concepts it is handed (a realizer with no world knowledge cannot hallucinate
    facts; there is nothing in it to hallucinate FROM). Fluency (morphology,
    agreement, word order beyond sequence) is the v1 grammar problem — this v0
    proves surface selection crosses languages from one derived table.
    """
    reverse = build_reverse_lexicon(lexicon or SEED_LEXICON).get(lang, {})
    words: list[str] = []
    for item in items:
        if item.startswith("L:"):
            words.append(item[2:].capitalize())
        else:
            words.append(reverse.get(item, item))
    joiner = "" if lang == "zh" else " "
    return joiner.join(words)


class ConceptMemory:
    def __init__(self, encoder: ConceptEncoder | None = None):
        self.encoder = encoder or ConceptEncoder()
        self.records: dict[str, Record] = {}
        self._postings: dict[str, set[str]] = defaultdict(set)

    def add(self, record_id: str, text: str, lang: str = "en") -> Record:
        enc = self.encoder.encode(text, lang)
        # Soft literals (ordinary OOV words) index alongside concepts — they can
        # support a match but never gate one. Hard literals gate (see retrieve).
        indexable = [c for c in enc.concepts if c not in STOP_CONCEPTS] + enc.soft_literals
        record = Record(
            record_id=record_id,
            text=text,
            lang=lang,
            concepts=frozenset(indexable),
            literals=frozenset(enc.literals),
            sequence=tuple(enc.concepts + enc.literals),
        )
        self.records[record_id] = record
        for key in record.concepts | record.literals:
            self._postings[key].add(record_id)
        return record

    def add_media(
        self,
        record_id: str,
        detections: list[Detection],
        modality: str = "image",
        perception: MockPerceptionInterface | None = None,
        description: str = "",
    ) -> Record:
        """Ingest a non-text record through a bounded perception interface.

        Accepted detections index exactly like text-derived concepts; each keeps
        its region + confidence as provenance so a claim grounded in this record
        can point at the pixels/timespan that support it.
        """
        perception = perception or MockPerceptionInterface()
        accepted = perception.perceive(detections)
        record = Record(
            record_id=record_id,
            text=description or f"<{modality}:{record_id}>",
            lang="-",
            concepts=frozenset(d.concept for d in accepted),
            literals=frozenset(),
            sequence=tuple(d.concept for d in accepted),
            modality=modality,
            provenance={d.concept: {"region": d.region, "confidence": d.confidence} for d in accepted},
        )
        self.records[record_id] = record
        for key in record.concepts:
            self._postings[key].add(record_id)
        return record

    def correct_media_concept(self, record_id: str, wrong: str, right: str) -> None:
        """Human correction as a graph edit — no retraining. 'That's not a dog,
        it's a fox' re-labels the concept and re-indexes the record."""
        record = self.records[record_id]
        if wrong not in record.concepts:
            return
        prov = dict(record.provenance)
        prov[right] = {**prov.pop(wrong), "corrected_from": wrong}
        updated = Record(
            record_id=record.record_id,
            text=record.text,
            lang=record.lang,
            concepts=(record.concepts - {wrong}) | {right},
            literals=record.literals,
            sequence=tuple(right if c == wrong else c for c in record.sequence),
            modality=record.modality,
            provenance=prov,
        )
        self.records[record_id] = updated
        self._postings[wrong].discard(record_id)
        self._postings[right].add(record_id)

    def _idf(self, key: str) -> float:
        df = len(self._postings.get(key, ()))
        if df == 0:
            return 0.0
        return math.log(1.0 + len(self.records) / df)

    def retrieve(self, query: str, lang: str = "en", limit: int = 5) -> list[tuple[Record, float, list[str]]]:
        enc = self.encoder.encode(query, lang)
        q_concepts = {c for c in enc.concepts if c not in STOP_CONCEPTS} | set(enc.soft_literals)
        q_literals = set(enc.literals)
        candidates: set[str] = set()
        for key in q_concepts | q_literals:
            candidates |= self._postings.get(key, set())
        scored: list[tuple[Record, float, list[str]]] = []
        for rid in candidates:
            record = self.records[rid]
            # Gap honesty at the index: a query that names specific literals
            # (entities unknown to the lexicon) admits only records sharing one.
            if q_literals and not (q_literals & record.literals):
                continue
            shared = (q_concepts & record.concepts) | (q_literals & record.literals)
            if not shared:
                continue
            score = sum(self._idf(key) for key in shared)
            scored.append((record, round(score, 4), sorted(shared)))
        scored.sort(key=lambda item: (-item[1], item[0].record_id))
        return scored[:limit]

    def related(self, record_id: str, limit: int = 5) -> list[tuple[Record, float, list[str]]]:
        """Graph intersection: records connected through shared concepts,
        IDF-weighted so ubiquitous concepts don't dominate the links."""
        seed = self.records[record_id]
        neighbors: dict[str, set[str]] = defaultdict(set)
        for key in seed.concepts | seed.literals:
            for rid in self._postings.get(key, set()):
                if rid != record_id:
                    neighbors[rid].add(key)
        out = [
            (self.records[rid], round(sum(self._idf(k) for k in keys), 4), sorted(keys))
            for rid, keys in neighbors.items()
        ]
        out.sort(key=lambda item: (-item[1], item[0].record_id))
        return out[:limit]
