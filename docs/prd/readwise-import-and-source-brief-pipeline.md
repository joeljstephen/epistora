# PRD: Readwise Import and Source Brief Pipeline

## Problem Statement

Epistora needs a polished Readwise to Obsidian v1 path that can handle a large saved library without forcing every imported Source through an immediate LLM compile. Today, the ingestion path is optimized around direct URLs and link-only providers: a Source enters the pipeline, content is fetched, analysis runs, artifacts are built, and the Vault is written in one pass. That shape is too expensive and slow for Readwise because Readwise is an Extracted Content Provider: it already supplies useful article text, highlights, and transcripts.

The user needs bulk Readwise sync to be fast, cheap, and safe, while still preserving enough Raw Capture evidence to compile high-signal Source Briefs later. The Source Brief also needs to be leaner than the existing 22-field source analysis so it answers the v1 decision: should I read, watch, skim, skip, or rely on the brief?

## Solution

Build a split Readwise import and Source Brief compilation flow.

Readwise import will pull recent Readwise items, normalize them into provider-neutral Sources, store provider references and raw evidence, and mark those Sources as content-ready but brief-pending. This import flow must not call an LLM.

Brief compilation will be a separate graph that loads pending Sources with available Source Content, composes a SourceType-aware prompt, asks the configured Backend for a trimmed Source Brief, builds the canonical Artifact Bundle, writes the Compiled Note and Raw Capture through the existing Vault sink, and marks the brief lifecycle ready or failed.

The v1 Studio and CLI experience should make this flow clear: sync Readwise cheaply, see pending Sources, compile a bounded number of Source Briefs, and optionally re-brief Sources when the prompt/schema improves. Raindrop and direct URL ingestion must continue using the existing single-pass flow.

## User Stories

1. As an Epistora user, I want to connect Readwise as an input provider, so that my saved articles, highlights, threads, and videos can enter my Vault workflow.
2. As an Epistora user, I want Readwise sync to import many items without LLM calls, so that initial setup does not become slow or expensive.
3. As an Epistora user, I want Readwise article text to become Raw Capture evidence, so that the original extracted evidence is preserved before any LLM analysis.
4. As an Epistora user, I want Readwise highlights to be preserved in Source Content metadata or evidence, so that the brief can respect what I personally marked as important.
5. As an Epistora user, I want Readwise YouTube transcripts to be stored as video Raw Capture, so that videos can be briefed without refetching transcripts from YouTube.
6. As an Epistora user, I want Readwise item metadata to populate the Source catalog, so that titles, tags, saved dates, authors, and provider identifiers are visible and deduplicated.
7. As an Epistora user, I want Readwise imports to deduplicate against existing Sources by normalized URL and stable provider identity, so that the same item is not compiled twice.
8. As an Epistora user, I want imported Readwise Sources to show as content ready and brief pending, so that I can decide what to compile next.
9. As an Epistora user, I want import failures to be recorded per Source or sync attempt, so that one bad Readwise item does not block the entire sync.
10. As an Epistora user, I want the sync cursor to remember the latest successful Readwise import position, so that future syncs are incremental.
11. As an Epistora user, I want to force a Readwise resync when needed, so that corrected provider metadata or improved normalization can be applied.
12. As an Epistora user, I want a bounded auto-brief after sync, so that the highest-priority new Sources become useful immediately without compiling my entire backlog.
13. As an Epistora user, I want auto-briefing to prioritize recent and high-signal Sources, so that the first compiled notes are likely to matter.
14. As an Epistora user, I want to manually compile pending Source Briefs by limit, so that I can control cost and backlog progress.
15. As an Epistora user, I want to re-brief a Source with a force option, so that prompt/schema improvements can regenerate better notes.
16. As an Epistora user, I want article Source Briefs to include a read verdict, so that I know whether to read, skim, skip, or rely on the brief.
17. As an Epistora user, I want video Source Briefs to include a watch verdict, so that I know whether to watch, skim, skip, or trust the transcript.
18. As an Epistora user, I want thread Source Briefs to include a distilled thread summary and main claims, so that long social threads are easier to evaluate.
19. As an Epistora user, I want every Source Brief to include a quick brief, best next action, consume recommendation, key ideas, takeaways, important terms, topics, entities, concepts, and evidence limits, so that every Compiled Note has a consistent core shape.
20. As an Epistora user, I want type-specific fields only when relevant, so that article notes do not contain empty video sections and video notes do not contain article-only sections.
21. As an Epistora user, I want evidence limits computed deterministically, so that weak or partial Source Content is clearly labelled without spending LLM tokens on that judgment.
22. As an Epistora user, I want the Compiled Note to foreground the verdict and next action, so that I can decide quickly whether to consume the original.
23. As an Epistora user, I want the Raw Capture and Compiled Note to be linked by stable Source identity, so that I can inspect the evidence behind a brief.
24. As an Epistora user, I want Source Brief compilation to use the existing Backend fallback chain, so that API, OpenCode, Claude Code, and Codex configurations continue to work.
25. As an Epistora user, I want structured output when the API Backend supports it and JSON fallback for CLI Backends, so that brief compilation is reliable across Backend choices.
26. As an Epistora user, I want brief failures to be visible and retryable, so that transient Backend errors do not permanently hide Sources.
27. As an Epistora user, I want Raindrop and manual URL ingestion to remain unchanged, so that existing workflows do not regress.
28. As an Epistora user, I want both the existing ingest graph and the new brief graph to produce consistent Artifact Bundles, so that downstream sinks and read models do not care which path compiled a Source.
29. As an Epistora user, I want Studio filters for brief-pending and brief-ready Sources, so that the backlog and completed notes are easy to manage.
30. As an Epistora user, I want Studio actions for syncing Readwise and briefing pending Sources, so that I do not need to use the CLI for ordinary operation.
31. As an Epistora user, I want CLI commands for Readwise sync and pending brief compilation, so that I can script or automate the workflow.
32. As an Epistora user, I want sync and brief progress events, so that long imports and compile batches are transparent.
33. As an Epistora user, I want usage/cost metadata for brief compilation attempts, so that I can understand the cost of turning imported Sources into Compiled Notes.
34. As an Epistora maintainer, I want provider content mode to be explicit, so that extracted-content and link-only providers can share interfaces without hiding important behavior.
35. As an Epistora maintainer, I want Readwise implemented as the first extracted-content provider, so that future providers can reuse the same import contract.
36. As an Epistora maintainer, I want Source Brief schema validation to be centralized and testable, so that prompt and artifact changes remain coherent.
37. As an Epistora maintainer, I want SourceType-conditional schema construction to be isolated, so that article, video, and thread requirements can evolve without duplicating prompt logic.
38. As an Epistora maintainer, I want Raw Capture writing to be shared between import and compile paths where appropriate, so that evidence storage semantics stay consistent.
39. As an Epistora maintainer, I want the brief graph to reuse the canonical artifact builder and Markdown Vault sink, so that provider-specific code stops at normalization.
40. As an Epistora maintainer, I want tests that prove import does not call the LLM, so that cost boundaries are protected.
41. As an Epistora maintainer, I want tests that prove brief compilation writes the expected Source lifecycle statuses, so that Studio state remains trustworthy.
42. As an Epistora maintainer, I want tests that prove trimmed Source Briefs render cleanly in Vault notes, so that the Obsidian product stays polished.

## Implementation Decisions

- Add explicit Provider Content Mode modeling with `extracted_content` and `link_only` values. Readwise uses extracted content. Raindrop remains link-only.
- Extend the provider Source item contract with optional pre-extracted content. This should carry normalized raw text, cleaned text, archived markdown, highlights/transcript metadata, extraction quality, and provider raw metadata without forcing link-only providers to fill those fields.
- Implement a Readwise connector as an Extracted Content Provider. It fetches Readwise items, maps provider item types into SourceType values, preserves provider identifiers, captures tags and saved timestamps, and exposes pre-extracted Source Content.
- Keep the existing single-pass ingest graph for direct URLs, Raindrop, and manual link-only flows.
- Add a plain asynchronous Readwise import flow, separate from LangGraph. It fetches Readwise items, upserts Source catalog rows, attaches provider references and tags, writes Raw Capture evidence, records Source Content identity, stores priority metadata, and marks content ready with brief pending.
- Import flow must not call any Backend or LLM helper.
- Add a Source Brief compilation graph. It loads pending Sources with ready Source Content, composes a type-conditional prompt, calls the Backend router, validates or extracts JSON, builds an Artifact Bundle, writes through the existing Vault sink, updates catalog lifecycle, and records attempts/usage.
- Evolve the existing source analysis into the Source Brief schema rather than creating a second parallel analysis output.
- Source Brief base fields are: quick brief, best next action, consume recommendation, key ideas, takeaways, important terms, topics, entities, concepts, and evidence limits.
- Source Brief video fields are: watch verdict, watch verdict reasoning, quick section guide, detailed sections, and signal versus filler.
- Source Brief article fields are: read verdict, why read or skip, and key sections.
- Source Brief thread fields are: thread summary, main claims, and useful links or references.
- Evidence limits are computed from extraction quality, word count, and SourceType. They are not generated by the LLM.
- The API Backend should use Pydantic-backed structured output for Source Briefs. CLI Backends should use JSON extraction fallback and validate into the same Pydantic model.
- Artifact Bundle construction should accept the trimmed Source Brief and map it into canonical source, topic, entity, concept, relationship, and evidence structures without requiring deprecated fields.
- The Markdown Vault sink and source note template should render the trimmed Source Brief with verdict-first structure and no empty irrelevant type-specific sections.
- Add pending brief selection ordered by priority score, saved date, and created date. The default post-sync auto-brief limit is five.
- Add force re-briefing. Force should allow a ready or failed brief to be regenerated while preserving source identity and raw evidence.
- Add CLI commands for Readwise sync and pending Source Brief compilation. Commands should expose limit and force options.
- Add Studio API/service support for Readwise sync, pending brief compilation, and per-source brief actions. Existing Studio display states should reflect content ready, brief pending, and brief ready lifecycle.
- Maintain provider neutrality at the catalog, artifact, sink, and read-model layers. Readwise-specific behavior belongs only in provider normalization and import orchestration.
- Treat Topic, Entity, Concept hub page expansion and Synthesis Notes as post-v1. Source Briefs may still emit topic/entity/concept metadata for future use.

## Testing Decisions

- Good tests should assert externally visible behavior: catalog state, lifecycle statuses, Raw Capture evidence, Artifact Bundle content, rendered note sections, queued or completed processing jobs, Backend calls, and user-facing command/service results. Tests should avoid asserting private helper call order unless that call boundary protects cost, such as proving import does not call the LLM.
- Test the Readwise connector normalization with representative article, highlight, YouTube transcript, thread, missing-content, and duplicate-provider-id fixtures.
- Test the Readwise import service with a fake connector and fake repositories/sinks, verifying catalog upsert, provider refs, tags, raw evidence, content ready status, brief pending status, cursor update, and per-item failure isolation.
- Test that Readwise import makes zero Backend/LLM calls.
- Test pending brief selection and priority ordering, including the default auto-brief limit.
- Test the Source Brief schema models for base fields, article fields, video fields, thread fields, enum validation, and deterministic evidence limits.
- Test prompt/schema composition by SourceType so only relevant fields are required for each SourceType.
- Test the Source Brief compilation graph with fake Backend output for article, YouTube, and X thread Sources.
- Test JSON extraction fallback for CLI Backends and structured validation for API Backend behavior where existing Backend test patterns allow it.
- Test Artifact Bundle mapping from trimmed Source Briefs, especially replacement of actionable takeaways with takeaways and absence of dropped fields.
- Test Markdown rendering for article, video, and thread Compiled Notes so verdicts, quick brief, key ideas, takeaways, important terms, and next actions appear without empty irrelevant sections.
- Test force re-briefing updates lifecycle and rendered outputs without duplicating Source identity.
- Test Raindrop/direct URL regression by keeping existing ingest graph tests passing and adding a focused assertion that link-only providers still use the current path.
- Prior art exists in the current ingest flow tests, artifact builder tests, Markdown Vault sink tests, source catalog tests, queue automation tests, Studio service tests, and Backend router structured-output tests.

## Out of Scope

- Building full Topic, Entity, Concept hub pages from Source Brief metadata.
- Producing Synthesis Notes.
- Replacing the existing Raindrop/manual URL ingest graph.
- Native URL fetching for Readwise items that do not provide extracted content.
- Full Broad Chat or Sidebar Chat behavior.
- Deep compile behavior beyond lifecycle compatibility.
- Multi-provider sync scheduling beyond fitting Readwise into the existing operator surfaces.
- Rich cost dashboards beyond recording usage/attempt metadata needed for later reporting.
- Perfect historical migration of already-compiled old 22-field notes.

## Further Notes

- The Obsidian Vault remains the durable product. SQLite remains a rebuildable runtime/read-model support layer.
- The important architectural boundary is cost: import is evidence capture and catalog state only; brief compilation is the LLM boundary.
- Two compilation paths will exist after this work: the existing link-only ingest graph and the new brief graph. Both must converge on the same Artifact Bundle and Vault sink contracts.
- The Source Brief schema is an in-place evolution of the current source analysis. Implementation should remove or de-emphasize old fields rather than preserving a hidden second analysis shape.
- The PRD assumes the module breakdown from the accepted ADRs: provider/content contracts, Readwise import orchestration, Source Brief schema/prompting, brief graph compilation, Vault rendering, CLI/Studio surfaces, and focused tests for each contract.
