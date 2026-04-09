"""Cross-platform scheduler helper generation for OS-level automation."""

from __future__ import annotations

import os
import shlex
import shutil
import sys
from textwrap import dedent

from app.config import epistora_home, epistora_logs_dir


def _launchd_environment_entries() -> str:
    """Return launchd EnvironmentVariables entries for CLI backend discovery."""
    env: dict[str, str] = {}

    path_value = os.environ.get("PATH")
    if path_value:
        env["PATH"] = path_value

    home_value = os.environ.get("HOME")
    if home_value:
        env["HOME"] = home_value

    if not env:
        return ""

    lines = ["    <key>EnvironmentVariables</key>", "    <dict>"]
    for key, value in env.items():
        lines.append(f"        <key>{key}</key>")
        lines.append(f"        <string>{value}</string>")
    lines.append("    </dict>")
    return "\n".join(lines)


def _cli_command_parts(mode: str) -> list[str]:
    """Return the preferred automation command for installed or source usage."""
    epistora_cli = shutil.which("epistora")
    if epistora_cli:
        return [epistora_cli, "automation", "run-pending", "--mode", mode]
    return [sys.executable, "-m", "app.cli.main", "automation", "run-pending", "--mode", mode]


def _cli_command_string(mode: str) -> str:
    """Return a shell-safe string form of the automation command."""
    return shlex.join(_cli_command_parts(mode))


def generate_launchd_plist(
    mode: str = "safe",
    interval_minutes: int = 30,
    label: str = "com.epistora.automation",
) -> str:
    """Generate a macOS LaunchAgent plist for scheduled automation."""
    command_parts = _cli_command_parts(mode)
    working_dir = str(epistora_home())
    logs_dir = epistora_logs_dir()
    interval_seconds = interval_minutes * 60
    environment_entries = _launchd_environment_entries()
    environment_block = f"\n{environment_entries}\n" if environment_entries else "\n"
    args_xml = "\n".join(f"            <string>{part}</string>" for part in command_parts)

    return dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
          "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
            <key>Label</key>
            <string>{label}</string>

            <key>ProgramArguments</key>
            <array>
{args_xml}
            </array>

            <key>WorkingDirectory</key>
            <string>{working_dir}</string>
{environment_block}

            <key>StartInterval</key>
            <integer>{interval_seconds}</integer>

            <key>StandardOutPath</key>
            <string>{logs_dir / 'automation-stdout.log'}</string>

            <key>StandardErrorPath</key>
            <string>{logs_dir / 'automation-stderr.log'}</string>

            <key>RunAtLoad</key>
            <false/>

            <key>KeepAlive</key>
            <false/>
        </dict>
        </plist>
    """)


def generate_systemd_timer(
    mode: str = "safe",
    interval_minutes: int = 30,
    unit_name: str = "epistora-automation",
) -> tuple[str, str]:
    """Generate Linux systemd service and timer unit files.

    Returns (service_content, timer_content).
    """
    working_dir = str(epistora_home())
    user = os.environ.get("USER", "epistora")
    command = _cli_command_string(mode)

    service = dedent(f"""\
        [Unit]
        Description=Epistora automation runner
        After=network.target

        [Service]
        Type=oneshot
        User={user}
        WorkingDirectory={working_dir}
        ExecStart={command}
        StandardOutput=journal
        StandardError=journal

        [Install]
        WantedBy=multi-user.target
    """)

    timer = dedent(f"""\
        [Unit]
        Description=Run Epistora automation every {interval_minutes} minutes

        [Timer]
        OnBootSec=5min
        OnUnitActiveSec={interval_minutes}min
        Persistent=true

        [Install]
        WantedBy=timers.target
    """)

    return service, timer


def generate_windows_task_xml(
    mode: str = "safe",
    interval_minutes: int = 30,
    task_name: str = "EpistoraAutomation",
) -> str:
    """Generate a Windows Task Scheduler XML import file."""
    command_parts = _cli_command_parts(mode)
    working_dir = str(epistora_home()).replace("/", "\\")
    command_win = command_parts[0].replace("/", "\\")
    arguments = " ".join(command_parts[1:])
    description = (
        "Epistora automation runner "
        f"({mode} mode every {interval_minutes} min)"
    )

    return dedent(f"""\
        <?xml version="1.0" encoding="UTF-16"?>
        <Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
          <RegistrationInfo>
            <Description>{description}</Description>
          </RegistrationInfo>
          <Triggers>
            <TimeTrigger>
              <Repetition>
                <Interval>PT{interval_minutes}M</Interval>
                <StopAtDurationEnd>false</StopAtDurationEnd>
              </Repetition>
              <StartBoundary>2024-01-01T00:00:00</StartBoundary>
              <Enabled>true</Enabled>
            </TimeTrigger>
          </Triggers>
          <Settings>
            <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
            <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
            <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
            <AllowHardTerminate>true</AllowHardTerminate>
            <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
            <IdleSettings>
              <StopOnIdleEnd>false</StopOnIdleEnd>
              <RestartOnIdle>false</RestartOnIdle>
            </IdleSettings>
            <AllowStartOnDemand>true</AllowStartOnDemand>
            <Enabled>true</Enabled>
            <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>
          </Settings>
          <Actions Context="Author">
            <Exec>
              <Command>{command_win}</Command>
              <Arguments>{arguments}</Arguments>
              <WorkingDirectory>{working_dir}</WorkingDirectory>
            </Exec>
          </Actions>
        </Task>
    """)


def generate_scheduler_instructions(
    mode: str = "safe",
    interval_minutes: int = 30,
) -> str:
    """Generate human-readable instructions for all platforms."""
    logs_dir = epistora_logs_dir()
    command = _cli_command_string(mode)
    macos_generate = (
        "epistora automation generate-scheduler "
        f"--platform macos --mode {mode} --interval {interval_minutes}"
    )
    linux_generate = (
        "epistora automation generate-scheduler "
        f"--platform linux --mode {mode} --interval {interval_minutes}"
    )
    windows_generate = (
        "epistora automation generate-scheduler "
        f"--platform windows --mode {mode} --interval {interval_minutes}"
    )
    windows_register = (
        "Register-ScheduledTask -Xml "
        "(Get-Content epistora-automation.xml | Out-String) "
        '-TaskName "EpistoraAutomation"'
    )
    cron_line = (
        f"*/{interval_minutes} * * * * {command} "
        f">> {logs_dir / 'automation.log'} 2>&1"
    )

    return dedent(f"""\
        # Epistora Cross-Platform Scheduling Guide

        Epistora's automation is designed as one-shot idempotent commands.
        Use your OS scheduler to invoke them on an interval.

        ## The Command

        All scheduling calls the same one-shot command:

            {command}

        This will:
        1. Discover new bookmarks from configured connectors
        2. Process pending queued items
        3. Optionally run maintenance (lint, index rebuild)
        4. Exit cleanly

        ---

        ## macOS (launchd)

        1. Generate the plist:
           {macos_generate}

        2. Ensure the log directory exists:
           mkdir -p {logs_dir}

        3. Copy to LaunchAgents:
           cp com.epistora.automation.plist ~/Library/LaunchAgents/com.epistora.automation.plist

        4. Load it for the current GUI session:
           launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.epistora.automation.plist

        5. Start one run immediately:
           launchctl kickstart -k gui/$(id -u)/com.epistora.automation

        6. To unload:
           launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.epistora.automation.plist

        ---

        ## Linux (systemd)

        1. Generate the units:
           {linux_generate}

        2. Copy the files:
           sudo cp epistora-automation.service /etc/systemd/system/
           sudo cp epistora-automation.timer /etc/systemd/system/

        3. Enable and start:
           sudo systemctl daemon-reload
           sudo systemctl enable --now epistora-automation.timer

        4. Check status:
           systemctl status epistora-automation.timer
           journalctl -u epistora-automation.service

        ---

        ## Windows (Task Scheduler)

        1. Generate the XML:
           {windows_generate}

        2. Import via PowerShell:
           {windows_register}

        3. Or import via Task Scheduler GUI:
           Open Task Scheduler → Import Task → Select the XML file

        ---

        ## Cron (any Unix)

        Add to crontab:
           crontab -e

        Add this line (every {interval_minutes} minutes):
           {cron_line}

        ---

        ## Notes

        - The command is idempotent and safe to run concurrently (uses file locks)
        - Safe mode avoids expensive LLM calls by default
        - Use --mode balanced or --mode deep for AI enrichment
        - Configure limits in Epistora's config file to control costs
    """)
