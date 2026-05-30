# Implementation Assumptions

1. The PDF is authoritative. When the repo request used names not literally present in the PDF, the nearest
   PDF-aligned interpretation was used.
2. Phase 1 must be local-first, so heavyweight encoders are represented by deterministic local adapters.
   This keeps bounded execution and testability while preserving the dual-representation contract.
3. The deterministic compiler path is primary. Transformer adapters are optional boundary interfaces and are
   never required for runtime correctness.
4. Production stores are represented by service contracts and Docker services. In-memory implementations
   prove behavior before Redis/Neo4j/PostgreSQL adapters are wired.
5. The benchmark suite reports local deterministic metrics now and leaves external LLM comparisons behind
   explicit API-key-controlled adapters.
