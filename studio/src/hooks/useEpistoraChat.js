import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { useEffect, useMemo, useState } from "react";

function studioToken() {
  return localStorage.getItem("epistoraStudioToken") || "";
}

function authHeaders() {
  const token = studioToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function toUiMessage(message) {
  const content = message.content || "";
  return {
    id: message.id || `local-${crypto.randomUUID()}`,
    role: message.role,
    parts: [{ type: "text", text: content }],
    metadata: {
      createdAt: message.created_at || "",
      toolCalls: message.tool_calls || [],
    },
  };
}

export function messageText(message) {
  if (!message) return "";
  if (message.content) return message.content;
  return (message.parts || [])
    .filter((part) => part.type === "text")
    .map((part) => part.text || "")
    .join("");
}

export function useEpistoraChat({ api, initialMessages = [], resetKey = api, onFinish, onConversation, onUsage } = {}) {
  const [toolEvents, setToolEvents] = useState([]);
  const [meta, setMeta] = useState({ nonStreaming: false, tokens: 0, backend: "", model: "" });
  const initial = useMemo(() => initialMessages, []);
  const transport = useMemo(
    () =>
      new DefaultChatTransport({
        api,
        headers: authHeaders,
      }),
    [api],
  );
  const chat = useChat({
    transport,
    messages: initial,
    onData: (part) => {
      if (part?.type === "data-tool-status") {
        setToolEvents((events) => [...events, part.data].slice(-12));
      }
      if (part?.type === "data-chat-meta") {
        const data = part.data || {};
        setMeta((prev) => ({
          ...prev,
          ...data,
          tokens: data.tokens ?? data.outputTokens ?? prev.tokens,
        }));
        if (data.tokens || data.outputTokens) onUsage?.(data);
      }
      if (part?.type === "data-conversation") {
        onConversation?.(part.data?.conversationId || "");
      }
    },
    onFinish,
  });

  useEffect(() => {
    chat.setMessages(initialMessages);
    setToolEvents([]);
    setMeta({ nonStreaming: false, tokens: 0, backend: "", model: "" });
  }, [resetKey]);

  async function send(text, body = {}) {
    const trimmed = text.trim();
    if (!trimmed || chat.status === "submitted" || chat.status === "streaming") return;
    setToolEvents([]);
    setMeta((prev) => ({ ...prev, nonStreaming: false }));
    await chat.sendMessage({ text: trimmed }, { body });
  }

  return {
    ...chat,
    send,
    toolEvents,
    meta,
    isRunning: chat.status === "submitted" || chat.status === "streaming",
  };
}
