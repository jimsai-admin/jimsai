#!/usr/bin/env python3
"""
CI validation: fail if any non-archived source file contains HF Space references.

Usage: python scripts/check_no_hf_space_refs.py
Exit 0 = clean, Exit 1 = violations found.

Requirements: 1.1, Property 1 (No HF Space References)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Patterns that must not appear in active source files after the migration
BANNED_PATTERNS = [
    "jimstechai-jimsai-embedding-service.hf.space",
    ".hf.space",
    "JIMS_LOCAL_INFERENCE_URL",
    "JIMS_QWEN_SERVICE_URL",
    "JIMS_CAPABILITY_CLASSIFIER_URL",
    "JIMS_RENDER_AGENT_TOKEN",
    "HF_SPACE_REPO_ID",
    "_wake_hf_space",
]

# Directory names to skip entirely
EXCLUDE_DIRS = frozenset([
    ".git", "node_modules", "__pycache__", ".kiro", "_archived",
    ".kaggle_runs", ".cache", ".lambda-build", ".venv", "venv",
    "dist", "build",
])

# Specific filenames to skip (historical docs, this script, spec files, live secrets)
EXCLUDE_FILES = frozenset([
    "DEPLOYMENT_GUIDE.md",
    "hf_space_audit.md",
    "check_no_hf_space_refs.py",
    "requirements.md",
    "design.md",
    "The_Prediction_Trap_Paper.md",
    # test_hf_render.py is a legacy diagnostic script kept for reference
    "test_hf_render.py",
    # The live .env is gitignored and excluded from CI scan (contains real secrets)
    ".env",
])

ALLOWED_EXTENSIONS = frozenset([
    ".py", ".ts", ".js", ".tsx", ".jsx",
    ".json", ".yaml", ".yml", ".toml",
    ".env", ".example",
])


def should_scan(path: Path) -> bool:
    if path.name in EXCLUDE_FILES:
        return False
    # Skip if any path component is an excluded directory
    if any(part in EXCLUDE_DIRS for part in path.parts):
        return False
    return path.suffix in ALLOWED_EXTENSIONS or path.name.startswith(".env")


def main() -> int:
    violations: list[str] = []

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if not should_scan(path):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pattern in BANNED_PATTERNS:
            if pattern in content:
                rel = path.relative_to(ROOT)
                violations.append(f"  {rel}: contains banned pattern '{pattern}'")

    if violations:
        print(f"FAIL — {len(violations)} HF Space reference violation(s) found:")
        for v in violations:
            print(v)
        return 1

    print("OK — no HF Space references found in active source files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
