from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional local convenience
    load_dotenv = None  # type: ignore[assignment]

from prototype.jimsai.models import Modality, PipelineRequest, TrainingIngestRequest
from prototype.jimsai.pipeline import JimsAIPipeline
from prototype.jimsai.semantic_compiler import SemanticCompilerRuntime


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRAINING_DATA = ROOT / "datasets" / "frontier_training_seed.jsonl"
DEFAULT_PUBLIC_TRAINING_DATA = ROOT / "datasets" / "public_domain_training_seed.jsonl"
DEFAULT_EVAL_DATA = ROOT / "datasets" / "iterative_eval_prompts.jsonl"
DEFAULT_REPORT_DIR = ROOT / ".logs" / "iterative_training"


@dataclass(frozen=True)
class TrainingRecord:
    content: str
    domain_hint: str = "iterative_training"
    source_trust: float = 0.9
    modality: str = "text"
    expected_focus: list[str] = field(default_factory=list)
    source_url: str = ""
    license: str = ""

    def payload_content(self) -> str:
        provenance_parts: list[str] = []
        if self.source_url:
            provenance_parts.append(f"Source URL: {self.source_url}.")
        if self.license:
            provenance_parts.append(f"Source license: {self.license}.")
        if not provenance_parts:
            return self.content
        return f"{' '.join(provenance_parts)} {self.content}"


@dataclass(frozen=True)
class EvalPrompt:
    id: str
    prompt: str
    expected_capability: str | None = None
    expected_target_ir: str | None = None
    min_confidence: float = 0.0
    must_include: list[str] = field(default_factory=list)
    source_required: bool = False
    max_gaps: int | None = None


@dataclass(frozen=True)
class EvalOutcome:
    id: str
    passed: bool
    failures: list[str]
    prompt: str
    response: str
    confidence: float
    sources: int
    gaps: int
    target_ir: str
    capability: str | None
    used_groq: bool


@dataclass(frozen=True)
class LanguageVariant:
    kind: str
    text: str
    source: str = "deterministic"


LANGUAGE_VARIANT_KINDS = (
    "formal_english",
    "casual_english",
    "slang",
    "misspelled",
    "ocr_corrupted",
    "shortened_form",
    "voice_transcription_error",
    "mixed_language",
    "pidgin",
    "regional_dialect",
)

DETERMINISTIC_VARIANT_KINDS = {
    "formal_english",
    "casual_english",
    "slang",
    "misspelled",
    "ocr_corrupted",
    "shortened_form",
}


def language_variants(text: str, corpus_variants: dict[str, list[str]] | None = None) -> list[LanguageVariant]:
    normalized = recompact(text)
    corpus_variants = corpus_variants or {}
    variants = [
        LanguageVariant("formal_english", normalized),
        LanguageVariant("casual_english", casual_variant(normalized)),
        LanguageVariant("slang", abbreviation_variant(normalized)),
        LanguageVariant("misspelled", typo_variant(normalized)),
        LanguageVariant("ocr_corrupted", ocr_variant(normalized)),
        LanguageVariant("shortened_form", shortened_variant(normalized)),
    ]
    for kind in sorted(set(LANGUAGE_VARIANT_KINDS) - DETERMINISTIC_VARIANT_KINDS):
        for variant in corpus_variants.get(kind, []):
            cleaned = recompact(variant)
            if cleaned:
                variants.append(LanguageVariant(kind, cleaned, source="corpus"))
    return variants


def recompact(text: str) -> str:
    return " ".join(str(text or "").strip().split())


def casual_variant(text: str) -> str:
    return recompact(re.sub(r"[?!]+$", "", text.lower()))


def abbreviation_variant(text: str) -> str:
    words = text.split()
    output: list[str] = []
    abbreviated = 0
    for word in words:
        bare = word.strip(".,?!;:")
        if abbreviated < 3 and len(bare) >= 5 and bare.isalpha():
            output.append(re.sub(r"(?i)[aeiou]", "", bare) or bare)
            abbreviated += 1
        else:
            output.append(word)
    return recompact(" ".join(output))


def typo_variant(text: str) -> str:
    words = text.split()
    output: list[str] = []
    changed = 0
    for word in words:
        bare = word.strip(".,?!;:")
        if changed < 2 and len(bare) >= 6 and bare.isalpha():
            middle = len(bare) // 2
            output.append(bare[:middle] + bare[middle + 1 :])
            changed += 1
        else:
            output.append(word)
    return recompact(" ".join(output))


def ocr_variant(text: str) -> str:
    table = str.maketrans({"o": "0", "O": "0", "l": "1", "I": "1", "i": "1"})
    words = text.split()
    output: list[str] = []
    changed = 0
    for word in words:
        if changed < 2 and any(char in word for char in "oOlIiI"):
            output.append(word.translate(table))
            changed += 1
        else:
            output.append(word)
    return recompact(" ".join(output))


def shortened_variant(text: str) -> str:
    drop = {"a", "an", "the", "do", "does", "should", "can", "please"}
    words = [word for word in text.split() if word.strip(".,?!").lower() not in drop]
    return recompact(" ".join(words)) or text


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number} is not valid JSONL") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{line_number} must contain a JSON object")
            records.append(payload)
    return records


def training_records(paths: Iterable[Path]) -> list[TrainingRecord]:
    records: list[TrainingRecord] = []
    for path in paths:
        for payload in load_jsonl(path):
            content = str(payload.get("content") or "").strip()
            if not content:
                continue
            records.append(
                TrainingRecord(
                    content=content,
                    domain_hint=str(payload.get("domain_hint") or "iterative_training"),
                    source_trust=float(payload.get("source_trust", 0.9)),
                    modality=str(payload.get("modality") or "text"),
                    expected_focus=[str(item) for item in payload.get("expected_focus", []) if str(item).strip()]
                    if isinstance(payload.get("expected_focus", []), list)
                    else [],
                    source_url=str(payload.get("source_url") or ""),
                    license=str(payload.get("license") or ""),
                )
            )
    return records


def eval_prompts(path: Path) -> list[EvalPrompt]:
    prompts: list[EvalPrompt] = []
    for payload in load_jsonl(path):
        prompt_id = str(payload.get("id") or "").strip()
        prompt = str(payload.get("prompt") or "").strip()
        if not prompt_id or not prompt:
            continue
        prompts.append(
            EvalPrompt(
                id=prompt_id,
                prompt=prompt,
                expected_capability=str(payload["expected_capability"]) if payload.get("expected_capability") else None,
                expected_target_ir=str(payload["expected_target_ir"]) if payload.get("expected_target_ir") else None,
                min_confidence=float(payload.get("min_confidence", 0.0)),
                must_include=[str(item) for item in payload.get("must_include", []) if str(item).strip()]
                if isinstance(payload.get("must_include", []), list)
                else [],
                source_required=bool(payload.get("source_required", False)),
                max_gaps=int(payload["max_gaps"]) if payload.get("max_gaps") is not None else None,
            )
        )
    return prompts


def project_training_records(paths: Iterable[Path], source_trust: float = 0.92) -> list[TrainingRecord]:
    records: list[TrainingRecord] = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
        if not text:
            continue
        chunks = chunk_text(text)
        for index, chunk in enumerate(chunks, start=1):
            records.append(
                TrainingRecord(
                    content=f"Project source {path.name} chunk {index}: {chunk}",
                    domain_hint="live_project_documentation",
                    source_trust=source_trust,
                )
            )
    return records


def chunk_text(text: str, max_chars: int = 3000) -> list[str]:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = paragraph[:max_chars]
    if current:
        chunks.append(current)
    return chunks


async def ingest_records(
    pipeline: JimsAIPipeline,
    records: list[TrainingRecord],
    user_id: str,
    workspace_id: str | None,
) -> list[dict[str, Any]]:
    ingested: list[dict[str, Any]] = []
    for record in records:
        response = await pipeline.ingest_training(
            TrainingIngestRequest(
                user_id=user_id,
                workspace_id=workspace_id,
                content=record.payload_content(),
                source_trust=max(0.0, min(record.source_trust, 1.0)),
                domain_hint=record.domain_hint,
                modality=Modality(record.modality),
            )
        )
        ingested.append(
            {
                "signature_id": response.signature.id,
                "domain_hint": record.domain_hint,
                "confidence": response.signature.confidence.score,
                "sppe_accepted": response.sppe_training_pair.accepted,
                "world_model_candidates": len(response.world_model_candidates),
            }
        )
    return ingested


async def run_eval(
    pipeline: JimsAIPipeline,
    prompts: list[EvalPrompt],
    user_id: str,
    workspace_id: str | None,
) -> list[EvalOutcome]:
    outcomes: list[EvalOutcome] = []
    for prompt in prompts:
        result = await pipeline.run(
            PipelineRequest(
                user_id=user_id,
                workspace_id=workspace_id,
                query=prompt.prompt,
                return_trace=True,
            )
        )
        capability = result.capability_plan.kind.value if result.capability_plan else None
        failures: list[str] = []
        if prompt.expected_capability and capability != prompt.expected_capability:
            failures.append(f"capability expected {prompt.expected_capability}, got {capability}")
        if prompt.expected_target_ir and result.ir.target_ir != prompt.expected_target_ir:
            failures.append(f"target_ir expected {prompt.expected_target_ir}, got {result.ir.target_ir}")
        if result.confidence < prompt.min_confidence:
            failures.append(f"confidence {result.confidence:.2f} below {prompt.min_confidence:.2f}")
        if prompt.source_required and not result.sources:
            failures.append("expected at least one source signature")
        if prompt.max_gaps is not None and len(result.gaps) > prompt.max_gaps:
            failures.append(f"gap count {len(result.gaps)} above {prompt.max_gaps}")
        response_lower = result.response.lower()
        for phrase in prompt.must_include:
            if phrase.lower() not in response_lower:
                failures.append(f"missing phrase: {phrase}")
        outcomes.append(
            EvalOutcome(
                id=prompt.id,
                passed=not failures,
                failures=failures,
                prompt=prompt.prompt,
                response=result.response,
                confidence=result.confidence,
                sources=len(result.sources),
                gaps=len(result.gaps),
                target_ir=result.ir.target_ir,
                capability=capability,
                used_groq=result.used_groq,
            )
        )
    return outcomes


def correction_candidates(outcomes: list[EvalOutcome]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for outcome in outcomes:
        if outcome.passed:
            continue
        candidates.append(
            {
                "domain_hint": "iterative_failure_correction",
                "source_trust": 0.72,
                "content": (
                    f"Evaluation case {outcome.id} failed for prompt: {outcome.prompt}. "
                    f"Observed capability {outcome.capability}; target IR {outcome.target_ir}; "
                    f"confidence {outcome.confidence:.2f}; sources {outcome.sources}; gaps {outcome.gaps}. "
                    f"Failures: {'; '.join(outcome.failures)}. "
                    "This record is a correction candidate and requires human review before promotion."
                ),
                "expected_focus": ["evaluation_failure", "human_review_required"],
            }
        )
    return candidates


def provider_usage_analysis(outcomes: list[EvalOutcome]) -> dict[str, Any]:
    total = len(outcomes)
    provider_model_calls = sum(1 for outcome in outcomes if outcome.used_groq)
    by_capability: dict[str, dict[str, int]] = {}
    for outcome in outcomes:
        capability = outcome.capability or "unknown"
        row = by_capability.setdefault(capability, {"total": 0, "provider_model_calls": 0, "provider_model_bypassed": 0})
        row["total"] += 1
        if outcome.used_groq:
            row["provider_model_calls"] += 1
        else:
            row["provider_model_bypassed"] += 1
    return {
        "eval_total": total,
        "provider_model_calls": provider_model_calls,
        "provider_model_bypassed": total - provider_model_calls,
        "provider_model_call_rate": round(provider_model_calls / total, 4) if total else 0.0,
        "by_capability": by_capability,
    }


def intent_signature(compiler: SemanticCompilerRuntime, prompt: str) -> dict[str, Any]:
    ir = compiler.compile(prompt)
    question_intent = ir.scope_constraints.get("question_intent", {})
    relation = question_intent.get("relation") if isinstance(question_intent, dict) else None
    direction = question_intent.get("direction") if isinstance(question_intent, dict) else None
    return {
        "target_ir": ir.target_ir,
        "capability_hint": ir.scope_constraints.get("v9_capability_hint"),
        "relation": relation,
        "direction": direction,
        "profile_query": bool(ir.scope_constraints.get("profile_query")),
    }


def intent_stability_analysis(compiler: SemanticCompilerRuntime, prompts: list[EvalPrompt]) -> dict[str, Any]:
    total = 0
    stable = 0
    by_kind = {kind: {"stable": 0, "total": 0} for kind in LANGUAGE_VARIANT_KINDS}
    failures: list[dict[str, Any]] = []
    for prompt in prompts:
        baseline = intent_signature(compiler, prompt.prompt)
        for variant in language_variants(prompt.prompt):
            observed = intent_signature(compiler, variant.text)
            total += 1
            by_kind.setdefault(variant.kind, {"stable": 0, "total": 0})
            by_kind[variant.kind]["total"] += 1
            if observed == baseline:
                stable += 1
                by_kind[variant.kind]["stable"] += 1
                continue
            failures.append(
                {
                    "id": prompt.id,
                    "kind": variant.kind,
                    "prompt": variant.text,
                    "expected": baseline,
                    "observed": observed,
                }
            )
    available_kinds = {kind for kind, counts in by_kind.items() if counts["total"] > 0}
    missing_kinds = [kind for kind in LANGUAGE_VARIANT_KINDS if kind not in available_kinds]
    return {
        "target_score": 0.95,
        "intent_stability_score": round(stable / total, 4) if total else 0.0,
        "stable": stable,
        "total": total,
        "variant_kind_coverage": round(len(available_kinds) / len(LANGUAGE_VARIANT_KINDS), 4),
        "available_variant_kinds": sorted(available_kinds),
        "missing_variant_kinds": missing_kinds,
        "by_kind": {
            kind: {
                **counts,
                "score": round(counts["stable"] / counts["total"], 4) if counts["total"] else 0.0,
            }
            for kind, counts in by_kind.items()
        },
        "failures": failures[:50],
        "failure_count": len(failures),
    }


def training_variant_summary(records: list[TrainingRecord]) -> dict[str, Any]:
    by_kind = {kind: 0 for kind in LANGUAGE_VARIANT_KINDS}
    for record in records:
        for variant in language_variants(record.content):
            by_kind[variant.kind] = by_kind.get(variant.kind, 0) + 1
    return {
        "record_count": len(records),
        "variant_kinds": list(LANGUAGE_VARIANT_KINDS),
        "deterministic_variant_kinds": sorted(DETERMINISTIC_VARIANT_KINDS),
        "corpus_required_variant_kinds": sorted(set(LANGUAGE_VARIANT_KINDS) - DETERMINISTIC_VARIANT_KINDS),
        "generated_total": sum(by_kind.values()),
        "by_kind": by_kind,
        "ingested_as_training": False,
        "reason": "Deterministic variants cover language-agnostic perturbations; dialect and multilingual variants require corpus or provider-assisted generation before promotion.",
    }


def write_report(
    report_dir: Path,
    ingested: list[dict[str, Any]],
    outcomes: list[EvalOutcome],
    candidates: list[dict[str, Any]],
    language_analysis: dict[str, Any],
    training_variants: dict[str, Any],
    production_write: bool,
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report_path = report_dir / f"iteration_{stamp}.json"
    passed = sum(1 for outcome in outcomes if outcome.passed)
    report = {
        "created_at": stamp,
        "production_write": production_write,
        "ingested_count": len(ingested),
        "ingested": ingested,
        "eval_total": len(outcomes),
        "eval_passed": passed,
        "eval_failed": len(outcomes) - passed,
        "outcomes": [asdict(outcome) for outcome in outcomes],
        "correction_candidates": candidates,
        "provider_usage_analysis": provider_usage_analysis(outcomes),
        "language_variant_analysis": language_analysis,
        "training_variant_summary": training_variants,
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if candidates:
        candidate_path = report_dir / f"correction_candidates_{stamp}.jsonl"
        with candidate_path.open("w", encoding="utf-8") as handle:
            for candidate in candidates:
                handle.write(json.dumps(candidate, sort_keys=True) + "\n")
    return report_path


async def run_iteration(args: argparse.Namespace) -> int:
    if load_dotenv:
        load_dotenv(ROOT / ".env", override=True)

    if not args.allow_provider_models:
        for name in (
            "JIMS_ENABLE_GROQ_T1",
            "JIMS_ENABLE_GROQ_T2",
            "JIMS_ENABLE_GROQ_CANVAS",
            "JIMS_ENABLE_GROQ_INVENTION",
            "JIMS_ENABLE_GROQ_INGEST",
        ):
            os.environ[name] = "false"

    if args.write_production:
        os.environ["JIMS_STORAGE_BACKEND"] = "production"
    elif not args.use_current_backend:
        os.environ["JIMS_STORAGE_BACKEND"] = "memory"

    pipeline = JimsAIPipeline()
    readiness = pipeline.production.readiness()
    production_write = args.write_production and any(
        bool(readiness.get(key))
        for key in (
            "r2_available",
            "supabase_postgres_available",
            "vectorize_available",
            "neo4j_aura_available",
        )
    )

    records = training_records([Path(path) for path in args.training_data])
    if args.include_project_docs:
        records.extend(
            project_training_records(
                [
                    ROOT / "README.md",
                    ROOT / "ROADMAP.md",
                    ROOT / "tracker.md",
                    ROOT / "docs" / "Jims_AI_v9.md",
                ]
            )
        )
    if args.limit_records is not None:
        records = records[: max(args.limit_records, 0)]

    ingested = await ingest_records(pipeline, records, args.user_id, args.workspace_id)
    prompts = eval_prompts(Path(args.eval_data))
    outcomes = await run_eval(pipeline, prompts, args.user_id, args.workspace_id)
    candidates = correction_candidates(outcomes)
    language_analysis = intent_stability_analysis(pipeline.compiler, prompts)
    training_variants = training_variant_summary(records)
    report_path = write_report(Path(args.report_dir), ingested, outcomes, candidates, language_analysis, training_variants, production_write)

    passed = sum(1 for outcome in outcomes if outcome.passed)
    print(f"ingested={len(ingested)} production_write={production_write}")
    print(f"eval_passed={passed}/{len(outcomes)}")
    print(f"correction_candidates={len(candidates)}")
    usage = provider_usage_analysis(outcomes)
    print(
        "provider_model_usage="
        f"{usage['provider_model_calls']}/{usage['eval_total']} "
        f"rate={usage['provider_model_call_rate']}"
    )
    print(
        "intent_stability_score="
        f"{language_analysis['intent_stability_score']} "
        f"stable={language_analysis['stable']}/{language_analysis['total']} "
        f"coverage={language_analysis['variant_kind_coverage']}"
    )
    print(f"training_variants_generated={training_variants['generated_total']}")
    print(f"report={report_path}")
    if candidates:
        print("failed_cases=" + ",".join(outcome.id for outcome in outcomes if not outcome.passed))
    return 0 if passed == len(outcomes) else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one JIMS-AI iterative training/evaluation cycle.")
    parser.add_argument("--training-data", action="append", default=[str(DEFAULT_TRAINING_DATA), str(DEFAULT_PUBLIC_TRAINING_DATA)])
    parser.add_argument("--eval-data", default=str(DEFAULT_EVAL_DATA))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--user-id", default="iterative-trainer")
    parser.add_argument("--workspace-id", default="workspace:iterative-training")
    parser.add_argument("--limit-records", type=int)
    parser.add_argument("--include-project-docs", action="store_true")
    parser.add_argument("--write-production", action="store_true")
    parser.add_argument("--use-current-backend", action="store_true")
    parser.add_argument("--allow-provider-models", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(run_iteration(args))


if __name__ == "__main__":
    raise SystemExit(main())
