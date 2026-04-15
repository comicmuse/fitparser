"""Unit tests for runcoach.db module."""

from __future__ import annotations

import pytest
from pathlib import Path

from runcoach.db import RunCoachDB, _now_iso


class TestDatabaseInit:
    """Tests for database initialization."""

    def test_db_init_creates_file(self, tmp_path):
        """Test that initializing the database creates the file."""
        db_path = tmp_path / "test.db"
        assert not db_path.exists()

        db = RunCoachDB(db_path)
        assert db_path.exists()

    def test_db_init_creates_schema(self, tmp_path):
        """Test that initializing creates all required tables."""
        db_path = tmp_path / "test.db"
        db = RunCoachDB(db_path)

        # Check that all tables exist
        with db._connect() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [row[0] for row in cursor.fetchall()]

        assert "runs" in tables
        assert "sync_log" in tables
        assert "planned_workouts" in tables

    def test_db_init_creates_indexes(self, tmp_path):
        """Test that indexes are created."""
        db_path = tmp_path / "test.db"
        db = RunCoachDB(db_path)

        with db._connect() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
            )
            indexes = [row[0] for row in cursor.fetchall()]

        assert "idx_runs_date" in indexes
        assert "idx_runs_stage" in indexes
        assert "idx_planned_date_title" in indexes
        assert "idx_planned_date" in indexes

    def test_db_double_init_safe(self, tmp_path):
        """Test that initializing twice doesn't break anything."""
        db_path = tmp_path / "test.db"
        db1 = RunCoachDB(db_path)
        db2 = RunCoachDB(db_path)

        # Both should work fine
        runs1 = db1.get_all_runs()
        runs2 = db2.get_all_runs()
        assert runs1 == runs2 == []


class TestRunsCRUD:
    """Tests for runs table CRUD operations."""

    def test_insert_and_get_run(self, temp_db):
        """Test inserting and retrieving a run."""
        run_id = temp_db.insert_run(
            stryd_activity_id=12345,
            name="Test Run",
            date="2026-03-01",
            fit_path="activities/2026/03/test.fit",
            distance_m=10000,
            moving_time_s=3000,
        )

        assert run_id > 0

        # Get by ID
        run = temp_db.get_run(run_id)
        assert run is not None
        assert run["id"] == run_id
        assert run["stryd_activity_id"] == 12345
        assert run["name"] == "Test Run"
        assert run["date"] == "2026-03-01"
        assert run["fit_path"] == "activities/2026/03/test.fit"
        assert run["distance_m"] == 10000
        assert run["moving_time_s"] == 3000
        assert run["stage"] == "synced"
        assert run["is_manual_upload"] == 0

        # Get by Stryd ID
        run2 = temp_db.get_run_by_stryd_id(12345)
        assert run2["id"] == run_id

    def test_insert_manual_run(self, temp_db):
        """Test inserting a manual upload run."""
        run_id = temp_db.insert_manual_run(
            name="Manual Upload",
            date="2026-03-01",
            fit_path="activities/2026/03/manual.fit",
            distance_m=5000,
            moving_time_s=1500,
        )

        run = temp_db.get_run(run_id)
        assert run is not None
        assert run["stryd_activity_id"] is None
        assert run["is_manual_upload"] == 1
        assert run["name"] == "Manual Upload"
        assert run["stage"] == "synced"

    def test_get_run_by_fit_path(self, temp_db):
        """Test retrieving a run by its FIT path."""
        fit_path = "activities/2026/03/test.fit"
        run_id = temp_db.insert_run(
            stryd_activity_id=12345,
            name="Test Run",
            date="2026-03-01",
            fit_path=fit_path,
        )

        run = temp_db.get_run_by_fit_path(fit_path)
        assert run is not None
        assert run["id"] == run_id

        # Non-existent path should return None
        run2 = temp_db.get_run_by_fit_path("nonexistent.fit")
        assert run2 is None

    def test_get_all_runs(self, temp_db):
        """Test retrieving all runs."""
        # Start with empty database
        assert temp_db.get_all_runs() == []

        # Insert multiple runs
        temp_db.insert_run(
            stryd_activity_id=1,
            name="Run 1",
            date="2026-03-01",
            fit_path="activities/1.fit",
        )
        temp_db.insert_run(
            stryd_activity_id=2,
            name="Run 2",
            date="2026-03-02",
            fit_path="activities/2.fit",
        )
        temp_db.insert_run(
            stryd_activity_id=3,
            name="Run 3",
            date="2026-03-03",
            fit_path="activities/3.fit",
        )

        runs = temp_db.get_all_runs()
        assert len(runs) == 3

        # Should be ordered by date DESC
        assert runs[0]["date"] == "2026-03-03"
        assert runs[1]["date"] == "2026-03-02"
        assert runs[2]["date"] == "2026-03-01"

    def test_update_parsed(self, temp_db):
        """Test updating a run to parsed stage."""
        run_id = temp_db.insert_run(
            stryd_activity_id=12345,
            name="Test Run",
            date="2026-03-01",
            fit_path="activities/test.fit",
        )

        # Update to parsed
        temp_db.update_parsed(
            run_id=run_id,
            yaml_path="activities/test.yaml",
            avg_power_w=250.5,
            avg_hr=150,
            workout_name="Tempo Run",
        )

        run = temp_db.get_run(run_id)
        assert run["stage"] == "parsed"
        assert run["yaml_path"] == "activities/test.yaml"
        assert run["avg_power_w"] == 250.5
        assert run["avg_hr"] == 150
        assert run["workout_name"] == "Tempo Run"
        assert run["parsed_at"] is not None

    def test_update_analyzed(self, temp_db):
        """Test updating a run to analyzed stage."""
        run_id = temp_db.insert_run(
            stryd_activity_id=12345,
            name="Test Run",
            date="2026-03-01",
            fit_path="activities/test.fit",
        )

        # Update to analyzed
        temp_db.update_analyzed(
            run_id=run_id,
            md_path="activities/test.md",
            commentary="Great workout!",
            model_used="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
        )

        run = temp_db.get_run(run_id)
        assert run["stage"] == "analyzed"
        assert run["md_path"] == "activities/test.md"
        assert run["commentary"] == "Great workout!"
        assert run["model_used"] == "gpt-4o"
        assert run["prompt_tokens"] == 1000
        assert run["completion_tokens"] == 500
        assert run["analyzed_at"] is not None

    def test_update_error(self, temp_db):
        """Test updating a run to error stage."""
        run_id = temp_db.insert_run(
            stryd_activity_id=12345,
            name="Test Run",
            date="2026-03-01",
            fit_path="activities/test.fit",
        )

        temp_db.update_error(run_id, "Parse failed")

        run = temp_db.get_run(run_id)
        assert run["stage"] == "error"
        assert run["error_message"] == "Parse failed"

    def test_get_pending_runs(self, temp_db):
        """Test retrieving pending runs by stage."""
        # Insert runs at different stages
        run1_id = temp_db.insert_run(12345, "Run 1", "2026-03-01", "1.fit")
        run2_id = temp_db.insert_run(12346, "Run 2", "2026-03-02", "2.fit")
        run3_id = temp_db.insert_run(12347, "Run 3", "2026-03-03", "3.fit")

        temp_db.update_parsed(run2_id, "2.yaml", 200, 150, "Run 2")

        # Get pending synced runs
        synced = temp_db.get_pending_runs("synced")
        assert len(synced) == 2
        assert synced[0]["id"] == run1_id
        assert synced[1]["id"] == run3_id

        # Get pending parsed runs
        parsed = temp_db.get_pending_runs("parsed")
        assert len(parsed) == 1
        assert parsed[0]["id"] == run2_id

    def test_get_pending_runs_with_date_filter(self, temp_db):
        """Test retrieving pending runs from a specific date."""
        temp_db.insert_run(12345, "Run 1", "2026-03-01", "1.fit")
        temp_db.insert_run(12346, "Run 2", "2026-03-05", "2.fit")
        temp_db.insert_run(12347, "Run 3", "2026-03-10", "3.fit")

        # Get runs from 2026-03-05 onwards
        pending = temp_db.get_pending_runs("synced", date_from="2026-03-05")
        assert len(pending) == 2
        assert pending[0]["date"] == "2026-03-05"
        assert pending[1]["date"] == "2026-03-10"

    def test_reset_errors_to_synced(self, temp_db):
        """Test resetting error runs back to synced."""
        run1_id = temp_db.insert_run(12345, "Run 1", "2026-03-01", "1.fit")
        run2_id = temp_db.insert_run(12346, "Run 2", "2026-03-02", "2.fit")

        # Set both to error
        temp_db.update_error(run1_id, "Error 1")
        temp_db.update_error(run2_id, "Error 2")

        # Reset errors
        count = temp_db.reset_errors_to_synced()
        assert count == 2

        # Check they're back to synced
        run1 = temp_db.get_run(run1_id)
        run2 = temp_db.get_run(run2_id)
        assert run1["stage"] == "synced"
        assert run2["stage"] == "synced"
        assert run1["error_message"] is None
        assert run2["error_message"] is None


class TestSyncLog:
    """Tests for sync_log table operations."""

    def test_sync_log_workflow(self, temp_db):
        """Test complete sync log workflow."""
        # Start a sync
        log_id = temp_db.start_sync_log()
        assert log_id > 0

        log = temp_db.get_last_sync()
        assert log is not None
        assert log["id"] == log_id
        assert log["status"] == "running"
        assert log["finished_at"] is None

        # Finish the sync
        temp_db.finish_sync_log(
            log_id=log_id,
            status="success",
            activities_found=10,
            activities_new=2,
        )

        log = temp_db.get_last_sync()
        assert log["status"] == "success"
        assert log["activities_found"] == 10
        assert log["activities_new"] == 2
        assert log["finished_at"] is not None
        assert log["error_message"] is None

    def test_sync_log_with_error(self, temp_db):
        """Test sync log with error."""
        log_id = temp_db.start_sync_log()

        temp_db.finish_sync_log(
            log_id=log_id,
            status="failed",
            error_message="Authentication failed",
        )

        log = temp_db.get_last_sync()
        assert log["status"] == "failed"
        assert log["error_message"] == "Authentication failed"

    def test_get_last_sync_empty(self, temp_db):
        """Test getting last sync when none exist."""
        log = temp_db.get_last_sync()
        assert log is None


class TestSyncStats:
    """Tests for sync statistics."""

    def test_get_sync_stats(self, temp_db):
        """Test retrieving sync statistics."""
        # Start with empty database
        stats = temp_db.get_sync_stats()
        assert stats["total_runs"] == 0
        assert stats["pending_parse"] == 0
        assert stats["pending_analyze"] == 0
        assert stats["errors"] == 0

        # Add runs at different stages
        run1_id = temp_db.insert_run(1, "Run 1", "2026-03-01", "1.fit")
        run2_id = temp_db.insert_run(2, "Run 2", "2026-03-02", "2.fit")
        run3_id = temp_db.insert_run(3, "Run 3", "2026-03-03", "3.fit")
        run4_id = temp_db.insert_run(4, "Run 4", "2026-03-04", "4.fit")

        temp_db.update_parsed(run2_id, "2.yaml", 200, 150, "Run 2")
        temp_db.update_analyzed(run3_id, "3.md", "Commentary", "gpt-4o")
        temp_db.update_error(run4_id, "Parse failed")

        stats = temp_db.get_sync_stats()
        assert stats["total_runs"] == 4
        assert stats["pending_parse"] == 1  # run1
        assert stats["pending_analyze"] == 1  # run2
        assert stats["errors"] == 1  # run4


class TestPlannedWorkouts:
    """Tests for planned_workouts table operations."""

    def test_upsert_planned_workout(self, temp_db):
        """Test inserting and updating planned workouts."""
        # Insert new workout
        workout_id = temp_db.upsert_planned_workout(
            date="2026-03-01",
            title="Tempo Run",
            description="30 min at tempo",
            workout_type="tempo",
            duration_s=1800,
            distance_m=6000,
            stress=75.0,
        )

        assert workout_id > 0

        # Get the workout
        workouts = temp_db.get_planned_workout_for_date("2026-03-01")
        assert len(workouts) == 1
        workout = workouts[0]
        assert workout["title"] == "Tempo Run"
        assert workout["duration_s"] == 1800
        assert workout["stress"] == 75.0

        # Update the same workout (same date+title)
        temp_db.upsert_planned_workout(
            date="2026-03-01",
            title="Tempo Run",
            description="40 min at tempo",  # Changed
            duration_s=2400,  # Changed
            stress=90.0,  # Changed
        )

        # Should still be only one workout
        workouts = temp_db.get_planned_workout_for_date("2026-03-01")
        assert len(workouts) == 1
        workout = workouts[0]
        assert workout["description"] == "40 min at tempo"
        assert workout["duration_s"] == 2400
        assert workout["stress"] == 90.0

    def test_get_planned_workout_for_date(self, temp_db):
        """Test retrieving planned workouts for a specific date."""
        # No workouts initially
        workouts = temp_db.get_planned_workout_for_date("2026-03-01")
        assert workouts == []

        # Add multiple workouts for same date
        temp_db.upsert_planned_workout(
            date="2026-03-01",
            title="AM Run",
            workout_type="easy",
        )
        temp_db.upsert_planned_workout(
            date="2026-03-01",
            title="PM Run",
            workout_type="tempo",
        )

        workouts = temp_db.get_planned_workout_for_date("2026-03-01")
        assert len(workouts) == 2

    def test_get_upcoming_planned_workouts(self, temp_db):
        """Test retrieving upcoming planned workouts."""
        temp_db.upsert_planned_workout(date="2026-03-01", title="Run 1")
        temp_db.upsert_planned_workout(date="2026-03-05", title="Run 2")
        temp_db.upsert_planned_workout(date="2026-03-10", title="Run 3")
        temp_db.upsert_planned_workout(date="2026-03-15", title="Run 4")

        # Get 2 workouts from 2026-03-05
        upcoming = temp_db.get_upcoming_planned_workouts(from_date="2026-03-05", limit=2)
        assert len(upcoming) == 2
        assert upcoming[0]["date"] == "2026-03-05"
        assert upcoming[1]["date"] == "2026-03-10"

    def test_get_planned_workouts_in_range(self, temp_db):
        """Test retrieving planned workouts in a date range."""
        temp_db.upsert_planned_workout(date="2026-03-01", title="Run 1")
        temp_db.upsert_planned_workout(date="2026-03-05", title="Run 2")
        temp_db.upsert_planned_workout(date="2026-03-10", title="Run 3")
        temp_db.upsert_planned_workout(date="2026-03-15", title="Run 4")

        # Get workouts from 2026-03-05 to 2026-03-12 (exclusive)
        in_range = temp_db.get_planned_workouts_in_range("2026-03-05", "2026-03-12")
        assert len(in_range) == 2
        assert in_range[0]["date"] == "2026-03-05"
        assert in_range[1]["date"] == "2026-03-10"

    def test_delete_planned_workout(self, temp_db):
        """Test deleting a planned workout by date and title."""
        temp_db.upsert_planned_workout(
            date="2026-03-01",
            title="Long Run",
            workout_type="long",
            duration_s=3600,
        )

        # Verify it exists
        workouts = temp_db.get_planned_workout_for_date("2026-03-01")
        assert len(workouts) == 1

        # Delete it
        deleted = temp_db.delete_planned_workout("2026-03-01", "Long Run")
        assert deleted is True

        # Verify it is gone
        workouts = temp_db.get_planned_workout_for_date("2026-03-01")
        assert workouts == []

    def test_delete_planned_workout_not_found(self, temp_db):
        """Test deleting a non-existent workout returns False."""
        deleted = temp_db.delete_planned_workout("2026-03-01", "Nonexistent Run")
        assert deleted is False

    def test_delete_planned_workout_only_matching(self, temp_db):
        """Test that delete only removes the matching workout, not others on the same date."""
        temp_db.upsert_planned_workout(date="2026-03-01", title="AM Run")
        temp_db.upsert_planned_workout(date="2026-03-01", title="PM Run")

        deleted = temp_db.delete_planned_workout("2026-03-01", "AM Run")
        assert deleted is True

        remaining = temp_db.get_planned_workout_for_date("2026-03-01")
        assert len(remaining) == 1
        assert remaining[0]["title"] == "PM Run"


class TestPagination:
    """Tests for pagination methods."""

    def test_get_runs_paginated(self, temp_db):
        """Test paginated run retrieval."""
        # Insert 15 runs
        for i in range(1, 16):
            temp_db.insert_run(
                stryd_activity_id=i,
                name=f"Run {i}",
                date=f"2026-03-{i:02d}",
                fit_path=f"{i}.fit",
            )

        # Get first page (10 runs)
        page1 = temp_db.get_runs_paginated(limit=10, offset=0)
        assert len(page1) == 10
        assert page1[0]["date"] == "2026-03-15"  # Most recent first

        # Get second page (5 runs)
        page2 = temp_db.get_runs_paginated(limit=10, offset=10)
        assert len(page2) == 5
        assert page2[0]["date"] == "2026-03-05"

    def test_count_runs(self, temp_db):
        """Test counting total runs."""
        assert temp_db.count_runs() == 0

        temp_db.insert_run(1, "Run 1", "2026-03-01", "1.fit")
        temp_db.insert_run(2, "Run 2", "2026-03-02", "2.fit")

        assert temp_db.count_runs() == 2

    def test_get_upcoming_planned_workouts_paged(self, temp_db):
        """Test paginated upcoming workouts."""
        for i in range(1, 16):
            temp_db.upsert_planned_workout(
                date=f"2026-03-{i:02d}",
                title=f"Workout {i}",
            )

        # First page
        page1 = temp_db.get_upcoming_planned_workouts_paged(
            from_date="2026-03-01", limit=10, offset=0
        )
        assert len(page1) == 10
        assert page1[0]["date"] == "2026-03-01"

        # Second page
        page2 = temp_db.get_upcoming_planned_workouts_paged(
            from_date="2026-03-01", limit=10, offset=10
        )
        assert len(page2) == 5

    def test_count_planned_workouts(self, temp_db):
        """Test counting planned workouts."""
        for i in range(1, 11):
            temp_db.upsert_planned_workout(
                date=f"2026-03-{i:02d}",
                title=f"Workout {i}",
            )

        assert temp_db.count_upcoming_planned_workouts("2026-03-01") == 10
        assert temp_db.count_upcoming_planned_workouts("2026-03-06") == 5
        assert temp_db.count_past_planned_workouts("2026-03-06") == 5


class TestGetRunsInDateRange:
    """Tests for date range queries."""

    def test_get_runs_in_date_range(self, temp_db):
        """Test retrieving runs within a date range."""
        temp_db.insert_run(1, "Run 1", "2026-03-01", "1.fit")
        temp_db.insert_run(2, "Run 2", "2026-03-05", "2.fit")
        temp_db.insert_run(3, "Run 3", "2026-03-10", "3.fit")
        temp_db.insert_run(4, "Run 4", "2026-03-15", "4.fit")

        # Get runs from 2026-03-05 to 2026-03-12 (exclusive)
        runs = temp_db.get_runs_in_date_range("2026-03-05", "2026-03-12")
        assert len(runs) == 2
        assert runs[0]["date"] == "2026-03-05"
        assert runs[1]["date"] == "2026-03-10"


class TestRaceGoal:
    """Tests for race goal CRUD operations."""

    def test_get_race_goal_default(self, temp_db):
        """Test that new users have no race goal set."""
        user_id = temp_db.get_default_user_id()
        goal = temp_db.get_race_goal(user_id)
        assert goal["race_date"] is None
        assert goal["race_distance"] is None

    def test_update_and_get_race_goal(self, temp_db):
        """Test setting and retrieving a race goal."""
        user_id = temp_db.get_default_user_id()
        temp_db.update_race_goal(user_id, "2026-10-04", "Marathon")

        goal = temp_db.get_race_goal(user_id)
        assert goal["race_date"] == "2026-10-04"
        assert goal["race_distance"] == "Marathon"

    def test_clear_race_goal(self, temp_db):
        """Test clearing a race goal by passing None values."""
        user_id = temp_db.get_default_user_id()
        temp_db.update_race_goal(user_id, "2026-10-04", "Marathon")

        # Clear it
        temp_db.update_race_goal(user_id, None, None)
        goal = temp_db.get_race_goal(user_id)
        assert goal["race_date"] is None
        assert goal["race_distance"] is None

    def test_update_race_goal_overwrites(self, temp_db):
        """Test that updating overwrites an existing race goal."""
        user_id = temp_db.get_default_user_id()
        temp_db.update_race_goal(user_id, "2026-10-04", "Marathon")
        temp_db.update_race_goal(user_id, "2026-06-07", "Half Marathon")

        goal = temp_db.get_race_goal(user_id)
        assert goal["race_date"] == "2026-06-07"
        assert goal["race_distance"] == "Half Marathon"
