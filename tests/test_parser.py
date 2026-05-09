"""Unit tests for runcoach.parser module."""

from __future__ import annotations

import json
import pytest
import shutil
from pathlib import Path

from runcoach.parser import parse_fit_file


class TestParseFitFile:
    """Tests for parse_fit_file function."""

    def test_parse_fit_file_returns_dict(self, tmp_path):
        """parse_fit_file returns a dict with expected top-level keys."""
        fit_file = Path("data/activities/2026/01/20260129_day_25_-_testing/20260129_day_25_-_testing.fit")
        if not fit_file.exists():
            pytest.skip("Test FIT file not found")

        temp_fit = tmp_path / "test.fit"
        shutil.copy(fit_file, temp_fit)

        result = parse_fit_file(temp_fit)

        assert isinstance(result, dict)
        assert "workout_name" in result
        assert "distance_km" in result
        assert "duration_min" in result

    def test_parse_fit_file_no_yaml_written(self, tmp_path):
        """parse_fit_file does not write any files to disk."""
        fit_file = Path("data/activities/2026/01/20260129_day_25_-_testing/20260129_day_25_-_testing.fit")
        if not fit_file.exists():
            pytest.skip("Test FIT file not found")

        temp_fit = tmp_path / "test.fit"
        shutil.copy(fit_file, temp_fit)

        parse_fit_file(temp_fit)

        # Only the .fit file should exist — no .yaml or other output
        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert files[0].suffix == ".fit"

    def test_parse_fit_file_result_is_json_serialisable(self, tmp_path):
        """Result of parse_fit_file can be serialised to JSON without error."""
        fit_file = Path("data/activities/2026/01/20260129_day_25_-_testing/20260129_day_25_-_testing.fit")
        if not fit_file.exists():
            pytest.skip("Test FIT file not found")

        temp_fit = tmp_path / "test.fit"
        shutil.copy(fit_file, temp_fit)

        result = parse_fit_file(temp_fit)

        serialised = json.dumps(result)
        assert isinstance(serialised, str)
        assert len(serialised) > 0
