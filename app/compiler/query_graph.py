"""LangGraph query workflow — answers questions grounded in the vault."""

from __future__ import annotations

import logging
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.backends.models import TaskName
from app.compiler.llm import run_text
from app.compiler.prompts import QUERY_PROMPT, SYSTEM_ROLE
from app.models.results import QueryResult

logger = logging.getLogger(__name__)


class QueryState(TypedDict, total=False):
    question: str
    vault_path: str
    relevant_notes: list[dict]
    context: str
    answer: str
    source_references: list[str]
    note_titles: list[str]
    result: QueryResult
    save_synthesis: bool


async def _resolve_context(state: QueryState) -> dict:
    """Find relevant notes in the vault for the question."""
    from pathlib import Path

    from app.retrieval.search import search_vault

    vault_path = Path(state["vault_path"])
    question = state["question"]

    index_context_parts: list[str] = []
    index_dir = vault_path / "wiki" / "indexes"
    if index_dir.exists():
        for index_file in sorted(index_dir.glob("*.md")):
            preview = index_file.read_text(encoding="utf-8")[:2000].strip()
            if preview:
                index_context_parts.append(f"### index: {index_file.stem}\n{preview}\n")

    results = search_vault(vault_path, question, limit=15)

    context_parts: list[str] = list(index_context_parts)
    references: list[str] = []
    note_titles: list[str] = []

    for note_info in results:
        title = note_info.get("title", "")
        snippet = note_info.get("snippet", "")
        note_type = note_info.get("type", "")
        path = note_info.get("path", "")
        context_parts.append(f"### {note_type}: {title}\nPath: {path}\n{snippet}\n")
        if path:
            references.append(path)
        if title:
            note_titles.append(title)

    context = "\n".join(context_parts) if context_parts else "No relevant notes found in the vault."

    return {
        "relevant_notes": results,
        "context": context,
        "source_references": references,
        "note_titles": note_titles,
    }


async def _generate_answer(state: QueryState) -> dict:
    """Use the LLM to generate a grounded answer."""
    if not state.get("relevant_notes"):
        answer = (
            "Direct findings:\n"
            "- I could not find relevant notes in the vault for this question.\n\n"
            "Synthesis:\n"
            "- Ingest more sources or broaden the query terms."
        )
        return {"answer": answer}

    prompt = QUERY_PROMPT.format(
        question=state["question"],
        context=state["context"],
    )

    try:
        resp = await run_text(
            task=TaskName.QUERY,
            system_prompt=SYSTEM_ROLE,
            user_prompt=prompt,
        )
        if resp.success:
            answer = resp.text
            logger.info(
                "Query answered via %s (model=%s, fallback=%s)",
                resp.backend_used,
                resp.model_used,
                resp.was_fallback,
            )
        else:
            raise RuntimeError(resp.error)
    except Exception as e:
        logger.error("Query LLM call failed: %s", e)
        note_titles = state.get("note_titles", [])
        references = state.get("source_references", [])
        bullets = (
            "\n".join(f"- {title}" for title in note_titles[:8]) or "- No relevant notes found"
        )
        refs = "\n".join(f"- {ref}" for ref in references[:8]) or "- No source note paths available"
        answer = (
            "Direct findings:\n"
            f"{bullets}\n\n"
            "Synthesis:\n"
            f"- Automatic answer generation was unavailable: {e}\n"
            "- Review the referenced notes directly for grounded details.\n\n"
            "Note paths:\n"
            f"{refs}"
        )

    return {"answer": answer}


async def _maybe_save(state: QueryState) -> dict:
    """Optionally save the answer as a synthesis note or to outputs/."""
    from pathlib import Path

    from app.utils.dates import friendly_date
    from app.utils.slugify import slugify

    vault_path = Path(state["vault_path"])
    saved_to = None

    if state.get("save_synthesis"):
        slug = slugify(state["question"])
        out_path = vault_path / "outputs" / "answers" / f"{slug}.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        content = f"""# Query: {state["question"]}

> Generated: {friendly_date()}

{state["answer"]}

## Sources Consulted

"""
        for title, ref in zip(
            state.get("note_titles", []), state.get("source_references", []), strict=False
        ):
            content += f"- {title} (`{ref}`)\n"

        out_path.write_text(content, encoding="utf-8")
        saved_to = str(out_path.relative_to(vault_path))

    result = QueryResult(
        question=state["question"],
        answer=state["answer"],
        source_references=state.get("source_references", []),
        confidence="high" if len(state.get("relevant_notes", [])) >= 3 else "medium",
        saved_to=saved_to,
    )

    return {"result": result}


def build_query_graph() -> StateGraph:
    graph = StateGraph(QueryState)

    graph.add_node("resolve", _resolve_context)
    graph.add_node("generate", _generate_answer)
    graph.add_node("save", _maybe_save)

    graph.add_edge(START, "resolve")
    graph.add_edge("resolve", "generate")
    graph.add_edge("generate", "save")
    graph.add_edge("save", END)

    return graph


_compiled_graph = None


def get_query_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_query_graph().compile()
    return _compiled_graph
