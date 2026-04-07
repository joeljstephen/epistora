"""All LLM prompt templates used by the compiler."""

from __future__ import annotations

import json

SYSTEM_ROLE = (
    "You are Epistora, a knowledge compiler that turns saved web content into "
    "structured, interconnected knowledge notes. Be precise, factual, and always "
    "distinguish between what the source directly states and your own inferences."
)

SOURCE_ANALYSIS_PROMPT = """\
Analyse the following source content and produce a structured knowledge summary.

**Title:** {title}
**Source Type:** {source_type}
**URL:** {url}

---
{content}
---

Respond in the following JSON format (no markdown fences):
{{
  "summary": "2-4 sentence summary of the core content",
  "key_takeaways": "Bullet list (use - prefix) of 3-7 key takeaways",
  "detailed_outline": "Hierarchical outline of the content using ## and - notation",
  "important_claims": "Bullet list of specific factual claims made",
  "why_matters": "1-3 sentences on why this content is significant or useful",
  "open_questions": "Bullet list of things left uncertain, unstated, or worth investigating",
  "topics": ["list", "of", "topic", "names"],
  "entities": [
    {{"name": "Entity Name", "type": "person|company|tool|other", "description": "brief"}}
  ],
  "concepts": [
    {{"name": "Concept Name", "definition": "brief definition"}}
  ]
}}
"""

QUERY_PROMPT = """\
You are answering a question grounded in the user's personal knowledge vault.

**Question:** {question}

**Available vault context:**
{context}

Rules:
1. Only use information from the provided vault context.
2. Reference specific source notes by their title using [[wikilinks]].
3. Clearly separate findings that come directly from sources vs your synthesis.
4. If the vault does not contain enough information, say so honestly.
5. Do not invent facts or certainty.

Provide a thorough, well-structured answer with source references.
"""

LINT_ANALYSIS_PROMPT = """\
Review the following vault statistics and note metadata for potential issues.

{vault_summary}

Identify:
1. Notes that appear to be near-duplicates based on title/topic similarity
2. Potential contradictions between claims in different source notes
3. Concepts or entities frequently mentioned but lacking their own pages
4. Topic pages that seem too thin or could be merged

Respond in JSON format (no markdown fences):
{{
  "duplicate_candidates": [
    {{"notes": ["note1", "note2"], "reason": "why they might be duplicates"}}
  ],
  "potential_contradictions": [
    {{"notes": ["note1", "note2"], "claim1": "...", "claim2": "...", "tension": "..."}}
  ],
  "missing_pages": [
    {{"name": "entity or concept name", "mention_count": 3, "type": "entity|concept"}}
  ],
  "merge_candidates": [
    {{"notes": ["note1", "note2"], "reason": "why they could be merged"}}
  ]
}}
"""

SOURCE_ANALYSIS_JSON_SCHEMA = json.dumps(
    {
        "type": "object",
        "required": [
            "summary",
            "key_takeaways",
            "detailed_outline",
            "important_claims",
            "why_matters",
            "open_questions",
            "topics",
            "entities",
            "concepts",
        ],
        "properties": {
            "summary": {"type": "string"},
            "key_takeaways": {"type": "string"},
            "detailed_outline": {"type": "string"},
            "important_claims": {"type": "string"},
            "why_matters": {"type": "string"},
            "open_questions": {"type": "string"},
            "topics": {"type": "array", "items": {"type": "string"}},
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["name", "type", "description"],
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "additionalProperties": True,
                },
            },
            "concepts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["name", "definition"],
                    "properties": {
                        "name": {"type": "string"},
                        "definition": {"type": "string"},
                    },
                    "additionalProperties": True,
                },
            },
        },
        "additionalProperties": True,
    }
)

LINT_ANALYSIS_JSON_SCHEMA = json.dumps(
    {
        "type": "object",
        "required": [
            "duplicate_candidates",
            "potential_contradictions",
            "missing_pages",
            "merge_candidates",
        ],
        "properties": {
            "duplicate_candidates": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
            },
            "potential_contradictions": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
            },
            "missing_pages": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
            },
            "merge_candidates": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
            },
        },
        "additionalProperties": True,
    }
)
