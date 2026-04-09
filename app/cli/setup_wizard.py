"""Interactive setup wizard for first-time Epistora configuration."""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path
from textwrap import dedent

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

BACKENDS = {
    "api": "Direct API (OpenAI-compatible endpoint)",
    "claude_code": "Claude Code CLI",
    "opencode": "OpenCode CLI",
    "codex": "Codex CLI",
}

AUTOMATION_MODES = {
    "safe": "No LLM cost — fetch and archive only",
    "balanced": "Capped LLM enrichment per run",
    "deep": "Full LLM analysis with topic/entity/concept updates",
}


def _prompt_vault_path() -> Path:
    """Ask the user where to create the vault."""
    console.print()
    console.print("[bold]Where should your knowledge vault live?[/bold]")
    console.print(
        "This is the folder where Epistora stores your compiled knowledge as markdown files."
    )
    console.print("You can open it in Obsidian or any markdown editor.\n")

    default = str(Path.home() / "epistora-vault")
    raw = typer.prompt("Vault path", default=default).strip()
    return Path(raw).expanduser().resolve()


def _prompt_raindrop() -> tuple[str, int]:
    """Ask the user for Raindrop.io configuration."""
    console.print()
    console.print("[bold]Raindrop.io Connector[/bold]")
    console.print("Epistora syncs bookmarks from Raindrop.io. You need an API token to connect.")
    console.print(
        "Get yours at: [link=https://app.raindrop.io/settings/integrations]"
        "https://app.raindrop.io/settings/integrations[/link]"
    )
    console.print("(Create a test token — it's free and takes 30 seconds)\n")

    token = typer.prompt("Raindrop API token (or press Enter to skip)", default="").strip()
    collection_id = 0
    if token:
        console.print("  [dim]Collection ID 0 = all unsorted bookmarks (default)[/dim]")
        collection_id = typer.prompt("Raindrop collection ID", default=0, type=int)

    return token, collection_id


def _prompt_backend() -> dict:
    """Ask the user which backend to use."""
    console.print()
    console.print("[bold]Backend Selection[/bold]")
    console.print("Epistora uses an LLM backend to analyze content and compile knowledge notes.")
    console.print("You need at least one backend configured.\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("#", style="dim", width=3)
    table.add_column("Backend")
    table.add_column("Description")
    table.add_row("1", "Direct API", "OpenAI-compatible API endpoint (easiest)")
    table.add_row("2", "Claude Code", "Claude Code CLI (if installed)")
    table.add_row("3", "OpenCode", "OpenCode CLI (if installed)")
    table.add_row("4", "Codex", "Codex CLI (if installed)")
    console.print(table)

    choice = typer.prompt("\nPrimary backend [1-4]", default="1").strip()
    if choice not in {"1", "2", "3", "4"}:
        console.print(f"[yellow]Unknown choice '{choice}', using Direct API.[/yellow]")
        choice = "1"

    config: dict = {
        "api_enabled": "false",
        "opencode_enabled": "false",
        "claude_code_enabled": "false",
        "codex_enabled": "false",
    }

    if choice == "1":
        console.print("\n[bold]API Backend Configuration[/bold]")
        api_key = typer.prompt("API key (e.g. sk-...)", default="").strip()
        model = typer.prompt("Model name", default="gpt-4o-mini").strip()
        base_url = typer.prompt("Base URL (leave empty for OpenAI)", default="").strip()
        config["api_enabled"] = "true"
        config["api_api_key"] = api_key
        config["api_model"] = model
        if base_url:
            config["api_base_url"] = base_url
        backend_order = "api,opencode,claude_code,codex"
    elif choice == "2":
        console.print("\n[bold]Claude Code Configuration[/bold]")
        binary = shutil.which("claude")
        if binary:
            console.print(f"  [green]Found claude at: {binary}[/green]")
        else:
            console.print("  [yellow]'claude' not found on PATH — install it first[/yellow]")
        model = typer.prompt("Claude Code model", default="claude-sonnet-4-20250514").strip()
        config["claude_code_enabled"] = "true"
        config["claude_code_model"] = model
        backend_order = "claude_code,api,opencode,codex"
    elif choice == "3":
        console.print("\n[bold]OpenCode Configuration[/bold]")
        binary = shutil.which("opencode")
        if binary:
            console.print(f"  [green]Found opencode at: {binary}[/green]")
        else:
            console.print("  [yellow]'opencode' not found on PATH — install it first[/yellow]")
        model = typer.prompt("OpenCode model", default="").strip()
        config["opencode_enabled"] = "true"
        if model:
            config["opencode_model"] = model
        backend_order = "opencode,api,claude_code,codex"
    elif choice == "4":
        console.print("\n[bold]Codex Configuration[/bold]")
        binary = shutil.which("codex")
        if binary:
            console.print(f"  [green]Found codex at: {binary}[/green]")
        else:
            console.print("  [yellow]'codex' not found on PATH — install it first[/yellow]")
        model = typer.prompt("Codex model", default="").strip()
        config["codex_enabled"] = "true"
        if model:
            config["codex_model"] = model
        backend_order = "codex,api,opencode,claude_code"

    config["backend_order_ingest"] = backend_order
    config["backend_order_query"] = backend_order
    config["backend_order_lint"] = backend_order

    return config


def _prompt_automation() -> dict:
    """Ask the user about automation preferences."""
    console.print()
    console.print("[bold]Automation Mode[/bold]")
    console.print("Epistora can automatically discover and process your bookmarks.\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Mode", width=10)
    table.add_column("LLM Cost", width=10)
    table.add_column("Description")
    for mode, desc in AUTOMATION_MODES.items():
        cost = "None" if mode == "safe" else ("Capped" if mode == "balanced" else "Full")
        table.add_row(mode, cost, desc)
    console.print(table)

    mode = typer.prompt("\nDefault automation mode", default="safe").strip().lower()
    if mode not in AUTOMATION_MODES:
        console.print(f"[yellow]Unknown mode '{mode}', using 'safe'[/yellow]")
        mode = "safe"

    enable = typer.confirm("Enable automation?", default=True)

    return {
        "automation_enabled": str(enable).lower(),
        "automation_default_mode": mode,
    }


def _prompt_scheduler() -> bool:
    """Ask if the user wants OS scheduler helpers generated."""
    console.print()
    console.print("[bold]Scheduled Automation[/bold]")
    console.print(
        "Epistora can generate configuration files for your OS scheduler\n"
        "so bookmarks are processed automatically on a timer."
    )
    return typer.confirm("Generate scheduler helper files?", default=False)


def _write_env_file(env_path: Path, config: dict) -> None:
    """Create or update the .env file from wizard answers."""
    env_path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                existing[key.strip()] = value.strip()

    merged = {**existing}
    for key, value in config.items():
        merged[key.upper()] = value

    lines = [
        "# Epistora configuration",
        "# Generated by: epistora setup",
        "# Edit as needed. See .env.example for all available settings.",
        "",
    ]

    groups = [
        ("Core", ["VAULT_PATH", "DATABASE_URL", "LOG_LEVEL"]),
        ("Raindrop", ["RAINDROP_API_TOKEN", "RAINDROP_COLLECTION_ID"]),
        ("API Backend", ["API_ENABLED", "API_API_KEY", "API_MODEL", "API_BASE_URL"]),
        (
            "CLI Backends",
            [
                "OPENCODE_ENABLED",
                "OPENCODE_MODEL",
                "OPENCODE_BINARY",
                "CLAUDE_CODE_ENABLED",
                "CLAUDE_CODE_MODEL",
                "CLAUDE_CODE_BINARY",
                "CODEX_ENABLED",
                "CODEX_MODEL",
                "CODEX_BINARY",
            ],
        ),
        (
            "Backend Order",
            [
                "BACKEND_ORDER_INGEST",
                "BACKEND_ORDER_QUERY",
                "BACKEND_ORDER_LINT",
            ],
        ),
        (
            "Automation",
            [
                "AUTOMATION_ENABLED",
                "AUTOMATION_DEFAULT_MODE",
                "AUTOMATION_DISCOVER_BATCH_LIMIT",
                "AUTOMATION_PROCESS_LIMIT",
            ],
        ),
    ]

    written_keys: set[str] = set()
    for group_name, keys in groups:
        group_lines = []
        for key in keys:
            if key in merged:
                group_lines.append(f"{key}={merged[key]}")
                written_keys.add(key)
        if group_lines:
            lines.append(f"# --- {group_name} ---")
            lines.extend(group_lines)
            lines.append("")

    remaining = {k: v for k, v in merged.items() if k not in written_keys}
    if remaining:
        lines.append("# --- Other ---")
        for key, value in sorted(remaining.items()):
            lines.append(f"{key}={value}")
        lines.append("")

    env_path.write_text("\n".join(lines) + "\n")


def _load_template_text(relative_path: str) -> str | None:
    """Load a template file from the source tree when available."""
    template_path = Path(__file__).resolve().parents[2] / "knowledge_vault_template" / relative_path
    if template_path.exists():
        return template_path.read_text(encoding="utf-8")
    return None


def _default_agents_content() -> str:
    """Fallback AGENTS.md content when template files are unavailable."""
    return dedent(
        """\
        # Epistora Vault — Agent Operating Manual

        Read this file first when working inside the vault.

        ## Vault Layers

        - `raw/` contains immutable evidence captures.
        - `wiki/` contains maintained knowledge notes and indexes.
        - `outputs/` contains temporary answers and reports.
        - `.system/` is internal state and should not be used for knowledge answers.

        ## Navigation Sequence

        1. Read `AGENTS.md`.
        2. Read `wiki/indexes/START_HERE.md`.
        3. Read `wiki/indexes/QUERY_PROTOCOL.md`.
        4. Use `TOPICS.md`, `ENTITIES.md`, and `CONCEPTS.md` to find candidate notes.
        5. Prefer `wiki/sources/` for grounded evidence.
        6. Escalate to `raw/` only when extraction quality is weak or exact text matters.

        ## Answer Rules

        - Ground claims in specific source notes or raw captures.
        - Surface contradictions and uncertainty explicitly.
        - Distinguish direct findings from synthesis.
        - Do not use `.system/` as knowledge content.
        - Promote durable answers into `wiki/synthesis/` when appropriate.
        """
    )


def _initialize_vault(vault_path: Path) -> None:
    """Create the vault directory structure."""
    from app.vault.index_updater import rebuild_indexes
    from app.vault.paths import ensure_vault_dirs

    ensure_vault_dirs(vault_path)

    agents_dest = vault_path / "AGENTS.md"
    if not agents_dest.exists():
        agents_content = _load_template_text("AGENTS.md") or _default_agents_content()
        agents_dest.write_text(agents_content, encoding="utf-8")

    for idx_name in ["INDEX.md", "TOPICS.md", "ENTITIES.md", "CONCEPTS.md"]:
        idx_path = vault_path / "wiki" / "indexes" / idx_name
        if not idx_path.exists():
            idx_path.write_text(
                f"# {idx_name.replace('.md', '')}\n\n"
                "_Empty — will be populated after first ingest._\n",
                encoding="utf-8",
            )

    for log_name, log_title in [("ingest-log.md", "Ingest Log"), ("lint-log.md", "Lint Log")]:
        log_path = vault_path / "wiki" / "logs" / log_name
        if not log_path.exists():
            log_path.write_text(
                f"# {log_title}\n\nAppend-only log.\n\n---\n\n",
                encoding="utf-8",
            )

    rebuild_indexes(vault_path)


def _detect_platform() -> str:
    """Detect the current OS for scheduler generation."""
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    elif system == "linux":
        return "linux"
    elif system == "windows":
        return "windows"
    return "unknown"


def run_setup_wizard(
    non_interactive: bool = False,
    vault_path_override: str | None = None,
) -> None:
    """Run the full interactive setup wizard."""
    del non_interactive

    console.print(
        Panel(
            "[bold blue]Welcome to Epistora![/bold blue]\n\n"
            "This wizard will guide you through setting up your personal\n"
            "knowledge compiler. It takes about 2 minutes.",
            title="Setup Wizard",
            border_style="blue",
        )
    )

    # Step 1: Vault location
    if vault_path_override:
        vault_path = Path(vault_path_override).expanduser().resolve()
    else:
        vault_path = _prompt_vault_path()

    # Step 2: Raindrop connector
    raindrop_token, raindrop_collection = _prompt_raindrop()

    # Step 3: Backend
    backend_config = _prompt_backend()

    # Step 4: Automation
    automation_config = _prompt_automation()

    # Step 5: Scheduler
    generate_scheduler = _prompt_scheduler()

    # Build the config
    env_config: dict[str, str] = {
        "vault_path": str(vault_path),
        "database_url": f"sqlite:///{vault_path / '.system' / 'epistora.db'}",
    }

    if raindrop_token:
        env_config["raindrop_api_token"] = raindrop_token
    if raindrop_collection:
        env_config["raindrop_collection_id"] = str(raindrop_collection)

    env_config.update(backend_config)
    env_config.update(automation_config)

    # Write config
    console.print()
    console.print("[bold]Creating configuration...[/bold]")

    from app.config import preferred_env_file

    env_path = preferred_env_file()

    _write_env_file(env_path, env_config)
    console.print(f"  [green]✓[/green] Configuration written to {env_path}")

    # Initialize vault
    console.print("[bold]Initializing vault...[/bold]")
    _initialize_vault(vault_path)
    console.print(f"  [green]✓[/green] Vault created at {vault_path}")

    # Initialize database
    try:
        from app.config import reset_settings

        reset_settings()
        os.environ["VAULT_PATH"] = str(vault_path)
        os.environ["DATABASE_URL"] = env_config.get(
            "database_url", f"sqlite:///{vault_path / '.system' / 'epistora.db'}"
        )

        db_path = vault_path / ".system" / "epistora.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        from app.storage.sqlite import Database

        db = Database(db_path)
        db.connect()
        db.close()
        console.print(f"  [green]✓[/green] Database initialized at {db_path}")
    except Exception as e:
        console.print(f"  [yellow]⚠[/yellow] Database init: {e}")

    # Generate scheduler files if requested
    if generate_scheduler:
        plat = _detect_platform()
        if plat != "unknown":
            try:
                from app.automation.scheduler_helpers import (
                    generate_launchd_plist,
                    generate_scheduler_instructions,
                    generate_systemd_timer,
                    generate_windows_task_xml,
                )

                mode = automation_config.get("automation_default_mode", "safe")
                out_dir = vault_path / ".system" / "scheduler"
                out_dir.mkdir(parents=True, exist_ok=True)

                if plat == "macos":
                    content = generate_launchd_plist(mode=mode)
                    (out_dir / "com.epistora.automation.plist").write_text(content)
                elif plat == "linux":
                    svc, tmr = generate_systemd_timer(mode=mode)
                    (out_dir / "epistora-automation.service").write_text(svc)
                    (out_dir / "epistora-automation.timer").write_text(tmr)
                elif plat == "windows":
                    content = generate_windows_task_xml(mode=mode)
                    (out_dir / "epistora-automation.xml").write_text(content)

                instructions = generate_scheduler_instructions(mode=mode)
                (out_dir / "SCHEDULING.md").write_text(instructions)
                console.print(f"  [green]✓[/green] Scheduler files generated in {out_dir}")
            except Exception as e:
                console.print(f"  [yellow]⚠[/yellow] Scheduler generation: {e}")

    # Summary
    console.print()
    summary_lines = [
        f"[green]✓[/green] [bold]Vault:[/bold] {vault_path}",
        f"[green]✓[/green] [bold]Config:[/bold] {env_path}",
    ]
    if raindrop_token:
        summary_lines.append("[green]✓[/green] [bold]Raindrop:[/bold] Connected")
    else:
        summary_lines.append(
            "[yellow]○[/yellow] [bold]Raindrop:[/bold] "
            "Not configured (run `epistora connect raindrop` later)"
        )

    api_key = backend_config.get("api_api_key", "")
    if api_key:
        summary_lines.append("[green]✓[/green] [bold]Backend:[/bold] API configured")
    else:
        summary_lines.append(
            "[yellow]○[/yellow] [bold]Backend:[/bold] "
            "CLI backends enabled (ensure they are installed)"
        )

    auto_mode = automation_config.get("automation_default_mode", "safe")
    summary_lines.append(f"[green]✓[/green] [bold]Automation:[/bold] {auto_mode} mode")

    console.print(
        Panel(
            "\n".join(summary_lines),
            title="[bold green]Setup Complete![/bold green]",
            border_style="green",
        )
    )

    console.print("\n[bold]Next steps:[/bold]\n")
    console.print("  1. Verify your setup:")
    console.print("     [cyan]epistora doctor[/cyan]\n")

    if raindrop_token:
        console.print("  2. Ingest your latest bookmarks:")
        console.print("     [cyan]epistora ingest latest[/cyan]\n")
        console.print("  3. Or sync from Raindrop:")
        console.print("     [cyan]epistora sync-raindrop[/cyan]\n")
    else:
        console.print("  2. Connect Raindrop.io:")
        console.print("     [cyan]epistora connect raindrop[/cyan]\n")
        console.print("  3. Ingest a URL directly:")
        console.print("     [cyan]epistora ingest url https://example.com/article[/cyan]\n")

    console.print("  Open your vault in Obsidian or point Claude Code / OpenCode at it!")
    console.print(f"  [dim]{vault_path}[/dim]\n")
