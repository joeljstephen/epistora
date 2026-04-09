# Troubleshooting

Common issues and how to fix them.

## First Steps

Always start by running the doctor command:

```bash
epistora doctor
```

This checks your entire environment and gives specific recommendations.

---

## Installation Issues

### "epistora: command not found"

**Cause:** The CLI is not on your PATH.

**Fix:**

If installed with `uv tool install`:
```bash
# Make sure uv's bin directory is on your PATH
export PATH="$HOME/.local/bin:$PATH"
# Add this line to your shell profile (~/.zshrc, ~/.bashrc, etc.)
```

If installed from source:
```bash
cd epistora
uv run epistora --help    # run via uv
# or
source .venv/bin/activate
epistora --help            # run from virtualenv
```

### "ModuleNotFoundError: No module named 'app'"

**Cause:** Epistora is not installed in your current environment.

**Fix:**
```bash
uv sync           # if using uv
pip install -e .   # if using pip
```

### uv is not installed

**Fix:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # macOS/Linux
# Or on Windows:
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

---

## Configuration Issues

### "No .env file found"

**Fix:** Run the setup wizard:
```bash
epistora setup
```

Or manually copy the example:
```bash
cp .env.example .env
# Then edit .env with your settings
```

If you're using the installed CLI instead of a source checkout, `epistora setup`
creates the config file in Epistora's OS-specific app directory automatically.

### "Configuration error: Raindrop API token not configured"

**Fix:**
```bash
epistora connect raindrop
```

Or set `RAINDROP_API_TOKEN` in your Epistora config file. Get a token at:
https://app.raindrop.io/settings/integrations

### Settings not taking effect

**Cause:** You're editing a different config file than the one Epistora is loading.

**Fix:** Either:
- Run `epistora doctor` and check the reported config path
- If running from a source checkout, edit that checkout's `.env`
- If running an installed CLI, edit Epistora's app config file
- Set `VAULT_PATH` and other settings as environment variables
- Use absolute paths in your config file

---

## Vault Issues

### "Vault not found"

**Fix:**
```bash
# Check where it's configured:
epistora status

# Initialize it:
epistora init --vault /path/to/your/vault
# Or re-run setup:
epistora setup
```

### Vault exists but is incomplete

**Fix:**
```bash
epistora init --vault /path/to/existing/vault
```

This is safe to run on existing vaults — it only adds missing directories
and files without overwriting anything.

### Vault notes look wrong or are missing content

**Possible causes:**
- Backend (LLM) is not configured or not available
- Content extraction failed for certain URLs
- The source is behind a paywall or requires JavaScript

**Fix:**
```bash
# Check backend status
epistora backend status

# Try re-ingesting with force
epistora ingest url --force "https://example.com/article"

# Check the raw capture in raw/ for extraction quality
```

---

## Backend Issues

### "No backend available"

**Fix:** You need at least one LLM backend configured.

**Easiest option — API backend:**
```bash
# In your Epistora config:
API_API_KEY=sk-your-key-here
API_MODEL=gpt-4o-mini
```

**CLI backend option:**
```bash
# Make sure claude/opencode/codex is installed and on PATH
which claude
which opencode
which codex

# Check availability:
epistora backend status
```

### Backend times out

**Fix:** Increase the timeout in your Epistora config:
```env
OPENCODE_TIMEOUT_SECONDS=600
CLAUDE_CODE_TIMEOUT_SECONDS=300
```

### "opencode/claude not found on PATH"

**Fix:** Install the CLI tool and make sure it's on your PATH:
```bash
which opencode  # should show a path
which claude    # should show a path
```

If installed but not found, add its directory to your PATH.

---

## Raindrop Issues

### Sync returns no items

**Possible causes:**
- No new bookmarks since last sync
- Wrong collection ID
- Token has expired

**Fix:**
```bash
# Check configuration
epistora doctor

# Try syncing with force (re-processes already-seen items)
epistora sync-raindrop --force --limit 5

# Verify your token works at:
# https://api.raindrop.io/rest/v1/raindrops/0
# (paste your token as a Bearer token)
```

### "403 Forbidden" from Raindrop

**Cause:** Invalid or expired API token.

**Fix:** Generate a new token at https://app.raindrop.io/settings/integrations
and update your Epistora config:
```bash
epistora connect raindrop
```

---

## Automation Issues

### Automation does nothing

**Fix:** Make sure automation is enabled:
```env
AUTOMATION_ENABLED=true
```

Then run:
```bash
epistora automation run-pending --mode safe
```

### Items stuck in "processing" state

**Cause:** A previous run may have crashed mid-processing.

**Fix:**
```bash
# Check the queue
epistora automation list-pending

# Retry failed items
epistora automation retry-failed
```

### Scheduler not running

**Fix:**
```bash
# Regenerate scheduler config
epistora automation generate-scheduler --platform macos --mode safe

# Check if it's loaded (macOS)
launchctl list | grep epistora

# Check logs
cat logs/automation-stdout.log
cat logs/automation-stderr.log
```

---

## Cross-Platform Notes

### Windows

- Use `python` instead of `python3`
- Use `.\\.venv\\Scripts\\activate` to activate the virtualenv
- File paths use backslashes, but Epistora handles this internally
- For Task Scheduler, use `epistora automation generate-scheduler --platform windows`

### Linux

- Use `python3` or `python` (depending on your distro)
- For systemd scheduling, use `epistora automation generate-scheduler --platform linux`
- Make sure your user has write access to the vault directory

### macOS

- Python from Homebrew (`brew install python`) works well
- For launchd scheduling, use `epistora automation generate-scheduler --platform macos`

---

## Getting Help

If you're still stuck:

1. Run `epistora doctor` and check the output carefully
2. Check the [GitHub issues](https://github.com/joeljstephen/epistora/issues)
3. Open a new issue with:
   - Your OS and Python version
   - The output of `epistora doctor`
   - Steps to reproduce the problem
   - Any error messages
