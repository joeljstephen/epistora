import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

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
  const text = cleanDisplayText(message.content || textFromParts(message.parts));
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
        {text ? (
          <div className="chat-markdown">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={markdownComponents}
            >
              {text}
            </ReactMarkdown>
          </div>
        ) : null}
      </div>
    </article>
  );
}

const markdownComponents = {
  a({ href, children }) {
    return (
      <a href={href} target="_blank" rel="noreferrer">
        {children}
      </a>
    );
  },
  h1({ children }) {
    return <h3>{children}</h3>;
  },
  h2({ children }) {
    return <h3>{children}</h3>;
  },
  h3({ children }) {
    return <h4>{children}</h4>;
  },
};

function cleanDisplayText(text = "") {
  const lines = text.split(/\r?\n/);
  const cleaned = [];
  let droppingSql = false;

  for (const line of lines) {
    const stripped = line.trim();
    if (!stripped) {
      droppingSql = false;
      if (cleaned.length && cleaned[cleaned.length - 1] !== "") cleaned.push("");
      continue;
    }
    if (looksLikeNoise(stripped) || droppingSql) {
      droppingSql = startsSqlBlock(stripped);
      continue;
    }
    cleaned.push(line);
  }

  return cleaned.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

function looksLikeNoise(line) {
  if (line === "(no output)") return true;
  if (line.startsWith("✱ ") || line.startsWith("✗ ") || line.startsWith("$ ") || line.startsWith("→ ")) {
    return true;
  }
  if (line.startsWith("ls: ") || line.includes("no such file or directory")) return true;
  if (line.includes("knowledge_vault/") || line.includes(".system/epistora.db")) return true;
  if (line.toLowerCase().includes("haven't been written to disk")) return true;
  if (line.startsWith("Error: in prepare")) return true;
  if (startsSqlBlock(line)) return true;
  if (line.includes("sqlite_sequence")) return true;
  if (line.includes("processed_sources") && line.includes("vault_notes")) return true;
  if (!line.startsWith("|") && line.split("|").length >= 4) {
    return line.includes("http") || line.includes("wiki/") || /^\d+\|/.test(line);
  }
  return false;
}

function startsSqlBlock(line) {
  return /^(CREATE TABLE|CREATE INDEX|SELECT|FROM|WHERE|ORDER BY)\b/i.test(line);
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
