# Route Suggestion Feature — Design Spec

**Date:** 2026-05-04

## Context

Users have planned workouts with a target distance. Before heading out, they need a round-trip running route that matches that distance starting from their current location. The app already renders Leaflet maps on the run detail page (Strava polylines); this feature adds a route-generation capability using the same map infrastructure.

## What We're Building

A "Suggested Route" section inside the existing **Prescribed Workout** card on the planned workout detail page (`run_detail.html`). The user clicks a button, grants geolocation, and gets 3 round-trip route options to cycle through on a Leaflet map.

## Routing API

**OpenRouteService (ORS)** — free tier, native round-trip pedestrian/running route endpoint. Returns up to 3 route variations in one call.

- Endpoint: `POST https://api.openrouteservice.org/v2/directions/foot-running/geojson`
- Round-trip params: `options.round_trip.length` (metres), `options.round_trip.points` (3 = 3 variants)
- Pedestrian preference: `profile_params.weightings.green = 1` (prefers parks/green areas/pedestrian paths) and `profile_params.weightings.quiet = 1` (prefers quieter ways over busy roads). Both are supported on `foot-*` profiles and together steer routes away from motorways/main roads toward footpaths and trails.
- API key stored in `.env` as `ORS_API_KEY`, never exposed to the client.

## Architecture

### New Flask route

```
GET /api/route-suggestion?lat=<float>&lng=<float>&distance_m=<int>
```

- Requires login (existing `@login_required` decorator)
- Validates params; calls ORS with the user's location and the target distance
- Returns JSON: `{ "routes": [ { "coords": [[lat,lng],...], "distance_m": 10234 }, ... ] }` (up to 3 items)
- On ORS error: returns `{ "error": "..." }` with appropriate HTTP status

### Template changes (`run_detail.html`)

Inside the existing `{% if prescribed %}` card, after the workout metadata, add a **Suggested Route** subsection:

1. **"📍 Suggest a Route" button** — visible when `pw.distance_m` is set
2. **Loading state** — shown while fetching location + calling the API
3. **Leaflet map div** — rendered with the first route polyline
4. **Prev/Next controls** — cycle through the 3 alternatives client-side (no extra network calls)
5. **Distance label** — shows actual loop length for the displayed route

Leaflet CSS/JS already conditionally loaded when `map_coords` is set. Since `map_coords` may be `None` for planned-only pages, the template must load Leaflet unconditionally when a prescribed workout with distance is present.

### Client-side JS (inline in template)

```
suggestRoute()
  → navigator.geolocation.getCurrentPosition()
  → fetch('/api/route-suggestion?lat=…&lng=…&distance_m=…')
  → render routes[0] on Leaflet map
  → Prev/Next cycle routes array, re-draw polyline
```

All 3 GeoJSON polylines stored in a JS array after the first fetch — no repeat API calls when cycling.

## Configuration

Add to `.env.example`:
```
ORS_API_KEY=your_openrouteservice_api_key_here
```

Add to `config.py`:
```python
ORS_API_KEY = os.getenv("ORS_API_KEY", "")
```

## Error Handling

| Scenario | Behaviour |
|---|---|
| User denies geolocation | Show inline message: "Location access needed to suggest a route." |
| `ORS_API_KEY` not set | Return 503 with message in UI |
| ORS returns error / timeout | Show inline error below button; button resets to try again |
| `pw.distance_m` is None | Hide the Suggest Route section entirely |

## Files to Change

| File | Change |
|---|---|
| `runcoach/web/routes.py` | Add `GET /api/route-suggestion` route |
| `runcoach/config.py` | Add `ORS_API_KEY` |
| `runcoach/web/templates/run_detail.html` | Add route suggestion UI in prescribed workout card |
| `.env.example` | Add `ORS_API_KEY` placeholder |

## Verification

1. Set `ORS_API_KEY` in `.env` (get free key at openrouteservice.org)
2. Open a planned workout detail page that has `distance_m` set
3. Click "Suggest a Route" → allow location
4. Verify map renders with a round-trip polyline and distance label
5. Click Next/Prev — verify polyline changes, counter updates
6. Test with geolocation denied → verify graceful error message
7. Test with `ORS_API_KEY` unset → verify 503 with user-facing message
8. Run `pytest tests/test_web.py` — add a test for the new endpoint with mocked ORS response
