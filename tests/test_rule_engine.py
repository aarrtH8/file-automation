"""
test_rule_engine.py
-------------------
Unit tests for rule_engine.py.

Tests verify:
  - Temp patterns trigger delete action.
  - Known extensions match the correct rule and return correct actions.
  - Unknown extensions return an empty list (skip).
  - Priority ordering picks the first matching rule.
  - Optional name pattern filtering works.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import logger_setup as ls
import tempfile


@pytest.fixture(autouse=True)
def bootstrap_logger(tmp_path):
    ls.setup_logging(logs_dir=tmp_path / "logs", log_level="DEBUG")


from rule_engine import RuleEngine

BASE_CONFIG = {
    "temp_patterns": ["~*", "*.tmp", "*.bak", "Thumbs.db"],
    "rename": {"enabled": True},
    "rules": [
        {
            "id": "rule_pdf",
            "priority": 10,
            "match_extensions": [".pdf"],
            "match_name_pattern": None,
            "actions": ["rename", "compress", "move_to_archive"],
        },
        {
            "id": "rule_jpg",
            "priority": 20,
            "match_extensions": [".jpg", ".jpeg"],
            "match_name_pattern": None,
            "actions": ["rename", "move_to_archive"],
        },
        {
            "id": "rule_txt",
            "priority": 30,
            "match_extensions": [".txt"],
            "match_name_pattern": None,
            "actions": ["rename", "compress", "move_to_archive"],
        },
    ],
}


class TestTempPatterns:

    def test_tmp_extension_triggers_delete(self):
        engine = RuleEngine(BASE_CONFIG)
        assert engine.get_actions_for_file(Path("file.tmp")) == ["delete"]

    def test_bak_extension_triggers_delete(self):
        engine = RuleEngine(BASE_CONFIG)
        assert engine.get_actions_for_file(Path("backup.bak")) == ["delete"]

    def test_tilde_prefix_triggers_delete(self):
        engine = RuleEngine(BASE_CONFIG)
        assert engine.get_actions_for_file(Path("~lockfile")) == ["delete"]

    def test_thumbs_db_triggers_delete(self):
        engine = RuleEngine(BASE_CONFIG)
        assert engine.get_actions_for_file(Path("Thumbs.db")) == ["delete"]

    def test_is_temp_file_returns_true(self):
        engine = RuleEngine(BASE_CONFIG)
        assert engine.is_temp_file(Path("file.tmp")) is True

    def test_normal_file_not_temp(self):
        engine = RuleEngine(BASE_CONFIG)
        assert engine.is_temp_file(Path("report.pdf")) is False


class TestRuleMatching:

    def test_pdf_returns_compress_pipeline(self):
        engine = RuleEngine(BASE_CONFIG)
        actions = engine.get_actions_for_file(Path("report.pdf"))
        assert actions == ["rename", "compress", "move_to_archive"]

    def test_jpg_returns_no_compress_pipeline(self):
        engine = RuleEngine(BASE_CONFIG)
        actions = engine.get_actions_for_file(Path("photo.jpg"))
        assert actions == ["rename", "move_to_archive"]

    def test_jpeg_matches_jpg_rule(self):
        engine = RuleEngine(BASE_CONFIG)
        actions = engine.get_actions_for_file(Path("photo.jpeg"))
        assert actions == ["rename", "move_to_archive"]

    def test_txt_returns_compress_pipeline(self):
        engine = RuleEngine(BASE_CONFIG)
        actions = engine.get_actions_for_file(Path("notes.txt"))
        assert actions == ["rename", "compress", "move_to_archive"]

    def test_unknown_extension_returns_empty(self):
        engine = RuleEngine(BASE_CONFIG)
        actions = engine.get_actions_for_file(Path("data.xyz"))
        assert actions == []

    def test_extension_matching_case_insensitive(self):
        engine = RuleEngine(BASE_CONFIG)
        actions = engine.get_actions_for_file(Path("REPORT.PDF"))
        assert actions == ["rename", "compress", "move_to_archive"]


class TestPriorityOrdering:

    def test_higher_priority_rule_wins(self):
        config = {
            **BASE_CONFIG,
            "rules": [
                {
                    "id": "low_priority",
                    "priority": 100,
                    "match_extensions": [".pdf"],
                    "match_name_pattern": None,
                    "actions": ["delete"],
                },
                {
                    "id": "high_priority",
                    "priority": 1,
                    "match_extensions": [".pdf"],
                    "match_name_pattern": None,
                    "actions": ["rename", "move_to_archive"],
                },
            ],
        }
        engine = RuleEngine(config)
        actions = engine.get_actions_for_file(Path("file.pdf"))
        assert actions == ["rename", "move_to_archive"]


class TestNamePatternMatching:

    def test_pattern_match_required_when_set(self):
        config = {
            **BASE_CONFIG,
            "rules": [
                {
                    "id": "invoice_rule",
                    "priority": 5,
                    "match_extensions": [".pdf"],
                    "match_name_pattern": "invoice_*",
                    "actions": ["rename", "compress", "move_to_archive"],
                },
                {
                    "id": "fallback_pdf",
                    "priority": 10,
                    "match_extensions": [".pdf"],
                    "match_name_pattern": None,
                    "actions": ["rename", "move_to_archive"],
                },
            ],
        }
        engine = RuleEngine(config)

        assert engine.get_actions_for_file(Path("invoice_001.pdf")) == [
            "rename", "compress", "move_to_archive"
        ]
        assert engine.get_actions_for_file(Path("report.pdf")) == [
            "rename", "move_to_archive"
        ]
