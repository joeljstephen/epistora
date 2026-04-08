"""All LLM prompt templates used by the compiler."""

from __future__ import annotations

import json

SYSTEM_ROLE = (
    "You are Epistora, the maintenance model for a persistent personal wiki. "
    "Treat raw captures as immutable evidence, treat wiki notes as cumulative compiled knowledge, "
    "and optimize for future usefulness rather than one-off summarization. "
    "Be precise, grounded, explicit about uncertainty, and conservative about claims not directly "
    "supported by the source material."
)

YOUTUBE_ANALYSIS_RULES = """
12. **YouTube / video transcript (only when source type is youtube):**
    - The evidence is spoken text (often repetitive or meandering). Produce a **standalone article**
      that captures the full intellectual arc and every major beat—**not** a line-by-line rephrase
      of the transcript.
    - **Coverage:** Address the entire timeline in the evidence. If the evidence says it was built
      from segment digests, or if timestamps stop before the video ends, state that limitation
      explicitly.
    - **`summary`:** State the speaker's core thesis and how the argument develops
      (not a play-by-play).
    - **`five_minute_read`:** A dense briefing that walks through **each major theme in order**,
      with enough
      substance that the reader grasps the whole video without watching it.
    - **`detailed_reading_note`:** A long-form article using multiple `###` subsections.
      For each major segment, include a short title and, when the evidence provides
      `## MM:SS-MM:SS` (or similar) headers, the approximate time range in the heading
      (e.g. `### [12:30–18:00] Why X matters`). Under each, explain claims, reasoning,
      and evidence in **synthesized prose** - do not paste transcript filler.
    - **`detailed_outline`:** Use a "Chapters & timestamps" shape:
      `## [H:MM–H:MM] Short chapter title`
      with nested bullets for sub-points. Mirror the structure of the video.
    - **`important_examples`:** Name specific products, people, stories, numbers, demos,
      or case studies the speaker uses (not generic restatements).
    - **Anti-paraphrase:** Compress repetition; elevate the speaker's conclusions and
      mechanisms. If two paragraphs of transcript say the same thing, merge them into
      one clear paragraph in the analysis.
"""

YOUTUBE_CHUNK_DIGEST_SYSTEM = (
    "You are compressing a portion of a YouTube transcript into notes for a later wiki article. "
    "Be dense and factual. Synthesize; do not copy long runs of dialogue verbatim."
)

YOUTUBE_CHUNK_DIGEST_USER = """\
Video title: {title}
This is segment {part} of {total} (chronological order).

Transcript segment (may include ## MM:SS-MM:SS section headers from the capture):
---
{chunk}
---

Produce markdown with:
- A one-line recap of what happens in this segment (time range if headers exist).
- Bullet points: main claims, arguments, named tools/products/people, stories,
  examples, and any numbers.
- If the segment is mostly an ad read or aside, label it briefly and move on.

Keep it under ~800 words. Use clear markdown (headings optional)."""

SOURCE_ANALYSIS_PROMPT = """\
Compile the following source into a durable wiki-ready analysis.

Source profile:
- Title: {title}
- Source type: {source_type}
- URL: {url}
- Canonical URL: {canonical_url}
- Author: {author}
- Published date: {published_date}
- Tags: {tags}
- Extraction quality: {extraction_quality}
- Extraction method: {extraction_method}
- Extraction notes: {extraction_notes}

Source-specific guidance:
{source_specific_guidance}

Evidence excerpt:
---
{content}
---

Rules:
1. Ground every section in the evidence excerpt and metadata above.
2. If extraction is partial or metadata-only, say so plainly and do not imply full coverage.
3. Write for a future human or model revisiting this vault months later.
4. Prefer concrete facts, mechanisms, examples, and tensions over generic summary language.
5. Use `[[wikilink]]`-friendly names for topics/entities/concepts.
6. `five_minute_read` should be a dense but readable briefing.
7. `detailed_reading_note` should read like a high-quality article note, not a transcript dump.
8. `key_ideas`, `important_examples`, `actionable_takeaways`, `notable_quotes`, `best_for`,
   and `open_questions` must be markdown bullet lists using `- ` prefixes.
9. `detailed_outline` must use markdown headings and bullets.
10. `notable_quotes` may only include short verbatim phrases clearly present in the evidence.
    If none are available, return `- None captured verbatim.`
11. `consume_recommendation` should say whether the original source is still
    worth reading or watching.
{youtube_rules}

Respond in the following JSON format (no markdown fences):
{{
  "summary": "2-4 sentence grounded overview",
  "five_minute_read": "Dense readable briefing in prose/markdown",
  "detailed_reading_note": "Detailed article-style reading note",
  "key_ideas": "Bullet list of the strongest ideas, arguments, or claims",
  "detailed_outline": "Section-by-section markdown outline using headings/bullets",
  "important_examples": "Bullet list of examples, stories, case studies, or concrete evidence",
  "actionable_takeaways": "Bullet list of practical implications or next actions",
  "notable_quotes": "Bullet list of short supported quotes, or '- None captured verbatim.'",
  "best_for": "Bullet list describing who or what this source is especially useful for",
  "consume_recommendation": "1-3 sentence recommendation on whether the original
    is still worth consuming",
  "why_it_matters": "1-3 sentence explanation of why this source matters in the wider vault",
  "open_questions": "Bullet list of unresolved questions, caveats, or follow-up items",
  "topics": ["list", "of", "topic", "names"],
  "entities": [
    {{
      "name": "Entity Name",
      "type": "person|company|tool|publication|other",
      "description": "brief"
    }}
  ],
  "concepts": [
    {{"name": "Concept Name", "definition": "brief definition"}}
  ]
}}
"""

QUERY_PROMPT = """\
You are answering a question using the user's persistent knowledge vault.

Question:
{question}

Vault context:
{context}

Rules:
1. Use only the provided vault context.
2. Prioritize concrete findings from source notes, then synthesize across pages.
3. Reference relevant notes with `[[wikilinks]]`.
4. Separate what the vault directly supports from your synthesis.
5. Surface contradictions, uncertainty, and missing information instead of smoothing them over.
6. Keep the answer useful for future filing back into the wiki.

Write the answer with these sections:
## Direct Findings
## Cross-Source Synthesis
## Gaps / Open Questions
## Useful Next Notes
"""

LINT_ANALYSIS_PROMPT = """\
Review the following vault summary with the mindset of maintaining a coherent long-lived wiki.

{vault_summary}

Identify:
1. Near-duplicate notes or pages that fragment the same concept
2. Contradictions or unresolved tensions between notes
3. Frequently referenced concepts/entities/topics that still lack strong dedicated pages
4. Merge candidates where navigation would improve if pages were consolidated
5. Navigation gaps where indexes, backlinks, or source-to-topic bridges seem weak

Respond in JSON format (no markdown fences):
{{
  "duplicate_candidates": [
    {{"notes": ["note1", "note2"], "reason": "why they might be duplicates"}}
  ],
  "potential_contradictions": [
    {{"notes": ["note1", "note2"], "claim1": "...", "claim2": "...", "tension": "..."}}
  ],
  "missing_pages": [
    {{"name": "entity or concept name", "mention_count": 3, "type": "entity|concept|topic"}}
  ],
  "merge_candidates": [
    {{"notes": ["note1", "note2"], "reason": "why they could be merged"}}
  ],
  "navigation_gaps": [
    {{"notes": ["note1", "note2"], "reason": "why navigation or linking is weak"}}
  ]
}}
"""

SOURCE_ANALYSIS_JSON_SCHEMA = json.dumps(
    {
        "type": "object",
        "required": [
            "summary",
            "five_minute_read",
            "detailed_reading_note",
            "key_ideas",
            "detailed_outline",
            "important_examples",
            "actionable_takeaways",
            "notable_quotes",
            "best_for",
            "consume_recommendation",
            "why_it_matters",
            "open_questions",
            "topics",
            "entities",
            "concepts",
        ],
        "properties": {
            "summary": {"type": "string"},
            "five_minute_read": {"type": "string"},
            "detailed_reading_note": {"type": "string"},
            "key_ideas": {"type": "string"},
            "detailed_outline": {"type": "string"},
            "important_examples": {"type": "string"},
            "actionable_takeaways": {"type": "string"},
            "notable_quotes": {"type": "string"},
            "best_for": {"type": "string"},
            "consume_recommendation": {"type": "string"},
            "why_it_matters": {"type": "string"},
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
            "navigation_gaps",
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
            "navigation_gaps": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
            },
        },
        "additionalProperties": True,
    }
)
