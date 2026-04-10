# Maintenance Framework

Phase 6 introduces a real maintenance framework under:

- [`app/maintenance/planner.py`](/Users/joeljacobstephen/Code/projects/epistora/app/maintenance/planner.py)
- [`app/maintenance/service.py`](/Users/joeljacobstephen/Code/projects/epistora/app/maintenance/service.py)
- [`app/maintenance/models.py`](/Users/joeljacobstephen/Code/projects/epistora/app/maintenance/models.py)

## Maintenance Classes

Epistora now has explicit first-pass maintenance classes:

- structural
- semantic
- synthesis
- storage

## What Each Class Does In Phase 6

Structural maintenance:

- runs a deterministic structural audit
- rebuilds vault indexes
- records maintenance output in `wiki/logs/maintenance-log.md`

Semantic maintenance:

- refreshes targeted topic/entity/concept hub pages
- improves backlink visibility with explicit `Backlinks` sections
- refreshes thin hub pages with supporting sources and maintenance notes

Synthesis maintenance:

- in deep mode, generates bounded candidate synthesis drafts for topics with multi-source support
- marks them clearly as candidate maintenance output instead of silently promoting them

Storage maintenance:

- repairs or refreshes the read model
- in deep mode, rebuilds the FTS search index

## Mode Differences

Safe:

- structural audit
- index refresh
- read-model refresh

Balanced:

- safe-mode structural/storage maintenance
- targeted hub refresh for changed note neighborhoods

Deep:

- broader neighborhood expansion
- hub refresh
- synthesis candidate generation
- full read-model rebuild
- FTS rebuild

This makes Deep materially different from Balanced in actual behavior, not only in budget policy.

## Targeting

Maintenance can be scoped by changed note paths.

The planner expands that scope into a bounded neighborhood using the read model:

- changed source notes pull in their related topic/entity/concept hubs
- changed hubs pull in supporting source notes
- deep mode expands one step further than balanced mode

## Automation Integration

Queue processing now carries changed note paths forward, and `run_automation(...)` passes them into maintenance. That means balanced and deep maintenance focus on the notes that actually changed during processing instead of running as an unbounded global rewrite.

## Safety Boundaries

Phase 6 keeps maintenance bounded and reviewable:

- hub refresh only updates maintenance-managed sections
- existing note introductions and unrelated sections are preserved
- synthesis output is written as explicit candidate drafts
- evidence files are never rewritten
