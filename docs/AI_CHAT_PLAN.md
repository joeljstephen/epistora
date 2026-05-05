# AI Chat Implementation Plan

Status: agreed direction, pending implementation.

## Overview

Add two AI chat surfaces to Epistora Studio: a **Sidebar Chat** for contextual
per-source Q&A and a **Broad Chat** page for vault-wide agent-driven
conversations. The Broad Chat exposes the same navigational power that developers
get by pointing opencode at the vault, but through a web UI for non-dev users.

## Resolved Decisions

### D1: Two separate chat surfaces

The sidebar chat and the broad chat are independent UI surfaces in separate
locations:

- **Sidebar Chat** appears as a slide-in panel from the right on the source
  detail view. Opened via a "Chat" button. Per-source in-memory message history
  (lost on page refresh). No tools — pure context injection.
- **Broad Chat** is a new **"Chat"** tab in the main Studio navigation
  (alongside Library, Knowledge, Search, Queue, Settings). Persistent
  multi-conversation history stored in SQLite. Agent with read-only tools.

Rationale: the sidebar is inherently contextual to what you're viewing. The
broad chat is a different mental model. Merging them creates UX confusion about
scope.

### D2: Sidebar chat uses context injection

The sidebar chat injects the current source's **compiled note** (in full) and
**raw capture** (truncated to ~4K tokens) into the system prompt. No tools, no
retrieval. The LLM answers questions about that specific source.

Context management: the compiled note is already condensed by the ingest
pipeline (it's the main analysis output). The raw capture is supplementary — it
handles specific questions like "what exact phrasing did they use." Truncating
the raw capture keeps total context within reasonable bounds.

### D3: Broad chat uses an agent with read-only tools

The broad chat agent has six tools for vault navigation:

| Tool | Purpose |
|---|---|
| `search_sources(query, filters?)` | Find sources by keyword/type/status |
| `read_source(source_id)` | Get compiled note + raw capture for a source |
| `read_note(path)` | Read any vault markdown file |
| `list_sources(filters?)` | List/filter sources by type, tag, date, topic |
| `list_topics()` / `list_entities()` / `list_concepts()` | Browse knowledge graph |
| `get_source_relations(source_id)` | Find connected sources via edges |

All tools are read-only. The agent cannot modify the vault, ingest URLs, or
trigger processing. It is a knowledge assistant, not a write interface.

This mirrors the opencode experience: the agent navigates the vault filesystem,
reads files, follows links, and builds answers iteratively.

### D4: Vercel AI SDK + FastAPI SSE streaming

**Frontend:** Vercel AI SDK (`ai` npm package) provides React hooks (`useChat`)
that handle streaming message state, auto-scroll, submit handling, and
intermediate step rendering. Minimal custom code.

**Backend:** FastAPI endpoints return `StreamingResponse` with Server-Sent Events
(SSE). The existing `DirectApiBackend` (which uses `langchain_openai.ChatOpenAI`)
streams tokens through the SSE response. For the agent, LangChain's
`.bind_tools()` with streaming handles multi-step tool-call loops.

**Why not LangServe or full LangChain agents on the frontend?** The Vercel AI
SDK is React-native and handles all the hard parts of chat UX. LangServe adds
significant dependency surface area. The backend already uses LangChain
(`ChatOpenAI`) — we just stream its output.

### D5: Same backend fallback chain

Chat uses the same backend router as the rest of the system:
`api → opencode → claude_code → codex`.

- When the **API backend** is active: full SSE streaming. Tokens arrive
  incrementally.
- When a **CLI backend** is active: blocking call, full response returned at
  once. The UI shows a "Non-streaming response" indicator.

This is a deliberate trade-off: streaming is the ideal experience, but forcing
API-only would exclude users who only have CLI backends configured. The UI makes
the degradation visible.

### D6: Hybrid backend configuration

Backend settings follow a precedence chain: **in-app setting → env var →
default**.

- Env vars already work for dev users (existing behavior).
- In-app settings (new "AI Backend" section in Settings) make configuration
  accessible for non-dev users.
- Stored in a new `chat_settings` table in SQLite.

Settings UI fields:

- **Backend type** (dropdown): `api`, `opencode`, `claude_code`, `codex`
- **API key** (password field, write-only display)
- **Base URL** (text, for OpenAI-compatible endpoints including local models)
- **Model name** (text)

### D7: Conversation persistence model

- **Sidebar chat**: ephemeral, per-source, in-memory. Each source has its own
  `Map<sourceId, messages[]>` in React state. Lost on page refresh.
- **Broad chat**: persistent, stored in SQLite. Multiple conversations with
  auto-generated titles (from the first message). Conversation list in a
  collapsible left panel on the Chat page.

New SQLite tables:

- `chat_conversations`: id, title, created_at, updated_at, message_count
- `chat_messages`: id, conversation_id, role, content, tool_calls (JSON),
  created_at

### D8: Agent tool calls visible in UI

The broad chat shows each agent tool call as it happens:

- "Searching vault for 'agent harness'..."
- "Reading 3 sources..."
- "Found related topic page..."

This builds trust and makes the experience feel alive. The Vercel AI SDK
supports rendering intermediate steps natively via `steps` in the message
stream.

### D9: Clickable source references

When the agent references a source in its response (e.g., "According to your
saved article *Attention Is All You Need*..."), the source title is rendered as
a clickable link that navigates to that source in the Library view. The Chat
page state is preserved so the user can return.

Implementation: the agent's `read_source` and `search_sources` tools return
source UIDs. Structured tool results include source metadata. The frontend
renders these as links.

### D10: Component-based frontend architecture

The chat features are extracted into separate component files under
`studio/src/`:

```
studio/src/
  components/
    chat/
      ChatPage.jsx          Broad chat page (main Chat tab)
      ConversationList.jsx  Left panel conversation list
      ChatMessage.jsx       Single message rendering (markdown + tool calls)
      ChatInput.jsx         Message input with submit handling
      SuggestedPrompts.jsx  Initial empty-state suggestions
      SidebarChat.jsx       Slide-in panel for source detail
  App.jsx                   (existing, modified to add Chat nav + sidebar)
```

The existing Library/Knowledge/Search/Queue/Settings views remain in `App.jsx`
for now.

### D11: "Open in Chat" bridge

A button in the sidebar chat that opens the broad chat page with the current
source pre-loaded as context and the user's question pre-filled. Prevents loss
of train of thought when a sidebar question needs vault-wide scope.

### D12: Suggested prompts for empty state

The broad chat page shows 4-6 static suggested prompts when a conversation is
empty:

- "What are the main topics in my knowledge base?"
- "Summarize my recent saves"
- "What connections exist between my sources?"
- "Find sources about [most common topic]"
- "What are the key entities across my vault?"

### D13: Usage tracking, no limits

Chat usage is logged to the existing `usage_events` table (token counts, cost
estimates). A "Tokens used this session" counter appears in the chat UI. No hard
rate limits for v1.

### D14: Context window management

- **Sidebar chat**: compiled note injected in full (already condensed by the
  ingest pipeline). Raw capture truncated to ~4K tokens.
- **Broad chat**: the agent manages its own context by re-reading sources via
  tools when needed. LangChain's tool-calling handles this natively — the agent
  decides what to read and when.

## New Backend Endpoints

### Chat API routes (new file: `app/api/routes_chat.py`)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/studio/chat/sidebar` | Sidebar chat: accepts `source_id` + `messages`, returns SSE stream |
| `POST` | `/studio/chat/broad` | Broad chat: accepts `conversation_id` + `message`, returns SSE agent stream |
| `GET` | `/studio/chat/conversations` | List conversations |
| `GET` | `/studio/chat/conversations/{id}/messages` | Get messages for a conversation |
| `POST` | `/studio/chat/conversations` | Create new conversation |
| `DELETE` | `/studio/chat/conversations/{id}` | Delete conversation |
| `GET` | `/studio/chat/settings` | Get chat backend settings |
| `PUT` | `/studio/chat/settings` | Update chat backend settings |

### Request/response models (in `app/models/chat.py`)

- `SidebarChatRequest`: source_id, messages[]
- `BroadChatRequest`: conversation_id (optional for new), message
- `ConversationResponse`: id, title, created_at, updated_at, message_count
- `MessageResponse`: id, role, content, tool_calls, created_at
- `ChatSettingsRequest`: backend_type, api_key, base_url, model_name
- `ChatSettingsResponse`: backend_type (masked key), base_url, model_name

### New service (in `app/services/chat_service.py`)

- `sidebar_chat(source_id, messages)` → builds context from compiled note +
  raw capture, calls LLM, returns stream
- `broad_chat(conversation_id, message)` → loads history, runs agent with
  tools, persists messages, returns stream
- Agent tool implementations wrapping existing infrastructure:
  - `search_sources` → `app/retrieval/orchestrator.py`
  - `read_source` → `app/storage/repositories.py` + vault reader
  - `read_note` → `app/vault/` filesystem read
  - `list_sources` → existing Studio sources query
  - `list_topics/entities/concepts` → `app/read_model/store.py`
  - `get_source_relations` → `app/read_model/store.py` edges

## New Database Tables

### `chat_conversations`

```sql
CREATE TABLE IF NOT EXISTS chat_conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'New conversation',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    message_count INTEGER NOT NULL DEFAULT 0
);
```

### `chat_messages`

```sql
CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL DEFAULT '',
    tool_calls TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation ON chat_messages(conversation_id, created_at);
```

### `chat_settings`

```sql
CREATE TABLE IF NOT EXISTS chat_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

## Frontend Architecture

### New npm dependencies

```
ai                  Vercel AI SDK core
@ai-sdk/openai      OpenAI provider for the SDK
react-markdown      Markdown rendering in chat messages (if not already used)
```

### Component tree

```
App.jsx
├── <Nav> (modified: add "Chat" tab)
├── <LibraryView> (existing)
├── <SourceDetailView> (existing, modified)
│   └── <SidebarChat />          ← new, slide-in panel
│       ├── <ChatMessage />       ← shared
│       └── <ChatInput />         ← shared
├── <KnowledgeView> (existing)
├── <SearchView> (existing)
├── <QueueView> (existing)
├── <ChatPage />                   ← new, full page
│   ├── <ConversationList />      ← left panel
│   ├── <SuggestedPrompts />      ← empty state
│   ├── <ChatMessage />           ← shared, with tool call rendering
│   │   └── <SourceReference />   ← clickable link
│   └── <ChatInput />             ← shared
└── <SettingsView> (existing, modified)
    └── <AIChatSettings />        ← new section
```

### Chat hook (shared between sidebar and broad chat)

A custom React hook wrapping Vercel AI SDK's `useChat` with Epistora-specific
configuration:

```jsx
// studio/src/hooks/useEpistoraChat.js
// Wraps useChat with:
// - Auth header injection
// - Streaming mode detection
// - Source reference parsing
// - Token usage tracking
```

## System Prompts

### Sidebar chat system prompt

```
You are a knowledgeable assistant helping the user understand a specific
source in their personal knowledge base. You have access to the compiled
analysis and the raw extracted content for this source.

Answer questions about the source accurately. Reference specific sections
when possible. If the user asks about something not covered in this source,
say so and suggest they use the Broad Chat for vault-wide questions.

[COMPILED NOTE FOLLOWS]
{compiled_note}

[RAW CAPTURE FOLLOWS]
{raw_capture_truncated}
```

### Broad chat agent system prompt

```
You are a knowledgeable assistant with full access to the user's personal
knowledge base (vault). You can search, read, and navigate their saved
sources, topics, entities, concepts, and the relationships between them.

Your role is to help the user understand, explore, and synthesize their
knowledge. You can:
- Answer questions about specific sources
- Find and list relevant sources on a topic
- Summarize across multiple sources
- Compare and contrast different sources
- Explain connections between topics, entities, and concepts
- Identify gaps or patterns in their knowledge

Always ground your answers in the user's actual saved content. Cite sources
by name when referencing them. Be thorough but concise.

When you use tools to search or read, explain what you're finding as you go.
```

## Implementation Order

### Phase 1: Backend foundation

1. Create `app/models/chat.py` with request/response models
2. Create `chat_conversations`, `chat_messages`, `chat_settings` tables in
   `app/storage/sqlite.py`
3. Create `app/services/chat_service.py` with:
   - Sidebar chat: context builder + LLM call + streaming
   - Conversation CRUD
4. Create `app/api/routes_chat.py` with all endpoints
5. Register chat routes in `app/main.py`

### Phase 2: Sidebar chat frontend

1. Install Vercel AI SDK npm packages
2. Create `studio/src/hooks/useEpistoraChat.js`
3. Create shared components: `ChatMessage.jsx`, `ChatInput.jsx`
4. Create `SidebarChat.jsx` with slide-in panel
5. Modify source detail view to add "Chat" button and sidebar panel
6. Test sidebar chat end-to-end

### Phase 3: Broad chat agent

1. Implement agent tools in `app/services/chat_service.py`:
   - `search_sources` wrapping retrieval orchestrator
   - `read_source` wrapping repositories + vault reader
   - `read_note` wrapping vault filesystem
   - `list_sources` wrapping Studio sources query
   - `list_topics/entities/concepts` wrapping read model
   - `get_source_relations` wrapping read model edges
2. Create LangChain tool-calling agent with streaming
3. Wire broad chat endpoint to agent with conversation persistence
4. Test agent end-to-end via API

### Phase 4: Broad chat frontend

1. Create `ChatPage.jsx` with conversation list panel
2. Create `ConversationList.jsx`
3. Create `SuggestedPrompts.jsx` for empty state
4. Enhance `ChatMessage.jsx` with tool call rendering and source references
5. Add "Chat" tab to main navigation
6. Test broad chat end-to-end

### Phase 5: Settings and polish

1. Create `AIChatSettings.jsx` component
2. Add chat settings section to Settings page
3. Wire settings API (GET/PUT `/studio/chat/settings`)
4. Add "Open in Chat" bridge from sidebar to broad chat
5. Add non-streaming indicator for CLI backends
6. Add token usage counter in chat UI
7. End-to-end testing across all backends

## Risks and Open Questions

- **Agent tool-call latency:** The agent may make 3-5 tool calls per question.
  Each adds latency. The streaming UI mitigates perceived latency, but the total
  response time could be 10-30 seconds for complex queries. Acceptable for v1.
- **Context window limits for agent:** The agent holds conversation history plus
  tool results in context. Long conversations may exceed model limits. Mitigate
  by trimming older messages when approaching the limit.
- **Non-streaming UX for CLI backends:** Blocking calls may take 5-15 seconds
  with no visual feedback beyond a spinner. The UI indicator ("Non-streaming
  response from CLI backend") sets expectations, but it's still a degraded
  experience. Acceptable trade-off for v1.
- **SQLite concurrent writes:** Chat persistence adds write load to SQLite. WAL
  mode already handles read concurrency well. Chat writes are small and
  infrequent enough that contention should not be an issue.
