"""Unit tests for runcoach.parser module."""

from __future__ import annotations

import pytest
import yaml
from pathlib import Path
import shutil

from runcoach.parser import parse_and_write


class TestParseAndWrite:
    """Tests for parse_and_write function."""

    def test_parse_and_write_basic(self, tmp_path):
        """Test basic FIT parsing and YAML output."""
        # Use a real FIT file from test data
        fit_file = Path("data/activities/2026/01/20260129_day_25_-_testing/20260129_day_25_-_testing.fit")
        if not fit_file.exists():
            pytest.skip("Test FIT file not found")

        # Copy to temp directory
        temp_fit = tmp_path / "test.fit"
        shutil.copy(fit_file, temp_fit)

        # Parse
        yaml_path = parse_and_write(temp_fit)

        # Verify YAML was created
        assert yaml_path.exists()
        assert yaml_path.suffix == ".yaml"

        # Verify YAML content
        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        assert "workout_name" in data
        assert "distance_km" in data
        assert "duration_min" in data

    def test_parse_and_write_with_planned_workout_title(self, tmp_path):
        """Test that planned workout title replaces truncated FIT name."""
        # Use a FIT file with a truncated name
        fit_file = Path("data/activities/2025/03/20250307_day_11_-_ez_aerobic___recovery_run/20250307_day_11_-_ez_aerobic___recovery_run.fit")
        if not fit_file.exists():
            pytest.skip("Test FIT file not found")

        # Copy to temp directory
        temp_fit = tmp_path / "test.fit"
        shutil.copy(fit_file, temp_fit)

        # The FIT file has truncated name at 32 chars
        truncated_name = "Day 11 - EZ Aerobic / Recovery R"
        full_name = "Day 11 - EZ Aerobic / Recovery Run"

        # Parse with planned workout title
        yaml_path = parse_and_write(temp_fit, planned_workout_title=full_name)

        # Read YAML
        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        # Should use full name from planned workout
        assert data["workout_name"] == full_name
        assert len(data["workout_name"]) > 32
        assert data.get("workout_name_source") == "planned_workout"

    def test_parse_and_write_with_non_matching_planned_workout(self, tmp_path):
        """Test that non-matching planned workout title is not used."""
        # Use a FIT file
        fit_file = Path("data/activities/2026/01/20260129_day_25_-_testing/20260129_day_25_-_testing.fit")
        if not fit_file.exists():
            pytest.skip("Test FIT file not found")

        # Copy to temp directory
        temp_fit = tmp_path / "test.fit"
        shutil.copy(fit_file, temp_fit)

        # Provide a planned workout title that doesn't match
        unrelated_title = "Completely Different Workout Name"

        # Parse with unrelated planned workout title
        yaml_path = parse_and_write(temp_fit, planned_workout_title=unrelated_title)

        # Read YAML
        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        # Should NOT use the unrelated planned workout title
        assert data["workout_name"] != unrelated_title
        assert "workout_name_source" not in data or data.get("workout_name_source") != "planned_workout"

    def test_parse_and_write_with_stryd_rss(self, tmp_path):
        """Test that Stryd RSS is included in YAML."""
        fit_file = Path("data/activities/2026/01/20260129_day_25_-_testing/20260129_day_25_-_testing.fit")
        if not fit_file.exists():
            pytest.skip("Test FIT file not found")

        temp_fit = tmp_path / "test.fit"
        shutil.copy(fit_file, temp_fit)

        # Parse with RSS
        yaml_path = parse_and_write(temp_fit, stryd_rss=85.3)

        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        assert data["stryd_rss"] == 85.3
        assert "stryd_rss_note" in data

    def test_parse_and_write_manual_upload(self, tmp_path):
        """Test manual upload flag is added to YAML."""
        fit_file = Path("data/activities/2026/01/20260129_day_25_-_testing/20260129_day_25_-_testing.fit")
        if not fit_file.exists():
            pytest.skip("Test FIT file not found")

        temp_fit = tmp_path / "test.fit"
        shutil.copy(fit_file, temp_fit)

        # Parse as manual upload
        yaml_path = parse_and_write(temp_fit, manual_upload=True)

        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        assert data["manual_upload"] is True
        assert "manual_upload_note" in data
