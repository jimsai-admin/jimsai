# About JimsAI: The Neuro-Symbolic Operating System

JimsAI is not just another LLM wrapper or simple chatbot. It is designed as an **Adaptive, Closed-Loop Neuro-Symbolic Operating System** built to run enterprise-grade, multi-tenant workspaces. 

This document explains JimsAI's core architecture, how it processes prompts, its safety guardrails, how it continuously learns, and how the upcoming enhancements in the implementation plan make it a resilient alternative to standard frontier models (like GPT-4, Claude, or Gemini).

---

## 1. What is JimsAI?

Standard AI models are **probabilistic**. They guess the next word based on patterns they have seen, which makes them excellent at creative writing but prone to hallucination, calculation errors, and logic drifts.

JimsAI bridges this gap by combining two systems:
1. **The Neural Brain (LLM/Transformer):** Excellent for understanding natural language, recognizing intent, and general reasoning.
2. **The Symbolic Engine (Solver/Database):** Excellent for mathematical calculations, strict logic, code verification, and absolute factual accuracy.

By combining these, JimsAI guarantees factual accuracy when it knows the answer, routes simple questions efficiently, and uses advanced reasoning for complex coding or math tasks.

---

## 2. Core Architecture: The "Frozen Base" + "Workspace Adapter"

JimsAI is designed for **Multi-Tenancy**. It allows multiple organizations (workspaces) to share the same core AI infrastructure while keeping their data completely isolated and their behaviors customized.

```
                  ┌──────────────────────────────┐
                  │      User Prompt Input       │
                  └──────────────┬───────────────┘
                                 │
                   ┌─────────────▼─────────────┐
                   │    Workspace Router       │ (Resolves WorkspaceContext)
                   └─────────────┬─────────────┘
                                 │
         ┌───────────────────────┴───────────────────────┐
         ▼                                               ▼
┌──────────────────┐                            ┌──────────────────┐
│  Workspace A     │                            │  Workspace B     │
│  - Custom Memory │                            │  - Custom Memory │
│  - Adapter Weights│                           │  - Adapter Weights│
└────────┬─────────┘                            └────────┬─────────┘
         │                                               │
         └───────────────────────┬───────────────────────┘
                                 │
                   ┌─────────────▼─────────────┐
                   │   Shared JimsAI Base      │ (Frozen Core Engines)
                   │   - Symbolic Solver       │
                   │   - Core Reasoning Model  │
                   └───────────────────────────┘
```

### The Frozen Base Model
The core reasoning capability of JimsAI is packaged as a **Base Model** that remains completely frozen. Because it is static, it cannot be corrupted by low-quality inputs or bad memory uploads from a single user.

### Workspace Adapters
Each workspace (tenant) gets a lightweight, customizable layer called a [WorkspaceAdapterModel](file:///c:/Users/ajibe/Jims-AI/prototype/jimsai/personalization.py#L355-L436). This adapter layer:
* **Learns Workspace Preferences:** Learns the preferred length, tone, and domain interests of the users in that workspace.
* **Optimizes Routing:** Adjusts internal confidence thresholds. For example, if a workspace asks repetitive customer support questions, JimsAI adapts by lowering check thresholds to skip expensive transformers, making responses faster and cheaper.
* **Isolates Memory:** All facts, rules, and vector embeddings uploaded by Workspace A are invisible to Workspace B.

---

## 3. The 5-Tier Confidence Model

When a user submits a prompt, JimsAI does not immediately send it to a heavy AI model. Instead, it evaluates the prompt through **5 Tiers of Confidence** to ensure accuracy and cost-efficiency:

| Tier | Name | Confidence Score | Action & Logic |
| :--- | :--- | :--- | :--- |
| **Tier 1** | **Symbolic Solver / Approved Memory** | 99% - 100% | Bypasses AI models entirely. It checks if the question matches a mathematically verified rule or a high-consensus memory signature in the database, yielding immediate, 100% accurate results. |
| **Tier 2** | **High-Consensus Knowledge** | 90% - 98% | Retrieves highly verified knowledge with clear citations and zero-hallucination guardrails. |
| **Tier 3** | **Plausible Learned Memory** | 70% - 89% | Uses the neural model to synthesize responses backed by workspace memories, marking them clearly with a provenance label. |
| **Tier 4** | **Weak/Stale Memory** | 40% - 69% | The system generates a response but prefixes it with a **warning label** notifying the user that the data is stale or unverified. |
| **Tier 5** | **Gap / Unknown** | < 40% | Avoids making up answers. JimsAI will honestly state: *"I don't have verified memory for this yet."* |

---

## 4. Key Problems & How the Implementation Plan Solves Them

The JimsAI codebase is continuously evolving. Below are the key engineering challenges identified in the current system and how the [Implementation_Plan.md](file:///c:/Users/ajibe/Jims-AI/Implementation_Plan.md) resolves them:

### A. The Serverless Cold Start Problem
* **The Problem:** Running heavy text-embedding libraries (`sentence-transformers`) inside serverless architectures (like AWS Lambda) causes major latency overhead and memory limits.
* **The Solution:** The pipeline is being upgraded to make lightweight HTTP API calls to an external Hugging Face Space endpoint (`/v1/embed`). This keeps JimsAI lightweight, fast, and operational in serverless environments.

### B. The Code & Math "Prediction Trap"
* **The Problem:** Standard AIs struggle with multi-step logic. If you ask a frontier model to write a complex script or solve a physics formula, it might write code that looks correct but fails to compile or run.
* **The Solution (The MCTS Invention Engine):** JimsAI is integrating a Monte Carlo Tree Search (MCTS) loop. When you ask it to code or do math, it:
  1. Spawns candidate logic trees.
  2. Syntactically checks code using an Abstract Syntax Tree (AST).
  3. Runs code in an isolated **sandbox** to verify if tests pass.
  4. Only returns the response once the code successfully compiles and executes.

### C. Math Operator Solver Crashes
* **The Problem:** The symbolic math solver crashes when encountering conversational prompts that contain math symbols (like `+`, `-`, `*`).
* **The Solution:** The system is implementing **Ambient Math Routing**. If a prompt contains math symbols but is conversational, it bypasses the rigid symbolic solver parser and routes to the sandbox or the neural engine, avoiding unexpected system crashes.

### D. Multi-Domain Vector Representation Gaps
* **The Problem:** Single-model encoders degrade in accuracy when representing highly diverse domains (such as mixing standard Yoruba conversational text with a Python function or an electrical schematic).
* **The Solution (Adaptive Hybrid Ingestion Encoder):** JimsAI introduces the [AdaptiveHybridEncoder](file:///c:/Users/ajibe/Jims-AI/prototype/jimsai/encoder/adaptive_hybrid_encoder.py). This fuses semantic (`multilingual-e5-small`), code (`codebert-base`), and technical (`jina-embeddings-v3`) representations into a weighted, unified 768-dimensional space. It includes a [SymbolicAugmenter](file:///c:/Users/ajibe/Jims-AI/prototype/jimsai/encoder/adaptive_hybrid_encoder.py#L17) for math normalization and code extraction, and falls back automatically to remote HTTP endpoints in cold-start environments.

---

## 5. Security, Safety, and Rollbacks

JimsAI is designed with defense-in-depth safety:

* **Sliding 24-Hour Undo Window:** If a user accidentally uploads a corrupted spreadsheet or bad database dump, it could poison the search results. JimsAI provides a `/v1/memory/rollback` endpoint. This acts as a global "undo" button, cascading deletion of all vector database indices, graph nodes (Neo4j), and database signatures committed in the last 24 hours.
* **Context Decoupling:** To prevent the AI from getting confused when a user changes the topic of conversation, JimsAI automatically detects "topic drift" and prunes stale history context, keeping responses focused.
* **Provenance Labels:** Every answer JimsAI renders includes a small tag showing where the information came from (e.g., `[Verified • Symbolic Solver]`, `[Plausible • Learned Pattern]`, or `[Unverified • Needs Review]`).

---

## 6. How JimsAI Processes a Prompt (Step-by-Step)

To see JimsAI in action, let's look at how it handles a user query:

1. **Ingest & Contextualize:** A user in Workspace A sends: *"What is the formula for our standard pricing and calculate it for 150 units?"*
2. **Retrieve Context:** The system resolves the user's `WorkspaceContext`. It fetches only Workspace A's memory signatures.
3. **Intent Detection & Route:** The query is routed to `/v1/embed` to classify intent. It detects a calculation/formula task.
4. **Symbolic Verification (T1):** The solver checks if Workspace A has a verified rule for `standard pricing formula`. It finds a symbolic formula rule: `Price = Units * 12.50`.
5. **Sandbox Rollout (MCTS):** JimsAI executes the calculation in a sandbox: `150 * 12.50 = 1875`. It verifies the math is correct.
6. **Provenance Labeling:** The system formats the answer and appends the source metadata: `[Verified • Symbolic Solver]`.
7. **Output:** The user receives a 100% accurate calculation with a clean citation.

---

## 7. How JimsAI Compares to Frontier Models

| Feature | Frontier Models (GPT-4, Claude, Gemini) | JimsAI |
| :--- | :--- | :--- |
| **Logic Foundation** | 100% Probabilistic Neural Network | Neuro-Symbolic (Neural + Symbolic Solver) |
| **Factual Accuracy** | High, but prone to hallucinations | Guaranteed 100% for Tier 1 & 2 facts |
| **Context Window Cost** | Expensive (must stuff entire history/docs) | Cheap (uses isolated vector/graph memory pools) |
| **Code/Math Verification** | Generates code blindly; no verification | Run-time Sandbox testing with MCTS validation |
| **Rollback Safety** | None (weights are contaminated permanently) | Sliding 24-hour undo window for vector/graph data |
| **Data Privacy** | Complex (data can opt-out but weights might train) | Strict tenant database separation out-of-the-box |
