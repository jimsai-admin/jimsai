from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv

from prototype.jimsai.kaggle_orchestrator import KaggleGPUOrchestrator
from prototype.jimsai.provider_adapters import ProductionRuntime


def sanitize(value: object) -> str:
    text = str(value or "")
    text = re.sub(r"(rediss?://[^:/\s]+:)[^@\s]+(@)", r"\1<redacted>\2", text)
    text = re.sub(r"(Bearer\s+)[A-Za-z0-9._\-]+", r"\1<redacted>", text, flags=re.I)
    text = re.sub(r"(apikey[=:\s]+)[A-Za-z0-9._\-]+", r"\1<redacted>", text, flags=re.I)
    text = re.sub(
        r"([A-Za-z0-9_-]{20,})",
        lambda match: match.group(1)
        if match.group(1).startswith(("JIMS_", "CF_", "NEO4J_", "SUPABASE_", "KAGGLE_", "REDIS_", "VAST_"))
        else "<redacted-id>",
        text,
    )
    return text[:320]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env", override=True)
    os.environ["JIMS_STRICT_PROVIDER_STARTUP"] = "false"

    print("JIMS-AI provider diagnostics (redacted)")
    print(f"storage_backend={os.getenv('JIMS_STORAGE_BACKEND', '<unset>')}")
    runtime = ProductionRuntime()
    failed = 0
    for name, status in runtime.statuses.items():
        if status.configured and not status.available:
            failed += 1
        print(
            f"{name}: configured={status.configured} available={status.available} "
            f"detail={sanitize(status.detail)}"
        )

    orchestrator = KaggleGPUOrchestrator()
    kagglehub_installed = orchestrator._kagglehub_available()
    dataset_owner = bool(os.getenv("KAGGLE_DATASET_OWNER", "").strip() or os.getenv("KAGGLE_USERNAME", "").strip())
    print(
        "kaggle_orchestrator: "
        f"configured={orchestrator.configured} kagglehub_installed={kagglehub_installed} "
        f"dataset_owner_configured={dataset_owner}"
    )
    if os.getenv("KAGGLE_API_TOKEN", "").strip() and not kagglehub_installed:
        failed += 1
        print("kagglehub=missing package")
    if os.getenv("KAGGLE_API_TOKEN", "").strip() and not orchestrator.configured:
        failed += 1
        print("kaggle_credentials=KAGGLE_API_TOKEN is present, but KAGGLE_DATASET_OWNER or kagglehub is missing")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
