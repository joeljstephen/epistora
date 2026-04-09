# Quickstart Guide

Get Epistora running in under 5 minutes.

## What You'll Need

- **Python 3.11 or later** — check with `python --version`
- **A Raindrop.io account** (free) — for syncing your saved bookmarks
- **An LLM backend** — at least one of:
  - An OpenAI API key (or any OpenAI-compatible API)
  - [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed
  - [OpenCode](https://github.com/opencode-ai/opencode) installed

## Step 1: Install Epistora

The recommended way to install is with [uv](https://docs.astral.sh/uv/):

```bash
# Install uv (if you don't have it)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install Epistora from a local checkout
uv tool install .

# Or install from GitHub once the repo is accessible to you
# uv tool install git+ssh://git@github.com/joeljstephen/epistora.git
```

Or install from source for development:

```bash
git clone https://github.com/joeljstephen/epistora.git
cd epistora
uv sync --extra dev
```

## Step 2: Run the Setup Wizard

```bash
epistora setup
```

The wizard will walk you through:

1. **Vault location** — where your knowledge files will live
2. **Raindrop connection** — your API token for syncing bookmarks
3. **Backend selection** — which LLM to use for content analysis
4. **Automation mode** — how aggressively to process bookmarks

It creates all the configuration for you automatically.

## Step 3: Verify Everything Works

```bash
epistora doctor
```

This checks your Python version, configuration, vault structure, backend
availability, and more. Fix any issues it reports.

## Step 4: Ingest Your First Content

```bash
# Start with one bookmark so you can verify the flow quickly
epistora ingest latest --limit 1

# Or ingest a single URL
epistora ingest url "https://lilianweng.github.io/posts/2023-06-23-agent/"
```

If you want a short command reference:

```bash
epistora help
eps help
```

## Step 5: Use Your Vault

Your knowledge vault is now populated! You can:

### Open in Obsidian

Open the vault folder in [Obsidian](https://obsidian.md/) and browse your
compiled knowledge notes, topics, entities, and concepts.

### Query with Claude Code or OpenCode

```bash
cd ~/epistora-vault  # or wherever your vault lives

# Then ask questions naturally:
# "What do I know about AI agents?"
# "Compare what different sources say about RAG vs fine-tuning"
```

The agent reads `AGENTS.md` and navigates your vault to produce grounded,
source-backed answers.

### Set Up Automation

```bash
# Process bookmarks automatically
epistora automation run-pending

# Or generate OS scheduler config for hands-free operation
epistora automation generate-scheduler --platform macos --mode safe
```

## What's Next?

- **`epistora status`** — see vault stats and configuration
- **`epistora vault use <path>`** — switch to a different vault without rerunning setup
- **`epistora lint`** — check vault health
- **`epistora backend status`** — see backend availability
- **`epistora automation status`** — see automation queue status

See the full [README](../README.md) for detailed documentation on all
commands, backends, automation modes, and more.
