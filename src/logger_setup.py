"""
logger_setup.py
---------------
Centralized logging configuration for the File Automation System.

Creates a named logger with two handlers:
  - TimedRotatingFileHandler: daily log files in the configured logs directory.
  - StreamHandler: real-time console output.

Usage:
    from logger_setup import get_logger
    logger = get_logger()
    logger.info("Processing started")
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

_logger: Optional[logging.Logger] = None


def setup_logging(logs_dir: Path, log_level: str = "INFO") -> logging.Logger:
    """
    Initialize the application logger.

    Args:
        logs_dir: Directory where daily log files are stored.
        log_level: Logging level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).

    Returns:
        Configured Logger instance.
    """
    global _logger

    logs_dir.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, log_level.upper(), logging.INFO)

    logger = logging.getLogger("file_automation")
    logger.setLevel(level)

    if logger.handlers:
        logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    log_file_path = logs_dir / "automation.log"
    file_handler = TimedRotatingFileHandler(
        filename=log_file_path,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
        utc=False,
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    file_handler.suffix = "%Y_%m_%d"
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    _logger = logger
    return logger


def get_logger() -> logging.Logger:
    """
    Return the application logger.

    Raises:
        RuntimeError: If setup_logging() has not been called yet.
    """
    if _logger is None:
        raise RuntimeError(
            "Logger not initialized. Call setup_logging() before get_logger()."
        )
    return _logger
