"""
CLL v1 lexicon builder — FROM SOURCE, per the anti-hardcoding protocol (Rule 1).

The repo holds this build script, never lexicon data:
  - WHICH concepts matter: Wikimedia QRank (CC0) — QIDs ranked by real page
    views. Popularity comes from the source, not from any list in this repo.
  - WHAT they're called per language: Wikidata labels + aliases (CC0) via the
    wbgetentities API.
  - HOW they relate: P279 (subclass-of) claims from the same API responses.

Every entry records source, source_id, license, and retrieval timestamp.

Outputs (experiments/concept_model/data/):
  lexicon.jsonl   {lang, surface, concept, source, source_id, license, retrieved_at}
  edges.jsonl     {subject, predicate: "P279", object, source, license, retrieved_at}
  manifest.json   build provenance (counts, params, timestamps)

Usage:
  python build_lexicon.py --languages en,fr,yo,zh,sw --top 3000
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

QRANK_URL = "https://qrank.wmcloud.org/download/qrank.csv.gz"
WD_API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "JimsAI-CLL-research/0.1 (jimstechinnovations@gmail.com) httpx"
LICENSE = "CC0-1.0 (Wikidata/Wikimedia)"
BATCH = 50  # wbgetentities max ids per anonymous request


def fetch_qrank_top(n: int, cache: Path) -> list[str]:
    if not cache.exists():
        print(f"downloading QRank ({QRANK_URL}) ...")
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=300.0, follow_redirects=True) as client:
            resp = client.get(QRANK_URL)
            resp.raise_for_status()
            cache.write_bytes(resp.content)
        print(f"  cached {cache.stat().st_size/1e6:.0f} MB")
    qids: list[str] = []
    with gzip.open(cache, "rt", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        next(reader, None)  # header: Entity,QRank
        for row in reader:
            if row and row[0].startswith("Q"):
                qids.append(row[0])
                if len(qids) >= n:
                    break
    return qids


def fetch_entities(qids: list[str], languages: list[str]) -> dict:
    """labels + P279 claims for a batch of QIDs."""
    params = {
        "action": "wbgetentities",
        "ids": "|".join(qids),
        "props": "labels|aliases|claims",
        "languages": "|".join(languages),
        "format": "json",
    }
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60.0) as client:
        for attempt in range(3):
            try:
                resp = client.get(WD_API, params=params)
                resp.raise_for_status()
                return resp.json().get("entities", {})
            except Exception as exc:
                if attempt == 2:
                    raise
                time.sleep(3 * (attempt + 1))
    return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--languages", default="en,fr,yo,zh,sw")
    ap.add_argument("--top", type=int, default=3000)
    ap.add_argument("--out", default=str(Path(__file__).parent / "data"))
    ap.add_argument("--crawl-depth", type=int, default=3,
                    help="follow P279 chains upward N levels beyond the seed set, so real "
                         "subclass chains exist for inference tests")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    languages = [x.strip() for x in args.languages.split(",") if x.strip()]
    now = datetime.now(timezone.utc).isoformat()

    qids = fetch_qrank_top(args.top, out_dir / "qrank.csv.gz")
    print(f"top {len(qids)} QIDs by QRank (source-ranked, not repo-ranked)")

    lexicon_count = {lang: 0 for lang in languages}
    edge_count = 0
    seen_qids: set[str] = set()
    frontier_supers: set[str] = set()
    lex_fh = (out_dir / "lexicon.jsonl").open("w", encoding="utf-8")
    edge_fh = (out_dir / "edges.jsonl").open("w", encoding="utf-8")

    def process_batch(batch: list[str], record_labels: bool) -> None:
        nonlocal edge_count
        entities = fetch_entities(batch, languages)
        for qid, ent in entities.items():
            seen_qids.add(qid)
            labels = ent.get("labels", {})
            aliases = ent.get("aliases", {})
            langs_to_record = languages if record_labels else ["en"]
            for lang in langs_to_record:
                surfaces = []
                if lang in labels:
                    surfaces.append(labels[lang]["value"])
                if record_labels:
                    surfaces.extend(a["value"] for a in aliases.get(lang, [])[:3])
                for surface in surfaces:
                    lex_fh.write(json.dumps({
                        "lang": lang, "surface": surface, "concept": f"C:{qid}",
                        "source": "wikidata", "source_id": qid,
                        "license": LICENSE, "retrieved_at": now,
                    }, ensure_ascii=False) + "\n")
                    lexicon_count[lang] += 1
            for claim in ent.get("claims", {}).get("P279", []):
                value = (claim.get("mainsnak", {}).get("datavalue") or {}).get("value") or {}
                super_qid = value.get("id")
                if super_qid:
                    edge_fh.write(json.dumps({
                        "subject": f"C:{qid}", "predicate": "P279", "object": f"C:{super_qid}",
                        "source": "wikidata", "license": LICENSE, "retrieved_at": now,
                    }, ensure_ascii=False) + "\n")
                    edge_count += 1
                    if super_qid not in seen_qids:
                        frontier_supers.add(super_qid)

    try:
        for i in range(0, len(qids), BATCH):
            process_batch(qids[i : i + BATCH], record_labels=True)
            done = min(i + BATCH, len(qids))
            if done % 500 == 0 or done == len(qids):
                print(f"  {done}/{len(qids)} entities — lexicon {sum(lexicon_count.values())}, edges {edge_count}")
            time.sleep(0.15)  # politeness

        # Upward P279 crawl: subclass chains (dog→canine→mammal→animal) mostly
        # run through concepts too abstract to rank high on page views. Without
        # them the graph is a shallow forest and multi-hop inference has nothing
        # to traverse. Crawled nodes get en labels only (they serve the graph,
        # not the lexicon).
        for depth in range(1, args.crawl_depth + 1):
            batch_qids = sorted(frontier_supers - seen_qids)
            frontier_supers = set()
            if not batch_qids:
                break
            print(f"crawl depth {depth}: {len(batch_qids)} new superclass nodes")
            for i in range(0, len(batch_qids), BATCH):
                process_batch(batch_qids[i : i + BATCH], record_labels=False)
                time.sleep(0.15)
            print(f"  edges now {edge_count}")
    finally:
        lex_fh.close()
        edge_fh.close()

    manifest = {
        "retrieved_at": now, "license": LICENSE,
        "rank_source": QRANK_URL, "label_source": WD_API,
        "top": args.top, "languages": lexicon_count, "edges": edge_count,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nlexicon entries per language: {lexicon_count}")
    print(f"P279 edges: {edge_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
