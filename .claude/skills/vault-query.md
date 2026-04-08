# Vault Query Skill

This skill teaches you how to answer knowledge questions using the Epistora
vault in this repository.

## When to Use This Skill

Use this skill whenever the user asks a question about knowledge stored in the
vault — anything that could be answered from the ingested sources, topic pages,
entity pages, concept pages, or synthesis notes.

## Procedure

### 1. Orient

Read these files in order:

1. `AGENTS.md` — the vault operating manual
2. `wiki/indexes/START_HERE.md` — vault orientation map
3. `wiki/indexes/QUERY_PROTOCOL.md` — standard query procedure

### 2. Classify

Determine the question type:

- **Topic overview** → start at `wiki/indexes/TOPICS.md`
- **Comparison** → find both sides' topic/entity pages
- **Evidence lookup** → search source notes directly
- **Gap analysis** → scan indexes for thin areas
- **Entity profile** → start at `wiki/indexes/ENTITIES.md`
- **Learning path** → topic page → suggested reading

### 3. Navigate

Follow this sequence:

1. Read index files (`TOPICS.md`, `ENTITIES.md`, `CONCEPTS.md`, `INDEX.md`)
2. Identify candidate notes from the indexes
3. Read YAML frontmatter of candidates (use Read tool with small limit)
4. Read full body only of the most relevant notes
5. Read hub pages (topic/entity/concept) as routing hubs
6. Read source notes as primary evidence
7. Escalate to raw captures (`inbox/raw/`) ONLY when:
   - extraction_quality is partial, metadata_only, or failed
   - exact wording matters
   - the compiled note is too compressed
8. Check `wiki/synthesis/` for prior cross-source work

### 4. Answer

Structure your answer as:

```markdown
## Direct Findings
- Grounded claims with explicit source references

## Cross-Source Synthesis
- Patterns, agreements, or tensions across multiple sources

## Gaps / Open Questions
- What the vault does not cover or where evidence is weak

## Relevant Notes to Read Next
- Note paths or [[wikilinks]] for follow-up
```

### 5. Rules

- Ground every claim in a specific source note or raw capture
- Surface contradictions instead of smoothing them away
- Note uncertainty when extraction quality is weak
- Do not invent evidence — say what is missing
- Reference notes by path or [[wikilink]]
- Distinguish direct findings from synthesis or inference
- Do not read `.system/` for knowledge answers
- Do not read raw captures by default

### 6. Save Valuable Answers

If the answer is particularly valuable, offer to save it:

- Save to `outputs/answers/` for the user
- If it is durable and generally useful, suggest promoting to `wiki/synthesis/`

## Evidence Trust Order

1. Compiled source notes (`wiki/sources/`) — primary evidence
2. Synthesis notes (`wiki/synthesis/`) — prior cross-source work
3. Hub pages (`wiki/topics/`, `wiki/entities/`, `wiki/concepts/`)
4. Raw captures (`inbox/raw/`) — escalation only
