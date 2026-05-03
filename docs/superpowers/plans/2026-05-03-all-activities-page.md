# All Activities Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `/workouts` page (three paginated tables mixing runs and planned workouts) with a single activity log showing actual runs only, navigated by year/month pills, with SVG route thumbnails decoded from stored Strava polylines.

**Architecture:** Two new DB methods return a year/month summary and the runs for a selected month. A new `polyline_to_svg_path()` utility in `runcoach/strava.py` converts stored polylines to inline SVG. The route is simplified to use these and `workouts.html` is rewritten.

**Tech Stack:** Flask/Jinja2, SQLite via `RunCoachDB`, existing `decode_polyline()` in `runcoach/strava.py`, Chart.js not used here.

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `runcoach/db.py` | Modify | Add `get_year_month_summary()` and `get_runs_for_month()` |
| `runcoach/strava.py` | Modify | Add `polyline_to_svg_path()` |
| `runcoach/web/routes.py` | Modify | Rewrite `workouts()` — remove planned workout logic, add year/month nav |
| `runcoach/web/templates/workouts.html` | Rewrite | Year pills, month pills, run card list |
| `tests/test_context.py` | No change | Not affected |
| `tests/test_web.py` | Modify | Update workouts route tests for new query params and template vars |

---

### Task 1: Add `get_year_month_summary` DB method

**Files:**
- Modify: `runcoach/db.py` (after `count_runs` method, ~line 856)
- Test: `tests/test_web.py` (add inside `TestWorkoutsView`)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_web.py` inside `class TestWorkoutsView`:

```python
def test_get_year_month_summary(self, db):
    db.add_run(stryd_activity_id=None, name="Run A", date="2026-05-01", user_id=1)
    db.add_run(stryd_activity_id=None, name="Run B", date="2026-05-15", user_id=1)
    db.add_run(stryd_activity_id=None, name="Run C", date="2026-03-10", user_id=1)
    db.add_run(stryd_activity_id=None, name="Run D", date="2025-12-20", user_id=1)
    summary = db.get_year_month_summary(user_id=1)
    assert len(summary) == 3
    assert summary[0] == {"year": 2026, "month": 5, "count": 2}
    assert summary[1] == {"year": 2026, "month": 3, "count": 1}
    assert summary[2] == {"year": 2025, "month": 12, "count": 1}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
source .venv/bin/activate
pytest tests/test_web.py::TestWorkoutsView::test_get_year_month_summary -v
```

Expected: `FAILED` — `AttributeError: 'RunCoachDB' object has no attribute 'get_year_month_summary'`

- [ ] **Step 3: Implement `get_year_month_summary` in `runcoach/db.py`**

Add after the `count_runs` method (~line 856):

```python
def get_year_month_summary(self, user_id: int | None = None) -> list[dict]:
    """Return [{year, month, count}] for every month that has runs, newest first."""
    with self._connect() as conn:
        if user_id is not None:
            rows = conn.execute(
                """
                SELECT CAST(strftime('%Y', date) AS INTEGER) AS year,
                       CAST(strftime('%m', date) AS INTEGER) AS month,
                       COUNT(*) AS count
                FROM runs
                WHERE user_id = ?
                GROUP BY year, month
                ORDER BY year DESC, month DESC
                """,
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT CAST(strftime('%Y', date) AS INTEGER) AS year,
                       CAST(strftime('%m', date) AS INTEGER) AS month,
                       COUNT(*) AS count
                FROM runs
                GROUP BY year, month
                ORDER BY year DESC, month DESC
                """
            ).fetchall()
    return [{"year": r["year"], "month": r["month"], "count": r["count"]} for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_web.py::TestWorkoutsView::test_get_year_month_summary -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add runcoach/db.py tests/test_web.py
git commit -m "feat: add get_year_month_summary DB method"
```

---

### Task 2: Add `get_runs_for_month` DB method

**Files:**
- Modify: `runcoach/db.py` (after `get_year_month_summary`)
- Test: `tests/test_web.py` (add inside `TestWorkoutsView`)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_web.py` inside `class TestWorkoutsView`:

```python
def test_get_runs_for_month(self, db):
    db.add_run(stryd_activity_id=None, name="May Run 1", date="2026-05-03", user_id=1)
    db.add_run(stryd_activity_id=None, name="May Run 2", date="2026-05-01", user_id=1)
    db.add_run(stryd_activity_id=None, name="Apr Run",   date="2026-04-28", user_id=1)
    runs = db.get_runs_for_month(2026, 5, user_id=1)
    assert len(runs) == 2
    assert runs[0]["name"] == "May Run 1"
    assert runs[1]["name"] == "May Run 2"
    # April run must not appear
    assert all(r["date"].startswith("2026-05") for r in runs)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_web.py::TestWorkoutsView::test_get_runs_for_month -v
```

Expected: `FAILED` — `AttributeError: 'RunCoachDB' object has no attribute 'get_runs_for_month'`

- [ ] **Step 3: Implement `get_runs_for_month` in `runcoach/db.py`**

Add after `get_year_month_summary`:

```python
def get_runs_for_month(self, year: int, month: int, user_id: int | None = None) -> list[dict]:
    """Return all runs for a given year/month, most recent first."""
    prefix = f"{year:04d}-{month:02d}-"
    with self._connect() as conn:
        if user_id is not None:
            rows = conn.execute(
                "SELECT * FROM runs WHERE date LIKE ? AND user_id = ? ORDER BY date DESC, id DESC",
                (prefix + "%", user_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM runs WHERE date LIKE ? ORDER BY date DESC, id DESC",
                (prefix + "%",),
            ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_web.py::TestWorkoutsView::test_get_runs_for_month -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add runcoach/db.py tests/test_web.py
git commit -m "feat: add get_runs_for_month DB method"
```

---

### Task 3: Add `polyline_to_svg_path` utility

**Files:**
- Modify: `runcoach/strava.py` (after `decode_polyline`, ~line 315)
- Test: `tests/test_web.py` (new `TestPolylineSvg` class) or `tests/test_sync.py`

- [ ] **Step 1: Write the failing test**

Add a new test class to `tests/test_web.py`:

```python
class TestPolylineSvg:
    def test_polyline_to_svg_path_basic(self):
        from runcoach.strava import polyline_to_svg_path
        coords = [[53.3, -6.2], [53.31, -6.21], [53.32, -6.19]]
        result = polyline_to_svg_path(coords, size=52)
        assert result.startswith("<polyline points=")
        assert 'stroke="#fc4c02"' in result
        # Should contain at least two x,y pairs
        import re
        pts = re.findall(r"[\d.]+,[\d.]+", result)
        assert len(pts) >= 2

    def test_polyline_to_svg_path_empty(self):
        from runcoach.strava import polyline_to_svg_path
        assert polyline_to_svg_path([], size=52) == ""

    def test_polyline_to_svg_path_fits_within_size(self):
        from runcoach.strava import polyline_to_svg_path
        import re
        coords = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
        result = polyline_to_svg_path(coords, size=52)
        pts = re.findall(r"([\d.]+),([\d.]+)", result)
        for x_str, y_str in pts:
            assert 0.0 <= float(x_str) <= 52.0
            assert 0.0 <= float(y_str) <= 52.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_web.py::TestPolylineSvg -v
```

Expected: `FAILED` — `ImportError: cannot import name 'polyline_to_svg_path'`

- [ ] **Step 3: Implement `polyline_to_svg_path` in `runcoach/strava.py`**

Add after `decode_polyline` (~line 315):

```python
def polyline_to_svg_path(coords: list[list[float]], size: int = 52) -> str:
    """
    Convert a list of [lat, lng] pairs to an SVG <polyline> string scaled to fit
    within a size×size viewBox with 4px padding.
    Returns empty string if coords is empty or has fewer than 2 points.
    """
    if len(coords) < 2:
        return ""
    pad = 4
    inner = size - 2 * pad
    lats = [c[0] for c in coords]
    lngs = [c[1] for c in coords]
    min_lat, max_lat = min(lats), max(lats)
    min_lng, max_lng = min(lngs), max(lngs)
    lat_span = max_lat - min_lat or 1e-9
    lng_span = max_lng - min_lng or 1e-9
    scale = inner / max(lat_span, lng_span)
    points = []
    for lat, lng in coords:
        x = pad + (lng - min_lng) * scale
        y = pad + (max_lat - lat) * scale  # invert y so north is up
        points.append(f"{x:.1f},{y:.1f}")
    pts_str = " ".join(points)
    return (
        f'<polyline points="{pts_str}" fill="none" stroke="#fc4c02" '
        f'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>'
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_web.py::TestPolylineSvg -v
```

Expected: all 3 `PASSED`

- [ ] **Step 5: Commit**

```bash
git add runcoach/strava.py tests/test_web.py
git commit -m "feat: add polyline_to_svg_path utility"
```

---

### Task 4: Rewrite `workouts()` route

**Files:**
- Modify: `runcoach/web/routes.py` (the `workouts()` function, ~lines 213-254)
- Test: `tests/test_web.py` (update `TestWorkoutsView` existing tests)

- [ ] **Step 1: Update existing workouts route tests first (they'll pass before and after)**

In `tests/test_web.py`, replace the existing `TestWorkoutsView` tests:

```python
class TestWorkoutsView:
    def test_workouts_page_loads(self, client):
        response = client.get("/workouts")
        assert response.status_code == 200

    def test_workouts_with_year_month_params(self, client, db):
        db.add_run(stryd_activity_id=None, name="May Run", date="2026-05-01", user_id=1)
        response = client.get("/workouts?year=2026&month=5")
        assert response.status_code == 200
        assert b"May Run" in response.data

    def test_workouts_with_no_runs(self, client):
        response = client.get("/workouts")
        assert response.status_code == 200

    def test_workouts_no_planned_workouts_in_context(self, client):
        response = client.get("/workouts")
        assert response.status_code == 200
        # Old template vars must not be present — template should render without them
        assert b"Upcoming Planned" not in response.data
        assert b"Past Planned" not in response.data

    # Keep these DB-level tests from Task 1 and 2 here
    def test_get_year_month_summary(self, db): ...  # already added in Task 1
    def test_get_runs_for_month(self, db): ...       # already added in Task 2
```

- [ ] **Step 2: Run existing tests to confirm they still pass before route change**

```bash
pytest tests/test_web.py::TestWorkoutsView -v
```

Expected: The `test_workouts_page_loads` and `test_workouts_with_no_runs` pass; `test_workouts_with_year_month_params` and `test_workouts_no_planned_workouts_in_context` may fail — that's fine, they target the new behaviour.

- [ ] **Step 3: Rewrite `workouts()` in `runcoach/web/routes.py`**

Replace the entire `workouts()` function (from `@bp.route("/workouts")` through the `return render_template(...)` call) with:

```python
@bp.route("/workouts")
@_login_required
def workouts():
    db = _db()
    user_id = _current_user_id()
    from datetime import date as _date
    from runcoach.strava import decode_polyline, polyline_to_svg_path

    today = _date.today()
    year = request.args.get("year", today.year, type=int)
    month = request.args.get("month", today.month, type=int)

    # Build year/month navigation summary
    year_month_summary = db.get_year_month_summary(user_id=user_id)

    # If no data yet, summary is empty — default to current year/month
    if year_month_summary:
        # Snap to most recent month if the requested year/month has no runs
        valid = {(r["year"], r["month"]) for r in year_month_summary}
        if (year, month) not in valid:
            year = year_month_summary[0]["year"]
            month = year_month_summary[0]["month"]

    # Group summary into {year: [month_dicts]} for template pill rendering
    from collections import defaultdict
    years_map: dict[int, list[dict]] = defaultdict(list)
    for row in year_month_summary:
        years_map[row["year"]].append({"month": row["month"], "count": row["count"]})
    years_nav = [
        {"year": y, "months": years_map[y]}
        for y in sorted(years_map.keys(), reverse=True)
    ]

    # Fetch runs for selected month and attach SVG thumbnails
    runs = db.get_runs_for_month(year, month, user_id=user_id)
    for run in runs:
        polyline = run.get("strava_map_polyline") or ""
        if polyline:
            coords = decode_polyline(polyline)
            run["route_svg"] = polyline_to_svg_path(coords, size=52)
        else:
            run["route_svg"] = ""

    return render_template(
        "workouts.html",
        runs=runs,
        years_nav=years_nav,
        selected_year=year,
        selected_month=month,
        stats=db.get_sync_stats(user_id=user_id),
        syncing=_scheduler().is_syncing,
    )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_web.py::TestWorkoutsView -v
```

Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add runcoach/web/routes.py tests/test_web.py
git commit -m "refactor: rewrite workouts route — activities only, year/month nav"
```

---

### Task 5: Rewrite `workouts.html` template

**Files:**
- Rewrite: `runcoach/web/templates/workouts.html`

- [ ] **Step 1: Replace the template entirely**

Write `runcoach/web/templates/workouts.html` with:

```html
{% extends "base.html" %}
{% block title %}RunCoach - All Activities{% endblock %}

{% block content %}
<div class="card">
  <h2 style="margin-bottom: 1rem;">All Activities</h2>

  {# ── Year pills ── #}
  {% if years_nav %}
  <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:0.6rem;">
    {% for y in years_nav %}
    <a href="{{ url_for('main.workouts', year=y.year, month=y.months[0].month) }}"
       style="text-decoration:none;">
      <span style="display:inline-block;padding:3px 13px;border-radius:20px;font-size:0.78rem;font-weight:{% if y.year == selected_year %}700{% else %}400{% endif %};
                   background:{% if y.year == selected_year %}var(--accent){% else %}var(--surface){% endif %};
                   color:{% if y.year == selected_year %}#fff{% else %}var(--fg-muted){% endif %};
                   cursor:pointer;">{{ y.year }}</span>
    </a>
    {% endfor %}
  </div>

  {# ── Month pills for selected year ── #}
  {% for y in years_nav %}{% if y.year == selected_year %}
  <div style="display:flex;gap:5px;flex-wrap:wrap;margin-bottom:1rem;">
    {% set month_names = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'] %}
    {% set month_counts = {} %}
    {% for m in y.months %}{% set _ = month_counts.update({m.month: m.count}) %}{% endfor %}
    {% for mn in range(1, 13) %}
    {% set cnt = month_counts.get(mn, 0) %}
    {% if cnt > 0 %}
    <a href="{{ url_for('main.workouts', year=selected_year, month=mn) }}"
       style="text-decoration:none;">
      <span style="display:inline-block;padding:2px 10px;border-radius:20px;font-size:0.72rem;
                   background:{% if mn == selected_month %}var(--accent){% else %}var(--surface){% endif %};
                   color:{% if mn == selected_month %}#fff{% else %}var(--fg-muted){% endif %};
                   font-weight:{% if mn == selected_month %}600{% else %}400{% endif %};">
        {{ month_names[mn - 1] }} <span style="opacity:0.75;">{{ cnt }}</span>
      </span>
    </a>
    {% else %}
    <span style="display:inline-block;padding:2px 10px;border-radius:20px;font-size:0.72rem;
                 background:var(--surface);color:var(--fg-muted);opacity:0.4;cursor:default;">
      {{ month_names[mn - 1] }}
    </span>
    {% endif %}
    {% endfor %}
  </div>
  {% endif %}{% endfor %}
  {% endif %}

  {# ── Run count heading ── #}
  {% set month_names = ['January','February','March','April','May','June','July','August','September','October','November','December'] %}
  <div style="font-size:0.7rem;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;
              color:var(--fg-muted);margin-bottom:0.75rem;">
    {{ month_names[selected_month - 1] }} {{ selected_year }}
    &middot; {{ runs|length }} run{{ 's' if runs|length != 1 }}
  </div>

  {# ── Run cards ── #}
  {% if runs %}
  <div style="display:flex;flex-direction:column;gap:7px;">
    {% for run in runs %}
    <a href="{{ url_for('main.run_detail', run_id=run.id) }}"
       style="text-decoration:none;color:inherit;display:flex;align-items:center;gap:10px;
              background:var(--card-bg,#fff);border:1px solid var(--border);border-radius:8px;
              padding:10px 12px;transition:box-shadow 0.15s;">

      {# Route thumbnail #}
      <div style="flex-shrink:0;width:52px;height:52px;background:var(--surface);border-radius:6px;
                  border:{% if run.route_svg %}1px solid var(--border){% else %}1px dashed var(--border){% endif %};
                  overflow:hidden;display:flex;align-items:center;justify-content:center;">
        {% if run.route_svg %}
        <svg viewBox="0 0 52 52" width="52" height="52" style="display:block;">
          {{ run.route_svg | safe }}
        </svg>
        {% endif %}
      </div>

      {# Run info #}
      <div style="flex:1;min-width:0;">
        <div style="font-weight:600;font-size:0.85rem;margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
          {{ run.workout_name or run.name }}
          {% if run.is_manual_upload %}
            <span class="badge badge-blue" style="margin-left:4px;">Manual</span>
          {% endif %}
        </div>
        <div style="font-size:0.72rem;color:var(--fg-muted);">
          {{ run.date }}
          {% if run.distance_m %}&nbsp;·&nbsp;{{ "%.1f"|format(run.distance_m / 1000) }} km{% endif %}
          {% if run.moving_time_s %}
            {% set total_min = run.moving_time_s | int // 60 %}
            {% set hrs = total_min // 60 %}
            {% set mins = total_min % 60 %}
            &nbsp;·&nbsp;{% if hrs > 0 %}{{ hrs }}h {{ "%02d"|format(mins) }}m{% else %}{{ mins }} min{% endif %}
          {% endif %}
          {% if run.avg_power_w %}&nbsp;·&nbsp;{{ run.avg_power_w | int }} W{% endif %}
          {% if run.avg_hr %}&nbsp;·&nbsp;{{ run.avg_hr | int }} bpm{% endif %}
        </div>
      </div>

      {# Status badge #}
      {% if run.stage == 'analyzed' %}
        <span class="badge badge-green" style="flex-shrink:0;">Analyzed</span>
      {% elif run.stage == 'parsed' %}
        <span class="badge badge-blue" style="flex-shrink:0;">Parsed</span>
      {% elif run.stage == 'synced' %}
        <span class="badge badge-yellow" style="flex-shrink:0;">Synced</span>
      {% elif run.stage == 'error' %}
        <span class="badge badge-red" title="{{ run.error_message }}" style="flex-shrink:0;">Error</span>
      {% endif %}

    </a>
    {% endfor %}
  </div>
  {% else %}
  <p style="color:var(--fg-muted);font-size:0.85rem;">No runs recorded for {{ month_names[selected_month - 1] }} {{ selected_year }}.</p>
  {% endif %}

</div>
{% endblock %}
```

- [ ] **Step 2: Run all web tests**

```bash
pytest tests/test_web.py -v
```

Expected: all pass

- [ ] **Step 3: Start dev server and verify manually**

```bash
python -m runcoach.web
```

Open http://localhost:5001/workouts — check:
- Year pills render, selected year is highlighted
- Month pills render with run counts, selected month is highlighted
- Empty months are greyed and not clickable
- Run cards show name, date line, status badge
- Cards with a Strava polyline show the SVG thumbnail
- Cards without a polyline show a plain dashed box
- Clicking a card navigates to run detail
- No planned workouts visible anywhere

- [ ] **Step 4: Run full test suite**

```bash
pytest -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add runcoach/web/templates/workouts.html
git commit -m "feat: rewrite workouts page — activity cards with year/month nav and route thumbnails"
```

---

### Task 6: Fix the `month_counts` Jinja dict update pattern

The Jinja2 `{% set _ = month_counts.update(...) %}` trick works but is fragile. This task replaces it with a cleaner approach by pre-building the month count map in the route.

**Files:**
- Modify: `runcoach/web/routes.py` (workouts function)
- Modify: `runcoach/web/templates/workouts.html` (month pills section)

- [ ] **Step 1: Add `months_in_year` to the route context**

In `runcoach/web/routes.py`, inside the `workouts()` function, add this after building `years_nav`:

```python
# Build month count lookup for selected year
months_in_year: dict[int, int] = {}
for row in year_month_summary:
    if row["year"] == year:
        months_in_year[row["month"]] = row["count"]
```

Add `months_in_year=months_in_year` to the `render_template(...)` call.

- [ ] **Step 2: Simplify month pills in template**

Replace the month pills `{% for y in years_nav %}{% if y.year == selected_year %}...{% endif %}{% endfor %}` block with:

```html
{# ── Month pills for selected year ── #}
{% if months_in_year %}
<div style="display:flex;gap:5px;flex-wrap:wrap;margin-bottom:1rem;">
  {% set month_names_short = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'] %}
  {% for mn in range(1, 13) %}
  {% set cnt = months_in_year.get(mn, 0) %}
  {% if cnt > 0 %}
  <a href="{{ url_for('main.workouts', year=selected_year, month=mn) }}"
     style="text-decoration:none;">
    <span style="display:inline-block;padding:2px 10px;border-radius:20px;font-size:0.72rem;
                 background:{% if mn == selected_month %}var(--accent){% else %}var(--surface){% endif %};
                 color:{% if mn == selected_month %}#fff{% else %}var(--fg-muted){% endif %};
                 font-weight:{% if mn == selected_month %}600{% else %}400{% endif %};">
      {{ month_names_short[mn - 1] }} <span style="opacity:0.75;">{{ cnt }}</span>
    </span>
  </a>
  {% else %}
  <span style="display:inline-block;padding:2px 10px;border-radius:20px;font-size:0.72rem;
               background:var(--surface);color:var(--fg-muted);opacity:0.4;">
    {{ month_names_short[mn - 1] }}
  </span>
  {% endif %}
  {% endfor %}
</div>
{% endif %}
```

Also remove the first `month_names` / `month_counts` set blocks inside the year pills loop since they are no longer needed.

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_web.py -v
```

Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add runcoach/web/routes.py runcoach/web/templates/workouts.html
git commit -m "refactor: pass months_in_year from route to avoid Jinja dict.update trick"
```

---

### Task 7: Push and deploy

- [ ] **Step 1: Run full test suite**

```bash
pytest -v
```

Expected: all pass

- [ ] **Step 2: Push**

```bash
git push
```

- [ ] **Step 3: Watch CI and deploy when green**

```bash
gh run list --limit 3
# wait for latest run to show "completed success"
cd /srv/runcoach && docker compose pull && docker compose up -d
```
