"""seed_lexicon.py — publish the concept-model artifacts to R2.

The lexicon, learned common words, and concept-graph edges are the single source of
truth in R2 for BOTH local development and the deployed Lambda — nothing is baked
into the deployment package (Lambda's filesystem is read-only and a bundled copy
drifts from local). Run this once to seed, and again after `enrich_lexicon.py` /
`fetch_common_words.py` to publish a new snapshot — the running services pick it up
on their next cold start (ETag revalidation), no redeploy required.

    python experiments/concept_model/seed_lexicon.py            # seed all present
    python experiments/concept_model/seed_lexicon.py lexicon.jsonl   # just one

Credentials come from .env (CF_ACCOUNT_ID / CF_R2_ACCESS_KEY / CF_R2_SECRET_KEY /
CF_R2_BUCKET), the same variables the deploy script already forwards to Lambda.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(__file__).resolve().parent / "data"
ARTIFACTS = ["lexicon.jsonl", "common_words.jsonl", "edges.jsonl"]


def _load_dotenv() -> None:
    """Populate os.environ from the repo .env (KEY=VALUE), without adding a
    dependency — matches the deploy script's own parser."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if key and key not in os.environ:
            os.environ[key] = val


def publish_artifacts(names: list[str]) -> int:
    """Best-effort publish of the named data/ artifacts to R2, for the enrichment
    writers to call right after they grow the lexicon locally — so a training run
    updates the single source of truth and the deployed service picks it up on its
    next cold start (no redeploy). Never raises: training must not fail because R2
    is briefly unavailable, and the local write remains re-seedable."""
    try:
        _load_dotenv()
        if str(ROOT / "prototype") not in sys.path:
            sys.path.insert(0, str(ROOT / "prototype"))
        from jimsai.cloud_artifact import upload_artifact

        prefix = os.getenv("JIMS_LEXICON_R2_PREFIX", "concept-model")
        ok = 0
        for name in names:
            local = DATA / name
            if local.exists() and upload_artifact(f"{prefix}/{name}", local):
                print(f"  [r2] published {name} -> {prefix}/{name}")
                ok += 1
        if not ok:
            print("  [r2] publish skipped (R2 unavailable) — run seed_lexicon.py later")
        return ok
    except Exception as e:  # never break a training run on a publish hiccup
        print(f"  [r2] publish skipped: {e}")
        return 0


def main(argv: list[str]) -> int:
    _load_dotenv()
    sys.path.insert(0, str(ROOT / "prototype"))
    from jimsai.cloud_artifact import r2_available, upload_artifact  # noqa: E402

    if not r2_available():
        print(
            "R2 is not reachable — check CF_ACCOUNT_ID / CF_R2_ACCESS_KEY / "
            "CF_R2_SECRET_KEY / CF_R2_BUCKET in .env.",
            file=sys.stderr,
        )
        return 2

    prefix = os.getenv("JIMS_LEXICON_R2_PREFIX", "concept-model")
    wanted = argv or ARTIFACTS
    ok = 0
    for name in wanted:
        local = DATA / name
        if not local.exists():
            print(f"  skip {name}: not found at {local}")
            continue
        mb = local.stat().st_size / 1_048_576
        if upload_artifact(f"{prefix}/{name}", local):
            print(f"  [ok]   {name} -> r2://{os.getenv('CF_R2_BUCKET')}/{prefix}/{name} ({mb:.1f} MB)")
            ok += 1
        else:
            print(f"  [fail] {name}: upload failed")
    print(f"Seeded {ok} artifact(s) to R2 under '{prefix}/'.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
