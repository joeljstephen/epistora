# Prompt Templates

Epistora now loads its LLM prompts from Markdown/text files in this directory.

If you want to change how ingestion writes wiki material, start here:

- `[ingest/source_analysis.md](./ingest/source_analysis.md)`: main structured prompt for source-to-wiki analysis
- `[ingest/source_guidance/](./ingest/source_guidance/)`: reusable per-source guidance fragments
- `[ingest/youtube_rules.md](./ingest/youtube_rules.md)`: extra rules injected for YouTube sources
- `[ingest/youtube_chunk_digest_system.md](./ingest/youtube_chunk_digest_system.md)` and `[ingest/youtube_chunk_digest_user.md](./ingest/youtube_chunk_digest_user.md)`: long-transcript chunking prompts

Other workflows:

- `[system_role.md](./system_role.md)`: shared system prompt
- `[query/query.md](./query/query.md)`: deprecated query workflow prompt
- `[lint/lint_analysis.md](./lint/lint_analysis.md)`: vault lint prompt

## Source-specific overrides

If you want a completely different ingest prompt for one source type, create one of these files:

- `prompts/ingest/source_analysis.article.md`
- `prompts/ingest/source_analysis.youtube.md`
- `prompts/ingest/source_analysis.x_thread.md`
- `prompts/ingest/source_analysis.pdf.md`
- `prompts/ingest/source_analysis.generic.md`

Epistora will use the source-specific file when it exists, and fall back to
`prompts/ingest/source_analysis.md` otherwise.

## Custom prompt directory

If you want prompts to live somewhere else entirely, set:

```bash
export EPISTORA_PROMPTS_DIR=/absolute/path/to/prompts
```

