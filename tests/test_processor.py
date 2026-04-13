"""
test_processor.py
-----------------
Unit tests for processor.py.

Tests use mocked file_operations to verify action sequencing logic
without touching the real filesystem beyond temporary directories.

Tests verify:
  - Correct action sequence for rename→compress→archive.
  - Correct action sequence for rename→archive (no compress).
  - Delete action exits the pipeline early.
  - Files that disappear before processing are skipped gracefully.
  - Failed operations trigger quarantine.
  - Unknown actions are skipped with a warning (no crash).
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import time

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import logger_setup as ls


@pytest.fixture(autouse=True)
def bootstrap_logger(tmp_path):
    ls.setup_logging(logs_dir=tmp_path / "logs", log_level="DEBUG")


from processor import FileProcessor
from rule_engine import RuleEngine


def _make_processor(tmp_path: Path, config_override: dict = None) -> FileProcessor:
    config = {
        "settings": {
            "file_stability_check_interval_ms": 10,
            "file_stability_max_retries": 2,
        },
        "paths": {
            "archive_dir": str(tmp_path / "archive"),
            "logs_dir": str(tmp_path / "logs"),
            "quarantine_dir": str(tmp_path / "quarantine"),
            "watch_dirs": [str(tmp_path / "input")],
        },
        "rename": {"enabled": True, "timestamp_format": "%Y%m%d_%H%M%S", "separator": "_"},
        "temp_patterns": ["*.tmp"],
        "rules": [],
    }
    if config_override:
        config.update(config_override)
    rule_engine = RuleEngine(config)
    return FileProcessor(config, rule_engine)


class TestActionSequencing:

    def test_rename_compress_archive_pipeline(self, tmp_path):
        src = tmp_path / "report.pdf"
        src.write_text("pdf content")

        renamed = tmp_path / "report_20260411_143210.pdf"
        # compress now writes directly into archive_dir, so the zip is there
        archive_dir = tmp_path / "archive"
        zip_path = archive_dir / "report_20260411_143210.zip"

        with (
            patch("processor.ops.rename_file", return_value=renamed) as mock_rename,
            patch("processor.ops.compress_file", return_value=zip_path) as mock_compress,
            patch("processor.ops.move_file") as mock_move,
        ):
            processor = _make_processor(tmp_path)
            processor._rule_engine.get_actions_for_file = MagicMock(
                return_value=["rename", "compress", "move_to_archive"]
            )
            processor.process(src)

        mock_rename.assert_called_once_with(src, processor._rename_cfg)
        # compress targets archive_dir directly (avoids watchdog re-firing on Input/)
        mock_compress.assert_called_once_with(renamed, processor._archive_dir)
        # move_to_archive is skipped — file is already in archive_dir
        mock_move.assert_not_called()

    def test_rename_archive_pipeline_no_compress(self, tmp_path):
        src = tmp_path / "photo.jpg"
        src.write_text("img")

        renamed = tmp_path / "photo_20260411_143210.jpg"
        final_path = tmp_path / "archive" / "photo_20260411_143210.jpg"

        with (
            patch("processor.ops.rename_file", return_value=renamed) as mock_rename,
            patch("processor.ops.compress_file") as mock_compress,
            patch("processor.ops.move_file", return_value=final_path) as mock_move,
        ):
            processor = _make_processor(tmp_path)
            processor._rule_engine.get_actions_for_file = MagicMock(
                return_value=["rename", "move_to_archive"]
            )
            processor.process(src)

        mock_rename.assert_called_once()
        mock_compress.assert_not_called()
        mock_move.assert_called_once_with(renamed, processor._archive_dir)

    def test_delete_action_exits_pipeline_early(self, tmp_path):
        src = tmp_path / "junk.tmp"
        src.write_text("temp")

        with (
            patch("processor.ops.delete_file") as mock_delete,
            patch("processor.ops.rename_file") as mock_rename,
            patch("processor.ops.move_file") as mock_move,
        ):
            processor = _make_processor(tmp_path)
            processor._rule_engine.get_actions_for_file = MagicMock(
                return_value=["delete"]
            )
            processor.process(src)

        mock_delete.assert_called_once_with(src)
        mock_rename.assert_not_called()
        mock_move.assert_not_called()

    def test_unknown_action_skipped_without_crash(self, tmp_path):
        src = tmp_path / "file.pdf"
        src.write_text("data")

        renamed = tmp_path / "file_renamed.pdf"

        with (
            patch("processor.ops.rename_file", return_value=renamed),
            patch("processor.ops.move_file") as mock_move,
        ):
            processor = _make_processor(tmp_path)
            processor._rule_engine.get_actions_for_file = MagicMock(
                return_value=["rename", "nonexistent_action", "move_to_archive"]
            )
            processor.process(src)

        mock_move.assert_called_once()


class TestEdgeCases:

    def test_no_matching_rule_skips_file(self, tmp_path):
        src = tmp_path / "file.xyz"
        src.write_text("data")

        with patch("processor.ops.rename_file") as mock_rename:
            processor = _make_processor(tmp_path)
            processor._rule_engine.get_actions_for_file = MagicMock(return_value=[])
            processor.process(src)

        mock_rename.assert_not_called()

    def test_disappeared_file_skipped_gracefully(self, tmp_path):
        src = tmp_path / "vanished.pdf"

        with patch("processor.ops.rename_file") as mock_rename:
            processor = _make_processor(tmp_path)
            processor.process(src)

        mock_rename.assert_not_called()

    def test_failed_operation_triggers_quarantine(self, tmp_path):
        src = tmp_path / "problematic.pdf"
        src.write_text("data")

        from file_operations import FileOperationError

        with (
            patch("processor.ops.rename_file", side_effect=FileOperationError("disk full")),
            patch("processor.ops.move_file") as mock_quarantine_move,
        ):
            processor = _make_processor(tmp_path)
            processor._rule_engine.get_actions_for_file = MagicMock(
                return_value=["rename", "move_to_archive"]
            )
            processor.process(src)

        mock_quarantine_move.assert_called_once_with(src, processor._quarantine_dir)
