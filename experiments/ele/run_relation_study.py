"""Phase 12 — one command regenerates the whole relation-extraction study (no LLM).

Runs the entire pipeline on a chosen corpus with NO manual steps: validation
(CV + baselines + ablation), the adaptive lexicon (recall@k + synonym clusters),
open-discovery clustering metrics, and the error taxonomy. Each stage writes its
table to stdout and its machine-readable result to results/.

  .venv/Scripts/python.exe experiments/ele/run_relation_study.py            # intro corpus
  .venv/Scripts/python.exe experiments/ele/run_relation_study.py --full     # larger corpus
  .venv/Scripts/python.exe experiments/ele/run_relation_study.py --fetch    # (re)fetch first

Data provenance is Wikidata (facts) + Wikipedia (text); see fetch_*.py.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
PY = sys.executable


def run(script: str, *args: str) -> None:
    print("\n" + "#" * 90)
    print(f"# {script} {' '.join(args)}")
    print("#" * 90)
    subprocess.run([PY, "-u", str(HERE / script), *args], check=False)


def main() -> int:
    full = "--full" in sys.argv
    corpus = "multi_relation_full.json" if full else "multi_relation.json"

    if "--fetch" in sys.argv:
        run("fetch_relation_facts.py")
        if full:
            run("fetch_corpus_full.py")

    if not (HERE / "data" / corpus).exists():
        print(f"missing data/{corpus} — run with --fetch (and --full for the larger corpus)")
        return 1

    run("validate_relations.py", corpus)      # Phase 1 (CV) + 2 (baselines) + 6 (ablation)
    run("adaptive_lexicon.py", corpus)         # Phase 7 (recall@k + lexicon + synonymy)
    run("open_discovery_eval.py", corpus)      # Phase 5 (Purity / NMI / ARI)
    run("error_analysis.py", corpus)           # Phase 11 (recall attribution)
    print("\nAll stages complete. Machine-readable results in experiments/ele/results/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
