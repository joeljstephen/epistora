"""Cross-platform scheduler helper generation for OS-level automation."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from textwrap import dedent


def generate_launchd_plist(
    mode: str = "safe",
    interval_minutes: int = 30,
    label: str = "com.epistora.automation",
) -> str:
    """Generate a macOS LaunchAgent plist for scheduled automation."""
    python = sys.executable
    kb_path = Path(__file__).parent.parent.parent
    working_dir = str(kb_path)
    interval_seconds = interval_minutes * 60

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
                <string>{python}</string>
                <string>-m</string>
                <string>app.cli.main</string>
                <string>automation</string>
                <string>run-pending</string>
                <string>--mode</string>
                <string>{mode}</string>
            </array>

            <key>WorkingDirectory</key>
            <string>{working_dir}</string>

            <key>StartInterval</key>
            <integer>{interval_seconds}</integer>

            <key>StandardOutPath</key>
            <string>{working_dir}/logs/automation-stdout.log</string>

            <key>StandardErrorPath</key>
            <string>{working_dir}/logs/automation-stderr.log</string>

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
    python = sys.executable
    kb_path = Path(__file__).parent.parent.parent
    working_dir = str(kb_path)
    user = os.environ.get("USER", "epistora")

    service = dedent(f"""\
        [Unit]
        Description=Epistora automation runner
        After=network.target

        [Service]
        Type=oneshot
        User={user}
        WorkingDirectory={working_dir}
        ExecStart={python} -m app.cli.main automation run-pending --mode {mode}
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
    python = sys.executable
    kb_path = Path(__file__).parent.parent.parent
    working_dir = str(kb_path).replace("/", "\\")
    python_win = python.replace("/", "\\")

    return dedent(f"""\
        <?xml version="1.0" encoding="UTF-16"?>
        <Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
          <RegistrationInfo>
            <Description>Epistora automation runner ({mode} mode every {interval_minutes} min)</Description>
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
              <Command>{python_win}</Command>
              <Arguments>-m app.cli.main automation run-pending --mode {mode}</Arguments>
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
    python = sys.executable
    kb_path = Path(__file__).parent.parent.parent
    working_dir = str(kb_path)

    return dedent(f"""\
        # Epistora Cross-Platform Scheduling Guide

        Epistora's automation is designed as one-shot idempotent commands.
        Use your OS scheduler to invoke them on an interval.

        ## The Command

        All scheduling calls the same one-shot command:

            cd {working_dir}
            {python} -m app.cli.main automation run-pending --mode {mode}

        Or using the installed `kb` CLI:

            kb automation run-pending --mode {mode}

        This will:
        1. Discover new bookmarks from configured connectors
        2. Process pending queued items
        3. Optionally run maintenance (lint, index rebuild)
        4. Exit cleanly

        ---

        ## macOS (launchd)

        1. Generate the plist:
           kb automation generate-scheduler --platform macos --mode {mode} --interval {interval_minutes}

        2. Copy to LaunchAgents:
           cp epistora-automation.plist ~/Library/LaunchAgents/com.epistora.automation.plist

        3. Load it:
           launchctl load ~/Library/LaunchAgents/com.epistora.automation.plist

        4. To unload:
           launchctl unload ~/Library/LaunchAgents/com.epistora.automation.plist

        ---

        ## Linux (systemd)

        1. Generate the units:
           kb automation generate-scheduler --platform linux --mode {mode} --interval {interval_minutes}

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
           kb automation generate-scheduler --platform windows --mode {mode} --interval {interval_minutes}

        2. Import via PowerShell:
           Register-ScheduledTask -Xml (Get-Content epistora-automation.xml | Out-String) -TaskName "EpistoraAutomation"

        3. Or import via Task Scheduler GUI:
           Open Task Scheduler → Import Task → Select the XML file

        ---

        ## Cron (any Unix)

        Add to crontab:
           crontab -e

        Add this line (every {interval_minutes} minutes):
           */{interval_minutes} * * * * cd {working_dir} && {python} -m app.cli.main automation run-pending --mode {mode} >> logs/automation.log 2>&1

        ---

        ## Notes

        - The command is idempotent and safe to run concurrently (uses file locks)
        - Safe mode avoids expensive LLM calls by default
        - Use --mode balanced or --mode deep for AI enrichment
        - Configure limits in .env to control costs
    """)
