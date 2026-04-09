"""Tests for the new CLI commands: setup wizard, doctor, connect, backend."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from app.cli.main import app

runner = CliRunner()


class TestCLIHelp:
    """Verify that all commands render help without errors."""

    def test_main_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Epistora" in result.output

    def test_setup_help(self):
        result = runner.invoke(app, ["setup", "--help"])
        assert result.exit_code == 0
        assert "setup" in result.output.lower()

    def test_doctor_help(self):
        result = runner.invoke(app, ["doctor", "--help"])
        assert result.exit_code == 0
        assert "doctor" in result.output.lower() or "Check" in result.output

    def test_init_help(self):
        result = runner.invoke(app, ["init", "--help"])
        assert result.exit_code == 0
        assert "vault" in result.output.lower()

    def test_ingest_help(self):
        result = runner.invoke(app, ["ingest", "--help"])
        assert result.exit_code == 0
        assert "latest" in result.output.lower()
        assert "url" in result.output.lower()

    def test_ingest_latest_help(self):
        result = runner.invoke(app, ["ingest", "latest", "--help"])
        assert result.exit_code == 0
        assert "connector" in result.output.lower()

    def test_automation_help(self):
        result = runner.invoke(app, ["automation", "--help"])
        assert result.exit_code == 0
        assert "discover" in result.output.lower()

    def test_automation_setup_help(self):
        result = runner.invoke(app, ["automation", "setup", "--help"])
        assert result.exit_code == 0

    def test_backend_help(self):
        result = runner.invoke(app, ["backend", "--help"])
        assert result.exit_code == 0
        assert "status" in result.output.lower()

    def test_backend_setup_help(self):
        result = runner.invoke(app, ["backend", "setup", "--help"])
        assert result.exit_code == 0

    def test_connect_help(self):
        result = runner.invoke(app, ["connect", "--help"])
        assert result.exit_code == 0
        assert "raindrop" in result.output.lower()

    def test_connect_raindrop_help(self):
        result = runner.invoke(app, ["connect", "raindrop", "--help"])
        assert result.exit_code == 0

    def test_version_option(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "epistora" in result.output.lower()


class TestDoctor:
    """Test the doctor command."""

    def test_doctor_runs(self):
        result = runner.invoke(app, ["doctor"])
        assert "Python" in result.output
        assert "Platform" in result.output

    def test_doctor_checks_python(self):
        from app.cli.doctor import _check_python

        check = _check_python()
        assert check.status == "ok"
        assert "Python" in check.message

    def test_doctor_checks_platform(self):
        from app.cli.doctor import _check_platform

        check = _check_platform()
        assert check.status == "ok"

    def test_doctor_checks_uv(self):
        from app.cli.doctor import _check_uv

        check = _check_uv()
        assert check.status in ("ok", "warn")


class TestInit:
    """Test the init command."""

    def test_init_creates_vault(self, tmp_path):
        vault = tmp_path / "test-vault"
        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.db_path = tmp_path / "test.db"
            mock_settings.return_value.vault_path = vault
            result = runner.invoke(app, ["init", "--vault", str(vault)])

        assert result.exit_code == 0
        assert vault.exists()
        assert (vault / "wiki").exists()
        assert (vault / "raw").exists()
        assert (vault / "wiki" / "indexes").exists()
        assert (vault / "wiki" / "logs").exists()


class TestSetupWizard:
    """Test the setup wizard helper functions."""

    def test_write_env_file(self, tmp_path):
        from app.cli.setup_wizard import _write_env_file

        env_path = tmp_path / ".env"
        config = {
            "vault_path": "/tmp/test-vault",
            "api_api_key": "test-key",
            "automation_enabled": "true",
        }
        _write_env_file(env_path, config)

        assert env_path.exists()
        content = env_path.read_text()
        assert "VAULT_PATH=/tmp/test-vault" in content
        assert "API_API_KEY=test-key" in content
        assert "AUTOMATION_ENABLED=true" in content

    def test_write_env_file_preserves_existing(self, tmp_path):
        from app.cli.setup_wizard import _write_env_file

        env_path = tmp_path / ".env"
        env_path.write_text("EXISTING_KEY=existing_value\n")

        _write_env_file(env_path, {"new_key": "new_value"})

        content = env_path.read_text()
        assert "EXISTING_KEY=existing_value" in content
        assert "NEW_KEY=new_value" in content

    def test_initialize_vault(self, tmp_path):
        from app.cli.setup_wizard import _initialize_vault

        vault = tmp_path / "vault"
        _initialize_vault(vault)

        assert (vault / "AGENTS.md").exists()
        assert (vault / "wiki" / "indexes").exists()
        assert (vault / "wiki" / "indexes" / "START_HERE.md").exists()
        assert (vault / "wiki" / "indexes" / "QUERY_PROTOCOL.md").exists()
        assert (vault / "raw").exists()
        assert (vault / "wiki" / "logs" / "ingest-log.md").exists()

    def test_detect_platform(self):
        from app.cli.setup_wizard import _detect_platform

        plat = _detect_platform()
        assert plat in ("macos", "linux", "windows", "unknown")


class TestDoctorChecks:
    """Test individual doctor check functions."""

    def test_check_env_file_missing(self, tmp_path, monkeypatch):
        from app.cli.doctor import _check_env_file

        workdir = tmp_path / "work"
        home = tmp_path / "home"
        workdir.mkdir()
        monkeypatch.chdir(workdir)
        monkeypatch.setenv("EPISTORA_HOME", str(home))
        monkeypatch.delenv("EPISTORA_ENV_FILE", raising=False)

        with patch("app.config.project_root", return_value=tmp_path / "project"):
            check = _check_env_file()
        assert check.status in {"fail", "warn"}

    def test_check_env_file_from_epistora_home(self, tmp_path, monkeypatch):
        from app.cli.doctor import _check_env_file

        workdir = tmp_path / "work"
        home = tmp_path / "home"
        workdir.mkdir()
        home.mkdir()
        (home / ".env").write_text("VAULT_PATH=/tmp/vault\n", encoding="utf-8")
        monkeypatch.chdir(workdir)
        monkeypatch.setenv("EPISTORA_HOME", str(home))
        monkeypatch.delenv("EPISTORA_ENV_FILE", raising=False)

        with patch("app.config.project_root", return_value=tmp_path / "project"):
            check = _check_env_file()
        assert check.status == "ok"
        assert str(home / ".env") in check.message

    def test_preferred_env_file_uses_epistora_home_outside_repo(self, tmp_path, monkeypatch):
        from app.config import preferred_env_file

        workdir = tmp_path / "work"
        home = tmp_path / "home"
        workdir.mkdir()
        monkeypatch.chdir(workdir)
        monkeypatch.setenv("EPISTORA_HOME", str(home))
        monkeypatch.delenv("EPISTORA_ENV_FILE", raising=False)

        with patch("app.config.project_root", return_value=tmp_path / "project"):
            preferred = preferred_env_file()
        assert preferred == Path(home) / ".env"

    def test_check_raindrop_no_token(self):
        from app.cli.doctor import _check_raindrop

        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.raindrop_api_token = ""
            check = _check_raindrop()
            assert check.status == "warn"

    def test_check_raindrop_with_token(self):
        from app.cli.doctor import _check_raindrop

        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.raindrop_api_token = "test-token-value-12345"
            check = _check_raindrop()
            assert check.status == "ok"

    def test_check_automation_disabled(self):
        from app.cli.doctor import _check_automation

        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.automation_enabled = False
            mock_settings.return_value.automation_default_mode = "safe"
            check = _check_automation()
            assert check.status == "ok"
            assert "Disabled" in check.message

    def test_check_automation_enabled(self):
        from app.cli.doctor import _check_automation

        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.automation_enabled = True
            mock_settings.return_value.automation_default_mode = "balanced"
            check = _check_automation()
            assert check.status == "ok"
            assert "Enabled" in check.message

    def test_check_api_backend_disabled(self):
        from app.cli.doctor import _check_backends

        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.api_enabled = False
            mock_settings.return_value.effective_api_key.return_value = ""
            mock_settings.return_value.effective_api_model.return_value = ""
            mock_settings.return_value.opencode_binary = "opencode"
            mock_settings.return_value.opencode_enabled = False
            mock_settings.return_value.claude_code_binary = "claude"
            mock_settings.return_value.claude_code_enabled = False
            mock_settings.return_value.codex_binary = "codex"
            mock_settings.return_value.codex_enabled = False
            checks = _check_backends()

        api_check = next(check for check in checks if check.name == "Backend: API")
        assert api_check.status == "ok"
        assert api_check.message == "Disabled"
