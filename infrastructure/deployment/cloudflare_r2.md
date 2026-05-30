# Cloudflare R2 Setup Guide

The production runtime includes a real Cloudflare R2 adapter. It is enabled by `JIMS_STORAGE_BACKEND=production`
or `JIMS_ENABLE_R2=true`.

## Role in JIMS-AI

The provider is used only for the architecture function assigned in the PDF. It must not become a hidden
reasoning engine or unbounded generation path.

## Configuration

Provision an R2 bucket and S3-compatible access keys, then set `CF_ACCOUNT_ID`, `CF_R2_BUCKET`,
`CF_R2_ACCESS_KEY`, and `CF_R2_SECRET_KEY`. Training ingestion stores raw content under
`training/{signature_id}.txt` and records the object reference in downstream vector metadata when available.

## Verification

- Health check passes.
- Deterministic test still passes without provider-specific behavior drift.
- Traces include provider operation names and resource identifiers.
