"""Rebuild and update vault index files."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent

from app.utils.dates import friendly_date
from app.utils.markdown import path_wikilink, wikilink
from app.vault import paths
from app.vault.parser import VaultNote, scan_vault


def _note_wikilink(note: VaultNote) -> str:
    rel = note.rel_path
    if rel.endswith(".md"):
        rel = rel[:-3]
    return f"[[{rel}|{note.title}]]"


def _find_note_by_title(notes: list[VaultNote], title: str) -> VaultNote | None:
    for note in notes:
        if note.title == title:
            return note
    return None


def rebuild_indexes(vault_path: Path) -> list[str]:
    notes = scan_vault(vault_path)
    updated: list[str] = []

    _write_obsidian_reader_snippet(vault_path)
    updated.append(_write_main_index(vault_path, notes))
    updated.append(_write_topics_index(vault_path, notes))
    updated.append(_write_entities_index(vault_path, notes))
    updated.append(_write_concepts_index(vault_path, notes))
    updated.append(_write_reading_home(vault_path, notes))
    updated.append(_write_videos_view(vault_path, notes))
    updated.append(_write_articles_view(vault_path, notes))
    updated.append(_write_topics_feed(vault_path, notes))
    updated.append(_write_start_here(vault_path, notes))
    updated.append(_write_query_protocol(vault_path, notes))
    updated.append(_write_dashboard(vault_path, notes))

    return updated


def _write_main_index(vault_path: Path, notes: list[VaultNote]) -> str:
    sources = [note for note in notes if note.note_type == "source"]
    raw_notes = [note for note in notes if note.note_type == "raw"]
    topics = [note for note in notes if note.note_type == "topic"]
    entities = [note for note in notes if note.note_type == "entity"]
    concepts = [note for note in notes if note.note_type == "concept"]
    synthesis = [note for note in notes if note.note_type == "synthesis"]

    source_type_counts = Counter(note.meta.get("source_type", "unknown") for note in sources)
    raw_kind_counts = Counter(
        (note.meta.get("raw_capture_kind") or "untyped_raw_capture") for note in raw_notes
    )
    topic_counts = _reference_counts(sources, "topics")

    lines = [
        "# Knowledge Vault Index",
        "",
        f"> Last rebuilt: {friendly_date()}",
        "",
        "## Stats",
        "",
        "| Type | Count |",
        "|------|-------|",
        f"| Source notes | {len(sources)} |",
        f"| Raw captures | {len(raw_notes)} |",
        f"| Topics | {len(topics)} |",
        f"| Entities | {len(entities)} |",
        f"| Concepts | {len(concepts)} |",
        f"| Synthesis | {len(synthesis)} |",
        "",
        "## Navigation",
        "",
        f"- {wikilink('TOPICS')}",
        f"- {wikilink('ENTITIES')}",
        f"- {wikilink('CONCEPTS')}",
        f"- {path_wikilink('wiki/logs/ingest-log.md', 'Ingest Log')}",
        f"- {path_wikilink('wiki/logs/lint-log.md', 'Lint Log')}",
        "",
        "## Layer Responsibilities",
        "",
        "- `raw/` stores immutable evidence captures.",
        "- `wiki/` stores compiled notes, maintained pages, indexes, and logs.",
        "- `outputs/` stores temporary or user-requested artifacts until promoted.",
        "",
        "## Source Breakdown",
        "",
    ]

    if source_type_counts:
        for source_type, count in sorted(source_type_counts.items()):
            lines.append(f"- `{source_type}`: {count}")
    else:
        lines.append("- _No source notes yet_")

    lines.extend(["", "## Raw Evidence Breakdown", ""])
    if raw_kind_counts:
        for raw_kind, count in sorted(raw_kind_counts.items()):
            lines.append(f"- `{raw_kind}`: {count}")
    else:
        lines.append("- _No raw captures yet_")

    lines.extend(["", "## Strongest Topic Areas", ""])
    if topic_counts:
        for topic, count in topic_counts.most_common(10):
            topic_note = _find_note_by_title(topics, topic)
            link = _note_wikilink(topic_note) if topic_note else wikilink(topic)
            lines.append(f"- {link} ({count} source note{'s' if count != 1 else ''})")
    else:
        lines.append("- _No topic references yet_")

    lines.extend(["", "## Recent Sources", ""])
    recent_sources = sorted(
        sources,
        key=lambda note: note.meta.get("ingested_at", ""),
        reverse=True,
    )[:20]
    if recent_sources:
        for note in recent_sources:
            source_type = note.meta.get("source_type", "unknown")
            quality = note.meta.get("extraction_quality", "unknown")
            raw_kind = note.meta.get("raw_capture_kind") or "untyped_raw_capture"
            lines.append(
                f"- {_note_wikilink(note)} — `{source_type}` / `{quality}` / raw `{raw_kind}`"
            )
    else:
        lines.append("- _No recent sources yet_")

    content = "\n".join(lines) + "\n"
    path = paths.index_path(vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path.relative_to(vault_path))


def _write_topics_index(vault_path: Path, notes: list[VaultNote]) -> str:
    topics = sorted(
        [note for note in notes if note.note_type == "topic"],
        key=lambda note: note.title.lower(),
    )
    topic_counts = _reference_counts(
        [note for note in notes if note.note_type == "source"],
        "topics",
    )
    lines = [f"# Topics Index\n\n> Last rebuilt: {friendly_date()}\n"]
    if topics:
        for note in topics:
            count = topic_counts.get(note.title, 0)
            suffix = "s" if count != 1 else ""
            lines.append(f"- {_note_wikilink(note)} ({count} source note{suffix})")
    else:
        lines.append("- _No topic pages yet_")
    path = paths.topics_index_path(vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path.relative_to(vault_path))


def _write_entities_index(vault_path: Path, notes: list[VaultNote]) -> str:
    entities = sorted(
        [note for note in notes if note.note_type == "entity"],
        key=lambda note: note.title.lower(),
    )
    entity_counts = _reference_counts(
        [note for note in notes if note.note_type == "source"],
        "entities",
    )
    lines = [f"# Entities Index\n\n> Last rebuilt: {friendly_date()}\n"]
    if entities:
        for note in entities:
            entity_type = note.meta.get("entity_type", "")
            label = f" ({entity_type})" if entity_type else ""
            count = entity_counts.get(note.title, 0)
            lines.append(
                f"- {_note_wikilink(note)}{label} ({count} source note{'s' if count != 1 else ''})"
            )
    else:
        lines.append("- _No entity pages yet_")
    path = paths.entities_index_path(vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path.relative_to(vault_path))


def _write_concepts_index(vault_path: Path, notes: list[VaultNote]) -> str:
    concepts = sorted(
        [note for note in notes if note.note_type == "concept"],
        key=lambda note: note.title.lower(),
    )
    concept_counts = _reference_counts(
        [note for note in notes if note.note_type == "source"],
        "concepts",
    )
    lines = [f"# Concepts Index\n\n> Last rebuilt: {friendly_date()}\n"]
    if concepts:
        for note in concepts:
            count = concept_counts.get(note.title, 0)
            suffix = "s" if count != 1 else ""
            lines.append(f"- {_note_wikilink(note)} ({count} source note{suffix})")
    else:
        lines.append("- _No concept pages yet_")
    path = paths.concepts_index_path(vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path.relative_to(vault_path))


def _reference_counts(source_notes: list[VaultNote], field: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for note in source_notes:
        for value in note.meta.get(field, []) or []:
            if value:
                counts[value] += 1
    return counts


def _source_notes(notes: list[VaultNote]) -> list[VaultNote]:
    return [note for note in notes if note.note_type == "source"]


def _parse_sort_dt(note: VaultNote) -> datetime:
    for field in ("saved_at", "ingested_at", "published_date"):
        raw = str(note.meta.get(field, "") or "").strip()
        parsed = _parse_dt(raw)
        if parsed is not None:
            return parsed
    return datetime.fromtimestamp(note.path.stat().st_mtime, tz=timezone.utc)


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized.endswith(" UTC"):
        normalized = normalized.removesuffix(" UTC")
        try:
            return datetime.strptime(normalized, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = datetime.strptime(normalized, "%Y-%m-%d")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _reading_state_rank(note: VaultNote) -> int:
    state = str(note.meta.get("reading_state", "") or "").strip().lower()
    return {
        "up_next": 0,
        "review": 1,
        "queued": 2,
        "brief_may_be_enough": 3,
    }.get(state, 4)


def _brief_rank(note: VaultNote) -> int:
    status = str(note.meta.get("brief_status", "") or "").strip().lower()
    return {
        "ready": 0,
        "partial": 1,
        "failed": 2,
    }.get(status, 2)


def _view_rank(note: VaultNote) -> tuple[int, int, float, str]:
    brief_rank = _brief_rank(note)
    state_rank = _reading_state_rank(note)
    timestamp = _parse_sort_dt(note).timestamp()
    return (brief_rank, state_rank, -timestamp, note.title.lower())


def _view_reason(note: VaultNote) -> str:
    reasons: list[str] = []
    brief_status = str(note.meta.get("brief_status", "") or "").strip()
    if brief_status == "ready":
        reasons.append("ready brief")
    elif brief_status == "partial":
        reasons.append("partial but usable")

    reading_state = str(note.meta.get("reading_state", "") or "").strip()
    if reading_state == "up_next":
        reasons.append("up next")
    elif reading_state == "review":
        reasons.append("flagged for review")
    elif reading_state == "queued":
        reasons.append("queued")

    theme_tags = note.meta.get("theme_tags", []) or []
    if theme_tags:
        reasons.append(f"matches {theme_tags[0]}")

    source_type = str(note.meta.get("source_type", "") or "").strip()
    if source_type == "youtube":
        reasons.append("video brief")
    elif source_type == "article":
        reasons.append("article brief")

    return ", ".join(reasons[:3]) or "recent source note"


def _quick_summary(note: VaultNote) -> str:
    summary = str(note.meta.get("quick_summary", "") or "").strip()
    if summary:
        return summary
    for line in note.body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith(">"):
            return stripped[:220]
    return "_No quick summary available._"


def _action_line(note: VaultNote) -> str:
    action = str(note.meta.get("best_next_action", "") or "").strip()
    if action:
        return action
    action = str(note.meta.get("consume_recommendation", "") or "").strip()
    if action:
        return action
    return "Use the brief first, then open the original only if you need more detail."


def _theme_counts(source_notes: list[VaultNote]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for note in source_notes:
        for value in note.meta.get("theme_tags", []) or []:
            if value:
                counts[str(value)] += 1
    return counts


def _write_view_page(vault_path: Path, path: Path, lines: list[str]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return str(path.relative_to(vault_path))


def _write_obsidian_reader_snippet(vault_path: Path) -> None:
    snippet_path = paths.obsidian_reader_snippet_path(vault_path)
    snippet_path.parent.mkdir(parents=True, exist_ok=True)
    snippet_path.write_text(_obsidian_reader_snippet_css().strip() + "\n", encoding="utf-8")


def _obsidian_reader_snippet_css() -> str:
    return dedent(
        """
        .epistora-reader-grid,
        .epistora-topic-grid,
        .epistora-theme-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
          gap: 1rem;
          margin: 1rem 0 0;
        }

        .epistora-reader-card,
        .epistora-topic-card,
        .epistora-theme-card {
          position: relative;
          overflow: hidden;
          padding: 1rem;
          border: 1px solid color-mix(in srgb, var(--background-modifier-border) 72%, transparent);
          border-radius: 18px;
          background:
            radial-gradient(circle at top right, color-mix(in srgb, var(--interactive-accent) 11%, transparent), transparent 34%),
            linear-gradient(160deg, color-mix(in srgb, var(--background-secondary) 94%, white 6%), var(--background-primary));
          box-shadow: 0 18px 40px rgba(15, 23, 42, 0.08);
        }

        .epistora-reader-card.is-up-next {
          border-color: color-mix(in srgb, var(--interactive-accent) 55%, var(--background-modifier-border));
          box-shadow: 0 20px 48px rgba(15, 23, 42, 0.12);
        }

        .epistora-reader-cover {
          height: 120px;
          margin: -1rem -1rem 0.9rem;
          border-radius: 18px 18px 12px 12px;
          background-position: center;
          background-size: cover;
          background-repeat: no-repeat;
          background-color: color-mix(in srgb, var(--background-secondary) 84%, black 16%);
        }

        .epistora-reader-cover.is-fallback {
          display: flex;
          align-items: flex-end;
          padding: 0.9rem;
          background:
            linear-gradient(135deg, color-mix(in srgb, var(--interactive-accent) 28%, transparent), transparent 72%),
            linear-gradient(160deg, color-mix(in srgb, var(--background-secondary) 90%, black 10%), var(--background-primary));
        }

        .epistora-reader-kicker {
          display: inline-flex;
          align-items: center;
          gap: 0.45rem;
          font-size: 0.72rem;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: var(--text-muted);
        }

        .epistora-reader-title,
        .epistora-topic-title {
          margin: 0.25rem 0 0.4rem;
          font-size: 1.05rem;
          line-height: 1.3;
        }

        .epistora-reader-title a,
        .epistora-topic-title a {
          color: var(--text-normal);
          text-decoration: none;
        }

        .epistora-reader-title a:hover,
        .epistora-topic-title a:hover {
          color: var(--interactive-accent);
        }

        .epistora-reader-byline,
        .epistora-reader-meta,
        .epistora-topic-meta {
          margin: 0;
          color: var(--text-muted);
          font-size: 0.82rem;
        }

        .epistora-reader-summary,
        .epistora-topic-summary {
          margin: 0.8rem 0;
          color: var(--text-normal);
          line-height: 1.5;
        }

        .epistora-reader-action {
          margin: 0.85rem 0 0;
          padding-top: 0.75rem;
          border-top: 1px solid color-mix(in srgb, var(--background-modifier-border) 72%, transparent);
          color: var(--text-normal);
          line-height: 1.45;
        }

        .epistora-chip-row {
          display: flex;
          flex-wrap: wrap;
          gap: 0.45rem;
          margin-top: 0.75rem;
        }

        .epistora-chip {
          display: inline-flex;
          align-items: center;
          border-radius: 999px;
          padding: 0.22rem 0.65rem;
          font-size: 0.75rem;
          background: color-mix(in srgb, var(--interactive-accent) 12%, var(--background-secondary));
          color: var(--text-muted);
        }

        .epistora-chip.is-theme {
          background: color-mix(in srgb, var(--color-green) 12%, var(--background-secondary));
        }

        .epistora-chip.is-count {
          background: color-mix(in srgb, var(--color-orange) 12%, var(--background-secondary));
        }

        .epistora-theme-list {
          display: flex;
          flex-wrap: wrap;
          gap: 0.55rem;
          margin-top: 0.75rem;
        }

        .epistora-theme-pill {
          display: inline-flex;
          align-items: center;
          gap: 0.4rem;
          border-radius: 999px;
          padding: 0.35rem 0.75rem;
          background: color-mix(in srgb, var(--interactive-accent) 10%, var(--background-secondary));
          color: var(--text-normal);
          font-size: 0.78rem;
        }
        """
    )


def _obsidian_reader_intro(view_name: str) -> list[str]:
    return [
        "## Obsidian Enhanced View",
        "",
        f"> [!tip] Reader-style `{view_name}`",
        "> Enable the Dataview plugin and the `epistora-reader-views.css` snippet",
        "> from `.obsidian/snippets/` to render the sections below as a richer browse UI.",
        "",
    ]


def _code_block(language: str, body: str) -> list[str]:
    return [f"```{language}", body.strip(), "```", ""]


def _obsidian_reader_card_block(*, source_type: str | None = None, limit: int = 20) -> str:
    source_filter = ""
    if source_type:
        source_filter = f' && (page.source_type ?? "") === "{source_type}"'
    return dedent(
        f"""
        const briefRank = {{ ready: 0, partial: 1, failed: 2 }};
        const stateRank = {{ up_next: 0, review: 1, queued: 2, brief_may_be_enough: 3 }};
        const fallbackAction = "Use the brief first, then open the original only if you need more detail.";

        const toArray = (value) => {{
          if (!value) return [];
          if (Array.isArray(value)) return value;
          if (typeof value.array === "function") return value.array();
          return [value];
        }};

        const toDateScore = (page) => {{
          const raw = page.saved_at ?? page.ingested_at ?? page.published_date ?? "";
          const parsed = Date.parse(raw);
          return Number.isNaN(parsed) ? 0 : parsed;
        }};

        const makeInternalLink = (parent, path, label) => {{
          const link = parent.createEl("a", {{ text: label, cls: "internal-link" }});
          link.setAttr("data-href", path);
          link.setAttr("href", path);
          return link;
        }};

        const pages = dv.pages('"wiki/sources"')
          .where((page) => (page.type ?? "") === "source" && (page.brief_status ?? "partial") !== "failed"{source_filter})
          .array()
          .sort((left, right) => {{
            const briefDelta =
              (briefRank[left.brief_status ?? "failed"] ?? 2) -
              (briefRank[right.brief_status ?? "failed"] ?? 2);
            if (briefDelta !== 0) return briefDelta;

            const stateDelta =
              (stateRank[left.reading_state ?? "unknown"] ?? 4) -
              (stateRank[right.reading_state ?? "unknown"] ?? 4);
            if (stateDelta !== 0) return stateDelta;

            return toDateScore(right) - toDateScore(left);
          }})
          .slice(0, {limit});

        if (!pages.length) {{
          dv.paragraph("_No readable source notes yet._");
        }} else {{
          const grid = dv.container.createDiv({{ cls: "epistora-reader-grid" }});

          pages.forEach((page, index) => {{
            const state = String(page.reading_state ?? "unknown");
            const type = String(page.source_type ?? "unknown");
            const card = grid.createDiv({{
              cls: `epistora-reader-card${{state === "up_next" ? " is-up-next" : ""}}`,
            }});

            if (page.cover_image) {{
              const cover = card.createDiv({{ cls: "epistora-reader-cover" }});
              cover.style.backgroundImage = `url("${{page.cover_image}}")`;
            }} else {{
              const cover = card.createDiv({{ cls: "epistora-reader-cover is-fallback" }});
              cover.createDiv({{
                cls: "epistora-reader-kicker",
                text: `${{type}} brief`,
              }});
            }}

            card.createDiv({{
              cls: "epistora-reader-kicker",
              text: `#${{index + 1}} · ${{type}} · ${{page.brief_status ?? "unknown"}}`,
            }});

            const title = card.createEl("h3", {{ cls: "epistora-reader-title" }});
            makeInternalLink(title, page.file.path, page.title ?? page.file.name);

            const bylineBits = [page.channel_or_author, page.published_date].filter(Boolean);
            if (bylineBits.length) {{
              card.createEl("p", {{
                cls: "epistora-reader-byline",
                text: bylineBits.join(" · "),
              }});
            }}

            const reasonBits = [];
            if (page.brief_status === "ready") reasonBits.push("ready brief");
            else if (page.brief_status === "partial") reasonBits.push("partial but usable");
            if (state === "up_next") reasonBits.push("up next");
            else if (state === "review") reasonBits.push("flagged for review");
            else if (state === "queued") reasonBits.push("queued");
            const themeTags = toArray(page.theme_tags).filter(Boolean).map(String);
            if (themeTags.length) reasonBits.push(`matches ${{themeTags[0]}}`);

            card.createEl("p", {{
              cls: "epistora-reader-meta",
              text: reasonBits.join(" · ") || "recent source note",
            }});

            card.createEl("p", {{
              cls: "epistora-reader-summary",
              text: String(page.quick_summary ?? "No quick summary available."),
            }});

            if (themeTags.length) {{
              const chips = card.createDiv({{ cls: "epistora-chip-row" }});
              themeTags.slice(0, 4).forEach((tag) => {{
                chips.createSpan({{ cls: "epistora-chip is-theme", text: tag }});
              }});
            }}

            card.createEl("p", {{
              cls: "epistora-reader-action",
              text: String(page.best_next_action ?? page.consume_recommendation ?? fallbackAction),
            }});
          }});
        }}
        """
    )


def _obsidian_topics_feed_block() -> str:
    return dedent(
        """
        const toArray = (value) => {
          if (!value) return [];
          if (Array.isArray(value)) return value;
          if (typeof value.array === "function") return value.array();
          return [value];
        };

        const makeInternalLink = (parent, path, label) => {
          const link = parent.createEl("a", { text: label, cls: "internal-link" });
          link.setAttr("data-href", path);
          link.setAttr("href", path);
          return link;
        };

        const sourcePages = dv.pages('"wiki/sources"')
          .where((page) => (page.type ?? "") === "source")
          .array();
        const topicPages = dv.pages('"wiki/topics"')
          .where((page) => (page.type ?? "") === "topic")
          .array();
        const topicMap = new Map(topicPages.map((page) => [String(page.title ?? page.file.name), page]));

        const topicClusters = new Map();
        const themeCounts = new Map();

        sourcePages.forEach((page) => {
          toArray(page.topics)
            .filter(Boolean)
            .map(String)
            .forEach((topic) => {
              const current = topicClusters.get(topic) ?? { count: 0, sources: [] };
              current.count += 1;
              current.sources.push(page);
              topicClusters.set(topic, current);
            });

          toArray(page.theme_tags)
            .filter(Boolean)
            .map(String)
            .forEach((theme) => {
              themeCounts.set(theme, (themeCounts.get(theme) ?? 0) + 1);
            });
        });

        const sortedTopics = [...topicClusters.entries()]
          .sort((left, right) => right[1].count - left[1].count)
          .slice(0, 12);
        const sortedThemes = [...themeCounts.entries()]
          .sort((left, right) => right[1] - left[1])
          .slice(0, 10);

        if (!sortedTopics.length) {
          dv.paragraph("_No topic clusters yet._");
        } else {
          const topicGrid = dv.container.createDiv({ cls: "epistora-topic-grid" });
          sortedTopics.forEach(([topic, payload]) => {
            const card = topicGrid.createDiv({ cls: "epistora-topic-card" });
            const title = card.createEl("h3", { cls: "epistora-topic-title" });
            const topicPage = topicMap.get(topic);
            if (topicPage) makeInternalLink(title, topicPage.file.path, topic);
            else title.setText(topic);

            card.createEl("p", {
              cls: "epistora-topic-meta",
              text: `${payload.count} source note${payload.count === 1 ? "" : "s"}`,
            });

            const summaries = payload.sources
              .slice()
              .sort((left, right) => String(left.title ?? "").localeCompare(String(right.title ?? "")))
              .slice(0, 3)
              .map((page) => String(page.title ?? page.file.name));

            card.createEl("p", {
              cls: "epistora-topic-summary",
              text: summaries.length
                ? `Representative sources: ${summaries.join(", ")}`
                : "No representative sources yet.",
            });
          });
        }

        const section = dv.container.createDiv({ cls: "epistora-theme-list" });
        if (!sortedThemes.length) {
          section.createSpan({ text: "No stable theme tags yet." });
        } else {
          sortedThemes.forEach(([theme, count]) => {
            const pill = section.createSpan({ cls: "epistora-theme-pill" });
            pill.createSpan({ text: theme });
            pill.createSpan({ text: `${count}` });
          });
        }
        """
    )


def _write_reading_home(vault_path: Path, notes: list[VaultNote]) -> str:
    source_notes = [
        note for note in _source_notes(notes) if str(note.meta.get("brief_status", "") or "partial") != "failed"
    ]
    ranked = sorted(source_notes, key=_view_rank)[:20]
    lines = [
        "# Reading Home",
        "",
        f"> Last rebuilt: {friendly_date()}",
        "",
        "This page is a deterministic reading feed built from source-note metadata.",
        "",
        "## What To Look At Next",
        "",
    ]

    if not ranked:
        lines.append("- _No readable source notes yet._")
    else:
        for note in ranked:
            lines.extend(
                [
                    f"### {_note_wikilink(note)}",
                    "",
                    f"- **Reason:** {_view_reason(note)}",
                    f"- **Type:** `{note.meta.get('source_type', 'unknown')}`",
                    f"- **Reading state:** `{note.meta.get('reading_state', 'unknown')}`",
                    f"- **Theme tags:** {', '.join(note.meta.get('theme_tags', []) or []) or 'none'}",
                    f"- **Quick summary:** {_quick_summary(note)}",
                    f"- **Best next action:** {_action_line(note)}",
                    "",
                ]
            )

    lines.extend(_obsidian_reader_intro("READING_HOME"))
    lines.extend(_code_block("dataviewjs", _obsidian_reader_card_block(limit=20)))
    return _write_view_page(vault_path, paths.reading_home_path(vault_path), lines)


def _write_source_type_view(
    *,
    vault_path: Path,
    notes: list[VaultNote],
    source_type: str,
    title: str,
    path: Path,
) -> str:
    source_notes = [note for note in _source_notes(notes) if note.meta.get("source_type") == source_type]
    ranked = sorted(source_notes, key=_view_rank)
    lines = [
        f"# {title}",
        "",
        f"> Last rebuilt: {friendly_date()}",
        "",
        f"This page lists `{source_type}` source notes ordered by brief readiness and freshness.",
        "",
    ]
    if not ranked:
        lines.append(f"- _No {source_type} source notes yet._")
        return _write_view_page(vault_path, path, lines)

    lines.extend(["| Source | Brief | Reading State | Why Surface It |", "|--------|-------|---------------|-----------------|"])
    for note in ranked[:30]:
        lines.append(
            "| "
            + " | ".join(
                [
                    _note_wikilink(note),
                    str(note.meta.get("brief_status", "unknown") or "unknown"),
                    str(note.meta.get("reading_state", "unknown") or "unknown"),
                    _view_reason(note),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Highlights", ""])
    for note in ranked[:8]:
        lines.extend(
            [
                f"### {_note_wikilink(note)}",
                "",
                f"- **Quick summary:** {_quick_summary(note)}",
                f"- **Best next action:** {_action_line(note)}",
                "",
            ]
        )
    lines.extend(_obsidian_reader_intro(title.upper().replace(" ", "_")))
    lines.extend(
        _code_block(
            "dataviewjs",
            _obsidian_reader_card_block(source_type=source_type, limit=30),
        )
    )
    return _write_view_page(vault_path, path, lines)


def _write_videos_view(vault_path: Path, notes: list[VaultNote]) -> str:
    return _write_source_type_view(
        vault_path=vault_path,
        notes=notes,
        source_type="youtube",
        title="Videos",
        path=paths.videos_index_path(vault_path),
    )


def _write_articles_view(vault_path: Path, notes: list[VaultNote]) -> str:
    return _write_source_type_view(
        vault_path=vault_path,
        notes=notes,
        source_type="article",
        title="Articles",
        path=paths.articles_index_path(vault_path),
    )


def _write_topics_feed(vault_path: Path, notes: list[VaultNote]) -> str:
    source_notes = _source_notes(notes)
    topics = [note for note in notes if note.note_type == "topic"]
    topic_counts = _reference_counts(source_notes, "topics")
    theme_counts = _theme_counts(source_notes)
    lines = [
        "# Topics Feed",
        "",
        f"> Last rebuilt: {friendly_date()}",
        "",
        "This page shows active topic clusters and stable themes emerging from source-note metadata.",
        "",
        "## Active Topic Clusters",
        "",
    ]

    if topic_counts:
        for topic_name, count in topic_counts.most_common(12):
            topic_note = _find_note_by_title(topics, topic_name)
            link = _note_wikilink(topic_note) if topic_note else wikilink(topic_name)
            representative = [
                _note_wikilink(note)
                for note in sorted(source_notes, key=_view_rank)
                if topic_name in (note.meta.get("topics", []) or [])
            ][:3]
            lines.append(f"### {link}")
            lines.append("")
            lines.append(f"- **Sources in cluster:** {count}")
            if representative:
                lines.append(f"- **Representative sources:** {', '.join(representative)}")
            lines.append("")
    else:
        lines.append("- _No topic clusters yet._")

    lines.extend(["## Theme Watchlist", ""])
    if theme_counts:
        for theme, count in theme_counts.most_common(10):
            lines.append(f"- `{theme}` ({count} source note{'s' if count != 1 else ''})")
    else:
        lines.append("- _No stable theme tags yet._")

    lines.extend(_obsidian_reader_intro("TOPICS_FEED"))
    lines.extend(_code_block("dataviewjs", _obsidian_topics_feed_block()))
    return _write_view_page(vault_path, paths.topics_feed_path(vault_path), lines)


def _write_start_here(vault_path: Path, notes: list[VaultNote]) -> str:
    sources = [n for n in notes if n.note_type == "source"]
    topics = [n for n in notes if n.note_type == "topic"]
    entities = [n for n in notes if n.note_type == "entity"]
    concepts = [n for n in notes if n.note_type == "concept"]
    synthesis = [n for n in notes if n.note_type == "synthesis"]
    raw_notes = [n for n in notes if n.note_type == "raw"]

    strong_topics = _reference_counts(sources, "topics").most_common(5)
    strong_entities = _reference_counts(sources, "entities").most_common(5)

    lines = [
        "# Start Here — Vault Orientation",
        "",
        f"> Last rebuilt: {friendly_date()}",
        "",
        "This file is the entry point for agents and humans navigating this vault.",
        "Read this first, then use the indexes and hub pages to find what you need.",
        "",
        "## Vault Layers",
        "",
        "| Layer | Location | Purpose | Trust Level |",
        "|-------|----------|---------|-------------|",
        "| Evidence | `raw/` | Immutable source captures | Escalation only |",
        "| Knowledge | `wiki/` | Compiled, maintained notes | Primary |",
        "| Scratch | `outputs/` | Temporary or user-requested artifacts | Unverified |",
        "",
        "## Current Vault Stats",
        "",
        f"- **{len(sources)}** source notes",
        f"- **{len(raw_notes)}** raw captures",
        f"- **{len(topics)}** topic pages",
        f"- **{len(entities)}** entity pages",
        f"- **{len(concepts)}** concept pages",
        f"- **{len(synthesis)}** synthesis notes",
        "",
        "## How to Route Your Question",
        "",
        "| Question Type | Start At | Then Read |",
        "|---------------|----------|-----------|",
        "| Topic overview | TOPICS.md | Topic page → source notes |",
        "| Specific claim | INDEX.md | Source notes w/ keywords |",
        "| Entity profile | ENTITIES.md | Entity page → source list |",
        "| Concept def | CONCEPTS.md | Concept page → examples |",
        "| Comparison | Both pages | Source notes for each side |",
        "| Gap analysis | All indexes | Note what is thin |",
        "| Learning path | Topic page | Suggested reading section |",
        "",
        "## Strongest Topic Areas",
        "",
    ]

    if strong_topics:
        for topic_name, count in strong_topics:
            topic_note = _find_note_by_title(topics, topic_name)
            link = _note_wikilink(topic_note) if topic_note else wikilink(topic_name)
            lines.append(f"- {link} ({count} sources)")
    else:
        lines.append("- _No topic references yet — ingest sources to build the vault_")

    lines.extend(["", "## Most-Referenced Entities", ""])

    if strong_entities:
        for entity_name, count in strong_entities:
            entity_note = _find_note_by_title(entities, entity_name)
            link = _note_wikilink(entity_note) if entity_note else wikilink(entity_name)
            lines.append(f"- {link} ({count} sources)")
    else:
        lines.append("- _No entity references yet_")

    lines.extend(
        [
            "",
            "## Navigation Files",
            "",
            f"- {wikilink('AGENTS')} — Full operating manual and conventions",
            f"- {wikilink('QUERY_PROTOCOL')} — Step-by-step query procedure",
            f"- {wikilink('INDEX')} — Complete vault index with stats",
            f"- {wikilink('TOPICS')} — All topic pages",
            f"- {wikilink('ENTITIES')} — All entity pages",
            f"- {wikilink('CONCEPTS')} — All concept pages",
            f"- {path_wikilink('wiki/logs/ingest-log.md', 'Ingest Log')}",
            "  — What was ingested and when",
            "",
            "## Quick Rules",
            "",
            "- Read source notes (`wiki/sources/`) first for grounded evidence",
            "- Use topic/entity/concept pages as routing hubs",
            "- Only read raw captures (`raw/`) when evidence quality is weak or exact text matters",
            "- Ignore `.system/` — it is internal state, not knowledge",
            "- Structure answers with: Direct Findings, "
            "Cross-Source Synthesis, Gaps, Relevant Notes",
            "",
        ]
    )

    content = "\n".join(lines)
    path = paths.start_here_path(vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path.relative_to(vault_path))


def _write_query_protocol(vault_path: Path, notes: list[VaultNote]) -> str:
    lines = [
        "# Query Protocol — Standard Agent Procedure",
        "",
        f"> Last rebuilt: {friendly_date()}",
        "",
        "This file defines the standard procedure for answering knowledge questions",
        "from this vault. Follow these steps in order.",
        "",
        "## Step 1: Orient",
        "",
        "Read these files first:",
        "",
        "1. `AGENTS.md` — vault conventions and operating manual",
        "2. `wiki/indexes/START_HERE.md` — vault orientation and routing",
        "3. `wiki/indexes/INDEX.md` — full vault overview",
        "",
        "## Step 2: Classify the Question",
        "",
        "Identify which type of question this is:",
        "",
        "- **Topic overview** — broad subject question → start at TOPICS.md",
        "- **Comparison** — how X and Y relate → find both topic/entity pages",
        "- **Evidence lookup** — specific claim → search source notes directly",
        "- **Gap analysis** — what is missing → scan all indexes for thin areas",
        "- **Entity profile** — person/company/tool → start at ENTITIES.md",
        "- **Learning path** — what to read next → topic page → suggested reading",
        "",
        "## Step 3: Find Candidate Notes",
        "",
        "Use the index files to identify relevant notes:",
        "",
        "1. Read `wiki/indexes/TOPICS.md` for topic matches",
        "2. Read `wiki/indexes/ENTITIES.md` for entity matches",
        "3. Read `wiki/indexes/CONCEPTS.md` for concept matches",
        "4. Read `wiki/indexes/INDEX.md` for recent sources that may be relevant",
        "",
        "## Step 4: Read Frontmatter Before Body",
        "",
        "For each candidate note, read only the YAML frontmatter first. Check:",
        "",
        "- `type` — is this the right note type?",
        "- `topics`, `entities`, `concepts` — does it match the question?",
        "- `extraction_quality` — how reliable is the evidence?",
        "- `source_url` — is this the right source?",
        "- `raw_capture_path` — where is the underlying evidence?",
        "",
        "Only read the full body for notes that pass this filter.",
        "",
        "## Step 5: Read Hub Pages",
        "",
        "Read relevant topic, entity, or concept pages. These pages serve as hubs:",
        "",
        "- They accumulate knowledge across multiple sources",
        "- They contain `[[wikilinks]]` to related source notes",
        "- They surface recurring patterns and contradictions",
        "",
        "## Step 6: Read Source Notes",
        "",
        "Source notes are the primary evidence. For each relevant source note:",
        "",
        "1. Check `Coverage & Limits` section for extraction quality",
        "2. Read `Key Ideas` and `Detailed Outline` for quick orientation",
        "3. Read `5-Minute Read` or `Detailed Reading Note` for depth",
        "4. Check `Open Questions` for unresolved issues",
        "5. Follow `[[wikilinks]]` in `Related Notes` for more context",
        "",
        "## Step 7: Escalate to Raw Captures (Only If Needed)",
        "",
        "Read raw captures ONLY when:",
        "",
        "- The source note has `extraction_quality` of `partial`, `metadata_only`, or `failed`",
        "- You need exact wording or exact evidence",
        "- The compiled note seems too compressed or missing details",
        "- You want to verify a specific claim against the original text",
        "",
        "Do NOT read raw captures by default. They are large and mostly redundant",
        "with the compiled source notes.",
        "",
        "## Step 8: Check Synthesis Notes",
        "",
        "If `wiki/synthesis/` contains relevant notes, read them. These represent",
        "prior cross-source work. Check their `Source Basis` section for grounding.",
        "",
        "## Step 9: Structure Your Answer",
        "",
        "Use this standard structure for all knowledge answers:",
        "",
        "```",
        "## Direct Findings",
        "- Grounded claims with explicit source references",
        "",
        "## Cross-Source Synthesis",
        "- Patterns, agreements, or tensions across sources",
        "",
        "## Gaps / Open Questions",
        "- What the vault does not cover or where evidence is weak",
        "",
        "## Relevant Notes to Read Next",
        "- Note paths or [[wikilinks]] for follow-up",
        "```",
        "",
        "## Answer Rules",
        "",
        "1. Ground every claim in a specific source note or raw capture",
        "2. Surface contradictions — do not smooth them away",
        "3. Note uncertainty when evidence quality is weak",
        "4. Do not invent evidence — state what is missing",
        "5. Reference notes by path or wikilink",
        "6. Distinguish direct findings from synthesis or inference",
        "",
        "## Evidence Trust Order",
        "",
        "1. Compiled source notes (`wiki/sources/`) — primary evidence",
        "2. Synthesis notes (`wiki/synthesis/`) — prior cross-source work",
        "3. Hub pages (`wiki/topics/`, `wiki/entities/`, `wiki/concepts/`) — routing + patterns",
        "4. Raw captures (`raw/`) — escalation evidence only",
        "",
        "## What Not To Do",
        "",
        "- Do not read `.system/` for knowledge answers",
        "- Do not treat `outputs/` as canonical wiki pages",
        "- Do not edit raw captures",
        "- Do not make claims unsupported by the vault evidence",
        "- Do not pad answers with generic filler when evidence is thin",
        "",
    ]

    content = "\n".join(lines)
    path = paths.query_protocol_path(vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path.relative_to(vault_path))


def _write_dashboard(vault_path: Path, notes: list[VaultNote]) -> str:
    sources = [n for n in notes if n.note_type == "source"]
    raw_notes = [n for n in notes if n.note_type == "raw"]
    topics = [n for n in notes if n.note_type == "topic"]
    entities = [n for n in notes if n.note_type == "entity"]
    concepts = [n for n in notes if n.note_type == "concept"]
    synthesis = [n for n in notes if n.note_type == "synthesis"]

    source_by_type: dict[str, list[VaultNote]] = {}
    for note in sources:
        stype = note.meta.get("source_type", "unknown")
        source_by_type.setdefault(stype, []).append(note)

    topic_counts = _reference_counts(sources, "topics")
    entity_counts = _reference_counts(sources, "entities")
    concept_counts = _reference_counts(sources, "concepts")

    source_type_labels = {
        "youtube": "Videos",
        "article": "Articles",
        "x_thread": "Threads",
        "pdf": "PDFs",
        "generic": "Misc",
    }

    lines = [
        "---",
        "cssclasses: [dashboard]",
        "---",
        "",
        "# Knowledge Vault",
        "",
        f"> Last updated: {friendly_date()}",
        "",
        "---",
        "",
    ]

    lines.extend(_dashboard_stats_section(sources, raw_notes, topics, entities, concepts, synthesis))

    lines.extend(["---", ""])
    lines.extend(_dashboard_quick_nav())

    lines.extend(["---", ""])
    lines.extend(_dashboard_source_browser(source_by_type, source_type_labels, vault_path))

    lines.extend(["---", ""])
    lines.extend(_dashboard_recent_sources(sources))

    lines.extend(["---", ""])
    lines.extend(_dashboard_top_section("Top Topics", topic_counts, topics, 10))

    lines.extend(["---", ""])
    lines.extend(_dashboard_top_section("Top Entities", entity_counts, entities, 10))

    lines.extend(["---", ""])
    lines.extend(_dashboard_top_section("Top Concepts", concept_counts, concepts, 10))

    content = "\n".join(lines) + "\n"
    path = paths.dashboard_path(vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path.relative_to(vault_path))


def _dashboard_stats_section(
    sources: list[VaultNote],
    raw_notes: list[VaultNote],
    topics: list[VaultNote],
    entities: list[VaultNote],
    concepts: list[VaultNote],
    synthesis: list[VaultNote],
) -> list[str]:
    return [
        "> [!info] Vault Overview",
        f"> **{len(sources)}** sources | **{len(raw_notes)}** raw captures | **{len(topics)}** topics | **{len(entities)}** entities | **{len(concepts)}** concepts | **{len(synthesis)}** synthesis notes",
        "",
    ]


def _dashboard_quick_nav() -> list[str]:
    return [
        "> [!tip] Quick Navigation",
        "> [[#Sources]] | [[#Recent Sources]] | [[#Top Topics]] | [[#Top Entities]] | [[#Top Concepts]]",
        "> [[INDEX]] | [[TOPICS]] | [[ENTITIES]] | [[CONCEPTS]] | [[START_HERE]] | [[QUERY_PROTOCOL]]",
        "> [[wiki/logs/ingest-log|Ingest Log]] | [[wiki/logs/lint-log|Lint Log]]",
        "",
    ]


def _dashboard_source_browser(
    source_by_type: dict[str, list[VaultNote]],
    source_type_labels: dict[str, str],
    vault_path: Path,
) -> list[str]:
    lines = [
        "## Sources",
        "",
    ]

    source_dir_links = {
        "youtube": "wiki/sources/videos",
        "article": "wiki/sources/articles",
        "x_thread": "wiki/sources/threads",
        "pdf": "wiki/sources/pdfs",
        "generic": "wiki/sources/misc",
    }
    raw_dir_links = {
        "youtube": "raw/videos",
        "article": "raw/articles",
        "x_thread": "raw/threads",
        "pdf": "raw/pdfs",
        "generic": "raw/misc",
    }

    for stype in ["youtube", "article", "x_thread", "pdf", "generic"]:
        count = len(source_by_type.get(stype, []))
        if count == 0:
            continue
        label = source_type_labels.get(stype, stype.capitalize())
        source_dir = source_dir_links.get(stype, "wiki/sources/misc")
        raw_dir = raw_dir_links.get(stype, "raw/misc")
        lines.append(f"### {label}")
        lines.append("")
        lines.append(
            f"**{count}** sources | "
            f"{path_wikilink(f'{source_dir}', 'Compiled Notes')} | "
            f"{path_wikilink(f'{raw_dir}', 'Raw Captures')}"
        )
        lines.append("")

        stype_sources = sorted(
            source_by_type.get(stype, []),
            key=lambda n: n.meta.get("ingested_at", ""),
            reverse=True,
        )[:8]
        for note in stype_sources:
            lines.append(f"- {_note_wikilink(note)}")
        lines.append("")

    return lines


def _dashboard_recent_sources(sources: list[VaultNote]) -> list[str]:
    lines = [
        "## Recent Sources",
        "",
    ]

    recent = sorted(
        sources,
        key=lambda n: n.meta.get("ingested_at", ""),
        reverse=True,
    )[:15]

    if not recent:
        lines.append("_No sources yet._")
        lines.append("")
        return lines

    lines.append("| Source | Type | Quality | Ingested |")
    lines.append("|--------|------|---------|----------|")
    for note in recent:
        stype = note.meta.get("source_type", "unknown")
        quality = note.meta.get("extraction_quality", "unknown")
        ingested = note.meta.get("ingested_at", "")
        if ingested:
            ingested = ingested.replace(" UTC", "").strip()
        lines.append(f"| {_note_wikilink(note)} | {stype} | {quality} | {ingested} |")

    lines.append("")
    return lines


def _dashboard_top_section(
    title: str,
    ref_counts: Counter[str],
    all_notes: list[VaultNote],
    limit: int,
) -> list[str]:
    lines = [
        f"## {title}",
        "",
    ]

    top = ref_counts.most_common(limit)
    if not top:
        lines.append("_None yet._")
        lines.append("")
        return lines

    lines.append(f"| Name | Sources |")
    lines.append(f"|------|---------|")
    for name, count in top:
        note = _find_note_by_title(all_notes, name)
        link = _note_wikilink(note) if note else wikilink(name)
        lines.append(f"| {link} | {count} |")

    lines.extend(["", f"> _{len(all_notes)} total — see [[{title.replace('Top ', '').upper()}]] for the full list._", ""])
    return lines
