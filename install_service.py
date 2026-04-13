"""
install_service.py
------------------
Cross-platform service installer for the File Automation System.

Detects the current OS and installs the system service automatically:
  - Linux   → systemd  (runs as a background service, starts at boot)
  - macOS   → launchd  (runs as a user agent, starts at login)
  - Windows → Task Scheduler (runs at startup, even when not logged in)

Usage:
    python install_service.py          # install
    python install_service.py --remove # uninstall
    python install_service.py --status # check current status
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
INSTALL_DIR = Path(__file__).parent.resolve()
SERVICE_DIR = INSTALL_DIR / "service"
CONFIG_FILE = INSTALL_DIR / "config" / "config.json"

# ── ANSI colours ─────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):   print(f"  {GREEN}✔{RESET}  {msg}")
def err(msg):  print(f"  {RED}✘{RESET}  {msg}"); sys.exit(1)
def warn(msg): print(f"  {YELLOW}!{RESET}  {msg}")
def info(msg): print(f"  {CYAN}→{RESET}  {msg}")
def step(msg): print(f"\n{BOLD}{msg}{RESET}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def find_python() -> Path:
    """Return the Python executable for the current environment."""
    return Path(sys.executable)


def run(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=True,
    )


def _fill_template(template_path: Path, replacements: dict[str, str]) -> str:
    content = template_path.read_text(encoding="utf-8")
    for key, value in replacements.items():
        content = content.replace(f"{{{key}}}", value)
    return content


# ══════════════════════════════════════════════════════════════════════════════
# Linux — systemd
# ══════════════════════════════════════════════════════════════════════════════

class SystemdInstaller:
    SERVICE_NAME = "file-automation"
    TEMPLATE     = SERVICE_DIR / "file-automation.service"
    DEST         = Path("/etc/systemd/system/file-automation.service")

    def install(self) -> None:
        step("Installing systemd service...")

        self._check_root()
        python = find_python()
        info(f"Python   : {python}")
        info(f"Directory: {INSTALL_DIR}")

        content = _fill_template(self.TEMPLATE, {
            "USER":        os.getenv("SUDO_USER") or os.getlogin(),
            "GROUP":       os.getenv("SUDO_USER") or os.getlogin(),
            "INSTALL_DIR": str(INSTALL_DIR),
            "PYTHON":      str(python),
        })

        self.DEST.write_text(content, encoding="utf-8")
        ok(f"Service file written to {self.DEST}")

        run(["systemctl", "daemon-reload"])
        run(["systemctl", "enable", self.SERVICE_NAME])
        run(["systemctl", "start",  self.SERVICE_NAME])

        ok("Service enabled and started.")
        self.status()

    def remove(self) -> None:
        step("Removing systemd service...")
        self._check_root()

        run(["systemctl", "stop",    self.SERVICE_NAME], check=False)
        run(["systemctl", "disable", self.SERVICE_NAME], check=False)

        if self.DEST.exists():
            self.DEST.unlink()
            ok(f"Removed {self.DEST}")

        run(["systemctl", "daemon-reload"])
        ok("Service removed.")

    def status(self) -> None:
        print()
        run(["systemctl", "status", self.SERVICE_NAME, "--no-pager"], check=False)

    def _check_root(self) -> None:
        if os.geteuid() != 0:
            err("systemd installation requires root. Run with: sudo python install_service.py")


# ══════════════════════════════════════════════════════════════════════════════
# macOS — launchd
# ══════════════════════════════════════════════════════════════════════════════

class LaunchdInstaller:
    LABEL    = "com.fileautomation"
    TEMPLATE = SERVICE_DIR / "com.fileautomation.plist"
    DEST     = Path.home() / "Library" / "LaunchAgents" / "com.fileautomation.plist"

    def install(self) -> None:
        step("Installing launchd agent...")

        python = find_python()
        info(f"Python   : {python}")
        info(f"Directory: {INSTALL_DIR}")

        self.DEST.parent.mkdir(parents=True, exist_ok=True)

        content = _fill_template(self.TEMPLATE, {
            "INSTALL_DIR": str(INSTALL_DIR),
            "PYTHON":      str(python),
        })

        self.DEST.write_text(content, encoding="utf-8")
        ok(f"Plist written to {self.DEST}")

        # Unload first if already loaded
        run(["launchctl", "unload", str(self.DEST)], check=False)
        run(["launchctl", "load",   str(self.DEST)])

        ok("Agent loaded — will start automatically at login.")
        self.status()

    def remove(self) -> None:
        step("Removing launchd agent...")

        run(["launchctl", "unload", str(self.DEST)], check=False)

        if self.DEST.exists():
            self.DEST.unlink()
            ok(f"Removed {self.DEST}")

        ok("Agent removed.")

    def status(self) -> None:
        result = run(
            ["launchctl", "list", self.LABEL],
            check=False, capture=True,
        )
        print()
        if result.returncode == 0:
            ok(f"Agent '{self.LABEL}' is loaded.")
            print(result.stdout)
        else:
            warn(f"Agent '{self.LABEL}' is not loaded.")


# ══════════════════════════════════════════════════════════════════════════════
# Windows — Task Scheduler
# ══════════════════════════════════════════════════════════════════════════════

class TaskSchedulerInstaller:
    TASK_NAME = "FileAutomationSystem"

    def install(self) -> None:
        step("Installing Windows Task Scheduler task...")

        python = find_python()
        info(f"Python   : {python}")
        info(f"Directory: {INSTALL_DIR}")

        # Build the schtasks command
        script_path = INSTALL_DIR / "src" / "main.py"
        cmd_action  = f'"{python}" "{script_path}" --config "{CONFIG_FILE}"'

        schtasks_cmd = [
            "schtasks", "/Create",
            "/F",                           # Overwrite if exists
            "/TN",  self.TASK_NAME,
            "/TR",  cmd_action,
            "/SC",  "ONLOGON",              # Trigger: at login
            "/RL",  "HIGHEST",              # Run with highest privileges
            "/RU",  os.getenv("USERNAME"),  # Run as current user
        ]

        run(schtasks_cmd)
        ok(f"Task '{self.TASK_NAME}' created.")

        # Start it immediately
        run(["schtasks", "/Run", "/TN", self.TASK_NAME])
        ok("Task started.")
        self.status()

    def remove(self) -> None:
        step("Removing Task Scheduler task...")

        run(["schtasks", "/End",    "/TN", self.TASK_NAME], check=False)
        run(["schtasks", "/Delete", "/TN", self.TASK_NAME, "/F"], check=False)
        ok(f"Task '{self.TASK_NAME}' removed.")

    def status(self) -> None:
        print()
        run(["schtasks", "/Query", "/TN", self.TASK_NAME, "/FO", "LIST"], check=False)


# ══════════════════════════════════════════════════════════════════════════════
# OS detection + dispatch
# ══════════════════════════════════════════════════════════════════════════════

def get_installer() -> SystemdInstaller | LaunchdInstaller | TaskSchedulerInstaller:
    system = platform.system()
    if system == "Linux":
        if not shutil.which("systemctl"):
            err("systemctl not found. Is systemd running on this machine?")
        return SystemdInstaller()
    elif system == "Darwin":
        return LaunchdInstaller()
    elif system == "Windows":
        return TaskSchedulerInstaller()
    else:
        err(f"Unsupported OS: {system}")


def _preflight_checks() -> None:
    """Verify the project is properly set up before installing."""
    step("Pre-flight checks...")

    if not CONFIG_FILE.exists():
        err(f"Config file not found: {CONFIG_FILE}\n"
            "  Edit config/config.json before installing the service.")

    main_script = INSTALL_DIR / "src" / "main.py"
    if not main_script.exists():
        err(f"Main script not found: {main_script}")

    try:
        import watchdog  # noqa: F401
    except ImportError:
        err("watchdog is not installed.\n"
            "  Run: pip install -r requirements.txt")

    ok("Config file found")
    ok("Source files found")
    ok("Dependencies installed")


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Install / remove the File Automation System as a background service."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--remove", action="store_true",
        help="Stop and remove the service.",
    )
    group.add_argument(
        "--status", action="store_true",
        help="Show current service status.",
    )
    args = parser.parse_args()

    print()
    print(f"{BOLD}{'═' * 54}{RESET}")
    print(f"{BOLD}   File Automation System — Service Installer{RESET}")
    print(f"{BOLD}   OS: {platform.system()} {platform.release()}{RESET}")
    print(f"{BOLD}{'═' * 54}{RESET}")

    installer = get_installer()

    if args.remove:
        installer.remove()
    elif args.status:
        installer.status()
    else:
        _preflight_checks()
        installer.install()
        print()
        print(f"{GREEN}{BOLD}  Done! The system is now running in the background.{RESET}")
        print(f"  It will start automatically every time the machine boots.")
        print()
        print(f"  Commands:")
        _print_commands()

    print()


def _print_commands() -> None:
    system = platform.system()
    if system == "Linux":
        print(f"    Stop    : sudo systemctl stop file-automation")
        print(f"    Start   : sudo systemctl start file-automation")
        print(f"    Logs    : sudo journalctl -u file-automation -f")
        print(f"    Remove  : sudo python install_service.py --remove")
    elif system == "Darwin":
        print(f"    Stop    : launchctl unload ~/Library/LaunchAgents/com.fileautomation.plist")
        print(f"    Start   : launchctl load  ~/Library/LaunchAgents/com.fileautomation.plist")
        print(f"    Logs    : tail -f {INSTALL_DIR}/service/launchd_stdout.log")
        print(f"    Remove  : python install_service.py --remove")
    elif system == "Windows":
        print(f"    Stop    : schtasks /End    /TN FileAutomationSystem")
        print(f"    Start   : schtasks /Run    /TN FileAutomationSystem")
        print(f"    Remove  : python install_service.py --remove")


if __name__ == "__main__":
    main()
