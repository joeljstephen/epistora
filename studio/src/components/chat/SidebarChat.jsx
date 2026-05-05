import { useEffect, useRef, useState } from "react";
import { useEpistoraChat } from "../../hooks/useEpistoraChat";
import ChatInput from "./ChatInput";
import ChatMessage from "./ChatMessage";

export default function SidebarChat({
  open,
  source,
  messages,
  onMessagesChange,
  onClose,
  onOpenBroadChat,
}) {
  const [draft, setDraft] = useState("");
  const bottomRef = useRef(null);
  const chat = useEpistoraChat({
    api: "/studio/chat/sidebar",
    initialMessages: messages,
    resetKey: source?.uid || "no-source",
  });

  useEffect(() => {
    if (source?.uid) onMessagesChange(source.uid, chat.messages);
  }, [chat.messages, source?.uid]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [chat.messages, chat.status]);

  async function submit() {
    const text = draft.trim();
    if (!text || !source?.uid) return;
    setDraft("");
    await chat.send(text, { source_id: source.uid });
  }

  return (
    <aside className={`sidebar-chat ${open ? "is-open" : ""}`} aria-label="Source chat">
      <div className="sidebar-chat-panel">
        <header className="sidebar-chat-head">
          <div>
            <p className="caption">Source chat</p>
            <h2>{source?.title || "Current source"}</h2>
          </div>
          <button type="button" className="icon-button" aria-label="Close chat" onClick={onClose}>
            x
          </button>
        </header>
        <div className="chat-thread">
          {chat.messages.length === 0 ? (
            <div className="empty-state compact">Ask about the compiled note or raw capture for this source.</div>
          ) : null}
          {chat.messages.map((message) => (
            <ChatMessage key={message.id} message={message} />
          ))}
          {chat.isRunning ? <div className="tool-status">Reading this source...</div> : null}
          {chat.error ? <div className="message is-error">{chat.error.message}</div> : null}
          <div ref={bottomRef} />
        </div>
        <footer className="sidebar-chat-foot">
          <button
            type="button"
            className="ghost"
            onClick={() => onOpenBroadChat({ source, draft })}
          >
            Open in Chat
          </button>
          {chat.meta.nonStreaming ? <span className="chat-indicator">Non-streaming response</span> : null}
          <ChatInput
            value={draft}
            onChange={setDraft}
            onSubmit={submit}
            disabled={!source?.uid || chat.isRunning}
            placeholder="Ask about this source"
          />
        </footer>
      </div>
    </aside>
  );
}
