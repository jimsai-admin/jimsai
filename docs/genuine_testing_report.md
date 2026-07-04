# JimsAI Genuine Testing Report — July 3, 2026

## Method: generative, property-based evaluation (anti-hardcoding by construction)

`benchmarks/genuine_eval.py` generates a **fresh knowledge base every run** from a seed:
pronounceable nonce entities and values (e.g. `Rovuku`/`MederDB`) that cannot exist in any
training corpus or keyword table. It teaches them through the real API, then grades
**properties**, never fixed expected strings:

| Property | Invariant tested |
|---|---|
| P1 learning | teach fact → English recall must surface the generated value |
| P2 gap-honesty | untaught nonce entity → explicit gap, no fabrication, no leak of other facts |
| P3 robustness | typos / casing+punctuation chaos / SMS-filler recall must still work |
| P4 multilingual | same recall in fr / yo / zh must still work |
| P5 multi-intent | math + recall in one prompt → both parts answered |
| P6 math | generated arithmetic/equations vs **locally computed** ground truth |
| P7 scoping | workspace-A facts must never leak into workspace B |

Because the seed changes each run, the system can only pass by having the general
capability — a hardcoded fix cannot survive the next seed.

## Results across runs (all against live Modal services)

| Property | Baseline (seed 42) | Fixes 1–3 (seed 777) | Fixes 1–7 (seed 370703) | All 11 fixes (seed 575266) |
|---|---|---|---|---|
| P1 learning | 33% | 33% | 67% | **100%** |
| P2 gap-honesty | 0% | 0% | 0% | **33%** |
| P3 robustness | 33% | 33% | 67% | **100%** |
| P4 multilingual | 0% | 0% | 0% | 0% |
| P5 multi-intent | 0% | 100% | 0% | 50% |
| P6 math | 0% | 67% | 100% | **100%** |
| P7 scoping | 0% | 100% | 100% | **100%** |

Baseline failures were ~100% availability collapse (503s), not capability. Successive fixes
first restored availability, then exposed and fixed genuine reasoning/retrieval defects.

## Defects found and fixed (all general mechanisms, no test-specific logic)

1. **T2 renderer was a single point of failure.** A Modal renderer timeout raised
   `CriticalServiceUnavailable` → user-facing 503, even though the deterministic CSSE render
   was already computed and passed in as an argument. Fixed: CSSE graceful fallback in
   `TransformerRenderInterface.render` and the SSE stream path (`JIMS_T2_STRICT=true`
   restores hard-fail). This is the paper's own §9 degradation contract, now real.
2. **Dead timeout config.** `.env` set `JIMS_LOCAL_RENDER_TIMEOUT=120` /
   `JIMS_LOCAL_INFERENCE_TIMEOUT=120`; code read only `JIMS_T2_TIMEOUT` (10s) /
   `JIMS_T1_TIMEOUT` (5s). Fixed: fallback chain in `QwenBridge._timeout_seconds`.
3. **Secondary intents were detected but never executed.** The pipeline now prepares and
   executes plans for up to 2 secondary intents (`CapabilityRouter.plan_for_secondary`).
4. **Structural routing short-circuit blinded multi-intent detection.** Math syntax or a
   code fence skipped semantic scoring entirely, so the other intent in the prompt was
   invisible. Semantic scoring now always runs; structural evidence keeps the query alive
   if the embedding service is down.
5. **Router could 503 a user query** ("no reliable route evidence"). Now falls back to the
   memory-first route at low confidence — retrieval/validation/gap-reporting still decide
   what is answerable. Routing uncertainty degrades ranking, never availability.
6. **Three "replace the reasoning chain" bugs** destroyed verified memory claims:
   - web search results replaced the chain (memory now outranks the public web, spec §4.4);
   - a solved math step replaced the chain even for multi-intent prompts;
   - a blocked capability gate step replaced the chain even when source-backed memory
     claims held the answer (this is how a Yoruba query misrouted to `audio_generation`
     lost an answer that retrieval had already found).
   All three now merge instead of replace whenever source-backed claims exist.
7. **Web search executed even when scoped memory already answered.** Now skipped when
   retrieval surfaced strong workspace/user-scoped evidence (`JIMS_WEB_SKIP_MEMORY_SCORE`,
   default 0.55) — memory precedence plus seconds saved per query. Retrieval was reordered
   before capability execution to make this possible (they were independent).
8. **Wrong-entity leaks (hallucination-adjacent).** A question about an unknown entity
   lexically/semantically matched a taught fact about a *different* entity and answered it
   confidently. Fixed: entity-scope evidence gate in retrieval — when a query names
   entities, no signature is admitted without matching one of them (user-profile and
   relation-scoped evidence exempt). P2 went 0% → 33%; remaining leaks come via the
   graph-expansion path (see below).
9. **T2 render prompt shipped the entire VCO** (layer results, trace events — tens of KB)
   to a 4B model. Now sends a render-view: claims, gaps, confidence, sources, capability
   summaries. T2 is strictly the fluency layer.
10. **Truncated `<think>` blocks leaked chain-of-thought** into responses. Unclosed blocks
    are now stripped everywhere closed ones were.
11. **Segment-aware multi-intent attention** (new mechanism): the prompt is split into
    sentence segments (script-neutral punctuation), each segment is embedded in one batched
    call and votes its own capability; any segment whose intent differs from the primary
    becomes a secondary intent. A whole-prompt embedding blends intents; per-segment
    embeddings see each one.

## Configuration corrections

- `.env` had `JIMS_LLM_PROVIDER=nvidia`, routing ALL T1/T2 traffic to
  `integrate.api.nvidia.com` (Llama-3.3-70B) — contradicting the v11 spec ("all LLM
  inference goes to Modal services only") and failing under rate limits while the healthy
  Modal Qwen services sat unused. Local servers should run with
  `JIMS_LLM_PROVIDER=modal JIMS_T1_PROVIDER=modal JIMS_T2_PROVIDER=modal` (used for all
  eval runs); decide whether the `.env` default should change permanently.
- Added `JIMS_T2_TIMEOUT=20` — interactive render budget; past 20s the CSSE deterministic
  render serves the verified answer.

## Remaining work (prioritized)

1. **P4 multilingual retrieval (0%)** — the one systemic capability gap left. Routing and
   rendering now behave; the failure is retrieval-side: cross-lingual queries (fr/yo/zh)
   containing the exact Latin entity nonce still miss the taught signature, while English
   phrasings hit. Suspects: compiler tokenization/question-intent extraction on non-English
   text producing relation filters that exclude, and taught signatures lacking real
   embeddings at query time (`reembedding_required` path). Needs a focused debug session
   with server-side retrieval logging.
2. **Entity gate for graph expansion** — `_expand_related_results` re-admits neighbors
   without the entity-scope gate; this is the remaining P2 leak path.
3. **Latency (median 113s/query)** — dominated by Modal cold starts and the CPU-hosted T1
   intent service (Qwen3-1.7B on CPU; multiple T1 calls per query). Recommendations:
   keep renderer + intent containers warm (`min_containers=1` or longer scaledown), move
   T1 to a small GPU, batch/deduplicate the query embedding (the intent classifier and the
   capability router each embed the same query), and make streaming the default UI path.
   The new 20s T2 budget bounds worst-case interactive latency.
4. **Render fluency under truncation** — when T2 output is cut mid-`<think>`, the stripped
   remainder can be garbled; prefer CSSE fallback when the stripped render is suspiciously
   short relative to the deterministic basis.
5. **Security**: `test_jimsai_live.py` commits a real Supabase password in plaintext (and
   the git history retains it). Rotate the credential and move it to `.env`. Same review
   for the NVIDIA/Modal/Supabase keys in `.env` if the repo ever becomes shared.

## How to re-run

```bash
# server (Modal backend)
JIMS_LLM_PROVIDER=modal JIMS_T1_PROVIDER=modal JIMS_T2_PROVIDER=modal \
  .venv/Scripts/python.exe -m uvicorn prototype.app:app --port 8000

# evaluation — new random seed each run; --seed N reproduces a run
JIMS_EVAL_PASSWORD=... .venv/Scripts/python.exe -u benchmarks/genuine_eval.py --facts 3 --languages fr,yo,zh
```
