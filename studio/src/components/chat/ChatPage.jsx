import { useEffect, useRef, useState } from "react";
import { messageText, toUiMessage, useEpistoraChat } from "../../hooks/useEpistoraChat";
import ChatInput from "./ChatInput";
import ChatMessage from "./ChatMessage";
import ConversationList from "./ConversationList";
import SuggestedPrompts from "./SuggestedPrompts";

function studioToken() {
  return localStorage.getItem("epistoraStudioToken") || "";
}

function headers(extra = {}) {
  const token = studioToken();
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  };
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: headers(options.headers || {}),
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return response.json();
}

export default function ChatPage({ bridgeDraft, onBridgeConsumed, onOpenSource }) {
  const [conversations, setConversations] = useState([]);
  const [activeConversationId, setActiveConversationId] = useState("");
  const [initialMessages, setInitialMessages] = useState([]);
  const [loadedKey, setLoadedKey] = useState("new");
  const [collapsed, setCollapsed] = useState(false);
  const [draft, setDraft] = useState("");
  const [sourceContext, setSourceContext] = useState(null);
  const [sessionTokens, setSessionTokens] = useState(0);
  const [error, setError] = useState("");
  const bottomRef = useRef(null);

  const chat = useEpistoraChat({
    api: "/studio/chat/broad",
    initialMessages,
    resetKey: loadedKey,
    onConversation: (conversationId) => {
      if (conversationId) setActiveConversationId(conversationId);
      loadConversations().catch((err) => setError(err.message));
    },
    onUsage: (usage) => setSessionTokens((tokens) => tokens + (usage.tokens || usage.outputTokens || 0)),
    onFinish: () => loadConversations().catch((err) => setError(err.message)),
  });

  useEffect(() => {
    loadConversations().catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!bridgeDraft) return;
    setActiveConversationId("");
    setInitialMessages([]);
    setLoadedKey(`bridge-${Date.now()}`);
    setDraft(bridgeDraft.draft || "");
    setSourceContext({
      source_id: bridgeDraft.source?.uid || "",
      title: bridgeDraft.source?.title || "",
    });
    onBridgeConsumed();
  }, [bridgeDraft]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [chat.messages, chat.status, chat.toolEvents]);

  async function loadConversations() {
    const rows = await api("/studio/chat/conversations");
    setConversations(rows || []);
  }

  async function openConversation(conversationId) {
    setError("");
    const rows = await api(`/studio/chat/conversations/${encodeURIComponent(conversationId)}/messages`);
    setActiveConversationId(conversationId);
    setInitialMessages((rows || []).map(toUiMessage));
    setLoadedKey(conversationId);
    setSourceContext(null);
  }

  async function deleteConversation(conversationId) {
    await api(`/studio/chat/conversations/${encodeURIComponent(conversationId)}`, { method: "DELETE" });
    if (conversationId === activeConversationId) newConversation();
    await loadConversations();
  }

  function newConversation() {
    setActiveConversationId("");
    setInitialMessages([]);
    setLoadedKey(`new-${Date.now()}`);
    setDraft("");
    setSourceContext(null);
    setError("");
  }

  async function submit(text = draft) {
    const trimmed = text.trim();
    if (!trimmed) return;
    setDraft("");
    const body = {
      conversation_id: activeConversationId || null,
      message: trimmed,
      ...(sourceContext?.source_id ? { source_context: sourceContext } : {}),
    };
    setSourceContext(null);
    await chat.send(trimmed, body);
  }

  const hasMessages = chat.messages.some((message) => messageText(message).trim());

  return (
    <section className="view is-active chat-page" aria-label="Chat">
      <ConversationList
        conversations={conversations}
        activeId={activeConversationId}
        collapsed={collapsed}
        onToggle={() => setCollapsed((value) => !value)}
        onNew={newConversation}
        onOpen={openConversation}
        onDelete={deleteConversation}
      />
      <div className="chat-main">
        <header className="chat-main-head">
          <div>
            <h2>{activeConversationId ? "Conversation" : "New conversation"}</h2>
            <p>Ask across sources, topics, entities, concepts, and saved notes.</p>
          </div>
          <div className="chat-counters">
            {chat.meta.nonStreaming ? <span>Non-streaming response</span> : null}
            <span>{sessionTokens} tokens this session</span>
          </div>
        </header>
        <div className="chat-thread broad">
          {!hasMessages ? (
            <div className="chat-empty">
              <h3>Start with a question</h3>
              <p>Search, summarize, compare, or ask for connections in your vault.</p>
              <SuggestedPrompts onPick={(prompt) => submit(prompt)} />
            </div>
          ) : null}
          {chat.toolEvents.map((event, idx) => (
            <div className="tool-status" key={`${event.status}-${idx}`}>{event.status}</div>
          ))}
          {chat.messages.map((message) => (
            <ChatMessage key={message.id} message={message} onOpenSource={onOpenSource} />
          ))}
          {chat.error ? <div className="message is-error">{chat.error.message}</div> : null}
          {error ? <div className="message is-error">{error}</div> : null}
          <div ref={bottomRef} />
        </div>
        <ChatInput
          value={draft}
          onChange={setDraft}
          onSubmit={() => submit()}
          disabled={chat.isRunning}
          placeholder="Ask across your vault"
        />
      </div>
    </section>
  );
}
