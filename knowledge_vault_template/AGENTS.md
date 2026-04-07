# Knowledge Vault Conventions

This file defines the rules that govern how the Epistora knowledge compiler
reads, writes, and maintains this vault. Both the automated system and any
human editors should follow these conventions.

---

## Immutability of Raw Captures

Files under `inbox/raw/` are **immutable**. Once a raw capture is saved, it
must never be edited. If the source needs to be re-ingested, a new capture is
created and the old one is kept for provenance.

## Required Frontmatter for Source Notes

Every source note (`wiki/sources/**`) must include the following YAML
frontmatter fields:

- `source_url` — the canonical URL of the original source
- `source_type` — one of: article, youtube, x_thread, pdf, generic
- `ingested_at` — ISO 8601 timestamp of when the note was created
- `topics` — list of related topic page names
- `entities` — list of related entity page names
- `concepts` — list of related concept page names

## Prefer Updates Over Duplicates

When a topic, entity, or concept page already exists, the system must
**update** that page rather than creating a duplicate. Merge new source
references into the existing page's lists.

## Wikilink Convention

All cross-references between pages must use Obsidian-compatible `[[wikilinks]]`.
Do not use standard markdown links for internal vault references.

## Handling Uncertainty

Claims that are unsupported, speculative, or contested must be placed in the
**Open Questions** section of a source note rather than presented as established
facts. Synthesis notes must clearly separate direct findings from inferred
patterns.

## Synthesis Note Sourcing

Every synthesis note must reference the specific source notes it was derived
from in a **Source Basis** section. Unsourced synthesis is not permitted.

## Lint Expectations

The lint system flags:

- **Orphan pages** — notes with no inbound links from other notes
- **Missing backlinks** — when note A links to note B but B does not link back
- **Duplicate or near-duplicate** topic/entity/concept pages
- **Weak pages** — topic, entity, or concept pages with fewer than two source references
- **Stale synthesis** — synthesis notes whose source basis includes notes that have been significantly updated since the synthesis was created
- **Missing pages** — concepts or entities frequently mentioned in `[[wikilinks]]` that do not have their own page yet
- **Contradictions** — claims in different source notes that directly conflict

## Note Naming

- Source notes use slugified titles: `my-article-title.md`
- Topic/entity/concept notes use slugified names: `machine-learning.md`
- All note filenames are lowercase with hyphens, no spaces

## Index Maintenance

Index files (`wiki/indexes/`) are automatically rebuilt after each ingest and
can be manually rebuilt with `kb rebuild-indexes`. They are generated files
and should not be manually edited.
