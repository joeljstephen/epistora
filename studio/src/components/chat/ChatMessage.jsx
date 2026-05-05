import ReactMarkdown from "react-markdown";

function textFromParts(parts = []) {
  return parts
    .filter((part) => part.type === "text")
    .map((part) => part.text || "")
    .join("");
}

function toolLabel(part) {
  const name = part.toolName || part.tool || part.type?.replace(/^tool-/, "") || "tool";
  if (part.type === "tool-input-available") return `Using ${name}`;
  if (part.type === "tool-output-available") return `${name} returned results`;
  return name;
}

function sourceRefsFromPart(part) {
  const output = part.output || part.data || {};
  const sources = output.sources || (output.source ? [output.source] : []);
  return sources.filter((source) => source?.uid);
}

export default function ChatMessage({ message, onOpenSource }) {
  const role = message.role || "assistant";
  const text = message.content || textFromParts(message.parts);
  const toolParts = (message.parts || []).filter((part) => part.type?.startsWith("tool-"));
  const dataParts = (message.parts || []).filter((part) => part.type === "data-tool-status");
  const persistedToolCalls = message.metadata?.toolCalls || [];

  return (
    <article className={`chat-message chat-message-${role}`}>
      <div className="chat-avatar" aria-hidden="true">{role === "user" ? "Y" : "E"}</div>
      <div className="chat-bubble">
        <div className="chat-role">{role === "user" ? "You" : "Epistora"}</div>
        {dataParts.map((part, idx) => (
          <div className="tool-status" key={`${message.id}-status-${idx}`}>
            {part.data?.status || "Working..."}
          </div>
        ))}
        {toolParts.map((part, idx) => (
          <div className="tool-call" key={`${message.id}-tool-${idx}`}>
            <span>{toolLabel(part)}</span>
            <SourceReferenceList sources={sourceRefsFromPart(part)} onOpenSource={onOpenSource} />
          </div>
        ))}
        {persistedToolCalls.map((call) => (
          <div className="tool-call" key={call.id || `${call.name}-${JSON.stringify(call.args)}`}>
            <span>{call.name}</span>
          </div>
        ))}
        {text ? <ReactMarkdown>{text}</ReactMarkdown> : null}
      </div>
    </article>
  );
}

export function SourceReferenceList({ sources, onOpenSource }) {
  if (!sources?.length) return null;
  return (
    <div className="source-ref-list">
      {sources.slice(0, 5).map((source) => (
        <button
          key={source.uid}
          type="button"
          className="source-ref"
          onClick={() => onOpenSource?.(source.uid)}
        >
          {source.title || source.uid}
        </button>
      ))}
    </div>
  );
}
