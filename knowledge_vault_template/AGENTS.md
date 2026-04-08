# Epistora Vault Operating Manual

This file defines how Epistora maintains the vault. Treat it as the standing
operating manual for both automated agents and human editors.

## Core Principle

The vault has three layers with different jobs:

- `inbox/raw/` is the immutable evidence layer.
- `wiki/` is the maintained, cumulative knowledge layer.
- `outputs/` is the scratchpad and delivery layer.

Never collapse these layers into one file.

Think in the Karpathy-style wiki pattern:

- ingest adds immutable evidence
- the wiki compiles and cross-links durable understanding
- indexes and logs help an agent navigate before re-reading everything
- valuable outputs can be promoted into synthesis notes
- contradictions, thin spots, and missing pages should become visible over time
- the vault should compound instead of rediscovering the same ideas each run

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
- For Raindrop bookmarks tagged `article`, preserve the readable article body as clean markdown here.
- For YouTube sources, preserve the transcript or metadata capture here even if the compiled note later becomes much richer.
- Do not mix compiled commentary into the archived article or transcript body.

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
- Use the wiki layer to answer: what is worth remembering, how does it connect, and what still looks unresolved?
- Keep source notes grounded in one source; use synthesis notes for multi-source claims.
- Prefer stable page names over source-specific phrasing that will fragment the graph later.

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
- No AI summary paragraphs mixed into the evidence body

### Source Note

- Short summary
- `5-Minute Read`
- Detailed reading note
- Coverage / limitations
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

For video source notes specifically:

- include transcript availability, caption type, extraction source, and transcript quality
- include a detailed article-style reading note that can often substitute for first-pass watching
- explicitly answer whether the original video is still worth watching

For article source notes specifically:

- keep the preserved readable article body in `inbox/raw/articles/`
- keep the wiki source note interpretive and linked, not a duplicate of the raw article text

### Topic Page

- Topic summary
- What is saved on this topic
- Related concepts and entities
- Recurring patterns across sources
- Conflicting viewpoints or unresolved tensions
- Gaps in understanding
- Active questions
- Suggested next reading or watching

### Entity Page

- What the entity is
- Why it keeps showing up in the vault
- Recurring contexts or roles
- Why it matters
- Related concepts
- Mentioned-in source list
- Open questions

### Concept Page

- Working definition
- Why it matters
- Where it appears
- Related concepts
- Examples from saved sources
- Competing definitions, edge cases, or ambiguities
- Open questions, ambiguities, or competing definitions

### Synthesis Note

- Durable claim or synthesis
- Clear source basis
- Cross-source patterns
- Conflicts or tensions
- Reusable takeaways or next steps

Use synthesis notes for:

- answers that are repeatedly useful
- cross-source comparisons
- named theses or frameworks that deserve a durable home in the wiki

## Knowledge Maintenance Rules

- Raw sources are the evidence layer. Do not overwrite them with improved prose.
- The wiki layer should become more coherent as more sources arrive.
- Prefer linking an existing page over inventing near-duplicate pages.
- When pages disagree, record the disagreement explicitly.
- When extraction quality is low, downgrade confidence and say what is missing.
- Indexes should help an agent orient before reading everything.
- Logs should make it obvious what changed and when.
- If a source note has no meaningful links into topics, entities, or concepts, that is a maintenance smell.
- If the raw layer captured useful evidence but the wiki page is thin, improve the compiled layer rather than rewriting the raw file.

## Handling Weak Extraction

If extraction is `metadata_only`, `partial`, or failed:

- keep the raw capture anyway
- mark the limitation in the source note
- avoid direct quotes unless they are clearly supported
- avoid over-specific claims
- leave follow-up questions for later re-ingest or manual review
- make it obvious whether the limitation came from missing transcript/text, weak parsing, or restricted access

## Filing Valuable Answers Back Into The Vault

If a generated answer or report becomes generally useful:

- promote it into `wiki/synthesis/`
- keep the source basis explicit
- rewrite it as a durable note, not a chat reply transcript
- connect it to the relevant topics, entities, and concepts
- leave transient or one-off outputs in `outputs/`

## Internal Consistency Checklist

Before considering the vault healthy, ensure:

- every source note has a raw archive link
- raw article archives and raw transcripts remain separate from compiled source notes
- topic, entity, and concept pages receive updates instead of duplicates
- indexes rebuild cleanly
- logs reflect the latest ingest/lint runs
- contradictions and missing pages are surfaced
- note titles and links remain stable enough for future automation
