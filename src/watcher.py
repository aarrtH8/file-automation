"""
watcher.py
----------
Real-time directory monitoring using the watchdog library.

Responsibilities:
  - Register one FileSystemEventHandler per watched directory.
  - Filter out directory events, archive/log feedback loops, and temp editor files.
  - Dispatch file processing to a ThreadPoolExecutor to keep event delivery
    non-blocking and meet the 2-second latency requirement even under load.
  - Support multiple watch directories via config.

Usage (called by main.py):
    watcher = DirectoryWatcher(config, processor)
    watcher.start()   # blocks until KeyboardInterrupt
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from watchdog.events import FileCreatedEvent, FileMovedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from logger_setup import get_logger
from processor import FileProcessor


class _FileEventHandler(FileSystemEventHandler):
    """Watchdog event handler — dispatches new/moved files to the processor."""

    def __init__(
        self,
        processor: FileProcessor,
        executor: ThreadPoolExecutor,
        ignored_dirs: list[Path],
    ) -> None:
        super().__init__()
        self._processor = processor
        self._executor = executor
        self._ignored_dirs = ignored_dirs
        self._logger = get_logger()

    # ------------------------------------------------------------------
    # Watchdog callbacks
    # ------------------------------------------------------------------

    def on_created(self, event: FileCreatedEvent) -> None:
        if event.is_directory:
            return
        self._dispatch(Path(event.src_path))

    def on_moved(self, event: FileMovedEvent) -> None:
        """
        Some editors and OS copy utilities write to a temp path then rename
        (atomic write). The final rename fires a FileMovedEvent.
        """
        if event.is_directory:
            return
        self._dispatch(Path(event.dest_path))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _dispatch(self, filepath: Path) -> None:
        """Submit a file to the thread pool if it passes all filters."""
        if self._is_in_ignored_dir(filepath):
            self._logger.debug(
                "Ignored event for '%s' (inside monitored-output directory).",
                filepath,
            )
            return

        self._logger.debug("Dispatching '%s' to processor.", filepath.name)
        self._executor.submit(self._safe_process, filepath)

    def _safe_process(self, filepath: Path) -> None:
        """Wrap processor.process() so thread pool workers never raise."""
        try:
            self._processor.process(filepath)
        except Exception as exc:
            self._logger.exception(
                "Unhandled exception in worker for '%s': %s", filepath.name, exc
            )

    def _is_in_ignored_dir(self, filepath: Path) -> bool:
        """Return True if the file resides inside any ignored output directory."""
        resolved = filepath.resolve()
        for ignored in self._ignored_dirs:
            try:
                resolved.relative_to(ignored.resolve())
                return True
            except ValueError:
                continue
        return False


class DirectoryWatcher:
    """Manages watchdog observers for one or more watched directories."""

    def __init__(self, config: dict, processor: FileProcessor) -> None:
        """
        Args:
            config:    Full parsed configuration dictionary.
            processor: Initialized FileProcessor instance.
        """
        self._config = config
        self._processor = processor
        self._logger = get_logger()

        settings = config.get("settings", {})
        max_workers: int = settings.get("max_worker_threads", 4)
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

        paths = config.get("paths", {})
        self._watch_dirs: list[Path] = [
            Path(d) for d in paths.get("watch_dirs", [])
        ]
        self._ignored_dirs: list[Path] = [
            Path(paths.get("archive_dir", "Archive")),
            Path(paths.get("logs_dir", "Logs")),
            Path(paths.get("quarantine_dir", "Archive/quarantine")),
        ]

    def start(self) -> None:
        """
        Start watching all configured directories.

        Blocks until a KeyboardInterrupt (Ctrl+C) is received,
        then shuts down cleanly.
        """
        observer = Observer()
        handler = _FileEventHandler(
            processor=self._processor,
            executor=self._executor,
            ignored_dirs=self._ignored_dirs,
        )

        if not self._watch_dirs:
            self._logger.error("No watch_dirs configured. Nothing to monitor.")
            return

        for watch_dir in self._watch_dirs:
            if not watch_dir.exists():
                self._logger.warning(
                    "Watch directory '%s' does not exist. Creating it.", watch_dir
                )
                watch_dir.mkdir(parents=True, exist_ok=True)

            observer.schedule(handler, str(watch_dir), recursive=False)
            self._logger.info("Watching : %s", watch_dir)

        observer.start()
        self._logger.info(
            "File Automation System running. Press Ctrl+C to stop."
        )

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self._logger.info("Shutdown signal received. Stopping...")
        finally:
            observer.stop()
            observer.join()
            self._executor.shutdown(wait=True)
            self._logger.info("File Automation System stopped cleanly.")
