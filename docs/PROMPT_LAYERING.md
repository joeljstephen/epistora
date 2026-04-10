# Prompt Layering

Phase 5 introduces explicit prompt composition for Epistora compiler workflows.

The implementation lives in:

- [`app/compiler/prompts.py`](/Users/joeljacobstephen/Code/projects/epistora/app/compiler/prompts.py)

The compiler paths now use composed prompts in:

- [`app/compiler/ingest_graph.py`](/Users/joeljacobstephen/Code/projects/epistora/app/compiler/ingest_graph.py)
- [`app/compiler/query_graph.py`](/Users/joeljacobstephen/Code/projects/epistora/app/compiler/query_graph.py)
- [`app/compiler/lint_graph.py`](/Users/joeljacobstephen/Code/projects/epistora/app/compiler/lint_graph.py)

## Precedence Model

Prompt layers are composed in this order:

1. base compiler instructions
2. artifact-type instructions
3. source-type instructions
4. workspace/profile instructions
5. user overrides
6. backend/model-specific hints

Lower-numbered layers are foundational. Higher-numbered layers narrow or refine behavior.

## Current Prompt Sources

Base prompt files are still loaded from prompt roots:

- `system_role.md`
- `ingest/source_analysis*.md`
- `query/query.md`
- `lint/lint_analysis.md`

Prompt roots are searched in this order:

1. `EPISTORA_PROMPTS_DIR`
2. active prompt-pack plugin root selected by `EPISTORA_PROMPT_PACK`
3. built-in `prompts/`

That keeps explicit user overrides above prompt packs, and prompt packs above built-in defaults.

## Layer Files

Optional layer files can live inside any prompt root:

- `layers/artifact/<artifact_type>.md`
- `profiles/<profile>/common.md`
- `profiles/<profile>/tasks/<task_name>.md`
- `backend_hints/<task_name>/<backend_id>.md`
- `backend_hints/<task_name>/<backend_id>.<model_token>.md`

Current task names are:

- `ingest_analysis`
- `query_answer`
- `lint_analysis`

Model tokens are normalized to lowercase alphanumeric segments joined by underscores.

Example:

- model `gpt-4o-mini` becomes `gpt_4o_mini`

## Workspace Instructions

Workspace-specific prompt instructions are loaded from the current vault when present:

- `<vault>/.system/prompts/common.md`
- `<vault>/.system/prompts/tasks/<task_name>.md`
- `<vault>/.system/prompts/profiles/<profile>/common.md`
- `<vault>/.system/prompts/profiles/<profile>/tasks/<task_name>.md`

This keeps local workspace guidance outside core code.

## User Overrides

User overrides can be supplied:

- programmatically to the composition functions
- or via `EPISTORA_PROMPT_USER_OVERRIDE`

## Inspectability

Prompt composition now returns a `ComposedPrompt` object containing:

- final `system_prompt`
- final `user_prompt`
- resolved `PromptLayer` list
- `inspect()` output for debugging

This makes precedence and prompt-pack behavior visible during development.

## Phase 5 Boundaries

This phase adds the prompt layering foundation, but does not add:

- a prompt UI
- remote prompt-pack distribution
- dynamic runtime prompt editing tools
- a broader redesign of compiler tasks beyond the current ingest/query/lint paths
