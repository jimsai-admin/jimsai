"""Ingest COMMON WORDS per language, FROM SOURCE — the messy-input fix.

The CLL lexicon is noun-only (QRank), so common verbs/adverbs/function words
("going", "where", "based", "actually") are out-of-vocabulary and get mistaken
for NAMES when reading real lowercase prose (grounding-review §0b). The remedy
is not a hardcoded stop-list and not English suffix rules — it is broader
VOCABULARY COVERAGE: give the lexicon the common words of each language so
"OOV ⇒ probably a name" becomes reliable (a nonce stays OOV; a common word does
not).

Source: hermitdave/FrequencyWords (CC-BY-SA-4.0), OpenSubtitles-derived
frequency lists for 100+ languages INCLUDING low-resource ones — the same
"from source, provenance-stamped" discipline as broaden_lexicon.py. We take the
top-N most frequent tokens per language: those ARE the common vocabulary. Output
is a set of (lang, surface) rows the shadow loads as "known, not a name."

Usage:
  python fetch_common_words.py --top 5000 --langs en,fr,yo,sw,zh
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/{code}/{code}_{sz}.txt"
LICENSE = "CC-BY-SA-4.0 (hermitdave/FrequencyWords, OpenSubtitles)"
# Corpus code differs from our lang tag for some languages (e.g. zh → zh_cn).
_CODE = {"zh": "zh_cn"}
# Keep alphabetic tokens (any script); drop pure numbers/punctuation rows.
_WORD = re.compile(r"^[^\W\d_][\w'\-]*$", re.UNICODE)


def fetch_lang(lang: str, top: int) -> list[str]:
    code = _CODE.get(lang, lang)
    resp = None
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        for sz in ("50k", "full"):          # low-resource langs often lack the 50k slice
            r = client.get(BASE.format(code=code, sz=sz))
            if r.status_code == 200:
                resp = r
                break
        if resp is None:
            print(f"  {lang}: not in corpus (no external frequency list exists) — "
                  f"low-resource, must be LEARNED from the user's own text")
            return []
    words: list[str] = []
    for line in resp.text.splitlines():
        parts = line.split()
        if not parts:
            continue
        w = parts[0].strip()
        if _WORD.match(w):
            words.append(w.lower())
        if len(words) >= top:
            break
    return words


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=5000)
    ap.add_argument("--langs", default="en,fr,yo,sw,zh")
    args = ap.parse_args()
    data = Path(__file__).parent / "data"
    data.mkdir(exist_ok=True)
    out_path = data / "common_words.jsonl"
    now = datetime.now(timezone.utc).isoformat()

    total = 0
    with out_path.open("w", encoding="utf-8") as out:
        for lang in [l.strip() for l in args.langs.split(",") if l.strip()]:
            words = fetch_lang(lang, args.top)
            for w in words:
                out.write(json.dumps({
                    "lang": lang, "surface": w, "kind": "common",
                    "source": "hermitdave/FrequencyWords", "license": LICENSE,
                    "retrieved_at": now,
                }, ensure_ascii=False) + "\n")
            total += len(words)
            print(f"  {lang}: {len(words)} common words")

    manifest = data / "manifest.json"
    m = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
    m.setdefault("common_words", []).append(
        {"retrieved_at": now, "top": args.top, "langs": args.langs, "total": total})
    manifest.write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {total} common-word rows -> {out_path}")
    # Publish the grown artifact to R2 (single source of truth for local + deploy).
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from seed_lexicon import publish_artifacts

        publish_artifacts(["common_words.jsonl"])
    except Exception as e:
        print(f"note: R2 publish skipped ({e})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
