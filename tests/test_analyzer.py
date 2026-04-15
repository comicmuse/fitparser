"""Unit tests for runcoach.analyzer module."""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
import yaml

from runcoach.analyzer import (
    analyze_run,
    analyze_and_write,
    _load_athlete_profile,
    _load_schema,
)


class TestLoadAthleteProfile:
    """Tests for loading athlete profile."""

    def test_load_athlete_profile_with_db(self, temp_db):
        """Test loading profile from database."""
        user_id = temp_db.get_default_user_id()
        assert user_id is not None
        temp_db.update_athlete_profile(user_id, "My custom athlete profile")

        profile = _load_athlete_profile(temp_db)
        assert profile == "My custom athlete profile"

    def test_load_athlete_profile_no_db(self):
        """Test loading profile without database returns empty string."""
        profile = _load_athlete_profile(None)
        assert profile == ""

    def test_load_athlete_profile_empty_profile(self, temp_db):
        """Test loading profile when profile is empty in DB."""
        user_id = temp_db.get_default_user_id()
        temp_db.update_athlete_profile(user_id, "")

        profile = _load_athlete_profile(temp_db)
        assert profile == ""


class TestLoadSchema:
    """Tests for loading workout schema."""

    def test_load_schema_default(self):
        """Test loading schema from default location."""
        schema = _load_schema()
        # Should return a string (JSON)
        assert isinstance(schema, str)
        # Should be valid JSON (or empty)
        if schema:
            import json
            try:
                json.loads(schema)
            except json.JSONDecodeError:
                pytest.fail("Schema is not valid JSON")

    def test_load_schema_custom_root(self, tmp_path):
        """Test loading schema from custom project root."""
        schema_path = tmp_path / "workout_yaml_schema.json"
        schema_path.write_text('{"test": "schema"}')

        schema = _load_schema(tmp_path)
        assert '{"test": "schema"}' in schema


class TestAnalyzeRun:
    """Tests for the analyze_run function."""

    def test_analyze_run_basic(self, test_config, mock_openai_client):
        """Test basic run analysis."""
        yaml_content = """
date: '2026-03-01'
name: Test Run
distance_km: 10.0
duration_min: 50.0
avg_power: 200
avg_hr: 150
"""

        result = analyze_run(yaml_content, test_config)

        assert "commentary" in result
        assert "prompt_tokens" in result
        assert "completion_tokens" in result

        # Check mock was called
        mock_openai_client.chat.completions.create.assert_called_once()

        # Verify the call structure
        call_args = mock_openai_client.chat.completions.create.call_args
        assert call_args.kwargs["model"] == test_config.openai_model

        messages = call_args.kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert yaml_content in messages[1]["content"]

    def test_analyze_run_with_context(self, test_config, mock_openai_client):
        """Test run analysis with training context."""
        yaml_content = """
date: '2026-03-01'
name: Test Run
distance_km: 10.0
"""

        context_yaml = """
training_context:
  period: '2026-02-23 to 2026-02-29'
  summary:
    total_runs: 3
    total_distance_km: 25.0
"""

        result = analyze_run(yaml_content, test_config, context_yaml=context_yaml)

        # Check that context was prepended
        call_args = mock_openai_client.chat.completions.create.call_args
        user_msg = call_args.kwargs["messages"][1]["content"]

        assert context_yaml.strip() in user_msg
        assert "---" in user_msg
        assert yaml_content in user_msg

    def test_analyze_run_manual_upload(self, test_config, mock_openai_client):
        """Test that manual uploads get special prompt note."""
        yaml_content = """
date: '2026-03-01'
name: Manual Upload
manual_upload: true
distance_km: 10.0
"""

        result = analyze_run(yaml_content, test_config)

        # Check that system message includes manual upload note
        call_args = mock_openai_client.chat.completions.create.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]

        assert "manual upload" in system_msg.lower()
        assert "power data" in system_msg.lower()

    def test_analyze_run_prompt_construction(self, test_config, mock_openai_client):
        """Test that prompt is constructed correctly."""
        yaml_content = "date: '2026-03-01'"

        result = analyze_run(yaml_content, test_config)

        call_args = mock_openai_client.chat.completions.create.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]

        # Check for key prompt elements
        assert "running trainer" in system_msg.lower()
        assert "YAML" in system_msg
        assert "training context" in system_msg.lower()

    def test_analyze_run_returns_tokens(self, test_config, mock_openai_client):
        """Test that token counts are returned."""
        yaml_content = "date: '2026-03-01'"

        result = analyze_run(yaml_content, test_config)

        assert result["prompt_tokens"] == 100
        assert result["completion_tokens"] == 50
        assert result["commentary"] == "Test commentary"


class TestAnalyzeAndWrite:
    """Tests for the analyze_and_write function."""

    def test_analyze_and_write_creates_md(self, test_config, mock_openai_client, tmp_path):
        """Test that analyze_and_write creates markdown file."""
        # Create a test YAML file
        yaml_path = tmp_path / "test.yaml"
        yaml_content = {
            "date": "2026-03-01",
            "name": "Test Run",
            "distance_km": 10.0,
        }
        yaml_path.write_text(yaml.dump(yaml_content))

        # Analyze and write
        md_path, result = analyze_and_write(yaml_path, test_config, db=None)

        # Check that .md file was created
        assert md_path.exists()
        assert md_path.suffix == ".md"
        assert md_path.stem == yaml_path.stem

        # Check content
        md_content = md_path.read_text()
        assert md_content == "Test commentary"

        # Check return values
        assert result["commentary"] == "Test commentary"
        assert result["prompt_tokens"] == 100
        assert result["completion_tokens"] == 50

    def test_analyze_and_write_with_context(self, test_config, mock_openai_client, temp_db, tmp_path):
        """Test analyze_and_write with training context."""
        # Set up data directory in temp_db's location
        test_config.data_dir = tmp_path

        # Create YAML file
        yaml_dir = tmp_path / "activities" / "2026" / "03"
        yaml_dir.mkdir(parents=True)
        yaml_path = yaml_dir / "20260301_test.yaml"

        yaml_content = {
            "date": "2026-03-01",
            "name": "Test Run",
            "distance_km": 10.0,
            "duration_min": 50.0,
            "avg_power": 200,
            "critical_power": 250,
        }
        yaml_path.write_text(yaml.dump(yaml_content))

        # Add a previous run to build context
        prev_yaml_path = tmp_path / "activities" / "2026" / "02" / "20260225_prev.yaml"
        prev_yaml_path.parent.mkdir(parents=True, exist_ok=True)
        prev_yaml_content = {
            "date": "2026-02-25",
            "name": "Previous Run",
            "distance_km": 8.0,
            "duration_min": 40.0,
            "avg_power": 190,
            "critical_power": 250,
        }
        prev_yaml_path.write_text(yaml.dump(prev_yaml_content))

        # Insert previous run into database
        temp_db.insert_run(
            stryd_activity_id=12345,
            name="Previous Run",
            date="2026-02-25",
            fit_path="activities/2026/02/20260225_prev.fit",
        )
        runs = temp_db.get_all_runs()
        temp_db.update_parsed(
            run_id=runs[0]["id"],
            yaml_path="activities/2026/02/20260225_prev.yaml",
            avg_power_w=190,
            avg_hr=145,
            workout_name="Previous Run",
        )

        # Analyze and write
        md_path, result = analyze_and_write(yaml_path, test_config, db=temp_db)

        # Check that context was built and included
        call_args = mock_openai_client.chat.completions.create.call_args
        user_msg = call_args.kwargs["messages"][1]["content"]

        assert "training_context" in user_msg
        assert "---" in user_msg  # YAML document separator

    def test_analyze_and_write_without_db(self, test_config, mock_openai_client, tmp_path):
        """Test analyze_and_write without database (no context)."""
        yaml_path = tmp_path / "test.yaml"
        yaml_content = {"date": "2026-03-01", "name": "Test"}
        yaml_path.write_text(yaml.dump(yaml_content))

        md_path, result = analyze_and_write(yaml_path, test_config, db=None)

        # Should work without context
        assert md_path.exists()

        # Check that no context was included
        call_args = mock_openai_client.chat.completions.create.call_args
        user_msg = call_args.kwargs["messages"][1]["content"]

        assert "training_context" not in user_msg
        assert "---" not in user_msg

    def test_analyze_and_write_handles_context_error(self, test_config, mock_openai_client, temp_db, tmp_path):
        """Test that context build errors don't prevent analysis."""
        test_config.data_dir = tmp_path

        # Create YAML with invalid date to trigger context error
        yaml_path = tmp_path / "test.yaml"
        yaml_content = {
            "date": "invalid-date",
            "name": "Test",
        }
        yaml_path.write_text(yaml.dump(yaml_content))

        # Should still succeed even if context building fails
        md_path, result = analyze_and_write(yaml_path, test_config, db=temp_db)

        assert md_path.exists()
        assert result["commentary"] == "Test commentary"


class TestAnalyzerIntegration:
    """Integration tests for the analyzer module."""

    def test_full_analysis_workflow(self, test_config, mock_openai_client, tmp_path, sample_yaml_file):
        """Test complete analysis workflow with real YAML structure."""
        if not sample_yaml_file.exists():
            pytest.skip(f"Sample YAML file not found: {sample_yaml_file}")

        # Copy sample YAML to temp location
        dest_yaml = tmp_path / "workout.yaml"
        import shutil
        shutil.copy(sample_yaml_file, dest_yaml)

        # Analyze it
        md_path, result = analyze_and_write(dest_yaml, test_config, db=None)

        # Verify output
        assert md_path.exists()
        assert result["commentary"] is not None
        assert result["prompt_tokens"] > 0
        assert result["completion_tokens"] > 0

        # Verify the actual YAML was sent to OpenAI
        call_args = mock_openai_client.chat.completions.create.call_args
        user_msg = call_args.kwargs["messages"][1]["content"]

        # Should contain workout data from the sample
        assert "distance_km" in user_msg or "duration_min" in user_msg


class TestTrainingPhase:
    """Tests for the _training_phase function."""

    def test_base_building(self):
        from runcoach.analyzer import _training_phase
        assert _training_phase(17 * 7) == "Base Building"
        assert _training_phase(16 * 7 + 1) == "Base Building"

    def test_build_phase(self):
        from runcoach.analyzer import _training_phase
        assert _training_phase(16 * 7) == "Build Phase"
        assert _training_phase(8 * 7 + 1) == "Build Phase"

    def test_peak_training(self):
        from runcoach.analyzer import _training_phase
        assert _training_phase(8 * 7) == "Peak Training"
        assert _training_phase(4 * 7 + 1) == "Peak Training"

    def test_taper(self):
        from runcoach.analyzer import _training_phase
        assert _training_phase(4 * 7) == "Taper"
        assert _training_phase(8) == "Taper"

    def test_race_week(self):
        from runcoach.analyzer import _training_phase
        assert _training_phase(7) == "Race Week"
        assert _training_phase(0) == "Race Week"

    def test_recovery(self):
        from runcoach.analyzer import _training_phase
        assert _training_phase(-1) == "Recovery"
        assert _training_phase(-28) == "Recovery"

    def test_post_race(self):
        from runcoach.analyzer import _training_phase
        assert _training_phase(-29) == "Post-race"


class TestAnalyzeRunWithRaceContext:
    """Tests for race context injection in analyze_run."""

    def test_race_context_included_when_goal_set(self, test_config, mock_openai_client, temp_db):
        """Race context appears in system prompt when race goal is set."""
        user_id = temp_db.get_default_user_id()
        temp_db.update_race_goal(user_id, "2026-10-04", "Marathon")

        yaml_content = "date: '2026-04-15'\nname: Test Run\n"
        analyze_run(yaml_content, test_config, db=temp_db, run_date="2026-04-15")

        call_args = mock_openai_client.chat.completions.create.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]

        assert "Marathon" in system_msg
        assert "2026-10-04" in system_msg
        assert "training phase" in system_msg.lower()

    def test_race_context_omitted_when_no_goal(self, test_config, mock_openai_client, temp_db):
        """Race context block is absent when no race goal is set."""
        yaml_content = "date: '2026-04-15'\nname: Test Run\n"
        analyze_run(yaml_content, test_config, db=temp_db, run_date="2026-04-15")

        call_args = mock_openai_client.chat.completions.create.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]

        assert "Current race goal" not in system_msg

    def test_race_context_omitted_when_no_db(self, test_config, mock_openai_client):
        """Race context is absent when no DB is provided."""
        yaml_content = "date: '2026-04-15'\nname: Test Run\n"
        analyze_run(yaml_content, test_config, db=None, run_date="2026-04-15")

        call_args = mock_openai_client.chat.completions.create.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]

        assert "Current race goal" not in system_msg

    def test_race_context_days_calculation(self, test_config, mock_openai_client, temp_db):
        """Correct days until race are computed and included."""
        user_id = temp_db.get_default_user_id()
        temp_db.update_race_goal(user_id, "2026-05-15", "Half Marathon")

        yaml_content = "date: '2026-04-15'\nname: Test Run\n"
        analyze_run(yaml_content, test_config, db=temp_db, run_date="2026-04-15")

        call_args = mock_openai_client.chat.completions.create.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]

        # 30 days from 2026-04-15 to 2026-05-15
        assert "30" in system_msg

    def test_malformed_race_date_does_not_crash(self, test_config, mock_openai_client, temp_db):
        """Malformed race_date in DB is silently ignored."""
        user_id = temp_db.get_default_user_id()
        # Force a bad value directly into the DB
        with temp_db._connect() as conn:
            conn.execute(
                "UPDATE users SET race_date = ?, race_distance = ? WHERE id = ?",
                ("not-a-date", "Marathon", user_id),
            )

        yaml_content = "date: '2026-04-15'\nname: Test Run\n"
        result = analyze_run(yaml_content, test_config, db=temp_db, run_date="2026-04-15")

        assert result["commentary"] == "Test commentary"
        call_args = mock_openai_client.chat.completions.create.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]
        assert "Current race goal" not in system_msg
