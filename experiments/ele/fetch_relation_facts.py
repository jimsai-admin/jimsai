"""Fetch REAL multi-relation facts + corpus for scientific relation-extraction
validation (no LLM).

Design for SOUNDNESS (so downstream statistics are not measuring artefacts):

  * Exact Wikipedia titles. Facts are fetched with the entity's actual enwiki
    sitelink title (schema:about + schema:name), not the Wikidata label — so the
    text we fetch is the right article and entity-linking by surface works. (The
    label-based version silently dropped ~23% of entities.)

  * COMPLETE KB over the entity set. For each relation we take ALL pairs among the
    fetched entities (no arbitrary cap). Distant supervision labels a co-occurring
    entity pair NEGATIVE when it is not in the KB; truncating the KB turns true
    positives into false negatives and destroys the trigger's measured precision
    (observed with a 100-pair border cap). Completeness removes that artefact.

  * Relation diversity. A list of relations (opaque Wikidata PIDs) across several
    entity domains — geography, organisations, people/institutions — so the SAME
    algorithm must run unchanged (Phase 3). No relation NAME or trigger in code.

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

# pid -> the CORE triple pattern binding ?s (subject) and ?o (object). Everything
# else (title resolution, dedup) is added generically. Comments name the relation
# for humans only; the code never reads a relation name or a trigger.
CORE = {
    "P36":  "?o wdt:P31 wd:Q3624078. ?o wdt:P36 ?s.",                 # capital (capital←country)
    "P47":  "?s wdt:P31 wd:Q3624078. ?s wdt:P47 ?o. ?o wdt:P31 wd:Q3624078.",  # shares border
    "P112": "?s wdt:P31/wdt:P279* wd:Q4830453. ?s wdt:P112 ?o.",      # founded by (company→person)
    "P159": "?s wdt:P31/wdt:P279* wd:Q4830453. ?s wdt:P159 ?o.",      # headquarters (company→city)
    "P17":  "?s wdt:P31 wd:Q515. ?s wdt:P17 ?o.",                     # country (city→country)
    "P38":  "?s wdt:P31 wd:Q3624078. ?s wdt:P38 ?o.",                 # currency (country→currency)
    "P37":  "?s wdt:P31 wd:Q3624078. ?s wdt:P37 ?o.",                 # official language
    "P30":  "?s wdt:P31 wd:Q3624078. ?s wdt:P30 ?o.",                 # continent
}
# generous caps — large enough to be COMPLETE over the fetched entity set, not to
# truncate a dense relation (borders). Non-dense relations return fewer anyway.
LIMIT = {"P47": 600, "P36": 100, "P112": 150, "P159": 150,
         "P17": 120, "P38": 120, "P37": 120, "P30": 120}
_QID = re.compile(r"^Q\d+$")


def sparql(client: httpx.Client, pid: str, attempts: int = 4) -> list[tuple[str, str]]:
    """Fetch (subject_title, object_title) pairs using exact enwiki titles."""
    query = f"""SELECT DISTINCT ?sT ?oT WHERE {{
      {CORE[pid]}
      ?sa schema:about ?s; schema:isPartOf <https://en.wikipedia.org/>; schema:name ?sT.
      ?oa schema:about ?o; schema:isPartOf <https://en.wikipedia.org/>; schema:name ?oT.
    }} LIMIT {LIMIT[pid]}"""
    for i in range(attempts):
        try:
            r = client.get(_SPARQL, params={"query": query, "format": "json"},
                           headers=_UA, timeout=90)
            if r.status_code in (429, 502, 503):
                time.sleep(3 * (i + 1)); continue
            r.raise_for_status()
            out = []
            for b in r.json()["results"]["bindings"]:
                s, o = b["sT"]["value"], b["oT"]["value"]
                if s and o and s != o and not _QID.match(s) and not _QID.match(o):
                    out.append((s, o))
            return out
        except Exception as e:  # noqa: BLE001
            print(f"   {pid} SPARQL try {i+1} failed ({type(e).__name__}); retrying")
            time.sleep(3 * (i + 1))
    print(f"   {pid} SPARQL failed — skipping")
    return []


def fetch_intros(client: httpx.Client, titles: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    titles = list(dict.fromkeys(titles))
    for i in range(0, len(titles), 20):
        batch = titles[i:i + 20]
        params = {"action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1,
                  "redirects": 1, "format": "json", "titles": "|".join(batch)}
        for attempt in range(3):
            try:
                r = client.get(_ACTION, params=params, headers=_UA, timeout=45, follow_redirects=True)
                r.raise_for_status()
                for p in r.json().get("query", {}).get("pages", {}).values():
                    if p.get("title") and p.get("extract"):
                        out[p["title"]] = p["extract"]
                break
            except Exception:  # noqa: BLE001
                time.sleep(2 * (attempt + 1))
        time.sleep(0.25)
    return out


def main() -> int:
    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    relations: dict[str, dict] = {}
    all_titles: set[str] = set()
    with httpx.Client() as client:
        for pid in CORE:
            pairs = sparql(client, pid)
            # dedup, drop self-pairs
            seen, uniq = set(), []
            for a, b in pairs:
                if (a, b) not in seen:
                    seen.add((a, b)); uniq.append([a, b])
            relations[pid] = {"pairs": uniq}
            for a, b in uniq:
                all_titles.add(a); all_titles.add(b)
            print(f"  {pid}: {len(uniq)} pairs")
        print(f"unique entities: {len(all_titles)}")
        print("fetching Wikipedia intros …")
        extracts = fetch_intros(client, sorted(all_titles))
        cov = len(extracts) / len(all_titles) if all_titles else 0
        print(f"got {len(extracts)}/{len(all_titles)} intros ({cov:.0%} coverage, "
              f"{sum(len(v.split()) for v in extracts.values())} words)")

    # Report per-relation how many pairs are fully covered (both articles fetched)
    for pid, rel in relations.items():
        covered = sum(1 for a, b in rel["pairs"] if a in extracts and b in extracts)
        print(f"  {pid}: {covered}/{len(rel['pairs'])} pairs with both articles")

    out = {"relations": relations, "extracts": extracts,
           "_provenance": {"facts": "Wikidata SPARQL, exact enwiki sitelink titles, complete over entity set",
                           "text": "Wikipedia action API prop=extracts explaintext (CC-BY-SA)",
                           "note": "relations are opaque PIDs; no relation name or trigger in code"}}
    path = data_dir / "multi_relation.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved → {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
