"""Epistora CLI — primary operator interface."""

from __future__ import annotations

import asyncio
import shutil
from datetime import date
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="epistora",
    help="Epistora — local-first personal knowledge compiler.\n\n"
    "Turn saved bookmarks into a persistent, agent-queryable knowledge base.\n\n"
    "Short alias: eps",
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


def _short_label(value: str, max_len: int = 72) -> str:
    if len(value) <= max_len:
        return value
    return value[: max_len - 3].rstrip() + "..."


def _progress_prefix(payload: dict[str, Any]) -> str:
    index = payload.get("index")
    total = payload.get("total")
    if isinstance(index, int) and isinstance(total, int) and total > 0:
        return f"[{index}/{total}] "
    return ""


def _progress_label(payload: dict[str, Any]) -> str:
    return _short_label(str(payload.get("title") or payload.get("url") or "item"))


def _print_cli_guide() -> None:
    essentials = Table(title="Most Used Commands")
    essentials.add_column("Command", style="bold cyan")
    essentials.add_column("What it does")
    essentials.add_row("epistora setup", "First-time guided setup")
    essentials.add_row("epistora doctor", "Verify config, backend, and vault health")
    essentials.add_row("epistora ingest latest --limit 1", "Try a small ingest run")
    essentials.add_row("epistora ingest url <url>", "Ingest one specific source")
    essentials.add_row("epistora vault use <path>", "Switch to a different vault directory")
    essentials.add_row("epistora status", "Show current vault path and system status")
    console.print(essentials)

    advanced = Table(title="Advanced Commands")
    advanced.add_column("Command", style="bold cyan")
    advanced.add_column("What it does")
    advanced.add_row("epistora connect raindrop", "Update Raindrop token and collection")
    advanced.add_row("epistora backend setup", "Change backend configuration")
    advanced.add_row("epistora automation --help", "See automation commands")
    advanced.add_row(
        "epistora automation run-personal-learning",
        "Run the composed personal-learning preset",
    )
    advanced.add_row("epistora rebuild-indexes", "Rebuild wiki index files")
    advanced.add_row("epistora reset-generated", "Clear generated state while keeping the vault")
    console.print(advanced)

    console.print("[bold]Tips[/bold]")
    console.print("  - Run [cyan]epistora --help[/cyan] for the full command tree.")
    console.print("  - Run [cyan]epistora <command> --help[/cyan] for options on one command.")
    console.print("  - Use [cyan]eps[/cyan] as the short alias for [cyan]epistora[/cyan].")


def _error_help_lines(message: str) -> list[str]:
    text = message.lower()
    hints: list[str] = []

    if "connector" in text and "not configured" in text:
        hints.append("Run `epistora connect raindrop` to configure your connector.")
    if "raindrop authentication failed" in text:
        hints.append("Run `epistora connect raindrop` and save a valid token.")
    if "raindrop collection not found" in text:
        hints.append(
            "Check the Raindrop collection ID in your config "
            "or rerun `epistora connect raindrop`."
        )
    if "could not reach the raindrop api" in text:
        hints.append("Check your network connection and try again.")
    if "api key not configured" in text or "no backends failed" in text:
        hints.append(
            "Run `epistora backend setup` or `epistora backend status` "
            "to configure an ingest backend."
        )
    if "backend unavailable" in text or "all backends failed" in text:
        hints.append(
            "Run `epistora backend status` to see which backend "
            "is missing or disabled."
        )
    if "opencode" in text and ("not found" in text or "disabled" in text):
        hints.append("Install OpenCode or disable it in backend config.")
    if "claude code" in text and ("not found" in text or "disabled" in text):
        hints.append("Install Claude Code or disable it in backend config.")
    if "codex" in text and ("not found" in text or "disabled" in text):
        hints.append("Install Codex or disable it in backend config.")
    if "timed out" in text or "timeout" in text:
        hints.append(
            "Retry the command. If it keeps happening, "
            "reduce the batch size or switch backend."
        )
    if "network" in text or "connection" in text:
        hints.append("Check your network connection and retry.")

    seen: set[str] = set()
    unique: list[str] = []
    for hint in hints:
        if hint not in seen:
            seen.add(hint)
            unique.append(hint)
    return unique


def _print_actionable_error(prefix: str, message: str) -> None:
    console.print(f"[red]{prefix}:[/red] {message}")
    for hint in _error_help_lines(message):
        console.print(f"[dim]  hint: {hint}[/dim]")


def _print_recent_item_issues(results: list[Any], *, field: str) -> None:
    issues = [r for r in results if getattr(r, field, None)]
    if not issues:
        return

    label = "Recent warnings" if field == "warnings" else "Recent failures"
    console.print(f"[yellow]{label}:[/yellow]")
    for result in issues[:3]:
        messages = getattr(result, field)
        if not messages:
            continue
        title = _short_label(
            getattr(result, "source_title", "") or getattr(result, "source_url", "item")
        )
        console.print(f"  - {title}: {messages[0]}")
        if field != "warnings":
            for hint in _error_help_lines(messages[0])[:1]:
                console.print(f"    [dim]{hint}[/dim]")


def _automation_progress_callback(status, *, mode: str | None = None):
    def _progress(stage: str, payload: dict[str, Any]) -> None:
        prefix = _progress_prefix(payload)
        label = _progress_label(payload)

        if stage == "automation_stage":
            status.update(f"{str(payload.get('stage_name', 'working')).capitalize()}...")
        elif stage == "discover_fetching":
            status.update("Fetching latest bookmarks...")
        elif stage == "discover_fetched":
            count = int(payload.get("count") or 0)
            noun = "item" if count == 1 else "items"
            status.update(f"Fetched {count} {noun} from the connector...")
        elif stage == "discover_queued":
            status.update(f"Queueing {label}...")
            console.print(f"  [green]queued[/green] {label}")
        elif stage == "discover_skipped":
            status.update(f"Skipping {label}...")
            console.print(f"  [yellow]skip[/yellow] {label}")
        elif stage == "process_loaded":
            count = int(payload.get("count") or 0)
            status.update(f"Loaded {count} queued items for processing...")
        elif stage == "process_item_start":
            current_mode = payload.get("mode") or mode or "safe"
            status.update(f"{prefix}Processing {label} ({current_mode})...")
        elif stage == "process_item_done":
            status.update(f"{prefix}Finished {label}")
            console.print(f"  [green]done[/green] {prefix}{label}")
        elif stage == "process_item_failed":
            status.update(f"{prefix}Failed {label}")
            console.print(f"  [red]fail[/red] {prefix}{label}")
        elif stage == "process_budget_reached":
            limit = payload.get("limit")
            status.update("Reached the enrichment budget for this run.")
            if limit:
                console.print(
                    f"  [yellow]stop[/yellow] Reached enrichment limit "
                    f"for this run ({limit})."
                )
        elif stage == "automation_done":
            current_mode = payload.get("mode") or mode or "safe"
            status.update(f"Automation complete ({current_mode})")
        elif stage == "automation_failed":
            status.update("Automation failed")

    return _progress


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


@app.command("help")
def help_cmd():
    """Show a concise guide to the most important CLI commands."""
    _print_cli_guide()


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

    console.print(f"[blue]Starting ingest:[/blue] {url}")

    try:
        with console.status("Preparing ingest...", spinner="dots") as status:
            def _progress(stage: str, payload: dict[str, Any]) -> None:
                label = _progress_label(payload)
                if stage == "fetching":
                    status.update(f"Fetching {label}...")
                elif stage == "analysing":
                    status.update(f"Analyzing {label}...")
                elif stage == "writing":
                    status.update(f"Writing notes for {label}...")
                elif stage == "done":
                    status.update(f"Finished {label}")
                elif stage == "skipped":
                    status.update(f"Already ingested: {label}")

            result = _run(_ingest(url, force=force, progress_callback=_progress))
    except Exception as e:
        _print_actionable_error("Ingest failed", str(e))
        raise typer.Exit(1)

    if result.deduplicated:
        console.print(f"[yellow]Already ingested.[/yellow] Source note: {result.source_note_path}")
        return

    if result.errors:
        _print_actionable_error("Completed with errors", "; ".join(result.errors))
    else:
        console.print("[green]✓ Ingest complete[/green]")
    if result.warnings:
        console.print(f"[yellow]Note:[/yellow] {result.warnings[0]}")

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

    try:
        console.print(f"[blue]Starting ingest:[/blue] latest {limit} items from {connector}")
        with console.status("Fetching saved items...", spinner="dots") as status:

            def _progress(stage: str, payload: dict[str, Any]) -> None:
                prefix = _progress_prefix(payload)
                label = _progress_label(payload)
                if stage == "sync_fetching":
                    status.update(f"Fetching latest items from {connector}...")
                elif stage == "sync_fetched":
                    count = int(payload.get("count") or 0)
                    noun = "item" if count == 1 else "items"
                    if count == 0:
                        status.update("No new items found.")
                    else:
                        status.update(f"Found {count} {noun}; starting ingest...")
                elif stage == "fetching":
                    status.update(f"{prefix}Fetching {label}...")
                elif stage == "analysing":
                    status.update(f"{prefix}Analyzing {label}...")
                elif stage == "writing":
                    status.update(f"{prefix}Writing notes for {label}...")
                elif stage == "done":
                    status.update(f"{prefix}Finished {label}")
                    console.print(f"  [green]done[/green] {prefix}{label}")
                elif stage == "skipped":
                    status.update(f"{prefix}Already ingested: {label}")
                    console.print(f"  [yellow]skip[/yellow] {prefix}{label}")
                elif stage == "failed":
                    status.update(f"{prefix}Failed {label}")
                    console.print(f"  [red]fail[/red] {prefix}{label}")

            results = _run(
                _sync(
                    connector_id=connector,
                    limit=limit,
                    force=force,
                    progress_callback=_progress,
                )
            )
    except ValueError as e:
        _print_actionable_error("Configuration error", str(e))
        raise typer.Exit(1)
    except Exception as e:
        _print_actionable_error("Ingest failed", str(e))
        raise typer.Exit(1)

    ingested = sum(1 for r in results if not r.deduplicated and not r.errors)
    skipped = sum(1 for r in results if r.deduplicated)
    failed = sum(1 for r in results if r.errors)

    if not results:
        console.print("[yellow]No new items found to ingest.[/yellow]")
        return

    console.print(
        f"[green]✓ Ingest complete:[/green] {ingested} ingested, {skipped} skipped, {failed} failed"
    )
    _print_recent_item_issues(results, field="warnings")
    _print_recent_item_issues(results, field="errors")


def _sync_inbox_impl(
    *,
    connector: str,
    limit: int,
    force: bool,
    label: str,
) -> None:
    from app.services.ingest_service import sync_inbox as _sync

    try:
        console.print(f"[blue]Starting {label}:[/blue] latest {limit} items from {connector}")
        with console.status("Fetching saved items...", spinner="dots") as status:

            def _progress(stage: str, payload: dict[str, Any]) -> None:
                prefix = _progress_prefix(payload)
                item_label = _progress_label(payload)
                if stage == "sync_fetching":
                    status.update(f"Fetching latest items from {connector}...")
                elif stage == "sync_fetched":
                    count = int(payload.get("count") or 0)
                    if count == 0:
                        status.update("No new items found.")
                    else:
                        noun = "item" if count == 1 else "items"
                        status.update(f"Found {count} {noun}; starting sync...")
                elif stage == "fetching":
                    status.update(f"{prefix}Fetching {item_label}...")
                elif stage == "analysing":
                    status.update(f"{prefix}Analyzing {item_label}...")
                elif stage == "writing":
                    status.update(f"{prefix}Writing notes for {item_label}...")
                elif stage == "done":
                    status.update(f"{prefix}Finished {item_label}")
                    console.print(f"  [green]done[/green] {prefix}{item_label}")
                elif stage == "skipped":
                    status.update(f"{prefix}Already ingested: {item_label}")
                    console.print(f"  [yellow]skip[/yellow] {prefix}{item_label}")
                elif stage == "failed":
                    status.update(f"{prefix}Failed {item_label}")
                    console.print(f"  [red]fail[/red] {prefix}{item_label}")

            results = _run(
                _sync(
                    connector_id=connector,
                    limit=limit,
                    force=force,
                    progress_callback=_progress,
                )
            )
    except ValueError as e:
        _print_actionable_error(f"{label.capitalize()} failed", str(e))
        raise typer.Exit(1)
    except Exception as e:
        _print_actionable_error(f"{label.capitalize()} failed", str(e))
        raise typer.Exit(1)

    if not results:
        console.print("[yellow]No new items found to sync.[/yellow]")
        return

    ingested = sum(1 for r in results if not r.deduplicated and not r.errors)
    skipped = sum(1 for r in results if r.deduplicated)
    failed = sum(1 for r in results if r.errors)
    console.print(
        f"[green]✓ {label.capitalize()} complete:[/green] "
        f"{ingested} ingested, {skipped} skipped, {failed} failed"
    )
    _print_recent_item_issues(results, field="warnings")
    _print_recent_item_issues(results, field="errors")


def _parse_csv_option(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_reference_date(value: str | None) -> date | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    try:
        return date.fromisoformat(normalized)
    except ValueError as exc:
        raise typer.BadParameter("Use YYYY-MM-DD for --date.") from exc


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
    _sync_inbox_impl(connector="raindrop", limit=limit, force=force, label="sync")


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
    _sync_inbox_impl(connector=connector, limit=limit, force=force, label="sync")


# ---------------------------------------------------------------------------
# Vault maintenance
# ---------------------------------------------------------------------------


@app.command()
def query(
    question: str = typer.Argument(..., help="Question to ask the vault"),
    save: bool = typer.Option(False, "--save", "-s", help="Save answer to outputs/"),
):
    """Query the vault through the v2 read-model retrieval path."""

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


@app.command("topic-bundle")
def topic_bundle(
    topic: str = typer.Argument(..., help="Topic or query to assemble into a learning packet"),
    days: int = typer.Option(None, "--days", help="Only include sources saved in the last N days"),
    source_types: str = typer.Option(
        "",
        "--source-types",
        help="Comma-separated source types, e.g. article,youtube,x_thread",
    ),
):
    """Generate a grounded topic learning packet from saved source notes."""

    from app.services.topic_bundle_service import generate_topic_bundle

    console.print(f"[blue]Generating topic bundle:[/blue] {topic}\n")

    try:
        result = _run(
            generate_topic_bundle(
                topic,
                days=days,
                source_types=_parse_csv_option(source_types),
            )
        )
    except Exception as e:
        console.print(f"[red]Topic bundle failed:[/red] {e}")
        raise typer.Exit(1)

    console.print(result.report)
    console.print()
    console.print(
        f"[bold]Bundle status:[/bold] {result.bundle_status} "
        f"({result.source_count} sources, {result.ready_source_count} ready)"
    )
    if result.saved_to:
        console.print(f"[green]Saved to:[/green] {result.saved_to}")


review_app = typer.Typer(
    name="review",
    help="Generate daily and weekly review digests.",
    add_completion=False,
)
app.add_typer(review_app, name="review")


def _print_review_result(result, *, label: str) -> None:
    if result.digest_status == "skipped":
        console.print(f"[yellow]Skipped {label} review:[/yellow] {result.reason}")
        return

    console.print(result.report)
    console.print()
    console.print(
        f"[bold]Review status:[/bold] {result.digest_status} "
        f"({result.source_count} sources, confidence: {result.confidence})"
    )
    if result.saved_to:
        console.print(f"[green]Saved to:[/green] {result.saved_to}")


@review_app.command("daily")
def review_daily(
    review_date: str = typer.Option(
        "",
        "--date",
        help="Optional review date in YYYY-MM-DD. Defaults to today (local UTC clock).",
    ),
):
    """Generate the daily review digest."""

    from app.services.review_service import generate_daily_digest

    reference_date = _parse_reference_date(review_date)
    console.print("[blue]Generating daily review...[/blue]\n")

    try:
        result = _run(generate_daily_digest(reference_date=reference_date))
    except Exception as e:
        console.print(f"[red]Daily review failed:[/red] {e}")
        raise typer.Exit(1)

    _print_review_result(result, label="daily")


@review_app.command("weekly")
def review_weekly(
    review_date: str = typer.Option(
        "",
        "--date",
        help="Optional reference date in YYYY-MM-DD for choosing the ISO week.",
    ),
):
    """Generate the weekly review digest."""

    from app.services.review_service import generate_weekly_digest

    reference_date = _parse_reference_date(review_date)
    console.print("[blue]Generating weekly review...[/blue]\n")

    try:
        result = _run(generate_weekly_digest(reference_date=reference_date))
    except Exception as e:
        console.print(f"[red]Weekly review failed:[/red] {e}")
        raise typer.Exit(1)

    _print_review_result(result, label="weekly")


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


views_app = typer.Typer(
    name="views",
    help="Generate deterministic reader-style browse pages.",
    add_completion=False,
)
app.add_typer(views_app, name="views")


@views_app.command("rebuild")
def views_rebuild():
    """Rebuild reader-style view pages from existing metadata."""
    from app.config import get_settings
    from app.vault.index_updater import rebuild_indexes as _rebuild

    settings = get_settings()
    vault_path = Path(settings.vault_path)

    if not vault_path.exists():
        console.print("[red]Vault not found. Run 'epistora init' first.[/red]")
        raise typer.Exit(1)

    updated = _rebuild(vault_path)
    view_names = {"READING_HOME.md", "VIDEOS.md", "ARTICLES.md", "TOPICS_FEED.md"}
    view_paths = [path for path in updated if Path(path).name in view_names]
    console.print(f"[green]✓ Rebuilt {len(view_paths)} reader views[/green]")
    for path in view_paths:
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
# Vault commands
# ---------------------------------------------------------------------------

vault_app = typer.Typer(
    name="vault",
    help="Show or change the active vault directory.",
    add_completion=False,
)
app.add_typer(vault_app, name="vault")


@vault_app.command("show")
def vault_show():
    """Show the vault path currently configured in Epistora."""
    from app.config import existing_env_file, get_settings

    settings = get_settings()
    env_path = existing_env_file()
    console.print(f"[bold]Current vault:[/bold] {settings.vault_path}")
    if env_path:
        console.print(f"[dim]Config file: {env_path}[/dim]")


@vault_app.command("use")
def vault_use(
    path: str = typer.Argument(..., help="Directory to use as the active vault"),
    copy_current: bool = typer.Option(
        False,
        "--copy-current",
        help="Copy the current vault contents into the new directory before switching",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompts when initializing or copying",
    ),
):
    """Switch Epistora to a different vault directory without rerunning setup."""
    from app.cli.setup_wizard import _initialize_vault, _vault_env_config, _write_env_file
    from app.config import get_settings, preferred_env_file, reset_settings
    from app.storage.sqlite import Database

    settings = get_settings()
    current_vault = Path(settings.vault_path).expanduser().resolve()
    target = Path(path).expanduser().resolve()

    if target == current_vault:
        console.print(f"[yellow]Already using vault:[/yellow] {target}")
        return

    if copy_current and current_vault.exists():
        if target.exists() and any(target.iterdir()) and not yes:
            confirmed = typer.confirm(
                f"{target} already has files. "
                "Copy the current vault into it and keep existing files?"
            )
            if not confirmed:
                raise typer.Abort()
        console.print(f"[blue]Copying current vault to:[/blue] {target}")
        shutil.copytree(current_vault, target, dirs_exist_ok=True)

    if target.exists() and any(target.iterdir()) and not _looks_like_epistora_vault(target):
        if not yes:
            confirmed = typer.confirm(
                f"{target} is not an Epistora vault yet. "
                "Initialize Epistora files there and keep existing files?"
            )
            if not confirmed:
                raise typer.Abort()

    console.print(f"[blue]Switching active vault to:[/blue] {target}")
    _initialize_vault(target)

    env_path = preferred_env_file()
    _write_env_file(env_path, _vault_env_config(target))

    reset_settings()
    db_path = target / ".system" / "epistora.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path)
    db.connect()
    db.close()

    console.print(f"[green]✓ Vault path updated[/green] {target}")
    console.print(f"[green]✓ Database ready[/green] {db_path}")
    console.print(f"[dim]Config updated: {env_path}[/dim]")


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
    console.print(
        "  [cyan]epistora automation run-personal-learning[/cyan] — full personal learning run"
    )


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
        _print_actionable_error("Sync failed", str(result.get("error", "unknown")))
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
        _print_actionable_error("Lint failed", str(result.get("error", "unknown")))
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

    console.print(f"[blue]Starting discovery:[/blue] {connector}")
    try:
        with console.status("Fetching latest bookmarks...", spinner="dots") as status:
            result = _run(
                run_discover(
                    connector_id=connector,
                    limit=limit,
                    progress_callback=_automation_progress_callback(status),
                )
            )
    except Exception as e:
        _print_actionable_error("Discovery failed", str(e))
        raise typer.Exit(1)

    if result.get("error"):
        _print_actionable_error("Discovery failed", result["error"])
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

    console.print(f"[blue]Starting processing:[/blue] {mode} mode")
    try:
        with console.status("Loading queue...", spinner="dots") as status:
            result = _run(
                run_process_pending(
                    mode=mode,
                    limit=limit,
                    retry_failed=retry_failed,
                    connector_id=connector,
                    progress_callback=_automation_progress_callback(status, mode=mode),
                )
            )
    except Exception as e:
        _print_actionable_error("Processing failed", str(e))
        raise typer.Exit(1)

    if result.get("status") == "ok":
        console.print(
            f"[green]Processing complete:[/green] "
            f"{result.get('succeeded', 0)} succeeded, "
            f"{result.get('failed', 0)} failed"
        )
        failed_results = [r for r in result.get("results", []) if not r.get("success")]
        if failed_results:
            console.print("[yellow]Recent failures:[/yellow]")
            for failed_item in failed_results[:3]:
                console.print(f"  - {failed_item.get('error', 'unknown error')}")
                for hint in _error_help_lines(failed_item.get("error", ""))[:1]:
                    console.print(f"    [dim]{hint}[/dim]")
    else:
        _print_actionable_error("Processing failed", str(result.get("error") or result))
        raise typer.Exit(1)


@automation_app.command("maintain")
def automation_maintain(
    lint: bool = typer.Option(None, "--lint/--no-lint", help="Run vault lint"),
    rebuild: bool = typer.Option(
        None,
        "--rebuild/--no-rebuild",
        help="Force a full read-model refresh and structural index rebuild",
    ),
):
    """Run bounded vault maintenance and optional lint."""
    from app.automation.runner import run_maintenance

    console.print("[blue]Running maintenance tasks...[/blue]")
    try:
        with console.status("Running maintenance...", spinner="dots"):
            result = _run(run_maintenance(run_lint=lint, run_rebuild=rebuild))
    except Exception as e:
        _print_actionable_error("Maintenance failed", str(e))
        raise typer.Exit(1)

    if result.get("lint"):
        lint_r = result["lint"]
        if lint_r.get("status") == "ok":
            console.print(
                f"  Lint: {lint_r.get('total_notes', 0)} notes, {lint_r.get('issues', 0)} issues"
            )
        else:
            _print_actionable_error("Lint failed", str(lint_r.get("error", "unknown error")))

    if result.get("rebuild_indexes"):
        rebuild_r = result["rebuild_indexes"]
        if rebuild_r.get("status") == "ok":
            console.print(f"  Indexes: {rebuild_r.get('indexes_updated', 0)} rebuilt")
        else:
            _print_actionable_error(
                "Index rebuild failed", str(rebuild_r.get("error", "unknown error"))
            )

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

    console.print(f"[blue]Starting automation:[/blue] {effective_mode} mode")
    try:
        with console.status("Preparing automation run...", spinner="dots") as status:
            result = _run(
                run_automation(
                    mode=effective_mode,
                    limit=limit,
                    connector_id=connector,
                    run_maintenance_tasks=not no_maintenance,
                    retry_failed=retry_failed,
                    progress_callback=_automation_progress_callback(status, mode=effective_mode),
                )
            )
    except Exception as e:
        _print_actionable_error("Automation failed", str(e))
        raise typer.Exit(1)

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
        _print_actionable_error("Automation failed", result["error"])
        raise typer.Exit(1)

    failed_results = [r for r in process.get("results", []) if not r.get("success")]
    if failed_results:
        console.print("[yellow]Recent failures:[/yellow]")
        for failed_item in failed_results[:3]:
            console.print(f"  - {failed_item.get('error', 'unknown error')}")
            for hint in _error_help_lines(failed_item.get("error", ""))[:1]:
                console.print(f"    [dim]{hint}[/dim]")

    console.print("[green]Automation run complete[/green]")


@automation_app.command("run-personal-learning")
def automation_run_personal_learning(
    mode: str = typer.Option(
        "balanced",
        "--mode",
        "-m",
        help="Preset mode: safe|balanced|deep",
    ),
    limit: int = typer.Option(None, "--limit", "-n", help="Max items per step"),
    connector: str = typer.Option("raindrop", "--connector", "-c", help="Inbox connector ID"),
    retry_failed: bool = typer.Option(False, "--retry-failed", help="Include retryable failures"),
    no_maintenance: bool = typer.Option(False, "--no-maintenance", help="Skip maintenance tasks"),
):
    """Run the composed personal-learning preset workflow."""
    from app.automation.runner import run_personal_learning

    console.print(f"[blue]Starting personal learning preset:[/blue] {mode} mode")
    try:
        with console.status("Preparing personal learning run...", spinner="dots") as status:
            result = _run(
                run_personal_learning(
                    mode=mode,
                    limit=limit,
                    connector_id=connector,
                    run_maintenance_tasks=not no_maintenance,
                    retry_failed=retry_failed,
                    progress_callback=_automation_progress_callback(status, mode=mode),
                )
            )
    except Exception as e:
        _print_actionable_error("Personal learning run failed", str(e))
        raise typer.Exit(1)

    if result.get("error"):
        _print_actionable_error("Personal learning run failed", result["error"])
        raise typer.Exit(1)

    discover = result.get("discover", {})
    process = result.get("process", {})
    read_model = result.get("read_model", {})
    views = result.get("views", {})
    reviews = result.get("reviews", {})
    daily = reviews.get("daily", {})
    weekly = reviews.get("weekly", {})

    console.print(
        f"  Discovered: {discover.get('items_discovered', 0)} new, "
        f"{discover.get('items_skipped_duplicate', 0)} skipped"
    )
    console.print(
        f"  Processed: {process.get('succeeded', 0)} succeeded, {process.get('failed', 0)} failed"
    )
    console.print(
        f"  Read model: {read_model.get('status', 'unknown')}"
    )
    console.print(
        f"  Views rebuilt: {views.get('count', 0)}"
    )
    console.print(
        f"  Daily review: {daily.get('digest_status', 'unknown')}"
        + (f" ({daily.get('saved_to')})" if daily.get('saved_to') else "")
    )
    console.print(
        f"  Weekly review: {weekly.get('digest_status', 'unknown')}"
        + (f" ({weekly.get('saved_to')})" if weekly.get('saved_to') else "")
    )
    if not no_maintenance:
        console.print(
            f"  Maintenance: {result.get('maintenance', {}).get('status', 'ok')}"
        )

    failed_results = [r for r in process.get("results", []) if not r.get("success")]
    if failed_results:
        console.print("[yellow]Recent failures:[/yellow]")
        for failed_item in failed_results[:3]:
            console.print(f"  - {failed_item.get('error', 'unknown error')}")
            for hint in _error_help_lines(failed_item.get("error", ""))[:1]:
                console.print(f"    [dim]{hint}[/dim]")

    console.print("[green]Personal learning run complete[/green]")


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

    console.print(f"[blue]Retrying failed items:[/blue] {mode} mode")
    try:
        with console.status("Loading retry queue...", spinner="dots") as status:
            result = _run(
                run_process_pending(
                    mode=mode,
                    limit=limit,
                    retry_failed=True,
                    progress_callback=_automation_progress_callback(status, mode=mode),
                )
            )
    except Exception as e:
        _print_actionable_error("Retry failed", str(e))
        raise typer.Exit(1)

    console.print(
        f"[green]Retry complete:[/green] "
        f"{result.get('succeeded', 0)} succeeded, "
        f"{result.get('failed', 0)} failed"
    )
    failed_results = [r for r in result.get("results", []) if not r.get("success")]
    if failed_results:
        console.print("[yellow]Recent failures:[/yellow]")
        for failed_item in failed_results[:3]:
            console.print(f"  - {failed_item.get('error', 'unknown error')}")
            for hint in _error_help_lines(failed_item.get("error", ""))[:1]:
                console.print(f"    [dim]{hint}[/dim]")


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
