# Maintenance Framework

Epistora has a bounded maintenance framework under:

- [`app/maintenance/planner.py`](/Users/joeljacobstephen/Code/projects/epistora/app/maintenance/planner.py)
- [`app/maintenance/service.py`](/Users/joeljacobstephen/Code/projects/epistora/app/maintenance/service.py)
- [`app/maintenance/models.py`](/Users/joeljacobstephen/Code/projects/epistora/app/maintenance/models.py)

## Maintenance Classes

Epistora now has explicit first-pass maintenance classes:

- structural
- semantic
- synthesis
- storage

## Task Contract

Maintenance is planned around one bounded task set:

- `artifact_neighborhood_refresh`
- `structural_repair`
- `hub_refresh`
- `backlink_repair`
- `candidate_synthesis_refresh`
- `read_model_refresh`
- `search_refresh`

Each task now has explicit:

- trigger metadata
- scope paths
- bounded write scope
- idempotency defaults
- per-task logging through `MaintenanceTaskResult`
- deterministic ordering in the planner

## What Each Class Does

Structural maintenance:

- plans and records the bounded artifact neighborhood before writes
- runs a deterministic structural audit
- rebuilds vault indexes as part of `structural_repair`
- records maintenance output in `wiki/logs/maintenance-log.md`

Semantic maintenance:

- refreshes targeted topic/entity/concept hub pages through `hub_refresh`
- repairs backlink sections through `backlink_repair`
- keeps writes limited to maintenance-managed sections and frontmatter

Synthesis maintenance:

- in deep mode, generates bounded candidate synthesis drafts for topics with multi-source support
- marks them clearly as candidate maintenance output instead of silently promoting them

Storage maintenance:

- refreshes the read model as the primary derived substrate
- refreshes lexical support inside `read_model_fts`
- retires obsolete legacy search state as part of the read-model lifecycle

## Mode Differences

Safe:

- artifact neighborhood refresh (read-only)
- structural repair
- read-model refresh
- search refresh

Balanced:

- safe-mode structural/storage maintenance
- first-degree neighborhood expansion from changed notes
- hub refresh and backlink repair for touched hubs

Deep:

- second-degree neighborhood expansion from changed notes
- hub refresh and backlink repair across the deeper neighborhood
- candidate synthesis generation for multi-source topics
- full read-model rebuild plus search refresh

This makes Deep materially different from Balanced in actual behavior, not only in budget policy.

## Targeting

Maintenance can be scoped by changed note paths.

The planner expands that scope into a bounded neighborhood using the read model:

- changed source notes pull in their related topic/entity/concept hubs
- changed hubs pull in supporting source notes
- deep mode expands a second degree and can produce candidate synthesis drafts

## Automation Integration

Queue processing now carries changed note paths forward, and `run_automation(...)` passes them into maintenance. That means balanced and deep maintenance focus on the notes that actually changed during processing instead of running as an unbounded global rewrite.

## Event Hooks

The runtime exposes a minimal internal event taxonomy in
[`app/events.py`](/Users/joeljacobstephen/Code/projects/epistora/app/events.py):

- `source_ingested`
- `artifact_written`
- `maintenance_completed`
- `query_answer_saved`
- `topic_bundle_saved`
- `review_digest_saved`
- `scheduled_maintenance_tick`

These hooks are intentionally small. They are there to support future
automation growth without forcing a later migration through the maintenance
runtime.

## Lifecycle And Derived Work Hooks

Lifecycle metadata is now present as a nested `lifecycle` block on source and
knowledge artifacts. The current fields are:

- `confidence`
- `last_confirmed_at`
- `supersedes`
- `superseded_by`
- `staleness_status`
- `reinforcement_count`

This is structural only. It is not a full confidence or retention engine yet.

Epistora also now reserves a clean source/artifact lane for work-derived
knowledge through `source_type: derived_work`, with bounded kinds such as:

- `derived_analysis`
- `session_digest`
- `crystallized_output`

## Safety Boundaries

Maintenance stays bounded and reviewable:

- hub refresh only updates maintenance-managed sections
- existing note introductions and unrelated sections are preserved
- synthesis output is written as explicit candidate drafts
- evidence files are never rewritten
