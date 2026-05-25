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
        assert _humidity_factor(95) <= 0.30


class TestWindFactor:
    def test_calm_is_full(self):
        assert _wind_factor(0) == pytest.approx(1.0)

    def test_forgiving_below_15(self):
        assert _wind_factor(12) == pytest.approx(1.0)

    def test_moderate_wind_penalised(self):
        assert _wind_factor(35) < 0.70

    def test_gale_near_floor(self):
        assert _wind_factor(55) < 0.20


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


from unittest.mock import patch, MagicMock
from runcoach.weather import fetch_forecast, score_forecast


FAKE_OPEN_METEO = {
    "hourly": {
        "time": (
            [f"2026-05-10T{h:02d}:00" for h in range(24)] +
            [f"2026-05-11T{h:02d}:00" for h in range(24)]
        ),
        "temperature_2m": [10.0] * 48,
        "precipitation_probability": [5] * 48,
        "relativehumidity_2m": [55] * 48,
        "windspeed_10m": [10.0] * 48,
    },
    "daily": {
        "sunrise": ["2026-05-10T05:30", "2026-05-11T05:29"],
        "sunset": ["2026-05-10T21:00", "2026-05-11T21:02"],
    },
}


class TestFetchForecast:
    def test_returns_48_hours(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = FAKE_OPEN_METEO
        with patch("runcoach.weather.requests.get", return_value=mock_resp):
            result = fetch_forecast(53.3, -6.3, "Europe/Dublin")
        assert len(result["hours"]) == 48

    def test_parses_sunrise_sunset_as_lists(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = FAKE_OPEN_METEO
        with patch("runcoach.weather.requests.get", return_value=mock_resp):
            result = fetch_forecast(53.3, -6.3, "Europe/Dublin")
        assert result["sunrise"][0] == datetime(2026, 5, 10, 5, 30)
        assert result["sunset"][0] == datetime(2026, 5, 10, 21, 0)
        assert result["sunrise"][1] == datetime(2026, 5, 11, 5, 29)
        assert result["sunset"][1] == datetime(2026, 5, 11, 21, 2)

    def test_hour_dict_has_expected_keys(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = FAKE_OPEN_METEO
        with patch("runcoach.weather.requests.get", return_value=mock_resp):
            result = fetch_forecast(53.3, -6.3, "Europe/Dublin")
        h = result["hours"][9]
        assert h["hour"] == 9
        assert "temp_c" in h
        assert "rain_pct" in h
        assert "humidity_pct" in h
        assert "wind_kmh" in h


class TestScoreForecast:
    def _make_forecast(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = FAKE_OPEN_METEO
        with patch("runcoach.weather.requests.get", return_value=mock_resp):
            return fetch_forecast(53.3, -6.3, "Europe/Dublin")

    def test_today_hours_returned_when_ample_window(self):
        # 6am → window covers most of today
        result = score_forecast(self._make_forecast(), now=datetime(2026, 5, 10, 6, 0))
        assert result["is_tomorrow"] is False
        assert len(result["hours"]) > 0
        assert all(h["hour"] >= 6 for h in result["hours"])

    def test_each_hour_has_score(self):
        result = score_forecast(self._make_forecast(), now=datetime(2026, 5, 10, 6, 0))
        for h in result["hours"]:
            assert 1 <= h["score"] <= 10

    def test_best_hour_matches_max_score(self):
        result = score_forecast(self._make_forecast(), now=datetime(2026, 5, 10, 6, 0))
        best = max(result["hours"], key=lambda h: h["score"])
        assert result["best_hour"] == best["hour"]
        assert result["best_score"] == best["score"]

    def test_day_label_good_day(self):
        result = score_forecast(self._make_forecast(), now=datetime(2026, 5, 10, 6, 0))
        if result["best_score"] >= 4:
            assert "Best window:" in result["day_label"]
            assert "/10" in result["day_label"]

    def test_day_label_no_good_windows(self):
        bad_data = {
            "hourly": {
                "time": (
                    [f"2026-05-10T{h:02d}:00" for h in range(24)] +
                    [f"2026-05-11T{h:02d}:00" for h in range(24)]
                ),
                "temperature_2m": [25.0] * 48,
                "precipitation_probability": [100] * 48,
                "relativehumidity_2m": [95] * 48,
                "windspeed_10m": [55.0] * 48,
            },
            "daily": {
                "sunrise": ["2026-05-10T05:30", "2026-05-11T05:29"],
                "sunset": ["2026-05-10T21:00", "2026-05-11T21:02"],
            },
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = bad_data
        with patch("runcoach.weather.requests.get", return_value=mock_resp):
            forecast = fetch_forecast(53.3, -6.3, "Europe/Dublin")
        result = score_forecast(forecast, now=datetime(2026, 5, 10, 6, 0))
        assert result["day_label"] == "No good windows today"


class TestScoreForecastWindowing:
    def _make_forecast(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = FAKE_OPEN_METEO
        with patch("runcoach.weather.requests.get", return_value=mock_resp):
            return fetch_forecast(53.3, -6.3, "Europe/Dublin")

    def test_today_window_trims_to_now_through_midnight(self):
        # now=15:00 → hours 15..23 = 9 bars
        now = datetime(2026, 5, 10, 15, 0)
        result = score_forecast(self._make_forecast(), now=now)
        assert result["is_tomorrow"] is False
        assert len(result["hours"]) == 9
        assert result["hours"][0]["hour"] == 15
        assert result["hours"][-1]["hour"] == 23

    def test_falls_back_to_tomorrow_when_fewer_than_3_hours_left(self):
        # now=22:00 → hours 22,23 = 2 bars < 3 → tomorrow
        # tomorrow: sunrise 05:29 (hour 5) → hours 5..23 = 19 bars
        now = datetime(2026, 5, 10, 22, 0)
        result = score_forecast(self._make_forecast(), now=now)
        assert result["is_tomorrow"] is True
        assert len(result["hours"]) == 19
        assert result["hours"][0]["hour"] == 5
        assert result["hours"][-1]["hour"] == 23

    def test_falls_back_to_tomorrow_when_past_window_end(self):
        # now=23:00 → 1 bar today, which is still fewer than 3 → tomorrow
        now = datetime(2026, 5, 10, 23, 0)
        result = score_forecast(self._make_forecast(), now=now)
        assert result["is_tomorrow"] is True

    def test_tomorrow_window_ends_at_midnight(self):
        # now=22:00 → 2 bars today < 3 → tomorrow
        # tomorrow should extend through 23:00
        now = datetime(2026, 5, 10, 22, 0)
        result = score_forecast(self._make_forecast(), now=now)
        assert result["is_tomorrow"] is True
        assert result["hours"][-1]["hour"] == 23

    def test_exactly_3_hours_stays_on_today(self):
        # now=21:00 → hours 21,22,23 = 3 bars → NOT < 3 → today
        now = datetime(2026, 5, 10, 21, 0)
        result = score_forecast(self._make_forecast(), now=now)
        assert result["is_tomorrow"] is False
        assert len(result["hours"]) == 3
