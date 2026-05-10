# Best Time to Run Today — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "best time to run today" feature showing a per-hour running score (1–10) as a bar chart on the web dashboard and mobile home screen, based on weather data from Open-Meteo.

**Architecture:** A new `runcoach/weather.py` module holds pure scoring functions and the Open-Meteo HTTP fetch; a JWT API endpoint and a session-auth endpoint both call it; the web dashboard gains a geolocation-triggered bar chart card; the Flutter home screen gains a matching card using a custom bar widget.

**Tech Stack:** Python `requests` (already in project), Open-Meteo free API (no key), Playwright for E2E, Flutter `geolocator` (already in project), Dart `flutter_riverpod` (already in project).

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `runcoach/weather.py` | Create | Scoring algorithm + Open-Meteo fetch |
| `tests/test_weather.py` | Create | Unit tests for scoring + fetch |
| `runcoach/web/api.py` | Modify | Add `GET /api/v1/best-run-time` endpoint |
| `runcoach/web/routes.py` | Modify | Add `GET /api/best-run-time` session-auth endpoint |
| `runcoach/web/templates/index.html` | Modify | Add best-run-time card with CSS bar chart |
| `tests/test_api.py` | Modify | Tests for JWT endpoint |
| `tests/test_web.py` | Modify | Test for session-auth endpoint |
| `tests/e2e/test_dashboard.py` | Modify | E2E smoke test for bar chart card |
| `mobile/lib/services/api_service.dart` | Modify | Add `getBestRunTime()` method |
| `mobile/lib/providers/best_run_time_provider.dart` | Create | `FutureProvider` for best-run-time data |
| `mobile/lib/widgets/best_run_time_card.dart` | Create | Bar chart card widget |
| `mobile/lib/screens/home_screen.dart` | Modify | Insert `BestRunTimeCard` |
| `mobile/test/widgets/best_run_time_card_test.dart` | Create | Widget tests |

---

## Task 1: Pure scoring functions in `weather.py`

**Files:**
- Create: `runcoach/weather.py`
- Create: `tests/test_weather.py`

- [ ] **Step 1: Write failing tests for `_piecewise` and all five factor functions**

```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_weather.py -v
```
Expected: `ModuleNotFoundError: No module named 'runcoach.weather'`

- [ ] **Step 3: Implement `weather.py` with scoring functions**

```python
# runcoach/weather.py
"""Weather-based running score calculator."""
from __future__ import annotations

import logging
from datetime import datetime

log = logging.getLogger(__name__)


def _piecewise(val: float, breakpoints: list[tuple[float, float]]) -> float:
    """Evaluate a piecewise linear function. Clamps outside the range."""
    if val <= breakpoints[0][0]:
        return breakpoints[0][1]
    if val >= breakpoints[-1][0]:
        return breakpoints[-1][1]
    for i in range(len(breakpoints) - 1):
        x0, y0 = breakpoints[i]
        x1, y1 = breakpoints[i + 1]
        if x0 <= val <= x1:
            return y0 + (val - x0) / (x1 - x0) * (y1 - y0)
    return breakpoints[-1][1]


def _temp_factor(temp_c: float) -> float:
    return _piecewise(temp_c, [
        (-5, 0.10), (4, 0.40), (11, 1.00), (18, 0.85), (28, 0.10),
    ])


def _rain_factor(rain_pct: float) -> float:
    return _piecewise(rain_pct, [
        (0, 1.00), (20, 1.00), (50, 0.50), (80, 0.15), (100, 0.10),
    ])


def _humidity_factor(humidity_pct: float) -> float:
    return _piecewise(humidity_pct, [
        (0, 1.00), (50, 1.00), (70, 0.85), (85, 0.50), (100, 0.10),
    ])


def _wind_factor(wind_kmh: float) -> float:
    return _piecewise(wind_kmh, [
        (0, 1.00), (15, 1.00), (30, 0.70), (50, 0.25), (60, 0.10),
    ])


def _daylight_factor(dt: datetime, sunrise: datetime, sunset: datetime) -> float:
    after = (dt - sunrise).total_seconds() / 60   # negative before sunrise
    before = (sunset - dt).total_seconds() / 60   # negative after sunset
    if after < 30:
        return _piecewise(after, [(-60, 0.30), (0, 0.75), (30, 1.00)])
    if before < 30:
        return _piecewise(before, [(-60, 0.30), (0, 0.75), (30, 1.00)])
    return 1.00


def score_hour(
    temp_c: float,
    rain_pct: float,
    humidity_pct: float,
    wind_kmh: float,
    dt: datetime,
    sunrise: datetime,
    sunset: datetime,
) -> int:
    """Return a running suitability score 1–10 for a single hour."""
    raw = (
        _temp_factor(temp_c)
        * _rain_factor(rain_pct)
        * _humidity_factor(humidity_pct)
        * _wind_factor(wind_kmh)
        * _daylight_factor(dt, sunrise, sunset)
    )
    return max(1, min(10, round(raw * 10)))
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_weather.py -v
```
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add runcoach/weather.py tests/test_weather.py
git commit -m "feat: add weather scoring algorithm for best-run-time"
```

---

## Task 2: Open-Meteo fetch and score_forecast

**Files:**
- Modify: `runcoach/weather.py`
- Modify: `tests/test_weather.py`

- [ ] **Step 1: Write failing tests for `fetch_forecast` and `score_forecast`**

Add to `tests/test_weather.py`:

```python
from unittest.mock import patch, MagicMock
from runcoach.weather import fetch_forecast, score_forecast


FAKE_OPEN_METEO = {
    "hourly": {
        "time": [f"2026-05-10T{h:02d}:00" for h in range(24)],
        "temperature_2m": [10.0] * 24,
        "precipitation_probability": [5] * 24,
        "relativehumidity_2m": [55] * 24,
        "windspeed_10m": [10.0] * 24,
    },
    "daily": {
        "sunrise": ["2026-05-10T05:30"],
        "sunset": ["2026-05-10T21:00"],
    },
}


class TestFetchForecast:
    def test_returns_24_hours(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = FAKE_OPEN_METEO
        with patch("runcoach.weather.requests.get", return_value=mock_resp):
            result = fetch_forecast(53.3, -6.3, "Europe/Dublin")
        assert len(result["hours"]) == 24

    def test_parses_sunrise_sunset(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = FAKE_OPEN_METEO
        with patch("runcoach.weather.requests.get", return_value=mock_resp):
            result = fetch_forecast(53.3, -6.3, "Europe/Dublin")
        assert result["sunrise"] == datetime(2026, 5, 10, 5, 30)
        assert result["sunset"] == datetime(2026, 5, 10, 21, 0)

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

    def test_returns_24_scored_hours(self):
        result = score_forecast(self._make_forecast())
        assert len(result["hours"]) == 24

    def test_each_hour_has_score(self):
        result = score_forecast(self._make_forecast())
        for h in result["hours"]:
            assert 1 <= h["score"] <= 10

    def test_best_hour_matches_max_score(self):
        result = score_forecast(self._make_forecast())
        best = max(result["hours"], key=lambda h: h["score"])
        assert result["best_hour"] == best["hour"]
        assert result["best_score"] == best["score"]

    def test_day_label_good_day(self):
        result = score_forecast(self._make_forecast())
        if result["best_score"] >= 4:
            assert "Best window:" in result["day_label"]
            assert "/10" in result["day_label"]

    def test_day_label_treadmill_day(self):
        # Heavy rain all day → best score will be very low
        bad_data = {
            "hourly": {
                "time": [f"2026-05-10T{h:02d}:00" for h in range(24)],
                "temperature_2m": [25.0] * 24,
                "precipitation_probability": [100] * 24,
                "relativehumidity_2m": [95] * 24,
                "windspeed_10m": [55.0] * 24,
            },
            "daily": {
                "sunrise": ["2026-05-10T05:30"],
                "sunset": ["2026-05-10T21:00"],
            },
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = bad_data
        with patch("runcoach.weather.requests.get", return_value=mock_resp):
            forecast = fetch_forecast(53.3, -6.3, "Europe/Dublin")
        result = score_forecast(forecast)
        assert result["day_label"] == "No good windows today"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_weather.py::TestFetchForecast tests/test_weather.py::TestScoreForecast -v
```
Expected: `ImportError: cannot import name 'fetch_forecast'`

- [ ] **Step 3: Implement `fetch_forecast` and `score_forecast` in `weather.py`**

Add to the bottom of `runcoach/weather.py`:

```python
import requests


def fetch_forecast(lat: float, lng: float, tz: str) -> dict:
    """Fetch today's hourly forecast from Open-Meteo (no API key required)."""
    r = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lng,
            "hourly": "temperature_2m,precipitation_probability,relativehumidity_2m,windspeed_10m",
            "daily": "sunrise,sunset",
            "forecast_days": 1,
            "timezone": tz,
        },
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()

    hourly = data["hourly"]
    daily = data["daily"]
    sunrise = datetime.fromisoformat(daily["sunrise"][0])
    sunset = datetime.fromisoformat(daily["sunset"][0])

    hours = []
    for i, time_str in enumerate(hourly["time"]):
        hours.append({
            "hour": int(time_str[11:13]),
            "dt": datetime.fromisoformat(time_str),
            "temp_c": float(hourly["temperature_2m"][i]),
            "rain_pct": float(hourly["precipitation_probability"][i] or 0),
            "humidity_pct": float(hourly["relativehumidity_2m"][i]),
            "wind_kmh": float(hourly["windspeed_10m"][i]),
        })

    return {"hours": hours, "sunrise": sunrise, "sunset": sunset}


def score_forecast(forecast: dict) -> dict:
    """Score all hours and build the API response payload."""
    sunrise = forecast["sunrise"]
    sunset = forecast["sunset"]

    scored_hours = []
    for h in forecast["hours"]:
        s = score_hour(
            temp_c=h["temp_c"],
            rain_pct=h["rain_pct"],
            humidity_pct=h["humidity_pct"],
            wind_kmh=h["wind_kmh"],
            dt=h["dt"],
            sunrise=sunrise,
            sunset=sunset,
        )
        scored_hours.append({
            "hour": h["hour"],
            "score": s,
            "temp_c": round(h["temp_c"], 1),
            "rain_pct": int(h["rain_pct"]),
            "humidity_pct": int(h["humidity_pct"]),
            "wind_kmh": round(h["wind_kmh"], 1),
        })

    best = max(scored_hours, key=lambda x: x["score"])
    best_score = best["score"]
    best_hour = best["hour"]

    if best_score >= 4:
        suffix = "am" if best_hour < 12 else "pm"
        display = best_hour % 12 or 12
        day_label = f"Best window: {display}{suffix} · {best_score}/10"
    else:
        day_label = "No good windows today"

    return {
        "date": sunrise.date().isoformat(),
        "hours": scored_hours,
        "best_hour": best_hour,
        "best_score": best_score,
        "day_label": day_label,
    }
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_weather.py -v
```
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add runcoach/weather.py tests/test_weather.py
git commit -m "feat: add fetch_forecast and score_forecast to weather.py"
```

---

## Task 3: JWT API endpoint

**Files:**
- Modify: `runcoach/web/api.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write failing tests**

Find the end of `tests/test_api.py` and add:

```python
class TestBestRunTime:
    def test_requires_auth(self, client):
        r = client.get("/api/v1/best-run-time?lat=53.3&lng=-6.3")
        assert r.status_code == 401

    def test_missing_lat_returns_400(self, client, auth_headers):
        r = client.get("/api/v1/best-run-time?lng=-6.3", headers=auth_headers)
        assert r.status_code == 400

    def test_missing_lng_returns_400(self, client, auth_headers):
        r = client.get("/api/v1/best-run-time?lat=53.3", headers=auth_headers)
        assert r.status_code == 400

    def test_invalid_lat_returns_400(self, client, auth_headers):
        r = client.get("/api/v1/best-run-time?lat=999&lng=-6.3", headers=auth_headers)
        assert r.status_code == 400

    def test_returns_scored_forecast(self, client, auth_headers, mocker):
        fake_result = {
            "date": "2026-05-10",
            "hours": [{"hour": h, "score": 7, "temp_c": 12.0, "rain_pct": 5, "humidity_pct": 55, "wind_kmh": 10.0} for h in range(24)],
            "best_hour": 9,
            "best_score": 8,
            "day_label": "Best window: 9am · 8/10",
        }
        mocker.patch("runcoach.web.api.fetch_forecast", return_value={})
        mocker.patch("runcoach.web.api.score_forecast", return_value=fake_result)

        r = client.get("/api/v1/best-run-time?lat=53.3&lng=-6.3", headers=auth_headers)
        assert r.status_code == 200
        data = r.get_json()
        assert data["best_score"] == 8
        assert len(data["hours"]) == 24
        assert "day_label" in data

    def test_open_meteo_failure_returns_503(self, client, auth_headers, mocker):
        import requests as req_lib
        mocker.patch("runcoach.web.api.fetch_forecast", side_effect=req_lib.RequestException("timeout"))
        r = client.get("/api/v1/best-run-time?lat=53.3&lng=-6.3", headers=auth_headers)
        assert r.status_code == 503
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_api.py::TestBestRunTime -v
```
Expected: FAIL with 404 (route not yet registered).

- [ ] **Step 3: Add the endpoint to `api.py`**

Add these imports near the top of `runcoach/web/api.py` with the other module-level imports:

```python
from runcoach.weather import fetch_forecast, score_forecast
```

Then add the endpoint (e.g. after the `/planned-workouts` route):

```python
@api_bp.route("/best-run-time", methods=["GET"])
@require_auth
def api_best_run_time():
    try:
        lat = float(request.args["lat"])
        lng = float(request.args["lng"])
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "lat and lng are required numeric parameters"}), 400

    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return jsonify({"error": "lat/lng out of range"}), 400

    cfg: Config = current_app.config["config"]
    try:
        forecast = fetch_forecast(lat, lng, cfg.timezone)
    except Exception as exc:
        log.warning("Open-Meteo fetch failed: %s", exc)
        return jsonify({"error": "Weather service unavailable"}), 503

    return jsonify(score_forecast(forecast)), 200
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_api.py::TestBestRunTime -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add runcoach/web/api.py tests/test_api.py
git commit -m "feat: add GET /api/v1/best-run-time endpoint"
```

---

## Task 4: Session-auth endpoint + web dashboard card + E2E test

**Files:**
- Modify: `runcoach/web/routes.py`
- Modify: `runcoach/web/templates/index.html`
- Modify: `tests/test_web.py`
- Modify: `tests/e2e/test_dashboard.py`

- [ ] **Step 1: Write failing unit test for the session-auth endpoint**

Add to `tests/test_web.py`:

```python
class TestBestRunTimeWeb:
    def test_requires_login(self, app):
        client = app.test_client()
        r = client.get("/api/best-run-time?lat=53.3&lng=-6.3")
        assert r.status_code in (302, 401)

    def test_returns_scored_forecast(self, client, app, mocker):
        fake_result = {
            "date": "2026-05-10",
            "hours": [{"hour": h, "score": 7, "temp_c": 12.0, "rain_pct": 5, "humidity_pct": 55, "wind_kmh": 10.0} for h in range(24)],
            "best_hour": 9,
            "best_score": 8,
            "day_label": "Best window: 9am · 8/10",
        }
        mocker.patch("runcoach.web.routes.fetch_forecast", return_value={})
        mocker.patch("runcoach.web.routes.score_forecast", return_value=fake_result)
        r = client.get("/api/best-run-time?lat=53.3&lng=-6.3")
        assert r.status_code == 200
        assert r.get_json()["best_score"] == 8

    def test_weather_failure_returns_503(self, client, mocker):
        import requests as req_lib
        mocker.patch("runcoach.web.routes.fetch_forecast", side_effect=req_lib.RequestException("timeout"))
        r = client.get("/api/best-run-time?lat=53.3&lng=-6.3")
        assert r.status_code == 503
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/test_web.py::TestBestRunTimeWeb -v
```
Expected: FAIL with 404.

- [ ] **Step 3: Add the session-auth endpoint to `routes.py`**

Add these imports near the other weather/ors imports in `runcoach/web/routes.py`:

```python
from runcoach.weather import fetch_forecast, score_forecast
```

Then add the endpoint (e.g. after the `route_suggestion` route):

```python
@bp.route("/api/best-run-time")
@_login_required
def best_run_time():
    try:
        lat = float(request.args["lat"])
        lng = float(request.args["lng"])
    except (KeyError, ValueError):
        return jsonify({"error": "lat and lng are required numeric parameters"}), 400

    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return jsonify({"error": "lat/lng out of range"}), 400

    cfg: Config = current_app.config["config"]
    try:
        forecast = fetch_forecast(lat, lng, cfg.timezone)
    except Exception as exc:
        log.warning("Open-Meteo fetch failed: %s", exc)
        return jsonify({"error": "Weather service unavailable"}), 503

    return jsonify(score_forecast(forecast)), 200
```

- [ ] **Step 4: Run unit tests to confirm they pass**

```bash
pytest tests/test_web.py::TestBestRunTimeWeb -v
```
Expected: all PASS.

- [ ] **Step 5: Add the bar chart card to `index.html`**

In `runcoach/web/templates/index.html`, find `{% block content %}` and add this card immediately after the opening tag (before the upload form div):

```html
<div id="brt-card" class="card" style="display:none;">
  <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:0.5rem;">
    <h2 style="margin:0;">Best time to run today</h2>
    <span id="brt-label" style="font-size:0.8rem; color:var(--fg-muted);"></span>
  </div>
  <div id="brt-chart" style="display:flex; align-items:flex-end; gap:2px; height:60px; margin-bottom:0.25rem;"></div>
  <div style="display:flex; justify-content:space-between; font-size:0.65rem; color:var(--fg-muted); padding:0 1px;">
    <span>12am</span><span>6am</span><span>12pm</span><span>6pm</span><span>11pm</span>
  </div>
</div>
<div id="brt-error" style="display:none;"></div>

<script>
(function() {
  if (!navigator.geolocation) return;
  navigator.geolocation.getCurrentPosition(function(pos) {
    fetch('/api/best-run-time?lat=' + pos.coords.latitude + '&lng=' + pos.coords.longitude)
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (!data.hours) return;
        var chart = document.getElementById('brt-chart');
        data.hours.forEach(function(h) {
          var bar = document.createElement('div');
          var pct = (h.score / 10) * 100;
          var color = h.score >= 7 ? '#4ade80' : h.score >= 4 ? '#fbbf24' : '#f87171';
          bar.style.cssText = 'flex:1; height:' + pct + '%; background:' + color + '; border-radius:2px 2px 0 0; min-height:2px;';
          if (h.hour === data.best_hour) {
            bar.style.outline = '2px solid var(--fg)';
            bar.style.outlineOffset = '1px';
          }
          bar.title = h.hour + ':00 · ' + h.score + '/10';
          chart.appendChild(bar);
        });
        document.getElementById('brt-label').textContent = data.day_label;
        document.getElementById('brt-card').style.display = 'block';
      })
      .catch(function() {});
  }, function() {});
})();
</script>
```

- [ ] **Step 6: Write the E2E test**

Add to `tests/e2e/test_dashboard.py`:

```python
import json as _json


class TestBestRunTimeCard:
    def test_card_appears_when_geolocation_granted(self, browser, server_url):
        """Bar chart card should render when geolocation is available and API succeeds."""
        context = browser.new_context(
            geolocation={"latitude": 53.3498, "longitude": -6.2603},
            permissions=["geolocation"],
        )
        page = context.new_page()

        # Intercept the API call so the test doesn't hit Open-Meteo
        fake_payload = _json.dumps({
            "date": "2026-05-10",
            "hours": [
                {"hour": h, "score": 7 if h == 9 else 5,
                 "temp_c": 12.0, "rain_pct": 5, "humidity_pct": 55, "wind_kmh": 10.0}
                for h in range(24)
            ],
            "best_hour": 9,
            "best_score": 7,
            "day_label": "Best window: 9am · 7/10",
        })
        page.route("**/api/best-run-time**", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=fake_payload,
        ))

        # Log in
        page.goto(f"{server_url}/login")
        page.fill("input[name='username']", "athlete")
        from tests.e2e.conftest import E2E_PASSWORD
        page.fill("input[name='password']", E2E_PASSWORD)
        page.click("button[type='submit']")
        page.wait_for_url(f"{server_url}/")

        card = page.locator("#brt-card")
        card.wait_for(state="visible", timeout=5000)
        assert "Best window" in page.locator("#brt-label").text_content()
        context.close()
```

- [ ] **Step 7: Run unit and E2E tests**

```bash
pytest tests/test_web.py::TestBestRunTimeWeb -v
pytest -m e2e --no-cov -v -k "TestBestRunTimeCard"
```
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add runcoach/web/routes.py runcoach/web/templates/index.html tests/test_web.py tests/e2e/test_dashboard.py
git commit -m "feat: add best-run-time web endpoint and dashboard bar chart card"
```

---

## Task 5: Mobile API method and Riverpod provider

**Files:**
- Modify: `mobile/lib/services/api_service.dart`
- Create: `mobile/lib/providers/best_run_time_provider.dart`

- [ ] **Step 1: Add `getBestRunTime` to `ApiService`**

In `mobile/lib/services/api_service.dart`, add after the `postRouteSuggestion` method:

```dart
Future<Map<String, dynamic>> getBestRunTime({
  required double lat,
  required double lng,
}) async {
  final r = await _dio.get<Map<String, dynamic>>(
    '/api/v1/best-run-time',
    queryParameters: {'lat': lat, 'lng': lng},
  );
  return r.data!;
}
```

- [ ] **Step 2: Create the Riverpod provider**

Create `mobile/lib/providers/best_run_time_provider.dart`:

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';
import 'auth_provider.dart';

final bestRunTimeProvider =
    FutureProvider.autoDispose<Map<String, dynamic>?>((ref) async {
  ref.watch(authProvider);
  final api = ref.read(apiServiceProvider);

  LocationPermission permission = await Geolocator.checkPermission();
  if (permission == LocationPermission.denied) {
    permission = await Geolocator.requestPermission();
  }
  if (permission == LocationPermission.denied ||
      permission == LocationPermission.deniedForever) {
    return null; // no location → card hidden
  }

  final pos = await Geolocator.getCurrentPosition(
    desiredAccuracy: LocationAccuracy.low,
  );
  return api.getBestRunTime(lat: pos.latitude, lng: pos.longitude);
});
```

- [ ] **Step 3: Run Dart analysis to check for errors**

```bash
cd mobile && dart analyze lib/services/api_service.dart lib/providers/best_run_time_provider.dart
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
cd mobile && dart format lib/services/api_service.dart lib/providers/best_run_time_provider.dart
cd ..
git add mobile/lib/services/api_service.dart mobile/lib/providers/best_run_time_provider.dart
git commit -m "feat: add getBestRunTime API method and bestRunTimeProvider"
```

---

## Task 6: `BestRunTimeCard` Flutter widget

**Files:**
- Create: `mobile/lib/widgets/best_run_time_card.dart`
- Create: `mobile/test/widgets/best_run_time_card_test.dart`

- [ ] **Step 1: Write failing widget tests**

Create `mobile/test/widgets/best_run_time_card_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:runcoach/widgets/best_run_time_card.dart';
import 'package:runcoach/providers/best_run_time_provider.dart';

Map<String, dynamic> _fakeData({int bestScore = 8}) => {
      'date': '2026-05-10',
      'hours': List.generate(
        24,
        (h) => {
          'hour': h,
          'score': h == 9 ? bestScore : 4,
          'temp_c': 12.0,
          'rain_pct': 5,
          'humidity_pct': 55,
          'wind_kmh': 10.0,
        },
      ),
      'best_hour': 9,
      'best_score': bestScore,
      'day_label': 'Best window: 9am · $bestScore/10',
    };

Widget _wrap(Map<String, dynamic>? data) => ProviderScope(
      overrides: [
        bestRunTimeProvider.overrideWith((_) async => data),
      ],
      child: const MaterialApp(home: Scaffold(body: BestRunTimeCard())),
    );

void main() {
  testWidgets('shows day_label when data available', (tester) async {
    await tester.pumpWidget(_wrap(_fakeData()));
    await tester.pumpAndSettle();
    expect(find.textContaining('Best window'), findsOneWidget);
  });

  testWidgets('renders 24 bars', (tester) async {
    await tester.pumpWidget(_wrap(_fakeData()));
    await tester.pumpAndSettle();
    // 24 bar containers identified by key
    expect(find.byKey(const ValueKey('brt-bars')), findsOneWidget);
  });

  testWidgets('hidden when location unavailable (null data)', (tester) async {
    await tester.pumpWidget(_wrap(null));
    await tester.pumpAndSettle();
    expect(find.byType(BestRunTimeCard), findsOneWidget);
    // Card should render nothing visible when data is null
    expect(find.textContaining('Best window'), findsNothing);
  });

  testWidgets('shows loading indicator while fetching', (tester) async {
    await tester.pumpWidget(ProviderScope(
      overrides: [
        bestRunTimeProvider.overrideWith((_) async {
          await Future.delayed(const Duration(seconds: 60));
          return null;
        }),
      ],
      child: const MaterialApp(home: Scaffold(body: BestRunTimeCard())),
    ));
    await tester.pump(); // one frame — still loading
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });
}
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd mobile && flutter test test/widgets/best_run_time_card_test.dart
```
Expected: FAIL with `BestRunTimeCard` not found.

- [ ] **Step 3: Implement `BestRunTimeCard`**

Create `mobile/lib/widgets/best_run_time_card.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/best_run_time_provider.dart';

class BestRunTimeCard extends ConsumerWidget {
  const BestRunTimeCard({super.key});

  Color _barColor(int score) {
    if (score >= 7) return const Color(0xFF4ade80);
    if (score >= 4) return const Color(0xFFfbbf24);
    return const Color(0xFFf87171);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(bestRunTimeProvider);

    return async.when(
      loading: () => const Card(
        child: Padding(
          padding: EdgeInsets.all(16),
          child: Center(child: CircularProgressIndicator()),
        ),
      ),
      error: (_, __) => const SizedBox.shrink(),
      data: (data) {
        if (data == null) return const SizedBox.shrink();
        final hours = List<Map<String, dynamic>>.from(data['hours'] as List);
        final bestHour = data['best_hour'] as int;
        final dayLabel = data['day_label'] as String;
        final maxBarHeight = 48.0;

        return Card(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      'Best time to run today',
                      style: TextStyle(
                          fontSize: 14, fontWeight: FontWeight.w600),
                    ),
                    Text(
                      dayLabel,
                      style: const TextStyle(
                          fontSize: 11, color: Color(0xFF888888)),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                SizedBox(
                  height: maxBarHeight + 4,
                  child: Row(
                    key: const ValueKey('brt-bars'),
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: hours.map((h) {
                      final score = h['score'] as int;
                      final isHour = h['hour'] as int;
                      final barH = (score / 10) * maxBarHeight;
                      return Expanded(
                        child: Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 0.5),
                          child: Container(
                            height: barH.clamp(2.0, maxBarHeight),
                            decoration: BoxDecoration(
                              color: _barColor(score),
                              borderRadius: const BorderRadius.vertical(
                                  top: Radius.circular(2)),
                              border: isHour == bestHour
                                  ? Border.all(
                                      color: Colors.white70, width: 1)
                                  : null,
                            ),
                          ),
                        ),
                      );
                    }).toList(),
                  ),
                ),
                const SizedBox(height: 2),
                const Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text('12am',
                        style: TextStyle(
                            fontSize: 9, color: Color(0xFF888888))),
                    Text('6am',
                        style: TextStyle(
                            fontSize: 9, color: Color(0xFF888888))),
                    Text('12pm',
                        style: TextStyle(
                            fontSize: 9, color: Color(0xFF888888))),
                    Text('6pm',
                        style: TextStyle(
                            fontSize: 9, color: Color(0xFF888888))),
                    Text('11pm',
                        style: TextStyle(
                            fontSize: 9, color: Color(0xFF888888))),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
```

- [ ] **Step 4: Run widget tests to confirm they pass**

```bash
cd mobile && flutter test test/widgets/best_run_time_card_test.dart
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd mobile && dart format lib/widgets/best_run_time_card.dart test/widgets/best_run_time_card_test.dart
cd ..
git add mobile/lib/widgets/best_run_time_card.dart mobile/test/widgets/best_run_time_card_test.dart
git commit -m "feat: add BestRunTimeCard Flutter widget with bar chart"
```

---

## Task 7: Wire into home screen and run all tests

**Files:**
- Modify: `mobile/lib/screens/home_screen.dart`

- [ ] **Step 1: Add `BestRunTimeCard` to the home screen**

In `mobile/lib/screens/home_screen.dart`, add the import at the top:

```dart
import '../widgets/best_run_time_card.dart';
```

Then in the `ListView` children list, add `const BestRunTimeCard()` as the first child (before `RsbCard`):

```dart
child: ListView(
  padding: const EdgeInsets.all(16),
  children: [
    const BestRunTimeCard(),            // ← add this
    const SizedBox(height: 12),
    RsbCard(summary: dashboard.trainingSummary),
    // ... rest unchanged
  ],
),
```

- [ ] **Step 2: Run dart format and flutter test**

```bash
cd mobile
dart format --output=none --set-exit-if-changed .
flutter test
```
Expected: format clean, all tests PASS.

- [ ] **Step 3: Commit**

```bash
cd ..
git add mobile/lib/screens/home_screen.dart
git commit -m "feat: add BestRunTimeCard to home screen (issue #26)"
```

- [ ] **Step 4: Run full Python test suite**

```bash
pytest && pytest -m e2e --no-cov -v
```
Expected: all PASS.

- [ ] **Step 5: Commit any fixes, then push and raise PR**

```bash
git push -u origin feature/issue-26-best-run-time
gh pr create --title "feat: best time to run today (issue #26)" --body "$(cat <<'EOF'
## Summary

- New `runcoach/weather.py` module with a multiplicative scoring algorithm (temperature, rain, humidity, wind, daylight) and Open-Meteo fetch (no API key required)
- `GET /api/v1/best-run-time?lat=X&lng=Y` (JWT) and `GET /api/best-run-time` (session) return 24 hourly scores + best window + day label
- Web dashboard gains a geolocation-triggered bar chart card (green/amber/red bars, no JS dependencies)
- Flutter home screen gains a `BestRunTimeCard` with the same bar chart

## Test Plan
- [ ] Unit tests for all five scoring factors, `score_hour`, `fetch_forecast`, `score_forecast`
- [ ] API endpoint tests (auth, validation, error handling)
- [ ] Web session-auth endpoint tests
- [ ] E2E test: bar chart card appears on dashboard with mocked API response
- [ ] Flutter widget tests: loading state, data state, null (no location) state

Closes #26

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
