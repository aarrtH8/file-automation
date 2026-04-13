"""
main.py
-------
Entry point for the File Automation System.

Responsibilities:
  - Parse the --config CLI argument (default: config/config.json).
  - Load and validate the configuration file (JSON or YAML).
  - Resolve all configured paths and create missing directories.
  - Initialize logging, RuleEngine, FileProcessor, and DirectoryWatcher.
  - Hand control to the watcher's blocking start() loop.

Usage:
    python src/main.py
    python src/main.py --config /path/to/custom_config.json
    python src/main.py --config /path/to/custom_config.yaml
"""

import argparse
import json
import sys
from pathlib import Path


def _load_config(config_path: Path) -> dict:
    """
    Load configuration from a JSON or YAML file.

    Args:
        config_path: Path to the config file.

    Returns:
        Parsed configuration dictionary.

    Raises:
        SystemExit: If the file cannot be parsed or found.
    """
    if not config_path.exists():
        print(f"[ERROR] Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    suffix = config_path.suffix.lower()

    try:
        if suffix in (".yaml", ".yml"):
            try:
                import yaml
            except ImportError:
                print(
                    "[ERROR] pyyaml is required for YAML config files.\n"
                    "        Run: pip install pyyaml",
                    file=sys.stderr,
                )
                sys.exit(1)
            with config_path.open("r", encoding="utf-8") as fh:
                return yaml.safe_load(fh)
        else:
            with config_path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
    except (json.JSONDecodeError, Exception) as exc:
        print(f"[ERROR] Failed to parse config file '{config_path}': {exc}", file=sys.stderr)
        sys.exit(1)


def _resolve_paths(config: dict) -> None:
    """
    Expand and resolve all path strings in the config in-place.

    Handles:
      - ~ (home directory expansion)
      - Relative paths (resolved from cwd)
      - Windows-style C:/... paths via pathlib
    """
    paths_cfg = config.get("paths", {})

    for key, value in paths_cfg.items():
        if key == "watch_dirs":
            paths_cfg[key] = [
                str(Path(d).expanduser().resolve()) for d in value
            ]
        elif isinstance(value, str):
            paths_cfg[key] = str(Path(value).expanduser().resolve())


def _ensure_directories(config: dict) -> None:
    """Create all required directories if they do not exist."""
    paths_cfg = config.get("paths", {})

    dirs_to_create = [
        paths_cfg.get("archive_dir"),
        paths_cfg.get("logs_dir"),
        paths_cfg.get("quarantine_dir"),
    ]

    for d in dirs_to_create:
        if d:
            Path(d).mkdir(parents=True, exist_ok=True)

    for watch_dir in paths_cfg.get("watch_dirs", []):
        Path(watch_dir).mkdir(parents=True, exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="File Automation System — monitors directories and applies rules."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent.parent / "config" / "config.json",
        help="Path to the configuration file (JSON or YAML). "
             "Default: config/config.json",
    )
    args = parser.parse_args()

    config = _load_config(args.config)
    _resolve_paths(config)
    _ensure_directories(config)

    # Import here so that path resolution happens before module-level code runs.
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent))

    from logger_setup import setup_logging, get_logger
    from rule_engine import RuleEngine
    from processor import FileProcessor
    from watcher import DirectoryWatcher

    paths_cfg = config.get("paths", {})
    log_level = config.get("settings", {}).get("log_level", "INFO")
    logs_dir = Path(paths_cfg.get("logs_dir", "Logs"))

    setup_logging(logs_dir=logs_dir, log_level=log_level)
    logger = get_logger()

    logger.info("=" * 60)
    logger.info("File Automation System  |  config: %s", args.config)
    logger.info("=" * 60)

    rule_engine = RuleEngine(config)
    processor = FileProcessor(config, rule_engine)
    watcher = DirectoryWatcher(config, processor)

    watcher.start()


if __name__ == "__main__":
    # Ensure src/ is on the path when running as python src/main.py
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).parent))

    main()
