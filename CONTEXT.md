# Epistora Domain Context

## Core Domain

Epistora is a local-first Readwise-to-Obsidian intelligence compiler. It imports
articles, highlights, threads, and video transcripts from Readwise, compiles them
into structured Markdown source notes with summaries, watch/read verdicts, key
sections, takeaways, and next actions. The Obsidian vault is the durable product.
SQLite supports the runtime.

The architecture is provider-neutral internally. Readwise is the first polished
input. Raindrop, manual URLs, and other connectors are supported by the
architecture and will be expanded after the Readwise → Obsidian flow is excellent.

## Domain Terms

| Term | Definition |
|------|-----------|
| **Source** | A saved link (article, YouTube video, X thread, PDF, etc.) that enters the knowledge pipeline. Has a lifecycle: metadata-only → captured → briefed → deep-compiled. |
| **SourceType** | The kind of source: `article`, `youtube`, `x_thread`, `pdf`, `generic`, or `derived_work`. |
| **Source Content** | Normalized extracted evidence after fetch. Includes raw text, cleaned text, archived markdown, and extraction quality metadata. |
| **Source Brief** | The rich v1 LLM analysis of a Source. It is the stable compiler contract between Source Content and Artifact Bundle construction. Produces triage fields, reading fields, evidence fields, topic/entity/concept extraction, evidence limits, and type-specific fields such as watch/read verdicts or thread claims. |
| **Compiled Note** | The Markdown source note in `wiki/sources/` rendered from the Source Brief. Contains the verdict, overview, key ideas, takeaways, and next actions. |
| **Raw Capture** | The immutable evidence entrypoint in `raw/`. The original extracted text (article body, transcript, etc.) before LLM analysis. |
| **Artifact Bundle** | The canonical compiler output: source artifact, topic/entity/concept artifacts, relationship artifacts, and evidence references. |
| **Vault** | The local markdown knowledge base on disk. The durable product of the system. |
| **Read Model** | A derived SQLite database (`.system/state/read_model.db`) for retrieval. Rebuildable from vault files. |
| **Topic** | A thematic hub page in `wiki/topics/` that aggregates sources about a subject. Deferred to post-v1. |
| **Entity** | A named hub page in `wiki/entities/` for people, companies, tools. Deferred to post-v1. |
| **Concept** | An idea hub page in `wiki/concepts/` for mental models, patterns, techniques. Deferred to post-v1. |
| **Synthesis Note** | A candidate synthesized note in `wiki/synthesis/` produced by maintenance. Deferred to post-v1. |
| **Backend** | An LLM reasoning backend: `api` (direct OpenAI-compatible), `opencode` (CLI), `claude_code` (CLI), or `codex` (CLI). The backend router falls back through these in order. |
| **Studio** | The local web UI served by FastAPI at `/studio`. React + Vite, production assets in `studio/static/`. |
| **Provider** | An input connector that feeds sources into Epistora. Either an extracted-content provider (Readwise) or a link-only provider (Raindrop). |
| **Extracted Content Provider** | A provider that already gives Epistora the useful content body (text, highlights, transcripts). Readwise is the first. Epistora normalizes provider content directly into SourceContent without native URL fetching. |
| **Link-Only Provider** | A provider that mainly gives URLs and metadata. Raindrop is the first. Epistora needs fetchers/extractors to obtain SourceContent. |
| **Provider Content Mode** | `extracted_content` or `link_only`. Distinguishes how Epistora obtains SourceContent from a provider. Set per-connector. |

## AI Chat Terms (Deferred to post-v1)

All chat features are architecturally supported but deferred from the v1 product path.

| Term | Definition |
|------|-----------|
| **Sidebar Chat** | A contextual chat panel attached to a source detail view. Uses simple context injection (compiled note + raw capture) with no tools. Ephemeral per-source in-memory history. |
| **Broad Chat** | A dedicated Chat page for vault-wide conversations. Uses an agent with tools that can search, read, and navigate the entire knowledge base. Persistent multi-conversation history stored in SQLite. |
| **Chat Conversation** | A persistent thread of messages in the Broad Chat. Auto-titled from the first message. Stored in SQLite with full message history. |
| **Chat Agent** | The LLM agent in the Broad Chat that has read-only tools to navigate the vault: search sources, read sources, read vault notes, list sources, browse knowledge graph, and get source relationships. |
| **Agent Tool** | A callable function the Broad Chat agent can invoke: `search_sources`, `read_source`, `read_note`, `list_sources`, `list_topics`/`list_entities`/`list_concepts`, `get_source_relations`. |
| **Chat Backend** | The LLM backend used for chat. Follows the same backend fallback chain as the rest of the system (api → opencode → claude_code → codex). Configurable via Settings UI (overrides env vars). |
| **Chat Streaming** | SSE-based token streaming from FastAPI to the frontend. Available when using the direct API backend. CLI backends return non-streaming responses with a UI indicator. |
