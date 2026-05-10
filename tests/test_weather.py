# tests/test_weather.py
from __future__ import annotations
import pytest
from datetime import datetime
from runcoach.weather import (
    _piecewise,
    _temp_factor,
    _rain_factor,
    _humidity_factor,
    _wind_factor,
    _daylight_factor,
    score_hour,
)


class TestPiecewise:
    def test_clamps_below_first_breakpoint(self):
        assert _piecewise(-100, [(-5, 0.1), (11, 1.0)]) == pytest.approx(0.1)

    def test_clamps_above_last_breakpoint(self):
        assert _piecewise(100, [(-5, 0.1), (11, 1.0)]) == pytest.approx(1.0)

    def test_interpolates_midpoint(self):
        assert _piecewise(3.0, [(0, 0.0), (6, 1.0)]) == pytest.approx(0.5)

    def test_exact_breakpoint_value(self):
        assert _piecewise(11.0, [(-5, 0.1), (11, 1.0)]) == pytest.approx(1.0)


class TestTempFactor:
    def test_peak_at_11c(self):
        assert _temp_factor(11.0) == pytest.approx(1.0)

    def test_floor_below_minus5(self):
        assert _temp_factor(-10.0) == pytest.approx(0.10)

    def test_floor_above_28(self):
        assert _temp_factor(35.0) == pytest.approx(0.10)

    def test_rapid_drop_above_18(self):
        assert _temp_factor(20.0) < _temp_factor(16.0)
        assert _temp_factor(25.0) < _temp_factor(20.0)

    def test_18c_noticeably_below_peak(self):
        assert _temp_factor(18.0) < 0.90


class TestRainFactor:
    def test_no_rain_is_full(self):
        assert _rain_factor(0) == pytest.approx(1.0)

    def test_forgiving_below_20pct(self):
        assert _rain_factor(15) == pytest.approx(1.0)

    def test_moderate_rain_penalised(self):
        assert _rain_factor(50) < 0.60

    def test_heavy_rain_near_floor(self):
        assert _rain_factor(90) <= 0.15


class TestHumidityFactor:
    def test_dry_is_full(self):
        assert _humidity_factor(30) == pytest.approx(1.0)

    def test_comfortable_below_50(self):
        assert _humidity_factor(50) == pytest.approx(1.0)

    def test_sticky_above_70_penalised(self):
        assert _humidity_factor(78) < 0.85

    def test_very_high_near_floor(self):
        assert _humidity_factor(95) <= 0.20


class TestWindFactor:
    def test_calm_is_full(self):
        assert _wind_factor(0) == pytest.approx(1.0)

    def test_forgiving_below_15(self):
        assert _wind_factor(12) == pytest.approx(1.0)

    def test_moderate_wind_penalised(self):
        assert _wind_factor(35) < 0.50

    def test_gale_near_floor(self):
        assert _wind_factor(55) == pytest.approx(0.10)


class TestDaylightFactor:
    _sunrise = datetime(2026, 5, 10, 5, 30)
    _sunset = datetime(2026, 5, 10, 21, 0)

    def test_full_daylight_is_1(self):
        midday = datetime(2026, 5, 10, 12, 0)
        assert _daylight_factor(midday, self._sunrise, self._sunset) == pytest.approx(1.0)

    def test_dark_night_is_low(self):
        midnight = datetime(2026, 5, 10, 2, 0)
        assert _daylight_factor(midnight, self._sunrise, self._sunset) == pytest.approx(0.30)

    def test_at_sunrise_is_intermediate(self):
        at_rise = self._sunrise
        d = _daylight_factor(at_rise, self._sunrise, self._sunset)
        assert 0.70 < d < 0.85

    def test_30min_after_sunrise_is_full(self):
        after = datetime(2026, 5, 10, 6, 1)  # 31 min after 05:30
        assert _daylight_factor(after, self._sunrise, self._sunset) == pytest.approx(1.0)

    def test_30min_before_sunset_starts_ramping(self):
        before = datetime(2026, 5, 10, 20, 29)  # 31 min before 21:00
        assert _daylight_factor(before, self._sunrise, self._sunset) == pytest.approx(1.0)

    def test_at_sunset_is_intermediate(self):
        at_set = self._sunset
        d = _daylight_factor(at_set, self._sunrise, self._sunset)
        assert 0.70 < d < 0.85


class TestScoreHour:
    _sr = datetime(2026, 5, 10, 5, 30)
    _ss = datetime(2026, 5, 10, 21, 0)

    def test_ideal_conditions_score_9_or_10(self):
        dt = datetime(2026, 5, 10, 9, 0)
        assert score_hour(10.0, 5, 50, 10, dt, self._sr, self._ss) >= 9

    def test_dark_night_scores_low(self):
        dt = datetime(2026, 5, 10, 2, 0)
        assert score_hour(10.0, 0, 50, 5, dt, self._sr, self._ss) <= 4

    def test_heavy_rain_scores_low(self):
        dt = datetime(2026, 5, 10, 10, 0)
        assert score_hour(12.0, 90, 50, 10, dt, self._sr, self._ss) <= 2

    def test_hot_and_humid_scores_low(self):
        dt = datetime(2026, 5, 10, 14, 0)
        assert score_hour(28.0, 10, 85, 10, dt, self._sr, self._ss) <= 3

    def test_score_is_between_1_and_10(self):
        dt = datetime(2026, 5, 10, 12, 0)
        s = score_hour(15.0, 30, 60, 20, dt, self._sr, self._ss)
        assert 1 <= s <= 10
