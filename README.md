# File Automation System

![Python](https://img.shields.io/badge/python-3.9%2B-blue?logo=python&logoColor=white)
![Tests](https://img.shields.io/badge/tests-36%20passed-brightgreen)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)

A lightweight, config-driven Python automation system that monitors directories in real time, applies intelligent rules, and executes automated file operations — rename, compress, archive, and delete — without manual intervention.

---

## Quick Start

```bash
git clone https://github.com/aarrtH8/file-automation.git
cd file-automation
pip install -r requirements.txt
```

Edit `config/config.json` to set your folder paths, then **install as a background service in one command:**

```bash
# Linux (requires sudo)
sudo python install_service.py

# macOS
python install_service.py

# Windows
python install_service.py
```

The system starts immediately and restarts automatically on every reboot — no terminal left open.

---

## Table of Contents

1. [Features](#features)
2. [How It Works](#how-it-works)
3. [Project Structure](#project-structure)
4. [Installation](#installation)
5. [Configuration Reference](#configuration-reference)
6. [Running Manually](#running-manually)
7. [Running as a Background Service](#running-as-a-background-service)
8. [Logging](#logging)
9. [Testing](#testing)
10. [Error Handling & Quarantine](#error-handling--quarantine)
11. [Adding New Rules](#adding-new-rules)
12. [Troubleshooting](#troubleshooting)
13. [Contributing](#contributing)
14. [License](#license)

---

## Features

- **Real-time monitoring** — detects new files within 2 seconds using `watchdog`
- **Rule-based processing** — all logic defined in `config/config.json`, zero hardcoding
- **Automated pipeline** — Rename → Compress (ZIP) → Move to Archive
- **Temp/duplicate detection** — glob pattern matching deletes junk files automatically
- **Multi-directory support** — monitor multiple input folders simultaneously
- **Cross-platform** — works on Windows, macOS, and Linux
- **Daily rotating logs** — timestamped activity records with full error tracking
- **Quarantine system** — failed files are isolated, never deleted, never re-processed
- **Graceful shutdown** — Ctrl+C stops everything cleanly, no data loss

---

## How It Works

```
 Input Folder (watched)
        │
        │  new file detected (< 2 seconds)
        ▼
 ┌─────────────────┐
 │   Rule Engine   │  ← reads config/config.json
 └────────┬────────┘
          │
    ┌─────┴──────────────────────────────┐
    │  temp pattern? (*.tmp, ~*, ...)    │ → DELETE
    └─────┬──────────────────────────────┘
          │  no
    ┌─────┴──────────────────────────────┐
    │  match a rule by extension/name?  │ → no match → SKIP (logged)
    └─────┬──────────────────────────────┘
          │  yes → execute action list in order
          │
    [rename]  →  [compress]  →  [move_to_archive]
    [rename]  →  [move_to_archive]
    [delete]
          │
          ▼
   Archive Folder  +  Logs Folder
```

If any step fails, the file is moved to **quarantine** — it is never deleted and never re-processed.

---

## Project Structure

```
file-automation/
├── config/
│   └── config.json              # All rules, paths, and settings — edit this file only
├── src/
│   ├── main.py                  # Entry point — starts everything
│   ├── watcher.py               # Real-time directory monitoring (watchdog)
│   ├── processor.py             # Pipeline orchestrator + quarantine logic
│   ├── file_operations.py       # Atomic operations: rename, compress, move, delete
│   ├── rule_engine.py           # Config-driven rule matching engine
│   └── logger_setup.py         # Daily rotating log configuration
├── service/
│   ├── file-automation.service  # systemd unit file (Linux)
│   └── com.fileautomation.plist # launchd agent plist (macOS)
├── tests/
│   ├── test_file_operations.py  # 15 tests for atomic operations
│   ├── test_rule_engine.py      # 15 tests for rule matching
│   └── test_processor.py       # 7 tests for pipeline sequencing
├── install_service.py           # One-command service installer (Linux/macOS/Windows)
├── test_live.py                 # Live end-to-end test script
├── requirements.txt
├── LICENSE
└── README.md
```

---

## Installation

### Prerequisites

- Python **3.9 or higher**
- pip

### Windows

```bat
REM 1. Clone the repository
git clone https://github.com/aarrtH8/file-automation.git
cd file-automation

REM 2. Create a virtual environment
python -m venv venv
venv\Scripts\activate

REM 3. Install dependencies
pip install -r requirements.txt
```

### macOS / Linux

```bash
# 1. Clone the repository
git clone https://github.com/aarrtH8/file-automation.git
cd file-automation

# 2. Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

### Verify installation

```bash
python src/main.py --help
```

Expected output:
```
usage: main.py [-h] [--config CONFIG]

File Automation System — monitors directories and applies rules.

options:
  --config CONFIG  Path to the configuration file (JSON or YAML). Default: config/config.json
```

---

## Configuration Reference

All behavior is controlled by `config/config.json`. **No Python files need to be edited.**

### Full config.json structure

```json
{
  "version": "1.0",
  "settings": { ... },
  "paths": { ... },
  "rename": { ... },
  "temp_patterns": [ ... ],
  "rules": [ ... ]
}
```

---

### `settings`

```json
"settings": {
    "log_level": "INFO",
    "max_worker_threads": 4,
    "file_stability_check_interval_ms": 100,
    "file_stability_max_retries": 3
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `log_level` | string | `"INFO"` | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `max_worker_threads` | int | `4` | Max parallel files processed simultaneously |
| `file_stability_check_interval_ms` | int | `100` | Milliseconds between file-size checks (slow-write detection) |
| `file_stability_max_retries` | int | `3` | Number of stability checks before giving up |

> **Tip:** Set `log_level` to `"DEBUG"` to see rule matching details in the logs.

---

### `paths`

```json
"paths": {
    "watch_dirs": ["C:/File_Automation/Input"],
    "archive_dir": "C:/File_Automation/Archive",
    "logs_dir":    "C:/File_Automation/Logs",
    "quarantine_dir": "C:/File_Automation/Archive/quarantine"
}
```

| Field | Description |
|---|---|
| `watch_dirs` | **List** of folders to monitor. Add multiple entries for multi-directory support. |
| `archive_dir` | Destination for all successfully processed files. |
| `logs_dir` | Where daily log files are written. |
| `quarantine_dir` | Where files that failed processing are isolated for review. |

> All directories are **created automatically** at startup if they do not exist.

**Linux/macOS example:**
```json
"watch_dirs": ["/home/user/file_automation/input"]
```

**Multiple directories:**
```json
"watch_dirs": [
    "C:/File_Automation/Input",
    "C:/Users/John/Downloads/ToProcess"
]
```

---

### `rename`

```json
"rename": {
    "enabled": true,
    "timestamp_format": "%Y%m%d_%H%M%S",
    "separator": "_"
}
```

| Field | Description |
|---|---|
| `enabled` | Set to `false` to skip renaming entirely (files keep their original name) |
| `timestamp_format` | Python `strftime` format string |
| `separator` | Character placed between the original name and the timestamp |

**Result:** `report.pdf` → `report_20260411_143210.pdf`

Common timestamp formats:
| Format | Result |
|---|---|
| `%Y%m%d_%H%M%S` | `20260411_143210` (default) |
| `%Y-%m-%d` | `2026-04-11` |
| `%d%m%Y_%H%M` | `11042026_1432` |

---

### `temp_patterns`

```json
"temp_patterns": ["~*", "*.tmp", "*.bak", "desktop.ini", "Thumbs.db", ".DS_Store"]
```

Files matching any of these **glob patterns** are deleted immediately, before any rule is checked.

| Pattern | Matches |
|---|---|
| `~*` | `~lockfile`, `~$report.docx` (Office temp files) |
| `*.tmp` | `upload.tmp`, `data.tmp` |
| `*.bak` | `config.bak`, `file.bak` |
| `Thumbs.db` | Windows thumbnail cache |
| `.DS_Store` | macOS folder metadata |
| `*_copy` | Any file ending with `_copy` |

---

### `rules`

```json
"rules": [
    {
        "id": "rule_pdf",
        "description": "PDF files: rename, compress, archive",
        "priority": 10,
        "match_extensions": [".pdf"],
        "match_name_pattern": null,
        "actions": ["rename", "compress", "move_to_archive"]
    }
]
```

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique identifier shown in logs |
| `description` | string | Human-readable note (not used by the engine) |
| `priority` | int | Lower number = evaluated first. First match wins. |
| `match_extensions` | list | Case-insensitive file extensions (include the dot: `".pdf"`) |
| `match_name_pattern` | string or null | Optional glob pattern for the filename (e.g. `"invoice_*"`) |
| `actions` | list | **Ordered** list of operations to execute |

#### Available actions

| Action | Description |
|---|---|
| `rename` | Renames file using the `rename` config block format |
| `compress` | Compresses file into a `.zip` archive (file is removed after zipping) |
| `move_to_archive` | Moves the file to `archive_dir` |
| `delete` | Deletes the file. Pipeline stops immediately after. |

#### Rule matching logic

1. If the filename matches any `temp_patterns` → **delete**, no rule checked
2. Rules are evaluated in ascending `priority` order
3. A file matches a rule if **both** conditions are true:
   - Its extension is in `match_extensions`
   - Its name matches `match_name_pattern` (if set; `null` means always match)
4. **First matching rule wins** — only one rule is applied per file
5. If no rule matches → file is left untouched and logged as skipped

---

## Running Manually

> For production use, see [Running as a Background Service](#running-as-a-background-service).

```bash
# Activate your virtual environment first
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Start with default config
python src/main.py

# Start with a custom config path
python src/main.py --config /path/to/custom_config.json

# YAML config is also supported (requires pyyaml — already in requirements.txt)
python src/main.py --config config/config.yaml
```

Press **Ctrl+C** to stop. The system shuts down cleanly — no files are lost.

### What you will see

```
2026-04-13 14:32:08 | INFO     | ============================================================
2026-04-13 14:32:08 | INFO     | File Automation System  |  config: config/config.json
2026-04-13 14:32:08 | INFO     | ============================================================
2026-04-13 14:32:08 | INFO     | Watching : C:/File_Automation/Input
2026-04-13 14:32:08 | INFO     | File Automation System running. Press Ctrl+C to stop.

# When a file is dropped into Input/:
2026-04-13 14:32:15 | INFO     | Detected : 'report.pdf'
2026-04-13 14:32:15 | INFO     | Renamed  : 'report.pdf'  ->  'report_20260413_143215.pdf'
2026-04-13 14:32:15 | INFO     | Compressed: 'report_20260413_143215.pdf'  ->  'report_20260413_143215.zip'
2026-04-13 14:32:15 | INFO     | Moved    : 'report_20260413_143215.zip'  ->  C:/File_Automation/Archive/
2026-04-13 14:32:15 | INFO     | Complete : 'report.pdf'  (all actions done)
```

---

## Running as a Background Service

The `install_service.py` script handles everything automatically — it detects your OS and installs the appropriate service.

### Install

```bash
# Linux (requires sudo — installs a systemd service)
sudo python install_service.py

# macOS (no sudo needed — installs a launchd user agent)
python install_service.py

# Windows (run as Administrator — creates a Task Scheduler task)
python install_service.py
```

What the installer does:
1. Verifies config and dependencies
2. Writes the correct service file for your OS
3. Enables it to start at boot/login
4. Starts it immediately

### Manage the service

```bash
# Check status
python install_service.py --status

# Uninstall
sudo python install_service.py --remove   # Linux
python install_service.py --remove        # macOS / Windows
```

### OS-specific management commands

| Action | Linux | macOS | Windows |
|---|---|---|---|
| Stop | `sudo systemctl stop file-automation` | `launchctl unload ~/Library/LaunchAgents/com.fileautomation.plist` | `schtasks /End /TN FileAutomationSystem` |
| Start | `sudo systemctl start file-automation` | `launchctl load ~/Library/LaunchAgents/com.fileautomation.plist` | `schtasks /Run /TN FileAutomationSystem` |
| Live logs | `sudo journalctl -u file-automation -f` | `tail -f service/launchd_stdout.log` | `type Logs\automation.log` |

---

## Logging

Log files are stored in the configured `logs_dir` and **rotate automatically at midnight**.

```
Logs/
├── automation.log                  # Today's log (active)
├── automation.log.2026_04_12       # Yesterday
├── automation.log.2026_04_11       # 2 days ago
└── ...                             # Up to 30 days kept
```

### Log format

```
YYYY-MM-DD HH:MM:SS | LEVEL    | Message
```

### Log levels

| Level | What it shows |
|---|---|
| `INFO` | Every file action (default) |
| `DEBUG` | + rule matching details, stability check results |
| `WARNING` | File disappeared, unknown action, quarantine |
| `ERROR` | Full traceback when an operation fails |

### Reading logs

```bash
# Live tail
tail -f C:/File_Automation/Logs/automation.log

# Search for errors
grep "ERROR" C:/File_Automation/Logs/automation.log

# See all processed files for today
grep "Complete" C:/File_Automation/Logs/automation.log

# See quarantined files
grep "Quarantined" C:/File_Automation/Logs/automation.log
```

---

## Testing

### Live end-to-end test

Spins up a real watcher, drops 9 test files, verifies results, and cleans up. No configuration needed.

```bash
python test_live.py
```

Expected output:
```
FILE                      EXPECTED        RESULT
invoice.pdf               archived_zip    ✔  renamed + zipped → invoice_20260413_195351.zip
photo.jpg                 archived_raw    ✔  renamed + moved  → photo_20260413_195351.jpg
notes.txt                 archived_zip    ✔  renamed + zipped → notes_20260413_195351.zip
report.docx               archived_zip    ✔  renamed + zipped → report_20260413_195351.zip
~lockfile                 deleted         ✔  deleted correctly
cache.tmp                 deleted         ✔  deleted correctly
backup.bak                deleted         ✔  deleted correctly
Thumbs.db                 deleted         ✔  deleted correctly
data.xyz                  untouched       ✔  left untouched in Input/ (no rule matched)

All 9/9 tests passed.
```

### Unit tests

```bash
pip install pytest
pytest tests/ -v
```

Expected: `36 passed`

Unit tests use temporary directories — they never touch your actual `Input/`, `Archive/`, or `Logs/` folders.

---

## Error Handling & Quarantine

| Scenario | Behavior |
|---|---|
| File disappears before processing | Warning logged, skipped silently |
| File still being written (large file) | Stability check polls until size is stable |
| Operation fails (permissions, disk full) | File moved to `quarantine_dir`, full error traceback logged |
| No rule matches | Info logged, file left untouched |
| Config file not found | Error to stderr, process exits with code 1 |
| Invalid JSON in config | Error to stderr, process exits with code 1 |
| Archive / quarantine dir missing | Created automatically at startup |
| Multiple files arrive simultaneously | Thread pool handles them in parallel |

### The quarantine folder

`Archive/quarantine/` is the safety net. Files end up there when something unexpected happens mid-pipeline. They are **never deleted automatically**.

To review quarantined files:
1. Check the logs for the corresponding error and traceback
2. Fix the root cause (permissions, disk space, etc.)
3. Manually move the file back to `Input/` to reprocess it

---

## Adding New Rules

Edit `config/config.json` only — no code changes required.

### Example: process `.docx` files differently from `.txt`

```json
{
    "id": "rule_word",
    "description": "Word documents: rename, compress, archive",
    "priority": 25,
    "match_extensions": [".docx", ".doc"],
    "match_name_pattern": null,
    "actions": ["rename", "compress", "move_to_archive"]
}
```

### Example: match files by name pattern (invoices only)

```json
{
    "id": "rule_invoice_pdf",
    "description": "Invoice PDFs (name starts with 'invoice_'): special handling",
    "priority": 5,
    "match_extensions": [".pdf"],
    "match_name_pattern": "invoice_*",
    "actions": ["rename", "compress", "move_to_archive"]
}
```

> This rule (priority 5) will match `invoice_001.pdf` before the general `rule_pdf` (priority 10).
> Regular PDFs not starting with `invoice_` will fall through to `rule_pdf`.

### Example: delete all `.log` files

```json
{
    "id": "rule_delete_logs",
    "description": "Delete all log files",
    "priority": 50,
    "match_extensions": [".log"],
    "match_name_pattern": null,
    "actions": ["delete"]
}
```

---

## Troubleshooting

### System starts but no files are processed

- Verify the `watch_dirs` path in `config.json` is exactly correct (check for typos, wrong slashes)
- Make sure the directory **exists** (it is created only if the path itself is valid)
- On Windows, use forward slashes: `"C:/File_Automation/Input"` not `"C:\\File_Automation\\Input"`
- Drop a test file and watch the console for `Detected :` output

### `ModuleNotFoundError: No module named 'watchdog'`

The virtual environment is not activated, or dependencies were not installed:
```bash
# Activate first
venv\Scripts\activate         # Windows
source venv/bin/activate      # macOS/Linux

# Then install
pip install -r requirements.txt
```

### Files are detected but go to quarantine

Check the logs for the error traceback:
```bash
grep -A 10 "Quarantined" Logs/automation.log
```

Common causes:
- **Permissions**: the process does not have write access to `Archive/`
- **Disk full**: no space left to move/compress the file
- **File locked**: another process is holding the file open (antivirus, sync tools)

### Files are processed twice

This can happen if both the `Input/` and `Archive/` folders are on the same watched path. Verify that `archive_dir` is **not inside** any `watch_dirs` entry, or add it to `ignored_dirs` logic.

### `RuntimeError: Logger not initialized`

`get_logger()` was called before `setup_logging()`. This should not happen in normal usage. If you are importing modules directly in a script, call `setup_logging()` first.

### Large files are being processed before they finish copying

Increase the stability check retries in config:
```json
"settings": {
    "file_stability_check_interval_ms": 200,
    "file_stability_max_retries": 10
}
```

### Python version error

```
SyntaxError: ...
```

Check your Python version:
```bash
python --version
```
Python **3.9 or higher** is required.

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make changes and add tests
4. Run the test suite: `pytest tests/ -v`
5. Commit: `git commit -m "Add: my feature"`
6. Push and open a Pull Request

All pull requests must pass the full 36-test suite before merging.

---

## License

MIT License — see [LICENSE](LICENSE) for full text.

Free to use, modify, and distribute for personal and commercial projects.
