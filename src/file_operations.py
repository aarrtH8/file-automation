"""
file_operations.py
------------------
Atomic file operation primitives for the File Automation System.

All functions are stateless and operate on pathlib.Path objects.
Each function logs its own action and raises FileOperationError on failure
instead of swallowing exceptions.

Operations:
  - rename_file    : Apply timestamp-based naming convention.
  - compress_file  : Wrap a single file in a ZIP archive.
  - move_file      : Move a file to a destination directory (collision-safe).
  - delete_file    : Remove a file from the filesystem.
"""

from __future__ import annotations

import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from logger_setup import get_logger


class FileOperationError(Exception):
    """Raised when an atomic file operation fails."""


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def rename_file(src: Path, rename_cfg: dict) -> Path:
    """
    Rename a file using the configured timestamp convention.

    New name format:  <stem><separator><YYYYMMDD><separator><HHMMSS><suffix>
    Example:          report.pdf  ->  report_20260411_143210.pdf

    Args:
        src:        Source file path.
        rename_cfg: Rename config block from config.json.

    Returns:
        Path to the renamed file (same parent directory).

    Raises:
        FileOperationError: If the file cannot be renamed.
    """
    logger = get_logger()

    if not rename_cfg.get("enabled", True):
        logger.debug("Rename disabled by config. Skipping rename for '%s'.", src.name)
        return src

    separator: str = rename_cfg.get("separator", "_")
    ts_format: str = rename_cfg.get("timestamp_format", "%Y%m%d_%H%M%S")
    timestamp: str = datetime.now().strftime(ts_format)

    new_name = f"{src.stem}{separator}{timestamp}{src.suffix}"
    dest = src.parent / new_name

    dest = _resolve_collision(dest)

    try:
        src.rename(dest)
        logger.info("Renamed  : '%s'  ->  '%s'", src.name, dest.name)
        return dest
    except OSError as exc:
        raise FileOperationError(
            f"Failed to rename '{src}' to '{dest}': {exc}"
        ) from exc


def compress_file(src: Path, dest_dir: Path) -> Path:
    """
    Compress a single file into a ZIP archive placed in dest_dir.

    The ZIP file is named after the source file (stem + .zip).
    The ZIP internal entry preserves the renamed filename.

    Args:
        src:      File to compress (should already be renamed).
        dest_dir: Directory where the ZIP will be created.

    Returns:
        Path to the created ZIP file.

    Raises:
        FileOperationError: If compression fails.
    """
    logger = get_logger()
    dest_dir.mkdir(parents=True, exist_ok=True)

    zip_path = dest_dir / f"{src.stem}.zip"
    zip_path = _resolve_collision(zip_path)

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(src, arcname=src.name)
        logger.info("Compressed: '%s'  ->  '%s'", src.name, zip_path.name)
        src.unlink()
        logger.debug("Removed original after compression: '%s'", src.name)
        return zip_path
    except (OSError, zipfile.BadZipFile) as exc:
        if zip_path.exists():
            zip_path.unlink(missing_ok=True)
        raise FileOperationError(
            f"Failed to compress '{src}' into '{zip_path}': {exc}"
        ) from exc


def move_file(src: Path, dest_dir: Path) -> Path:
    """
    Move a file to dest_dir (collision-safe).

    If a file with the same name already exists in dest_dir, a numeric
    suffix is appended:  report_20260411_143210_1.zip

    Args:
        src:      File to move.
        dest_dir: Destination directory.

    Returns:
        Path to the moved file in dest_dir.

    Raises:
        FileOperationError: If the move fails.
    """
    logger = get_logger()
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest = dest_dir / src.name
    dest = _resolve_collision(dest)

    try:
        shutil.move(str(src), str(dest))
        logger.info("Moved    : '%s'  ->  '%s'", src.name, dest)
        return dest
    except (OSError, shutil.Error) as exc:
        raise FileOperationError(
            f"Failed to move '{src}' to '{dest}': {exc}"
        ) from exc


def delete_file(src: Path) -> None:
    """
    Delete a file from the filesystem.

    Args:
        src: File to delete.

    Raises:
        FileOperationError: If the file cannot be deleted.
    """
    logger = get_logger()
    try:
        src.unlink()
        logger.info("Deleted  : '%s'", src)
    except OSError as exc:
        raise FileOperationError(f"Failed to delete '{src}': {exc}") from exc


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _resolve_collision(path: Path) -> Path:
    """
    Return a collision-free path by appending a counter suffix if needed.

    Example:  report.zip  ->  report_1.zip  ->  report_2.zip  ...
    """
    if not path.exists():
        return path

    counter = 1
    while True:
        candidate = path.parent / f"{path.stem}_{counter}{path.suffix}"
        if not candidate.exists():
            return candidate
        counter += 1
