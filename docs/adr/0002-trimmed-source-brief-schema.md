# ADR 0002: Trimmed Source Brief Schema with Type-Conditional Fields

## Status

Accepted

## Context

The existing LLM analysis schema requires 22 fields per source, all generated in a single LLM call regardless of source type. Fields like `detailed_outline`, `important_examples`, `notable_quotes`, `best_for`, `why_it_matters`, and `open_questions` are expensive in token cost but low in immediate value for the v1 "should I read/watch this?" decision.

The Source Brief is evolved in-place from the existing analysis — same job, new schema. No parallel output.

## Decision

Trim the schema to a lean v1 set:

**Base fields (all source types):** `quick_brief`, `best_next_action`, `consume_recommendation`, `key_ideas` (array), `takeaways` (array, replaces `actionable_takeaways`), `important_terms` (array), `topics` (array), `entities` (array of objects), `concepts` (array of objects).

**Video-specific:** `watch_verdict` (enum: watch/skim/skip/transcript_sufficient), `watch_verdict_reasoning`, `quick_section_guide`, `detailed_sections`, `signal_vs_filler`.

**Article-specific:** `read_verdict` (enum: read/skim/skip/brief_sufficient), `why_read_or_skip`, `key_sections`.

**Thread-specific:** `thread_summary`, `main_claims` (array of distilled claims), `useful_links_or_references` (array of curated links).

**Dropped:** `summary`, `five_minute_read`, `detailed_reading_note`, `detailed_outline`, `important_examples`, `notable_quotes`, `best_for`, `why_it_matters`, `open_questions`.

**Auto-detected (not LLM-generated):** `evidence_limits` — computed from `extraction_quality`, word count, and source type.

The JSON schema is type-conditional: the prompt and required fields vary by SourceType. A single LLM call produces only the relevant fields.

Output is defined as a Pydantic model with structured output for the API backend and JSON extraction fallback for CLI backends.

## Consequences

- Fewer tokens per LLM call (estimated 30-40% reduction).
- Type-specific analysis is more focused (no empty video fields on articles).
- Structured verdicts (enum-like) enable machine-parseable filtering in Studio.
- Existing vault note templates must be updated to match the new section structure.
- Tests that assert on the old 22-field schema must be updated.
