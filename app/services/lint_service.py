"""High-level lint service."""

from __future__ import annotations

from app.compiler.lint_graph import get_lint_graph
from app.config import get_settings
from app.models.results import LintResult


async def lint_vault() -> LintResult:
    settings = get_settings()
    graph = get_lint_graph()

    final_state = await graph.ainvoke(
        {
            "vault_path": str(settings.vault_path),
        }
    )

    result = final_state.get("result")
    if result:
        return result

    return LintResult()
