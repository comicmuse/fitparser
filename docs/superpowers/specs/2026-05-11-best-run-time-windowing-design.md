# Best Run Time Windowing — Design Spec

**Issue:** #32 — Start the Best Times to Run graph from the current hour  
**Date:** 2026-05-11  
**Branch:** feature/issue-32-best-run-time-windowing

## Summary

The Best Times to Run bar chart currently shows all 24 hours of the day, starting from midnight. This change trims the chart to only show the actionable window: from the current hour to 2 hours after sunset. If fewer than 3 hours remain in today's window (or it's already past sunset+2h), the chart switches to show tomorrow's window (tomorrow's sunrise to tomorrow's sunset+2h).

This applies to both the Flutter mobile card and the web dashboard card.

## Decisions Made

| Question | Decision |
|---|---|
| Chart approach | Trim to window — show only the relevant hours (Option A) |
| Minimum hours for "enough time" | 3 hours |
| Tomorrow's window | Sunrise to sunset+2h (same windowing logic as today) |
| Where logic lives | Backend-owned — all windowing computed in Python |
| Platforms affected | Both Flutter mobile and web dashboard |

---

## Architecture

All windowing logic lives in `weather.py`. Both API endpoints pass a timezone-aware `now` to `score_forecast`. The frontends render whatever `hours` they receive — no client-side time logic.

---

## Section 1 — Backend: `weather.py`

### `fetch_forecast`

Add `days=2` parameter (default 2). Open-Meteo is called with `forecast_days=2`, producing:
- 48 hourly entries
- 2-element `sunrise` and `sunset` daily arrays

Return shape:
```python
{
  "hours": [48 dicts, each with "dt" as a timezone-aware datetime, plus temp/rain/etc.],
  "sunrise": [today_datetime, tomorrow_datetime],
  "sunset":  [today_datetime, tomorrow_datetime],
}
```

### `score_forecast`

Add `now: datetime` parameter (timezone-aware, required).

**Window selection logic:**

1. Compute `today_window_end = today_sunset + timedelta(hours=2)`
2. Filter: `today_hours = [h for h in hours if h["dt"].date() == today and now <= h["dt"] < today_window_end]`
3. If `len(today_hours) < 3`:
   - `is_tomorrow = True`
   - `window_hours = [h for h in hours if h["dt"].date() == tomorrow and tomorrow_sunrise <= h["dt"] < tomorrow_sunset + 2h]`
4. Else:
   - `is_tomorrow = False`
   - `window_hours = today_hours`

Score `window_hours`, find best, build `day_label` (existing logic unchanged).

**Response shape** (additions in bold):

```python
{
  "date": "2026-05-11",
  "hours": [...],        # trimmed to window — variable length (typically 4–18)
  "best_hour": 19,
  "best_score": 8,
  "day_label": "Best window: 7pm · 8/10",
  "is_tomorrow": False,  # NEW
}
```

---

## Section 2 — API Endpoints

Both endpoints get the same change — pass `datetime.now(ZoneInfo(cfg.timezone))` to `score_forecast`:

Open-Meteo returns naive local datetimes (e.g. `"2026-05-11T17:00"`) when a timezone is set — no UTC offset in the string. So `now` must also be naive local time in the configured timezone, otherwise comparisons raise `TypeError`.

**`runcoach/web/api.py`** — `api_best_run_time()`:
```python
from zoneinfo import ZoneInfo
from datetime import datetime

forecast = fetch_forecast(lat, lng, cfg.timezone)
now = datetime.now(ZoneInfo(cfg.timezone)).replace(tzinfo=None)
return jsonify(score_forecast(forecast, now=now))
```

**`runcoach/web/routes.py`** — `best_run_time()`: identical change.

No new routes. No new parameters exposed to clients.

---

## Section 3 — Flutter: `BestRunTimeCard`

**File:** `mobile/lib/widgets/best_run_time_card.dart`

### Title

Change from hardcoded `'Best time to run today'` to:
```dart
final isTomorrow = data['is_tomorrow'] as bool? ?? false;
// in the Text widget:
isTomorrow ? 'Best time to run tomorrow' : 'Best time to run today'
```

### Time axis labels

Replace the 5 hardcoded `Text` widgets with 3 dynamic labels derived from the `hours` list:

```dart
String _hourLabel(int h) {
  if (h == 0) return '12am';
  if (h == 12) return '12pm';
  return h < 12 ? '${h}am' : '${h - 12}pm';
}

final firstHour = hours.first['hour'] as int;
final midHour   = hours[hours.length ~/ 2]['hour'] as int;
final lastHour  = hours.last['hour'] as int;
```

Render as a `Row` with `MainAxisAlignment.spaceBetween` containing 3 `Text` widgets.

The bar rendering loop (`hours.map(...)`) already handles variable-length lists — no change needed there.

---

## Section 4 — Web Dashboard: `index.html`

**File:** `runcoach/web/templates/index.html`

### Title

Replace the static `<h2>Best time to run today</h2>` with:
```html
<h2 id="brt-title" style="margin:0;"></h2>
```

Set in JS after data loads:
```javascript
document.getElementById('brt-title').textContent =
  data.is_tomorrow ? 'Best time to run tomorrow' : 'Best time to run today';
```

### Axis labels

Replace the 5 hardcoded `<span>` elements with an empty container:
```html
<div id="brt-axis" style="display:flex; justify-content:space-between; font-size:0.65rem; color:var(--fg-muted); padding:0 1px;"></div>
```

Populate in JS after rendering bars:
```javascript
function hourLabel(h) {
  if (h === 0) return '12am';
  if (h === 12) return '12pm';
  return h < 12 ? h + 'am' : (h - 12) + 'pm';
}
var firstH = data.hours[0].hour;
var midH   = data.hours[Math.floor(data.hours.length / 2)].hour;
var lastH  = data.hours[data.hours.length - 1].hour;
var axis = document.getElementById('brt-axis');
[firstH, midH, lastH].forEach(function(h) {
  var s = document.createElement('span');
  s.textContent = hourLabel(h);
  axis.appendChild(s);
});
```

---

## Section 5 — Testing

### Python unit tests (`tests/test_weather.py` or inline in `tests/test_api.py`)

New tests for `score_forecast` with `now` parameter:

- `now` within today's window → `is_tomorrow: False`, `hours` trimmed to `[now, sunset+2h)`
- `now` with fewer than 3 hours to `sunset+2h` → `is_tomorrow: True`, hours anchored to tomorrow's sunrise
- `now` after `sunset+2h` → `is_tomorrow: True`
- Tomorrow window correctly anchored to tomorrow's sunrise (not midnight)

### Flutter widget tests (`mobile/test/widgets/best_run_time_card_test.dart`)

- Update `_fakeData` to use a short `hours` list (e.g. 6 entries) with `is_tomorrow: false`
- Add `_fakeTomorrowData` with `is_tomorrow: true` — assert title shows "Best time to run tomorrow"
- Assert dynamic axis labels appear (first and last hour text present)
- Update "renders 24 bars" test to match variable bar count

### E2E tests

No new E2E tests — the web card renders client-side via geolocation JS and is not covered by the existing Playwright suite.
