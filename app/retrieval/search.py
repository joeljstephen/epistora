"""High-level vault search combining FTS, filename matching, and frontmatter."""

from __future__ import annotations

from pathlib import Path

from app.retrieval.indexer import VaultIndexer
from app.vault.parser import scan_vault


def search_vault(vault_path: Path, query: str, limit: int = 15) -> list[dict]:
    """Search the vault using FTS index with fallback to filename/frontmatter matching."""
    indexer = VaultIndexer(vault_path)

    try:
        indexer.rebuild()
    except Exception:
        pass

    results = indexer.search(query, limit=limit)
    if results:
        return results

    return _fallback_search(vault_path, query, limit)


def _fallback_search(vault_path: Path, query: str, limit: int) -> list[dict]:
    """Simple keyword matching when FTS fails or yields no results."""
    notes = scan_vault(vault_path)
    query_lower = query.lower()
    terms = query_lower.split()

    scored: list[tuple[float, dict]] = []

    for note in notes:
        if note.note_type == "raw":
            continue

        score = 0.0
        title_lower = note.title.lower()

        for term in terms:
            if term in title_lower:
                score += 3.0
            if term in " ".join(note.topics).lower():
                score += 2.0
            if term in note.body[:3000].lower():
                score += 1.0

        if score > 0:
            snippet = _extract_snippet(note.body, terms)
            scored.append(
                (
                    score,
                    {
                        "title": note.title,
                        "snippet": snippet,
                        "type": note.note_type,
                        "path": note.rel_path,
                    },
                )
            )

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:limit]]


def _extract_snippet(body: str, terms: list[str], window: int = 200) -> str:
    body_lower = body.lower()
    best_pos = -1
    for term in terms:
        pos = body_lower.find(term)
        if pos != -1:
            best_pos = pos
            break

    if best_pos == -1:
        return body[:window].replace("\n", " ").strip()

    start = max(0, best_pos - window // 2)
    end = min(len(body), best_pos + window // 2)
    snippet = body[start:end].replace("\n", " ").strip()
    return f"...{snippet}..." if start > 0 else f"{snippet}..."
