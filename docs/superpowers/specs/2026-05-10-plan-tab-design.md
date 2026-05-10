# Plan Tab — Design Spec

**Date:** 2026-05-10
**Issue:** #25 — Add future workouts to the Mobile app

## Overview

Add a new **Plan** tab to the mobile app showing all upcoming planned workouts from today until the end of the synced Stryd training plan, grouped by week. Tapping any workout opens the existing `WorkoutDetailScreen` (Overview / Structure / Route tabs).

---

## Backend

### New endpoint

```
GET /api/v1/planned-workouts
```

- Requires JWT auth (`@require_auth`).
- Calls `db.get_upcoming_planned_workouts(from_date=today, limit=90, user_id=user_id)`.
  - 90-day limit comfortably covers any realistic Stryd plan window.
- Returns a JSON array of planned workout objects.

### Response shape

```json
[
  {
    "id": 42,
    "date": "2026-05-12",
    "name": "Easy Run",
    "description": "...",
    "distance_m": 8000.0,
    "duration_s": 3600.0,
    "stress": 45.2,
    "intensity_zones": [10, 60, 20, 8, 2],
    "structure": [
      {
        "repeat": 1,
        "segments": [
          {"intensity_class": "warmup", "duration_s": 600, "power_min_pct": 65, "power_max_pct": 79}
        ]
      }
    ]
  }
]
```

All fields except `id` and `date` are nullable.

### Shared serialisation

Extract a `_format_planned_workout(w: dict) -> dict` helper from the existing inline `next_workout` block in `dashboard()`. Both `dashboard()` and the new `planned_workouts()` endpoint use it, eliminating duplication. The helper adds `stress` (currently missing from the dashboard response).

### Tests

- Unit test for the new endpoint: authenticated request returns list; `stress` field present; empty list when no upcoming workouts.
- Update `dashboard` test to confirm `stress` is now included in `next_workout`.

---

## Mobile

### Model change

`PlannedWorkout` (`models/planned_workout.dart`): add `final double? stress` field and deserialise from `json['stress']`.

### New files

| File | Purpose |
|---|---|
| `providers/plan_provider.dart` | `FutureProvider.autoDispose<List<PlannedWorkout>>` watching `authProvider`, calling `api.getPlannedWorkouts()` |
| `screens/plan_screen.dart` | Plan tab screen (see UI section) |
| `widgets/plan_workout_card.dart` | Card widget used in the Plan screen list |

### ApiService change

Add `getPlannedWorkouts()` to `api_service.dart`:

```dart
Future<List<PlannedWorkout>> getPlannedWorkouts() async {
  final resp = await _dio.get('/planned-workouts');
  return (resp.data as List<dynamic>)
      .map((e) => PlannedWorkout.fromJson(e as Map<String, dynamic>))
      .toList();
}
```

### Routing (`app.dart`)

- Add `/plan` as a `GoRoute` inside the `ShellRoute` siblings, between `/activities` and `/profile`.
- The existing root-level `/workout-detail` route stays and is reused. Both `NextWorkoutCard` (home) and `PlanWorkoutCard` push `/workout-detail` with the `PlannedWorkout` as `state.extra`. No new route needed.
- Nav bar: add a fourth `NavigationDestination` between Activities and Profile:
  - Icon: `Icons.calendar_month_outlined` / selected: `Icons.calendar_month`
  - Label: `"Plan"`
- Update the `index` switch in `ScaffoldWithNavBar` to handle `/plan → 2`, `/profile → 3`.

### Plan screen UI (`plan_screen.dart`)

`PlanScreen` is a `ConsumerWidget` watching `planProvider`.

- **Loading**: `CircularProgressIndicator` centered.
- **Error**: centered error message.
- **Empty**: centered text — *"No upcoming workouts. Sync to fetch your training plan."*
- **Data**: `RefreshIndicator` wrapping a `ListView`. The workout list is grouped into weeks client-side by the Monday of each workout's date. Two item types rendered inline:
  - **Week header**: `"WEEK OF 12 MAY"` — small-caps label style, muted colour, left-padded 16px, 12px vertical padding.
  - **Workout card**: `PlanWorkoutCard` (see below).

### Plan workout card (`plan_workout_card.dart`)

Tapping calls `context.push('/plan/workout-detail', extra: workout)`.

Layout (inside a `Card` with left amber border, matching `NextWorkoutCard` style):

```
MON 12 MAY                          >
Easy Run
45 min  ·  8.0 km  ·  RSS 45
```

- Top line: `"${dayName} ${day} ${monthName}"` — 10px muted label, letter-spaced.
- Middle: workout name, 15px bold.
- Bottom row: duration, distance, RSS — each shown only if non-null, joined with `·`. 11px, muted colour.

### Flutter tests

- `plan_provider_test.dart`: mock `ApiService`, verify provider returns parsed list.
- `plan_workout_card_test.dart`: widget test — card shows name, duration, distance, RSS; omits null fields.
- `plan_screen_test.dart`: empty state message; loading state; populated list groups by week with correct headers.

---

## What is not in scope

- Pagination (Stryd syncs ~30 days ahead; 90-item limit is sufficient).
- Marking workouts as complete from the Plan tab.
- Any changes to the web UI.
