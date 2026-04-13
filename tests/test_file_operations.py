"""
test_file_operations.py
-----------------------
Unit tests for file_operations.py.

All tests use tempfile.TemporaryDirectory so no real project paths are touched.
Tests verify:
  - Rename format produces the correct timestamp pattern.
  - Rename collision handling appends numeric suffixes.
  - Compress creates a valid ZIP containing the renamed file.
  - Move transfers the file and handles collisions in destination.
  - Delete removes the file.
"""

import sys
import zipfile
from pathlib import Path
from unittest.mock import patch
import tempfile
import os

# Ensure src/ is importable when tests are run from the project root.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import logging
import logger_setup as ls

# Bootstrap a test logger so modules that call get_logger() don't raise.
def _bootstrap_logger(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    ls.setup_logging(logs_dir=logs_dir, log_level="DEBUG")


import file_operations as ops
from datetime import datetime
import pytest


@pytest.fixture(autouse=True)
def tmp_workspace(tmp_path):
    _bootstrap_logger(tmp_path)
    return tmp_path


RENAME_CFG = {
    "enabled": True,
    "timestamp_format": "%Y%m%d_%H%M%S",
    "separator": "_",
}


# ------------------------------------------------------------------
# rename_file
# ------------------------------------------------------------------

class TestRenameFile:

    def test_basic_rename_format(self, tmp_path):
        src = tmp_path / "report.pdf"
        src.write_text("data")

        fixed_dt = datetime(2026, 4, 11, 14, 32, 10)
        with patch("file_operations.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_dt

            result = ops.rename_file(src, RENAME_CFG)

        assert result.name == "report_20260411_143210.pdf"
        assert result.exists()
        assert not src.exists()

    def test_preserves_extension(self, tmp_path):
        src = tmp_path / "image.JPEG"
        src.write_text("img")

        result = ops.rename_file(src, RENAME_CFG)
        assert result.suffix == ".JPEG"

    def test_rename_disabled(self, tmp_path):
        src = tmp_path / "file.txt"
        src.write_text("text")

        cfg = {**RENAME_CFG, "enabled": False}
        result = ops.rename_file(src, cfg)

        assert result == src
        assert result.exists()

    def test_collision_appends_counter(self, tmp_path):
        (tmp_path / "report_20260411_143210.pdf").write_text("existing")
        src = tmp_path / "report.pdf"
        src.write_text("new")

        fixed_dt = datetime(2026, 4, 11, 14, 32, 10)
        with patch("file_operations.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_dt

            result = ops.rename_file(src, RENAME_CFG)

        assert result.name == "report_20260411_143210_1.pdf"

    def test_nonexistent_source_raises(self, tmp_path):
        missing = tmp_path / "ghost.pdf"
        with pytest.raises(ops.FileOperationError):
            ops.rename_file(missing, RENAME_CFG)


# ------------------------------------------------------------------
# compress_file
# ------------------------------------------------------------------

class TestCompressFile:

    def test_creates_zip_in_dest_dir(self, tmp_path):
        src = tmp_path / "report_20260411.pdf"
        src.write_text("pdf content")
        dest_dir = tmp_path / "archive"

        zip_path = ops.compress_file(src, dest_dir)

        assert zip_path.suffix == ".zip"
        assert zip_path.parent == dest_dir
        assert zip_path.exists()

    def test_zip_contains_source_file(self, tmp_path):
        src = tmp_path / "report_20260411.pdf"
        src.write_bytes(b"binary pdf")
        dest_dir = tmp_path / "archive"

        zip_path = ops.compress_file(src, dest_dir)

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
        assert "report_20260411.pdf" in names

    def test_original_removed_after_compression(self, tmp_path):
        src = tmp_path / "report_20260411.pdf"
        src.write_text("content")
        dest_dir = tmp_path / "archive"

        ops.compress_file(src, dest_dir)

        assert not src.exists()

    def test_collision_in_dest(self, tmp_path):
        dest_dir = tmp_path / "archive"
        dest_dir.mkdir()
        (dest_dir / "report_20260411.zip").write_text("old zip")

        src = tmp_path / "report_20260411.pdf"
        src.write_text("content")

        zip_path = ops.compress_file(src, dest_dir)
        assert zip_path.name == "report_20260411_1.zip"

    def test_dest_dir_created_if_missing(self, tmp_path):
        src = tmp_path / "file.txt"
        src.write_text("hello")
        dest_dir = tmp_path / "deep" / "nested" / "archive"

        ops.compress_file(src, dest_dir)

        assert dest_dir.exists()


# ------------------------------------------------------------------
# move_file
# ------------------------------------------------------------------

class TestMoveFile:

    def test_moves_to_destination(self, tmp_path):
        src = tmp_path / "file.zip"
        src.write_text("zip")
        dest_dir = tmp_path / "archive"

        result = ops.move_file(src, dest_dir)

        assert result == dest_dir / "file.zip"
        assert result.exists()
        assert not src.exists()

    def test_collision_appends_counter(self, tmp_path):
        dest_dir = tmp_path / "archive"
        dest_dir.mkdir()
        (dest_dir / "file.zip").write_text("existing")

        src = tmp_path / "file.zip"
        src.write_text("new")

        result = ops.move_file(src, dest_dir)
        assert result.name == "file_1.zip"

    def test_dest_dir_created_if_missing(self, tmp_path):
        src = tmp_path / "file.txt"
        src.write_text("data")
        dest_dir = tmp_path / "new_dir"

        ops.move_file(src, dest_dir)
        assert dest_dir.exists()


# ------------------------------------------------------------------
# delete_file
# ------------------------------------------------------------------

class TestDeleteFile:

    def test_deletes_existing_file(self, tmp_path):
        src = tmp_path / "temp.tmp"
        src.write_text("junk")

        ops.delete_file(src)

        assert not src.exists()

    def test_missing_file_raises(self, tmp_path):
        missing = tmp_path / "nope.tmp"
        with pytest.raises(ops.FileOperationError):
            ops.delete_file(missing)
