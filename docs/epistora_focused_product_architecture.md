# Epistora Focused Product Architecture

**Status:** Proposed direction  
**Purpose:** Refocus Epistora around a smaller, stronger first product while keeping the existing modular architecture open for future connectors, sinks, and intelligence backends.

---

## 1. Summary

Epistora should remain a **provider-neutral local-first knowledge compiler**, but the first polished product path should be much narrower:

```text
Readwise → Epistora Intelligence Compiler → Obsidian / Markdown LLM Wiki
```

This means Epistora should **not** remove the connector system, plugin system, backend router, sink abstraction, source catalog, or vault model. Those are good architectural seams.

The simplification should happen at the **product workflow level**:

- Readwise becomes the first-class input.
- Obsidian/Markdown vault remains the first-class sink.
- Source briefing becomes the main intelligence job.
- API/OpenCode/Claude Code/Codex remain selectable intelligence backends.
- Raindrop stays in the architecture, but it is no longer the default v1 path.
- Topic bundles, daily digests, broad chat, MCP, OpenClaw, and deep maintenance move out of the basic product.

The focused v1 product should answer one clear promise:

> Epistora imports already-extracted Readwise content and turns it into clean, useful, agent-readable Markdown learning notes in Obsidian.

---

## 2. Current Architecture Assessment

The current architecture is stronger than the current product scope.

The good foundations are:

- `SourceItem → SourceContent → ArtifactBundle → configured sinks`.
- The Markdown vault remains the durable product.
- SQLite supports runtime state but does not replace the vault.
- The source catalog separates library identity from processed/published state.
- Provider references allow a single source to be known through multiple providers.
- The backend router already supports API, OpenCode, Claude Code, and Codex.
- The sink system keeps Markdown and JSON publishing separate from the compiler.
- The plugin loader allows future provider/backend/sink/prompt-pack extensions.

The main problem is not the architecture. The main problem is that too many product workflows have become “v1” at the same time:

- Raindrop extraction
- direct URL ingest
- article extraction
- YouTube extraction
- X/Twitter extraction
- PDF extraction
- topic/entity/concept pages
- reader views
- topic bundles
- daily/weekly digests
- Local Studio
- broad search
- query
- maintenance
- plugin support
- multi-backend support
- future chat/MCP/OpenClaw ideas

The product needs a smaller happy path.

---

## 3. Focused Product Identity

### New v1 identity

Epistora v1 should be:

> A local-first Readwise-to-Obsidian intelligence compiler.

Expanded version:

> Epistora imports your Readwise articles, highlights, threads, and video transcripts, then compiles them into beautiful Markdown source notes with summaries, watch/read verdicts, key sections, takeaways, and next actions.

This keeps the Karpathy-style LLM wiki idea, but grounds it in a simple first workflow:

```text
Captured knowledge → clean source notes → agent-readable Markdown vault
```

### What Epistora is not in v1

Epistora v1 should not present itself as:

- a full second-brain automation system
- a generic n8n replacement
- a full AI chat product
- a full Raindrop extraction engine
- a complete research synthesis engine
- a multi-sink publishing platform
- an MCP/OpenClaw automation layer

Those may come later. They should not define the first usable product.

---

## 4. Core v1 Workflow

The first polished loop should be:

```text
1. User saves content in Readwise.
2. Epistora syncs new Readwise items.
3. Epistora creates or updates source catalog rows.
4. Epistora stores Readwise-provided content as raw evidence.
5. Epistora runs a source brief intelligence job.
6. Epistora publishes a Markdown source note into the Obsidian vault.
7. User opens the note and immediately knows:
   - what the source is about
   - whether it is worth reading or watching
   - which sections matter
   - what the key ideas are
   - what to do next
   - how it might connect to the vault
```

The first version should optimize this loop until it feels excellent.

---

## 5. Provider-Neutral, Readwise-First

The architecture should stay provider-neutral, but the implementation should be Readwise-first.

### Internal abstraction

Do not make the core model `ReadwiseItem → ReadwiseNote`.

Use:

```text
ProviderItem → SourceRecord → SourceContent → SourceArtifact → MarkdownNote
```

Readwise is just the first fully polished provider.

### Two kinds of providers

Epistora should explicitly distinguish between two input provider types.

#### 5.1 Extracted content providers

These providers already give Epistora the useful content body.

Examples:

- Readwise Reader
- future full-text sources
- imported local markdown files
- exported article/highlight archives

For these providers, Epistora should not fetch the URL first. It should normalize provider content directly into `SourceContent`.

```text
Readwise item
  → provider metadata
  → extracted text / highlights / transcript
  → SourceContent
```

#### 5.2 Link-only providers

These providers mainly give Epistora URLs and metadata.

Examples:

- Raindrop
- browser bookmarks
- manual URL list
- RSS feeds
- Telegram links

For these providers, Epistora needs fetchers/extractors.

```text
Raindrop item
  → URL metadata
  → fetcher dispatch
  → article/youtube/x/pdf extraction
  → SourceContent
```

This distinction is important because Readwise should not be forced through the same path as Raindrop.

---

## 6. What v1 Should Fully Support

### Inputs

First-class:

- Readwise

Allowed but not the main path:

- manual URL
- Raindrop metadata/import foundation

Deferred as polished workflows:

- Raindrop full extraction
- RSS
- Telegram
- local folder watch
- browser extension
- Notion import

### Source types

First-class through Readwise:

- article
- YouTube/video transcript
- X/Twitter thread
- highlight-heavy saved document

Best-effort or later:

- PDF
- podcast/audio
- arbitrary webpage extraction outside Readwise

### Sink

First-class:

- Markdown vault / Obsidian

Keep but de-emphasize:

- JSON export as machine-facing/debug/export artifact

Deferred:

- Notion
- static site
- Readwise write-back

### Intelligence backends

Keep the existing backend router idea, but simplify the UI.

Supported:

- API backend
- OpenCode
- Claude Code
- Codex

The user-facing choice should be:

```text
Intelligence backend:
- API recommended
- OpenCode
- Claude Code
- Codex
```

Advanced per-task routing can stay in `.env`, but the main product should not force the user to understand it.

### Studio

Keep only the useful control panel pieces:

- Library
- Source Detail
- Queue / Jobs
- Search
- Settings

Defer or hide:

- Knowledge browse
- Topic bundles UI
- Outputs page
- recipes
- MCP status
- broad AI chat
- advanced customization

---

## 7. Intelligence Layer

The intelligence layer should be split into two concepts:

```text
Intelligence Jobs
Intelligence Backends
```

### 7.1 Intelligence Jobs

These are the tasks Epistora performs.

For v1, keep only:

```text
source_brief
video_watch_guide
markdown_publish
```

Later:

```text
article_reading_guide
thread_digest
wiki_link_suggestions
topic_bundle
daily_digest
weekly_digest
vault_chat
maintenance_refactor
```

### 7.2 Intelligence Backends

These are the engines that run intelligence jobs.

```text
api
opencode
claude_code
codex
```

The job should not know which backend runs it. It should say:

```text
I need a structured source brief from this SourceContent.
```

The backend router decides how to execute it.

---

## 8. Source Brief Compiler

This should become the heart of the v1 product.

### Role

The Source Brief Compiler turns provider evidence into a useful reading note.

```text
SourceContent → SourceBriefArtifact → Markdown source note
```

### Required fields

For every source:

```yaml
quick_brief: string
best_next_action: string
brief_status: ready | partial | failed
consume_recommendation: string
key_ideas: string[]
takeaways: string[]
important_terms: string[]
evidence_limits: string
```

For video/YouTube:

```yaml
watch_verdict: string
watch_verdict_reasoning: string
quick_section_guide: string
detailed_sections: string
signal_vs_filler: string
```

For articles:

```yaml
read_verdict: string
why_read_or_skip: string
key_sections: string
```

For X/Twitter threads:

```yaml
thread_summary: string
main_claims: string[]
useful_links_or_references: string[]
```

### What a good v1 YouTube note should answer

When a YouTube item comes from Readwise with transcript content, the generated note should answer:

- What is this video about?
- Is it worth watching?
- Is reading the transcript enough?
- What are the best sections?
- What are the key ideas?
- What is filler?
- What should I do next?
- What should I search or connect in my vault?

This directly solves the current personal pain: avoiding manual Gemini/ChatGPT prompts for every video transcript.

---

## 9. Karpathy LLM Wiki Scope

The Karpathy-style LLM wiki idea should stay as the long-term north star.

For v1, it should mean:

```text
A clean Markdown vault of source notes that humans and filesystem-capable agents can read directly.
```

Keep:

- `AGENTS.md`
- `wiki/sources/`
- `raw/`
- minimal indexes
- clear source note frontmatter
- stable paths
- agent-readable structure

Avoid in v1:

- auto-promoting every source into topic/entity/concept pages
- generating synthesis pages by default
- complex graph maintenance
- deep refactors
- daily/weekly compounding workflows

A strong v1 LLM wiki is not a giant auto-generated graph. It is a highly readable, consistent, searchable source-note corpus.

---

## 10. Proposed Simplified Runtime

### Current runtime

```text
SourceItem
  → SourceContent
  → ArtifactBundle
  → configured sinks
  → markdown vault / JSON export
  → read-model refresh
```

### Focused v1 runtime

```text
Readwise Provider Item
  → Source Catalog Row
  → Provider Reference
  → SourceContent from Readwise extracted content
  → Source Brief Compiler
  → SourceBriefArtifact
  → Markdown Vault Sink
  → Minimal Index / Search Refresh
```

### Future full runtime

```text
Any Provider
  → Source Catalog
  → Provider Content Normalizer or Fetcher
  → SourceContent
  → Intelligence Jobs
  → ArtifactBundle
  → Sinks
  → Read Model
  → Optional Studio / Agent / Plugin Surfaces
```

---

## 11. What to Keep

Keep these architecture seams:

```text
SourceConnector / ProviderConnector
SourceCatalogRepository
SourceProviderRef
SourceContent
ArtifactBundle
MarkdownVaultSink
BackendRouter
PluginRegistry
Prompt layering
Studio source catalog APIs
Read model
```

These are foundational, not bloat.

---

## 12. What to Hide or Defer

Move these out of v1:

```text
Raindrop full extraction as default workflow
native YouTube transcript extraction as default workflow
native X/Twitter extraction as default workflow
topic bundles
daily review digest
weekly review digest
broad chat
sidebar chat
MCP
OpenClaw plugin
deep maintenance
auto synthesis
advanced recipe builder
multiple polished sinks
complex budget UI
spaced repetition
```

Some of these can remain in code, but they should not be part of the main README, setup wizard, or product promise.

---

## 13. Codebase Direction

### 13.1 Add Readwise as the main connector

Add:

```text
app/connectors/readwise.py
```

It should implement the same connector protocol, but it should not behave like a simple link provider.

Recommended distinction:

```python
class ProviderContentMode(StrEnum):
    EXTRACTED_CONTENT = "extracted_content"
    LINK_ONLY = "link_only"
```

Readwise should be `EXTRACTED_CONTENT`.

Raindrop should be `LINK_ONLY`.

### 13.2 Extend settings

Add settings:

```text
READWISE_API_TOKEN
READWISE_SYNC_MODE
READWISE_INCLUDE_HIGHLIGHTS
READWISE_INCLUDE_FULL_TEXT
READWISE_INCLUDE_YOUTUBE_TRANSCRIPTS
```

Keep Raindrop settings, but do not make them the default first-run path.

### 13.3 Add Readwise setup commands

Add:

```bash
epistora connect readwise
epistora sync readwise --limit 10
epistora ingest latest --connector readwise
```

Long term, the default connector can be configurable:

```text
DEFAULT_INBOX_CONNECTOR=readwise
```

For your personal workflow, default it to Readwise.

### 13.4 Split provider import from source compilation

The pipeline should support this distinction:

```text
Import provider item
  → source catalog row
  → provider ref
  → raw provider evidence
```

and:

```text
Compile source
  → source brief
  → markdown note
```

This makes it possible to import a lot from Readwise without immediately spending model calls on everything.

### 13.5 Simplify publish behavior for v1

The Markdown sink currently writes raw captures, source notes, hub pages, indexes, and read model refresh.

For focused v1, make this behavior configurable:

```text
PUBLISH_SOURCE_NOTES=true
PUBLISH_RAW_CAPTURE=true
PUBLISH_HUB_PAGES=false by default
PUBLISH_SYNTHESIS=false by default
```

This keeps the existing power but avoids flooding the vault with auto-generated topic/entity/concept pages too early.

### 13.6 Update the setup wizard

The setup wizard should ask only:

```text
1. Where is your Obsidian vault?
2. Do you want to connect Readwise?
3. Which intelligence backend do you want?
4. Do you want automatic sync enabled?
```

Raindrop should appear under advanced connectors.

### 13.7 Update README

The README should stop leading with every feature.

New README opening:

```text
Epistora turns Readwise saves into an Obsidian-ready LLM wiki.

It imports articles, highlights, threads, and video transcripts from Readwise,
then compiles them into structured Markdown source notes with summaries,
watch/read verdicts, key sections, takeaways, and next actions.
```

Then add a small architecture note:

```text
Epistora is provider-neutral internally. Readwise is the first polished input.
Raindrop, manual URLs, and other connectors are supported by the architecture
and will be expanded after the Readwise → Obsidian flow is excellent.
```

---

## 14. Simplified CLI Surface

### Primary commands

```bash
epistora setup
epistora connect readwise
epistora sync readwise --limit 10
epistora brief pending --limit 5
epistora studio
epistora status
epistora doctor
```

### Secondary commands

```bash
epistora ingest url <url>
epistora connect raindrop
epistora sync raindrop --limit 10
epistora backend setup
epistora vault use <path>
```

### Hidden or advanced for now

```bash
epistora topic-bundle
epistora review daily
epistora review weekly
epistora automation run-personal-learning
epistora lint
epistora automation maintain
```

They do not have to be deleted. They just should not define the core product path.

---

## 15. Simplified Studio Surface

### Keep

Library:

- all Readwise items
- imported
- brief ready
- needs attention
- videos
- articles
- threads

Source detail:

- compiled note
- raw Readwise evidence
- metadata
- jobs

Queue:

- pending brief jobs
- failed jobs
- completed jobs

Search:

- source catalog search
- compiled note search

Settings:

- vault path
- Readwise connection
- backend choice
- sync options

### Hide for now

- Knowledge browse
- topic bundle outputs
- daily/weekly reviews
- recipes
- MCP
- broad AI chat
- complex budget/cost dashboards

---

## 16. Minimal Data Model for the Focused Flow

### Source catalog

Keep:

```text
source_uid
primary_url
title
source_type
provider_snapshot
metadata_status
content_status
brief_status
output_status
last_seen_at
created_at
updated_at
```

### Provider refs

Keep:

```text
source_uid
provider
provider_external_id
provider_url
saved_at
provider_metadata_json
```

### Processing jobs

Keep:

```text
job_id
source_uid
job_type
status
backend
requested_by
started_at
finished_at
error_message
```

Recommended v1 job types:

```text
import_readwise_item
compile_source_brief
publish_markdown
```

Later job types:

```text
fetch_url_content
deep_compile
topic_bundle
daily_digest
weekly_digest
vault_maintenance
```

---

## 17. Roadmap

### Phase 0 — Refocus docs and defaults

- Rewrite README around Readwise → Obsidian.
- Add this focused architecture doc.
- Make Readwise the primary planned connector.
- Move topic bundles, digests, chat, MCP, OpenClaw, and deep maintenance to later phases.
- Keep all architecture seams, but simplify product language.

### Phase 1 — Readwise import foundation

- Add Readwise connector.
- Store Readwise provider refs.
- Normalize Readwise items into source catalog rows.
- Store raw Readwise evidence.
- Avoid native fetching for Readwise items unless explicitly requested.
- Add `epistora connect readwise`.
- Add `epistora sync readwise`.

### Phase 2 — Source Brief Compiler

- Add a focused source brief job.
- Add video/watch guide prompt.
- Add article/read guide prompt.
- Write source notes to Obsidian.
- Preserve evidence limits and transcript/source quality.
- Make source notes excellent before adding larger synthesis features.

### Phase 3 — Focused Studio

- Tune Library for Readwise workflow.
- Add “Create brief” and “Rebuild note” actions.
- Add source detail reader for compiled note and raw evidence.
- Add clear job status.
- Keep Settings simple.

### Phase 4 — Reintroduce Raindrop as link-only provider

- Keep Raindrop metadata import.
- Improve native article extraction.
- Improve native YouTube transcript extraction.
- Improve native X/thread extraction.
- Only then make Raindrop a first-class input again.

### Phase 5 — LLM wiki growth

- Add wiki link suggestions.
- Add optional topic/entity/concept hubs.
- Add synthesis candidates.
- Add agent-friendly query workflows.
- Add topic bundles and digests after the source corpus is strong.

### Phase 6 — Ecosystem

- OpenClaw plugin.
- MCP.
- additional sinks.
- additional connectors.
- advanced automation.

---

## 18. Success Criteria

The v1 product is successful when:

- A new Readwise item becomes a useful Obsidian note with minimal effort.
- A saved YouTube video produces a clear “watch or skip” guide.
- A saved article produces a clear “read or skip” guide.
- Raw evidence is preserved and easy to inspect.
- Notes are readable by both humans and coding/LLM agents.
- The user can choose API/OpenCode/Claude Code/Codex without changing the source workflow.
- Raindrop remains possible later, but does not slow the Readwise flow.
- The product can be explained in one sentence.

One-sentence test:

> Epistora turns Readwise saves into a local Obsidian LLM wiki.

If a feature does not support that sentence, it should not be in the first product path.

---

## 19. Recommended Next Engineering Tasks

1. Add this document under `docs/FOCUSED_PRODUCT_ARCHITECTURE.md`.
2. Rewrite `README.md` around the Readwise-first product promise.
3. Add `READWISE_*` settings.
4. Add `app/connectors/readwise.py`.
5. Add provider content mode: `extracted_content` vs `link_only`.
6. Add `connect readwise` CLI command.
7. Add `sync readwise` CLI command.
8. Add a source brief job that can run without native URL fetching.
9. Make Markdown source notes the only default published knowledge artifact.
10. Hide/de-emphasize topic bundles, daily/weekly review, broad chat, and MCP from the first product surface.

---

## 20. Final Direction

Do not shrink Epistora by deleting its architecture.

Shrink Epistora by narrowing the first product path.

The right direction is:

```text
Provider-neutral architecture.
Readwise-first implementation.
Obsidian-first sink.
Source-brief-first intelligence.
Agent-readable Markdown as the durable product.
```

This preserves the future while making the present buildable.
