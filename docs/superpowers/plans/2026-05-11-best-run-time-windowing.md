# Best Run Time Windowing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trim the Best Times to Run bar chart to show only the actionable window (current hour → sunset+2h for today; sunrise → sunset+2h for tomorrow), falling back to tomorrow when fewer than 3 hours remain.

**Architecture:** All windowing logic lives in `weather.py`. `fetch_forecast` fetches 2 days from Open-Meteo so a tomorrow fallback is always available. `score_forecast` gains a `now: datetime` parameter and trims the hours list before scoring. Both API endpoints pass the current naive local time. The Flutter card and web template render whatever `hours` they receive with dynamic axis labels.

**Tech Stack:** Python 3.11, Flask, `zoneinfo`, Dart/Flutter, Riverpod, Open-Meteo API

---

## File Map

| File | Change |
|---|---|
| `runcoach/weather.py` | `fetch_forecast` fetches 2 days; `score_forecast` gains `now` param + windowing |
| `tests/test_weather.py` | Update 2-day fake data; update existing tests; add windowing tests |
| `runcoach/web/api.py` | Pass `now` to `score_forecast` |
| `runcoach/web/routes.py` | Pass `now` to `score_forecast` |
| `tests/test_api.py` | Update mock fake data to include `is_tomorrow` |
| `mobile/lib/widgets/best_run_time_card.dart` | Dynamic title + 3-label axis |
| `mobile/test/widgets/best_run_time_card_test.dart` | Update fake data; add tomorrow + axis label tests |
| `runcoach/web/templates/index.html` | Dynamic title + 3-label axis in JS |

---

## Task 1: Update `fetch_forecast` to return 2 days

**Files:**
- Modify: `runcoach/weather.py`
- Modify: `tests/test_weather.py`

- [ ] **Step 1: Update `FAKE_OPEN_METEO` in `tests/test_weather.py` to 2-day format**

Replace the existing `FAKE_OPEN_METEO` constant (lines 151–163) with:

```python
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
```

- [ ] **Step 2: Update `TestFetchForecast` tests to match the new 2-day return shape**

Replace the entire `TestFetchForecast` class with:

```python
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
```

- [ ] **Step 3: Run `TestFetchForecast` to confirm it fails**

```bash
pytest tests/test_weather.py::TestFetchForecast -v
```

Expected: FAIL — `AssertionError` on `len == 48` (currently returns 24) and list indexing on `sunrise`.

- [ ] **Step 4: Update `fetch_forecast` in `runcoach/weather.py`**

Replace the existing `fetch_forecast` function with:

```python
def fetch_forecast(lat: float, lng: float, tz: str, days: int = 2) -> dict:
    """Fetch hourly forecast from Open-Meteo (no API key required)."""
    r = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lng,
            "hourly": "temperature_2m,precipitation_probability,relativehumidity_2m,windspeed_10m",
            "daily": "sunrise,sunset",
            "forecast_days": days,
            "timezone": tz,
        },
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()

    hourly = data["hourly"]
    daily = data["daily"]
    sunrises = [datetime.fromisoformat(s) for s in daily["sunrise"]]
    sunsets = [datetime.fromisoformat(s) for s in daily["sunset"]]

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

    return {"hours": hours, "sunrise": sunrises, "sunset": sunsets}
```

- [ ] **Step 5: Run `TestFetchForecast` to confirm it passes**

```bash
pytest tests/test_weather.py::TestFetchForecast -v
```

Expected: all 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add runcoach/weather.py tests/test_weather.py
git commit -m "feat: fetch_forecast returns 2-day forecast with sunrise/sunset lists"
```

---

## Task 2: Update `score_forecast` with `now` parameter and windowing logic

**Files:**
- Modify: `runcoach/weather.py`
- Modify: `tests/test_weather.py`

- [ ] **Step 1: Write failing windowing tests — add `TestScoreForecastWindowing` to `tests/test_weather.py`**

Add this class after `TestScoreForecast`:

```python
class TestScoreForecastWindowing:
    def _make_forecast(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = FAKE_OPEN_METEO
        with patch("runcoach.weather.requests.get", return_value=mock_resp):
            return fetch_forecast(53.3, -6.3, "Europe/Dublin")

    def test_today_window_trims_to_now_through_sunset_plus_2h(self):
        # now=15:00, sunset=21:00, window_end=23:00 → hours 15..22 = 8 bars
        now = datetime(2026, 5, 10, 15, 0)
        result = score_forecast(self._make_forecast(), now=now)
        assert result["is_tomorrow"] is False
        assert len(result["hours"]) == 8
        assert result["hours"][0]["hour"] == 15
        assert result["hours"][-1]["hour"] == 22

    def test_falls_back_to_tomorrow_when_fewer_than_3_hours_left(self):
        # now=21:00, window_end=23:00 → hours 21,22 = 2 bars < 3 → tomorrow
        # tomorrow: sunrise 05:29 (hour 5), sunset 21:02, window_end 23:02
        # → hours 5..22 = 18 bars
        now = datetime(2026, 5, 10, 21, 0)
        result = score_forecast(self._make_forecast(), now=now)
        assert result["is_tomorrow"] is True
        assert result["hours"][0]["hour"] == 5

    def test_falls_back_to_tomorrow_when_past_window_end(self):
        # now=23:00, window_end=23:00 → 0 bars today → tomorrow
        now = datetime(2026, 5, 10, 23, 0)
        result = score_forecast(self._make_forecast(), now=now)
        assert result["is_tomorrow"] is True

    def test_tomorrow_window_ends_at_sunset_plus_2h(self):
        # now=22:00 → 1 bar today (hour 22) < 3 → tomorrow
        # tomorrow sunset=21:02, window_end=23:02 → hours 5..22 = 18 bars
        now = datetime(2026, 5, 10, 22, 0)
        result = score_forecast(self._make_forecast(), now=now)
        assert result["is_tomorrow"] is True
        assert result["hours"][-1]["hour"] == 22

    def test_exactly_3_hours_stays_on_today(self):
        # now=20:00, window_end=23:00 → hours 20,21,22 = 3 bars → NOT < 3 → today
        now = datetime(2026, 5, 10, 20, 0)
        result = score_forecast(self._make_forecast(), now=now)
        assert result["is_tomorrow"] is False
        assert len(result["hours"]) == 3
```

- [ ] **Step 2: Run new tests to confirm they fail**

```bash
pytest tests/test_weather.py::TestScoreForecastWindowing -v
```

Expected: FAIL — `score_forecast()` missing required argument `now` (or TypeError).

- [ ] **Step 3: Replace `score_forecast` in `runcoach/weather.py`**

Add `from datetime import datetime, timedelta` to the imports at the top of `weather.py` (replace the existing `from datetime import datetime`):

```python
from datetime import datetime, timedelta
```

Then replace the entire `score_forecast` function with:

```python
def score_forecast(forecast: dict, now: datetime) -> dict:
    """Score hours within the actionable window and build the API response payload."""
    sunrises = forecast["sunrise"]
    sunsets = forecast["sunset"]
    today_sunrise = sunrises[0]
    today_sunset = sunsets[0]

    now_snapped = now.replace(minute=0, second=0, microsecond=0)
    today_window_end = today_sunset + timedelta(hours=2)

    today_hours = [
        h for h in forecast["hours"]
        if h["dt"].date() == today_sunrise.date()
        and h["dt"] >= now_snapped
        and h["dt"] < today_window_end
    ]

    if len(today_hours) < 3 and len(sunrises) > 1:
        is_tomorrow = True
        tomorrow_sunrise = sunrises[1]
        tomorrow_sunset = sunsets[1]
        tomorrow_start = tomorrow_sunrise.replace(minute=0, second=0, microsecond=0)
        tomorrow_window_end = tomorrow_sunset + timedelta(hours=2)
        window_hours = [
            h for h in forecast["hours"]
            if h["dt"].date() == tomorrow_sunrise.date()
            and h["dt"] >= tomorrow_start
            and h["dt"] < tomorrow_window_end
        ]
        day_sunrise = tomorrow_sunrise
        day_sunset = tomorrow_sunset
    else:
        is_tomorrow = False
        window_hours = today_hours
        day_sunrise = today_sunrise
        day_sunset = today_sunset

    scored_hours = []
    for h in window_hours:
        s = score_hour(
            temp_c=h["temp_c"],
            rain_pct=h["rain_pct"],
            humidity_pct=h["humidity_pct"],
            wind_kmh=h["wind_kmh"],
            dt=h["dt"],
            sunrise=day_sunrise,
            sunset=day_sunset,
        )
        scored_hours.append({
            "hour": h["hour"],
            "score": s,
            "temp_c": round(h["temp_c"], 1),
            "rain_pct": int(h["rain_pct"]),
            "humidity_pct": int(h["humidity_pct"]),
            "wind_kmh": round(h["wind_kmh"], 1),
        })

    if not scored_hours:
        date_val = (sunrises[1] if is_tomorrow else today_sunrise).date()
        return {
            "date": date_val.isoformat(),
            "hours": [],
            "best_hour": 0,
            "best_score": 0,
            "day_label": "No forecast available",
            "is_tomorrow": is_tomorrow,
        }

    best = max(scored_hours, key=lambda x: x["score"])
    best_score = best["score"]
    best_hour = best["hour"]
    date_val = (sunrises[1] if is_tomorrow else today_sunrise).date()

    if best_score >= 4:
        suffix = "am" if best_hour < 12 else "pm"
        display = best_hour % 12 or 12
        day_label = f"Best window: {display}{suffix} · {best_score}/10"
    else:
        day_label = "No good windows tomorrow" if is_tomorrow else "No good windows today"

    return {
        "date": date_val.isoformat(),
        "hours": scored_hours,
        "best_hour": best_hour,
        "best_score": best_score,
        "day_label": day_label,
        "is_tomorrow": is_tomorrow,
    }
```

- [ ] **Step 4: Update existing `TestScoreForecast` tests in `tests/test_weather.py` to pass `now`**

Replace the entire `TestScoreForecast` class with:

```python
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
```

- [ ] **Step 5: Run all weather tests to confirm they pass**

```bash
pytest tests/test_weather.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add runcoach/weather.py tests/test_weather.py
git commit -m "feat: score_forecast trims hours to actionable window, falls back to tomorrow"
```

---

## Task 3: Update API endpoints to pass `now`

**Files:**
- Modify: `runcoach/web/api.py`
- Modify: `runcoach/web/routes.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Update the mock fake result in `tests/test_api.py`**

In `TestBestRunTime.test_returns_scored_forecast`, update `fake_result` to include `is_tomorrow` and change the `hours` length assertion:

Find the `fake_result` dict and replace it with:

```python
fake_result = {
    "date": "2026-05-10",
    "hours": [{"hour": h, "score": 7, "temp_c": 12.0, "rain_pct": 5, "humidity_pct": 55, "wind_kmh": 10.0} for h in range(8)],
    "best_hour": 9,
    "best_score": 8,
    "day_label": "Best window: 9am · 8/10",
    "is_tomorrow": False,
}
```

And update the assertion `assert len(data["hours"]) == 24` to:

```python
assert len(data["hours"]) == 8
assert data["is_tomorrow"] is False
```

- [ ] **Step 2: Run `TestBestRunTime` to confirm current state**

```bash
pytest tests/test_api.py::TestBestRunTime -v
```

Expected: all tests PASS (the mock insulates them from the signature change — this is a baseline check).

- [ ] **Step 3: Update `api_best_run_time` in `runcoach/web/api.py`**

Add `zoneinfo` to the imports at the top of `api.py`. Find the line:
```python
from datetime import datetime, timezone, date as date_type
```
Replace with:
```python
from datetime import datetime, timezone, date as date_type
from zoneinfo import ZoneInfo
```

Then in `api_best_run_time`, replace:
```python
    return jsonify(score_forecast(forecast)), 200
```
with:
```python
    now = datetime.now(ZoneInfo(cfg.timezone)).replace(tzinfo=None)
    return jsonify(score_forecast(forecast, now=now)), 200
```

- [ ] **Step 4: Update `best_run_time` in `runcoach/web/routes.py`**

Add `zoneinfo` and `datetime` imports to `routes.py`. Find the line:
```python
from datetime import date
```
Replace with:
```python
from datetime import date, datetime
from zoneinfo import ZoneInfo
```

Then in `best_run_time`, replace:
```python
    return jsonify(score_forecast(forecast)), 200
```
with:
```python
    now = datetime.now(ZoneInfo(cfg.timezone)).replace(tzinfo=None)
    return jsonify(score_forecast(forecast, now=now)), 200
```

- [ ] **Step 5: Run API tests to confirm they pass**

```bash
pytest tests/test_api.py::TestBestRunTime -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add runcoach/web/api.py runcoach/web/routes.py tests/test_api.py
git commit -m "feat: pass current local time to score_forecast in best-run-time endpoints"
```

---

## Task 4: Update Flutter `BestRunTimeCard`

**Files:**
- Modify: `mobile/lib/widgets/best_run_time_card.dart`
- Modify: `mobile/test/widgets/best_run_time_card_test.dart`

- [ ] **Step 1: Update `_fakeData` and add failing tests in `best_run_time_card_test.dart`**

Replace the entire file with:

```dart
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:runcoach/widgets/best_run_time_card.dart';
import 'package:runcoach/providers/best_run_time_provider.dart';

// 6 hours (5am–10am), is_tomorrow: false by default
Map<String, dynamic> _fakeData({int bestScore = 8, bool isTomorrow = false}) => {
  'date': '2026-05-10',
  'is_tomorrow': isTomorrow,
  'hours': List.generate(
    6,
    (i) => {
      'hour': i + 5,
      'score': (i + 5) == 9 ? bestScore : 4,
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
  overrides: [bestRunTimeProvider.overrideWith((_) async => data)],
  child: const MaterialApp(home: Scaffold(body: BestRunTimeCard())),
);

void main() {
  testWidgets('shows day_label when data available', (tester) async {
    await tester.pumpWidget(_wrap(_fakeData()));
    await tester.pumpAndSettle();
    expect(find.textContaining('Best window'), findsOneWidget);
  });

  testWidgets('renders bar chart row', (tester) async {
    await tester.pumpWidget(_wrap(_fakeData()));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('brt-bars')), findsOneWidget);
  });

  testWidgets('title shows today when is_tomorrow is false', (tester) async {
    await tester.pumpWidget(_wrap(_fakeData()));
    await tester.pumpAndSettle();
    expect(find.text('Best time to run today'), findsOneWidget);
  });

  testWidgets('title shows tomorrow when is_tomorrow is true', (tester) async {
    await tester.pumpWidget(_wrap(_fakeData(isTomorrow: true)));
    await tester.pumpAndSettle();
    expect(find.text('Best time to run tomorrow'), findsOneWidget);
  });

  testWidgets('axis shows first and last hour labels', (tester) async {
    // _fakeData hours: 5,6,7,8,9,10 → first=5am, last=10am
    await tester.pumpWidget(_wrap(_fakeData()));
    await tester.pumpAndSettle();
    expect(find.text('5am'), findsOneWidget);
    expect(find.text('10am'), findsOneWidget);
  });

  testWidgets('hidden when location unavailable (null data)', (tester) async {
    await tester.pumpWidget(_wrap(null));
    await tester.pumpAndSettle();
    expect(find.byType(BestRunTimeCard), findsOneWidget);
    expect(find.textContaining('Best window'), findsNothing);
  });

  testWidgets('shows loading indicator while fetching', (tester) async {
    final completer = Completer<Map<String, dynamic>?>();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [bestRunTimeProvider.overrideWith((_) => completer.future)],
        child: const MaterialApp(home: Scaffold(body: BestRunTimeCard())),
      ),
    );
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    completer.complete(null);
  });
}
```

- [ ] **Step 2: Run Flutter tests to confirm they fail**

```bash
cd mobile && flutter test test/widgets/best_run_time_card_test.dart
```

Expected: FAIL — `find.text('Best time to run today')` not found (currently hardcoded string may not match, title test for tomorrow will definitely fail), axis label tests fail.

- [ ] **Step 3: Replace `best_run_time_card.dart` with the updated widget**

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

  String _hourLabel(int h) {
    if (h == 0) return '12am';
    if (h == 12) return '12pm';
    return h < 12 ? '${h}am' : '${h - 12}pm';
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
        final isTomorrow = data['is_tomorrow'] as bool? ?? false;
        const maxBarHeight = 48.0;

        final firstHour = hours.first['hour'] as int;
        final midHour = hours[hours.length ~/ 2]['hour'] as int;
        final lastHour = hours.last['hour'] as int;

        return Card(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      isTomorrow
                          ? 'Best time to run tomorrow'
                          : 'Best time to run today',
                      style: const TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    Text(
                      dayLabel,
                      style: const TextStyle(
                        fontSize: 11,
                        color: Color(0xFF888888),
                      ),
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
                                top: Radius.circular(2),
                              ),
                              border: isHour == bestHour
                                  ? Border.all(color: Colors.white70, width: 1)
                                  : null,
                            ),
                          ),
                        ),
                      );
                    }).toList(),
                  ),
                ),
                const SizedBox(height: 2),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      _hourLabel(firstHour),
                      style: const TextStyle(
                          fontSize: 9, color: Color(0xFF888888)),
                    ),
                    Text(
                      _hourLabel(midHour),
                      style: const TextStyle(
                          fontSize: 9, color: Color(0xFF888888)),
                    ),
                    Text(
                      _hourLabel(lastHour),
                      style: const TextStyle(
                          fontSize: 9, color: Color(0xFF888888)),
                    ),
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

- [ ] **Step 4: Run Flutter tests to confirm they pass**

```bash
cd mobile && flutter test test/widgets/best_run_time_card_test.dart
```

Expected: all tests PASS.

- [ ] **Step 5: Run `dart format` to enforce CI formatting**

```bash
cd mobile && dart format --output=none --set-exit-if-changed .
```

Expected: exit 0 (no formatting changes needed). If it exits non-zero, run `dart format .` to apply formatting, then re-run the check.

- [ ] **Step 6: Commit**

```bash
git add mobile/lib/widgets/best_run_time_card.dart mobile/test/widgets/best_run_time_card_test.dart
git commit -m "feat: BestRunTimeCard uses dynamic title and time axis labels (issue #32)"
```

---

## Task 5: Update web dashboard template

**Files:**
- Modify: `runcoach/web/templates/index.html`

- [ ] **Step 1: Replace static title and axis labels in `index.html`**

In `runcoach/web/templates/index.html`, find the `brt-card` div:

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
```

Replace with:

```html
<div id="brt-card" class="card" style="display:none;">
  <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:0.5rem;">
    <h2 id="brt-title" style="margin:0;"></h2>
    <span id="brt-label" style="font-size:0.8rem; color:var(--fg-muted);"></span>
  </div>
  <div id="brt-chart" style="display:flex; align-items:flex-end; gap:2px; height:60px; margin-bottom:0.25rem;"></div>
  <div id="brt-axis" style="display:flex; justify-content:space-between; font-size:0.65rem; color:var(--fg-muted); padding:0 1px;"></div>
</div>
```

- [ ] **Step 2: Update the JavaScript block to set title and axis dynamically**

Find the `.then(function(data) {` block inside the `<script>` tag and replace it with:

```javascript
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!data.hours || !data.hours.length) return;
      document.getElementById('brt-title').textContent =
        data.is_tomorrow ? 'Best time to run tomorrow' : 'Best time to run today';
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
      function hourLabel(h) {
        if (h === 0) return '12am';
        if (h === 12) return '12pm';
        return h < 12 ? h + 'am' : (h - 12) + 'pm';
      }
      var firstH = data.hours[0].hour;
      var midH = data.hours[Math.floor(data.hours.length / 2)].hour;
      var lastH = data.hours[data.hours.length - 1].hour;
      var axis = document.getElementById('brt-axis');
      [firstH, midH, lastH].forEach(function(h) {
        var s = document.createElement('span');
        s.textContent = hourLabel(h);
        axis.appendChild(s);
      });
      document.getElementById('brt-label').textContent = data.day_label;
      document.getElementById('brt-card').style.display = 'block';
    })
```

- [ ] **Step 3: Commit**

```bash
git add runcoach/web/templates/index.html
git commit -m "feat: web dashboard best-run-time card uses dynamic title and axis labels"
```

---

## Task 6: Final verification

- [ ] **Step 1: Run the full Python test suite**

```bash
pytest && pytest -m e2e --no-cov -v
```

Expected: all tests PASS.

- [ ] **Step 2: Run the full Flutter test suite with dart format check**

```bash
cd mobile && dart format --output=none --set-exit-if-changed . && flutter test
```

Expected: `dart format` exits 0, all Flutter tests PASS.

- [ ] **Step 3: Raise the PR**

```bash
git push origin feature/issue-26-best-run-time
gh pr create \
  --title "feat: trim Best Run Time chart to current window (issue #32)" \
  --body "$(cat <<'EOF'
## Summary

- `fetch_forecast` now fetches 2 days from Open-Meteo so a tomorrow fallback is always available
- `score_forecast` gains a `now` parameter and trims the hours list to today's actionable window (current hour → sunset+2h), falling back to tomorrow (sunrise → sunset+2h) when fewer than 3 hours remain
- Both the mobile API and web dashboard endpoints pass the current local time
- Flutter `BestRunTimeCard` and the web dashboard card display a dynamic title (today/tomorrow) and 3-label time axis derived from the returned hours

Closes #32
EOF
)"
```
