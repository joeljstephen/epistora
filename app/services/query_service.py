"""High-level query service."""

from __future__ import annotations

from app.compiler.query_graph import get_query_graph
from app.config import get_settings
from app.models.results import QueryResult


async def query_vault(question: str, save_synthesis: bool = False) -> QueryResult:
    settings = get_settings()
    graph = get_query_graph()

    final_state = await graph.ainvoke(
        {
            "question": question,
            "vault_path": str(settings.vault_path),
            "save_synthesis": save_synthesis,
        }
    )

    result = final_state.get("result")
    if result:
        return result

    return QueryResult(
        question=question,
        answer="Query pipeline did not return a result.",
    )
