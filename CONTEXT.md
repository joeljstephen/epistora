# Epistora Domain Context

## Core Domain

Epistora is a local-first personal knowledge compiler. Saved links are fetched,
compiled by LLM analysis into canonical artifacts, and published as a markdown
knowledge vault. The vault is the durable product. SQLite supports the runtime.

## Domain Terms

| Term | Definition |
|------|-----------|
| **Source** | A saved link (article, YouTube video, X thread, PDF, etc.) that enters the knowledge pipeline. Has a lifecycle: metadata-only → captured → briefed → deep-compiled. |
| **SourceType** | The kind of source: `article`, `youtube`, `x_thread`, `pdf`, `generic`, or `derived_work`. |
| **Source Content** | Normalized extracted evidence after fetch. Includes raw text, cleaned text, archived markdown, and extraction quality metadata. |
| **Compiled Note** | The LLM-analyzed source note in `wiki/sources/`. Contains summary, key ideas, topics, entities, concepts, and structured reading guidance. |
| **Raw Capture** | The immutable evidence entrypoint in `raw/`. The original extracted text (article body, transcript, etc.) before LLM analysis. |
| **Artifact Bundle** | The canonical compiler output: source artifact, topic/entity/concept artifacts, relationship artifacts, and evidence references. |
| **Vault** | The local markdown knowledge base on disk. The durable product of the system. |
| **Read Model** | A derived SQLite database (`.system/state/read_model.db`) for retrieval. Rebuildable from vault files. |
| **Topic** | A thematic hub page in `wiki/topics/` that aggregates sources about a subject. |
| **Entity** | A named hub page in `wiki/entities/` for people, companies, tools. |
| **Concept** | An idea hub page in `wiki/concepts/` for mental models, patterns, techniques. |
| **Synthesis Note** | A candidate synthesized note in `wiki/synthesis/` produced by maintenance. |
| **Backend** | An LLM reasoning backend: `api` (direct OpenAI-compatible), `opencode` (CLI), `claude_code` (CLI), or `codex` (CLI). The backend router falls back through these in order. |
| **Studio** | The local web UI served by FastAPI at `/studio`. React + Vite, production assets in `studio/static/`. |

## AI Chat Terms

| Term | Definition |
|------|-----------|
| **Sidebar Chat** | A contextual chat panel attached to a source detail view. Uses simple context injection (compiled note + raw capture) with no tools. Ephemeral per-source in-memory history. |
| **Broad Chat** | A dedicated Chat page for vault-wide conversations. Uses an agent with tools that can search, read, and navigate the entire knowledge base. Persistent multi-conversation history stored in SQLite. |
| **Chat Conversation** | A persistent thread of messages in the Broad Chat. Auto-titled from the first message. Stored in SQLite with full message history. |
| **Chat Agent** | The LLM agent in the Broad Chat that has read-only tools to navigate the vault: search sources, read sources, read vault notes, list sources, browse knowledge graph, and get source relationships. |
| **Agent Tool** | A callable function the Broad Chat agent can invoke: `search_sources`, `read_source`, `read_note`, `list_sources`, `list_topics`/`list_entities`/`list_concepts`, `get_source_relations`. |
| **Chat Backend** | The LLM backend used for chat. Follows the same backend fallback chain as the rest of the system (api → opencode → claude_code → codex). Configurable via Settings UI (overrides env vars). |
| **Chat Streaming** | SSE-based token streaming from FastAPI to the frontend. Available when using the direct API backend. CLI backends return non-streaming responses with a UI indicator. |
