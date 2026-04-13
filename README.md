# File Automation System

A lightweight, config-driven Python automation system that monitors directories in real time, applies intelligent rules, and executes automated file operations — rename, compress, archive, and delete — without manual intervention.

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

---

## Project Structure

```
file-automation/
├── config/
│   └── config.json          # All rules, paths, and settings
├── src/
│   ├── main.py              # Entry point
│   ├── watcher.py           # Directory monitoring
│   ├── processor.py         # Pipeline orchestrator
│   ├── file_operations.py   # Atomic file operations
│   ├── rule_engine.py       # Rule matching engine
│   └── logger_setup.py     # Logging configuration
├── tests/
│   ├── test_file_operations.py
│   ├── test_rule_engine.py
│   └── test_processor.py
├── requirements.txt
└── README.md
```

---

## Installation

### Prerequisites

- Python 3.10 or higher
- pip

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/aarrtH8/file-automation.git
cd file-automation

# 2. (Recommended) Create a virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Configuration

All behavior is controlled by `config/config.json`. No Python files need to be edited.

### Paths

```json
"paths": {
    "watch_dirs": ["C:/File_Automation/Input"],
    "archive_dir": "C:/File_Automation/Archive",
    "logs_dir":    "C:/File_Automation/Logs",
    "quarantine_dir": "C:/File_Automation/Archive/quarantine"
}
```

- **`watch_dirs`** — list of folders to monitor (add more for multi-directory support)
- **`archive_dir`** — where processed files end up
- **`logs_dir`** — where daily log files are written
- **`quarantine_dir`** — where files that failed processing are isolated

> All directories are created automatically at startup if they do not exist.

### Rules

Each rule in the `rules` array defines which files to match and what to do with them:

```json
{
    "id": "rule_pdf",
    "description": "PDFs: rename, compress, archive",
    "priority": 10,
    "match_extensions": [".pdf"],
    "match_name_pattern": null,
    "actions": ["rename", "compress", "move_to_archive"]
}
```

| Field | Description |
|---|---|
| `id` | Unique identifier (for logging) |
| `priority` | Lower number = evaluated first |
| `match_extensions` | List of file extensions (case-insensitive) |
| `match_name_pattern` | Optional glob pattern for the filename (e.g. `"invoice_*"`) |
| `actions` | Ordered list of operations to perform |

#### Available Actions

| Action | Description |
|---|---|
| `rename` | Renames file to `<name>_<YYYYMMDD>_<HHMMSS>.<ext>` |
| `compress` | Wraps the file in a ZIP archive |
| `move_to_archive` | Moves the file to `archive_dir` |
| `delete` | Deletes the file permanently |

### Temp Patterns

Files matching any temp pattern are **deleted immediately**, before rules are evaluated:

```json
"temp_patterns": ["~*", "*.tmp", "*.bak", "desktop.ini", "Thumbs.db"]
```

Standard glob syntax applies (`*` matches any characters, `?` matches one character).

### Rename Format

```json
"rename": {
    "enabled": true,
    "timestamp_format": "%Y%m%d_%H%M%S",
    "separator": "_"
}
```

Example: `report.pdf` → `report_20260411_143210.pdf`

---

## Execution

### Run manually

```bash
# From the project root
python src/main.py

# With a custom config path
python src/main.py --config /path/to/my_config.json

# YAML config is also supported (requires pyyaml)
python src/main.py --config config/config.yaml
```

Press **Ctrl+C** to stop. The system shuts down cleanly.

### Run as a background service

#### Linux — systemd

Create `/etc/systemd/system/file-automation.service`:

```ini
[Unit]
Description=File Automation System
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/file-automation
ExecStart=/path/to/venv/bin/python src/main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable file-automation
sudo systemctl start file-automation
sudo systemctl status file-automation
```

#### Linux — cron (on boot)

```bash
@reboot /path/to/venv/bin/python /path/to/file-automation/src/main.py >> /var/log/file-automation.log 2>&1
```

#### Windows — Task Scheduler

1. Open **Task Scheduler** → Create Basic Task
2. Trigger: **At startup** (or on login)
3. Action: **Start a program**
   - Program: `C:\path\to\venv\Scripts\python.exe`
   - Arguments: `src/main.py`
   - Start in: `C:\path\to\file-automation`
4. Check **Run whether user is logged on or not**

---

## Logging

Log files are stored in the configured `logs_dir` and rotate daily at midnight.

```
Logs/
├── automation.log                  # Current day (active)
├── automation.log.2026_04_12       # Yesterday's log
└── automation.log.2026_04_11       # Two days ago
```

The last 30 days of logs are kept automatically.

### Log format

```
2026-04-13 14:32:10 | INFO     | Detected : 'report.pdf'
2026-04-13 14:32:10 | INFO     | Renamed  : 'report.pdf'  ->  'report_20260413_143210.pdf'
2026-04-13 14:32:10 | INFO     | Compressed: 'report_20260413_143210.pdf'  ->  'report_20260413_143210.zip'
2026-04-13 14:32:10 | INFO     | Moved    : 'report_20260413_143210.zip'  ->  /File_Automation/Archive/...
2026-04-13 14:32:10 | INFO     | Complete : 'report.pdf'  (all actions done)
```

Set `"log_level": "DEBUG"` in config for verbose output including rule matching details.

---

## Running Tests

```bash
# Install test dependency
pip install pytest

# Run all tests from the project root
pytest tests/ -v
```

---

## Error Handling

| Scenario | Behavior |
|---|---|
| File disappears before processing | Logged as warning, skipped |
| File written slowly (large file) | Stability check polls until size is stable |
| Operation fails (e.g. permissions) | File moved to quarantine, error logged with traceback |
| No rule matches a file | Logged as info, file left untouched |
| Config file not found | Error printed to stderr, process exits with code 1 |
| Archive/Quarantine dir missing | Created automatically |

---

## Adding New Rules

Edit `config/config.json` — no code changes required:

```json
{
    "id": "rule_invoices",
    "description": "Invoice PDFs: rename, compress, archive",
    "priority": 5,
    "match_extensions": [".pdf"],
    "match_name_pattern": "invoice_*",
    "actions": ["rename", "compress", "move_to_archive"]
}
```

---

## License

MIT License. See `LICENSE` for details.
