# Troubleshooting

Start with:

```bash
epistora doctor
```

From a checkout:

```bash
uv run epistora doctor
```

The doctor command reports the config path, vault status, backend availability,
plugin health, sink configuration, and storage-tier settings.

## CLI Not Found

If `epistora` is not on your PATH after `uv tool install .`, ensure uv's bin
directory is on your PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

From a source checkout, use:

```bash
uv run epistora --help
```

## Config Not Taking Effect

You are probably editing a different `.env` than Epistora is loading.

Run:

```bash
epistora doctor
```

Then check the reported loaded config path and preferred write target. You can
force a config file with:

```bash
EPISTORA_ENV_FILE=/absolute/path/to/.env epistora doctor
```

## Missing Connector Credentials

Readwise:

```bash
epistora connect readwise
```

Raindrop:

```bash
epistora connect raindrop
```

Manual `.env` variables:

```bash
READWISE_API_TOKEN=...
RAINDROP_API_TOKEN=...
RAINDROP_COLLECTION_ID=0
```

## Backend Unavailable

Check:

```bash
epistora backend status
```

At least one configured backend must be available. For direct API usage, set:

```bash
API_ENABLED=true
API_API_KEY=...
API_MODEL=gpt-4o-mini
```

CLI backends require the matching binary on PATH:

```bash
opencode --help
claude --help
codex --help
```

Fallback order is controlled by:

```bash
BACKEND_ORDER_INGEST=api,opencode,claude_code,codex
BACKEND_ORDER_QUERY=api,opencode,claude_code,codex
BACKEND_ORDER_LINT=api,opencode,claude_code,codex
```

## Vault Missing Or Incomplete

Show the active vault:

```bash
epistora vault show
```

Initialize or repair the folder structure:

```bash
epistora init --vault /path/to/vault
```

Switch vaults:

```bash
epistora vault use /path/to/new-vault
```

Copy the current vault while switching:

```bash
epistora vault use /path/to/new-vault --copy-current
```

## Readwise Import Works But No Notes Appear

Readwise import creates catalog rows and raw/content-ready state without
necessarily compiling every item. Compile pending briefs:

```bash
epistora brief pending --limit 5
```

Or use Studio's Readwise sync and brief controls:

```bash
epistora studio
```

## Raindrop Or URL Ingest Fails

Try a small batch:

```bash
epistora ingest latest --limit 1
```

For one URL:

```bash
epistora ingest url "https://example.com/article" --force
```

Common causes:

- No backend is available.
- The page blocks extraction.
- The source is private, paywalled, or JavaScript-heavy.
- Browser fallback is disabled.

Optional browser fallback requires Playwright:

```bash
uv sync --extra browser
uv run playwright install chromium
```

Then set:

```bash
BROWSER_FALLBACK_ENABLED=true
ARTICLE_USE_BROWSER_FALLBACK=true
```

## YouTube Transcript Issues

Check whether transcript fallback is enabled:

```bash
YOUTUBE_USE_YTDLP_FALLBACK=true
```

Install `yt-dlp` if you rely on that fallback. Very long transcripts may be
chunked before analysis according to:

```bash
INGEST_YOUTUBE_EVIDENCE_MAX_CHARS=100000
INGEST_YOUTUBE_CHUNK_CHARS=24000
```

## X/Twitter Extraction Issues

The default path uses mirror/oEmbed fallbacks when enabled:

```bash
X_MIRROR_ENABLED=true
X_OEMBED_ENABLED=true
```

For official API access:

```bash
X_API_ENABLED=true
X_API_BEARER_TOKEN=...
```

## Studio Does Not Load

Rebuild frontend assets:

```bash
cd studio
npm install
npm run build
cd ..
epistora studio
```

If the preferred port is busy, `epistora studio` selects another available port.

If API auth is enabled, use the same local Studio session started by the CLI or
provide the configured bearer token to direct API clients.

## API Requests Return 401

When `EPISTORA_API_KEY` is set, protected routes require:

```text
Authorization: Bearer <token>
```

`/health` is intentionally unauthenticated.

## JSON Export Missing

Enable the sink:

```bash
ARTIFACT_SINK_IDS=markdown_vault,json_export
```

Default export path:

```text
<vault>/.system/exports/json/
```

`json_export` only writes when a source is compiled/published through the sink.

## Large Raw Notes Or Blob Confusion

Large evidence can be stored as blob-backed raw captures:

```bash
EVIDENCE_BLOB_DIR=.system/blobs
EVIDENCE_BLOB_THRESHOLD_BYTES=50000
EVIDENCE_BLOB_PREVIEW_CHARS=4000
```

The visible raw note remains the stable evidence entrypoint and points to the
full blob path plus checksum metadata.

## Reset Generated State

For a clean replay while keeping the vault shell:

```bash
epistora reset-generated --yes --archive
```

This clears generated artifacts and can archive existing generated outputs. It
does not replace the need to back up important vault content.
