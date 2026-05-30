# JIMS-AI Work Tracker

Last updated: 2026-05-29

## Completed In This Pass

- Compared `JimsAI Complete Specification v9.pdf` with `docs/Jims_AI_v9.md`.
- Added the missing v9 scale and architecture decisions to `docs/Jims_AI_v9.md`:
  result caching for math/code execution, Event Sourcing/CQRS, materialized views, Saga orchestration, MCTS,
  Z3/SAT/SMT verification, self-consistency voting, and synthetic bootstrap for active learning.
- Added UI rules to keep the interface useful instead of crowded:
  collapsed traces by default, evidence summary first, and real actions only.
- Added a backend System Health Score to the pipeline monitor.
- Added a compact System Health block in the training pipeline panel.
- Simplified the chat insight rail:
  confidence/sources/gaps/capability are visible first, deep layer/simulation traces are optional, and the
  old loose feedback controls were replaced with a real Learn This action plus Export Trace.
- Removed default prompt/training text from the chat composer and ingestion editor.
- Replaced the inline auth panel with a dedicated enterprise sign-in/create-account gate before chat loads.
- Added active Chat/Training navigation state and compact runtime status layout.
- Removed the duplicate floating insight opener.
- Added clearer API/runtime status messages instead of the generic `API unavailable.` fallback.
- Added the first event-sourced/cached/auditable runtime slice:
  append-only local audit events, scoped query result cache, cache-hit/cache-invalidated events, feedback events,
  memory-write events, and `/v1/audit/events`.
- Promoted the audit and cache layer from JSONL/in-memory to durable SQLite:
  WAL-enabled `audit_events`, indexed aggregate/user/type lookup, CQRS read-model projections, and persistent
  verified result cache.
- Added backend auth proxy endpoints:
  `/v1/auth/config`, `/v1/auth/signin`, and `/v1/auth/signup`, so the frontend no longer depends on loading
  Supabase public env vars from the `frontend` working directory.
- Fixed the Training UI unauthenticated state:
  it no longer calls protected panel endpoints without a stored session and now shows a sign-in instruction.
- Added event-store tests and raised the suite to 25 passing tests.
- Added production-shaped event/result coverage for Canvas, Invention, training, review actions, sandbox runs,
  and math solver results:
  Saga events, verified result signatures, persistent cache entries, and CQRS projections all write through the
  same SQLite event store.
- Added protected API routes for review, sandbox, and math:
  `/v1/review/action`, `/v1/sandbox/run`, and `/v1/math/solve`.
- Added deterministic sandbox policy and SymPy-backed math solving with result caching.
- Raised the suite to 26 passing tests.

## Current Codebase Assessment

JIMS-AI is strongest as an architecture-first prototype. The codebase already reflects the core idea from the
spec: transformer calls are bounded at T1/T2, while memory, retrieval, graph reasoning, verification, capability
routing, and CSSE are separate runtime pieces.

The main risk is narrowing. Several services are still scaffolded with health routes and Dockerfiles, while much
of the behavior remains concentrated in `prototype/jimsai`. However, the runtime now has durable audit events,
CQRS-style read projections, and persistent verified result caching, so it is moving from architecture demo toward
operational substrate.

The highest-leverage next move is extending this foundation into execution routes: deterministic executor results,
symbolic math results, saga state, and human review decisions should all write events and result signatures.

## Priority Backlog

0. Make event-sourced, cached, auditable state production ready. Status: in progress; SQLite event store, CQRS projections, audit API, result signatures, and persistent query/sandbox/math caches are implemented.
1. Extend durable Event Sourcing/CQRS to production database migrations, retention policy, tenant partitioning, and replay tooling.
2. Move deterministic executor from local subprocess policy to isolated Docker/Kubernetes worker pool.
3. Expand Saga orchestration with compensation handlers and retry/dead-letter queues for Canvas, Invention, training, sandbox, and solver flows.
4. Add Z3-backed formal constraint checks for rules that can be encoded as invariants.
5. Replace the Invention Engine search strategy with MCTS while preserving the current planner interface.
6. Build the coding adapter: docs retrieval, sandbox execution, static checks, tests, result signatures.
7. Build the math/science adapter: canonical expression parsing, symbolic solve, numeric fallback, result signatures.
8. Add real review actions in the Training UI: accept, correct, reject, promote, and rollback.
9. Add retrieval-quality metrics: misses, false positives, source precision, cache hit rate, and per-workspace trends.
10. Add admin governance: provider quotas, execution budgets, model activation policy, and audit log views.

## UI Guardrails

- Keep answer, evidence, and Learn This as the primary path.
- Keep traceability collapsed until requested.
- Show gaps as distinct actionable blocks, not buried footnotes.
- Avoid adding buttons unless they call an implemented endpoint or change visible state immediately.
- Put admin maturity signals in Training, not in the normal user chat path.
