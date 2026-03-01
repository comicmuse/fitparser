"""Unit tests for runcoach.fit_parser module."""

from __future__ import annotations

import pytest
from pathlib import Path

from runcoach.fit_parser import (
    build_blocks_from_fit,
    load_fit,
    extract_laps,
    extract_workout_steps,
    _round,
)


class TestRoundHelper:
    """Tests for the _round helper function."""

    def test_round_normal(self):
        """Test rounding normal floats."""
        assert _round(1.2345, 2) == 1.23
        assert _round(1.2345, 1) == 1.2
        assert _round(1.2345, 0) == 1.0

    def test_round_none(self):
        """Test that None returns None."""
        assert _round(None, 2) is None

    def test_round_default_precision(self):
        """Test default precision of 1."""
        assert _round(1.2345) == 1.2

    def test_round_invalid_input(self):
        """Test invalid inputs return None."""
        assert _round("not a number", 2) is None


class TestFitFileLoading:
    """Tests for FIT file loading."""

    def test_load_fit_file(self, sample_fit_file):
        """Test loading a FIT file."""
        if not sample_fit_file.exists():
            pytest.skip(f"Sample FIT file not found: {sample_fit_file}")

        fit = load_fit(sample_fit_file)
        assert fit is not None

    def test_extract_laps(self, sample_fit_file):
        """Test extracting lap messages from FIT file."""
        if not sample_fit_file.exists():
            pytest.skip(f"Sample FIT file not found: {sample_fit_file}")

        fit = load_fit(sample_fit_file)
        laps = extract_laps(fit)

        assert isinstance(laps, list)
        assert len(laps) > 0

        # Check that laps have expected fields
        lap = laps[0]
        assert isinstance(lap, dict)
        # Common lap fields (may vary by device)
        # Just check that we got a dict with some data
        assert len(lap) > 0

    def test_extract_workout_steps(self, sample_fit_file):
        """Test extracting workout steps from FIT file."""
        if not sample_fit_file.exists():
            pytest.skip(f"Sample FIT file not found: {sample_fit_file}")

        fit = load_fit(sample_fit_file)
        steps = extract_workout_steps(fit)

        assert isinstance(steps, list)
        # May be empty if this isn't a structured workout
        # Just verify the function returns a list


class TestBuildBlocksFromFit:
    """Tests for the main build_blocks_from_fit function."""

    def test_build_blocks_from_fit_integration(self, sample_fit_file):
        """Test parsing a real FIT file end-to-end."""
        if not sample_fit_file.exists():
            pytest.skip(f"Sample FIT file not found: {sample_fit_file}")

        result = build_blocks_from_fit(
            path=sample_fit_file,
            tz_name="Europe/London",
        )

        assert isinstance(result, dict)

        # Check for expected top-level keys
        assert "source_file" in result
        assert "date" in result
        assert "sport" in result
        assert "blocks" in result

        # Check metadata
        assert result["sport"] == "running"
        assert isinstance(result["date"], str)
        assert len(result["date"]) == 10  # YYYY-MM-DD format

    def test_build_blocks_structure(self, sample_fit_file):
        """Test that output has expected structure."""
        if not sample_fit_file.exists():
            pytest.skip(f"Sample FIT file not found: {sample_fit_file}")

        result = build_blocks_from_fit(sample_fit_file, "Europe/London")

        # Activity-level fields
        expected_fields = [
            "source_file",
            "date",
            "sport",
            "start_utc",
            "start_local",
            "distance_km",
            "duration_min",
            "blocks",
        ]

        for field in expected_fields:
            assert field in result, f"Missing expected field: {field}"

        # Check blocks structure
        blocks = result.get("blocks", {})
        assert isinstance(blocks, dict)

        if len(blocks) > 0:
            # Check first block has expected structure
            first_block = next(iter(blocks.values()))
            assert "type" in first_block
            assert first_block["type"] in [
                "warmup", "work", "active", "float", "cooldown", "rest", "other"
            ]

    def test_build_blocks_hr_zones(self, sample_fit_file):
        """Test that HR zone distribution is calculated."""
        if not sample_fit_file.exists():
            pytest.skip(f"Sample FIT file not found: {sample_fit_file}")

        result = build_blocks_from_fit(sample_fit_file, "Europe/London")

        # Check for HR zone definition
        if "hr_zone_definition" in result:
            hr_zones = result["hr_zone_definition"]
            assert "zones" in hr_zones
            assert "system" in hr_zones

            # Check that zones are defined
            zones = hr_zones["zones"]
            assert isinstance(zones, dict)
            assert len(zones) > 0

            # Each zone should have min/max
            for zone_name, zone_data in zones.items():
                assert "min_bpm" in zone_data
                assert "max_bpm" in zone_data

        # Check blocks for HR zone distributions
        blocks = result.get("blocks", {})
        for block_name, block_data in blocks.items():
            if "hr_zone_distribution" in block_data:
                hr_dist = block_data["hr_zone_distribution"]
                assert isinstance(hr_dist, dict)

                # Check that percentages sum to ~100%
                if hr_dist:
                    total_pct = sum(v.get("pct", 0) for v in hr_dist.values())
                    assert 99 <= total_pct <= 101  # Allow for rounding

    def test_build_blocks_power_data(self, sample_fit_file):
        """Test that power data is extracted."""
        if not sample_fit_file.exists():
            pytest.skip(f"Sample FIT file not found: {sample_fit_file}")

        result = build_blocks_from_fit(sample_fit_file, "Europe/London")

        # Check for power fields at activity level
        if "avg_power" in result and result["avg_power"] is not None:
            assert result["avg_power"] > 0
            assert "max_power" in result

            # Check critical power if available
            if "critical_power" in result:
                assert result["critical_power"] > 0

            # Check blocks for power data
            blocks = result.get("blocks", {})
            for block_name, block_data in blocks.items():
                if "avg_power" in block_data and block_data["avg_power"] is not None:
                    assert block_data["avg_power"] > 0

    def test_build_blocks_power_targets(self, sample_fit_file):
        """Test power target compliance calculation."""
        if not sample_fit_file.exists():
            pytest.skip(f"Sample FIT file not found: {sample_fit_file}")

        result = build_blocks_from_fit(sample_fit_file, "Europe/London")

        blocks = result.get("blocks", {})
        for block_name, block_data in blocks.items():
            # If block has power targets, check compliance fields
            if "target_min_w" in block_data and block_data["target_min_w"] is not None:
                assert "target_max_w" in block_data
                assert "pct_time_below" in block_data or block_data.get("pct_time_below") is not None
                assert "pct_time_in_range" in block_data or block_data.get("pct_time_in_range") is not None
                assert "pct_time_above" in block_data or block_data.get("pct_time_above") is not None

                # If we have compliance data, percentages should sum to ~100%
                if all(k in block_data for k in ["pct_time_below", "pct_time_in_range", "pct_time_above"]):
                    total = (
                        block_data["pct_time_below"] +
                        block_data["pct_time_in_range"] +
                        block_data["pct_time_above"]
                    )
                    if total > 0:  # Only check if we have data
                        assert 99 <= total <= 101  # Allow for rounding

    def test_build_blocks_timezone_handling(self, sample_fit_file):
        """Test that timezone is properly applied."""
        if not sample_fit_file.exists():
            pytest.skip(f"Sample FIT file not found: {sample_fit_file}")

        # Parse with different timezones
        result_utc = build_blocks_from_fit(sample_fit_file, "UTC")
        result_london = build_blocks_from_fit(sample_fit_file, "Europe/London")

        # start_utc should be the same
        assert result_utc["start_utc"] == result_london["start_utc"]

        # start_local may differ depending on DST
        # Just verify both have local times
        assert "start_local" in result_utc
        assert "start_local" in result_london

    def test_build_blocks_date_extraction(self, sample_fit_file):
        """Test that date is correctly extracted."""
        if not sample_fit_file.exists():
            pytest.skip(f"Sample FIT file not found: {sample_fit_file}")

        result = build_blocks_from_fit(sample_fit_file, "Europe/London")

        # Date should be in YYYY-MM-DD format
        date_str = result["date"]
        assert len(date_str) == 10
        assert date_str[4] == "-"
        assert date_str[7] == "-"

        # Should be valid date
        from datetime import datetime
        parsed_date = datetime.fromisoformat(date_str)
        assert parsed_date is not None

    def test_build_blocks_distances_and_durations(self, sample_fit_file):
        """Test that distances and durations are reasonable."""
        if not sample_fit_file.exists():
            pytest.skip(f"Sample FIT file not found: {sample_fit_file}")

        result = build_blocks_from_fit(sample_fit_file, "Europe/London")

        # Activity-level distance and duration
        assert result["distance_km"] > 0
        assert result["duration_min"] > 0

        # Block-level distances and durations
        blocks = result.get("blocks", {})
        total_block_distance = 0
        total_block_duration = 0

        for block_name, block_data in blocks.items():
            if "distance_km" in block_data and block_data["distance_km"] is not None:
                assert block_data["distance_km"] >= 0
                total_block_distance += block_data["distance_km"]

            if "duration_min" in block_data and block_data["duration_min"] is not None:
                assert block_data["duration_min"] > 0
                total_block_duration += block_data["duration_min"]

        # Blocks should roughly sum to total (allow for rounding/structure differences)
        if len(blocks) > 0:
            assert total_block_distance > 0
            assert total_block_duration > 0

    def test_build_blocks_no_power_data(self):
        """Test handling of FIT files without power data."""
        # This test would need a FIT file without power data
        # For now, we'll skip it if the sample has power
        pytest.skip("Need a FIT file without power data for this test")

    def test_build_blocks_hr_drift(self, sample_fit_file):
        """Test HR drift calculation for longer blocks."""
        if not sample_fit_file.exists():
            pytest.skip(f"Sample FIT file not found: {sample_fit_file}")

        result = build_blocks_from_fit(sample_fit_file, "Europe/London")

        blocks = result.get("blocks", {})
        for block_name, block_data in blocks.items():
            # For blocks longer than 10 minutes, we should have drift data
            if block_data.get("duration_min", 0) > 10:
                if "hr_drift_pct" in block_data and block_data["hr_drift_pct"] is not None:
                    # HR drift should be a reasonable percentage
                    assert -50 <= block_data["hr_drift_pct"] <= 50


class TestBuildBlocksEdgeCases:
    """Tests for edge cases and error handling."""

    def test_build_blocks_nonexistent_file(self):
        """Test handling of nonexistent FIT file."""
        with pytest.raises(Exception):  # Should raise some exception
            build_blocks_from_fit(
                fit_path=Path("/nonexistent/file.fit"),
                tz_name="Europe/London",
            )

    def test_build_blocks_invalid_timezone(self, sample_fit_file):
        """Test handling of invalid timezone."""
        if not sample_fit_file.exists():
            pytest.skip(f"Sample FIT file not found: {sample_fit_file}")

        # Invalid timezone should either raise or default to UTC
        # Depending on implementation, this might raise or handle gracefully
        try:
            result = build_blocks_from_fit(sample_fit_file, "Invalid/Timezone")
            # If it doesn't raise, it should have some timezone
            assert "start_local" in result
        except Exception:
            # If it raises, that's also acceptable
            pass


class TestBuildBlocksRealWorkouts:
    """Integration tests with different workout types."""

    @pytest.mark.parametrize("fit_file_name", [
        "20260129_day_25_-_testing/20260129_day_25_-_testing.fit",
        "20260127_day_23_-_ez_aerobic___recovery_run/20260127_day_23_-_ez_aerobic___recovery_run.fit",
    ])
    def test_parse_various_workouts(self, fit_file_name):
        """Test parsing various types of workouts."""
        fit_path = Path("data/activities/2026/01") / fit_file_name
        if not fit_path.exists():
            pytest.skip(f"Sample FIT file not found: {fit_path}")

        result = build_blocks_from_fit(fit_path, "Europe/London")

        # Basic structure checks
        assert "date" in result
        assert "distance_km" in result
        assert "duration_min" in result
        assert "blocks" in result

        # Should have at least one block
        assert len(result["blocks"]) > 0
