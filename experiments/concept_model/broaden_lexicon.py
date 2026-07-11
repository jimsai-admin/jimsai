"""M5 (breadth) — extend the CLL lexicon to more concepts, FROM SOURCE.

The lexicon was built from the top-3,000 QRank concepts — popularity-ranked, so
it captures named topics/entities but misses common nouns ("city" @ rank 4148,
"engineer" @ 13331) that a person's factual sentence uses. That coverage gap
limits cross-lingual person recall (P4) and per-language realization (P11).

This adds QRank ranks [start, end) — the SAME CC0 popularity source, just
deeper — fetching multilingual labels+aliases (incl. zh variant codes) from
Wikidata and appending only NEW (lang, surface, concept) triples with full
provenance. No hand-curated word list: which concepts to add is decided by the
source's popularity ranking, not by the developer. New language/coverage = data.

Usage:
  python broaden_lexicon.py --start 3000 --end 15000
"""

from __future__ import annotations

import argparse
import csv
import gzip
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
TARGET_LANGS = ["en", "fr", "yo", "sw", "zh"]
VARIANT_FOLD = {"zh-hans": "zh", "zh-hant": "zh", "zh-cn": "zh", "zh-tw": "zh",
                "zh-sg": "zh", "zh-hk": "zh", "zh-mo": "zh", "zh-my": "zh"}
FETCH_LANGS = TARGET_LANGS + sorted(VARIANT_FOLD)


def qrank_slice(cache: Path, start: int, end: int) -> list[str]:
    qids = []
    with gzip.open(cache, "rt", encoding="utf-8") as fh:
        r = csv.reader(fh)
        next(r, None)
        for i, row in enumerate(r):
            if i >= end:
                break
            if i >= start and row and row[0].startswith("Q"):
                qids.append(row[0])
    return qids


def fetch_batch(qids: list[str]) -> dict:
    params = {"action": "wbgetentities", "ids": "|".join(qids),
              "props": "labels|aliases", "languages": "|".join(FETCH_LANGS), "format": "json"}
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=3000)
    ap.add_argument("--end", type=int, default=15000)
    args = ap.parse_args()
    data = Path(__file__).parent / "data"
    lex_path = data / "lexicon.jsonl"
    now = datetime.now(timezone.utc).isoformat()

    existing: set[tuple[str, str, str]] = set()
    for line in lex_path.open(encoding="utf-8"):
        row = json.loads(line)
        existing.add((row["lang"], row["surface"], row["concept"]))
    have_concepts = {c for _, _, c in existing}
    print(f"lexicon has {len(existing)} entries, {len(have_concepts)} concepts")

    qids = [q for q in qrank_slice(data / "qrank.csv.gz", args.start, args.end)
            if f"C:{q}" not in have_concepts]
    print(f"QRank [{args.start},{args.end}): {len(qids)} new concepts to fetch")

    added = {lang: 0 for lang in TARGET_LANGS}
    with lex_path.open("a", encoding="utf-8") as out:
        for i in range(0, len(qids), BATCH):
            entities = fetch_batch(qids[i:i + BATCH])
            for qid, ent in entities.items():
                surfaces: dict[str, set[str]] = {}
                for code, payload in ent.get("labels", {}).items():
                    lang = VARIANT_FOLD.get(code, code)
                    if lang in TARGET_LANGS:
                        surfaces.setdefault(lang, set()).add(payload["value"])
                for code, alist in ent.get("aliases", {}).items():
                    lang = VARIANT_FOLD.get(code, code)
                    if lang in TARGET_LANGS:
                        surfaces.setdefault(lang, set()).update(a["value"] for a in alist[:4])
                for lang, forms in surfaces.items():
                    for surface in forms:
                        key = (lang, surface, f"C:{qid}")
                        if key in existing:
                            continue
                        existing.add(key)
                        out.write(json.dumps({
                            "lang": lang, "surface": surface, "concept": f"C:{qid}",
                            "source": "wikidata", "source_id": qid, "license": LICENSE,
                            "retrieved_at": now, "build": "broaden_v1",
                        }, ensure_ascii=False) + "\n")
                        added[lang] += 1
            done = min(i + BATCH, len(qids))
            if done % 1000 < BATCH or done == len(qids):
                print(f"  {done}/{len(qids)} — added: {added}")
            time.sleep(0.1)

    mpath = data / "manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {}
    manifest.setdefault("broadenings", []).append(
        {"retrieved_at": now, "range": [args.start, args.end], "added": added})
    mpath.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nadded per language: {added}")
    # Publish the grown lexicon to R2 (single source of truth for local + deploy).
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from seed_lexicon import publish_artifacts

        publish_artifacts(["lexicon.jsonl"])
    except Exception as e:
        print(f"note: R2 publish skipped ({e})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
