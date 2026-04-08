# Epistora Vault Operating Manual

This file defines how Epistora maintains the vault. Treat it as the standing
operating manual for both automated agents and human editors.

## Core Principle

The vault has three layers with different jobs:

- `inbox/raw/` is the immutable evidence layer.
- `wiki/` is the maintained, cumulative knowledge layer.
- `outputs/` is the scratchpad and delivery layer.

Never collapse these layers into one file.

## Folder Responsibilities

### `inbox/raw/`

Use this layer for preserved source material only.

- `articles/` stores readable article archives in clean markdown.
- `videos/` stores transcript captures and video metadata.
- `threads/` stores raw X/thread captures.
- `pdfs/` stores extracted PDF text.
- `misc/` stores raw captures for sources that do not fit the main types.

Rules:

- Raw captures are immutable once written.
- Raw captures may contain metadata headers, but not AI-written summaries.
- If extraction is weak, say so plainly inside the raw capture instead of faking completeness.
- Preserve the best available evidence even when it is partial.

### `wiki/`

Use this layer for maintained knowledge artifacts.

- `sources/` contains compiled source notes.
- `topics/` contains broad subject pages that accumulate over time.
- `entities/` contains pages for people, companies, tools, publications, and other named things.
- `concepts/` contains definitions, patterns, and reusable ideas.
- `synthesis/` contains durable cross-source artifacts.
- `indexes/` contains navigation maps for the vault.
- `logs/` contains append-only operational history and lint reports.

Rules:

- Source notes should link back to the raw archive.
- Topic, entity, and concept pages should be updated instead of duplicated.
- Prefer cumulative updates over rewriting from scratch.
- Use `[[wikilinks]]` for internal references.
- Surface contradictions, uncertainty, and gaps instead of smoothing them over.

### `outputs/`

Use this layer for user-requested or temporary artifacts.

- Query answers and reports belong here first.
- If an output becomes generally useful, promote it into `wiki/synthesis/`.
- Do not treat outputs as canonical wiki pages unless they are promoted.

## What Each Note Type Should Contain

### Raw Capture

- Original source title and URL
- Extraction provenance
- Preserved source material only
- Explicit note when the capture is partial, metadata-only, or failed

### Source Note

- Short summary
- `5-Minute Read`
- Detailed reading note
- Key ideas
- Detailed outline
- Important examples or stories
- Actionable takeaways
- Notable quotes only when directly supported
- Why it matters
- Who it is useful for
- Whether the original is still worth reading or watching
- Links to related topics, entities, concepts, and the raw archive
- Open questions and capture limitations

### Topic Page

- Topic summary
- What is saved on this topic
- Related concepts and entities
- Recurring patterns across sources
- Conflicting viewpoints or unresolved tensions
- Gaps in understanding
- Suggested next reading or watching

### Entity Page

- What the entity is
- Why it keeps showing up in the vault
- Recurring contexts or roles
- Related concepts
- Mentioned-in source list
- Open questions

### Concept Page

- Working definition
- Why it matters
- Where it appears
- Related concepts
- Examples from saved sources
- Open questions, ambiguities, or competing definitions

### Synthesis Note

- Durable claim or synthesis
- Clear source basis
- Cross-source patterns
- Conflicts or tensions
- Reusable takeaways or next steps

## Knowledge Maintenance Rules

- Raw sources are the evidence layer. Do not overwrite them with improved prose.
- The wiki layer should become more coherent as more sources arrive.
- Prefer linking an existing page over inventing near-duplicate pages.
- When pages disagree, record the disagreement explicitly.
- When extraction quality is low, downgrade confidence and say what is missing.
- Indexes should help an agent orient before reading everything.
- Logs should make it obvious what changed and when.

## Handling Weak Extraction

If extraction is `metadata_only`, `partial`, or failed:

- keep the raw capture anyway
- mark the limitation in the source note
- avoid direct quotes unless they are clearly supported
- avoid over-specific claims
- leave follow-up questions for later re-ingest or manual review

## Filing Valuable Answers Back Into The Vault

If a generated answer or report becomes generally useful:

- promote it into `wiki/synthesis/`
- keep the source basis explicit
- rewrite it as a durable note, not a chat reply transcript
- connect it to the relevant topics, entities, and concepts

## Internal Consistency Checklist

Before considering the vault healthy, ensure:

- every source note has a raw archive link
- topic, entity, and concept pages receive updates instead of duplicates
- indexes rebuild cleanly
- logs reflect the latest ingest/lint runs
- contradictions and missing pages are surfaced
- note titles and links remain stable enough for future automation
