# Start Here — Vault Orientation

> This file will be populated after the first ingest.

This file is the entry point for agents and humans navigating this vault.
Read this first, then use the indexes and hub pages to find what you need.

## Vault Layers

| Layer | Location | Purpose | Trust Level |
|-------|----------|---------|-------------|
| Evidence | `raw/` | Immutable source captures | Escalation only |
| Knowledge | `wiki/` | Compiled, maintained notes | Primary |
| Scratch | `outputs/` | Temporary or user-requested artifacts | Unverified |

## How to Route Your Question

| Question Type | Start At | Then Read |
|---------------|----------|-----------|
| Broad topic overview | `wiki/indexes/TOPICS.md` | Relevant topic page → its source notes |
| Specific claim or evidence | `wiki/indexes/INDEX.md` | Source notes with matching keywords |
| Entity profile (person, company) | `wiki/indexes/ENTITIES.md` | Entity page → its source list |
| Concept definition | `wiki/indexes/CONCEPTS.md` | Concept page → examples from sources |
| Comparison (X vs Y) | Both topic/entity pages | Source notes for each side |
| Gap analysis | All index files | Note what is missing or thin |
| Learning path | Relevant topic page | Suggested next reading section |

## Navigation Files

- [[AGENTS]] — Full operating manual and conventions
- [[QUERY_PROTOCOL]] — Step-by-step query procedure
- [[INDEX]] — Complete vault index with stats
- [[TOPICS]] — All topic pages
- [[ENTITIES]] — All entity pages
- [[CONCEPTS]] — All concept pages
- [[READING_HOME]] — Reader-style attention feed
- [[VIDEOS]] — Video source view
- [[ARTICLES]] — Article source view
- [[TOPICS_FEED]] — Topic and theme cluster view

## Quick Rules

- Read source notes (`wiki/sources/`) first for grounded evidence
- Use reader views for fast triage and learning-path questions
- Use topic/entity/concept pages as routing hubs
- Only read raw captures (`raw/`) when evidence quality is weak or exact text matters
- Ignore `.system/` — it is internal state, not knowledge
- Structure answers with: Direct Findings, Cross-Source Synthesis, Gaps, Relevant Notes
