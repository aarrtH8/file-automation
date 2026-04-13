"""
processor.py
------------
Core file processing pipeline orchestrator.

Responsibilities:
  - Wait for a newly detected file to finish writing (stability check).
  - Retrieve the action sequence from the RuleEngine.
  - Execute each action in order via file_operations primitives.
  - On failure, quarantine the file and log the full error — never crash.

The processor is called from watcher.py in a thread pool worker,
so all logging must be thread-safe (Python's logging module is).
"""

from __future__ import annotations

import time
import traceback
from pathlib import Path

import file_operations as ops
from logger_setup import get_logger
from rule_engine import RuleEngine


class FileProcessor:
    """Runs the rename → compress → move (or delete) pipeline for a single file."""

    def __init__(self, config: dict, rule_engine: RuleEngine) -> None:
        """
        Args:
            config:      Full parsed configuration dictionary.
            rule_engine: Initialized RuleEngine instance.
        """
        self._config = config
        self._rule_engine = rule_engine
        self._logger = get_logger()

        settings = config.get("settings", {})
        self._stability_interval_ms: int = settings.get(
            "file_stability_check_interval_ms", 100
        )
        self._stability_max_retries: int = settings.get(
            "file_stability_max_retries", 3
        )

        paths = config.get("paths", {})
        self._archive_dir = Path(paths.get("archive_dir", "Archive"))
        self._quarantine_dir = Path(paths.get("quarantine_dir", "Archive/quarantine"))
        self._rename_cfg: dict = config.get("rename", {})

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, filepath: Path) -> None:
        """
        Full processing pipeline for a single file.

        This method never raises. All errors are caught, logged, and the
        file is moved to quarantine to avoid blocking the queue.

        Args:
            filepath: Absolute path to the file to process.
        """
        self._logger.info("Detected : '%s'", filepath.name)

        try:
            if not self._wait_for_stable(filepath):
                self._logger.warning(
                    "File '%s' did not stabilize in time. Skipping.", filepath.name
                )
                return

            if not filepath.exists():
                self._logger.warning(
                    "File '%s' disappeared before processing. Skipping.", filepath.name
                )
                return

            actions = self._rule_engine.get_actions_for_file(filepath)

            if not actions:
                self._logger.info(
                    "No rule matched '%s'. File left untouched.", filepath.name
                )
                return

            self._logger.debug(
                "Actions for '%s': %s", filepath.name, actions
            )

            self._execute_pipeline(filepath, actions)

        except Exception:
            self._logger.error(
                "Unexpected error processing '%s':\n%s",
                filepath.name,
                traceback.format_exc(),
            )
            self._quarantine(filepath)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _wait_for_stable(self, filepath: Path) -> bool:
        """
        Poll the file size until it remains unchanged for two consecutive reads.

        Returns True if the file stabilized within the retry budget, False otherwise.
        The budget = stability_max_retries * stability_check_interval_ms.
        """
        interval = self._stability_interval_ms / 1000.0
        prev_size = -1
        stable_count = 0

        for _ in range(self._stability_max_retries * 2):
            try:
                current_size = filepath.stat().st_size
            except FileNotFoundError:
                return False

            if current_size == prev_size:
                stable_count += 1
                if stable_count >= 2:
                    return True
            else:
                stable_count = 0

            prev_size = current_size
            time.sleep(interval)

        return stable_count >= 2

    def _execute_pipeline(self, filepath: Path, actions: list[str]) -> None:
        """
        Execute each action in sequence, tracking the current file path.

        The path is updated after each action because rename and compress
        produce a different output file.

        Args:
            filepath: Starting file path.
            actions:  Ordered list of action strings from the rule engine.
        """
        current_path = filepath

        for action in actions:
            if action == "rename":
                current_path = ops.rename_file(current_path, self._rename_cfg)

            elif action == "compress":
                # Compress directly into archive_dir so the ZIP is never
                # created inside the watched Input/ folder, which would
                # trigger a spurious second watchdog event.
                current_path = ops.compress_file(current_path, self._archive_dir)

            elif action == "move_to_archive":
                # If a prior compress already landed the file in archive_dir,
                # skip the move to avoid a no-op or collision.
                if current_path.parent.resolve() == self._archive_dir.resolve():
                    self._logger.debug(
                        "File '%s' is already in archive_dir — skipping move.",
                        current_path.name,
                    )
                else:
                    current_path = ops.move_file(current_path, self._archive_dir)

            elif action == "delete":
                ops.delete_file(current_path)
                return  # No further actions after deletion.

            else:
                self._logger.warning(
                    "Unknown action '%s' for file '%s'. Skipping action.",
                    action,
                    filepath.name,
                )

        self._logger.info("Complete : '%s'  (all actions done)", filepath.name)

    def _quarantine(self, filepath: Path) -> None:
        """
        Move a failed file to the quarantine directory.

        Quarantine prevents re-processing loops and preserves data for review.
        """
        if not filepath.exists():
            return
        try:
            ops.move_file(filepath, self._quarantine_dir)
            self._logger.warning(
                "Quarantined: '%s' moved to '%s'.", filepath.name, self._quarantine_dir
            )
        except ops.FileOperationError:
            self._logger.error(
                "Could not quarantine '%s'. File may still be in source directory.",
                filepath.name,
            )
