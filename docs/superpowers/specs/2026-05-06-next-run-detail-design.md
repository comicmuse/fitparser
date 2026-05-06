# Next Run Detail Screen — Design Spec

## Overview

Improve the "Next Activity" section of the mobile home screen: truncate the description to the first paragraph with a drill-down chevron, and add a dedicated detail screen showing the full description, a power zone breakdown, and 3 route suggestions.

## Architecture

Four coordinated changes:

1. **Backend** — extend the dashboard `next_workout` JSON with `id`, `distance_m`, `duration_s`, `intensity_zones`. Add a new JWT-auth `POST /api/v1/route-suggestion` endpoint (same logic as the existing session-auth route, different decorator).
2. **`PlannedWorkout` model** — add the four new fields; `intensityZones` is `List<int>?` (5 elements, seconds per zone Z1–Z5).
3. **`NextWorkoutCard`** (modified) — shows first paragraph of description only, right-facing chevron, tappable; navigates to the detail screen via GoRouter `extra`.
4. **`WorkoutDetailScreen`** (new) — tabbed screen matching the `RunDetailScreen` pattern.

### Data Flow

```
dashboardProvider → PlannedWorkout (extended model)
  └─ NextWorkoutCard (tap) → GoRouter.push('/workout-detail', extra: workout)
       └─ WorkoutDetailScreen receives GoRouterState.extra as PlannedWorkout
            ├─ Overview tab: renders directly from workout fields (no fetch)
            └─ Route tab: locationService → POST /api/v1/route-suggestion → local state
```

## Components

### `NextWorkoutCard` (modified)

- Truncate `description` to the first paragraph (split on `\n\n`, take index 0; fall back to full text if no double newline)
- Add `chevron_right` icon aligned to the card's trailing edge
- Wrap in `InkWell` / `GestureDetector`; on tap, `context.push('/workout-detail', extra: workout)`

### `WorkoutDetailScreen` (new)

Header: gradient `#1c1917 → #ea580c` (orange, distinct from `RunDetailScreen`'s blue). Shows:
- Back navigation + workout date
- Title (workout name)
- Subtitle: formatted duration + distance (e.g., "40 min · 6.3 km")

Two tabs in the header: **Overview** | **Route**

**Overview tab**
- Full description text
- `PowerZoneBar` widget (hidden if all zones are zero or field is null)

**Route tab**
- Fetched lazily on first tab entry
- Requests device location, then calls `POST /api/v1/route-suggestion` with `{lat, lng, distance_m}`
- Displays up to 3 route suggestions with Prev/Next navigation
- Routes stored in local widget state (ephemeral, no provider)

### `PowerZoneBar` (new widget)

Stateless. Takes `List<int> zones` (5 elements, seconds).

- Renders a horizontal stacked bar; each non-zero zone gets a proportional segment
- Zone colours: Z1 `#4ade80`, Z2 `#a3e635`, Z3 `#facc15`, Z4 `#f97316`, Z5 `#ef4444`
- Below the bar: label per non-zero zone ("Z1 39:00") in the zone's colour
- Hidden entirely if all values are zero or input is null

### Navigation

New GoRouter route: `/workout-detail` (no ID in path — data passed via `extra`). Deep-linking not required; screen is only reachable from the home page.

## Backend Changes

### Dashboard API (`/api/v1/dashboard`)

Extend `next_workout` response object with:

```json
{
  "id": 784,
  "date": "2026-05-09",
  "name": "Easy Run / Strides #01",
  "description": "...",
  "distance_m": 6292.8,
  "duration_s": 2400.0,
  "intensity_zones": [2340, 0, 0, 60, 0]
}
```

`intensity_zones` is stored as a JSON string in the DB; parse it before returning.

### New JWT Route Suggestion Endpoint

`POST /api/v1/route-suggestion`

Request body: `{ "lat": float, "lng": float, "distance_m": float }`

Response: same shape as the existing session-auth endpoint (array of up to 3 route objects).

Implementation: extract the ORS call logic from the existing `POST /route-suggestion` web route into a shared helper; call it from both the session-auth and JWT-auth endpoints.

## Error Handling

| Scenario | Behaviour |
|---|---|
| `intensity_zones` null or all-zeros | Zone bar section hidden; no empty state shown |
| Location permission denied | Route tab: "Location access needed for route suggestions" (no retry) |
| Location timeout / route fetch failure | Route tab: "Couldn't load route suggestions" + retry button |
| No next workout | `NextWorkoutCard` already handles null; no change |

## Testing

- **Unit**: `PlannedWorkout.fromJson()` round-trips the new fields; `intensityZones` correctly parses from the DB's JSON string format `"[1590, 2520, 0, 0, 0]"`
- **Widget**: `PowerZoneBar` renders correct proportional segments, suppresses zero-zone entries
- **Widget**: `NextWorkoutCard` truncates description to first paragraph and displays chevron
- **Python**: `POST /api/v1/route-suggestion` returns 401 without JWT, 200 with valid token
- No Playwright E2E tests (mobile-only screen)
