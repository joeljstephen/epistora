# Epistora Vault — Agent Operating Manual

This file is the operating manual for agents (Claude Code, OpenCode, or any
filesystem-capable LLM agent) working with this knowledge vault. Read it first,
then follow the navigation sequence below.

---

## Three-Layer Model

This vault has three layers with strictly different jobs. Never collapse them.

### Layer 1: Immutable Evidence — `inbox/raw/`

- Contains the original captured source material: article archives, video
  transcripts, thread captures, PDF extractions.
- Raw captures are **immutable**. Never edit them.
- Each file has YAML frontmatter with `type: raw`, `immutable: true`,
  `extraction_quality`, and `source_url`.
- Raw captures may be partial or metadata-only. Check `extraction_quality`.

### Layer 2: Maintained Knowledge — `wiki/`

- `wiki/sources/` — Compiled source notes (one per ingested source).
  These are the **primary evidence** for answering questions.
- `wiki/topics/` — Topic hub pages that accumulate across sources.
- `wiki/entities/` — Pages for named entities (people, companies, tools).
- `wiki/concepts/` — Pages for reusable ideas and definitions.
- `wiki/synthesis/` — Durable cross-source synthesis notes.
- `wiki/indexes/` — Navigation maps (START_HERE, INDEX, TOPICS, ENTITIES,
  CONCEPTS, QUERY_PROTOCOL).
- `wiki/logs/` — Append-only operational logs.

### Layer 3: Scratch / Delivery — `outputs/`

- Saved query answers, digests, reports.
- If an output becomes generally useful, promote it into `wiki/synthesis/`.
- Outputs are not canonical wiki pages unless promoted.

---

## Agent Navigation Sequence

When answering a knowledge question from this vault, follow this sequence
exactly:

### Step 1: Orient

Read these files first:

1. `AGENTS.md` (this file)
2. `wiki/indexes/START_HERE.md` — vault orientation map
3. `wiki/indexes/QUERY_PROTOCOL.md` — standard query procedure

### Step 2: Identify the Question Type

Classify the question into one of these types:

- **Topic overview** — broad question about a subject
- **Comparison** — how do X and Y relate or differ
- **Evidence lookup** — what does the vault say about a specific claim
- **Gap analysis** — what is missing or uncertain
- **Entity profile** — what do I know about a specific person/company/tool
- **Learning path** — what should I read/watch next on a subject

### Step 3: Consult Indexes

Read the relevant index files to find candidate notes:

- `wiki/indexes/INDEX.md` — full vault overview with stats and recent sources
- `wiki/indexes/TOPICS.md` — topic pages with source counts
- `wiki/indexes/ENTITIES.md` — entity pages with types and source counts
- `wiki/indexes/CONCEPTS.md` — concept pages with source counts

### Step 4: Read Frontmatter First

Before reading the full body of any note, inspect its YAML frontmatter. This
tells you:

- `type` — note type (source, topic, entity, concept, synthesis, raw)
- `topics`, `entities`, `concepts` — what this note connects to
- `extraction_quality` — how reliable the evidence is
- `raw_capture_path` — where the underlying raw evidence lives
- `source_url` — the original source
- `tags` — user-provided tags

Use frontmatter to decide whether a note is relevant before investing time
reading its full body.

### Step 5: Read Hub Pages

For topic/entity/concept questions, read the relevant hub page. These pages
accumulate knowledge across sources and serve as routing hubs via `[[wikilinks]]`.

### Step 6: Read Source Notes

Source notes (`wiki/sources/`) are the **primary evidence** for grounded
answers. Each source note contains:

- Short summary and 5-Minute Read
- Detailed reading note
- Key ideas, outline, examples, takeaways, quotes
- Coverage & limits section
- Related notes with wikilinks
- Open questions

### Step 7: Escalate to Raw Captures Only When Needed

Read raw captures (`inbox/raw/`) only when:

- The source note's `extraction_quality` is `partial`, `metadata_only`, or
  `failed`
- You need exact evidence or exact wording
- The compiled source note appears too compressed for the question
- You suspect the compilation missed something important

Do NOT read raw captures by default. They are large and often redundant with
the compiled source note.

### Step 8: Check Synthesis Notes

If `wiki/synthesis/` contains relevant notes, read them. These represent
prior cross-source work that may answer or partially answer the question.

### Step 9: Ignore `.system/` for Knowledge Answers

The `.system/` directory contains internal state, caches, and manifests. It is
not knowledge content. Do not read it when answering questions.

---

## Answer Structure

Structure knowledge answers using these sections:

```markdown
## Direct Findings
- Grounded claims with explicit evidence sources

## Cross-Source Synthesis
- Patterns, agreements, or tensions across multiple sources

## Gaps / Open Questions
- What the vault does not cover or where evidence is weak

## Relevant Notes to Read Next
- List of specific note paths or [[wikilinks]]
```

### Answer Rules

1. **Ground every claim** in a specific source note or raw capture. If you
   cannot find supporting evidence, say so explicitly.
2. **Surface contradictions** between sources instead of smoothing them away.
3. **Note uncertainty** when extraction quality is weak or evidence is partial.
4. **Do not invent evidence.** If the vault does not contain something, state
   that it is missing.
5. **Reference notes by path or wikilink** so the reader can follow up.
6. **Distinguish direct findings from synthesis.** Make clear what the sources
   say versus what you are inferring.

---

## Evidence Trust Hierarchy

Trust sources in this order:

1. **Compiled source notes** (`wiki/sources/`) — primary evidence, already
   structured and grounded
2. **Synthesis notes** (`wiki/synthesis/`) — prior cross-source work, check
   source basis
3. **Hub pages** (`wiki/topics/`, `wiki/entities/`, `wiki/concepts/`) — good
   for routing, may contain accumulated patterns
4. **Raw captures** (`inbox/raw/`) — use only for escalation or verification

### Extraction Quality Signals

When a source note has:

- `extraction_quality: full` — strong evidence, reliable for direct claims
- `extraction_quality: mostly_full` — good but may have minor gaps
- `extraction_quality: partial` — significant gaps, avoid over-specific claims
- `extraction_quality: metadata_only` — very limited, treat as weak evidence
- `extraction_quality: failed` — almost no useful content, note the failure

---

## Handling Weak Extraction

When a source note indicates weak extraction:

- Do not make specific claims that the raw evidence does not support
- Flag the limitation explicitly in your answer
- Suggest re-ingesting the source if exact evidence matters
- Use the raw capture as supplementary evidence if needed
- Leave follow-up questions for the user

---

## Filing Valuable Answers Back

If you produce a particularly valuable answer:

1. Save it to `outputs/answers/` first
2. If it is generally useful and durable, promote it to `wiki/synthesis/`
3. Connect the synthesis note to relevant topics, entities, and concepts
4. Keep the source basis explicit

---

## Using Wikilinks for Graph Navigation

All internal vault references use `[[wikilinks]]`. Use these to:

- Navigate from a topic page to its source notes
- Navigate from a source note to related concepts and entities
- Navigate from an entity to sources that mention it
- Follow the knowledge graph without reading every file

When a note contains `[[Some Topic]]`, look for `wiki/topics/some-topic.md`.

---

## Quick Reference: File Locations

| Content Type | Location | Note Type |
|---|---|---|
| Raw article archive | `inbox/raw/articles/` | raw |
| Raw video transcript | `inbox/raw/videos/` | raw |
| Raw thread capture | `inbox/raw/threads/` | raw |
| Raw PDF text | `inbox/raw/pdfs/` | raw |
| Source note (article) | `wiki/sources/articles/` | source |
| Source note (video) | `wiki/sources/videos/` | source |
| Source note (thread) | `wiki/sources/threads/` | source |
| Topic page | `wiki/topics/` | topic |
| Entity page | `wiki/entities/` | entity |
| Concept page | `wiki/concepts/` | concept |
| Synthesis note | `wiki/synthesis/` | synthesis |
| Vault index | `wiki/indexes/INDEX.md` | index |
| Navigation hub | `wiki/indexes/START_HERE.md` | index |
| Query procedure | `wiki/indexes/QUERY_PROTOCOL.md` | index |
| Saved answers | `outputs/answers/` | output |

---

## Vault Maintenance Conventions

- Raw sources are immutable evidence. Do not overwrite them.
- The wiki layer should become more coherent over time as sources accumulate.
- Prefer linking an existing page over creating near-duplicates.
- When pages disagree, record the disagreement explicitly.
- Indexes are auto-generated. Rebuild with `epistora rebuild-indexes`.
- Logs are append-only and track all ingest/lint operations.
