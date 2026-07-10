"""Fetch REAL multi-relation facts + corpus for open relation discovery (no LLM).

Answers the "are you hardcoding relations like capital_of?" challenge at the
SOURCE: the relations and their facts come from Wikidata (SPARQL), not typed into
the code. Three DISTINCT relations across TWO entity domains, so the discovery
mechanism must be relation-agnostic, not tuned to geography:

  P36  capital       (capital  → country)   geographic
  P47  shares_border (country  → country)   geographic, symmetric
  P19  born_in       (person   → city)      biographical, different entity type

The Wikidata property IDs (P36/P47/P19) are opaque identifiers — the code never
contains a relation NAME or a trigger word. The corpus is real Wikipedia intros
(CC-BY-SA) for every entity involved. Downstream, distant supervision uses these
facts only to LABEL/SCORE; the trigger and (in open mode) the relations
themselves are discovered from text.

Run: .venv/Scripts/python.exe experiments/ele/fetch_relation_facts.py
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_UA = {"User-Agent": "JimsAI-research/0.1 (jimstechinnovations@gmail.com) offline ELE experiment"}
_SPARQL = "https://query.wikidata.org/sparql"
_ACTION = "https://en.wikipedia.org/w/api.php"

# Property → a SPARQL body binding ?s and ?o labels as ?sL ?oL. Nothing here is a
# trigger or a natural-language relation name — only opaque Wikidata PIDs. Three
# distinct relations across TWO entity domains (geography ×2, organisations ×1):
#   P36  capital        (capital → country)
#   P47  shares_border  (country → country, symmetric)
#   P112 founded_by     (company → person)
QUERIES = {
    "P36": """SELECT ?sL ?oL WHERE {
        ?o wdt:P31 wd:Q3624078; wdt:P36 ?s.
        SERVICE wikibase:label { bd:serviceParam wikibase:language "en".
          ?s rdfs:label ?sL. ?o rdfs:label ?oL. } } LIMIT 90""",
    "P47": """SELECT ?sL ?oL WHERE {
        ?s wdt:P31 wd:Q3624078; wdt:P47 ?o. ?o wdt:P31 wd:Q3624078.
        SERVICE wikibase:label { bd:serviceParam wikibase:language "en".
          ?s rdfs:label ?sL. ?o rdfs:label ?oL. } } LIMIT 400""",
    "P112": """SELECT ?sL ?oL WHERE {
        ?s wdt:P31/wdt:P279* wd:Q4830453; wdt:P112 ?o.
        SERVICE wikibase:label { bd:serviceParam wikibase:language "en".
          ?s rdfs:label ?sL. ?o rdfs:label ?oL. } } LIMIT 160""",
}
_QID = re.compile(r"^Q\d+$")


def sparql(client: httpx.Client, query: str, attempts: int = 4) -> list[tuple[str, str]]:
    """SPARQL with retry — Wikidata returns transient 502/429 under load."""
    last = None
    for i in range(attempts):
        try:
            r = client.get(_SPARQL, params={"query": query, "format": "json"},
                           headers=_UA, timeout=60)
            if r.status_code in (429, 502, 503):
                last = f"{r.status_code}"; time.sleep(2 * (i + 1)); continue
            r.raise_for_status()
            out = []
            for b in r.json()["results"]["bindings"]:
                s, o = b["sL"]["value"], b["oL"]["value"]
                if _QID.match(s) or _QID.match(o) or not s or not o:
                    continue  # skip entities with no English label
                out.append((s, o))
            return out
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}"; time.sleep(2 * (i + 1))
    print(f"   SPARQL failed after {attempts} tries ({last}) — skipping this relation")
    return []


def fetch_intros(client: httpx.Client, titles: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    titles = list(dict.fromkeys(titles))
    for i in range(0, len(titles), 20):
        batch = titles[i:i + 20]
        params = {"action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1,
                  "redirects": 1, "format": "json", "titles": "|".join(batch)}
        r = client.get(_ACTION, params=params, headers=_UA, timeout=40, follow_redirects=True)
        r.raise_for_status()
        for p in r.json().get("query", {}).get("pages", {}).values():
            if p.get("title") and p.get("extract"):
                out[p["title"]] = p["extract"]
        time.sleep(0.3)
    return out


def main() -> int:
    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    relations: dict[str, dict] = {}
    all_titles: set[str] = set()
    with httpx.Client() as client:
        # capitals + borders share the country/capital entity domain
        caps = sparql(client, QUERIES["P36"])[:80]
        relations["P36"] = {"pairs": caps}

        borders_all = sparql(client, QUERIES["P47"])
        # keep border pairs whose BOTH countries appear as capitals' countries
        countries = {o for _s, o in caps}
        borders = [(a, b) for a, b in borders_all if a in countries and b in countries][:100]
        relations["P47"] = {"pairs": borders}

        # organisations domain — founded_by (company → person)
        founded = sparql(client, QUERIES["P112"])[:90]
        relations["P112"] = {"pairs": founded}

        for rel in relations.values():
            for s, o in rel["pairs"]:
                all_titles.add(s); all_titles.add(o)
        print(f"facts: P36={len(caps)} P47={len(borders)} P112={len(founded)} "
              f"| unique entities={len(all_titles)}")

        print("fetching Wikipedia intros …")
        extracts = fetch_intros(client, sorted(all_titles))
        print(f"got {len(extracts)}/{len(all_titles)} intros "
              f"({sum(len(v.split()) for v in extracts.values())} words)")

    out = {
        "relations": relations,
        "extracts": extracts,
        "_provenance": {
            "facts": "Wikidata SPARQL (P36 capital, P47 shares-border, P19 place-of-birth)",
            "text": "Wikipedia action API prop=extracts explaintext (CC-BY-SA)",
            "note": "relations identified by opaque PIDs; no relation name or trigger in code",
        },
    }
    path = data_dir / "multi_relation.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved → {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
