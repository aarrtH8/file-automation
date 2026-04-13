"""
rule_engine.py
--------------
Config-driven rule evaluation engine.

Responsibilities:
  - Load rules and temp patterns from the parsed config dictionary.
  - Evaluate a file path against temp patterns first (immediate delete).
  - Match a file path against the ordered rule list to return an action sequence.

Rules are matched by:
  1. Extension match (case-insensitive).
  2. Optional name pattern match (fnmatch glob).
  First matching rule (by ascending priority) wins.

Usage:
    engine = RuleEngine(config)
    actions = engine.get_actions_for_file(Path("report.pdf"))
    # returns: ["rename", "compress", "move_to_archive"]
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Optional

from logger_setup import get_logger


class RuleEngine:
    """Evaluates file paths against config-driven rules and returns action lists."""

    def __init__(self, config: dict) -> None:
        """
        Args:
            config: Parsed configuration dictionary (from config.json or config.yaml).
        """
        self._logger = get_logger()
        self._temp_patterns: list[str] = config.get("temp_patterns", [])
        self._rename_cfg: dict = config.get("rename", {})
        self._rules: list[dict] = sorted(
            config.get("rules", []),
            key=lambda r: r.get("priority", 999),
        )
        self._logger.debug(
            "RuleEngine initialized with %d rules and %d temp patterns.",
            len(self._rules),
            len(self._temp_patterns),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_temp_file(self, filepath: Path) -> bool:
        """
        Return True if the file name matches any temporary/duplicate pattern.

        Temp patterns are evaluated before all rules. Matching files are deleted.

        Args:
            filepath: Path object for the file to evaluate.
        """
        name = filepath.name
        for pattern in self._temp_patterns:
            if fnmatch.fnmatch(name, pattern):
                self._logger.debug(
                    "File '%s' matched temp pattern '%s'.", name, pattern
                )
                return True
        return False

    def get_actions_for_file(self, filepath: Path) -> list[str]:
        """
        Return the ordered list of actions for a given file.

        Returns an empty list if no rule matches (file is skipped).

        Args:
            filepath: Path object for the file to evaluate.
        """
        if self.is_temp_file(filepath):
            return ["delete"]

        suffix = filepath.suffix.lower()
        name = filepath.name

        for rule in self._rules:
            extensions: list[str] = [
                ext.lower() for ext in rule.get("match_extensions", [])
            ]
            pattern: Optional[str] = rule.get("match_name_pattern")

            extension_match = suffix in extensions if extensions else False
            pattern_match = fnmatch.fnmatch(name, pattern) if pattern else True

            if extension_match and pattern_match:
                actions: list[str] = rule.get("actions", [])
                self._logger.debug(
                    "File '%s' matched rule '%s' -> actions: %s.",
                    name,
                    rule.get("id", "unknown"),
                    actions,
                )
                return actions

        self._logger.debug(
            "File '%s' did not match any rule. Skipping.", filepath.name
        )
        return []

    def get_rename_config(self) -> dict:
        """Return the rename configuration block from the loaded config."""
        return self._rename_cfg
