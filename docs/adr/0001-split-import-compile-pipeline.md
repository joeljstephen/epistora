# ADR 0001: Split Import and Compile Pipeline with Readwise as Extracted-Content Provider

## Status

Accepted

## Context

Epistora's existing ingest pipeline is a single-pass LangGraph StateGraph: fetch → dedup → analyse → extract_knowledge → write_vault → persist. Every item that enters the pipeline triggers a full LLM analysis immediately.

Readwise is being introduced as the first-class v1 input. Unlike Raindrop (a link-only provider), Readwise already provides extracted content — full article text, highlights, and YouTube transcripts. Running Readwise items through the existing single-pass pipeline means every imported item immediately costs an LLM call, which is expensive and slow for bulk imports (e.g., initial sync of hundreds of items).

## Decision

Split the pipeline into two separate flows:

1. **Import flow** (plain async function, no LangGraph): Pull items from Readwise API → create catalog rows → write raw evidence → mark `content_status = ready`, `brief_status = pending`.

2. **Brief compilation flow** (LangGraph graph): Load pending sources → compose prompt → run LLM → build artifacts → write vault via existing sink → mark `brief_status = ready`.

The Readwise connector extends the existing `LinkInboxConnector` protocol with an optional `pre_extracted_content` field on `SourceItem`. A `ProviderContentMode` enum (`extracted_content` vs `link_only`) distinguishes provider types.

The existing `ingest_graph.py` remains unchanged for Raindrop and manual URL flows.

Auto-brief triggers after sync with a configurable limit (default: 5 items), using priority-scored ordering weighted toward newer items.

## Consequences

- Bulk Readwise imports are fast and free (no LLM calls until briefing).
- Users can selectively brief items via CLI (`epistora brief pending --limit N`) or Studio.
- Two code paths into the vault (existing ingest graph + new brief graph) must produce consistent artifacts. Both use the same `MarkdownVaultSink`.
- The brief graph reuses `ArtifactBundle` and `MarkdownVaultSink` — the sink is provider-neutral.
- Re-briefing is supported via `--force` flag.
- Raindrop/manual URL flow is unaffected.
