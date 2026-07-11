"""Phase 4 — LARGER corpus, SAME relations/algorithm (no LLM).

The validation showed recall is the bottleneck and CIs are wide because few entity
pairs co-occur in tiny article *intros*. This fetches much MORE text per entity
(full-article plaintext, capped) for the exact same entities/KBs, so more pairs
co-occur. Then `validate_relations.py multi_relation_full.json` re-runs the
IDENTICAL algorithm — only the corpus changes (the point of Phase 4).

Run: .venv/Scripts/python.exe experiments/ele/fetch_corpus_full.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_UA = {"User-Agent": "JimsAI-research/0.1 (jimstechinnovations@gmail.com) offline ELE experiment"}
_ACTION = "https://en.wikipedia.org/w/api.php"
# The extracts API returns the FULL article as plaintext only when NO length
# param is set (exchars/exsentences/exintro all CAP it to ~intro length — the
# bug that made two "larger" fetches no bigger than intros). We fetch full text
# then truncate in code to bound processing.
MAX_CHARS = 20000  # ~3000 words/article — genuinely ~10x the intro, corpus ~2-3M words


def fetch_full(client: httpx.Client, titles: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    titles = list(dict.fromkeys(titles))
    for n, title in enumerate(titles):
        params = {"action": "query", "prop": "extracts", "explaintext": 1,
                  "redirects": 1, "format": "json", "titles": title}
        for attempt in range(3):
            try:
                r = client.get(_ACTION, params=params, headers=_UA, timeout=45, follow_redirects=True)
                r.raise_for_status()
                for p in r.json().get("query", {}).get("pages", {}).values():
                    if p.get("title") and p.get("extract"):
                        out[p["title"]] = p["extract"][:MAX_CHARS]
                break
            except Exception:  # noqa: BLE001
                time.sleep(2 * (attempt + 1))
        if (n + 1) % 100 == 0:
            print(f"   … {n + 1}/{len(titles)} fetched")
        time.sleep(0.12)
    return out


def main() -> int:
    data_dir = Path(__file__).parent / "data"
    src = json.loads((data_dir / "multi_relation.json").read_text(encoding="utf-8"))
    relations = src["relations"]
    titles = sorted({e for rel in relations.values() for pair in rel["pairs"] for e in pair})
    print(f"entities: {len(titles)} — fetching full-article text (truncated to {MAX_CHARS} chars) …")
    with httpx.Client() as client:
        extracts = fetch_full(client, titles)
    cov = len(extracts) / len(titles) if titles else 0
    words = sum(len(v.split()) for v in extracts.values())
    print(f"got {len(extracts)}/{len(titles)} ({cov:.0%}), {words} words "
          f"(intro corpus was ~247k)")
    out = {"relations": relations, "extracts": extracts,
           "_provenance": {**src.get("_provenance", {}), "corpus": f"full article, truncated to {MAX_CHARS} chars"}}
    (data_dir / "multi_relation_full.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved → data/multi_relation_full.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
