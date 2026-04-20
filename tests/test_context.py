"""Unit tests for runcoach.context module."""

from __future__ import annotations

import pytest
from datetime import date, timedelta
from pathlib import Path
import yaml

from runcoach.context import compute_rss, build_weekly_context, _classify_workout_type, build_training_summary
from runcoach.db import RunCoachDB


class TestComputeRSS:
    """Tests for RSS calculation."""

    def test_compute_rss_normal(self):
        """Test standard RSS calculation."""
        # RSS = (duration_s / 3600) * (avg_power / CP)^2 * 100
        # Example: 60 min at 200W with CP=250W
        # RSS = 1 * (200/250)^2 * 100 = 1 * 0.64 * 100 = 64
        rss = compute_rss(avg_power=200, critical_power=250, duration_min=60)
        assert rss == pytest.approx(64.0, rel=0.01)

    def test_compute_rss_zero_cp(self):
        """Test RSS calculation with zero critical power."""
        rss = compute_rss(avg_power=200, critical_power=0, duration_min=60)
        assert rss == 0.0

    def test_compute_rss_negative_cp(self):
        """Test RSS calculation with negative critical power."""
        rss = compute_rss(avg_power=200, critical_power=-100, duration_min=60)
        assert rss == 0.0

    def test_compute_rss_zero_power(self):
        """Test RSS calculation with zero average power."""
        rss = compute_rss(avg_power=0, critical_power=250, duration_min=60)
        assert rss == 0.0

    def test_compute_rss_high_intensity(self):
        """Test RSS calculation at high intensity (above CP)."""
        # 30 min at 300W with CP=250W
        # RSS = 0.5 * (300/250)^2 * 100 = 0.5 * 1.44 * 100 = 72
        rss = compute_rss(avg_power=300, critical_power=250, duration_min=30)
        assert rss == pytest.approx(72.0, rel=0.01)

    def test_compute_rss_low_intensity(self):
        """Test RSS calculation at low intensity (below CP)."""
        # 120 min at 150W with CP=250W
        # RSS = 2 * (150/250)^2 * 100 = 2 * 0.36 * 100 = 72
        rss = compute_rss(avg_power=150, critical_power=250, duration_min=120)
        assert rss == pytest.approx(72.0, rel=0.01)


class TestClassifyWorkoutType:
    """Tests for workout type classification."""

    def test_classify_recovery(self):
        """Test classification of recovery runs."""
        assert _classify_workout_type("recovery run", {}) == "easy/recovery"
        assert _classify_workout_type("Easy Run", {}) == "easy/recovery"
        assert _classify_workout_type("ez aerobic", {}) == "easy/recovery"

    def test_classify_long_run(self):
        """Test classification of long runs."""
        assert _classify_workout_type("Long Run", {}) == "long run"
        assert _classify_workout_type("Sunday long run", {}) == "long run"

    def test_classify_tempo(self):
        """Test classification of tempo runs."""
        assert _classify_workout_type("HM Power Tempo", {}) == "tempo"
        assert _classify_workout_type("tempo workout", {}) == "tempo"

    def test_classify_intervals(self):
        """Test classification of interval workouts."""
        assert _classify_workout_type("interval workout", {}) == "intervals"
        assert _classify_workout_type("supra-threshold interval workout", {}) == "intervals"

    def test_classify_threshold(self):
        """Test classification of threshold workouts."""
        assert _classify_workout_type("threshold run", {}) == "threshold"
        assert _classify_workout_type("near-threshold workout", {}) == "threshold"

    def test_classify_race(self):
        """Test classification of races."""
        assert _classify_workout_type("marathon race", {}) == "race"
        assert _classify_workout_type("Race day", {}) == "race"

    def test_classify_test(self):
        """Test classification of test workouts."""
        assert _classify_workout_type("CP estimation test", {}) == "test"
        assert _classify_workout_type("testing run", {}) == "test"

    def test_classify_structured_with_blocks(self):
        """Test classification based on block structure."""
        blocks = {
            "block_1": {"type": "warmup"},
            "block_2": {"type": "active"},
            "block_3": {"type": "cooldown"},
        }
        assert _classify_workout_type("unknown workout", blocks) == "structured"

    def test_classify_fallback(self):
        """Test fallback classification."""
        assert _classify_workout_type("morning jog", {}) == "run"


class TestBuildWeeklyContext:
    """Tests for weekly context building."""

    def test_build_weekly_context_empty_db(self, temp_db, tmp_path):
        """Test context building with no runs in database."""
        context = build_weekly_context(
            run_date="2026-03-01",
            data_dir=tmp_path,
            db=temp_db,
        )

        assert "training_context" in context
        tc = context["training_context"]

        # Should have structure even with no data
        assert tc["days"] == 7
        assert tc["summary"]["total_runs"] == 0
        assert tc["summary"]["rest_days"] == 7
        assert tc["summary"]["total_distance_km"] == 0.0
        assert tc["summary"]["total_duration_min"] == 0.0

        # Training load should be zero
        assert tc["training_load"]["atl_7d_avg_daily_rss"] == 0
        assert tc["training_load"]["ctl_42d_avg_daily_rss"] == 0
        assert tc["training_load"]["rsb_running_stress_balance"] == 0

        # Activities list should be empty
        assert tc["activities"] == []

    def test_build_weekly_context_with_runs(self, temp_db, tmp_path):
        """Test context building with runs in the 7-day window."""
        # Create a data directory structure
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        # Create a sample YAML file
        yaml_dir = data_dir / "activities" / "2026" / "02"
        yaml_dir.mkdir(parents=True)
        yaml_path = yaml_dir / "20260225_test_run" / "20260225_test_run.yaml"
        yaml_path.parent.mkdir(parents=True)

        sample_yaml = {
            "date": "2026-02-25",
            "name": "Test Run",
            "distance_km": 10.0,
            "duration_min": 50.0,
            "avg_power": 200,
            "avg_hr": 150,
            "critical_power": 250,
            "blocks": {
                "block_1": {"type": "warmup"},
                "block_2": {"type": "active"},
            }
        }
        with open(yaml_path, "w") as f:
            yaml.dump(sample_yaml, f)

        # Insert run into database
        temp_db.insert_run(
            stryd_activity_id=12345,
            name="Test Run",
            date="2026-02-25",
            distance_m=10000,
            moving_time_s=3000,
            fit_path="activities/2026/02/20260225_test_run/20260225_test_run.fit",
        )

        # Update to parsed stage with yaml_path
        runs = temp_db.get_all_runs(1)
        temp_db.update_parsed(
            run_id=runs[0]["id"],
            yaml_path="activities/2026/02/20260225_test_run/20260225_test_run.yaml",
            avg_power_w=200,
            avg_hr=150,
            workout_name="Test Run",
        )

        # Build context for one week after the run
        context = build_weekly_context(
            run_date="2026-03-01",
            data_dir=data_dir,
            db=temp_db,
        )

        tc = context["training_context"]

        # Should have one run in the window
        assert tc["summary"]["total_runs"] == 1
        assert tc["summary"]["rest_days"] == 6
        assert tc["summary"]["total_distance_km"] == 10.0
        assert tc["summary"]["total_duration_min"] == 50.0

        # Check RSS calculation: (50/60) * (200/250)^2 * 100 = 0.833 * 0.64 * 100 = 53.3
        expected_rss = (50/60) * (200/250)**2 * 100
        assert tc["summary"]["total_rss"] == pytest.approx(expected_rss, rel=0.1)

        # Check activities
        assert len(tc["activities"]) == 1
        activity = tc["activities"][0]
        assert activity["name"] == "Test Run"
        assert activity["distance_km"] == 10.0
        assert activity["duration_min"] == 50.0
        assert activity["avg_power_w"] == 200
        assert activity["avg_hr_bpm"] == 150

        # Training load
        # ATL = total_rss / 7 (7-day average)
        # CTL = total_rss / 42 (42-day average, but we only have 1 run)
        # Since the run is within the 42-day window, it contributes to CTL
        # but CTL is averaged over 42 days, so CTL = total_rss / 42
        atl = tc["training_load"]["atl_7d_avg_daily_rss"]
        ctl = tc["training_load"]["ctl_42d_avg_daily_rss"]
        assert atl > 0
        # CTL should be less than ATL since it's averaged over more days
        assert ctl < atl
        assert tc["training_load"]["rsb_running_stress_balance"] == pytest.approx(ctl - atl, rel=0.1)

    def test_build_weekly_context_excludes_future_runs(self, temp_db, tmp_path):
        """Test that runs on or after the target date are excluded."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        # Create YAML for a run on the target date
        yaml_dir = data_dir / "activities" / "2026" / "03"
        yaml_dir.mkdir(parents=True)
        yaml_path = yaml_dir / "20260301_future_run" / "20260301_future_run.yaml"
        yaml_path.parent.mkdir(parents=True)

        sample_yaml = {
            "date": "2026-03-01",
            "name": "Future Run",
            "distance_km": 5.0,
            "duration_min": 25.0,
            "avg_power": 180,
            "critical_power": 250,
        }
        with open(yaml_path, "w") as f:
            yaml.dump(sample_yaml, f)

        temp_db.insert_run(
            stryd_activity_id=12346,
            name="Future Run",
            date="2026-03-01",
            distance_m=5000,
            moving_time_s=1500,
            fit_path="activities/2026/03/20260301_future_run/20260301_future_run.fit",
        )

        runs = temp_db.get_all_runs(1)
        temp_db.update_parsed(
            run_id=runs[0]["id"],
            yaml_path="activities/2026/03/20260301_future_run/20260301_future_run.yaml",
            avg_power_w=180,
            avg_hr=None,
            workout_name="Future Run",
        )

        # Build context for the same date as the run
        context = build_weekly_context(
            run_date="2026-03-01",
            data_dir=data_dir,
            db=temp_db,
        )

        # Run on target date should be excluded
        assert context["training_context"]["summary"]["total_runs"] == 0
        assert context["training_context"]["activities"] == []

    def test_build_weekly_context_with_planned_workout(self, temp_db, tmp_path):
        """Test context includes prescribed workout when available."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        # Insert a planned workout for the target date
        temp_db.upsert_planned_workout(
            date="2026-03-01",
            title="Tempo Run",
            description="30 min at tempo pace",
            workout_type="tempo",
            duration_s=1800,
            distance_m=6000,
            stress=75.0,
        )

        context = build_weekly_context(
            run_date="2026-03-01",
            data_dir=data_dir,
            db=temp_db,
        )

        tc = context["training_context"]

        # Should have prescribed workout
        assert "prescribed_workout" in tc
        pw = tc["prescribed_workout"]
        assert pw["title"] == "Tempo Run"
        assert pw["type"] == "tempo"
        assert pw["planned_duration_min"] == 30.0
        assert pw["planned_distance_km"] == 6.0
        assert pw["planned_stress"] == 75.0

    def test_build_weekly_context_with_upcoming_workouts(self, temp_db, tmp_path):
        """Test context includes next 2 scheduled workouts."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        # Insert upcoming planned workouts
        temp_db.upsert_planned_workout(
            date="2026-03-02",
            title="Recovery Run",
            workout_type="recovery",
            duration_s=2400,
            distance_m=5000,
        )

        temp_db.upsert_planned_workout(
            date="2026-03-03",
            title="Interval Workout",
            workout_type="intervals",
            duration_s=3600,
            distance_m=8000,
        )

        context = build_weekly_context(
            run_date="2026-03-01",
            data_dir=data_dir,
            db=temp_db,
        )

        tc = context["training_context"]

        # Should have next scheduled workouts
        assert "next_scheduled_workouts" in tc
        next_workouts = tc["next_scheduled_workouts"]
        assert len(next_workouts) == 2

        assert next_workouts[0]["date"] == "2026-03-02"
        assert next_workouts[0]["title"] == "Recovery Run"
        assert next_workouts[0]["type"] == "recovery"

        assert next_workouts[1]["date"] == "2026-03-03"
        assert next_workouts[1]["title"] == "Interval Workout"
        assert next_workouts[1]["type"] == "intervals"

    def test_build_weekly_context_with_cp_change(self, temp_db, tmp_path):
        """Test context detects and reports CP changes."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        # Create a run before the target date with CP=200
        run_dir_1 = data_dir / "run1"
        run_dir_1.mkdir()
        yaml_file_1 = run_dir_1 / "run1.yaml"
        yaml_file_1.write_text(
            "date: '2026-02-25'\n"
            "workout_name: Test Run 1\n"
            "distance_km: 5.0\n"
            "duration_min: 30.0\n"
            "avg_power: 180\n"
            "avg_hr: 145\n"
            "critical_power: 200\n"
            "blocks: {}\n"
        )

        temp_db.insert_run(
            stryd_activity_id=1,
            name="Test Run 1",
            date="2026-02-25",
            fit_path="run1/run1.fit",
        )
        temp_db.update_parsed(
            run_id=1,
            yaml_path="run1/run1.yaml",
            avg_power_w=180,
            avg_hr=145,
            workout_name="Test Run 1",
        )

        # Build context for a run on 2026-03-01 with NEW CP=210
        context = build_weekly_context(
            run_date="2026-03-01",
            data_dir=data_dir,
            db=temp_db,
            current_cp=210,  # New CP value
        )

        tc = context["training_context"]

        # Should have current CP
        assert tc["critical_power_w"] == 210

        # Should detect CP change
        assert "cp_update" in tc
        cp_update = tc["cp_update"]
        assert cp_update["previous_cp_w"] == 200
        assert cp_update["current_cp_w"] == 210
        assert cp_update["change_w"] == 10
        assert cp_update["change_pct"] == 5.0
        assert "increased from 200W to 210W" in cp_update["note"]

    def test_build_weekly_context_with_cp_decrease(self, temp_db, tmp_path):
        """Test context detects CP decreases."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        # Create a run before the target date with CP=210
        run_dir_1 = data_dir / "run1"
        run_dir_1.mkdir()
        yaml_file_1 = run_dir_1 / "run1.yaml"
        yaml_file_1.write_text(
            "date: '2026-02-25'\n"
            "workout_name: Test Run 1\n"
            "distance_km: 5.0\n"
            "duration_min: 30.0\n"
            "avg_power: 190\n"
            "avg_hr: 145\n"
            "critical_power: 210\n"
            "blocks: {}\n"
        )

        temp_db.insert_run(
            stryd_activity_id=1,
            name="Test Run 1",
            date="2026-02-25",
            fit_path="run1/run1.fit",
        )
        temp_db.update_parsed(
            run_id=1,
            yaml_path="run1/run1.yaml",
            avg_power_w=190,
            avg_hr=145,
            workout_name="Test Run 1",
        )

        # Build context for a run on 2026-03-01 with DECREASED CP=200
        context = build_weekly_context(
            run_date="2026-03-01",
            data_dir=data_dir,
            db=temp_db,
            current_cp=200,  # Decreased CP value
        )

        tc = context["training_context"]

        # Should have current CP
        assert tc["critical_power_w"] == 200

        # Should detect CP change
        assert "cp_update" in tc
        cp_update = tc["cp_update"]
        assert cp_update["previous_cp_w"] == 210
        assert cp_update["current_cp_w"] == 200
        assert cp_update["change_w"] == -10
        assert cp_update["change_pct"] == pytest.approx(-4.76, rel=0.01)
        assert "decreased from 210W to 200W" in cp_update["note"]

    def test_build_weekly_context_no_cp_change(self, temp_db, tmp_path):
        """Test context when CP stays the same."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        # Create a run before the target date with CP=200
        run_dir_1 = data_dir / "run1"
        run_dir_1.mkdir()
        yaml_file_1 = run_dir_1 / "run1.yaml"
        yaml_file_1.write_text(
            "date: '2026-02-25'\n"
            "workout_name: Test Run 1\n"
            "distance_km: 5.0\n"
            "duration_min: 30.0\n"
            "avg_power: 180\n"
            "avg_hr: 145\n"
            "critical_power: 200\n"
            "blocks: {}\n"
        )

        temp_db.insert_run(
            stryd_activity_id=1,
            name="Test Run 1",
            date="2026-02-25",
            fit_path="run1/run1.fit",
        )
        temp_db.update_parsed(
            run_id=1,
            yaml_path="run1/run1.yaml",
            avg_power_w=180,
            avg_hr=145,
            workout_name="Test Run 1",
        )

        # Build context for a run on 2026-03-01 with SAME CP=200
        context = build_weekly_context(
            run_date="2026-03-01",
            data_dir=data_dir,
            db=temp_db,
            current_cp=200,  # Same CP value
        )

        tc = context["training_context"]

        # Should have current CP
        assert tc["critical_power_w"] == 200

        # Should NOT have cp_update since it didn't change
        assert "cp_update" not in tc


class TestBuildTrainingSummary:
    """Tests for the rolling training summary metrics function."""

    def _insert_run(self, db, date_str, distance_m=10000, stryd_rss=100.0, user_id=1):
        run_id = db.insert_run(
            stryd_activity_id=None,
            name="Test Run",
            date=date_str,
            fit_path=f"activities/{date_str}.fit",
            user_id=user_id,
            distance_m=distance_m,
            stryd_rss=stryd_rss,
        )
        db.update_parsed(run_id, f"activities/{date_str}.yaml", 200.0, 145, "Test Run")
        return run_id

    def test_empty_db_returns_structure(self, temp_db):
        result = build_training_summary(db=temp_db, as_of_date=date(2026, 4, 20))
        ts = result["training_summary"]
        assert ts["as_of"] == "2026-04-20"
        assert "windows" in ts
        assert "1_week" in ts["windows"]
        assert "4_week_avg" in ts["windows"]
        assert "16_week_avg" in ts["windows"]
        assert "rsb_history" in ts
        assert len(ts["rsb_history"]) == 16

    def test_empty_db_all_null_rss(self, temp_db):
        result = build_training_summary(db=temp_db, as_of_date=date(2026, 4, 20))
        ts = result["training_summary"]
        for window in ts["windows"].values():
            assert window["rss"] is None
            assert window["km"] == 0.0
            assert window["runs"] == 0.0
        for entry in ts["rsb_history"]:
            assert entry["rsb"] is None
            assert entry["atl"] is None
            assert entry["ctl"] is None

    def test_run_in_1_week_window(self, temp_db):
        self._insert_run(temp_db, "2026-04-18", distance_m=10000, stryd_rss=200.0)
        result = build_training_summary(db=temp_db, as_of_date=date(2026, 4, 20))
        ts = result["training_summary"]
        w1 = ts["windows"]["1_week"]
        assert w1["runs"] == pytest.approx(1 / 1, rel=0.01)
        assert w1["km"] == pytest.approx(10.0 / 1, rel=0.01)
        assert w1["rss"] == pytest.approx(200.0 / 1, rel=0.01)

    def test_4_week_avg_divides_by_4(self, temp_db):
        # 4 runs across 4 weeks, each 10 km, 100 RSS
        for days_ago in [3, 10, 17, 24]:
            d = (date(2026, 4, 20) - timedelta(days=days_ago)).isoformat()
            self._insert_run(temp_db, d, distance_m=10000, stryd_rss=100.0)
        result = build_training_summary(db=temp_db, as_of_date=date(2026, 4, 20))
        w4 = result["training_summary"]["windows"]["4_week_avg"]
        assert w4["runs"] == pytest.approx(4 / 4, rel=0.01)
        assert w4["km"] == pytest.approx(40.0 / 4, rel=0.01)
        assert w4["rss"] == pytest.approx(400.0 / 4, rel=0.01)

    def test_null_stryd_rss_excluded_from_rss_but_counted_in_runs(self, temp_db):
        self._insert_run(temp_db, "2026-04-18", distance_m=5000, stryd_rss=None)
        result = build_training_summary(db=temp_db, as_of_date=date(2026, 4, 20))
        w1 = result["training_summary"]["windows"]["1_week"]
        assert w1["runs"] == pytest.approx(1.0, rel=0.01)
        assert w1["km"] == pytest.approx(5.0, rel=0.01)
        assert w1["rss"] is None

    def test_user_id_isolation(self, temp_db):
        from runcoach.auth import hash_password
        temp_db.create_user("user2", hash_password("pass"))
        user2 = temp_db.get_user_by_username("user2")
        self._insert_run(temp_db, "2026-04-18", user_id=user2["id"], stryd_rss=999.0)
        result = build_training_summary(db=temp_db, as_of_date=date(2026, 4, 20), user_id=1)
        w1 = result["training_summary"]["windows"]["1_week"]
        assert w1["rss"] is None
        assert w1["runs"] == 0.0

    def test_as_of_date_controls_window(self, temp_db):
        self._insert_run(temp_db, "2026-04-10", distance_m=8000, stryd_rss=150.0)
        # as_of_date=2026-04-11 → run is in the 1-week window
        result_in = build_training_summary(db=temp_db, as_of_date=date(2026, 4, 11))
        assert result_in["training_summary"]["windows"]["1_week"]["runs"] == pytest.approx(1.0, rel=0.01)
        # as_of_date=2026-04-10 → run is NOT in the window (exclusive upper bound)
        result_out = build_training_summary(db=temp_db, as_of_date=date(2026, 4, 10))
        assert result_out["training_summary"]["windows"]["1_week"]["runs"] == pytest.approx(0.0, rel=0.01)

    def test_rsb_history_has_16_entries(self, temp_db):
        self._insert_run(temp_db, "2026-04-18", stryd_rss=100.0)
        result = build_training_summary(db=temp_db, as_of_date=date(2026, 4, 20))
        assert len(result["training_summary"]["rsb_history"]) == 16

    def test_current_rsb_fresh(self, temp_db):
        # No recent runs → ATL 0, CTL positive → RSB positive (fresh)
        # Insert runs only in weeks 2-6 ago to build CTL without recent ATL
        for weeks_ago in range(2, 7):
            d = (date(2026, 4, 20) - timedelta(weeks=weeks_ago)).isoformat()
            self._insert_run(temp_db, d, stryd_rss=200.0)
        result = build_training_summary(db=temp_db, as_of_date=date(2026, 4, 20))
        rsb = result["training_summary"]["current_rsb"]
        if rsb["rsb"] is not None:
            assert rsb["rsb"] > 0
            assert rsb["interpretation"] in ("fresh", "balanced")

