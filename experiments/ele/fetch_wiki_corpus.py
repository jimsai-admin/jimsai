"""Fetch a REAL corpus for self-supervised relation extraction (no LLM).

Provenance: Wikipedia intro extracts via the MediaWiki action API
(`prop=extracts&explaintext`), CC-BY-SA. This is real prose we did NOT write —
the whole point: the ELE construction-discovery must survive text as people
actually write it, not 5 clean templates.

The seed KB is a set of TRUE `capital_of(capital, country)` facts (world
knowledge, not designed to pass). Distant supervision (see the experiment) labels
any sentence mentioning both members of a known pair as a positive occurrence of
the relation, and any sentence mentioning two KB entities that are NOT a known
pair as a negative — so both the constructions AND the negatives come from real
text, in two languages, with zero hardcoded markers.

Run: .venv/Scripts/python.exe experiments/ele/fetch_wiki_corpus.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# (capital, country) — TRUE facts. English surface forms. A larger, real slice so
# the discriminative trigger clears support in BOTH languages (breadth = data, the
# training-agent's job — not a lowered threshold).
EN_PAIRS = [
    ("Paris", "France"), ("Tokyo", "Japan"), ("Berlin", "Germany"),
    ("Ottawa", "Canada"), ("Canberra", "Australia"), ("Nairobi", "Kenya"),
    ("Cairo", "Egypt"), ("Lima", "Peru"), ("Oslo", "Norway"), ("Vienna", "Austria"),
    ("Madrid", "Spain"), ("Rome", "Italy"), ("Lisbon", "Portugal"), ("Athens", "Greece"),
    ("Helsinki", "Finland"), ("Warsaw", "Poland"), ("Bangkok", "Thailand"),
    ("Hanoi", "Vietnam"), ("Santiago", "Chile"), ("Dublin", "Ireland"),
    ("Stockholm", "Sweden"), ("Copenhagen", "Denmark"), ("Budapest", "Hungary"),
    ("Jakarta", "Indonesia"), ("Manila", "Philippines"), ("Brasília", "Brazil"),
    ("Moscow", "Russia"), ("Beijing", "China"), ("Ankara", "Turkey"),
    ("Brussels", "Belgium"), ("Amsterdam", "Netherlands"), ("Bern", "Switzerland"),
    ("Prague", "Czechia"), ("Bucharest", "Romania"), ("Sofia", "Bulgaria"),
    ("Belgrade", "Serbia"), ("Zagreb", "Croatia"), ("Kyiv", "Ukraine"),
    ("Reykjavík", "Iceland"), ("Tehran", "Iran"), ("Baghdad", "Iraq"),
    ("Islamabad", "Pakistan"), ("Kathmandu", "Nepal"), ("Wellington", "New Zealand"),
    ("Nairobi", "Kenya"), ("Tunis", "Tunisia"), ("Rabat", "Morocco"),
]

# French surface forms — SAME relation, DIFFERENT language (the frame the model
# must discover is "est la capitale de …", learned from data, not hardcoded).
FR_PAIRS = [
    ("Paris", "France"), ("Berlin", "Allemagne"), ("Madrid", "Espagne"),
    ("Rome", "Italie"), ("Lisbonne", "Portugal"), ("Vienne", "Autriche"),
    ("Oslo", "Norvège"), ("Athènes", "Grèce"), ("Varsovie", "Pologne"),
    ("Tokyo", "Japon"), ("Moscou", "Russie"), ("Stockholm", "Suède"),
    ("Copenhague", "Danemark"), ("Dublin", "Irlande"), ("Helsinki", "Finlande"),
    ("Ankara", "Turquie"), ("Le Caire", "Égypte"), ("Ottawa", "Canada"),
    ("Bruxelles", "Belgique"), ("Amsterdam", "Pays-Bas"), ("Berne", "Suisse"),
    ("Prague", "Tchéquie"), ("Bucarest", "Roumanie"), ("Sofia", "Bulgarie"),
    ("Belgrade", "Serbie"), ("Zagreb", "Croatie"), ("Kiev", "Ukraine"),
    ("Reykjavik", "Islande"), ("Téhéran", "Iran"), ("Bagdad", "Irak"),
    ("Rabat", "Maroc"), ("Tunis", "Tunisie"), ("Lima", "Pérou"),
    ("Madrid", "Espagne"), ("Nairobi", "Kenya"), ("Wellington", "Nouvelle-Zélande"),
    ("Bangkok", "Thaïlande"), ("Santiago", "Chili"), ("Budapest", "Hongrie"),
]

_HOST = {"en": "https://en.wikipedia.org/w/api.php", "fr": "https://fr.wikipedia.org/w/api.php"}
_UA = {"User-Agent": "JimsAI-research/0.1 (jimstechinnovations@gmail.com) offline ELE experiment"}


def _titles(pairs: list[tuple[str, str]]) -> list[str]:
    seen: dict[str, None] = {}
    for cap, country in pairs:
        seen.setdefault(cap, None)
        seen.setdefault(country, None)
    return list(seen)


def fetch_lang(client: httpx.Client, lang: str, titles: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for i in range(0, len(titles), 20):
        batch = titles[i:i + 20]
        params = {
            "action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1,
            "redirects": 1, "format": "json", "titles": "|".join(batch),
        }
        r = client.get(_HOST[lang], params=params, headers=_UA, timeout=30, follow_redirects=True)
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})
        for p in pages.values():
            title, extract = p.get("title"), p.get("extract")
            if title and extract:
                out[title] = extract
        time.sleep(0.4)  # be polite
    return out


def main() -> int:
    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    corpus: dict[str, dict] = {}
    with httpx.Client() as client:
        for lang, pairs in (("en", EN_PAIRS), ("fr", FR_PAIRS)):
            titles = _titles(pairs)
            print(f"[{lang}] fetching {len(titles)} article intros …")
            extracts = fetch_lang(client, lang, titles)
            print(f"[{lang}] got {len(extracts)}/{len(titles)} extracts "
                  f"({sum(len(v.split()) for v in extracts.values())} words)")
            corpus[lang] = {
                "pairs": pairs,
                "extracts": extracts,
                "missing": [t for t in titles if t not in extracts],
            }
    corpus["_provenance"] = {
        "source": "Wikipedia action API prop=extracts explaintext (CC-BY-SA)",
        "relation": "capital_of(capital, country)",
        "note": "real prose; distant-supervision labels from the seed KB pairs",
    }
    out = data_dir / "wiki_extracts.json"
    out.write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
