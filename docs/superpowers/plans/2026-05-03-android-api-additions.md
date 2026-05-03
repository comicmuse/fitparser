# Android API Additions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four small backend API changes needed by the Android app: a `/dashboard` endpoint, Strava/Stryd IDs in run responses, year/month filtering on `/runs`, and `strava_athlete_id` in the athlete profile response.

**Architecture:** All changes are in `runcoach/web/api.py` and `runcoach/db.py`. No schema migrations needed — all required columns already exist. Tests go in the existing `tests/test_api.py`.

**Tech Stack:** Python 3.11+, Flask, SQLite, pytest. Always activate `.venv` before running commands: `source .venv/bin/activate`.

---

## File Map

- **Modify:** `runcoach/web/api.py` — add `/dashboard` endpoint, extend `format_run_for_api`, extend `list_runs`, extend `get_athlete_profile`
- **Modify:** `runcoach/db.py` — add `get_runs_paginated_filtered` method
- **Modify:** `tests/test_api.py` — add tests for all four changes

---

### Task 1: Add Strava/Stryd IDs to run response

**Files:**
- Modify: `runcoach/web/api.py:51-92`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api.py` inside `class TestRuns`:

```python
def test_run_response_includes_strava_stryd_ids(self, client, auth_headers, app):
    db = app.config["db"]
    user_id = db.get_default_user_id()
    db.insert_run(
        stryd_activity_id=None,
        name="Test Run",
        date="2026-04-01T06:00:00",
        fit_path="",
        user_id=user_id,
    )
    with db._connect() as conn:
        run = conn.execute("SELECT id FROM runs WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()
        conn.execute(
            "UPDATE runs SET strava_activity_id = ?, stryd_activity_id = ? WHERE id = ?",
            ("strava123", "9876543", run["id"]),
        )
        run_id = run["id"]

    resp = client.get(f"/api/v1/runs/{run_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["strava_activity_id"] == "strava123"
    assert data["stryd_activity_id"] == 9876543 or data["stryd_activity_id"] == "9876543"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
source .venv/bin/activate
pytest tests/test_api.py::TestRuns::test_run_response_includes_strava_stryd_ids -v
```

Expected: FAIL — `KeyError: 'strava_activity_id'` or assertion error

- [ ] **Step 3: Add fields to `format_run_for_api`**

In `runcoach/web/api.py`, in the `format_run_for_api` function, add to the `result` dict (after `"error_message"`):

```python
        "strava_activity_id": run.get("strava_activity_id"),
        "stryd_activity_id": run.get("stryd_activity_id"),
        "strava_map_polyline": run.get("strava_map_polyline"),
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_api.py::TestRuns::test_run_response_includes_strava_stryd_ids -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add runcoach/web/api.py tests/test_api.py
git commit -m "feat: add strava_activity_id and stryd_activity_id to run API response"
```

---

### Task 2: Add year/month filtering to `/runs`

**Files:**
- Modify: `runcoach/db.py:832-855`
- Modify: `runcoach/web/api.py:180-226`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_api.py` inside `class TestRuns`:

```python
def test_list_runs_filter_by_year(self, client, auth_headers, app):
    db = app.config["db"]
    user_id = db.get_default_user_id()
    db.insert_run(stryd_activity_id=None, name="Run April", date="2026-04-15T06:00:00", fit_path="", user_id=user_id)
    db.insert_run(stryd_activity_id=None, name="Run March", date="2026-03-10T06:00:00", fit_path="", user_id=user_id)
    db.insert_run(stryd_activity_id=None, name="Run 2025", date="2025-11-01T06:00:00", fit_path="", user_id=user_id)

    resp = client.get("/api/v1/runs?year=2026", headers=auth_headers)
    assert resp.status_code == 200
    names = [r["name"] for r in resp.get_json()["runs"]]
    assert "Run April" in names
    assert "Run March" in names
    assert "Run 2025" not in names

def test_list_runs_filter_by_year_and_month(self, client, auth_headers, app):
    db = app.config["db"]
    user_id = db.get_default_user_id()
    db.insert_run(stryd_activity_id=None, name="Run April", date="2026-04-15T06:00:00", fit_path="", user_id=user_id)
    db.insert_run(stryd_activity_id=None, name="Run March", date="2026-03-10T06:00:00", fit_path="", user_id=user_id)

    resp = client.get("/api/v1/runs?year=2026&month=4", headers=auth_headers)
    assert resp.status_code == 200
    names = [r["name"] for r in resp.get_json()["runs"]]
    assert "Run April" in names
    assert "Run March" not in names
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_api.py::TestRuns::test_list_runs_filter_by_year tests/test_api.py::TestRuns::test_list_runs_filter_by_year_and_month -v
```

Expected: FAIL — filters not applied, wrong results returned

- [ ] **Step 3: Add `get_runs_paginated_filtered` to `db.py`**

In `runcoach/db.py`, add this method after `get_runs_paginated` (around line 848):

```python
def get_runs_paginated_filtered(
    self,
    limit: int = 10,
    offset: int = 0,
    user_id: int | None = None,
    year: int | None = None,
    month: int | None = None,
) -> list[dict]:
    """Get runs with optional year/month filter, most recent first."""
    conditions = []
    params: list = []

    if user_id is not None:
        conditions.append("user_id = ?")
        params.append(user_id)
    if year is not None:
        conditions.append("strftime('%Y', date) = ?")
        params.append(str(year))
    if month is not None:
        conditions.append("strftime('%m', date) = ?")
        params.append(f"{month:02d}")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.extend([limit, offset])

    with self._connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM runs {where} ORDER BY date DESC, id DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
    return [dict(r) for r in rows]

def count_runs_filtered(
    self,
    user_id: int | None = None,
    year: int | None = None,
    month: int | None = None,
) -> int:
    """Count runs with optional year/month filter."""
    conditions = []
    params: list = []

    if user_id is not None:
        conditions.append("user_id = ?")
        params.append(user_id)
    if year is not None:
        conditions.append("strftime('%Y', date) = ?")
        params.append(str(year))
    if month is not None:
        conditions.append("strftime('%m', date) = ?")
        params.append(f"{month:02d}")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with self._connect() as conn:
        return conn.execute(
            f"SELECT COUNT(*) FROM runs {where}",
            params,
        ).fetchone()[0]
```

- [ ] **Step 4: Update `list_runs` in `api.py` to use filtered methods**

Replace the `list_runs` function body in `runcoach/web/api.py` (the section after parameter validation, around lines 198-226):

```python
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)

    if page < 1:
        page = 1
    if per_page < 1 or per_page > 100:
        per_page = 20

    db = get_db()
    user_id = request.user_id

    total = db.count_runs_filtered(user_id=user_id, year=year, month=month)
    total_pages = (total + per_page - 1) // per_page
    offset = (page - 1) * per_page
    runs = db.get_runs_paginated_filtered(limit=per_page, offset=offset, user_id=user_id, year=year, month=month)

    return jsonify({
        "runs": [format_run_for_api(run) for run in runs],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        }
    }), 200
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_api.py::TestRuns::test_list_runs_filter_by_year tests/test_api.py::TestRuns::test_list_runs_filter_by_year_and_month -v
```

Expected: PASS

- [ ] **Step 6: Run full test suite to check for regressions**

```bash
pytest tests/test_api.py -v
```

Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add runcoach/web/api.py runcoach/db.py tests/test_api.py
git commit -m "feat: add year/month filtering to /api/v1/runs endpoint"
```

---

### Task 3: Add `strava_athlete_id` to athlete profile response

**Files:**
- Modify: `runcoach/web/api.py:513-531`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api.py` inside `class TestAthleteProfile`:

```python
def test_profile_includes_strava_athlete_id(self, client, auth_headers, app):
    db = app.config["db"]
    user_id = db.get_default_user_id()
    with db._connect() as conn:
        conn.execute(
            "UPDATE users SET strava_athlete_id = ? WHERE id = ?",
            ("athlete_456", user_id),
        )

    resp = client.get("/api/v1/athlete/profile", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert "strava_athlete_id" in data
    assert data["strava_athlete_id"] == "athlete_456"

def test_profile_strava_athlete_id_null_when_not_connected(self, client, auth_headers):
    resp = client.get("/api/v1/athlete/profile", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert "strava_athlete_id" in data
    assert data["strava_athlete_id"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_api.py::TestAthleteProfile::test_profile_includes_strava_athlete_id tests/test_api.py::TestAthleteProfile::test_profile_strava_athlete_id_null_when_not_connected -v
```

Expected: FAIL — `strava_athlete_id` not in response

- [ ] **Step 3: Update `get_athlete_profile` in `api.py`**

In `runcoach/web/api.py`, update the `get_athlete_profile` function's return statement:

```python
    return jsonify({
        "profile": profile,
        "display_name": user["display_name"] if user and user["display_name"] else "",
        "username": user["username"] if user else "",
        "strava_athlete_id": user.get("strava_athlete_id") if user else None,
    }), 200
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_api.py::TestAthleteProfile::test_profile_includes_strava_athlete_id tests/test_api.py::TestAthleteProfile::test_profile_strava_athlete_id_null_when_not_connected -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add runcoach/web/api.py tests/test_api.py
git commit -m "feat: include strava_athlete_id in athlete profile API response"
```

---

### Task 4: Add `/api/v1/dashboard` endpoint

**Files:**
- Modify: `runcoach/web/api.py` — add new endpoint at end of file
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write the failing tests**

Add a new test class to `tests/test_api.py`:

```python
class TestDashboard:
    def test_dashboard_requires_auth(self, client):
        resp = client.get("/api/v1/dashboard")
        assert resp.status_code == 401

    def test_dashboard_returns_structure(self, client, auth_headers):
        resp = client.get("/api/v1/dashboard")
        assert resp.status_code == 401  # without auth

        resp = client.get("/api/v1/dashboard", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "latest_run" in data
        assert "next_workout" in data
        assert "training_summary" in data

    def test_dashboard_latest_run_is_most_recent(self, client, auth_headers, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        db.insert_run(stryd_activity_id=None, name="Older Run", date="2026-04-01T06:00:00", fit_path="", user_id=user_id)
        db.insert_run(stryd_activity_id=None, name="Newer Run", date="2026-04-15T06:00:00", fit_path="", user_id=user_id)

        resp = client.get("/api/v1/dashboard", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["latest_run"]["name"] == "Newer Run"

    def test_dashboard_no_runs_returns_null_latest(self, client, auth_headers):
        resp = client.get("/api/v1/dashboard", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["latest_run"] is None

    def test_dashboard_training_summary_shape(self, client, auth_headers):
        resp = client.get("/api/v1/dashboard", headers=auth_headers)
        assert resp.status_code == 200
        ts = resp.get_json()["training_summary"]
        assert "current_rsb" in ts
        assert "rsb_history" in ts
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_api.py::TestDashboard -v
```

Expected: FAIL — 404 (endpoint not defined)

- [ ] **Step 3: Add the dashboard endpoint to `api.py`**

Add the following import at the top of `runcoach/web/api.py` (with other imports):

```python
from datetime import date as date_type
from runcoach.context import build_training_summary
```

Then add the endpoint at the end of `runcoach/web/api.py`:

```python
@api_bp.route("/dashboard", methods=["GET"])
@require_auth
def dashboard():
    """
    Return home screen data: latest run, next planned workout, training summary.

    GET /api/v1/dashboard
    Headers: Authorization: Bearer <access_token>
    Response: {
        "latest_run": {...} | null,
        "next_workout": {"date": "...", "name": "...", "description": "..."} | null,
        "training_summary": {
            "current_rsb": {"rsb": float, "ctl": float, "atl": float, "interpretation": str},
            "rsb_history": [{"date": str, "rsb": float, "ctl": float, "atl": float}, ...]
        }
    }
    """
    db = get_db()
    user_id = request.user_id

    # Latest run
    runs = db.get_runs_paginated_filtered(limit=1, offset=0, user_id=user_id)
    latest_run = format_run_for_api(runs[0]) if runs else None

    # Next planned workout (first upcoming from today)
    today = date_type.today().isoformat()
    upcoming = db.get_upcoming_planned_workouts(from_date=today, limit=1, user_id=user_id)
    next_workout = None
    if upcoming:
        w = upcoming[0]
        next_workout = {
            "date": w["date"],
            "name": w["title"],
            "description": w.get("description") or "",
        }

    # Training summary (RSB/CTL/ATL + 30-day history)
    summary_data = build_training_summary(db, user_id=user_id)
    ts = summary_data.get("training_summary", {})
    current_rsb_raw = ts.get("current_rsb", {})
    training_summary = {
        "current_rsb": {
            "rsb": current_rsb_raw.get("rsb"),
            "ctl": current_rsb_raw.get("ctl"),
            "atl": current_rsb_raw.get("atl"),
            "interpretation": current_rsb_raw.get("interpretation", "unknown"),
        },
        "rsb_history": [
            {
                "date": h["date"],
                "rsb": h.get("rsb"),
                "ctl": h.get("ctl"),
                "atl": h.get("atl"),
            }
            for h in ts.get("rsb_history", [])
        ],
    }

    return jsonify({
        "latest_run": latest_run,
        "next_workout": next_workout,
        "training_summary": training_summary,
    }), 200
```

- [ ] **Step 4: Check what `build_training_summary` actually returns**

The function is in `runcoach/context.py:318`. Its return value wraps everything under a `"training_summary"` key. Verify by running a quick check:

```bash
source .venv/bin/activate
python -c "
from runcoach.db import RunCoachDB
from runcoach.context import build_training_summary
import tempfile, pathlib
with tempfile.TemporaryDirectory() as d:
    db = RunCoachDB(pathlib.Path(d) / 'test.db')
    result = build_training_summary(db)
    print(list(result.keys()))
    print(list(result.get('training_summary', {}).keys()))
"
```

Expected output shows keys include `current_rsb` and `rsb_history` nested under `training_summary`. If the structure differs, adjust the endpoint code accordingly.

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_api.py::TestDashboard -v
```

Expected: PASS

- [ ] **Step 6: Run full test suite**

```bash
pytest tests/test_api.py -v
```

Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add runcoach/web/api.py tests/test_api.py
git commit -m "feat: add /api/v1/dashboard endpoint for mobile home screen"
```

---

### Task 5: Final verification

- [ ] **Step 1: Run complete test suite**

```bash
source .venv/bin/activate
pytest -v
```

Expected: all tests pass, no regressions

- [ ] **Step 2: Verify API changes work end-to-end with a running server**

```bash
source .venv/bin/activate
python -m runcoach.web &
sleep 2

# Login and get token
TOKEN=$(curl -s -X POST http://localhost:5000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"athlete","password":"changeme"}' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Test dashboard
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/v1/dashboard | python -m json.tool | head -30

# Test year/month filter
curl -s -H "Authorization: Bearer $TOKEN" "http://localhost:5000/api/v1/runs?year=2026&month=4" | python -m json.tool | head -20

kill %1
```

Expected: valid JSON responses with correct structure

- [ ] **Step 3: Commit if any fixes were needed, otherwise done**

```bash
git log --oneline -5
```
