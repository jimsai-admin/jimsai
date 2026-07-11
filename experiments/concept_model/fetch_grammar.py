"""fetch_grammar.py — source person-deixis paradigms from Wiktionary.

Why this exists: the CLL concept lexicon is noun-only (QRank). It has no
representation of grammatical PERSON, so the Surface Realizer can translate content
nouns ("name" -> "nom"/"Orúkọ") but cannot flip a recalled SELF-fact from the user's
first person ("my name is X") into the second person JimsAI must answer in ("your
name is X"). That closed-class grammar is documented explicitly on Wiktionary
(CC-BY-SA), including low-resource languages (Yoruba: mi = 1st-person possessive,
rẹ = 2nd-person). We fetch the 1st/2nd-person possessives + personal pronouns per
language and publish grammar.jsonl to R2 — DATA, not a code-baked table. The
realizer's flip mechanism then generalises to any language whose paradigm is present
(bounded by coverage, exactly like the lexicon).

Schema (grammar.jsonl):  {lang, role, person, number, surface, source, license, ...}
  role   = "possessive" | "pronoun"      person = 1 | 2        number = "s" | "p" | ""

Usage:  python fetch_grammar.py [lang ...]      # default: en fr yo sw zh es
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WIK = "https://en.wiktionary.org/w/api.php"
UA = "JimsAI-CLL-research/0.1 (jimstechinnovations@gmail.com)"
LICENSE = "CC-BY-SA-4.0 (Wiktionary)"

# Language code -> the English name Wiktionary uses in category/section headers.
LANG_NAME = {
    "en": "English", "fr": "French", "yo": "Yoruba", "sw": "Swahili",
    "zh": "Chinese", "es": "Spanish", "de": "German", "pt": "Portuguese",
}
# Wiktionary category suffixes that hold the person-deictic closed-class words.
# en/fr have specific "possessive determiners" categories; yo/es/… only have the
# BROAD "determiners" / "pronouns" categories — so we include both. person_number()
# filters every member to the 1st/2nd-person forms, so the breadth only costs recall
# of non-person words (articles, demonstratives), never wrong data.
ROLE_CATS = {
    "possessive": ["possessive determiners", "possessive adjectives", "determiners"],
    "pronoun": ["personal pronouns", "pronouns"],
}


def _get(params: dict) -> dict:
    url = WIK + "?" + urllib.parse.urlencode({**params, "format": "json", "formatversion": "2"})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=40).read())
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))
    return {}


def category_members(lang_name: str, cat_suffix: str) -> set[str]:
    members: set[str] = set()
    cont = None
    while True:
        params = {
            "action": "query", "list": "categorymembers",
            "cmtitle": f"Category:{lang_name} {cat_suffix}",
            "cmlimit": "500", "cmtype": "page",
        }
        if cont:
            params["cmcontinue"] = cont
        d = _get(params)
        for m in d.get("query", {}).get("categorymembers", []):
            title = m.get("title", "")
            if ":" not in title:  # skip namespaced entries
                members.add(title)
        cont = d.get("continue", {}).get("cmcontinue")
        if not cont:
            break
    return members


def person_number(word: str, lang_name: str) -> tuple[int | None, str]:
    """Return (person, number) for `word` in its `lang_name` section — parsed from
    Wiktionary, never guessed. Uses explicit person tags AND English-gloss deixis
    ("belonging to you" -> 2nd, "to me"/"the speaker" -> 1st), because en.Wiktionary
    documents person in the GLOSS, not always as a tag. These pages are multi-
    language, so the section MUST be isolated first (e.g. "mon" is an English noun
    and a French possessive). Ambiguous (both persons) -> (None, '')."""
    d = _get({"action": "parse", "page": word, "prop": "wikitext"})
    wt = d.get("parse", {}).get("wikitext", "")
    # Isolate the target language's own == section == (stop at the next L2 header).
    m = re.search(r"^==\s*" + re.escape(lang_name) + r"\s*==\s*$(.*?)(?=^==[^=]|\Z)", wt, re.S | re.M)
    if not m:
        return None, ""
    sec = m.group(1)
    low = sec[:3000].lower()
    defs = " ".join(re.findall(r"^#\s*[:*]?\s*(.+)$", sec[:3000], re.M)).lower()
    has1 = "first-person" in low or "first person" in low or bool(re.search(r"\b(to|of|belonging to) me\b", defs)) or "the speaker" in defs
    has2 = "second-person" in low or "second person" in low or bool(re.search(r"\b(to|of|belonging to) you\b", defs))
    person = 1 if (has1 and not has2) else 2 if (has2 and not has1) else None
    has_s = "singular" in low or "(one owner)" in defs or "one owner" in defs
    has_p = "plural" in low or "more owners" in defs
    number = "s" if (has_s and not has_p) else "p" if (has_p and not has_s) else ""
    return person, number


def main(argv: list[str]) -> int:
    langs = argv or ["en", "fr", "yo", "sw", "zh", "es"]
    data = Path(__file__).parent / "data"
    data.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    rows: list[dict] = []
    seen: set[tuple] = set()
    for lang in langs:
        name = LANG_NAME.get(lang)
        if not name:
            print(f"  {lang}: no Wiktionary language name mapped — skipped")
            continue
        for role, cats in ROLE_CATS.items():
            words: set[str] = set()
            for cat in cats:
                try:
                    words |= category_members(name, cat)
                except Exception as exc:
                    print(f"  {lang}/{cat}: {exc}")
            kept = 0
            for w in sorted(words):
                try:
                    person, number = person_number(w, name)
                except Exception:
                    person, number = None, ""
                time.sleep(0.05)
                if person in (1, 2):
                    key = (lang, role, person, number, w)
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append({
                        "lang": lang, "role": role, "person": person, "number": number,
                        "surface": w, "source": "wiktionary", "license": LICENSE,
                        "retrieved_at": now,
                    })
                    kept += 1
            print(f"  {lang}/{role}: {kept} person-marked forms")

    out = data / "grammar.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    manifest = data / "manifest.json"
    m = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
    m.setdefault("grammar", []).append({"retrieved_at": now, "langs": langs, "rows": len(rows), "source": "wiktionary"})
    manifest.write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {len(rows)} grammar rows -> {out}")

    # Publish to R2 (single source of truth for local + deploy) — same path as the lexicon.
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from seed_lexicon import publish_artifacts

        publish_artifacts(["grammar.jsonl"])
    except Exception as exc:
        print(f"note: R2 publish skipped ({exc})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
