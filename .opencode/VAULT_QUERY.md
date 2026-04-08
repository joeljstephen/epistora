# OpenCode — Vault Query Agent Instructions

This file provides instructions for OpenCode when operating on the Epistora
vault directory. It supplements AGENTS.md with query-specific guidance.

## When the User Asks a Knowledge Question

If the user asks a question that could be answered from the vault's stored
knowledge, follow this procedure:

### Quick Start

1. Read `AGENTS.md` first
2. Read `wiki/indexes/START_HERE.md` for orientation
3. Read `wiki/indexes/QUERY_PROTOCOL.md` for the full procedure
4. Follow the 9-step navigation sequence

### Navigation Shortcut

- Broad topic? → `wiki/indexes/TOPICS.md` → relevant topic page → source notes
- Specific entity? → `wiki/indexes/ENTITIES.md` → entity page → source list
- Specific concept? → `wiki/indexes/CONCEPTS.md` → concept page → examples
- Specific claim? → `wiki/indexes/INDEX.md` → search source notes
- What's missing? → Scan all indexes for thin or empty areas

### Answer Format

```markdown
## Direct Findings
## Cross-Source Synthesis
## Gaps / Open Questions
## Relevant Notes to Read Next
```

### Key Rules

- Ground claims in source notes, not raw captures
- Escalate to `inbox/raw/` only for weak extraction or exact evidence
- Surface contradictions explicitly
- Do not invent missing evidence
- Ignore `.system/` for knowledge answers
