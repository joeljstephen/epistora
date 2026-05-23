# ADR 0002: Rich Source Brief Schema as the v1 Compiler Contract

## Status

Accepted

## Context

Epistora needs a stable v1 analysis shape between Source Content and Artifact
Bundle construction. A verdict-only "should I read/watch this?" schema is too
narrow for the actual product: the Compiled Note is not only a triage card, it
is the durable source note in the Vault and the main evidence-backed reading
surface.

The current 22-field analysis shape contains several fields that are still
valuable for v1: `summary`, `five_minute_read`, `detailed_reading_note`,
`detailed_outline`, `important_examples`, `notable_quotes`, `best_for`,
`why_it_matters`, and `open_questions`. Removing those fields pushes useful
knowledge either into prompts, templates, or caller-specific filler, which makes
the Source Brief module shallow.

The architectural problem is not that the Source Brief has too many useful
fields. The problem is that the fields are inconsistently typed and the compiler
path treats Source Brief as a smaller schema that must be expanded back into the
full source-analysis shape.

## Decision

Make Source Brief the single rich v1 analysis contract. It should contain the
fields required to render a useful Compiled Note, build Artifact Bundles, support
Studio filtering, and power later review/query flows.

The v1 Source Brief should keep these base fields for all source types:

- `quick_brief`
- `summary`
- `five_minute_read`
- `detailed_reading_note`
- `best_next_action`
- `consume_recommendation`
- `why_it_matters`
- `key_ideas`
- `detailed_outline`
- `important_examples`
- `takeaways`
- `notable_quotes`
- `best_for`
- `important_terms`
- `open_questions`
- `topics`
- `entities`
- `concepts`

`takeaways` is the canonical field name; older wording such as
`actionable_takeaways` should not remain a separate v1 concept.

The v1 Source Brief should also keep type-conditional fields:

**Video-specific:** `watch_verdict` (enum:
watch/skim/skip/transcript_sufficient), `watch_verdict_reasoning`,
`quick_section_guide`, `detailed_sections`, `signal_vs_filler`.

**Article-specific:** `read_verdict` (enum: read/skim/skip/brief_sufficient),
`why_read_or_skip`, `key_sections`.

**Thread-specific:** `thread_summary`, `main_claims`,
`useful_links_or_references`.

Fields that are lists in the domain should be modeled as lists, not markdown
strings: `key_ideas`, `important_examples`, `takeaways`, `notable_quotes`,
`best_for`, `important_terms`, `open_questions`, `topics`, `entities`,
`concepts`, and type-specific lists.

`evidence_limits` remains auto-detected, not LLM-generated. It is computed from
`extraction_quality`, word count, source type, and extraction method.

There should be one v1 Source Brief path:

```text
Source Content -> Source Brief -> Artifact Bundle -> sinks
```

The ingest graph, Readwise brief compilation flow, and safe/fallback capture
path should all produce or derive the same Source Brief shape before building an
Artifact Bundle. The Artifact Bundle builder should consume this stable Source
Brief contract directly instead of requiring callers to assemble a loose
analysis dictionary.

The JSON schema remains type-conditional: a single LLM call should produce the
base fields plus only the relevant type-specific fields.

## Consequences

- Token usage is higher than a verdict-only brief, but the output is more useful
  as a durable Vault note and avoids re-expansion/filler later in the pipeline.
- Source Brief becomes the stable v1 compiler interface, not a thin triage
  object.
- Artifact Bundle construction becomes more typed and more testable.
- Studio can still use verdicts and best-next-action fields for triage, while
  the Vault keeps richer reading and evidence sections.
- Prompt, Pydantic, Artifact Bundle, and template tests should converge on the
  same Source Brief contract.
