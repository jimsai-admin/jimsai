# PDF Alignment Matrix

Date: 2026-05-27

This matrix records the conservative implementation mapping back to `docs/JimsAI_Complete_Specification_v8.pdf`.

## Transformer Role

PDF anchor: pages 5, 7, 8, 49.

- JIMS-AI is not a replacement for transformers; it uses them as precision tools.
- T1 handles ambiguity, slang, metaphor, emotion, and incomplete thought, then emits structured IR.
- T2 renders a Verified Cognitive Object into fluent natural language.
- Active Canvas and Invention can use larger transformer calls as bounded, one-shot or candidate-generation tools.
- The middle runtime owns memory, retrieval, routing, simulation, validation, reasoning, and feedback.

Implementation:

- `prototype/jimsai/model_bridge.py`: Groq adapter with bounded JSON calls and deterministic fallback.
- `prototype/jimsai/runtime_layers.py`: explicit T1/L1-L9/T2 chain.
- `prototype/jimsai/pipeline.py`: response exposes layer results and whether Groq was used.

## Training UI Panels

PDF anchor: pages 29-31.

- Panel 1: Multimodal Data Ingestion.
- Panel 2: Human Review Queue.
- Panel 3: Ambiguity Resolution Queue.
- Panel 4: Memory Inspection and Management.
- Panel 5: World Model Dashboard.
- Panel 6: Training Pipeline Monitor.
- Panel 7: Canvas and Invention Management.
- Panel 8: Model Inspection and Feedback.

Implementation:

- `frontend/app/training/page.tsx`: eight-panel operator UI.
- `GET /v1/training/dashboard`: panel data contract.
- `POST /v1/training/ingest`: signature, world model candidate, and SPPE pair generation.
- `POST /v1/canvas/run` and `POST /v1/invention/run`: prototype scheduling contracts.

## User Chat UI

PDF anchor: pages 32-33.

- Persistent multimodal chat with file upload.
- Canvas and Invention triggers from chat.
- Memory context sidebar.
- Transparency controls for reasoning, sources, confidence, gaps, canvas, and invention.
- Memory controls for remember, correct, forget, and export.

Implementation:

- `frontend/app/user/page.tsx`: persistent chat runtime.
- `frontend/app/chat/page.tsx`: public chat alias.
- `POST /v1/query`: strict pipeline response with sources, gaps, simulations, layer results, abstraction, world model activations, and Groq usage.
- `POST /v1/feedback`: feedback signal capture.

## Production Readiness Boundary

The repository is moving toward production readiness, but Phase 1 remains a local prototype runtime. The PDF's provider stack is represented by environment contracts, compose services, deployment guides, and API boundaries. Full production readiness still requires active adapters for Cloudflare R2, Cloudflare Vectorize, Supabase/PostgreSQL, Neo4j Aura, Redis/Celery workers, authentication hardening, and multimodal encoders beyond deterministic text extraction.
