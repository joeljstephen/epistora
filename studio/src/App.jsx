import { Fragment, useEffect, useRef, useState } from "react";
import AIChatSettings from "./components/chat/AIChatSettings";
import ChatPage from "./components/chat/ChatPage";
import SidebarChat from "./components/chat/SidebarChat";

const EMPTY_MESSAGES = [];

const VIEW_TITLES = {
  library: ["Library", "A quiet local catalog of everything you have saved."],
  source: ["Source", "Reader-first view of a single source."],
  knowledge: ["Knowledge", "Topics, entities, and concepts derived from the vault."],
  search: ["Search", "Combined catalog and knowledge search."],
  queue: ["Queue", "Source-linked jobs you can process on demand."],
  settings: ["Settings", "Local runtime, catalog snapshots, and tokens."],
  chat: ["Chat", "Ask across your whole knowledge base."],
};

const LIBRARY_SECTIONS = {
  all: {
    title: "All sources",
    subtitle: "Everything we have noticed across providers and manual additions.",
    caption: "Showing every source we have noticed across providers.",
    filter: () => ({}),
    empty: "No sources yet. Start by adding a URL or running a connector sync.",
  },
  article: {
    title: "Articles",
    subtitle: "Long-form writing from the open web.",
    caption: "Articles only.",
    filter: () => ({ source_type: "article" }),
    empty: "No articles in the library yet.",
  },
  youtube: {
    title: "Videos & YouTube",
    subtitle: "Talks, lectures, and longform video.",
    caption: "Video sources with compact YouTube cover previews.",
    filter: () => ({ source_type: "youtube" }),
    empty: "No videos saved yet.",
  },
  x_thread: {
    title: "Threads",
    subtitle: "Twitter/X threads and conversations.",
    caption: "Threads from X / Twitter.",
    filter: () => ({ source_type: "x_thread" }),
    empty: "No threads saved yet.",
  },
  pdf: {
    title: "Documents",
    subtitle: "PDFs and longer documents.",
    caption: "Document captures.",
    filter: () => ({ source_type: "pdf" }),
    empty: "No PDF documents in the library yet.",
  },
  "state-metadata_only": {
    title: "Metadata only",
    subtitle: "Imported but not yet captured. Vault notes have not been written.",
    caption: "Metadata-only catalog rows.",
    filter: () => ({ display_state: "metadata_only" }),
    empty: "Nothing in metadata-only state.",
  },
  "state-brief_ready": {
    title: "Brief ready",
    subtitle: "Sources with a compiled brief note ready to read.",
    caption: "Sources with brief artifacts ready.",
    filter: () => ({ display_state: "brief_ready" }),
    empty: "No briefs ready yet.",
  },
  "state-deep_compiled": {
    title: "Deep compiled",
    subtitle: "Sources processed in deep mode with full enrichment.",
    caption: "Deep-compiled sources.",
    filter: () => ({ display_state: "deep_compiled" }),
    empty: "No deep-compiled sources yet.",
  },
  "state-failed": {
    title: "Needs attention",
    subtitle: "Sources that failed at least once. Review and retry as needed.",
    caption: "Sources with failures.",
    filter: () => ({ display_state: "failed" }),
    empty: "Nothing failed. Quiet day on the queue.",
  },
};

const KNOWLEDGE_SECTIONS = {
  topic: {
    title: "Topics",
    subtitle: "Themes and recurring subjects in the vault.",
    empty: "No topic notes yet. Compile some sources in deep mode to populate this view.",
  },
  entity: {
    title: "Entities",
    subtitle: "People, organizations, and named entities mentioned across sources.",
    empty: "No entity notes yet.",
  },
  concept: {
    title: "Concepts",
    subtitle: "Ideas, frameworks, and abstractions surfaced from your reading.",
    empty: "No concept notes yet.",
  },
  synthesis: {
    title: "Synthesis",
    subtitle: "Saved syntheses and compiled answers.",
    empty: "No synthesis notes yet.",
  },
};

const NAV_GROUPS = [
  {
    label: "Library",
    items: [
      ["library:all", "All sources"],
      ["library:article", "Articles"],
      ["library:youtube", "Videos & YouTube"],
      ["library:x_thread", "Threads"],
      ["library:pdf", "Documents"],
      ["library:state-metadata_only", "Metadata only"],
      ["library:state-brief_ready", "Brief ready"],
      ["library:state-deep_compiled", "Deep compiled"],
      ["library:state-failed", "Needs attention"],
    ],
  },
  {
    label: "Knowledge",
    items: [
      ["knowledge:topic", "Topics"],
      ["knowledge:entity", "Entities"],
      ["knowledge:concept", "Concepts"],
      ["knowledge:synthesis", "Synthesis"],
    ],
  },
  {
    label: "Workspace",
    items: [
      ["chat", "Chat"],
      ["search", "Search"],
      ["queue", "Queue"],
      ["settings", "Settings"],
    ],
  },
];

function token() {
  return localStorage.getItem("epistoraStudioToken") || "";
}

function headers(extra = {}) {
  const t = token();
  return {
    "Content-Type": "application/json",
    ...(t ? { Authorization: `Bearer ${t}` } : {}),
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

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function attr(value) {
  return escapeHtml(value).replaceAll('"', "&quot;");
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatRelativeOrDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  const diffMin = Math.round((Date.now() - date.getTime()) / 60000);
  if (Math.abs(diffMin) < 60) return diffMin <= 0 ? "just now" : `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (Math.abs(diffHr) < 24) return `${diffHr}h ago`;
  return formatDate(value);
}

function label(value) {
  return String(value || "-").replaceAll("_", " ");
}

function domainOf(url) {
  try {
    const parsed = new URL(url);
    return parsed.host.replace(/^www\./, "") + (parsed.pathname === "/" ? "" : parsed.pathname);
  } catch {
    return url || "";
  }
}

function extractYouTubeId(url) {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.replace(/^www\./, "");
    if (host === "youtu.be") return parsed.pathname.split("/").filter(Boolean)[0] || "";
    if (host.endsWith("youtube.com")) {
      if (parsed.searchParams.get("v")) return parsed.searchParams.get("v");
      const parts = parsed.pathname.split("/").filter(Boolean);
      if (["shorts", "embed", "live"].includes(parts[0])) return parts[1] || "";
    }
  } catch {
    return "";
  }
  return "";
}

function youtubeThumb(url) {
  const id = extractYouTubeId(url);
  return id ? `https://i.ytimg.com/vi/${id}/hqdefault.jpg` : "";
}

function sourceInitials(source) {
  const basis = source.site_name || domainOf(source.url) || source.title || source.source_type || "source";
  const cleaned = basis.replace(/[^a-z0-9\s.-]/gi, " ").replace(/\s+/g, " ").trim();
  const parts = cleaned.split(/[.\s-]+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return (parts[0] || "S").slice(0, 2).toUpperCase();
}

function sourcePreview(source) {
  const sourceType = source.source_type || "generic";
  const thumb = sourceType === "youtube" ? youtubeThumb(source.url) : "";
  const host = domainOf(source.url).split("/")[0] || label(sourceType);
  const title = {
    article: "Article",
    youtube: "YouTube",
    x_thread: "Thread",
    pdf: "PDF",
    generic: "Source",
  }[sourceType] || label(sourceType);
  return {
    sourceType,
    thumb,
    title,
    host,
    initials: sourceInitials(source),
  };
}

function pickInitialReaderMode(reader) {
  if (reader?.has_source_note) return "note";
  if (reader?.has_raw_capture) return "raw";
  return "metadata";
}

function stripFrontmatter(markdown) {
  return String(markdown || "").replace(/^---\n[\s\S]*?\n---\n?/, "").trim();
}

const URL_RE = /\bhttps?:\/\/[^\s<>"'`]+/g;
const WIKILINK_RE = /\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g;
const LINK_RE = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;
const BOLD_RE = /\*\*([^*]+)\*\*/g;
const ITALIC_RE = /(^|\W)_([^_\n]+)_(\W|$)/g;
const ITALIC_ASTERISK_RE = /(^|\W)\*([^*\n]+)\*(\W|$)/g;
const STRIKE_RE = /~~([^~]+)~~/g;
const INLINE_CODE_RE = /`([^`]+)`/g;

function inlineMarkdown(text) {
  let value = escapeHtml(text);
  const codes = [];
  value = value.replace(INLINE_CODE_RE, (_, code) => {
    codes.push(code);
    return `\u0001CODE${codes.length - 1}\u0001`;
  });
  value = value.replace(LINK_RE, (_, label_, href) => {
    return `<a href="${attr(href)}" target="_blank" rel="noreferrer">${label_}</a>`;
  });
  value = value.replace(WIKILINK_RE, (_, target, alias) => `<span class="wikilink">${escapeHtml(alias || target)}</span>`);
  value = value.replace(BOLD_RE, "<strong>$1</strong>");
  value = value.replace(ITALIC_RE, "$1<em>$2</em>$3");
  value = value.replace(ITALIC_ASTERISK_RE, "$1<em>$2</em>$3");
  value = value.replace(STRIKE_RE, "<del>$1</del>");
  value = value.replace(URL_RE, (url) => {
    if (value.includes(`href="${url}"`)) return url;
    return `<a href="${attr(url)}" target="_blank" rel="noreferrer">${escapeHtml(url)}</a>`;
  });
  return value.replace(/\u0001CODE(\d+)\u0001/g, (_, idx) => `<code>${escapeHtml(codes[Number(idx)])}</code>`);
}

function markdownToHtml(text) {
  const lines = String(text || "").split("\n");
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim().startsWith("```")) {
      const lang = line.trim().slice(3).trim();
      const codeLines = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      i++;
      const langClass = lang ? ` class="lang-${attr(lang)}"` : "";
      out.push(`<pre><code${langClass}>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
      continue;
    }
    if (/^\s*$/.test(line)) {
      i++;
      continue;
    }
    if (/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      out.push("<hr>");
      i++;
      continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      out.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
      i++;
      continue;
    }
    if (/^\s*>\s?/.test(line)) {
      const quoted = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        quoted.push(lines[i].replace(/^\s*>\s?/, ""));
        i++;
      }
      out.push(`<blockquote>${markdownToHtml(quoted.join("\n"))}</blockquote>`);
      continue;
    }
    if (
      i + 1 < lines.length &&
      /\|/.test(line) &&
      /^\s*\|?\s*[:-]+(\s*\|\s*[:-]+)+\s*\|?\s*$/.test(lines[i + 1])
    ) {
      const header = splitTableRow(line);
      const aligns = splitTableRow(lines[i + 1]).map(alignFromCell);
      i += 2;
      const rows = [];
      while (i < lines.length && /\|/.test(lines[i]) && lines[i].trim() !== "") {
        rows.push(splitTableRow(lines[i]));
        i++;
      }
      const head = `<tr>${header.map((cell, idx) => `<th${aligns[idx] ? ` style="text-align:${aligns[idx]}"` : ""}>${inlineMarkdown(cell)}</th>`).join("")}</tr>`;
      const body = rows
        .map((row) => `<tr>${row.map((cell, idx) => `<td${aligns[idx] ? ` style="text-align:${aligns[idx]}"` : ""}>${inlineMarkdown(cell)}</td>`).join("")}</tr>`)
        .join("");
      out.push(`<table><thead>${head}</thead><tbody>${body}</tbody></table>`);
      continue;
    }
    if (/^\s*([-*+]\s+|\d+\.\s+)/.test(line)) {
      const consumed = consumeList(lines, i);
      out.push(consumed.html);
      i = consumed.next;
      continue;
    }
    const para = [line];
    i++;
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^\s*(#{1,6}\s+|>\s?|[-*+]\s+|\d+\.\s+|```)/.test(lines[i])
    ) {
      para.push(lines[i]);
      i++;
    }
    out.push(`<p>${inlineMarkdown(para.join(" "))}</p>`);
  }
  return out.join("\n");
}

function splitTableRow(line) {
  let trimmed = line.trim();
  if (trimmed.startsWith("|")) trimmed = trimmed.slice(1);
  if (trimmed.endsWith("|")) trimmed = trimmed.slice(0, -1);
  return trimmed.split("|").map((cell) => cell.trim());
}

function alignFromCell(cell) {
  const trimmed = cell.trim();
  const left = trimmed.startsWith(":");
  const right = trimmed.endsWith(":");
  if (left && right) return "center";
  if (right) return "right";
  if (left) return "left";
  return "";
}

function consumeList(lines, start) {
  const baseIndent = (lines[start].match(/^(\s*)/) || ["", ""])[1].length;
  const ordered = /^\s*\d+\.\s+/.test(lines[start]);
  const tag = ordered ? "ol" : "ul";
  const items = [];
  let i = start;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === "") {
      if (
        i + 1 < lines.length &&
        /^\s*([-*+]\s+|\d+\.\s+)/.test(lines[i + 1]) &&
        ((lines[i + 1].match(/^(\s*)/) || ["", ""])[1].length >= baseIndent)
      ) {
        i++;
        continue;
      }
      i++;
      break;
    }
    const indent = (line.match(/^(\s*)/) || ["", ""])[1].length;
    if (indent < baseIndent) break;
    const matchTop = /^(\s*)([-*+]\s+|\d+\.\s+)(.*)$/.exec(line);
    if (!matchTop) break;
    if (indent !== baseIndent) {
      if (items.length === 0) break;
      const lastIdx = items.length - 1;
      const childLines = [];
      while (
        i < lines.length &&
        (lines[i].trim() === "" || ((lines[i].match(/^(\s*)/) || ["", ""])[1].length > baseIndent))
      ) {
        childLines.push(lines[i].slice(baseIndent + 2));
        i++;
      }
      items[lastIdx].children = (items[lastIdx].children || "") + markdownToHtml(childLines.join("\n"));
      continue;
    }
    items.push({ text: matchTop[3], children: "" });
    i++;
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      ((lines[i].match(/^(\s*)/) || ["", ""])[1].length > baseIndent)
    ) {
      items[items.length - 1].children += `\n${lines[i].slice(baseIndent + 2)}`;
      i++;
    }
  }
  return {
    html: `<${tag}>${items
      .map((item) => {
        const rendered = item.children?.trim() ? markdownToHtml(item.children) : "";
        return `<li>${inlineMarkdown(item.text)}${rendered ? `\n${rendered}` : ""}</li>`;
      })
      .join("")}</${tag}>`,
    next: i,
  };
}

function renderProse(markdown) {
  const text = String(markdown || "").trim();
  return text ? markdownToHtml(text) : "";
}

function Skeleton({ count = 3 }) {
  return (
    <div className="skeleton">
      {Array.from({ length: count }).map((_, idx) => (
        <div className="skeleton-row" key={idx} />
      ))}
    </div>
  );
}

function Tag({ children, kind = "" }) {
  return <span className={`tag ${kind}`}>{children}</span>;
}

function Prose({ markdown }) {
  return <article className="prose" dangerouslySetInnerHTML={{ __html: renderProse(markdown) }} />;
}

export default function App() {
  const [route, setRoute] = useState("library:all");
  const [view, setView] = useState("library");
  const [titleOverride, setTitleOverride] = useState(LIBRARY_SECTIONS.all);
  const [message, setMessage] = useState(null);
  const [activeLibraryKey, setActiveLibraryKey] = useState("all");
  const [librarySources, setLibrarySources] = useState([]);
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [selectedSourceUid, setSelectedSourceUid] = useState("");
  const [selectedSourceDetail, setSelectedSourceDetail] = useState(null);
  const [selectedReader, setSelectedReader] = useState(null);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [readerMode, setReaderMode] = useState("metadata");
  const [knowledgeType, setKnowledgeType] = useState("topic");
  const [knowledgeNotes, setKnowledgeNotes] = useState([]);
  const [selectedKnowledgePath, setSelectedKnowledgePath] = useState("");
  const [knowledgeDetail, setKnowledgeDetail] = useState(null);
  const [knowledgeLoading, setKnowledgeLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchHits, setSearchHits] = useState([]);
  const [searchMeta, setSearchMeta] = useState("");
  const [searchLoading, setSearchLoading] = useState(false);
  const [jobs, setJobs] = useState([]);
  const [jobStatusFilter, setJobStatusFilter] = useState("");
  const [stats, setStats] = useState(null);
  const [queueLoading, setQueueLoading] = useState(false);
  const [runtimeStatus, setRuntimeStatus] = useState(null);
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [apiToken, setApiToken] = useState(token());
  const [snapshotPath, setSnapshotPath] = useState("");
  const [snapshotResult, setSnapshotResult] = useState("");
  const [quickSearch, setQuickSearch] = useState("");
  const [searchForm, setSearchForm] = useState({ q: "", sourceType: "", displayState: "" });
  const [dialogOpen, setDialogOpen] = useState(false);
  const [manualForm, setManualForm] = useState({ url: "", title: "", tags: "", action: "" });
  const [sidebarChatOpen, setSidebarChatOpen] = useState(false);
  const [sidebarMessagesBySource, setSidebarMessagesBySource] = useState({});
  const [chatBridgeDraft, setChatBridgeDraft] = useState(null);
  const addDialogRef = useRef(null);

  const viewTitle = titleOverride?.title || VIEW_TITLES[view]?.[0] || "";
  const viewSubtitle = titleOverride?.subtitle || VIEW_TITLES[view]?.[1] || "";
  const activeLibraryConfig = LIBRARY_SECTIONS[activeLibraryKey] || LIBRARY_SECTIONS.all;
  const isNavActive = (itemRoute) => (
    route === itemRoute ||
    (route.startsWith("source:") && itemRoute === `library:${activeLibraryKey || "all"}`)
  );

  useEffect(() => {
    const dialog = addDialogRef.current;
    if (!dialog) return;
    if (dialogOpen && !dialog.open) dialog.showModal();
    if (!dialogOpen && dialog.open) dialog.close();
  }, [dialogOpen]);

  async function navigate(nextRoute) {
    setRoute(nextRoute);
    setMessage(null);

    if (nextRoute.startsWith("library:")) {
      const key = nextRoute.split(":")[1] || "all";
      const config = LIBRARY_SECTIONS[key] || LIBRARY_SECTIONS.all;
      setActiveLibraryKey(key);
      setView("library");
      setTitleOverride(config);
      await loadLibrary(config);
      return;
    }
    if (nextRoute.startsWith("knowledge:")) {
      const noteType = nextRoute.split(":")[1] || "topic";
      await openKnowledgeSection(noteType);
      return;
    }
    if (nextRoute.startsWith("source:")) {
      const uid = nextRoute.split(":")[1];
      await openSourceDetail(uid);
      return;
    }
    if (nextRoute === "search") {
      setView("search");
      setTitleOverride(null);
      return;
    }
    if (nextRoute === "chat") {
      setSidebarChatOpen(false);
      setView("chat");
      setTitleOverride(null);
      return;
    }
    if (nextRoute === "queue") {
      setView("queue");
      setTitleOverride(null);
      await loadQueue();
      return;
    }
    if (nextRoute === "settings") {
      setView("settings");
      setTitleOverride(null);
      await loadSettings();
    }
  }

  async function loadLibrary(config = activeLibraryConfig, query = searchQuery) {
    const params = new URLSearchParams({ limit: "200" });
    Object.entries(config.filter()).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
    if (query) params.set("q", query);
    setLibraryLoading(true);
    try {
      const payload = await api(`/studio/sources?${params}`);
      setLibrarySources(payload.sources || []);
    } catch (err) {
      setMessage({ text: `Failed to load library: ${err.message}`, kind: "error" });
      setLibrarySources([]);
    } finally {
      setLibraryLoading(false);
    }
  }

  async function openSourceDetail(uid) {
    setSelectedSourceUid(uid);
    setView("source");
    setTitleOverride(null);
    setSourceLoading(true);
    try {
      const [detail, reader] = await Promise.all([
        api(`/studio/sources/${encodeURIComponent(uid)}`),
        api(`/studio/sources/${encodeURIComponent(uid)}/reader`),
      ]);
      setSelectedSourceDetail(detail);
      setSelectedReader(reader);
      setReaderMode(pickInitialReaderMode(reader));
    } catch (err) {
      setMessage({ text: `Failed to load source: ${err.message}`, kind: "error" });
      setSelectedSourceDetail(null);
      setSelectedReader(null);
    } finally {
      setSourceLoading(false);
    }
  }

  async function enqueueAction(uid, action) {
    try {
      await api(`/studio/sources/${encodeURIComponent(uid)}/actions/enqueue`, {
        method: "POST",
        body: JSON.stringify({ action, requested_reason: "Studio action" }),
      });
      setMessage({ text: `${label(action)} queued. Use the Queue page to process source-linked jobs.`, kind: "info" });
      await openSourceDetail(uid);
    } catch (err) {
      setMessage({ text: err.message, kind: "error" });
    }
  }

  async function openKnowledgeSection(noteType) {
    const config = KNOWLEDGE_SECTIONS[noteType] || KNOWLEDGE_SECTIONS.topic;
    setView("knowledge");
    setTitleOverride(config);
    setKnowledgeType(noteType);
    setKnowledgeNotes([]);
    setKnowledgeDetail(null);
    setKnowledgeLoading(true);
    try {
      const payload = await api(`/studio/knowledge/${encodeURIComponent(noteType)}?limit=300`);
      const notes = payload.notes || [];
      setKnowledgeNotes(notes);
      if (notes[0]) {
        await openKnowledgeNote(notes[0].note_path, notes);
      }
    } catch (err) {
      setMessage({ text: err.message, kind: "error" });
    } finally {
      setKnowledgeLoading(false);
    }
  }

  async function openKnowledgeNote(notePath) {
    setSelectedKnowledgePath(notePath);
    setKnowledgeDetail(null);
    try {
      const detail = await api(`/studio/knowledge/note/detail?note_path=${encodeURIComponent(notePath)}`);
      setKnowledgeDetail(detail);
    } catch (err) {
      setMessage({ text: err.message, kind: "error" });
    }
  }

  async function runSearch(query, options = {}) {
    setSearchQuery(query);
    if (!query.trim()) {
      setSearchHits([]);
      setSearchMeta("");
      return;
    }
    const params = new URLSearchParams({ q: query, limit: "30" });
    if (options.sourceType) params.set("source_type", options.sourceType);
    if (options.displayState) params.set("display_state", options.displayState);
    setSearchLoading(true);
    try {
      const payload = await api(`/studio/search?${params}`);
      const hits = payload.hits || [];
      setSearchHits(hits);
      setSearchMeta(`${hits.length} result${hits.length === 1 ? "" : "s"} for "${payload.query}".`);
    } catch (err) {
      setMessage({ text: err.message, kind: "error" });
      setSearchHits([]);
      setSearchMeta("");
    } finally {
      setSearchLoading(false);
    }
  }

  async function loadQueue(filter = jobStatusFilter) {
    setQueueLoading(true);
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (filter) params.set("status", filter);
      const [jobsPayload, statsPayload] = await Promise.all([
        api(`/studio/jobs?${params}`),
        api("/studio/stats"),
      ]);
      setJobs(jobsPayload.jobs || []);
      setStats(statsPayload);
    } catch (err) {
      setMessage({ text: err.message, kind: "error" });
    } finally {
      setQueueLoading(false);
    }
  }

  async function loadSettings() {
    setSettingsLoading(true);
    try {
      const [status, statsPayload] = await Promise.all([api("/status"), api("/studio/stats")]);
      setRuntimeStatus(status);
      setStats(statsPayload);
      setApiToken(token());
    } catch (err) {
      setMessage({ text: err.message, kind: "error" });
    } finally {
      setSettingsLoading(false);
    }
  }

  async function processJobsOnce() {
    try {
      const res = await api("/studio/jobs/process-once?limit=5", { method: "POST" });
      setMessage({ text: `Processed ${res.processed}; ${res.succeeded} succeeded, ${res.failed} failed.`, kind: "info" });
      await loadQueue();
    } catch (err) {
      setMessage({ text: err.message, kind: "error" });
    }
  }

  async function submitManualAdd(event) {
    event.preventDefault();
    const tags = manualForm.tags.split(",").map((t) => t.trim()).filter(Boolean);
    try {
      const payload = await api("/studio/sources/manual", {
        method: "POST",
        body: JSON.stringify({
          url: manualForm.url.trim(),
          title: manualForm.title.trim(),
          tags,
          enqueue_action: manualForm.action || null,
        }),
      });
      setDialogOpen(false);
      setManualForm({ url: "", title: "", tags: "", action: "" });
      setMessage({ text: manualForm.action ? `Added and queued ${label(manualForm.action)}.` : "Source added as metadata only.", kind: "info" });
      await loadLibrary();
      await navigate(`source:${payload.source.uid}`);
    } catch (err) {
      setMessage({ text: err.message, kind: "error" });
    }
  }

  useEffect(() => {
    navigate("library:all").catch((err) => setMessage({ text: err.message, kind: "error" }));
  }, []);

  return (
    <div className="shell">
      <aside className="rail" aria-label="Studio navigation">
        <header className="rail-brand">
          <div className="rail-mark" aria-hidden="true">
            <svg viewBox="0 0 32 32" width="32" height="32" focusable="false">
              <circle cx="16" cy="16" r="13" fill="none" stroke="currentColor" strokeWidth="1.4" />
              <path d="M9 18 Q16 8 23 18" fill="none" stroke="currentColor" strokeWidth="1.4" />
              <path d="M9 14 Q16 24 23 14" fill="none" stroke="currentColor" strokeWidth="1.4" opacity="0.45" />
            </svg>
          </div>
          <div className="rail-title">
            <strong>Epistora</strong>
            <span>Local Studio</span>
          </div>
        </header>

        <nav className="rail-nav" aria-label="Primary">
          {NAV_GROUPS.map((group) => (
            <div key={group.label}>
              <p className="rail-section">{group.label}</p>
              <ul className="rail-list">
                {group.items.map(([itemRoute, itemLabel]) => (
                  <li key={itemRoute}>
                    <button
                      className={`rail-item ${isNavActive(itemRoute) ? "is-active" : ""}`}
                      type="button"
                      onClick={() => navigate(itemRoute)}
                    >
                      {itemLabel}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>

        <footer className="rail-footer">
          <button className="rail-add" type="button" aria-label="Add a URL" onClick={() => setDialogOpen(true)}>
            <span aria-hidden="true">+</span> Add URL
          </button>
        </footer>
      </aside>

      <main className="workspace">
        <header className="workspace-head">
          <div className="head-titles">
            <h1>{viewTitle}</h1>
            <p>{viewSubtitle}</p>
          </div>
          <form
            className="head-search"
            role="search"
            onSubmit={(event) => {
              event.preventDefault();
              const query = quickSearch.trim();
              if (!query) return;
              setSearchForm((prev) => ({ ...prev, q: query }));
              setView("search");
              setRoute("search");
              setTitleOverride(null);
              runSearch(query, { sourceType: searchForm.sourceType, displayState: searchForm.displayState });
            }}
          >
            <span className="head-search-icon" aria-hidden="true">/</span>
            <input
              type="search"
              placeholder="Search title, URL, description, or notes"
              autoComplete="off"
              value={quickSearch}
              onChange={(event) => setQuickSearch(event.target.value)}
            />
          </form>
        </header>

        {message ? <section className={`message ${message.kind === "error" ? "is-error" : ""}`}>{message.text}</section> : null}

        {view === "library" ? (
          <LibraryView
            config={activeLibraryConfig}
            loading={libraryLoading}
            sources={librarySources}
            activeUid={selectedSourceUid}
            onRefresh={() => loadLibrary()}
            onOpen={(uid) => navigate(`source:${uid}`)}
          />
        ) : null}

        {view === "source" ? (
          <SourceView
            loading={sourceLoading}
            detail={selectedSourceDetail}
            reader={selectedReader}
            readerMode={readerMode}
            setReaderMode={setReaderMode}
            onBack={() => navigate(activeLibraryKey ? `library:${activeLibraryKey}` : "library:all")}
            onAction={enqueueAction}
            onChat={() => setSidebarChatOpen(true)}
          />
        ) : null}

        {view === "knowledge" ? (
          <KnowledgeView
            loading={knowledgeLoading}
            notes={knowledgeNotes}
            detail={knowledgeDetail}
            selectedPath={selectedKnowledgePath}
            empty={KNOWLEDGE_SECTIONS[knowledgeType]?.empty || "No notes yet."}
            onOpen={openKnowledgeNote}
          />
        ) : null}

        {view === "search" ? (
          <SearchView
            form={searchForm}
            setForm={setSearchForm}
            meta={searchMeta}
            hits={searchHits}
            loading={searchLoading}
            onSearch={runSearch}
            onOpenSource={(uid) => navigate(`source:${uid}`)}
            onOpenNote={(noteType, notePath) => {
              if (noteType && KNOWLEDGE_SECTIONS[noteType]) {
                navigate(`knowledge:${noteType}`).then(() => openKnowledgeNote(notePath));
              } else {
                openKnowledgeNote(notePath);
              }
            }}
          />
        ) : null}

        {view === "queue" ? (
          <QueueView
            loading={queueLoading}
            stats={stats}
            jobs={jobs}
            filter={jobStatusFilter}
            onFilter={(filter) => {
              setJobStatusFilter(filter);
              loadQueue(filter);
            }}
            onProcess={processJobsOnce}
            onRefresh={() => loadQueue()}
            onOpenSource={(uid) => navigate(`source:${uid}`)}
          />
        ) : null}

        {view === "chat" ? (
          <ChatPage
            bridgeDraft={chatBridgeDraft}
            onBridgeConsumed={() => setChatBridgeDraft(null)}
            onOpenSource={(uid) => navigate(`source:${uid}`)}
          />
        ) : null}

        {view === "settings" ? (
          <SettingsView
            loading={settingsLoading}
            runtime={runtimeStatus}
            stats={stats}
            apiToken={apiToken}
            setApiToken={setApiToken}
            snapshotPath={snapshotPath}
            setSnapshotPath={setSnapshotPath}
            snapshotResult={snapshotResult}
            onSaveToken={() => {
              localStorage.setItem("epistoraStudioToken", apiToken.trim());
              setMessage({ text: "API token saved.", kind: "info" });
            }}
            onClearToken={() => {
              localStorage.removeItem("epistoraStudioToken");
              setApiToken("");
              setMessage({ text: "API token cleared.", kind: "info" });
            }}
            onExport={async () => {
              try {
                const res = await api("/studio/snapshots/export?reason=studio", { method: "POST" });
                setSnapshotResult(`Exported ${res.source_count} sources to ${res.snapshot_path}`);
              } catch (err) {
                setSnapshotResult(err.message);
              }
            }}
            onImport={async () => {
              try {
                const res = await api("/studio/snapshots/import", {
                  method: "POST",
                  body: JSON.stringify({ snapshot_path: snapshotPath.trim() }),
                });
                setSnapshotResult(`Imported ${res.imported} sources.`);
                await loadLibrary();
              } catch (err) {
                setSnapshotResult(err.message);
              }
            }}
          />
        ) : null}
      </main>

      <SidebarChat
        open={sidebarChatOpen}
        source={selectedSourceDetail}
        messages={sidebarMessagesBySource[selectedSourceUid] || EMPTY_MESSAGES}
        onMessagesChange={(sourceUid, messages) => {
          if (!sourceUid) return;
          setSidebarMessagesBySource((prev) => ({ ...prev, [sourceUid]: messages }));
        }}
        onClose={() => setSidebarChatOpen(false)}
        onOpenBroadChat={({ source, draft }) => {
          setChatBridgeDraft({ source, draft });
          setSidebarChatOpen(false);
          navigate("chat");
        }}
      />

      <dialog ref={addDialogRef} id="add-dialog" aria-label="Add a URL" onCancel={() => setDialogOpen(false)} onClose={() => setDialogOpen(false)}>
        <form method="dialog" className="dialog-body" onSubmit={submitManualAdd}>
          <header>
            <h2>Add a URL</h2>
            <button type="button" className="icon-button" aria-label="Close" onClick={() => setDialogOpen(false)}>x</button>
          </header>
          <p className="caption">Adds a metadata-only catalog entry. Enqueue capture or brief if you want Epistora to fetch and compile.</p>
          <label>
            URL
            <input required type="url" placeholder="https://example.com/source" value={manualForm.url} onChange={(event) => setManualForm({ ...manualForm, url: event.target.value })} />
          </label>
          <label>
            Title <span className="caption">optional</span>
            <input type="text" placeholder="Optional title" value={manualForm.title} onChange={(event) => setManualForm({ ...manualForm, title: event.target.value })} />
          </label>
          <label>
            Tags <span className="caption">comma separated</span>
            <input type="text" placeholder="research, ml, history" value={manualForm.tags} onChange={(event) => setManualForm({ ...manualForm, tags: event.target.value })} />
          </label>
          <label>
            Action
            <select value={manualForm.action} onChange={(event) => setManualForm({ ...manualForm, action: event.target.value })}>
              <option value="">Add metadata only</option>
              <option value="capture">Capture</option>
              <option value="brief">Brief</option>
            </select>
          </label>
          <footer>
            <button type="button" className="ghost" onClick={() => setDialogOpen(false)}>Cancel</button>
            <button type="submit" className="primary">Add to library</button>
          </footer>
        </form>
      </dialog>
    </div>
  );
}

function LibraryView({ config, loading, sources, activeUid, onRefresh, onOpen }) {
  return (
    <section className="view is-active" aria-label="Library">
      <div className="library-meta">
        <p className="caption">{config.caption}</p>
        <div className="library-actions">
          <button className="ghost" type="button" onClick={onRefresh}>Refresh</button>
        </div>
      </div>
      <div className="library-list" role="list">
        {loading ? <Skeleton count={4} /> : null}
        {!loading && sources.length === 0 ? <div className="empty-state">{config.empty}</div> : null}
        {!loading ? sources.map((source) => (
          <SourceCard key={source.uid} source={source} active={source.uid === activeUid} onOpen={() => onOpen(source.uid)} />
        )) : null}
      </div>
    </section>
  );
}

function SourceCard({ source, active, onOpen }) {
  const title = source.title || source.url;
  const tags = (source.tag_snapshot || []).slice(0, 4);
  const provider = Object.keys(source.provider_snapshot || {})[0] || "";
  const priority = Math.round(source.priority_score || 0);
  const priorityClass = priority >= 50 ? "high" : "";
  const sourceType = source.source_type || "source";
  const preview = sourcePreview(source);
  return (
    <article
      className={`source-card has-source-preview ${active ? "is-active" : ""}`}
      tabIndex={0}
      role="listitem"
      onClick={onOpen}
      onKeyDown={(event) => {
        if (event.key === "Enter") onOpen();
      }}
    >
      <SourcePreview preview={preview} />
      <div className="card-header">
        <div className="card-eyebrow">
          <span>{label(sourceType)}</span>
          {provider ? <><span className="dot" /><span>{provider}</span></> : null}
          <span className="dot" />
          <span>{formatRelativeOrDate(source.saved_at || source.created_at)}</span>
        </div>
        <h2 className="card-title">{title}</h2>
        <p className="card-domain">{domainOf(source.url)}</p>
        {source.description ? <p className="card-description">{source.description}</p> : null}
        <div className="card-meta">
          <Tag kind={`kind-state-${source.display_state}`}>{label(source.display_state)}</Tag>
          {sourceType ? <Tag kind={`kind-type kind-source-${sourceType}`}>{sourceType}</Tag> : null}
          {provider ? <Tag kind={`kind-provider kind-provider-${provider}`}>{provider}</Tag> : null}
          {tags.map((tag) => <Tag key={tag} kind="kind-tag">{tag}</Tag>)}
        </div>
      </div>
      <div className={`priority-badge ${priorityClass}`} title={`Priority ${priority}`}>{priority}</div>
    </article>
  );
}

function SourcePreview({ preview }) {
  const fallback = !preview.thumb;
  return (
    <div className={`source-preview source-preview-${preview.sourceType} ${fallback ? "is-fallback" : "has-image"}`} aria-hidden="true">
      {preview.thumb ? <img src={preview.thumb} alt="" loading="lazy" /> : null}
      {fallback ? (
        <div className="preview-fallback">
          <span className="preview-mark">{preview.initials}</span>
          <span className="preview-lines">
            <i />
            <i />
            <i />
          </span>
        </div>
      ) : null}
      <span className="preview-label">{preview.title}</span>
      <span className="preview-host">{preview.host}</span>
    </div>
  );
}

function SourceView({ loading, detail, reader, readerMode, setReaderMode, onBack, onAction, onChat }) {
  if (loading) return <section className="view is-active" aria-label="Source detail"><div className="reader-frame"><Skeleton count={3} /></div></section>;
  if (!detail) return <section className="view is-active" aria-label="Source detail"><div className="empty-state">No source selected.</div></section>;

  const tags = detail.tag_snapshot || [];
  const refs = detail.provider_refs || [];
  const tabs = [
    { key: "note", label: "Compiled note", enabled: !!reader?.has_source_note },
    { key: "raw", label: "Raw capture", enabled: !!reader?.has_raw_capture },
    { key: "metadata", label: "Metadata", enabled: true },
    { key: "jobs", label: "Jobs", enabled: true },
  ];
  const noteText = reader?.source_body || stripFrontmatter(reader?.source_markdown || "");
  const rawText = reader?.raw_body || stripFrontmatter(reader?.raw_markdown || "");

  return (
    <section className="view is-active" aria-label="Source detail">
      <div className="reader-frame">
        <div className="reader-toolbar">
          <button className="ghost back" type="button" onClick={onBack}>Back to library</button>
          <div className="reader-actions">
            <button type="button" className="primary" onClick={onChat}>Chat</button>
            {["capture", "brief", "deep_compile", "refresh"].map((action) => (
              <button key={action} type="button" className={action === "refresh" ? "ghost" : ""} onClick={() => onAction(detail.uid, action)}>{label(action)}</button>
            ))}
            <a className="tag kind-provider" href={detail.url} target="_blank" rel="noreferrer">Original</a>
          </div>
        </div>

        <header className="reader-header">
          <div className="reader-eyebrow">
            <span>{label(detail.source_type || "source")}</span>
            {detail.site_name ? <><span className="dot" /><span>{detail.site_name}</span></> : null}
            {detail.published_date ? <><span className="dot" /><span>{detail.published_date}</span></> : null}
          </div>
          <h1 className="reader-title">{detail.title || detail.url}</h1>
          <p className="reader-byline">
            {detail.author ? `By ${detail.author} / ` : ""}
            <a href={detail.url} target="_blank" rel="noreferrer">{domainOf(detail.url)}</a>
          </p>
          <div className="card-meta">
            <Tag kind={`kind-state-${detail.display_state}`}>{label(detail.display_state)}</Tag>
            {detail.source_type ? <Tag kind={`kind-type kind-source-${detail.source_type}`}>{detail.source_type}</Tag> : null}
            {tags.map((tag) => <Tag key={tag} kind="kind-tag">{tag}</Tag>)}
          </div>
        </header>

        <nav className="reader-tabs" role="tablist">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              className={`reader-tab ${readerMode === tab.key ? "is-active" : ""}`}
              disabled={!tab.enabled}
              type="button"
              role="tab"
              onClick={() => tab.enabled && setReaderMode(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        {readerMode === "note" ? (
          <section className="reader-panel is-active">
            {reader?.has_source_note ? <Prose markdown={noteText} /> : <div className="empty-state">No compiled note yet. Run capture or brief to generate one.</div>}
          </section>
        ) : null}

        {readerMode === "raw" ? (
          <section className="reader-panel is-active">
            {reader?.has_raw_capture ? <Prose markdown={rawText} /> : <div className="empty-state">No raw capture stored for this source yet.</div>}
          </section>
        ) : null}

        {readerMode === "metadata" ? <MetadataPanel detail={detail} refs={refs} /> : null}
        {readerMode === "jobs" ? <section className="reader-panel is-active">{renderSourceJobs(detail.latest_jobs || [])}</section> : null}
      </div>
    </section>
  );
}

function MetadataPanel({ detail, refs }) {
  const tagRows = (detail.tags || []).map((tag) => <Tag key={tag.normalized_tag} kind="kind-tag">{tag.normalized_tag}</Tag>);
  return (
    <section className="reader-panel is-active">
      <div className="reader-meta-grid">
        <div className="card">
          <h2>Lifecycle</h2>
          <dl className="dl">
            <dt>Display state</dt><dd>{label(detail.display_state)}</dd>
            <dt>Metadata</dt><dd>{label(detail.metadata_status)}</dd>
            <dt>Content</dt><dd>{label(detail.content_status)}</dd>
            <dt>Brief</dt><dd>{label(detail.brief_status)}</dd>
            <dt>Deep</dt><dd>{label(detail.deep_status)}</dd>
            <dt>Output</dt><dd>{label(detail.output_status)}</dd>
            <dt>Failure</dt><dd>{label(detail.failure_status)}{detail.last_failure_reason ? ` - ${detail.last_failure_reason}` : ""}</dd>
          </dl>
        </div>
        <div className="card">
          <h2>Identity</h2>
          <dl className="dl">
            <dt>UID</dt><dd>{detail.uid}</dd>
            <dt>URL</dt><dd>{detail.url}</dd>
            {detail.canonical_url ? <><dt>Canonical</dt><dd>{detail.canonical_url}</dd></> : null}
            {detail.published_date ? <><dt>Published</dt><dd>{detail.published_date}</dd></> : null}
            {detail.author ? <><dt>Author</dt><dd>{detail.author}</dd></> : null}
            {detail.site_name ? <><dt>Site</dt><dd>{detail.site_name}</dd></> : null}
            <dt>Saved</dt><dd>{formatDate(detail.saved_at || detail.created_at)}</dd>
            <dt>Updated</dt><dd>{formatDate(detail.updated_at)}</dd>
          </dl>
        </div>
        <div className="card">
          <h2>Provider refs</h2>
          {refs.length ? (
            <dl className="dl">
              {refs.map((ref) => (
                <Fragment key={`${ref.provider}-${ref.external_id || ref.external_url}`}>
                  <dt>{ref.provider}</dt>
                  <dd>{ref.external_id || ref.external_url || "-"}</dd>
                </Fragment>
              ))}
            </dl>
          ) : <p className="caption">No provider references.</p>}
        </div>
        <div className="card">
          <h2>Tags</h2>
          <div className="card-meta">{tagRows.length ? tagRows : <span className="caption">No tags.</span>}</div>
        </div>
        <div className="card">
          <h2>Files</h2>
          <dl className="dl">
            <dt>Source note</dt><dd>{detail.source_note_path || "-"}</dd>
            <dt>Raw capture</dt><dd>{detail.raw_capture_path || "-"}</dd>
          </dl>
        </div>
      </div>
    </section>
  );
}

function renderSourceJobs(jobs) {
  if (!jobs.length) return <div className="empty-state">No jobs for this source yet. Use the buttons above to enqueue work.</div>;
  return <div className="reader-jobs">{jobs.map((job) => <JobRow key={job.job_uid} job={job} />)}</div>;
}

function JobRow({ job }) {
  return (
    <div className="job-row">
      <div className="job-title">
        <strong>{label(job.task_type)} <span className="muted">/ {job.mode}</span></strong>
        <span className="domain">{job.requested_by || "system"}{job.requested_reason ? ` / ${job.requested_reason}` : ""}</span>
      </div>
      <span className={`job-status ${job.status}`}>{label(job.status)}</span>
      <span className="muted">priority {Math.round(job.priority_score || 0)}</span>
      <span className="muted">attempt {job.attempt_count || 0}</span>
      <span className="muted">{formatRelativeOrDate(job.updated_at)}</span>
      <span className="job-error">{job.last_error || ""}</span>
    </div>
  );
}

function KnowledgeView({ loading, notes, detail, selectedPath, empty, onOpen }) {
  const tags = detail ? [
    ...(detail.topics || []),
    ...(detail.entities || []),
    ...(detail.concepts || []),
    ...(detail.tags || []),
  ] : [];
  return (
    <section className="view is-active" aria-label="Knowledge">
      <div className="knowledge-layout">
        <aside className="knowledge-list" aria-label="Knowledge notes">
          {loading ? <Skeleton count={4} /> : null}
          {!loading && notes.length === 0 ? <div className="empty-state">No notes yet.</div> : null}
          {!loading ? notes.map((note) => (
            <button key={note.note_path} type="button" className={`knowledge-item ${note.note_path === selectedPath ? "is-active" : ""}`} onClick={() => onOpen(note.note_path)}>
              {note.title}
              <span className="meta">{note.note_type}</span>
            </button>
          )) : null}
        </aside>
        <article className="knowledge-detail">
          {loading ? <p className="empty-note">Loading...</p> : null}
          {!loading && !detail ? <p className="empty-note">{empty}</p> : null}
          {detail ? (
            <>
              <div className="reader-eyebrow">
                <span>{detail.note_type}</span>
                <span className="dot" />
                <span>{detail.note_path}</span>
              </div>
              <h2 className="reader-title knowledge-title">{detail.title}</h2>
              {tags.length ? <div className="card-meta knowledge-tags">{tags.map((tag) => <Tag key={tag} kind="kind-tag">{tag}</Tag>)}</div> : null}
              <div className="knowledge-prose"><Prose markdown={detail.body || ""} /></div>
            </>
          ) : null}
        </article>
      </div>
    </section>
  );
}

function SearchView({ form, setForm, meta, hits, loading, onSearch, onOpenSource, onOpenNote }) {
  return (
    <section className="view is-active" aria-label="Search">
      <form
        className="search-shell"
        role="search"
        onSubmit={(event) => {
          event.preventDefault();
          onSearch(form.q.trim(), { sourceType: form.sourceType, displayState: form.displayState });
        }}
      >
        <input type="search" placeholder="Search the entire local studio" autoComplete="off" value={form.q} onChange={(event) => setForm({ ...form, q: event.target.value })} />
        <select value={form.sourceType} onChange={(event) => setForm({ ...form, sourceType: event.target.value })}>
          <option value="">All source types</option>
          <option value="article">Articles</option>
          <option value="youtube">Videos / YouTube</option>
          <option value="x_thread">Threads</option>
          <option value="pdf">PDFs</option>
          <option value="generic">Other</option>
        </select>
        <select value={form.displayState} onChange={(event) => setForm({ ...form, displayState: event.target.value })}>
          <option value="">Any lifecycle state</option>
          <option value="metadata_only">Metadata only</option>
          <option value="content_available">Captured</option>
          <option value="brief_ready">Brief ready</option>
          <option value="deep_compiled">Deep compiled</option>
          <option value="failed_partial">Failed partial</option>
          <option value="failed">Failed</option>
        </select>
        <button type="submit" className="primary">Search</button>
      </form>
      <p className="caption">{meta}</p>
      <div className="search-results">
        {loading ? <Skeleton count={3} /> : null}
        {!loading && !form.q.trim() ? <div className="empty-state">Type a query to search across the catalog and your knowledge notes.</div> : null}
        {!loading && form.q.trim() && hits.length === 0 ? <div className="empty-state">No matches. Try a different phrase.</div> : null}
        {!loading ? hits.map((hit, idx) => <SearchHit key={`${hit.kind}-${hit.source_uid || hit.note_path}-${idx}`} hit={hit} onOpenSource={onOpenSource} onOpenNote={onOpenNote} />) : null}
      </div>
    </section>
  );
}

function SearchHit({ hit, onOpenSource, onOpenNote }) {
  if (hit.kind === "source") {
    return (
      <article className="search-hit" onClick={() => onOpenSource(hit.source_uid)}>
        <div className="card-eyebrow">
          {(hit.provenance || []).map((p) => <span key={p} className="provenance">{p}</span>)}
          {hit.source_type ? <><span className="dot" /><span>{hit.source_type}</span></> : null}
          {hit.display_state ? <><span className="dot" /><span>{label(hit.display_state)}</span></> : null}
        </div>
        <h3 className="hit-title">{hit.title}</h3>
        <p className="card-domain">{domainOf(hit.url)}</p>
        {hit.snippet ? <p className="hit-snippet">{hit.snippet}</p> : null}
      </article>
    );
  }
  return (
    <article className="search-hit" onClick={() => onOpenNote(hit.note_type, hit.note_path)}>
      <div className="card-eyebrow">
        {(hit.provenance || []).map((p) => <span key={p} className="provenance">{p}</span>)}
        <span className="dot" /><span>{hit.note_type || "note"}</span>
      </div>
      <h3 className="hit-title">{hit.title}</h3>
      <p className="card-domain">{hit.note_path}</p>
      {hit.snippet ? <p className="hit-snippet">{hit.snippet}</p> : null}
    </article>
  );
}

function QueueView({ loading, stats, jobs, filter, onFilter, onProcess, onRefresh, onOpenSource }) {
  const jobCounts = stats?.queue_jobs || {};
  const itemCounts = stats?.queue_items || {};
  const metrics = [
    ["Queued", jobCounts.queued || 0],
    ["Running", jobCounts.running || 0],
    ["Completed", jobCounts.completed || 0],
    ["Failed", jobCounts.failed || 0],
    ["Discovered queue", itemCounts.discovered || 0],
    ["Retryable", itemCounts.retryable_failed || 0],
  ];
  return (
    <section className="view is-active" aria-label="Queue">
      <div className="metric-row">
        {metrics.map(([name, value]) => <div className="metric" key={name}><span>{name}</span><strong>{value}</strong></div>)}
      </div>
      <div className="queue-toolbar">
        <div className="chip-group" role="group" aria-label="Filter by job status">
          {["", "queued", "running", "completed", "failed"].map((status) => (
            <button key={status || "all"} className={`filter-chip ${filter === status ? "is-active" : ""}`} type="button" onClick={() => onFilter(status)}>
              {status || "All"}
            </button>
          ))}
        </div>
        <div className="queue-actions">
          <button type="button" className="primary" onClick={onProcess}>Process jobs once</button>
          <button type="button" className="ghost" onClick={onRefresh}>Refresh</button>
        </div>
      </div>
      <div className="jobs-list">
        {loading ? <Skeleton count={3} /> : null}
        {!loading && jobs.length === 0 ? <div className="empty-state">No source-linked jobs match this filter.</div> : null}
        {!loading ? jobs.map((job) => <QueueJobRow key={job.job_uid} job={job} onOpen={() => onOpenSource(job.source_uid)} />) : null}
      </div>
    </section>
  );
}

function QueueJobRow({ job, onOpen }) {
  const sourceTitle = job.source_title || job.source_url || job.source_uid;
  return (
    <div className="job-row" tabIndex={0} onClick={onOpen} onKeyDown={(event) => { if (event.key === "Enter") onOpen(); }}>
      <div className="job-title">
        <strong>{sourceTitle}</strong>
        <span className="domain">{domainOf(job.source_url || "")}</span>
      </div>
      <span>{label(job.task_type)}<br /><span className="muted">{job.mode}</span></span>
      <span className={`job-status ${job.status}`}>{label(job.status)}</span>
      <span className="muted">priority {Math.round(job.priority_score || 0)}</span>
      <span className="muted">attempt {job.attempt_count || 0}</span>
      <span className="muted">{formatRelativeOrDate(job.updated_at)}<br /><span className="job-error">{(job.last_error || "").slice(0, 90)}</span></span>
    </div>
  );
}

function SettingsView({ loading, runtime, stats, apiToken, setApiToken, snapshotPath, setSnapshotPath, snapshotResult, onSaveToken, onClearToken, onExport, onImport }) {
  const providers = (runtime?.configured_inbox_connectors || []).join(", ") || "none";
  const runtimeRows = runtime ? [
    ["Vault", runtime.vault_path],
    ["Vault exists", runtime.vault_exists ? "yes" : "no"],
    ["API auth", runtime.api_auth_enabled ? "enabled" : "disabled (localhost)"],
    ["Configured providers", providers],
    ["Backend model", runtime.model],
    ["Processed sources (legacy)", String(runtime.processed_sources ?? "-")],
  ] : [];
  const types = stats?.by_source_type || {};
  const typeBreakdown = Object.keys(types).length === 0 ? "-" : Object.entries(types).map(([key, value]) => `${key} ${value}`).join(", ");
  const catalogRows = stats ? [
    ["Total sources", stats.total_sources ?? 0],
    ["Metadata only", stats.metadata_only_sources ?? 0],
    ["Captured", stats.captured_sources ?? 0],
    ["Brief ready", stats.brief_ready_sources ?? 0],
    ["Deep compiled", stats.deep_compiled_sources ?? 0],
    ["Failed", stats.failed_sources ?? 0],
    ["By source type", typeBreakdown],
  ] : [];
  return (
    <section className="view is-active" aria-label="Settings">
      {loading ? <Skeleton count={2} /> : null}
      {!loading ? (
        <div className="settings-grid">
          <section className="card"><h2>Runtime</h2><DescriptionList rows={runtimeRows} /></section>
          <section className="card"><h2>Library snapshot</h2><DescriptionList rows={catalogRows} /></section>
          <section className="card">
            <h2>Catalog snapshot</h2>
            <p className="caption">Export a JSONL backup of your metadata-only catalog so manual URLs and provider data survive even if the operational DB is lost.</p>
            <div className="stack">
              <button type="button" onClick={onExport}>Export snapshot</button>
              <form className="row-form" onSubmit={(event) => { event.preventDefault(); onImport(); }}>
                <input type="text" placeholder="Snapshot JSONL path" value={snapshotPath} onChange={(event) => setSnapshotPath(event.target.value)} />
                <button type="submit" className="ghost">Import</button>
              </form>
              <p className="caption">{snapshotResult}</p>
            </div>
          </section>
          <section className="card">
            <h2>API token</h2>
            <p className="caption">Used by the browser when the local API key is set. Stored in browser localStorage only.</p>
            <form className="stack" onSubmit={(event) => { event.preventDefault(); onSaveToken(); }}>
              <input type="password" placeholder="Bearer token" value={apiToken} onChange={(event) => setApiToken(event.target.value)} />
              <div className="row-form">
                <button type="submit">Save token</button>
                <button type="button" className="ghost" onClick={onClearToken}>Clear</button>
              </div>
            </form>
          </section>
          <AIChatSettings />
        </div>
      ) : null}
    </section>
  );
}

function DescriptionList({ rows }) {
  return (
    <dl className="dl">
      {rows.map(([key, value]) => (
        <Fragment key={key}>
          <dt>{key}</dt>
          <dd>{value}</dd>
        </Fragment>
      ))}
    </dl>
  );
}
