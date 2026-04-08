"""Epistora CLI — primary operator interface."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="kb",
    help="Epistora – local-first personal knowledge compiler",
    add_completion=False,
)
console = Console()


def _run(coro):
    """Run an async coroutine from the sync CLI."""
    return asyncio.run(coro)


def _looks_like_epistora_vault(path: Path) -> bool:
    return (
        (path / "wiki").exists()
        and (path / "inbox").exists()
        and (path / "wiki" / "indexes").exists()
        and (path / "wiki" / "logs").exists()
    )


@app.command()
def init(
    vault_path: str = typer.Option(
        "./knowledge_vault",
        "--vault",
        "-v",
        help="Path where the knowledge vault will be created",
    ),
):
    """Initialize a new knowledge vault and app configuration."""
    from app.config import get_settings
    from app.vault.paths import ensure_vault_dirs

    target = Path(vault_path).resolve()

    if target.exists() and any(target.iterdir()):
        console.print(f"[yellow]Vault directory already exists at {target}[/yellow]")
        if _looks_like_epistora_vault(target):
            console.print(
                "[blue]Existing Epistora vault detected; "
                "ensuring required files exist.[/blue]"
            )
        elif not typer.confirm("Reinitialize? (existing files will be kept)"):
            raise typer.Abort()

    ensure_vault_dirs(target)

    template_dir = Path(__file__).parent.parent.parent / "knowledge_vault_template"
    if template_dir.exists():
        agents_md = template_dir / "AGENTS.md"
        if agents_md.exists():
            dest = target / "AGENTS.md"
            if not dest.exists():
                shutil.copy2(agents_md, dest)

    for idx_name in ["INDEX.md", "TOPICS.md", "ENTITIES.md", "CONCEPTS.md"]:
        idx_path = target / "wiki" / "indexes" / idx_name
        if not idx_path.exists():
            idx_path.write_text(
                f"# {idx_name.replace('.md', '')}\n\n"
                "_Empty — will be populated after first ingest._\n"
            )

    for log_name, log_title in [("ingest-log.md", "Ingest Log"), ("lint-log.md", "Lint Log")]:
        log_path = target / "wiki" / "logs" / log_name
        if not log_path.exists():
            log_path.write_text(f"# {log_title}\n\nAppend-only log.\n\n---\n\n")

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
    console.print("  1. Copy .env.example to .env and fill in your API keys")
    console.print("  2. Run: kb ingest-url <url>")


@app.command("ingest-url")
def ingest_url(
    url: str = typer.Argument(..., help="URL to ingest"),
):
    """Ingest a single URL into the knowledge vault."""
    from app.services.ingest_service import ingest_url as _ingest

    console.print(f"[blue]Ingesting:[/blue] {url}")

    try:
        result = _run(_ingest(url))
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


@app.command("sync-raindrop")
def sync_raindrop(
    limit: int = typer.Option(25, "--limit", "-n", help="Max items to sync"),
):
    """Sync recent items from Raindrop.io and ingest them."""
    from app.services.ingest_service import sync_raindrop as _sync

    console.print("[blue]Syncing from Raindrop...[/blue]")

    try:
        results = _run(_sync(limit=limit))
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


@app.command()
def query(
    question: str = typer.Argument(..., help="Question to ask the vault"),
    save: bool = typer.Option(False, "--save", "-s", help="Save answer to outputs/"),
):
    """Query the knowledge vault with a question."""
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

    console.print(table)


@app.command()
def worker():
    """Run the background automation worker (sync, lint, index rebuild)."""
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


@app.command("backend-status")
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
                desc.backend_type.value,
                desc.model or "-",
                f"[{color}]{'yes' if desc.available else 'no'}[/{color}]",
                desc.reason or "",
            )
    console.print(table)


@app.command("run-sync")
def run_sync_now(
    limit: int = typer.Option(25, "--limit", "-n", help="Max items to sync"),
):
    """Run a one-off Raindrop sync (like sync-raindrop, via automation jobs)."""
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


@app.command("run-lint")
def run_lint_now():
    """Run a one-off lint check via automation jobs."""
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


@app.command("rebuild-indexes")
def rebuild_indexes():
    """Rebuild all vault index files."""
    from app.config import get_settings
    from app.vault.index_updater import rebuild_indexes as _rebuild

    settings = get_settings()
    vault_path = Path(settings.vault_path)

    if not vault_path.exists():
        console.print("[red]Vault not found. Run 'kb init' first.[/red]")
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
    """Reset generated vault content and generated internal state."""
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


if __name__ == "__main__":
    app()
