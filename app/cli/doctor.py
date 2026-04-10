"""Epistora doctor — environment and configuration health check."""

from __future__ import annotations

import os
import platform
import shutil
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


class Check:
    """A single health check result."""

    def __init__(self, name: str, status: str, message: str, hint: str = ""):
        self.name = name
        self.status = status  # "ok", "warn", "fail"
        self.message = message
        self.hint = hint

    @property
    def icon(self) -> str:
        return {"ok": "[green]✓[/green]", "warn": "[yellow]⚠[/yellow]", "fail": "[red]✗[/red]"}[
            self.status
        ]


def _check_python() -> Check:
    """Check Python version."""
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"
    if version >= (3, 11):
        return Check("Python", "ok", f"Python {version_str}")
    elif version >= (3, 10):
        return Check(
            "Python",
            "warn",
            f"Python {version_str} (3.11+ recommended)",
            hint="Consider upgrading to Python 3.11 or later",
        )
    return Check(
        "Python",
        "fail",
        f"Python {version_str} (3.11+ required)",
        hint="Install Python 3.11 or later: https://www.python.org/downloads/",
    )


def _check_uv() -> Check:
    """Check if uv is available."""
    uv = shutil.which("uv")
    if uv:
        return Check("uv", "ok", f"Found at {uv}")
    return Check(
        "uv",
        "warn",
        "Not found on PATH",
        hint="Install uv: https://docs.astral.sh/uv/getting-started/installation/",
    )


def _check_installation() -> Check:
    """Report whether Epistora is running from an installed package or source checkout."""
    try:
        resolved_version = package_version("epistora")
        return Check(
            "Installation",
            "ok",
            f"Installed package detected (version {resolved_version})",
        )
    except PackageNotFoundError:
        repo_root = Path(__file__).resolve().parents[2]
        if (repo_root / "pyproject.toml").exists():
            return Check(
                "Installation",
                "warn",
                "Running from a source checkout",
                hint="Use `uv run epistora ...` from the repo, or install with `uv tool install .`",
            )
        return Check(
            "Installation",
            "warn",
            "Epistora package metadata not found",
            hint="Install with `uv tool install .` or `pip install -e .`",
        )


def _check_platform() -> Check:
    """Report the current platform."""
    system = platform.system()
    release = platform.release()
    machine = platform.machine()
    return Check("Platform", "ok", f"{system} {release} ({machine})")


def _check_env_file() -> Check:
    """Check if .env file exists."""
    from app.config import existing_env_file

    env_path = existing_env_file()
    if env_path is not None:
        return Check("Config (.env)", "ok", f"Found at {env_path}")

    if any(
        key in os.environ
        for key in ("VAULT_PATH", "DATABASE_URL", "RAINDROP_API_TOKEN", "API_API_KEY")
    ):
        return Check(
            "Config (.env)",
            "warn",
            "No .env file found, but Epistora settings are present in environment variables",
            hint="Run 'epistora setup' if you want Epistora to persist your config to disk",
        )

    return Check(
        "Config (.env)",
        "fail",
        "No .env file found",
        hint="Run 'epistora setup' to create one in the Epistora config directory",
    )


def _check_config_resolution() -> Check:
    """Report Epistora home and the preferred config write target."""
    try:
        from app.config import epistora_home, existing_env_file, preferred_env_file

        env_path = existing_env_file()
        preferred = preferred_env_file()
        home = epistora_home()
        active = str(env_path) if env_path is not None else "environment variables only"
        return Check(
            "Config Resolution",
            "ok",
            f"Active config: {active}; write target: {preferred}; home: {home}",
        )
    except Exception as exc:
        return Check("Config Resolution", "fail", f"Error: {exc}")


def _check_vault() -> Check:
    """Check if vault exists and is valid."""
    try:
        from app.config import get_settings

        settings = get_settings()
        vault_path = Path(settings.vault_path).resolve()

        if not vault_path.exists():
            return Check(
                "Vault",
                "fail",
                f"Not found at {vault_path}",
                hint="Run 'epistora init' or 'epistora setup' to create a vault",
            )

        required_dirs = ["wiki", "raw", "wiki/indexes", "wiki/logs"]
        missing = [d for d in required_dirs if not (vault_path / d).exists()]

        if missing:
            return Check(
                "Vault",
                "warn",
                f"Found at {vault_path} but missing: {', '.join(missing)}",
                hint="Run 'epistora init' to repair the vault structure",
            )

        agents_md = vault_path / "AGENTS.md"
        if not agents_md.exists():
            return Check(
                "Vault",
                "warn",
                f"Found at {vault_path} but AGENTS.md is missing",
                hint="Run 'epistora init' to copy AGENTS.md into the vault",
            )

        return Check("Vault", "ok", f"{vault_path}")
    except Exception as e:
        return Check(
            "Vault",
            "fail",
            f"Error checking vault: {e}",
            hint="Make sure .env is configured with VAULT_PATH",
        )


def _check_database() -> Check:
    """Check database connectivity."""
    try:
        from app.config import get_settings

        settings = get_settings()
        db_path = settings.db_path

        if not db_path.parent.exists():
            return Check(
                "Database",
                "warn",
                f"Parent directory does not exist: {db_path.parent}",
                hint="Run 'epistora init' to create the database",
            )

        if db_path.exists():
            from app.storage.sqlite import Database

            db = Database(db_path)
            db.connect()
            db.close()
            return Check("Database", "ok", f"{db_path}")

        return Check(
            "Database",
            "warn",
            f"Database not yet created at {db_path}",
            hint="Run 'epistora init' to initialize the database",
        )
    except Exception as e:
        return Check("Database", "fail", f"Error: {e}")


def _check_raindrop() -> Check:
    """Check Raindrop.io configuration."""
    try:
        from app.config import get_settings

        settings = get_settings()
        token = settings.raindrop_api_token

        if not token:
            return Check(
                "Raindrop",
                "warn",
                "No API token configured",
                hint="Run 'epistora connect raindrop' or set RAINDROP_API_TOKEN in .env",
            )

        if len(token) < 10:
            return Check(
                "Raindrop",
                "warn",
                "Token looks too short",
                hint="Check RAINDROP_API_TOKEN in .env",
            )

        return Check("Raindrop", "ok", "Token configured")
    except Exception as e:
        return Check("Raindrop", "fail", f"Error: {e}")


def _check_backends() -> list[Check]:
    """Check backend availability."""
    checks = []

    try:
        from app.config import get_settings

        settings = get_settings()

        # API backend
        if not settings.api_enabled:
            checks.append(
                Check(
                    "Backend: API",
                    "ok",
                    "Disabled",
                )
            )
        else:
            api_key = settings.effective_api_key()
            if api_key:
                model = settings.effective_api_model()
                checks.append(
                    Check(
                        "Backend: API",
                        "ok",
                        f"Key configured, model: {model}",
                    )
                )
            else:
                checks.append(
                    Check(
                        "Backend: API",
                        "warn",
                        "No API key configured",
                        hint="Set API_API_KEY (or OPENAI_API_KEY) in your Epistora config",
                    )
                )

        # CLI backends
        for name, binary_setting, enabled_setting in [
            ("OpenCode", settings.opencode_binary, settings.opencode_enabled),
            ("Claude Code", settings.claude_code_binary, settings.claude_code_enabled),
            ("Codex", settings.codex_binary, settings.codex_enabled),
        ]:
            if not enabled_setting:
                checks.append(Check(f"Backend: {name}", "ok", "Disabled"))
                continue

            binary = shutil.which(binary_setting)
            if binary:
                checks.append(Check(f"Backend: {name}", "ok", f"Found at {binary}"))
            else:
                checks.append(
                    Check(
                        f"Backend: {name}",
                        "warn",
                        f"'{binary_setting}' not found on PATH",
                        hint=f"Install {name} or disable it in your Epistora config",
                    )
                )

    except Exception as e:
        checks.append(Check("Backends", "fail", f"Error checking backends: {e}"))

    return checks


def _check_automation() -> Check:
    """Check automation readiness."""
    try:
        from app.config import get_settings

        settings = get_settings()

        if not settings.automation_enabled:
            return Check(
                "Automation",
                "ok",
                f"Disabled (default mode: {settings.automation_default_mode})",
            )

        return Check(
            "Automation",
            "ok",
            f"Enabled, mode: {settings.automation_default_mode}",
        )
    except Exception as e:
        return Check("Automation", "fail", f"Error: {e}")


def _check_plugins() -> Check:
    """Check plugin discovery and active prompt-pack selection."""
    try:
        from app.plugins.loader import (
            PLUGIN_DIRS_ENV_VAR,
            PROMPT_PACK_ENV_VAR,
            active_prompt_pack_root,
            discover_plugins,
            plugin_search_paths,
        )

        registry = discover_plugins()
        compatible = registry.compatible()
        discovered = registry.all()
        prompt_pack = os.environ.get(PROMPT_PACK_ENV_VAR, "").strip()
        search_paths = ", ".join(str(path) for path in plugin_search_paths())

        if registry.errors:
            return Check(
                "Plugins",
                "warn",
                (
                    f"{len(discovered)} discovered, {len(compatible)} compatible, "
                    f"{len(registry.errors)} manifest/load issue(s)"
                ),
                hint=(
                    f"Review plugin manifests and {PLUGIN_DIRS_ENV_VAR}. "
                    f"Search paths: {search_paths}"
                ),
            )

        if prompt_pack:
            try:
                prompt_root = active_prompt_pack_root()
            except Exception as exc:
                return Check(
                    "Plugins",
                    "warn",
                    f"Prompt pack '{prompt_pack}' is configured but not healthy: {exc}",
                    hint=f"Fix or unset {PROMPT_PACK_ENV_VAR}",
                )
            return Check(
                "Plugins",
                "ok",
                (
                    f"{len(compatible)} compatible plugin(s); active prompt pack: "
                    f"{prompt_pack} ({prompt_root})"
                ),
            )

        if compatible:
            return Check(
                "Plugins",
                "ok",
                f"{len(compatible)} compatible plugin(s) discovered",
            )
        return Check(
            "Plugins",
            "ok",
            "No local plugins discovered",
            hint=f"You can add local plugins under repo `plugins/`, {search_paths}",
        )
    except Exception as exc:
        return Check("Plugins", "fail", f"Error checking plugins: {exc}")


def _check_outputs() -> Check:
    """Check configured sink and storage-tier settings."""
    try:
        from app.config import get_settings
        from app.sinks.registry import available_sink_ids

        settings = get_settings()
        configured = settings.configured_artifact_sink_ids
        available = available_sink_ids(settings)
        unknown = sorted(set(configured) - set(available))
        blob_dir = settings.evidence_blob_dir
        threshold = settings.evidence_blob_threshold_bytes

        if unknown:
            return Check(
                "Outputs",
                "fail",
                f"Unknown sink(s): {', '.join(unknown)}",
                hint=f"Use one of: {', '.join(available)}",
            )

        return Check(
            "Outputs",
            "ok",
            (
                f"Sinks: {', '.join(configured)}; JSON export dir: {settings.json_export_dir}; "
                f"blob dir: {blob_dir}; blob threshold: {threshold} bytes"
            ),
        )
    except Exception as exc:
        return Check("Outputs", "fail", f"Error checking sinks/storage: {exc}")


def run_doctor() -> int:
    """Run all health checks and print a report. Returns exit code (0 = all ok)."""
    console.print(
        Panel(
            "[bold]Epistora Doctor[/bold]\nChecking your environment...",
            border_style="blue",
        )
    )
    console.print()

    checks: list[Check] = []

    # Environment
    checks.append(_check_installation())
    checks.append(_check_python())
    checks.append(_check_uv())
    checks.append(_check_platform())

    # Configuration
    checks.append(_check_env_file())
    checks.append(_check_config_resolution())
    checks.append(_check_vault())
    checks.append(_check_database())

    # Connectors
    checks.append(_check_raindrop())

    # Backends
    checks.extend(_check_backends())

    # Automation
    checks.append(_check_automation())

    # Plugins / output layers
    checks.append(_check_plugins())
    checks.append(_check_outputs())

    # Print results
    table = Table(show_header=True, header_style="bold", show_lines=False)
    table.add_column("Status", width=3, justify="center")
    table.add_column("Check", min_width=20)
    table.add_column("Details")

    for check in checks:
        table.add_row(check.icon, check.name, check.message)

    console.print(table)

    # Print hints for issues
    issues = [c for c in checks if c.status in ("warn", "fail") and c.hint]
    if issues:
        console.print()
        console.print("[bold]Recommendations:[/bold]")
        for check in issues:
            icon = "[yellow]→[/yellow]" if check.status == "warn" else "[red]→[/red]"
            console.print(f"  {icon} [bold]{check.name}:[/bold] {check.hint}")

    # Summary
    ok_count = sum(1 for c in checks if c.status == "ok")
    warn_count = sum(1 for c in checks if c.status == "warn")
    fail_count = sum(1 for c in checks if c.status == "fail")

    console.print()
    if fail_count:
        console.print(
            f"[red]✗ {fail_count} issue(s) need attention[/red], "
            f"{warn_count} warning(s), {ok_count} ok"
        )
        return 1
    elif warn_count:
        console.print(
            f"[yellow]⚠ {warn_count} warning(s)[/yellow], {ok_count} ok — "
            "Epistora should work but some features may be limited"
        )
        return 0
    else:
        console.print(f"[green]✓ All {ok_count} checks passed![/green] You're ready to go.")
        return 0
