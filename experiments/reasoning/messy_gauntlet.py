"""Messy-input gauntlet — recall + gap-honesty + scoping on REAL phrasing.

Reusable A/B harness for the case-independent-name fix. Same facts, phrased the
way people actually write (lowercase, filler, colloquial), plus a ghost-entity
gap check and a cross-workspace scoping check. Reports the real numbers so the
recall gain and the gap-honesty cost can be weighed honestly. Optional --lang
substitutes a low-resource (Nigerian-Pidgin-style) phrasing to test that the
fix — and its noise — behave the same without a per-language list.

Run (backend up): JIMS_EVAL_EMAIL=.. JIMS_EVAL_PASSWORD=.. \
  .venv/Scripts/python.exe experiments/reasoning/messy_gauntlet.py --label ON
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# (entity, value, messy-English fact, messy-English query, messy-Pidgin fact, messy-Pidgin query)
DATA = [
    ("Zorvenqia", "Trelvax",
     "so um zorvenqia, yeah she actually moved out to trelvax like a year ago",
     "where is zorvenqia living now again",
     "zorvenqia sef, na trelvax she comot go since last year",
     "abeg where zorvenqia dey stay now"),
    ("Kwendal", "PoziDB",
     "kwendal? oh we ended up going with pozidb for that one, works fine",
     "what db did we pick for kwendal",
     "for kwendal we just use pozidb, e dey work well",
     "wetin be the db wey we use for kwendal"),
    ("Muvrenko", "Bexil",
     "yeah muvrenko is basically the thing that took over from the old bexil stuff",
     "whats muvrenko replacing again",
     "muvrenko na the thing wey replace that old bexil own",
     "wetin muvrenko take over from"),
    ("Trplanar", "Okoye",
     "i think trplanar these days is run by okoye",
     "whos running trplanar these days",
     "trplanar these days na okoye dey run am",
     "who dey run trplanar now"),
    ("Vexomni", "forty",
     "vexomni had a decent quarter, up like forty percent or so",
     "how did vexomni do last quarter",
     "vexomni get better quarter, e go up like forty percent",
     "how vexomni take do last quarter"),
]

GHOST = ("where is Nemoxyzq based these days", "abeg where nemoxyzq dey these days")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="run")
    ap.add_argument("--lang", choices=["en", "pcm"], default="en")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    c = httpx.Client(timeout=90)
    tok = c.post(f"{base}/v1/auth/signin", json={
        "email": os.getenv("JIMS_EVAL_EMAIL", "Jimstechinnovations@gmail.com"),
        "password": os.getenv("JIMS_EVAL_PASSWORD", "")}).json().get("access_token")
    h = {"Authorization": f"Bearer {tok}"}
    fi, qi = (2, 3) if args.lang == "en" else (4, 5)
    ghost_q = GHOST[0 if args.lang == "en" else 1]

    def teach(ws, txt):
        c.post(f"{base}/v1/memory/insert", headers=h,
               json={"user_id": "p", "content": txt, "source_trust": 0.9, "workspace_id": ws})

    def ask(ws, q):
        return (c.post(f"{base}/v1/query", headers=h,
                json={"user_id": "p", "query": q, "workspace_id": ws}).json().get("response") or "").lower()

    recall = gap_ok = scope_ok = 0
    for row in DATA:
        ent, val = row[0], row[1]
        fact, query = row[fi], row[qi]
        wsA = f"a-{uuid.uuid4().hex[:5]}"
        wsB = f"b-{uuid.uuid4().hex[:5]}"
        teach(wsA, fact)
        recall += val.lower() in ask(wsA, query)
        gap_ok += val.lower() not in ask(wsA, ghost_q)      # ghost must not leak the value
        scope_ok += val.lower() not in ask(wsB, query)      # other workspace must not recall

    n = len(DATA)
    print(f"[{args.label} | lang={args.lang}] recall={recall}/{n}  "
          f"gap_honesty={gap_ok}/{n}  scoping={scope_ok}/{n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
