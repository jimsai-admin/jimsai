from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any

from prototype.jimsai.errors import CriticalServiceUnavailable
from prototype.jimsai.models import PipelineRequest, TrainingIngestRequest
from prototype.jimsai.pipeline import JimsAIPipeline


ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path) -> int:
    if not path.exists():
        return 0
    loaded = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            loaded += 1
    return loaded


def _service_snapshot() -> dict[str, bool]:
    required = [
        "JIMS_MODAL_API_KEY",
        "JIMS_EMBEDDING_SERVICE_URL",
        "JIMS_CLASSIFICATION_SERVICE_URL",
        "JIMS_INTENT_SERVICE_URL",
        "JIMS_RENDERER_SERVICE_URL",
    ]
    return {key: bool(os.getenv(key)) for key in required}


async def _timed(label: str, coro):
    start = time.perf_counter()
    try:
        timeout = float(os.getenv("JIMS_PROBE_STAGE_TIMEOUT", "45") or "45")
        value = await asyncio.wait_for(coro, timeout=timeout)
        return value, (time.perf_counter() - start) * 1000.0, None
    except Exception as exc:  # surfaced in result table, not swallowed
        return None, (time.perf_counter() - start) * 1000.0, exc


async def _run_case(pipeline: JimsAIPipeline, case: dict[str, Any]) -> dict[str, Any]:
    ingest_request = TrainingIngestRequest(
        user_id=case["user_id"],
        workspace_id=case["workspace_id"],
        content=case["content"],
        source_trust=case["source_trust"],
        domain_hint=case["domain_hint"],
    )
    ingest, ingest_ms, ingest_error = await _timed("ingest", pipeline.ingest_training(ingest_request))
    if ingest_error:
        return {
            "name": case["name"],
            "stage": "ingest",
            "ingest_ms": round(ingest_ms, 2),
            "error_type": type(ingest_error).__name__,
            "error": str(ingest_error),
        }

    query_request = PipelineRequest(
        user_id=case["user_id"],
        workspace_id=case["workspace_id"],
        query=case["query"],
        return_trace=True,
    )
    response, query_ms, query_error = await _timed("query", pipeline.run(query_request))
    if query_error:
        return {
            "name": case["name"],
            "stage": "query",
            "ingest_ms": round(ingest_ms, 2),
            "query_ms": round(query_ms, 2),
            "signature_id": ingest.signature.id if ingest else "",
            "world_model_candidates": len(ingest.world_model_candidates) if ingest else 0,
            "error_type": type(query_error).__name__,
            "error": str(query_error),
        }

    expected_terms = [term.lower() for term in case.get("expected_terms", [])]
    answer_text = response.response or ""
    answer_lower = answer_text.lower()
    missing_terms = [term for term in expected_terms if term not in answer_lower]
    return {
        "name": case["name"],
        "stage": "complete",
        "ingest_ms": round(ingest_ms, 2),
        "query_ms": round(query_ms, 2),
        "signature_id": ingest.signature.id,
        "world_model_candidates": len(ingest.world_model_candidates),
        "ir": response.ir.target_ir,
        "confidence": response.confidence,
        "sources": response.sources,
        "gaps": response.gaps,
        "missing_expected_terms": missing_terms,
        "answer_preview": answer_text[:500].replace("\n", " "),
    }


async def main() -> int:
    loaded = _load_dotenv(ROOT / ".env")
    os.environ["JIMS_INTERACTIVE_SERVICE_TIMEOUT_CAP"] = os.getenv("JIMS_PROBE_TIMEOUT_CAP", "12")
    os.environ["JIMS_T1_PROVIDER"] = os.getenv("JIMS_PROBE_T1_PROVIDER", "modal")
    os.environ["JIMS_T2_PROVIDER"] = os.getenv("JIMS_PROBE_T2_PROVIDER", "modal")
    os.environ["JIMS_T1_TIMEOUT"] = os.getenv("JIMS_PROBE_T1_TIMEOUT", "12")
    os.environ["JIMS_T2_TIMEOUT"] = os.getenv("JIMS_PROBE_T2_TIMEOUT", "12")
    os.environ["JIMS_INGESTION_OVERLAY_TIMEOUT"] = os.getenv("JIMS_PROBE_INGESTION_OVERLAY_TIMEOUT", "8")
    os.environ["JIMS_L1_EMBEDDING_TIMEOUT"] = os.getenv("JIMS_PROBE_EMBEDDING_TIMEOUT", "5")
    os.environ["JIMS_EMBEDDING_MAX_ATTEMPTS"] = os.getenv("JIMS_PROBE_EMBEDDING_ATTEMPTS", "2")
    os.environ["JIMS_CAPABILITY_CLASSIFIER_TIMEOUT"] = os.getenv("JIMS_PROBE_CLASSIFIER_TIMEOUT", "6")
    os.environ["JIMS_CAPABILITY_EMBEDDING_TIMEOUT"] = os.getenv("JIMS_PROBE_CAPABILITY_EMBEDDING_TIMEOUT", "4")
    os.environ["JIMS_CAPABILITY_CLASSIFIER_MODE"] = os.getenv("JIMS_PROBE_CLASSIFIER_MODE", "off")
    os.environ["JIMS_INLINE_INGESTION_OVERLAY"] = os.getenv("JIMS_PROBE_INLINE_INGESTION_OVERLAY", "false")
    os.environ["JIMS_SYNC_CLOUD_WRITES"] = os.getenv("JIMS_PROBE_SYNC_CLOUD_WRITES", "false")
    os.environ["JIMS_ENABLE_QUERY_CLOUD_HYDRATION"] = os.getenv("JIMS_PROBE_QUERY_CLOUD_HYDRATION", "false")
    print(f"loaded_env_keys={loaded}", flush=True)
    print(f"service_snapshot={_service_snapshot()}", flush=True)

    cases = [
        {
            "name": "01_simple_profile_memory",
            "user_id": "probe-user",
            "workspace_id": "probe-workspace",
            "content": "User profile: My name is Ajibew Irekanmi. I am building JimsAI as a memory-centric AI system.",
            "query": "What is my name?",
            "source_trust": 0.98,
            "domain_hint": "user_profile_training",
            "expected_terms": ["ajibew", "irekanmi"],
        },
        {
            "name": "02_simple_causal_recall",
            "user_id": "probe-user",
            "workspace_id": "probe-workspace",
            "content": "DoorSensor.failure causes AlarmService.alert. AlarmService.alert causes SecurityDashboard.incident_card.",
            "query": "What does DoorSensor.failure cause?",
            "source_trust": 0.94,
            "domain_hint": "systems_causal_training",
            "expected_terms": ["alarmservice.alert"],
        },
        {
            "name": "03_multihop_dependency_trace",
            "user_id": "probe-user",
            "workspace_id": "probe-workspace",
            "content": "OrderWrite.failure causes PaymentCapture.retry. PaymentCapture.retry causes LedgerQueue.backlog. LedgerQueue.backlog causes FinanceDashboard.delay.",
            "query": "Trace the downstream effects of OrderWrite.failure all the way to the dashboard.",
            "source_trust": 0.94,
            "domain_hint": "systems_causal_training",
            "expected_terms": ["paymentcapture.retry", "ledgerqueue.backlog", "financedashboard.delay"],
        },
        {
            "name": "04_chaotic_multi_intent_workspace_query",
            "user_id": "probe-user",
            "workspace_id": "probe-workspace",
            "content": (
                "IncidentPlaybook depends_on AlertRouter. AlertRouter.misroute causes OnCallDelay. "
                "OnCallDelay causes SLAReview. The recovery note is: verify routing rules before changing escalation policy."
            ),
            "query": "ok messy ask: if AlertRouter.misroute happens, what breaks, what should I check, and keep it short",
            "source_trust": 0.92,
            "domain_hint": "incident_ops_training",
            "expected_terms": ["oncalldelay", "slareview", "routing"],
        },
    ]

    pipeline = JimsAIPipeline()
    failures = 0
    for case in cases:
        print(f"\nSTART {case['name']}", flush=True)
        result = await _run_case(pipeline, case)
        print(f"CASE {result['name']}", flush=True)
        for key, value in result.items():
            if key != "name":
                print(f"{key}={value}", flush=True)
        if result.get("stage") != "complete" or result.get("missing_expected_terms"):
            failures += 1
            if result.get("error_type") == CriticalServiceUnavailable.__name__:
                break
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
