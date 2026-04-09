"""Epistora CLI — primary operator interface."""

from __future__ import annotations

import asyncio
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="epistora",
    help="Epistora — local-first personal knowledge compiler.\n\n"
    "Turn saved bookmarks into a persistent, agent-queryable knowledge base.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


def _print_version(value: bool) -> None:
    """Print the installed package version and exit."""
    if not value:
        return

    try:
        resolved_version = package_version("epistora")
    except PackageNotFoundError:
        resolved_version = "0.1.0+local"

    console.print(f"epistora {resolved_version}")
    raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_print_version,
        is_eager=True,
        help="Show the Epistora version and exit.",
    ),
):
    """Epistora CLI."""
    del version


def _run(coro):
    """Run an async coroutine from the sync CLI."""
    return asyncio.run(coro)


def _looks_like_epistora_vault(path: Path) -> bool:
    return (
        (path / "wiki").exists()
        and (path / "raw").exists()
        and (path / "wiki" / "indexes").exists()
        and (path / "wiki" / "logs").exists()
    )


# ---------------------------------------------------------------------------
# Core commands
# ---------------------------------------------------------------------------


@app.command()
def setup(
    vault: str = typer.Option(None, "--vault", "-v", help="Vault path (skip interactive prompt)"),
):
    """Interactive setup wizard — configure Epistora from scratch.

    This is the recommended way to get started. It walks you through:
    vault location, Raindrop connection, backend selection, automation mode,
    and generates all required configuration.
    """
    from app.cli.setup_wizard import run_setup_wizard

    run_setup_wizard(vault_path_override=vault)


@app.command()
def doctor():
    """Check your environment and configuration for issues.

    Verifies Python version, config files, vault structure, backend availability,
    and more. Prints a clear report with recommendations.
    """
    from app.cli.doctor import run_doctor

    exit_code = run_doctor()
    raise typer.Exit(exit_code)


@app.command()
def init(
    vault_path: str = typer.Option(
        "./knowledge_vault",
        "--vault",
        "-v",
        help="Path where the knowledge vault will be created",
    ),
):
    """Initialize a new knowledge vault and database.

    Creates the vault directory structure, copies template files, and
    initializes the SQLite database. Safe to run on existing vaults.
    """
    from app.cli.setup_wizard import _initialize_vault
    from app.config import get_settings

    target = Path(vault_path).resolve()

    if target.exists() and any(target.iterdir()):
        console.print(f"[yellow]Vault directory already exists at {target}[/yellow]")
        if _looks_like_epistora_vault(target):
            console.print(
                "[blue]Existing Epistora vault detected; ensuring required files exist.[/blue]"
            )
        elif not typer.confirm("Reinitialize? (existing files will be kept)"):
            raise typer.Abort()

    _initialize_vault(target)

    settings = get_settings()
    db_path = settings.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    from app.storage.sqlite import Database

    db = Database(db_path)
    db.connect()
    db.close()

    console.print(f"[green]✓ Vault initialized at {target}[/green]")
    console.print(f"[green]✓ Database initialized at {db_path}[/green]")
    console.print("\nNext steps:")
    console.print("  1. Run: [cyan]epistora setup[/cyan] (if you haven't yet)")
    console.print("  2. Run: [cyan]epistora doctor[/cyan] to verify")
    console.print("  3. Run: [cyan]epistora ingest url <url>[/cyan]")


@app.command()
def status():
    """Show vault and system status."""
    from app.config import get_settings
    from app.storage.repositories import SourceRepository
    from app.storage.sqlite import Database
    from app.vault.parser import scan_vault

    settings = get_settings()
    vault_path = Path(settings.vault_path)

    table = Table(title="Epistora Status")
    table.add_column("Item", style="bold")
    table.add_column("Value")

    table.add_row("Vault path", str(vault_path))
    table.add_row("Vault exists", "yes" if vault_path.exists() else "no")
    table.add_row("Database", str(settings.db_path))

    if vault_path.exists():
        notes = scan_vault(vault_path)
        by_type: dict[str, int] = {}
        for n in notes:
            by_type[n.note_type] = by_type.get(n.note_type, 0) + 1
        for ntype, count in sorted(by_type.items()):
            table.add_row(f"  {ntype} notes", str(count))

    if settings.db_path.exists():
        db = Database(settings.db_path)
        db.connect()
        source_repo = SourceRepository(db)
        table.add_row("Processed sources (DB)", str(source_repo.count()))
        db.close()

    table.add_row("OpenAI model", settings.openai_model)
    table.add_row("Raindrop configured", "yes" if settings.raindrop_api_token else "no")
    table.add_row("API auth enabled", "yes" if settings.epistora_api_key else "no")

    console.print(table)


# ---------------------------------------------------------------------------
# Ingest commands
# ---------------------------------------------------------------------------


def _ingest_url_impl(
    url: str = typer.Argument(..., help="URL to ingest"),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-run ingest even if the URL was already compiled before",
    ),
):
    """Ingest a single URL into the knowledge vault."""
    from app.services.ingest_service import ingest_url as _ingest

    console.print(f"[blue]Ingesting:[/blue] {url}")

    try:
        result = _run(_ingest(url, force=force))
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if result.deduplicated:
        console.print(f"[yellow]Already ingested.[/yellow] Source note: {result.source_note_path}")
        return

    if result.errors:
        console.print(f"[red]Completed with errors:[/red] {'; '.join(result.errors)}")
    else:
        console.print("[green]✓ Ingest complete[/green]")

    table = Table(title="Ingest Result")
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("Source Note", result.source_note_path)
    table.add_row("Raw Capture", result.raw_capture_path)
    table.add_row("Type", result.source_type)
    table.add_row("Topics", ", ".join(result.topics_updated) or "none")
    table.add_row("Entities", ", ".join(result.entities_updated) or "none")
    table.add_row("Concepts", ", ".join(result.concepts_updated) or "none")
    console.print(table)


ingest_app = typer.Typer(
    name="ingest",
    help="Ingest content from bookmarks or direct URLs.",
    add_completion=False,
)
app.add_typer(ingest_app, name="ingest")


@ingest_app.command("url")
def ingest_url(
    url: str = typer.Argument(..., help="URL to ingest"),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-run ingest even if the URL was already compiled before",
    ),
):
    """Ingest a single URL into the knowledge vault."""
    _ingest_url_impl(url=url, force=force)


@app.command("ingest-url", hidden=True)
def ingest_url_compat(
    url: str = typer.Argument(..., help="URL to ingest"),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-run ingest even if the URL was already compiled before",
    ),
):
    """Backward-compatible alias for 'ingest url'."""
    _ingest_url_impl(url=url, force=force)


def _ingest_latest_impl(
    limit: int = typer.Option(10, "--limit", "-n", help="Max items to ingest"),
    connector: str = typer.Option("raindrop", "--connector", "-c", help="Inbox connector"),
    force: bool = typer.Option(False, "--force", help="Re-run for already-seen sources"),
):
    """Ingest the latest bookmarks from your configured connector.

    This is a convenience command that syncs recent items from your
    inbox connector (Raindrop by default) and ingests them.
    """
    from app.services.ingest_service import sync_inbox as _sync

    console.print(f"[blue]Ingesting latest {limit} items from {connector}...[/blue]")

    try:
        results = _run(_sync(connector_id=connector, limit=limit, force=force))
    except ValueError as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        console.print("[dim]Run 'epistora connect raindrop' to set up your connector.[/dim]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Ingest failed:[/red] {e}")
        raise typer.Exit(1)

    ingested = sum(1 for r in results if not r.deduplicated and not r.errors)
    skipped = sum(1 for r in results if r.deduplicated)
    failed = sum(1 for r in results if r.errors)

    console.print(
        f"[green]✓ Ingest complete:[/green] {ingested} ingested, {skipped} skipped, {failed} failed"
    )


@ingest_app.command("latest")
def ingest_latest(
    limit: int = typer.Option(10, "--limit", "-n", help="Max items to ingest"),
    connector: str = typer.Option("raindrop", "--connector", "-c", help="Inbox connector"),
    force: bool = typer.Option(False, "--force", help="Re-run for already-seen sources"),
):
    """Ingest the latest bookmarks from your configured connector."""
    _ingest_latest_impl(limit=limit, connector=connector, force=force)


@app.command("sync-raindrop")
def sync_raindrop(
    limit: int = typer.Option(25, "--limit", "-n", help="Max items to sync"),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-run ingest for fetched items even if they were already compiled",
    ),
):
    """Sync recent items from Raindrop.io and ingest them."""
    from app.services.ingest_service import sync_inbox as _sync

    console.print("[blue]Syncing from Raindrop...[/blue]")

    try:
        results = _run(_sync(connector_id="raindrop", limit=limit, force=force))
    except ValueError as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Sync failed:[/red] {e}")
        raise typer.Exit(1)

    ingested = sum(1 for r in results if not r.deduplicated and not r.errors)
    skipped = sum(1 for r in results if r.deduplicated)
    failed = sum(1 for r in results if r.errors)

    console.print(
        f"[green]✓ Sync complete:[/green] {ingested} ingested, {skipped} skipped, {failed} failed"
    )


@app.command("sync-inbox")
def sync_inbox(
    connector: str = typer.Option("raindrop", "--connector", "-c", help="Inbox connector ID"),
    limit: int = typer.Option(25, "--limit", "-n", help="Max items to sync"),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-run ingest for fetched items even if they were already compiled",
    ),
):
    """Sync recent items from a configured inbox connector and ingest them."""
    from app.services.ingest_service import sync_inbox as _sync

    console.print(f"[blue]Syncing inbox connector:[/blue] {connector}")

    try:
        results = _run(_sync(connector_id=connector, limit=limit, force=force))
    except ValueError as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Sync failed:[/red] {e}")
        raise typer.Exit(1)

    ingested = sum(1 for r in results if not r.deduplicated and not r.errors)
    skipped = sum(1 for r in results if r.deduplicated)
    failed = sum(1 for r in results if r.errors)

    console.print(
        f"[green]✓ Sync complete:[/green] {ingested} ingested, {skipped} skipped, {failed} failed"
    )


# ---------------------------------------------------------------------------
# Vault maintenance
# ---------------------------------------------------------------------------


@app.command(deprecated=True)
def query(
    question: str = typer.Argument(..., help="Question to ask the vault"),
    save: bool = typer.Option(False, "--save", "-s", help="Save answer to outputs/"),
):
    """[DEPRECATED] Query the knowledge vault with a question.

    Prefer pointing Claude Code or OpenCode at the vault directory directly.
    See AGENTS.md and wiki/indexes/START_HERE.md for the agent-first workflow.
    """
    import warnings

    warnings.warn(
        "`epistora query` is deprecated. Use Claude Code or OpenCode directly on the "
        "vault directory instead. See AGENTS.md for guidance.",
        DeprecationWarning,
        stacklevel=2,
    )
    console.print(
        "[yellow]Warning: `epistora query` is deprecated. "
        "Use Claude Code or OpenCode directly on the vault directory.[/yellow]\n"
    )

    from app.services.query_service import query_vault

    console.print(f"[blue]Querying:[/blue] {question}\n")

    try:
        result = _run(query_vault(question, save_synthesis=save))
    except Exception as e:
        console.print(f"[red]Query failed:[/red] {e}")
        raise typer.Exit(1)

    console.print(result.answer)
    console.print()

    if result.source_references:
        console.print("[bold]Sources consulted:[/bold]")
        for ref in result.source_references:
            console.print(f"  - {ref}")

    if result.saved_to:
        console.print(f"\n[green]Answer saved to:[/green] {result.saved_to}")


@app.command()
def lint():
    """Run health checks on the knowledge vault."""
    from app.services.lint_service import lint_vault

    console.print("[blue]Running vault lint...[/blue]")

    try:
        result = _run(lint_vault())
    except Exception as e:
        console.print(f"[red]Lint failed:[/red] {e}")
        raise typer.Exit(1)

    table = Table(title="Lint Summary")
    table.add_column("Metric", style="bold")
    table.add_column("Count")
    table.add_row("Total notes", str(result.total_notes))
    table.add_row("Orphan pages", str(result.orphan_pages))
    table.add_row("Missing backlinks", str(result.missing_backlinks))
    table.add_row("Weak pages", str(result.weak_pages))
    table.add_row("Total issues", str(len(result.issues)))
    console.print(table)

    for issue in result.issues[:20]:
        severity_color = {
            "error": "red",
            "warning": "yellow",
            "info": "blue",
        }.get(issue.severity, "white")
        console.print(
            f"  [{severity_color}][{issue.severity.upper()}][/{severity_color}] "
            f"{issue.category}: {issue.message}"
        )

    if result.report_path:
        console.print(f"\n[green]Full report:[/green] {result.report_path}")


@app.command("rebuild-indexes")
def rebuild_indexes():
    """Rebuild all vault index files."""
    from app.config import get_settings
    from app.vault.index_updater import rebuild_indexes as _rebuild

    settings = get_settings()
    vault_path = Path(settings.vault_path)

    if not vault_path.exists():
        console.print("[red]Vault not found. Run 'epistora init' first.[/red]")
        raise typer.Exit(1)

    updated = _rebuild(vault_path)
    console.print(f"[green]✓ Rebuilt {len(updated)} index files[/green]")
    for path in updated:
        console.print(f"  - {path}")


@app.command("reset-generated")
def reset_generated(
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation prompt"),
    archive: bool = typer.Option(
        True,
        "--archive/--no-archive",
        help="Archive current generated artifacts before clearing",
    ),
):
    """Reset generated vault content and internal state."""
    from app.config import get_settings
    from app.services.reset_service import reset_generated_state

    settings = get_settings()
    vault_path = Path(settings.vault_path)

    if not yes:
        confirmed = typer.confirm(
            f"Reset generated content under {vault_path}? This keeps source code and AGENTS.md."
        )
        if not confirmed:
            raise typer.Abort()

    result = reset_generated_state(archive_existing=archive)
    console.print("[green]✓ Generated vault artifacts reset[/green]")
    if result.get("archive_path"):
        console.print(f"[blue]Archive:[/blue] {result['archive_path']}")
    cleared = result.get("cleared", [])
    if isinstance(cleared, list):
        for relative in cleared:
            console.print(f"  - cleared {relative}")


# ---------------------------------------------------------------------------
# Backend commands
# ---------------------------------------------------------------------------

backend_app = typer.Typer(
    name="backend",
    help="Backend configuration and status.",
    add_completion=False,
)
app.add_typer(backend_app, name="backend")


@backend_app.command("status")
def backend_status():
    """Show which backend is configured and available for each task."""
    from app.backends.models import TaskName
    from app.compiler.llm import get_backend_router

    router = get_backend_router()
    table = Table(title="Backend Status")
    table.add_column("Task", style="bold")
    table.add_column("Backend")
    table.add_column("Model")
    table.add_column("Available")
    table.add_column("Reason")

    for task in TaskName:
        descriptors = router.describe_all(task)
        for desc in descriptors:
            color = "green" if desc.available else "red"
            table.add_row(
                task.value,
                desc.backend_type,
                desc.model or "-",
                f"[{color}]{'yes' if desc.available else 'no'}[/{color}]",
                desc.reason or "",
            )
    console.print(table)


@backend_app.command("setup")
def backend_setup_cmd():
    """Interactive backend configuration helper.

    Walks you through configuring your preferred LLM backend.
    """
    from app.cli.setup_wizard import _prompt_backend, _write_env_file
    from app.config import preferred_env_file

    console.print("[bold blue]Backend Configuration[/bold blue]\n")
    config = _prompt_backend()

    env_path = preferred_env_file()
    _write_env_file(env_path, config)
    console.print(f"\n[green]✓ Backend configuration saved to {env_path}[/green]")
    console.print("[dim]Run 'epistora backend status' to verify.[/dim]")


# Keep the top-level alias for backward compatibility
@app.command("backend-status", hidden=True)
def backend_status_compat():
    """Show backend status (alias for 'backend status')."""
    backend_status()


# ---------------------------------------------------------------------------
# Connect commands
# ---------------------------------------------------------------------------

connect_app = typer.Typer(
    name="connect",
    help="Connect to external services.",
    add_completion=False,
)
app.add_typer(connect_app, name="connect")


@connect_app.command("raindrop")
def connect_raindrop():
    """Set up Raindrop.io connection interactively.

    Walks you through getting an API token and configuring the connection.
    """
    from app.cli.setup_wizard import _write_env_file
    from app.config import preferred_env_file

    console.print("[bold blue]Raindrop.io Connection Setup[/bold blue]\n")
    console.print(
        "Epistora syncs your saved bookmarks from Raindrop.io.\nYou need an API token to connect.\n"
    )
    console.print(
        "  1. Go to [link=https://app.raindrop.io/settings/integrations]"
        "https://app.raindrop.io/settings/integrations[/link]"
    )
    console.print("  2. Create a new app (or use an existing one)")
    console.print("  3. Generate a test token")
    console.print()

    token = typer.prompt("Raindrop API token").strip()
    if not token:
        console.print("[yellow]No token provided. Aborting.[/yellow]")
        raise typer.Abort()

    collection_id = typer.prompt("Collection ID (0 = all unsorted bookmarks)", default=0, type=int)

    config = {
        "raindrop_api_token": token,
        "raindrop_collection_id": str(collection_id),
    }
    env_path = preferred_env_file()
    _write_env_file(env_path, config)

    console.print("\n[green]✓ Raindrop.io configured![/green]")
    console.print(f"  Token saved to {env_path}")
    console.print("\nNext steps:")
    console.print("  [cyan]epistora sync-raindrop[/cyan]        — sync recent bookmarks")
    console.print("  [cyan]epistora ingest latest[/cyan]        — ingest latest items")
    console.print("  [cyan]epistora automation run-pending[/cyan] — full automation run")


# ---------------------------------------------------------------------------
# Worker / legacy commands
# ---------------------------------------------------------------------------


@app.command()
def worker():
    """Run the background automation worker (legacy interval-based)."""
    import logging

    from app.config import get_settings

    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    console.print("[blue]Starting Epistora worker...[/blue]")
    interval = settings.sync_interval_seconds
    console.print(f"  Sync enabled: {settings.sync_enabled} (every {interval}s)")
    console.print(f"  Auto-lint enabled: {settings.auto_lint_enabled}")
    console.print(f"  Auto-rebuild enabled: {settings.auto_rebuild_indexes_enabled}")
    console.print("[dim]Press Ctrl+C to stop.[/dim]\n")

    from app.automation.worker import run_worker

    _run(run_worker())


@app.command("run-sync", hidden=True)
def run_sync_now(
    limit: int = typer.Option(25, "--limit", "-n", help="Max items to sync"),
):
    """Run a one-off Raindrop sync (alias)."""
    from app.automation.jobs import run_sync_job

    console.print("[blue]Running sync job...[/blue]")
    result = _run(run_sync_job(limit=limit))
    if result.get("status") == "ok":
        console.print(
            f"[green]✓ Sync complete:[/green] "
            f"{result.get('ingested', 0)} ingested, "
            f"{result.get('skipped', 0)} skipped, "
            f"{result.get('failed', 0)} failed"
        )
    else:
        console.print(f"[red]Sync failed:[/red] {result.get('error', 'unknown')}")
        raise typer.Exit(1)


@app.command("run-lint", hidden=True)
def run_lint_now():
    """Run a one-off lint check (alias)."""
    from app.automation.jobs import run_lint_job

    console.print("[blue]Running lint job...[/blue]")
    result = _run(run_lint_job())
    if result.get("status") == "ok":
        console.print(
            f"[green]✓ Lint complete:[/green] "
            f"{result.get('total_notes', 0)} notes, {result.get('issues', 0)} issues"
        )
    else:
        console.print(f"[red]Lint failed:[/red] {result.get('error', 'unknown')}")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Automation subcommand group
# ---------------------------------------------------------------------------

automation_app = typer.Typer(
    name="automation",
    help="Queue-based automation: discover, process, maintain, schedule.",
    add_completion=False,
)
app.add_typer(automation_app, name="automation")


@automation_app.command("setup")
def automation_setup_cmd():
    """Interactive automation configuration helper.

    Walks you through choosing an automation mode, enabling automation,
    and optionally generating OS scheduler files.
    """
    from app.cli.setup_wizard import _prompt_automation, _prompt_scheduler, _write_env_file
    from app.config import epistora_logs_dir, preferred_env_file

    console.print("[bold blue]Automation Configuration[/bold blue]\n")
    config = _prompt_automation()

    generate_scheduler = _prompt_scheduler()

    env_path = preferred_env_file()
    _write_env_file(env_path, config)
    console.print(f"\n[green]✓ Automation configuration saved to {env_path}[/green]")

    if generate_scheduler:
        from app.cli.setup_wizard import _detect_platform

        plat = _detect_platform()
        if plat != "unknown":
            from app.automation.scheduler_helpers import (
                generate_launchd_plist,
                generate_scheduler_instructions,
                generate_systemd_timer,
                generate_windows_task_xml,
            )

            mode = config.get("automation_default_mode", "safe")
            out = Path.cwd()
            epistora_logs_dir().mkdir(parents=True, exist_ok=True)

            if plat == "macos":
                content = generate_launchd_plist(mode=mode)
                path = out / "com.epistora.automation.plist"
                path.write_text(content)
                console.print(f"[green]Generated:[/green] {path}")
            elif plat == "linux":
                svc, tmr = generate_systemd_timer(mode=mode)
                (out / "epistora-automation.service").write_text(svc)
                (out / "epistora-automation.timer").write_text(tmr)
                console.print("[green]Generated:[/green] epistora-automation.service/timer")
            elif plat == "windows":
                content = generate_windows_task_xml(mode=mode)
                path = out / "epistora-automation.xml"
                path.write_text(content)
                console.print(f"[green]Generated:[/green] {path}")

            instructions = generate_scheduler_instructions(mode=mode)
            (out / "SCHEDULING.md").write_text(instructions)
            console.print("[green]Generated:[/green] SCHEDULING.md")

    console.print("\n[dim]Run 'epistora automation status' to verify.[/dim]")


@automation_app.command("discover")
def automation_discover(
    connector: str = typer.Option("raindrop", "--connector", "-c", help="Inbox connector ID"),
    limit: int = typer.Option(None, "--limit", "-n", help="Max items to discover"),
):
    """Discover and queue new bookmarks from configured inbox connectors."""
    from app.automation.runner import run_discover

    console.print(f"[blue]Discovering items from connector:[/blue] {connector}")
    result = _run(run_discover(connector_id=connector, limit=limit))

    if result.get("error"):
        console.print(f"[red]Discovery failed:[/red] {result['error']}")
        raise typer.Exit(1)

    console.print(
        f"[green]Discovery complete:[/green] "
        f"{result.get('items_discovered', 0)} discovered, "
        f"{result.get('items_skipped_duplicate', 0)} skipped (duplicate)"
    )


@automation_app.command("process-pending")
def automation_process_pending(
    mode: str = typer.Option("safe", "--mode", "-m", help="Processing mode: safe|balanced|deep"),
    limit: int = typer.Option(None, "--limit", "-n", help="Max items to process"),
    retry_failed: bool = typer.Option(False, "--retry-failed", help="Include retryable failures"),
    connector: str = typer.Option(None, "--connector", "-c", help="Filter by connector ID"),
):
    """Process pending queued items with mode-aware enrichment."""
    from app.automation.runner import run_process_pending

    console.print(f"[blue]Processing pending items in {mode} mode...[/blue]")
    result = _run(
        run_process_pending(
            mode=mode,
            limit=limit,
            retry_failed=retry_failed,
            connector_id=connector,
        )
    )

    if result.get("status") == "ok":
        console.print(
            f"[green]Processing complete:[/green] "
            f"{result.get('succeeded', 0)} succeeded, "
            f"{result.get('failed', 0)} failed"
        )
    else:
        console.print(f"[red]Processing failed:[/red] {result}")
        raise typer.Exit(1)


@automation_app.command("maintain")
def automation_maintain(
    lint: bool = typer.Option(None, "--lint/--no-lint", help="Run vault lint"),
    rebuild: bool = typer.Option(None, "--rebuild/--no-rebuild", help="Rebuild indexes"),
):
    """Run maintenance tasks (lint, index rebuild)."""
    from app.automation.runner import run_maintenance

    console.print("[blue]Running maintenance tasks...[/blue]")
    result = _run(run_maintenance(run_lint=lint, run_rebuild=rebuild))

    if result.get("lint"):
        lint_r = result["lint"]
        if lint_r.get("status") == "ok":
            console.print(
                f"  Lint: {lint_r.get('total_notes', 0)} notes, {lint_r.get('issues', 0)} issues"
            )

    if result.get("rebuild_indexes"):
        rebuild_r = result["rebuild_indexes"]
        if rebuild_r.get("status") == "ok":
            console.print(f"  Indexes: {rebuild_r.get('indexes_updated', 0)} rebuilt")

    console.print("[green]Maintenance complete[/green]")


@automation_app.command("run-pending")
def automation_run_pending(
    mode: str = typer.Option(None, "--mode", "-m", help="Processing mode: safe|balanced|deep"),
    limit: int = typer.Option(None, "--limit", "-n", help="Max items per step"),
    connector: str = typer.Option("raindrop", "--connector", "-c", help="Inbox connector ID"),
    retry_failed: bool = typer.Option(False, "--retry-failed", help="Include retryable failures"),
    no_maintenance: bool = typer.Option(False, "--no-maintenance", help="Skip maintenance tasks"),
):
    """One-shot end-to-end: discover + process + maintain, then exit.

    This is the primary command for OS scheduler integration.
    """
    from app.automation.runner import run_automation

    effective_mode = mode
    if effective_mode is None:
        from app.config import get_settings

        effective_mode = get_settings().automation_default_mode

    console.print(f"[blue]Running automation ({effective_mode} mode)...[/blue]")
    result = _run(
        run_automation(
            mode=effective_mode,
            limit=limit,
            connector_id=connector,
            run_maintenance_tasks=not no_maintenance,
            retry_failed=retry_failed,
        )
    )

    discover = result.get("discover", {})
    process = result.get("process", {})

    console.print(
        f"  Discovered: {discover.get('items_discovered', 0)} new, "
        f"{discover.get('items_skipped_duplicate', 0)} skipped"
    )
    console.print(
        f"  Processed: {process.get('succeeded', 0)} succeeded, {process.get('failed', 0)} failed"
    )

    if result.get("error"):
        console.print(f"[red]Error:[/red] {result['error']}")
        raise typer.Exit(1)

    console.print("[green]Automation run complete[/green]")


@automation_app.command("status")
def automation_status():
    """Show automation system status: queue counts, last run, backends."""
    from app.automation.runner import get_automation_status

    result = _run(get_automation_status())

    table = Table(title="Automation Status")
    table.add_column("Item", style="bold")
    table.add_column("Value")

    table.add_row("Enabled", "yes" if result["automation_enabled"] else "no")
    table.add_row("Default mode", result["default_mode"])

    counts = result.get("queue_counts", {})
    for status_name, count in sorted(counts.items()):
        table.add_row(f"  queue: {status_name}", str(count))
    table.add_row("  queue: total", str(result.get("total_queued", 0)))
    table.add_row("Retryable failures", str(result.get("retryable_failures", 0)))

    for cid, info in result.get("connectors", {}).items():
        last_sync = info.get("last_sync_at", "never")
        table.add_row(f"Connector: {cid}", f"last sync: {last_sync}")

    last_run = result.get("last_run")
    if last_run:
        table.add_row("Last run type", last_run.get("run_type", ""))
        table.add_row("Last run mode", last_run.get("mode", ""))
        table.add_row("Last run at", str(last_run.get("started_at", "")))
        table.add_row("Last run summary", last_run.get("summary", ""))

    for backend, available in result.get("backends_available", {}).items():
        color = "green" if available else "red"
        table.add_row(
            f"Backend: {backend}",
            f"[{color}]{'available' if available else 'unavailable'}[/{color}]",
        )

    console.print(table)


@automation_app.command("retry-failed")
def automation_retry_failed(
    mode: str = typer.Option("safe", "--mode", "-m", help="Processing mode"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max items to retry"),
):
    """Retry items with retryable failures."""
    from app.automation.runner import run_process_pending

    console.print(f"[blue]Retrying failed items in {mode} mode...[/blue]")
    result = _run(
        run_process_pending(
            mode=mode,
            limit=limit,
            retry_failed=True,
        )
    )

    console.print(
        f"[green]Retry complete:[/green] "
        f"{result.get('succeeded', 0)} succeeded, "
        f"{result.get('failed', 0)} failed"
    )


@automation_app.command("list-pending")
def automation_list_pending(
    limit: int = typer.Option(20, "--limit", "-n", help="Max items to show"),
    status_filter: str = typer.Option(None, "--status", "-s", help="Filter by status"),
):
    """List queued items pending processing."""
    from app.automation.queue_store import QueueRepository
    from app.config import get_settings
    from app.storage.sqlite import Database

    settings = get_settings()
    db = Database(settings.db_path)
    db.connect()

    try:
        queue_repo = QueueRepository(db)
        if status_filter:
            items = queue_repo.list_items(limit=limit, statuses=[status_filter])
        else:
            items = queue_repo.get_pending(limit=limit, include_retryable=True)

        if not items:
            console.print("[dim]No pending items in queue.[/dim]")
            return

        table = Table(title=f"Pending Queue Items ({len(items)})")
        table.add_column("ID", style="dim")
        table.add_column("Status")
        table.add_column("Title")
        table.add_column("URL")
        table.add_column("Attempts")
        table.add_column("Last Error")

        for item in items[:limit]:
            status_color = {
                "discovered": "blue",
                "retryable_failed": "yellow",
                "processing": "cyan",
            }.get(item.status, "white")
            table.add_row(
                str(item.id),
                f"[{status_color}]{item.status}[/{status_color}]",
                (item.title or "untitled")[:40],
                item.url[:50],
                str(item.attempt_count),
                (item.last_error or "")[:40],
            )

        console.print(table)
    finally:
        db.close()


@automation_app.command("generate-scheduler")
def automation_generate_scheduler(
    platform: str = typer.Option(
        ..., "--platform", "-p", help="Target platform: macos|linux|windows|all"
    ),
    mode: str = typer.Option("safe", "--mode", "-m", help="Automation mode"),
    interval: int = typer.Option(30, "--interval", "-i", help="Interval in minutes"),
    output_dir: str = typer.Option(".", "--output", "-o", help="Output directory"),
):
    """Generate OS-specific scheduler configuration files."""
    from app.automation.scheduler_helpers import (
        generate_launchd_plist,
        generate_scheduler_instructions,
        generate_systemd_timer,
        generate_windows_task_xml,
    )
    from app.config import epistora_logs_dir

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    epistora_logs_dir().mkdir(parents=True, exist_ok=True)

    platforms = [platform] if platform != "all" else ["macos", "linux", "windows"]

    for plat in platforms:
        if plat == "macos":
            content = generate_launchd_plist(mode=mode, interval_minutes=interval)
            path = out / "com.epistora.automation.plist"
            path.write_text(content)
            console.print(f"[green]Generated:[/green] {path}")

        elif plat == "linux":
            service, timer = generate_systemd_timer(mode=mode, interval_minutes=interval)
            svc_path = out / "epistora-automation.service"
            tmr_path = out / "epistora-automation.timer"
            svc_path.write_text(service)
            tmr_path.write_text(timer)
            console.print(f"[green]Generated:[/green] {svc_path}")
            console.print(f"[green]Generated:[/green] {tmr_path}")

        elif plat == "windows":
            content = generate_windows_task_xml(mode=mode, interval_minutes=interval)
            path = out / "epistora-automation.xml"
            path.write_text(content)
            console.print(f"[green]Generated:[/green] {path}")

    instructions = generate_scheduler_instructions(mode=mode, interval_minutes=interval)
    inst_path = out / "SCHEDULING.md"
    inst_path.write_text(instructions)
    console.print(f"[green]Generated:[/green] {inst_path}")


if __name__ == "__main__":
    app()
