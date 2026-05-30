# Local Dev with Ollama and LanceDB Setup Guide

This guide is a Phase 2 integration note. Phase 1 runs locally without this provider.

## Role in JIMS-AI

The provider is used only for the architecture function assigned in the PDF. It must not become a hidden
reasoning engine or unbounded generation path.

## Configuration

Add the matching placeholders in `.env.example`, provision the provider resource, then map credentials
into Docker, Kubernetes, or the deployment platform secret manager.

## Verification

- Health check passes.
- Deterministic test still passes without provider-specific behavior drift.
- Traces include provider operation names and resource identifiers.
