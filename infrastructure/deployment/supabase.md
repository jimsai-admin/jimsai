# Supabase Setup Guide

The production runtime includes a real Supabase/Postgres adapter. It is enabled by `JIMS_STORAGE_BACKEND=postgres`,
`JIMS_STORAGE_BACKEND=production`, or `JIMS_ENABLE_POSTGRES=true`.

## Role in JIMS-AI

The provider is used only for the architecture function assigned in the PDF. It must not become a hidden
reasoning engine or unbounded generation path.

## Configuration

Use the Supabase pooler or direct Postgres connection string as `POSTGRES_URL`, then run
`infrastructure/postgres/supabase.sql`. The runtime writes signatures plus `training_panel_items`, which power the
infinite-paginated operator panel pages.

## Verification

- Health check passes.
- Deterministic test still passes without provider-specific behavior drift.
- Traces include provider operation names and resource identifiers.
