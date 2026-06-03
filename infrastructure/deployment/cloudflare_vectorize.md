# Cloudflare Vectorize Setup Guide

The production runtime includes a real Cloudflare Vectorize REST adapter. It is enabled by
`JIMS_STORAGE_BACKEND=production` or `JIMS_ENABLE_VECTORIZE=true`.

## Role in JIMS-AI

The provider is used only for the architecture function assigned in the PDF. It must not become a hidden
reasoning engine or unbounded generation path.

## Configuration

Create a Vectorize index with dimensions matching the configured encoder model, then set `CF_ACCOUNT_ID`,
`CF_VECTORIZE_INDEX`, and `CF_VECTORIZE_API_TOKEN`. The runtime inserts signature records with `id`,
`values`, and metadata through the Vectorize insert endpoint.

Use the index **name**, not the dashboard description, for `CF_VECTORIZE_INDEX`. For the current
768-dimensional index, keep:

```env
CF_VECTORIZE_DIMENSIONS=768
CF_VECTORIZE_INDEX=jimsai-embeddings
```

The API token must be scoped to the same Cloudflare account as `CF_ACCOUNT_ID` and needs account-level
Vectorize read/write capability. If provider readiness reports HTTP 403, recreate
`CF_VECTORIZE_API_TOKEN` with the account permission required for Vectorize writes and make sure the
account filter includes the account that owns the index.

## Verification

- Lambda provider readiness reports `vectorize: configured=True available=True`.
- Deterministic test still passes without provider-specific behavior drift.
- Traces include provider operation names and resource identifiers.
