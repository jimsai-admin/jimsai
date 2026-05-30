# Benchmarking Methodology

Phase 1 benchmarks are deterministic local measurements. External GPT-style, transformer pipeline, and
agentic runtime comparisons are adapter-based and must not be called unless keys are configured.

Metrics:

- Hallucination rate: count unsupported claims not backed by a source signature or explicit gap.
- Energy proxy: module activations, transformer bypass count, and wall-clock runtime.
- Memory usage: Python process RSS where available plus signature/index counts.
- Latency: compiler, retrieval, graph traversal, simulation, validation, planner, CSSE.
- Determinism: same input and memory must produce identical trace hash.
- Reproducibility: benchmark config and data are versioned under `benchmarks/` and `datasets/`.
- Context scaling: grow signatures and ensure retrieval does not reprocess all raw source text.
