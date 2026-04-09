# Query Protocol — Standard Agent Procedure

> This file will be populated after the first ingest.

This file defines the standard procedure for answering knowledge questions
from this vault. Follow these steps in order.

## Step 1: Orient

Read these files first:

1. `AGENTS.md` — vault conventions and operating manual
2. `wiki/indexes/START_HERE.md` — vault orientation and routing
3. `wiki/indexes/INDEX.md` — full vault overview

## Step 2: Classify the Question

Identify which type of question this is:

- **Topic overview** — broad subject question → start at TOPICS.md
- **Comparison** — how X and Y relate → find both topic/entity pages
- **Evidence lookup** — specific claim → search source notes directly
- **Gap analysis** — what is missing → scan all indexes for thin areas
- **Entity profile** — person/company/tool → start at ENTITIES.md
- **Learning path** — what to read next → topic page → suggested reading

## Step 3: Find Candidate Notes

Use the index files to identify relevant notes:

1. Read `wiki/indexes/TOPICS.md` for topic matches
2. Read `wiki/indexes/ENTITIES.md` for entity matches
3. Read `wiki/indexes/CONCEPTS.md` for concept matches
4. Read `wiki/indexes/INDEX.md` for recent sources that may be relevant

## Step 4: Read Frontmatter Before Body

For each candidate note, read only the YAML frontmatter first. Check:

- `type` — is this the right note type?
- `topics`, `entities`, `concepts` — does it match the question?
- `extraction_quality` — how reliable is the evidence?
- `source_url` — is this the right source?
- `raw_capture_path` — where is the underlying evidence?

Only read the full body for notes that pass this filter.

## Step 5: Read Hub Pages

Read relevant topic, entity, or concept pages. These pages serve as hubs:

- They accumulate knowledge across multiple sources
- They contain `[[wikilinks]]` to related source notes
- They surface recurring patterns and contradictions

## Step 6: Read Source Notes

Source notes are the primary evidence. For each relevant source note:

1. Check `Coverage & Limits` section for extraction quality
2. Read `Key Ideas` and `Detailed Outline` for quick orientation
3. Read `5-Minute Read` or `Detailed Reading Note` for depth
4. Check `Open Questions` for unresolved issues
5. Follow `[[wikilinks]]` in `Related Notes` for more context

## Step 7: Escalate to Raw Captures (Only If Needed)

Read raw captures ONLY when:

- The source note has `extraction_quality` of `partial`, `metadata_only`, or `failed`
- You need exact wording or exact evidence
- The compiled note seems too compressed or missing details
- You want to verify a specific claim against the original text

Do NOT read raw captures by default.

## Step 8: Check Synthesis Notes

If `wiki/synthesis/` contains relevant notes, read them. These represent
prior cross-source work. Check their `Source Basis` section for grounding.

## Step 9: Structure Your Answer

Use this standard structure for all knowledge answers:

```
## Direct Findings
- Grounded claims with explicit source references

## Cross-Source Synthesis
- Patterns, agreements, or tensions across sources

## Gaps / Open Questions
- What the vault does not cover or where evidence is weak

## Relevant Notes to Read Next
- Note paths or [[wikilinks]] for follow-up
```

## Answer Rules

1. Ground every claim in a specific source note or raw capture
2. Surface contradictions — do not smooth them away
3. Note uncertainty when evidence quality is weak
4. Do not invent evidence — state what is missing
5. Reference notes by path or wikilink
6. Distinguish direct findings from synthesis or inference

## Evidence Trust Order

1. Compiled source notes (`wiki/sources/`) — primary evidence
2. Synthesis notes (`wiki/synthesis/`) — prior cross-source work
3. Hub pages (`wiki/topics/`, `wiki/entities/`, `wiki/concepts/`) — routing + patterns
4. Raw captures (`raw/`) — escalation evidence only
