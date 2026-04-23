# Epistora Personal Learning Mode — Implementation Spec

## Status

Draft v2, implementation-ready

## Purpose

Define a narrow, buildable first version of **Epistora Personal Learning Mode**.

This mode should make Epistora feel like a practical local learning system for a
single-user workflow:

- save mixed-media content into an inbox
- compile sources into readable briefs
- browse the resulting corpus through view pages instead of folders
- generate grounded topic learning packets
- emit small review outputs over time

This document is intentionally narrower than the earlier concept spec. It fixes
the main architecture and product decisions so implementation can proceed
without re-litigating the design on every feature.

---

## 1. Product Objective

Build a preset on top of the current v2 architecture that is optimized for:

- **Raindrop** as the default inbox
- **Markdown vault / Obsidian** as the main human-facing sink
- strong first-pass support for:
  - YouTube
  - articles
  - X/Twitter threads
  - topic learning
  - brief-first consumption

The durable product remains the local vault on disk. The preset improves the
experience; it does not replace the underlying compiler architecture.

---

## 2. Fixed Decisions

These decisions are locked for v1 unless implementation proves them unworkable.

### 2.1 Personal Learning Mode is a composed preset

It is **not** a new core compiler mode.

It selects and orchestrates:

- a prompt-pack profile
- a source-note renderer profile
- view generation
- topic-bundle generation
- review digest generation
- automation defaults

It does **not** introduce a parallel architecture.

### 2.2 `safe`, `balanced`, and `deep` remain execution-depth policies

They continue to answer:

- how much enrichment to run
- how much maintenance to run
- how much cost/time budget to spend

They do **not** define the product persona.

`personal_learning` answers workflow questions; `safe|balanced|deep` answer
execution-depth questions.

### 2.3 Compiled source notes remain the primary durable retrieval unit

Retrieval should prefer:

1. compiled source artifacts / source notes
2. durable topic/entity/concept/synthesis notes
3. raw evidence drill-down only when needed

Topic bundles and digests are output artifacts, not the primary retrieval
substrate.

### 2.4 Topic bundles are output artifacts

Topic bundles are:

- generated reports
- built from an explicit frozen source set
- immutable per run
- written under `outputs/digests/topic-bundles/`

They are **not** canonical durable knowledge artifacts and are not auto-promoted
into `wiki/`.

### 2.5 Reader views are deterministic projections

Generated pages such as `READING_HOME.md` are:

- rebuildable
- derived from metadata and read-model state
- not hand-maintained
- not semantically authoritative

### 2.6 Digests are editorial outputs, not maintained knowledge

Daily and weekly digests:

- live under `outputs/digests/`
- are action-oriented and scheduled
- are gated by minimum-signal thresholds
- do not mutate or promote durable knowledge automatically

### 2.7 User overrides are narrow and explicit

Generated source note bodies are automation-owned in v1.

User-preserved edits are limited to a small override namespace in frontmatter.

### 2.8 Balanced mode is the default meaningful preset experience

For personal learning mode:

- `safe` is continuity-preserving but limited
- `balanced` is the default recommended mode
- `deep` uses the same workflow with richer enrichment and maintenance

---

## 3. v1 Scope

### 3.1 In scope

- brief-first source-note rendering, especially for YouTube
- canonical/source-level additions needed for retrieval and triage
- lightweight theme tagging
- topic-bundle generation
- generated reader-style index pages
- daily and weekly digests
- a personal-learning automation preset

### 3.2 Explicitly out of scope

- graph database adoption
- hosted UI or SaaS workflow
- auto-promotion from outputs into durable knowledge
- behavioral personalization from click history
- advanced spaced-repetition or forgetting models
- arbitrary user editing and round-trip preservation of generated note bodies
- making topic pages the center of the phase-1 experience
- redesigning the canonical artifact model around one sink or one user persona

---

## 4. Architecture Mapping

Personal learning mode must fit the current v2 seams.

### 4.1 Prompt-pack responsibility

The prompt-pack profile is responsible for producing improved source
understanding, including:

- `quick_brief`
- `best_next_action`
- `watch_verdict` for YouTube
- `quick_section_guide` for YouTube
- `detailed_sections` for YouTube
- `signal_vs_filler` for YouTube
- `important_terms`

The prompt pack should remain swappable.

### 4.2 Canonical artifact responsibility

Canonical source understanding should remain sink-agnostic and durable enough to
support retrieval, downstream sinks, and report generation.

Only broadly useful fields should become canonical.

### 4.3 Renderer responsibility

The renderer profile is responsible for:

- source-type-specific note structure
- frontmatter projection for vault browsing
- top-of-note reading experience
- human-readable ranking reasons where needed

The renderer may vary by source type.

### 4.4 Orchestration responsibility

Personal learning orchestration belongs in services / automation flow, not
inside the core ingest graph.

The orchestration layer coordinates:

1. inbox discovery
2. queued item processing
3. view rebuilds
4. digest evaluation and generation
5. optional maintenance

---

## 5. Source-Type Strategy

### 5.1 YouTube is the strongest v1 path

YouTube should receive the richest treatment first because it offers the highest
time-saving payoff.

Required v1 YouTube outcomes:

- a short orientation layer at the top of the note
- a usable section guide
- a grounded watch verdict
- a source-aware section-by-section breakdown
- visible transcript/evidence quality indicators

Success is judged by **fast orientation and watch-decision usefulness**, not
transcript completeness.

### 5.2 Article and X support is brief-first but lighter

Articles and X threads should improve in v1, but they do not need to match the
YouTube contract.

Required outcomes:

- stronger `quick_brief`
- stronger `best_next_action`
- clearer “read the original or not?” guidance
- source-type-appropriate top sections

### 5.3 One uniform source-note template is not required

All source types may share a common substrate, but the top sections and
presentation contract may differ by source type.

---

## 6. Data Contract

This section defines the v1 persistence boundary.

### 6.1 Canonical source-level additions

The following fields should become part of durable source understanding, either
as explicit `SourceArtifact` fields or as structured source metadata that the
read model can index reliably:

- `quick_brief`
- `best_next_action`
- `theme_tags`
- `brief_status`
- `watch_verdict` for YouTube
- `watch_verdict_reasoning` for YouTube
- `quick_section_guide` for YouTube
- `detailed_sections` for YouTube
- `signal_vs_filler` for YouTube
- `important_terms`

Notes:

- `theme_tags` are canonical because they support retrieval/ranking across
sinks.
- `brief_status` is a usability/quality field, not a pipeline execution log.
- `channel_context` is optional and opportunistic, not required in v1.

### 6.2 Sink/render metadata

The following fields are primarily for vault browsing and presentation:

- `quick_summary`
- `channel_or_author`
- `cover_image`
- `source_type`
- `saved_at`
- `ingested_at`
- display-oriented ranking reasons

These should degrade cleanly when absent.

### 6.3 Fields excluded from the v1 durable contract

Do **not** introduce these as durable v1 requirements:

- numeric `importance_score`
- arbitrary auto-promotable `topic_bundle_candidates`
- mandatory `channel_context` for every video

Ranking should be driven by interpretable heuristics, not by a durable numeric
score.

### 6.4 Theme tag contract

`theme_tags` are:

- low-cardinality
- stable
- human-meaningful
- distinct from `topics`, `entities`, and `concepts`

They exist for:

- filtering
- ranking support
- browse/feed grouping
- explicit user filters

They do **not** replace the richer semantic model.

### 6.5 Theme tag assignment

V1 theme-tag assignment should be deterministic.

Inputs may include:

- inbox tags
- title
- `quick_brief`
- extracted topics/concepts

Assignment should flow through explicit mapping rules over an allowed theme set.

Unconstrained model-generated tags should not be the final authority.

### 6.6 Reading state contract

`reading_state` is:

- system-inferred by default
- user-overridable
- view-layer metadata first

V1 allowed values should stay small:

- `up_next`
- `queued`
- `brief_may_be_enough`
- `review`

User edits win over automation.

### 6.7 Override namespace

User-preserved note-local overrides should live in frontmatter under an explicit
namespace. The exact key name may vary, but the structure should be explicit and
separate from generated fields.

Recommended shape:

```yaml
user_state:
  reading_state: queued
  review_excluded: false
  pinned: false
```

Rules:

- fields in the override namespace are user-authoritative
- generated fields outside that namespace are system-authoritative
- rebuilds overwrite automation-owned fields
- rebuilds preserve explicit overrides

### 6.8 Source note body ownership

In v1:

- source note body content is automation-owned and rebuildable
- ad hoc manual edits to generated body sections are not guaranteed to survive
- durable user-authored writing belongs elsewhere, such as `wiki/synthesis/`

---

## 7. Source Note Rendering Contract

### 7.1 Brief-first principle

The first screen of a source note should answer:

- what is this about?
- is it worth my time?
- what should I do next?
- where should I jump if I consume the original?

### 7.2 YouTube note structure

Recommended v1 order:

1. Overview
2. Quick Section Guide
3. Should I Watch This?
4. Detailed Section-by-Section Breakdown
5. Key Takeaways
6. Important Terms / People / Tools
7. Signal vs Filler
8. Evidence / Transcript Status
9. Raw capture references

### 7.3 Article and X note structure

These should stay simpler:

- overview / quick brief
- whether the original is still worth opening
- key points
- why it matters
- best next action
- evidence / limitations

### 7.4 Trust contract

Briefs are:

- grounded guides to the source
- allowed to compress and prioritize
- not authoritative replacements for the source

When evidence quality is partial or weak, the note must make that visible.

---

## 8. Brief Quality and Degradation

### 8.1 `brief_status`

Use `brief_status` as a user-facing usability field with these values:

- `ready`
- `partial`
- `failed`

It should mean:

- `ready`: usable as a real brief
- `partial`: useful but clearly limited
- `failed`: source is preserved, but the brief is not trustworthy enough for
brief-first flows

Pipeline state, retries, and backend failures should be tracked separately in
operational state.

### 8.2 Degradation policy

When a source cannot get a strong brief:

- preserve the source
- keep raw evidence links visible
- publish an honest partial note when possible
- keep it retrievable
- demote or exclude it from attention surfaces as appropriate

`partial` notes may still appear in some views and some topic bundles when they
add unique value.

### 8.3 Candid source recommendations are allowed

`watch_verdict` and `best_next_action` may say:

- skip
- deprioritize
- skim only
- open only for diagrams/examples

Low-value items should remain in the corpus but be demoted in attention
surfaces.

---

## 9. Topic Bundle Contract

### 9.1 Product role

A topic bundle is a request-specific learning packet built from the user’s saved
corpus.

It should help the user:

- orient quickly
- understand what sources matter
- see what each source contributes
- identify disagreement and gaps
- decide how to spend the next 10 minutes

It is **not** a full tutoring system and **not** a durable topic page.

### 9.2 Output location and identity

Topic bundles live under:

`outputs/digests/topic-bundles/`

They are immutable per run.

Filename guidance:

- include the topic/query slug
- include the generation date or timestamp
- optionally include scope suffixes when filters materially change the source set

### 9.3 Frozen source set

Each topic-bundle run must:

1. resolve candidates through the normal retrieval stack
2. apply explicit filters
3. freeze the included source set
4. synthesize only from that frozen set

The bundle artifact itself must record:

- topic/query
- filters
- generated timestamp
- included source ids and/or note paths

### 9.4 Source-set threshold

Use two output statuses:

- `normal`
- `limited`

Recommended v1 threshold for a normal bundle:

- at least 3 usable sources
- at least 2 with `brief_status=ready`

Weaker cases should produce a **limited bundle** when there is still user value.

### 9.5 Limited bundle behavior

A limited bundle:

- lives in the same directory as normal bundles
- uses the same broad output shape
- clearly labels sparse or provisional coverage

Recommended metadata:

- `bundle_status: normal|limited`
- `source_count`
- `ready_source_count`

### 9.6 Bundle structure

Recommended v1 sections:

1. Topic Overview
2. Why This Matters
3. Best Sources To Start With
4. What Each Source Contributed
5. Agreements and Disagreements
6. Key Concepts / Terms
7. Recommended Order
8. If I Only Have 10 Minutes
9. Gaps / Missing Coverage
10. Included Sources

### 9.7 Bundle organization

Primary organization should be by **semantic contribution**, not by source type.

Source type should remain visible as a label because it affects time and
attention planning.

### 9.8 Disagreement handling

Bundles must surface disagreement explicitly.

They should:

- distinguish disagreement from mere difference in emphasis
- attribute claims to sources when possible
- synthesize cautiously
- avoid flattening conflict into one narrative

### 9.9 Use of low-value or partial sources

Bundles may include:

- `partial` briefs when they add unique value
- individually low-value sources when they make a unique contribution

When that happens, the bundle should explain why the source is included despite
its weaker standalone status.

### 9.10 Relationship to topic pages

Topic pages and topic bundles serve different roles:

- `wiki/topics/`: durable navigational knowledge pages
- topic bundles: request-specific learning packets

Neither replaces the other.

---

## 10. Reader Views

### 10.1 Role

Reader views are passive browse surfaces built on top of durable metadata.

They should help the user browse the corpus without replacing the underlying
source notes.

### 10.2 Output location

Reader views belong under:

`wiki/indexes/`

Recommended v1 pages:

- `READING_HOME.md`
- `VIDEOS.md`
- `ARTICLES.md`
- `TOPICS_FEED.md`

### 10.3 Baseline UX

These pages must remain useful as plain generated markdown.

Obsidian Bases / Dataview support is optional enhancement, not a core
dependency.

### 10.4 `READING_HOME`

`READING_HOME` is an item-centric attention feed.

It should rank by a blend of:

- freshness
- `brief_status`
- source-level recommendation strength
- recurring or active themes
- source-type mix
- anti-repetition logic for scheduled outputs where relevant

It should not be simple reverse chronology.

### 10.5 `TOPICS_FEED`

`TOPICS_FEED` is a topic/theme-centric cluster view.

It should be driven primarily by:

- extracted topics
- read-model relationships
- recurrence across saved sources

`theme_tags` may act as a stabilizing secondary signal.

### 10.6 Views are projections

`epistora views rebuild` must:

- read existing metadata and read-model state
- apply deterministic ranking logic
- never run fresh LLM analysis

---

## 11. Review Digests

### 11.1 Role

Digests are scheduled editorial outputs.

Their purpose is:

1. guide user attention
2. encourage revisit/review
3. summarize only insofar as it supports action

They are not meant to recap everything.

### 11.2 Output location

Digests live under:

- `outputs/digests/daily/`
- `outputs/digests/weekly/`

### 11.3 File identity

Daily and weekly digests should use one stable file per period.

Examples:

- `outputs/digests/daily/2026-04-21.md`
- `outputs/digests/weekly/2026-W17.md`

If a run is repeated for the same period, it updates that period’s file.

### 11.4 Publication gating

Digest jobs should run on schedule, but publication should be gated by minimum
usefulness thresholds.

If there is insufficient signal, no digest should be written for that period.

### 11.5 Daily digest contract

The daily digest answers:

**What is worth your attention today?**

It should be:

- short
- selective
- reason-driven

Recommended contents:

- a few strong recent ready briefs
- at most one resurfaced older item
- one concrete next-step suggestion

### 11.6 Weekly digest contract

The weekly digest answers:

**What patterns are forming, and where should you go deeper next?**

It should:

- identify repeated or emerging themes
- highlight the strongest saves
- propose where deeper study may pay off
- nominate candidate topic bundles

It should **not** behave like many mini topic bundles.

### 11.7 Resurfacing policy

Start with a simple explainable heuristic, not advanced spaced repetition.

Eligible resurfacing candidates should typically be:

- old enough
- not resurfaced recently
- at least partially usable
- not explicitly excluded by the user

Rank using interpretable signals such as:

- age since last surfacing
- quality/usability
- theme recurrence
- neglect / lack of revisit

### 11.8 Surfacing history

Anti-repetition and resurfacing history should live in structured system state
or DB records, not be inferred from markdown files.

Recommended recorded data:

- source id
- surfaced in which output type
- surfaced at timestamp
- surfacing reason/category

---

## 12. Personal Learning Automation Preset

### 12.1 Workflow

Add a workflow entrypoint:

`epistora automation run-personal-learning --mode safe|balanced|deep`

This preset should orchestrate:

1. inbox discovery
2. pending-item processing
3. read-model refresh
4. view rebuilds
5. digest evaluation
6. optional maintenance

### 12.2 Mode expectations

#### `safe`

`safe` personal learning should:

- preserve continuity
- keep the corpus visible
- refresh deterministic browse surfaces when possible

It should **not** promise full brief-first value.

#### `balanced`

`balanced` is the recommended default and the first fully supported personal
learning experience.

It should:

- produce real briefs
- power trustworthy browse views
- support digest generation

#### `deep`

`deep` uses the same product contract with:

- richer enrichment
- broader maintenance
- stronger downstream synthesis support

---

## 13. CLI and API Surface

### 13.1 CLI

Add only intent-based commands that represent distinct user actions:

- `epistora automation run-personal-learning --mode ...`
- `epistora topic-bundle "<topic>" [filters]`
- `epistora views rebuild`
- `epistora review daily`
- `epistora review weekly`

Do not add separate v1 commands for every internal ranking or resurfacing step.

### 13.2 API

Mirror only the same high-level intents:

- `POST /topic-bundle`
- `POST /review/daily`
- `POST /review/weekly`
- `POST /views/rebuild`

Do not expose internal orchestration steps as a wide public contract.

---

## 14. Implementation Sequence

Implementation order is part of the design.

### Phase 1: Brief Contract

Ship first:

1. source-type-specific prompt profile, especially YouTube
2. source-type-specific renderer profile
3. canonical/source-level additions needed for brief-first use
4. deterministic theme-tag mapping
5. `brief_status` and degradation handling

### Phase 2: Topic Bundle

Ship next:

1. `epistora topic-bundle`
2. frozen source-set selection
3. normal vs limited bundle behavior
4. report rendering and output writing

### Phase 3: Reader Views

Ship next:

1. `epistora views rebuild`
2. `READING_HOME`
3. `VIDEOS`
4. `ARTICLES`
5. `TOPICS_FEED`

### Phase 4: Review Digests

Ship next:

1. daily digest generation
2. weekly digest generation
3. anti-repetition state
4. simple resurfacing heuristic

### Phase 5: Smarter Maintenance Later

Possible future work:

- lifecycle-informed resurfacing
- richer topic synthesis
- more advanced personalization
- additional sinks/providers

---

## 15. Testing Strategy

Most new behavior should be deterministic and unit-testable.

### 15.1 Deterministic tests

Add deterministic tests for:

- theme-tag mapping
- `brief_status` handling
- reading-state override preservation
- topic-bundle candidate selection
- frozen source-set persistence
- limited-bundle threshold behavior
- digest publish/skip gating
- resurfacing eligibility and anti-repetition windows
- view ranking and exclusion rules
- generated file naming and output locations

### 15.2 LLM-dependent tests

Keep LLM-dependent tests narrower:

- schema conformance for source analysis outputs
- a few golden-path integration tests for YouTube briefs
- a few golden-path integration tests for topic bundles

LLMs should generate understanding and synthesis text. They should not own the
core control flow.

---

## 16. Acceptance Criteria

### 16.1 Brief-first source notes

- A typical saved YouTube source can be oriented from the top of the note in a
few minutes.
- The note makes a grounded recommendation about whether to watch more.
- Partial or weak evidence is clearly labeled.

### 16.2 Topic bundles

- A user can generate a grounded topic packet from saved material with one
command.
- The packet names its included source set.
- Weak retrieval produces a clearly labeled limited bundle rather than confident
junk.

### 16.3 Reader views

- A user can browse from generated index pages without folder traversal.
- `READING_HOME` feels more useful than reverse chronology.
- `TOPICS_FEED` reveals active clusters rather than repeating the main feed.

### 16.4 Review digests

- Daily and weekly digests are sparse enough to be plausibly read.
- Digests explain why surfaced items were chosen.
- Repetition is controlled through structured surfacing history.

### 16.5 Architecture integrity

- The preset uses existing seams rather than creating a private parallel stack.
- Canonical artifacts remain sink-agnostic.
- Outputs remain separate from durable knowledge.

---

## 17. Success Metric

Evaluate this phase primarily by whether it **reduces attention friction** for
saved content.

The success question is:

**Does Epistora make it materially easier to decide what matters, revisit useful
material, and assemble a grounded packet on a topic from the user’s own saved
corpus?**

Do not evaluate success primarily by:

- number of generated files
- number of new schema fields
- number of commands added
- number of digests emitted

The correct product outcome is improved decision quality and reduced browsing
friction.