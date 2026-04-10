"""High-level query service."""

from __future__ import annotations

import logging
from pathlib import Path

from app.backends.models import TaskName
from app.compiler.llm import run_text
from app.compiler.prompts import compose_query_prompt
from app.config import get_settings
from app.events import EventType, publish
from app.models.results import QueryResult
from app.retrieval import RetrievalContext, build_retrieval_context
from app.utils.dates import friendly_date
from app.utils.slugify import slugify

logger = logging.getLogger(__name__)


async def query_vault(question: str, save_synthesis: bool = False) -> QueryResult:
    settings = get_settings()
    vault_path = Path(settings.vault_path)
    retrieval = _resolve_context(vault_path=vault_path, question=question)
    answer = await _generate_answer(vault_path=vault_path, retrieval=retrieval)
    saved_to = _maybe_save(
        vault_path=vault_path,
        question=question,
        answer=answer,
        references=retrieval.source_references,
        save_synthesis=save_synthesis,
    )
    return QueryResult(
        question=question,
        answer=answer,
        source_references=retrieval.source_references,
        topics_consulted=retrieval.topics_consulted,
        confidence=_confidence_label(retrieval),
        saved_to=saved_to,
    )


def _resolve_context(*, vault_path: Path, question: str) -> RetrievalContext:
    return build_retrieval_context(vault_path, question)


async def _generate_answer(*, vault_path: Path, retrieval: RetrievalContext) -> str:
    if not retrieval.artifacts:
        return (
            "## Direct Findings\n"
            "- I could not find relevant notes in the vault for this question.\n\n"
            "## Cross-Source Synthesis\n"
            "- No supported synthesis is possible yet from the current vault context.\n\n"
            "## Contradictions / Uncertainty\n"
            "- The main limitation is missing relevant source material.\n\n"
            "## Gaps / Open Questions\n"
            "- Ingest more sources or broaden the query terms.\n\n"
            "## Useful Next Notes\n"
            "- Add or ingest sources directly related to the question."
        )

    composition = compose_query_prompt(
        workspace_path=vault_path,
        format_kwargs={
            "question": retrieval.question,
            "context": retrieval.text_context,
        },
    )

    try:
        resp = await run_text(
            task=TaskName.QUERY,
            system_prompt=composition.system_prompt,
            user_prompt=composition.user_prompt,
        )
        if resp.success:
            logger.info(
                "Query answered via %s (model=%s, fallback=%s)",
                resp.backend_used,
                resp.model_used,
                resp.was_fallback,
            )
            return resp.text
        raise RuntimeError(resp.error)
    except Exception as exc:
        logger.error("Query LLM call failed: %s", exc)
        bullets = (
            "\n".join(f"- {artifact.note.title}" for artifact in retrieval.artifacts[:8])
            or "- No relevant notes found"
        )
        refs = (
            "\n".join(f"- {ref}" for ref in retrieval.source_references[:8])
            or "- No source note paths available"
        )
        return (
            "## Direct Findings\n"
            f"{bullets}\n\n"
            "## Cross-Source Synthesis\n"
            f"- Automatic answer generation was unavailable: {exc}\n"
            "- Review the referenced notes directly for grounded details.\n\n"
            "## Contradictions / Uncertainty\n"
            "- This fallback answer is incomplete because the reasoning backend "
            "was unavailable.\n\n"
            "## Gaps / Open Questions\n"
            "- Which of the referenced notes best answers the question?\n"
            "- Do those notes agree, or do they need a synthesis pass?\n\n"
            "## Useful Next Notes\n"
            "- Review or promote the strongest relevant source notes.\n"
            "- If the answer matters long term, save a synthesis note after review.\n\n"
            "Referenced note paths:\n"
            f"{refs}"
        )


def _maybe_save(
    *,
    vault_path: Path,
    question: str,
    answer: str,
    references: list[str],
    save_synthesis: bool,
) -> str | None:
    if not save_synthesis:
        return None

    out_path = vault_path / "outputs" / "answers" / f"{slugify(question)}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        f"# Query: {question}\n\n"
        f"> Generated: {friendly_date()}\n"
        "> This file is an output-layer artifact.\n"
        "> Promote durable material into `wiki/synthesis/` if it becomes generally useful.\n\n"
        f"{answer}\n\n"
        "## Sources Consulted\n\n"
    )
    for ref in references:
        content += f"- `{ref}`\n"
    out_path.write_text(content, encoding="utf-8")
    publish(
        EventType.QUERY_ANSWER_SAVED,
        question=question,
        saved_to=str(out_path.relative_to(vault_path)),
        source_references=references,
    )
    return str(out_path.relative_to(vault_path))


def _confidence_label(retrieval: RetrievalContext) -> str:
    if len(retrieval.artifacts) >= 5:
        return "high"
    if len(retrieval.artifacts) >= 2:
        return "medium"
    return "low"
