import pytest
from pydantic import ValidationError

from app.models.source import SourceContent, SourceItem, SourceType
from app.models.source_brief import (
    SourceBrief,
    source_brief_json_schema,
    validate_source_brief,
)


def _base_payload() -> dict:
    return {
        "quick_brief": "A concise orientation.",
        "summary": "A short summary.",
        "five_minute_read": "A readable briefing.",
        "detailed_reading_note": "A detailed note.",
        "best_next_action": "Use the brief first.",
        "consume_recommendation": "Skim",
        "key_ideas": ["One idea"],
        "detailed_outline": "## Outline\n- One section",
        "important_examples": ["One example"],
        "takeaways": ["One takeaway"],
        "notable_quotes": ["One quote"],
        "best_for": ["One audience"],
        "why_it_matters": "It helps decide whether to read.",
        "open_questions": ["One question"],
        "important_terms": ["Term"],
        "topics": ["Topic"],
        "entities": [],
        "concepts": [],
    }


def _content(source_type: SourceType) -> SourceContent:
    return SourceContent(
        source=SourceItem(
            url="https://example.com/source",
            title="Source",
            source_type=source_type,
        ),
        cleaned_text="A captured source body.",
        extraction_quality="full",
        word_count=800,
    )


def test_article_source_brief_rejects_invalid_read_verdict():
    payload = _base_payload() | {
        "read_verdict": "maybe",
        "why_read_or_skip": "The article is useful.",
        "key_sections": ["Middle"],
    }

    with pytest.raises(ValidationError):
        validate_source_brief(
            payload,
            source_type=SourceType.ARTICLE,
            content=_content(SourceType.ARTICLE),
        )


def test_article_source_brief_requires_article_fields_and_computes_evidence_limits():
    content = SourceContent(
        source=SourceItem(
            url="https://example.com/article",
            title="Article",
            source_type=SourceType.ARTICLE,
        ),
        cleaned_text="A short but complete article body.",
        extraction_quality="mostly_full",
        word_count=1200,
    )

    brief = validate_source_brief(
        {
            "quick_brief": "A concise orientation to the article.",
            "summary": "The article argues for brief-first reading.",
            "five_minute_read": "A readable brief of the argument.",
            "detailed_reading_note": "A detailed note about the argument.",
            "best_next_action": "Skim the key sections.",
            "consume_recommendation": "Skim",
            "key_ideas": ["The first useful idea."],
            "detailed_outline": "## Useful Section\n- Practical middle section.",
            "important_examples": ["A practical workflow example."],
            "takeaways": ["Try the practical recommendation."],
            "notable_quotes": ["Briefs should support decisions."],
            "best_for": ["People triaging saved sources."],
            "why_it_matters": "It prevents wasting time on low-value reading.",
            "open_questions": ["Whether this applies to all source types."],
            "important_terms": ["Source Brief"],
            "topics": ["Knowledge management"],
            "entities": [{"name": "Readwise", "type": "tool", "description": "Reader app"}],
            "concepts": [{"name": "Brief-first reading", "definition": "Decide before reading"}],
            "read_verdict": "skim",
            "why_read_or_skip": "The article has useful sections but does not need deep reading.",
            "key_sections": ["The practical middle section"],
        },
        source_type=SourceType.ARTICLE,
        content=content,
    )

    assert isinstance(brief, SourceBrief)
    assert brief.read_verdict == "skim"
    assert brief.watch_verdict == ""
    assert brief.evidence_limits.extraction_quality == "mostly_full"
    assert brief.evidence_limits.word_count == 1200
    assert brief.evidence_limits.source_type == SourceType.ARTICLE


def test_video_source_brief_requires_video_fields_without_article_fields():
    payload = _base_payload() | {
        "watch_verdict": "transcript_sufficient",
        "watch_verdict_reasoning": "The transcript contains the useful material.",
        "quick_section_guide": "0:00 setup; 4:00 useful section",
        "detailed_sections": "The useful section explains the method.",
        "signal_vs_filler": "Mostly signal after the introduction.",
    }

    brief = validate_source_brief(
        payload,
        source_type=SourceType.YOUTUBE,
        content=_content(SourceType.YOUTUBE),
    )

    assert brief.watch_verdict == "transcript_sufficient"
    assert brief.read_verdict == ""


def test_thread_source_brief_requires_thread_fields_without_article_fields():
    payload = _base_payload() | {
        "thread_summary": "A thread arguing for brief-first reading.",
        "main_claims": ["Briefs should decide whether deeper reading is worthwhile."],
        "useful_links_or_references": ["https://example.com/reference"],
    }

    brief = validate_source_brief(
        payload,
        source_type=SourceType.X_THREAD,
        content=_content(SourceType.X_THREAD),
    )

    assert brief.thread_summary.startswith("A thread")
    assert brief.read_verdict == ""


def test_source_brief_json_schema_is_type_conditional():
    article_schema = source_brief_json_schema(SourceType.ARTICLE)
    video_schema = source_brief_json_schema(SourceType.YOUTUBE)

    assert "read_verdict" in article_schema["required"]
    assert "summary" in article_schema["required"]
    assert "detailed_reading_note" in article_schema["required"]
    assert "important_examples" in article_schema["required"]
    assert "watch_verdict" not in article_schema["required"]
    assert "watch_verdict" in video_schema["required"]
    assert "read_verdict" not in video_schema["required"]
