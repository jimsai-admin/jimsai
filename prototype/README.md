# Phase 1 Prototype

The prototype is the local hybrid runtime for the PDF pipeline. It uses structured execution for memory,
retrieval, graph traversal, simulation, validation, planning, abstraction, world-model activation, and CSSE.
It can also call bounded Groq transformer interfaces at T1, T2, Active Canvas, and Invention Engine when the
corresponding environment flags are enabled.

The public-facing UX is a chat runtime; the architecture behind it is not an LLM-only chatbot. Transformers
interpret and render. The cognitive state remains inspectable, traceable, and constrained.

```bash
uvicorn prototype.app:app --reload --port 8000
pytest tests
```

Frontend routes:

- `/chat` and `/user`: persistent chat runtime with memory, reasoning, source, simulation, canvas, invention, and feedback panels.
- `/training`: eight-panel operator UI from the PDF training specification.
