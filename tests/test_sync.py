"""Tests for sync.py — planned-workout cleanup and activity name fix-up."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from runcoach.config import Config
from runcoach.db import RunCoachDB
from runcoach.sync import sync_new_activities, sync_planned_workouts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stryd_workout(date_str: str, title: str) -> dict:
    """Build a minimal Stryd API workout payload."""
    return {
        "date": f"{date_str}T07:00:00Z",
        "name": title,
        "workout": {"title": title, "desc": "", "type": "easy"},
        "duration": 3600,
        "distance": 10000,
        "stress": 50.0,
    }


def _within_window(days_back: int = 30, days_ahead: int = 30) -> str:
    """Return a date string that falls inside the default sync window."""
    today = datetime.now(timezone.utc).date()
    return (today + timedelta(days=5)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSyncPlannedWorkoutsCleanup:
    """Verify that stale planned workouts are removed during sync (PR #7 feature)."""

    def _make_config(self, tmp_path) -> Config:
        return Config(
            openai_api_key="test-key",
            openai_model="gpt-4o",
            data_dir=tmp_path / "data",
            timezone="UTC",
            stryd_email="test@example.com",
            stryd_password="test-password",
            sync_lookback_days=30,
        )

    def _mock_stryd(self, workouts: list[dict]):
        """Return a context-manager-ready patch for StrydAPI.

        StrydAPI is imported locally inside sync_planned_workouts, so we must
        patch it at its source module rather than on runcoach.sync.
        """
        mock_api = MagicMock()
        mock_api.authenticate.return_value = None
        mock_api.get_planned_workouts.return_value = workouts
        return patch("strydcmd.stryd_api.StrydAPI", return_value=mock_api)

    # ------------------------------------------------------------------
    # Core stale-cleanup tests
    # ------------------------------------------------------------------

    def test_stale_workout_is_removed(self, tmp_path, temp_db):
        """A local workout NOT returned by Stryd within the sync window is deleted."""
        today = datetime.now(timezone.utc).date()
        stale_date = (today + timedelta(days=3)).strftime("%Y-%m-%d")
        active_date = (today + timedelta(days=5)).strftime("%Y-%m-%d")

        # Seed the local DB with both
        temp_db.upsert_planned_workout(date=stale_date, title="Old Tempo Run")
        temp_db.upsert_planned_workout(date=active_date, title="Easy Recovery Run")

        # Stryd only returns the active one (stale was moved/deleted in Stryd)
        stryd_response = [_make_stryd_workout(active_date, "Easy Recovery Run")]

        config = self._make_config(tmp_path)
        with self._mock_stryd(stryd_response):
            upserted = sync_planned_workouts(config, temp_db)

        # Active workout still present
        active = temp_db.get_planned_workout_for_date(active_date)
        assert len(active) == 1
        assert active[0]["title"] == "Easy Recovery Run"

        # Stale workout was removed
        stale = temp_db.get_planned_workout_for_date(stale_date)
        assert stale == [], f"Expected stale workout to be deleted, got: {stale}"

        assert upserted == 1

    def test_workout_moved_to_new_date(self, tmp_path, temp_db):
        """When Stryd moves a workout to a different date, the old entry is removed
        and a new one is created on the correct date."""
        today = datetime.now(timezone.utc).date()
        old_date = (today + timedelta(days=3)).strftime("%Y-%m-%d")
        new_date = (today + timedelta(days=4)).strftime("%Y-%m-%d")
        title = "Threshold Intervals"

        # Local DB has the workout on the old date only
        temp_db.upsert_planned_workout(date=old_date, title=title)

        # Stryd now returns it on the new date (it was moved in the calendar)
        stryd_response = [_make_stryd_workout(new_date, title)]

        config = self._make_config(tmp_path)
        with self._mock_stryd(stryd_response):
            upserted = sync_planned_workouts(config, temp_db)

        assert upserted == 1

        # Old date entry should be gone
        old = temp_db.get_planned_workout_for_date(old_date)
        assert old == [], f"Old-date entry should have been removed, got: {old}"

        # New date entry should exist
        new = temp_db.get_planned_workout_for_date(new_date)
        assert len(new) == 1
        assert new[0]["title"] == title

    def test_workout_outside_window_is_not_touched(self, tmp_path, temp_db):
        """Workouts outside the sync window are never deleted even if not in the Stryd response."""
        today = datetime.now(timezone.utc).date()
        # Way in the past — outside any 30-day lookback
        old_historic_date = (today - timedelta(days=90)).strftime("%Y-%m-%d")
        in_window_date = (today + timedelta(days=5)).strftime("%Y-%m-%d")

        temp_db.upsert_planned_workout(date=old_historic_date, title="Old Historic Run")
        temp_db.upsert_planned_workout(date=in_window_date, title="Current Run")

        # Stryd only returns the in-window one
        stryd_response = [_make_stryd_workout(in_window_date, "Current Run")]

        config = self._make_config(tmp_path)
        with self._mock_stryd(stryd_response):
            sync_planned_workouts(config, temp_db)

        # The historic run should still be in the DB untouched
        historic = temp_db.get_planned_workout_for_date(old_historic_date)
        assert len(historic) == 1, "Historic workout outside the sync window must not be deleted"

    def test_no_removal_when_all_local_workouts_are_active(self, tmp_path, temp_db):
        """If all local workouts are still in the Stryd response, nothing is deleted."""
        today = datetime.now(timezone.utc).date()
        dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(1, 4)]
        titles = ["Easy Run", "Tempo Run", "Long Run"]

        for date, title in zip(dates, titles):
            temp_db.upsert_planned_workout(date=date, title=title)

        stryd_response = [_make_stryd_workout(d, t) for d, t in zip(dates, titles)]

        config = self._make_config(tmp_path)
        with self._mock_stryd(stryd_response):
            upserted = sync_planned_workouts(config, temp_db)

        assert upserted == 3
        for date, title in zip(dates, titles):
            rows = temp_db.get_planned_workout_for_date(date)
            assert len(rows) == 1
            assert rows[0]["title"] == title

    def test_deleted_flag_on_stryd_workout_is_skipped(self, tmp_path, temp_db):
        """Stryd workouts with deleted=True should be completely ignored (not upserted)."""
        today = datetime.now(timezone.utc).date()
        date = (today + timedelta(days=5)).strftime("%Y-%m-%d")

        deleted_workout = _make_stryd_workout(date, "Cancelled Run")
        deleted_workout["deleted"] = True

        config = self._make_config(tmp_path)
        with self._mock_stryd([deleted_workout]):
            upserted = sync_planned_workouts(config, temp_db)

        assert upserted == 0
        rows = temp_db.get_planned_workout_for_date(date)
        assert rows == []


# ---------------------------------------------------------------------------
# Live database check
# ---------------------------------------------------------------------------

class TestLocalDatabaseHasPlannedWorkouts:
    """Sanity-checks against the real local database (read-only)."""

    def test_local_db_has_planned_workouts(self):
        """The real DB has planned workouts — confirms sync has run at least once."""
        from pathlib import Path
        db_path = Path("data/runcoach.db")
        if not db_path.exists():
            pytest.skip("Local database not found")

        db = RunCoachDB(db_path)
        today = datetime.now(timezone.utc).date()
        start = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        end = (today + timedelta(days=31)).strftime("%Y-%m-%d")

        workouts = db.get_planned_workouts_in_range(start, end)
        assert len(workouts) > 0, "Expected planned workouts in sync window in local DB"
        print(f"\nFound {len(workouts)} planned workouts in local DB within sync window:")
        for w in workouts:
            print(f"  {w['date']} — {w['title']} ({w.get('workout_type', '')})")


# ---------------------------------------------------------------------------
# sync_new_activities — activity name fix-up
# ---------------------------------------------------------------------------

def _make_stryd_activity(
    activity_id: int,
    name: str,
    date: datetime,
    fit_content: bytes = b"FITDATA",
) -> dict:
    """Minimal Stryd activity dict."""
    return {
        "id": activity_id,
        "name": name,
        "timestamp": date.timestamp(),
        "distance": 10000.0,
        "moving_time": 3600,
        "stress": 55.0,
    }


def _patch_stryd(activities: list[dict], fit_content: bytes = b"FITDATA"):
    """Patch StrydAPI so get_activities returns *activities* and download writes dummy FIT."""

    def _fake_download(activity_id, output_dir, filename=None):
        p = Path(output_dir) / f"{filename or activity_id}.fit"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(fit_content)
        return str(p)

    mock_api = MagicMock()
    mock_api.authenticate.return_value = None
    mock_api.get_activities.return_value = activities
    mock_api.download_fit_file.side_effect = _fake_download
    return patch("strydcmd.stryd_api.StrydAPI", return_value=mock_api)


class TestSyncNewActivitiesUsesPlannedName:
    """When a planned workout exists for the run date, its title is used as the run name."""

    def _config(self, tmp_path) -> Config:
        return Config(
            openai_api_key="test",
            openai_model="gpt-4o",
            data_dir=tmp_path / "data",
            timezone="UTC",
            stryd_email="a@b.com",
            stryd_password="pw",
        )

    def test_planned_title_used_instead_of_generic_stryd_name(self, tmp_path, temp_db):
        today = datetime(2026, 3, 22, 15, 0, 0, tzinfo=timezone.utc)
        date_str = "2026-03-22"

        temp_db.upsert_planned_workout(date=date_str, title="Day 77 - Long Run")

        activity = _make_stryd_activity(999, "Afternoon Run", today)
        config = self._config(tmp_path)

        with _patch_stryd([activity]):
            new_runs = sync_new_activities(config, temp_db)

        assert len(new_runs) == 1
        assert new_runs[0]["name"] == "Day 77 - Long Run"

        row = temp_db.get_run_by_stryd_id(999)
        assert row["name"] == "Day 77 - Long Run"

    def test_stryd_name_used_when_no_planned_workout(self, tmp_path, temp_db):
        today = datetime(2026, 3, 22, 15, 0, 0, tzinfo=timezone.utc)

        activity = _make_stryd_activity(1000, "Afternoon Run", today)
        config = self._config(tmp_path)

        with _patch_stryd([activity]):
            new_runs = sync_new_activities(config, temp_db)

        assert len(new_runs) == 1
        assert new_runs[0]["name"] == "Afternoon Run"

    def test_planned_title_only_used_if_not_blank(self, tmp_path, temp_db):
        today = datetime(2026, 3, 22, 15, 0, 0, tzinfo=timezone.utc)
        date_str = "2026-03-22"

        # A planned workout with no title
        temp_db.upsert_planned_workout(date=date_str, title="")

        activity = _make_stryd_activity(1001, "Afternoon Run", today)
        config = self._config(tmp_path)

        with _patch_stryd([activity]):
            new_runs = sync_new_activities(config, temp_db)

        assert new_runs[0]["name"] == "Afternoon Run"


class TestSyncNewActivitiesUpdatesStaleNames:
    """When an activity is already in the DB but Stryd has updated its name, the DB is updated."""

    def _config(self, tmp_path) -> Config:
        return Config(
            openai_api_key="test",
            openai_model="gpt-4o",
            data_dir=tmp_path / "data",
            timezone="UTC",
            stryd_email="a@b.com",
            stryd_password="pw",
        )

    def _seed_run(self, temp_db, stryd_id: int, name: str, date_str: str, tmp_path) -> int:
        fit_path = tmp_path / "data" / "activities" / "2026" / "03" / "dummy.fit"
        fit_path.parent.mkdir(parents=True, exist_ok=True)
        fit_path.write_bytes(b"FIT")
        run_id = temp_db.insert_run(
            stryd_activity_id=stryd_id,
            name=name,
            date=date_str,
            fit_path=str(fit_path),
        )
        return run_id

    def test_name_updated_when_stryd_renames_activity(self, tmp_path, temp_db):
        run_id = self._seed_run(temp_db, 555, "Afternoon Run", "2026-03-22", tmp_path)

        # Stryd now returns the same activity with the plan-linked name
        today = datetime(2026, 3, 22, 15, 0, 0, tzinfo=timezone.utc)
        activity = _make_stryd_activity(555, "Day 77 - Long Run", today)

        config = self._config(tmp_path)
        with _patch_stryd([activity]):
            new_runs = sync_new_activities(config, temp_db)

        # No new run inserted (already existed)
        assert new_runs == []

        row = temp_db.get_run_by_stryd_id(555)
        assert row["name"] == "Day 77 - Long Run"

    def test_name_not_updated_when_unchanged(self, tmp_path, temp_db):
        run_id = self._seed_run(temp_db, 556, "Day 77 - Long Run", "2026-03-22", tmp_path)

        today = datetime(2026, 3, 22, 15, 0, 0, tzinfo=timezone.utc)
        activity = _make_stryd_activity(556, "Day 77 - Long Run", today)

        config = self._config(tmp_path)
        with _patch_stryd([activity]):
            new_runs = sync_new_activities(config, temp_db)

        assert new_runs == []
        row = temp_db.get_run_by_stryd_id(556)
        assert row["name"] == "Day 77 - Long Run"
