# Neo4j AuraDB Setup Guide

The production runtime includes a real Neo4j Aura adapter. It is enabled by `JIMS_STORAGE_BACKEND=production`
or `JIMS_ENABLE_NEO4J=true`.

## Role in JIMS-AI

The provider is used only for the architecture function assigned in the PDF. It must not become a hidden
reasoning engine or unbounded generation path.

## Configuration

Set `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, and optionally `NEO4J_DATABASE`. Aura URIs should use
`neo4j+s://...`. Training ingestion merges `MemorySignature`, `Entity`, `RELATION`, and `CAUSES` records.

## Verification

- Health check passes.
- Deterministic test still passes without provider-specific behavior drift.
- Traces include provider operation names and resource identifiers.
