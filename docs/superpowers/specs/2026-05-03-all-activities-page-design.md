# All Activities Page — Redesign

**Date:** 2026-05-03

## Context

The existing `/workouts` page mixes actual runs with planned workouts (past and upcoming) in three separate paginated tables. Pagination breaks the page width and doesn't scale well for 400+ runs over 5 years. The user wants a dedicated activity log focused solely on completed runs, with calendar-based navigation instead of page numbers.

## Design

### What changes

- Remove all planned workout sections (upcoming and past) from `/workouts`
- Replace three-table layout with a single monthly run list
- Replace pagination with year pill + month pill navigation
- Add SVG route thumbnails to run cards where a Strava polyline is stored

### Navigation

Year pills render as a horizontal row at the top — one pill per year that has at least one run. The current (or most recently selected) year is highlighted in accent orange. Clicking a year updates the month pills row below it.

Month pills render below the year row — one per month of the selected year, showing the run count. Months with zero runs are shown greyed/disabled. The current (or most recently selected) month is highlighted. Default view on page load: current year, current month (or most recent month with runs).

Both rows are generated server-side from a `year_months` summary dict passed to the template. Navigation triggers a simple GET request: `/workouts?year=2026&month=5`.

### Run list

Runs for the selected year+month render as cards, most recent first. Each card contains:

- **Route thumbnail** (52×52px): SVG polyline decoded server-side from `strava_map_polyline`, scaled to fit the box. Runs without a polyline show a dashed placeholder box (no icon, just empty).
- **Name**: `workout_name` falling back to `name`
- **Date line**: day + date + distance + duration + avg power (if present) + avg HR (if present)
- **Status badge**: Analyzed / Parsed / Synced / Error (same badge styles as elsewhere)
- **Manual badge**: shown if `is_manual_upload`

Cards link to the run detail page on click (whole card, not just the name).

### Server-side polyline decoding

Add a `decode_polyline(encoded)` utility function in `runcoach/strava.py` (or a new `runcoach/geo.py`) that decodes a Google-encoded polyline string into a list of `(lat, lng)` coordinate pairs. Then a `polyline_to_svg_path(coords, size=52)` function normalises the coordinates to fit within a `size × size` viewBox and returns an SVG `<polyline points="...">` string. This is called in the route and the result stored on each run dict before passing to the template.

### DB changes

Add a new DB method `get_runs_for_month(year, month, user_id)` returning runs where `date` matches `YYYY-MM-%`, ordered by date DESC. Add `get_year_month_summary(user_id)` returning a list of `{year, month, count}` rows (one per non-empty month), used to build the navigation pills.

### Route changes

`/workouts` route simplified to:
- Read `year` and `month` query params (default: current year/month)
- Call `get_year_month_summary` to build pill data
- Call `get_runs_for_month` to fetch the run list
- Decode polylines and attach SVG paths to each run dict
- Remove all planned workout fetching and pagination logic

### Template changes

`workouts.html` rewritten to:
- Year pills row
- Month pills row
- Month heading (`May 2026 · N runs`)
- Run card list
- No pagination controls

## Out of scope

- Filtering by run type or status
- Infinite scroll or lazy loading
- Editing or deleting runs from this page

## Testing

- Unit test `decode_polyline` with a known encoded string
- Unit test `polyline_to_svg_path` — check output is valid SVG points within bounds
- Unit test `get_runs_for_month` and `get_year_month_summary` DB methods
- Update `test_web.py` — existing workouts route tests will need to reflect new query params and removed planned workout context vars
- Manual: navigate year/month pills, verify correct runs shown; verify route thumbnail renders on Strava-linked run; verify placeholder on manual upload
