"""CLL lexicon enrichment — fill non-English surface gaps FROM SOURCE (Rule 1).

Why this exists (M1 shadow finding, 2026-07-07): live cross-lingual queries
missed on zh because concepts already IN the lexicon lack zh surfaces:
  - build_lexicon.py records crawled P279 superclass nodes with en labels only;
  - it requests the exact language code `zh`, but Wikidata frequently stores
    Chinese labels under variant codes (zh-hans, zh-cn, zh-hant, ...).

This script re-fetches labels+aliases for EVERY concept already in the lexicon,
for all target languages plus zh variant codes (folded to lang="zh"), and
appends only entries whose (lang, surface, concept) triple is new. Pure data
repair with full provenance; no code path changes, no surfaces named here.

Usage:
  python enrich_lexicon.py            # enrich data/lexicon.jsonl in place (append)
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WD_API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "JimsAI-CLL-research/0.1 (jimstechinnovations@gmail.com) httpx"
LICENSE = "CC0-1.0 (Wikidata/Wikimedia)"
BATCH = 50

TARGET_LANGS = ["en", "fr", "yo", "zh", "sw"]
# Wikidata Chinese labels live under many variant codes; all fold to "zh"
# (the lexicon key is (lang, surface); surface_key() strips nothing CJK-wise).
VARIANT_FOLD = {
    "zh-hans": "zh", "zh-hant": "zh", "zh-cn": "zh", "zh-tw": "zh",
    "zh-sg": "zh", "zh-hk": "zh", "zh-mo": "zh", "zh-my": "zh",
}
FETCH_LANGS = TARGET_LANGS + sorted(VARIANT_FOLD)


def fetch_batch(qids: list[str]) -> dict:
    params = {
        "action": "wbgetentities",
        "ids": "|".join(qids),
        "props": "labels|aliases",
        "languages": "|".join(FETCH_LANGS),
        "format": "json",
    }
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60.0) as client:
        for attempt in range(4):
            try:
                resp = client.get(WD_API, params=params)
                resp.raise_for_status()
                return resp.json().get("entities", {})
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(3 * (attempt + 1))
    return {}


def main() -> int:
    data = Path(__file__).parent / "data"
    lex_path = data / "lexicon.jsonl"
    now = datetime.now(timezone.utc).isoformat()

    existing: set[tuple[str, str, str]] = set()
    concepts: set[str] = set()
    for line in lex_path.open(encoding="utf-8"):
        row = json.loads(line)
        existing.add((row["lang"], row["surface"], row["concept"]))
        concepts.add(row["concept"])
    qids = sorted(c[2:] for c in concepts if c.startswith("C:Q"))
    print(f"{len(qids)} concepts in lexicon; {len(existing)} existing entries")

    added = {lang: 0 for lang in TARGET_LANGS}
    with lex_path.open("a", encoding="utf-8") as out:
        for i in range(0, len(qids), BATCH):
            entities = fetch_batch(qids[i : i + BATCH])
            for qid, ent in entities.items():
                labels = ent.get("labels", {})
                aliases = ent.get("aliases", {})
                surfaces: dict[str, set[str]] = {}
                for code, payload in labels.items():
                    lang = VARIANT_FOLD.get(code, code)
                    if lang in TARGET_LANGS:
                        surfaces.setdefault(lang, set()).add(payload["value"])
                for code, alist in aliases.items():
                    lang = VARIANT_FOLD.get(code, code)
                    if lang in TARGET_LANGS:
                        surfaces.setdefault(lang, set()).update(
                            a["value"] for a in alist[:4])
                for lang, forms in surfaces.items():
                    for surface in forms:
                        key = (lang, surface, f"C:{qid}")
                        if key in existing:
                            continue
                        existing.add(key)
                        out.write(json.dumps({
                            "lang": lang, "surface": surface, "concept": f"C:{qid}",
                            "source": "wikidata", "source_id": qid,
                            "license": LICENSE, "retrieved_at": now,
                            "build": "enrich_v1",
                        }, ensure_ascii=False) + "\n")
                        added[lang] += 1
            done = min(i + BATCH, len(qids))
            if done % 1000 < BATCH or done == len(qids):
                print(f"  {done}/{len(qids)} — added so far: {added}")
            time.sleep(0.1)

    manifest_path = data / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    manifest.setdefault("enrichments", []).append(
        {"retrieved_at": now, "added": added, "fetch_langs": FETCH_LANGS,
         "license": LICENSE, "label_source": WD_API})
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nadded entries per language: {added}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
