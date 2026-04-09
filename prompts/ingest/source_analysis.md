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

Existing vault pages to reuse when they already fit:
{existing_knowledge}

Evidence excerpt:
---
{content}
---

Rules:
1. Ground every section in the evidence excerpt and metadata above.
2. If extraction is partial or metadata-only, say so plainly and do not imply full coverage.
3. Write for a future human or model revisiting this vault months later.
4. Prefer concrete facts, mechanisms, examples, and tensions over generic summary language.
5. Use stable, reusable `[[wikilink]]`-friendly names for topics/entities/concepts.
6. `five_minute_read` should be a dense but readable briefing.
7. `detailed_reading_note` should read like a high-quality article note, not a transcript dump.
8. `key_ideas`, `important_examples`, `actionable_takeaways`, `notable_quotes`, `best_for`,
   and `open_questions` must be markdown bullet lists using `- ` prefixes.
9. `detailed_outline` must use markdown headings and bullets.
10. `notable_quotes` may only include short verbatim phrases clearly present in the evidence.
    If none are available, return `- None captured verbatim.`
11. `consume_recommendation` should say whether the original source is still
    worth reading or watching.
12. Optimize for vault usefulness:
    - explain why the source matters, not just what it says
    - preserve structure and argument flow
    - call out contradictions, caveats, and open loops
    - avoid generic filler such as "this article discusses"
13. `topics` should be broad durable subject pages, usually 1-5 items.
14. `entities` should be named people, companies, tools, publications, or projects that
    clearly deserve their own pages. Do not emit near-duplicates.
15. `concepts` should be reusable ideas, methods, or definitions that would compound across
    multiple future sources. Favor stable concepts over source-specific jargon.
16. Reuse existing topic/entity/concept titles from the provided vault-page list when they already
    fit. Avoid near-duplicate variants that would fragment the wiki.
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
