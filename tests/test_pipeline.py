"""Tests for runcoach.pipeline — full sync/parse/analyze orchestration."""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from runcoach.config import Config
from runcoach.db import RunCoachDB
from runcoach.pipeline import run_full_pipeline


@pytest.fixture
def config(tmp_path):
    cfg = Config(
        openai_api_key="test-key",
        openai_model="gpt-4o",
        data_dir=tmp_path / "data",
        timezone="Europe/London",
        stryd_email="",
        stryd_password="",
        sync_interval_hours=24,
        openai_auto_analyse=False,  # prevent analyze stage from running by default
    )
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    return cfg


@pytest.fixture
def db(config):
    from runcoach.auth import hash_password
    d = RunCoachDB(config.db_path)
    d.ensure_default_user("athlete", hash_password("pass"))
    return d


# ---------------------------------------------------------------------------
# Skip-sync branch (no credentials)
# ---------------------------------------------------------------------------

class TestPipelineNoCredentials:
    def test_skips_sync_without_stryd_credentials(self, config, db):
        """Pipeline should not attempt sync when Stryd creds are absent."""
        with patch("runcoach.pipeline.sync_new_activities") as mock_sync:
            result = run_full_pipeline(config, db)
        mock_sync.assert_not_called()
        assert result["synced"] == 0

    def test_skips_analysis_without_openai_key(self, config, db):
        """Pipeline should skip analysis when no OpenAI key is set."""
        config.openai_api_key = ""
        with patch("runcoach.pipeline.analyze_and_write") as mock_analyze:
            run_full_pipeline(config, db)
        mock_analyze.assert_not_called()

    def test_skips_analysis_when_auto_analyse_off(self, config, db):
        """Pipeline respects OPENAI_AUTO_ANALYSE=false."""
        config.openai_auto_analyse = False
        with patch("runcoach.pipeline.analyze_and_write") as mock_analyze:
            run_full_pipeline(config, db)
        mock_analyze.assert_not_called()

    def test_returns_summary_dict(self, config, db):
        result = run_full_pipeline(config, db)
        for key in ("synced", "parsed", "analyzed", "errors", "planned"):
            assert key in result

    def test_empty_pipeline_zero_counts(self, config, db):
        result = run_full_pipeline(config, db)
        assert result["synced"] == 0
        assert result["parsed"] == 0
        assert result["analyzed"] == 0
        assert result["errors"] == 0


# ---------------------------------------------------------------------------
# Concurrency lock
# ---------------------------------------------------------------------------

class TestPipelineLock:
    def test_concurrent_run_skipped(self, config, db):
        """A second concurrent call returns skipped=True immediately."""
        import runcoach.pipeline as pipeline_mod

        # Acquire the lock manually to simulate an in-progress pipeline
        acquired = pipeline_mod._pipeline_lock.acquire(blocking=False)
        assert acquired, "Lock should be free at test start"
        try:
            result = run_full_pipeline(config, db)
            assert result == {"skipped": True}
        finally:
            pipeline_mod._pipeline_lock.release()


# ---------------------------------------------------------------------------
# Parse stage
# ---------------------------------------------------------------------------

class TestPipelineParseStage:
    def test_parse_stage_processes_synced_runs(self, config, db, tmp_path):
        """Runs in 'synced' stage should be parsed."""
        # Create a minimal FIT file placeholder at the expected path
        fit_dir = config.data_dir / "activities"
        fit_dir.mkdir(parents=True, exist_ok=True)
        fit_path = fit_dir / "test.fit"
        fit_path.write_bytes(b"\x00" * 20)  # dummy bytes

        run_id = db.insert_run(
            stryd_activity_id=1,
            name="Sync'd Run",
            date="2026-03-01",
            fit_path="activities/test.fit",
        )

        fake_yaml = {"workout_name": "Easy Run", "avg_power": 250, "avg_hr": 140}

        yaml_output = config.data_dir / "activities" / "test.yaml"

        def fake_parse(fit_path, timezone, stryd_rss=None, planned_workout_title=None):
            import yaml as _yaml
            yaml_output.write_text(_yaml.dump(fake_yaml))
            return yaml_output

        with patch("runcoach.pipeline.parse_and_write", side_effect=fake_parse):
            result = run_full_pipeline(config, db)

        assert result["parsed"] == 1
        assert result["errors"] == 0

        updated = db.get_run(run_id)
        assert updated["stage"] == "parsed"
        assert updated["workout_name"] == "Easy Run"

    def test_parse_stage_records_error_on_failure(self, config, db):
        """A parse failure should increment errors and set stage to 'error'."""
        fit_dir = config.data_dir / "activities"
        fit_dir.mkdir(parents=True, exist_ok=True)
        (fit_dir / "bad.fit").write_bytes(b"\x00")

        run_id = db.insert_run(
            stryd_activity_id=2,
            name="Bad Run",
            date="2026-03-02",
            fit_path="activities/bad.fit",
        )

        with patch("runcoach.pipeline.parse_and_write", side_effect=RuntimeError("parse boom")):
            result = run_full_pipeline(config, db)

        assert result["errors"] == 1
        assert db.get_run(run_id)["stage"] == "error"


# ---------------------------------------------------------------------------
# Analyze stage
# ---------------------------------------------------------------------------

class TestPipelineAnalyzeStage:
    def _insert_parsed_run(self, config, db, tmp_path):
        """Helper: insert a run already in 'parsed' stage with a YAML file."""
        import yaml as _yaml
        yaml_dir = config.data_dir / "activities"
        yaml_dir.mkdir(parents=True, exist_ok=True)
        yaml_path = yaml_dir / "run.yaml"
        yaml_path.write_text(_yaml.dump({"workout_name": "Test", "avg_power": 260}))

        run_id = db.insert_run(
            stryd_activity_id=10,
            name="Parsed Run",
            date="2026-03-05",
            fit_path="activities/run.fit",
        )
        db.update_parsed(
            run_id=run_id,
            yaml_path="activities/run.yaml",
            avg_power_w=260,
            avg_hr=145,
            workout_name="Test",
        )
        return run_id

    def test_analyze_stage_processes_parsed_runs(self, config, db, tmp_path):
        config.openai_auto_analyse = True
        run_id = self._insert_parsed_run(config, db, tmp_path)

        md_path = config.data_dir / "activities" / "run.md"
        mock_result = {
            "commentary": "Great run!",
            "prompt_tokens": 100,
            "completion_tokens": 50,
        }

        with patch(
            "runcoach.pipeline.analyze_and_write",
            return_value=(md_path, mock_result),
        ), patch("runcoach.pipeline.send_analysis_notification"):
            result = run_full_pipeline(config, db)

        assert result["analyzed"] == 1
        assert result["errors"] == 0
        updated = db.get_run(run_id)
        assert updated["stage"] == "analyzed"
        assert updated["commentary"] == "Great run!"

    def test_analyze_stage_records_error_on_failure(self, config, db, tmp_path):
        config.openai_auto_analyse = True
        run_id = self._insert_parsed_run(config, db, tmp_path)

        with patch(
            "runcoach.pipeline.analyze_and_write",
            side_effect=RuntimeError("openai boom"),
        ):
            result = run_full_pipeline(config, db)

        assert result["errors"] == 1
        assert db.get_run(run_id)["stage"] == "error"

    def test_analyze_stage_ignores_push_notification_failure(self, config, db, tmp_path):
        """A push notification failure must not mark the run as errored."""
        config.openai_auto_analyse = True
        run_id = self._insert_parsed_run(config, db, tmp_path)

        md_path = config.data_dir / "activities" / "run.md"
        mock_result = {"commentary": "Nice!", "prompt_tokens": 10, "completion_tokens": 5}

        with patch(
            "runcoach.pipeline.analyze_and_write",
            return_value=(md_path, mock_result),
        ), patch(
            "runcoach.pipeline.send_analysis_notification",
            side_effect=RuntimeError("push failed"),
        ):
            result = run_full_pipeline(config, db)

        # errors should be 0 — push failure is non-fatal
        assert result["analyzed"] == 1
        assert result["errors"] == 0

    def test_analyze_respects_date_from_filter(self, config, db, tmp_path):
        """analyze_from config causes old runs to be skipped."""
        config.openai_auto_analyse = True
        config.analyze_from = "2026-04-01"  # future date
        run_id = self._insert_parsed_run(config, db, tmp_path)  # date="2026-03-05"

        with patch("runcoach.pipeline.analyze_and_write") as mock_analyze:
            result = run_full_pipeline(config, db)

        mock_analyze.assert_not_called()
        assert result["analyzed"] == 0


# ---------------------------------------------------------------------------
# Sync stage (with credentials, mocked network)
# ---------------------------------------------------------------------------

class TestPipelineSyncStage:
    def test_sync_stage_uses_credentials(self, config, db):
        config.stryd_email = "user@example.com"
        config.stryd_password = "secret"

        with patch(
            "runcoach.pipeline.sync_new_activities",
            return_value=[],
        ) as mock_sync, patch(
            "runcoach.pipeline.sync_planned_workouts",
            return_value=0,
        ):
            result = run_full_pipeline(config, db)

        mock_sync.assert_called_once()
        assert result["synced"] == 0

    def test_sync_failure_increments_errors(self, config, db):
        config.stryd_email = "user@example.com"
        config.stryd_password = "secret"

        with patch(
            "runcoach.pipeline.sync_new_activities",
            side_effect=RuntimeError("network error"),
        ), patch("runcoach.pipeline.sync_planned_workouts", return_value=0):
            result = run_full_pipeline(config, db)

        assert result["errors"] == 1

    def test_planned_sync_failure_is_non_fatal(self, config, db):
        """Planned workout sync failure should not increment errors."""
        config.stryd_email = "user@example.com"
        config.stryd_password = "secret"

        with patch(
            "runcoach.pipeline.sync_new_activities",
            return_value=[],
        ), patch(
            "runcoach.pipeline.sync_planned_workouts",
            side_effect=RuntimeError("calendar error"),
        ):
            result = run_full_pipeline(config, db)

        # errors only counts sync_new_activities failures
        assert result["errors"] == 0
