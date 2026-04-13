"""
test_live.py
------------
End-to-end live test for the File Automation System.

Creates a self-contained temporary environment, starts the watcher,
drops test files, waits for processing, and prints a full report.

Usage:
    python test_live.py

No configuration needed — everything runs in a temp folder and is
cleaned up automatically at the end.
"""

import sys
import time
import shutil
import tempfile
import threading
import zipfile
from pathlib import Path

# ── Make sure src/ is importable ─────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent / "src"))

from logger_setup import setup_logging
from rule_engine import RuleEngine
from processor import FileProcessor
from watcher import DirectoryWatcher

# ── ANSI colours ─────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):   print(f"  {GREEN}✔{RESET}  {msg}")
def fail(msg): print(f"  {RED}✘{RESET}  {msg}")
def info(msg): print(f"  {CYAN}→{RESET}  {msg}")
def warn(msg): print(f"  {YELLOW}!{RESET}  {msg}")

# ── Test cases ────────────────────────────────────────────────────────────────
# Each entry: (filename, content, expected_outcome)
# expected_outcome: "archived_zip" | "archived_raw" | "deleted" | "untouched"
TEST_FILES = [
    ("invoice.pdf",      b"%PDF-1.4 fake pdf content",   "archived_zip"),
    ("photo.jpg",        b"\xff\xd8\xff fake jpeg data",  "archived_raw"),
    ("notes.txt",        b"Hello, this is a text file.",  "archived_zip"),
    ("report.docx",      b"PK fake docx content",         "archived_zip"),
    ("~lockfile",        b"",                             "deleted"),
    ("cache.tmp",        b"temporary data",               "deleted"),
    ("backup.bak",       b"old version",                  "deleted"),
    ("Thumbs.db",        b"windows thumbnail cache",      "deleted"),
    ("data.xyz",         b"unknown extension",            "untouched"),
]

# ── Config builder ────────────────────────────────────────────────────────────
def build_config(base: Path) -> dict:
    input_dir     = base / "Input"
    archive_dir   = base / "Archive"
    logs_dir      = base / "Logs"
    quarantine_dir = base / "Archive" / "quarantine"

    for d in [input_dir, archive_dir, logs_dir, quarantine_dir]:
        d.mkdir(parents=True, exist_ok=True)

    return {
        "version": "1.0",
        "settings": {
            "log_level": "INFO",
            "max_worker_threads": 4,
            "file_stability_check_interval_ms": 50,
            "file_stability_max_retries": 3,
        },
        "paths": {
            "watch_dirs":     [str(input_dir)],
            "archive_dir":    str(archive_dir),
            "logs_dir":       str(logs_dir),
            "quarantine_dir": str(quarantine_dir),
        },
        "rename": {
            "enabled": True,
            "timestamp_format": "%Y%m%d_%H%M%S",
            "separator": "_",
        },
        "temp_patterns": ["~*", "*.tmp", "*.bak", "Thumbs.db", ".DS_Store"],
        "rules": [
            {
                "id": "rule_pdf",
                "priority": 10,
                "match_extensions": [".pdf"],
                "match_name_pattern": None,
                "actions": ["rename", "compress", "move_to_archive"],
            },
            {
                "id": "rule_image",
                "priority": 20,
                "match_extensions": [".jpg", ".jpeg", ".png"],
                "match_name_pattern": None,
                "actions": ["rename", "move_to_archive"],
            },
            {
                "id": "rule_document",
                "priority": 30,
                "match_extensions": [".txt", ".csv", ".docx", ".doc", ".xlsx"],
                "match_name_pattern": None,
                "actions": ["rename", "compress", "move_to_archive"],
            },
        ],
    }

# ── Outcome checker ───────────────────────────────────────────────────────────
def check_outcome(original_name: str, expected: str, config: dict) -> tuple[bool, str]:
    """
    Returns (passed: bool, detail: str).
    """
    archive_dir   = Path(config["paths"]["archive_dir"])
    input_dir     = Path(config["paths"]["watch_dirs"][0])
    quarantine_dir = Path(config["paths"]["quarantine_dir"])
    stem          = Path(original_name).stem
    suffix        = Path(original_name).suffix

    if expected == "deleted":
        still_in_input  = (input_dir / original_name).exists()
        in_archive       = any(archive_dir.rglob(f"{stem}*"))
        if not still_in_input and not in_archive:
            return True, "deleted correctly"
        if still_in_input:
            return False, "still in Input/ — not deleted"
        return False, f"ended up in Archive/ instead of being deleted"

    if expected == "archived_zip":
        zips = list(archive_dir.glob(f"{stem}_*.zip"))
        if zips:
            # Verify the ZIP is valid and contains the renamed file
            try:
                with zipfile.ZipFile(zips[0], "r") as zf:
                    names = zf.namelist()
                return True, f"renamed + zipped → {zips[0].name}  (contains: {names[0]})"
            except zipfile.BadZipFile:
                return False, f"ZIP exists but is corrupt: {zips[0].name}"
        # Check quarantine
        if any(quarantine_dir.rglob(f"{stem}*")):
            return False, "ended up in quarantine — check logs"
        if (input_dir / original_name).exists():
            return False, "still in Input/ — not processed"
        return False, "not found in Archive/ — processing may have failed"

    if expected == "archived_raw":
        # Should be renamed but NOT zipped
        raw_files = [
            f for f in archive_dir.glob(f"{stem}_*{suffix}")
            if not f.suffix == ".zip"
        ]
        if raw_files:
            return True, f"renamed + moved → {raw_files[0].name}"
        zips = list(archive_dir.glob(f"{stem}_*.zip"))
        if zips:
            return False, f"was compressed when it should not have been: {zips[0].name}"
        if (input_dir / original_name).exists():
            return False, "still in Input/ — not processed"
        return False, "not found in Archive/"

    if expected == "untouched":
        if (input_dir / original_name).exists():
            return True, "left untouched in Input/ (no rule matched)"
        if any(archive_dir.rglob(f"{stem}*")):
            return False, "was moved to Archive/ — should have been skipped"
        return False, "disappeared from Input/ for unknown reason"

    return False, f"unknown expected outcome: {expected}"

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print()
    print(f"{BOLD}{'═' * 58}{RESET}")
    print(f"{BOLD}   File Automation System — Live End-to-End Test{RESET}")
    print(f"{BOLD}{'═' * 58}{RESET}")

    base = Path(tempfile.mkdtemp(prefix="file_automation_test_"))
    print(f"\n  Test workspace: {base}\n")

    config = build_config(base)
    input_dir = Path(config["paths"]["watch_dirs"][0])

    # Boot logger
    setup_logging(logs_dir=Path(config["paths"]["logs_dir"]), log_level="WARNING")

    # Boot system
    rule_engine = RuleEngine(config)
    processor   = FileProcessor(config, rule_engine)
    watcher     = DirectoryWatcher(config, processor)

    # Start watcher in a background thread
    watcher_thread = threading.Thread(target=watcher.start, daemon=True)
    watcher_thread.start()
    time.sleep(0.5)  # Let watchdog register the directory

    # ── Drop test files ───────────────────────────────────────────────────────
    print(f"  {BOLD}Dropping {len(TEST_FILES)} test files into Input/...{RESET}\n")
    for name, content, _ in TEST_FILES:
        path = input_dir / name
        path.write_bytes(content)
        info(f"Dropped: {name}")
        time.sleep(0.05)   # small spread so timestamps differ

    # ── Wait for processing ───────────────────────────────────────────────────
    print(f"\n  {BOLD}Waiting for processing (max 6 seconds)...{RESET}\n")
    deadline = time.time() + 6
    while time.time() < deadline:
        # Check if all non-untouched files have left the Input folder
        remaining = [
            name for name, _, expected in TEST_FILES
            if expected != "untouched" and (input_dir / name).exists()
        ]
        if not remaining:
            break
        time.sleep(0.2)

    # ── Report ────────────────────────────────────────────────────────────────
    print(f"  {BOLD}{'─' * 54}{RESET}")
    print(f"  {'FILE':<25} {'EXPECTED':<15} {'RESULT'}")
    print(f"  {BOLD}{'─' * 54}{RESET}")

    passed = 0
    failed_list = []

    for name, _, expected in TEST_FILES:
        ok_flag, detail = check_outcome(name, expected, config)
        status = f"{GREEN}PASS{RESET}" if ok_flag else f"{RED}FAIL{RESET}"
        print(f"  {name:<25} {expected:<15} {status}  {detail}")
        if ok_flag:
            passed += 1
        else:
            failed_list.append((name, detail))

    total = len(TEST_FILES)
    print(f"\n  {BOLD}{'─' * 54}{RESET}")

    if passed == total:
        print(f"\n  {GREEN}{BOLD}All {total}/{total} tests passed.{RESET}\n")
    else:
        print(f"\n  {RED}{BOLD}{passed}/{total} passed — {total - passed} failed:{RESET}")
        for name, reason in failed_list:
            print(f"    {RED}✘{RESET}  {name}: {reason}")
        print()

    # ── Show archive contents ─────────────────────────────────────────────────
    archive_dir = Path(config["paths"]["archive_dir"])
    archived = sorted(archive_dir.glob("*"))
    archived = [f for f in archived if f.is_file()]

    if archived:
        print(f"  {BOLD}Archive contents:{RESET}")
        for f in archived:
            size = f.stat().st_size
            print(f"    {CYAN}•{RESET} {f.name:<45} ({size:,} bytes)")
        print()

    # ── Show log tail ─────────────────────────────────────────────────────────
    log_file = Path(config["paths"]["logs_dir"]) / "automation.log"
    if log_file.exists():
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        if lines:
            print(f"  {BOLD}Log output:{RESET}")
            for line in lines:
                print(f"    {line}")
            print()

    # ── Cleanup ───────────────────────────────────────────────────────────────
    shutil.rmtree(base, ignore_errors=True)
    print(f"  Temp workspace cleaned up.\n")
    print(f"{BOLD}{'═' * 58}{RESET}\n")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
