# Strava Route Suggestions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Route tab in WorkoutDetailScreen to show Strava saved routes and previously-run routes (from activity history) alongside ORS-generated suggestions, filtered by proximity to the user's current location and target distance.

**Architecture:** Two new route sources are added to the existing `POST /api/v1/route-suggestion` endpoint. Strava saved routes are fetched via a new `StravaClient.list_routes()` method and cached in a new `strava_routes` DB table (populated at Strava OAuth + pipeline sync time). Previously-run routes come from the existing `runs.strava_map_polyline` column; both sources are filtered using a haversine proximity check (≤500m start, ±1km distance). All routes receive a `source` field ("ors" | "strava" | "previous"); the Flutter UI shows a badge chip for non-ORS routes.

**Tech Stack:** Python/Flask, SQLite (WAL mode), Dart/Flutter, Riverpod, flutter_map

---

## File Map

| File | Change |
|------|--------|
| `runcoach/db.py` | Add `strava_routes` table to SCHEMA_SQL + 3 new DB methods |
| `runcoach/strava.py` | Add `StravaClient.list_routes()` + `sync_strava_routes()` function |
| `runcoach/web/ors.py` | Add `haversine_m()`, `filter_routes_by_proximity()`, `deduplicate_routes()` |
| `runcoach/web/api.py` | Extend `api_route_suggestion()` to merge all three sources |
| `runcoach/web/routes.py` | Call `sync_strava_routes()` in Strava OAuth callback |
| `runcoach/pipeline.py` | Call `sync_strava_routes()` after `link_unlinked_runs()` |
| `tests/test_db.py` | Tests for new DB methods |
| `tests/test_ors.py` | New file: haversine + filter + dedup tests |
| `tests/test_api.py` | Update/extend route suggestion tests |
| `mobile/lib/screens/workout_detail_screen.dart` | Add source badge in `_RouteTab` |
| `mobile/test/screens/workout_detail_screen_test.dart` | Tests for badge display |

---

## Task 1: DB — `strava_routes` table + methods

**Files:**
- Modify: `runcoach/db.py` (SCHEMA_SQL constant + new methods)
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write failing tests**

Add a new test class to `tests/test_db.py`:

```python
class TestStravaRoutes:
    def test_upsert_and_get_strava_routes(self, db):
        routes = [
            {
                "strava_route_id": "111",
                "name": "Morning Loop",
                "distance_m": 8000.0,
                "start_lat": 51.50,
                "start_lng": -0.12,
                "polyline": "abc123",
            },
            {
                "strava_route_id": "222",
                "name": "Evening 5k",
                "distance_m": 5000.0,
                "start_lat": 51.51,
                "start_lng": -0.13,
                "polyline": "def456",
            },
        ]
        db.upsert_strava_routes(user_id=1, routes=routes)
        result = db.get_strava_routes(user_id=1)
        assert len(result) == 2
        names = {r["name"] for r in result}
        assert names == {"Morning Loop", "Evening 5k"}

    def test_upsert_updates_existing_route(self, db):
        db.upsert_strava_routes(user_id=1, routes=[{
            "strava_route_id": "333",
            "name": "Old Name",
            "distance_m": 10000.0,
            "start_lat": 51.5,
            "start_lng": -0.1,
            "polyline": "old_polyline",
        }])
        db.upsert_strava_routes(user_id=1, routes=[{
            "strava_route_id": "333",
            "name": "New Name",
            "distance_m": 10100.0,
            "start_lat": 51.5,
            "start_lng": -0.1,
            "polyline": "new_polyline",
        }])
        result = db.get_strava_routes(user_id=1)
        assert len(result) == 1
        assert result[0]["name"] == "New Name"
        assert result[0]["polyline"] == "new_polyline"

    def test_get_strava_routes_empty(self, db):
        result = db.get_strava_routes(user_id=1)
        assert result == []

    def test_get_runs_with_polylines(self, db):
        # Insert two runs: one with a polyline, one without
        with db._connect() as conn:
            conn.execute(
                """INSERT INTO runs (name, date, fit_path, stage, synced_at,
                   distance_m, strava_map_polyline, user_id)
                   VALUES ('Run A', '2026-01-01', 'a.fit', 'analyzed',
                   datetime('now'), 5000, 'poly1', 1)"""
            )
            conn.execute(
                """INSERT INTO runs (name, date, fit_path, stage, synced_at,
                   distance_m, user_id)
                   VALUES ('Run B', '2026-01-02', 'b.fit', 'analyzed',
                   datetime('now'), 6000, 1)"""
            )
        result = db.get_runs_with_polylines(user_id=1, limit=50)
        assert len(result) == 1
        assert result[0]["name"] == "Run A"
        assert result[0]["strava_map_polyline"] == "poly1"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_db.py::TestStravaRoutes -v
```

Expected: `AttributeError: 'RunCoachDB' object has no attribute 'upsert_strava_routes'`

- [ ] **Step 3: Add `strava_routes` table to SCHEMA_SQL in `runcoach/db.py`**

Add this block to `SCHEMA_SQL` (after the `device_tokens` block, before the closing `"""`):

```sql
CREATE TABLE IF NOT EXISTS strava_routes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    strava_route_id TEXT NOT NULL,
    name TEXT,
    distance_m REAL,
    start_lat REAL,
    start_lng REAL,
    polyline TEXT,
    cached_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE (user_id, strava_route_id)
);

CREATE INDEX IF NOT EXISTS idx_strava_routes_user ON strava_routes(user_id);
```

- [ ] **Step 4: Add the three new DB methods to `RunCoachDB`**

Add after `get_device_tokens_for_user` at the end of the class:

```python
# ------ strava_routes ------

def upsert_strava_routes(self, user_id: int, routes: list[dict]) -> None:
    """Cache Strava saved routes for a user. Each dict must have strava_route_id,
    name, distance_m, start_lat, start_lng, polyline. Upserts on (user_id, strava_route_id)."""
    now = _now_iso()
    with self._connect() as conn:
        for r in routes:
            conn.execute(
                """INSERT INTO strava_routes
                   (user_id, strava_route_id, name, distance_m, start_lat, start_lng, polyline, cached_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(user_id, strava_route_id) DO UPDATE SET
                     name = excluded.name,
                     distance_m = excluded.distance_m,
                     start_lat = excluded.start_lat,
                     start_lng = excluded.start_lng,
                     polyline = excluded.polyline,
                     cached_at = excluded.cached_at""",
                (user_id, r["strava_route_id"], r.get("name"), r.get("distance_m"),
                 r.get("start_lat"), r.get("start_lng"), r.get("polyline"), now),
            )

def get_strava_routes(self, user_id: int) -> list[dict]:
    """Return all cached Strava saved routes for a user."""
    with self._connect() as conn:
        rows = conn.execute(
            "SELECT * FROM strava_routes WHERE user_id = ? ORDER BY name",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]

def get_runs_with_polylines(self, user_id: int, limit: int = 200) -> list[dict]:
    """Return the most recent runs that have a Strava map polyline, ordered newest first."""
    with self._connect() as conn:
        rows = conn.execute(
            """SELECT id, name, date, distance_m, strava_map_polyline
               FROM runs
               WHERE user_id = ?
                 AND strava_map_polyline IS NOT NULL
                 AND strava_map_polyline != ''
               ORDER BY date DESC, id DESC
               LIMIT ?""",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/test_db.py::TestStravaRoutes -v
```

Expected: 4 tests pass.

- [ ] **Step 6: Run full DB test suite to check for regressions**

```bash
pytest tests/test_db.py -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add runcoach/db.py tests/test_db.py
git commit -m "feat: add strava_routes table and DB methods for route caching"
```

---

## Task 2: `StravaClient.list_routes()` + `sync_strava_routes()`

**Files:**
- Modify: `runcoach/strava.py`
- Modify: `runcoach/web/routes.py` (OAuth callback)
- Modify: `runcoach/pipeline.py`
- Modify: `tests/test_api.py` (new sync test) or `tests/test_strava.py` if it exists

Check whether `tests/test_strava.py` exists; add the test there, otherwise add to `tests/test_api.py`.

- [ ] **Step 1: Write failing tests**

In `tests/test_api.py`, add a new test class:

```python
class TestSyncStravaRoutes:
    def _strava_config(self, app):
        from runcoach.config import Config
        return Config(
            openai_api_key="test-key",
            openai_model="gpt-4o",
            data_dir=app.config["config"].data_dir,
            timezone="Europe/London",
            secret_key="test-secret-key",
            strava_client_id="fake-client-id",
            strava_client_secret="fake-secret",
        )

    def test_sync_stores_routes_in_db(self, app):
        import unittest.mock as mock
        from runcoach.strava import sync_strava_routes

        db = app.config["db"]
        cfg = self._strava_config(app)
        user_id = db.get_default_user_id()

        # Give the test user Strava tokens + athlete ID
        with db._connect() as conn:
            conn.execute(
                """UPDATE users SET strava_access_token = 'tok',
                   strava_refresh_token = 'ref', strava_token_expires_at = 9999999999,
                   strava_athlete_id = '42' WHERE id = ?""",
                (user_id,),
            )

        fake_routes = [
            {
                "id": 1001,
                "name": "Morning Loop",
                "distance": 8500.0,
                "map": {"summary_polyline": "abc123"},
                "starting_latlng": [51.5, -0.1],
            },
            {
                "id": 1002,
                "name": "Evening 5k",
                "distance": 5000.0,
                "map": {"summary_polyline": "def456"},
                "starting_latlng": [51.51, -0.12],
            },
        ]

        with mock.patch(
            "runcoach.strava.StravaClient.list_routes",
            return_value=fake_routes,
        ):
            count = sync_strava_routes(db, user_id, cfg)

        assert count == 2
        stored = db.get_strava_routes(user_id)
        assert len(stored) == 2
        names = {r["name"] for r in stored}
        assert names == {"Morning Loop", "Evening 5k"}

    def test_sync_skips_when_no_strava_tokens(self, app):
        from runcoach.strava import sync_strava_routes

        db = app.config["db"]
        cfg = self._strava_config(app)  # has strava creds, but user has no tokens
        user_id = db.get_default_user_id()

        count = sync_strava_routes(db, user_id, cfg)
        assert count == 0

    def test_sync_skips_when_strava_not_configured(self, app):
        from runcoach.strava import sync_strava_routes
        from runcoach.config import Config

        db = app.config["db"]
        cfg_no_strava = Config(
            openai_api_key="key",
            openai_model="gpt-4o",
            data_dir=app.config["config"].data_dir,
            timezone="Europe/London",
            secret_key="test-secret-key",
            # no strava_client_id — strava not configured
        )
        user_id = db.get_default_user_id()

        count = sync_strava_routes(db, user_id, cfg_no_strava)
        assert count == 0
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_api.py::TestSyncStravaRoutes -v
```

Expected: `ImportError: cannot import name 'sync_strava_routes' from 'runcoach.strava'`

- [ ] **Step 3: Add `list_routes()` to `StravaClient` in `runcoach/strava.py`**

Add after `list_activities()`:

```python
def list_routes(
    self,
    athlete_id: str | int,
    access_token: str,
    per_page: int = 200,
) -> list[dict]:
    """Fetch all saved routes for an athlete.

    Returns list of route dicts from Strava's GET /athletes/{id}/routes API.
    Each dict includes id, name, distance, map.summary_polyline, starting_latlng.
    """
    resp = requests.get(
        f"{STRAVA_API_BASE}/athletes/{int(athlete_id)}/routes",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"per_page": per_page, "page": 1},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()
```

- [ ] **Step 4: Add `sync_strava_routes()` standalone function in `runcoach/strava.py`**

Add after `link_unlinked_runs()`:

```python
def sync_strava_routes(db: RunCoachDB, user_id: int, config) -> int:
    """Fetch and cache Strava saved routes for a user.

    Returns the number of routes upserted (0 if Strava not configured or no token).
    """
    if not config.strava_client_id:
        return 0

    client = StravaClient(config.strava_client_id, config.strava_client_secret)
    access_token = client.get_valid_access_token(db, user_id)
    if not access_token:
        log.debug("Strava: no valid access token for user %d, skipping route sync", user_id)
        return 0

    tokens = db.get_strava_tokens(user_id)
    athlete_id = tokens.get("strava_athlete_id") if tokens else None
    if not athlete_id:
        log.debug("Strava: no athlete_id for user %d, skipping route sync", user_id)
        return 0

    try:
        raw_routes = client.list_routes(athlete_id, access_token)
    except Exception as exc:
        log.warning("Strava route sync failed for user %d: %s", user_id, exc)
        return 0

    routes_to_store = []
    for r in raw_routes:
        strava_id = str(r.get("id", ""))
        if not strava_id:
            continue
        starting = r.get("starting_latlng") or []
        start_lat = float(starting[0]) if len(starting) >= 2 else None
        start_lng = float(starting[1]) if len(starting) >= 2 else None
        routes_to_store.append({
            "strava_route_id": strava_id,
            "name": r.get("name"),
            "distance_m": float(r["distance"]) if r.get("distance") else None,
            "start_lat": start_lat,
            "start_lng": start_lng,
            "polyline": (r.get("map") or {}).get("summary_polyline"),
        })

    if routes_to_store:
        db.upsert_strava_routes(user_id, routes_to_store)
        log.info("Strava: cached %d route(s) for user %d", len(routes_to_store), user_id)

    return len(routes_to_store)
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/test_api.py::TestSyncStravaRoutes -v
```

Expected: 3 tests pass.

- [ ] **Step 6: Call `sync_strava_routes()` in the Strava OAuth callback**

In `runcoach/web/routes.py`, in `strava_callback()`, add after the `flash(...)` line (before `return redirect`):

```python
    # Cache the user's saved Strava routes now that we have a valid token.
    try:
        from runcoach.strava import sync_strava_routes
        sync_strava_routes(db, user_id, config)
    except Exception as exc:
        log.warning("Strava route sync after OAuth failed: %s", exc)
```

- [ ] **Step 7: Call `sync_strava_routes()` in the pipeline**

In `runcoach/pipeline.py`, add after the `link_unlinked_runs` block (after line ~77):

```python
        # 1d. Sync Strava saved routes to local cache
        if config.strava_client_id:
            try:
                from runcoach.strava import sync_strava_routes
                synced_routes = sync_strava_routes(db, user_id, config)
                if synced_routes:
                    log.info("Strava: synced %d route(s) for user %d", synced_routes, user_id)
            except Exception as e:
                log.error("Strava route sync failed for user %d: %s", user_id, e)
```

- [ ] **Step 8: Commit**

```bash
git add runcoach/strava.py runcoach/web/routes.py runcoach/pipeline.py tests/test_api.py
git commit -m "feat: add StravaClient.list_routes() and sync_strava_routes() with pipeline + OAuth triggers"
```

---

## Task 3: Route filtering helpers in `runcoach/web/ors.py`

**Files:**
- Modify: `runcoach/web/ors.py`
- Create: `tests/test_ors.py`

- [ ] **Step 1: Write failing tests in `tests/test_ors.py`**

```python
"""Tests for runcoach.web.ors helper functions."""
from __future__ import annotations
import pytest
from runcoach.web.ors import haversine_m, filter_routes_by_proximity, deduplicate_routes


class TestHaversine:
    def test_same_point_is_zero(self):
        assert haversine_m(51.5, -0.1, 51.5, -0.1) == pytest.approx(0.0, abs=0.1)

    def test_known_distance(self):
        # London (51.5074, -0.1278) to Paris (48.8566, 2.3522) ≈ 340 km
        d = haversine_m(51.5074, -0.1278, 48.8566, 2.3522)
        assert 330_000 < d < 350_000

    def test_short_distance(self):
        # ~111m north (1 arc-second latitude ≈ 30.8m, so 0.001° ≈ 111m)
        d = haversine_m(51.5, -0.1, 51.501, -0.1)
        assert 100 < d < 120


class TestFilterRoutesByProximity:
    def _route(self, start_lat, start_lng, distance_m, **extra):
        # A minimal route dict with just two coords (start + end)
        return {
            "coords": [[start_lat, start_lng], [start_lat + 0.001, start_lng + 0.001]],
            "distance_m": distance_m,
            **extra,
        }

    def test_includes_nearby_matching_distance(self):
        route = self._route(51.5001, -0.1001, 5000)
        result = filter_routes_by_proximity([route], 51.5, -0.1, 5000)
        assert len(result) == 1

    def test_excludes_route_too_far_away(self):
        route = self._route(51.51, -0.1, 5000)  # ~1.1 km from user
        result = filter_routes_by_proximity([route], 51.5, -0.1, 5000)
        assert len(result) == 0

    def test_excludes_route_wrong_distance(self):
        route = self._route(51.5001, -0.1001, 10000)  # 10 km, target is 5 km
        result = filter_routes_by_proximity([route], 51.5, -0.1, 5000)
        assert len(result) == 0

    def test_includes_route_at_distance_boundary(self):
        # 999m offset from target distance — should be included (max_dist_offset_m=1000)
        route = self._route(51.5001, -0.1001, 5999)
        result = filter_routes_by_proximity([route], 51.5, -0.1, 5000)
        assert len(result) == 1

    def test_excludes_route_just_over_distance_boundary(self):
        route = self._route(51.5001, -0.1001, 6001)
        result = filter_routes_by_proximity([route], 51.5, -0.1, 5000)
        assert len(result) == 0

    def test_empty_input(self):
        result = filter_routes_by_proximity([], 51.5, -0.1, 5000)
        assert result == []

    def test_route_with_no_coords_is_skipped(self):
        result = filter_routes_by_proximity(
            [{"coords": [], "distance_m": 5000}], 51.5, -0.1, 5000
        )
        assert result == []


class TestDeduplicateRoutes:
    def _route(self, start_lat, start_lng, name):
        return {
            "coords": [[start_lat, start_lng], [start_lat + 0.001, start_lng]],
            "distance_m": 5000,
            "name": name,
        }

    def test_keeps_first_when_two_routes_same_start(self):
        r1 = self._route(51.5, -0.1, "First")
        r2 = self._route(51.5001, -0.1001, "Second")  # ~13m away — same cluster
        result = deduplicate_routes([r1, r2])
        assert len(result) == 1
        assert result[0]["name"] == "First"

    def test_keeps_both_when_starts_far_apart(self):
        r1 = self._route(51.5, -0.1, "Loop A")
        r2 = self._route(51.503, -0.1, "Loop B")  # ~330m away — different cluster
        result = deduplicate_routes([r1, r2])
        assert len(result) == 2

    def test_empty_input(self):
        assert deduplicate_routes([]) == []

    def test_route_with_no_coords_is_preserved(self):
        r = {"coords": [], "distance_m": 5000, "name": "Empty"}
        result = deduplicate_routes([r])
        assert len(result) == 1
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_ors.py -v
```

Expected: `ImportError: cannot import name 'haversine_m' from 'runcoach.web.ors'`

- [ ] **Step 3: Add helpers to `runcoach/web/ors.py`**

Add after the existing imports, before `fetch_routes`:

```python
import math


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return the great-circle distance in metres between two WGS84 lat/lng points."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def filter_routes_by_proximity(
    routes: list[dict],
    user_lat: float,
    user_lng: float,
    target_distance_m: float,
    max_start_m: float = 500,
    max_dist_offset_m: float = 1000,
) -> list[dict]:
    """Return routes whose start point is within max_start_m of (user_lat, user_lng)
    and whose distance is within max_dist_offset_m of target_distance_m."""
    result = []
    for route in routes:
        coords = route.get("coords") or []
        if not coords:
            continue
        start_lat, start_lng = coords[0][0], coords[0][1]
        if haversine_m(user_lat, user_lng, start_lat, start_lng) > max_start_m:
            continue
        route_dist = route.get("distance_m") or 0
        if abs(route_dist - target_distance_m) > max_dist_offset_m:
            continue
        result.append(route)
    return result


def deduplicate_routes(routes: list[dict], min_separation_m: float = 200) -> list[dict]:
    """Remove routes whose start point is within min_separation_m of an already-kept route.
    Preserves the order of the input list (first occurrence wins)."""
    kept: list[dict] = []
    for route in routes:
        coords = route.get("coords") or []
        if not coords:
            kept.append(route)
            continue
        lat, lng = coords[0][0], coords[0][1]
        too_close = any(
            (k_coords := (k.get("coords") or [])) and
            haversine_m(lat, lng, k_coords[0][0], k_coords[0][1]) < min_separation_m
            for k in kept
            if (k.get("coords") or [])
        )
        if not too_close:
            kept.append(route)
    return kept
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_ors.py -v
```

Expected: all 15 tests pass.

- [ ] **Step 5: Commit**

```bash
git add runcoach/web/ors.py tests/test_ors.py
git commit -m "feat: add haversine_m, filter_routes_by_proximity, deduplicate_routes to ors.py"
```

---

## Task 4: Extend `api_route_suggestion` endpoint

**Files:**
- Modify: `runcoach/web/api.py`
- Modify: `tests/test_api.py`

The endpoint currently returns `{"routes": [...]}` where each route is `{"coords": [...], "distance_m": int}`. After this task each route also has `"source": "ors" | "strava" | "previous"` and an optional `"name": str | null`.

- [ ] **Step 1: Write new/updated tests**

In `tests/test_api.py`, update `TestRouteSuggestion` to add these tests after the existing ones:

```python
    def test_routes_have_source_field(self, client, auth_headers, app, monkeypatch):
        from runcoach.config import Config
        app.config["config"] = Config(
            openai_api_key="test-key",
            openai_model="gpt-4o",
            data_dir=app.config["config"].data_dir,
            timezone="Europe/London",
            secret_key="test-secret-key",
            ors_api_key="fake-ors-key",
        )
        fake_response = {
            "features": [{
                "geometry": {"coordinates": [[-0.1, 51.5], [-0.11, 51.51]]},
                "properties": {"summary": {"distance": 5012}},
            }]
        }
        import unittest.mock as mock
        with mock.patch("runcoach.web.ors.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = fake_response
            resp = client.post(
                "/api/v1/route-suggestion",
                json={"lat": 51.5, "lng": -0.1, "distance_m": 5000},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        routes = resp.get_json()["routes"]
        assert all("source" in r for r in routes)
        assert routes[0]["source"] == "ors"

    def test_includes_strava_routes_near_user(self, client, auth_headers, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        # Seed a Strava route that starts very close to the request lat/lng
        # and has matching distance. Polyline encodes a single point at (51.5001, -0.1001)
        # — use a real encoded polyline for (51.5001, -0.1001) -> (51.5011, -0.1011)
        # Encode manually: we'll use decode_polyline in reverse (or just store a
        # precomputed encoded value).
        # Instead, store a known polyline decoded by decode_polyline as:
        # [[51.5001, -0.1001], [51.5011, -0.1011]]
        # We precompute: use the actual encode or mock decode_polyline.
        from runcoach.strava import decode_polyline
        # Use the Python polyline encoder to create a valid polyline
        # Encode [(51.5001, -0.1001), (51.5011, -0.1011)]
        # We'll mock decode_polyline to return a known value instead.
        import unittest.mock as mock
        near_coords = [[51.5001, -0.1001], [51.5011, -0.1011]]
        db.upsert_strava_routes(user_id, [{
            "strava_route_id": "999",
            "name": "My Strava Loop",
            "distance_m": 5100.0,
            "start_lat": 51.5001,
            "start_lng": -0.1001,
            "polyline": "encoded_placeholder",
        }])
        with mock.patch("runcoach.web.api.decode_polyline", return_value=near_coords), \
             mock.patch("runcoach.web.ors.fetch_routes", return_value=[]):
            resp = client.post(
                "/api/v1/route-suggestion",
                json={"lat": 51.5, "lng": -0.1, "distance_m": 5000},
                headers=auth_headers,
            )
        data = resp.get_json()
        assert resp.status_code == 200
        strava_routes = [r for r in data["routes"] if r.get("source") == "strava"]
        assert len(strava_routes) == 1
        assert strava_routes[0]["name"] == "My Strava Loop"

    def test_includes_previously_run_routes(self, client, auth_headers, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        # Insert a run with a polyline starting near (51.5, -0.1)
        with db._connect() as conn:
            conn.execute(
                """INSERT INTO runs (name, date, fit_path, stage, synced_at,
                   distance_m, strava_map_polyline, user_id)
                   VALUES ('Tuesday Run', '2026-03-01', 'r.fit', 'analyzed',
                   datetime('now'), 5050, 'poly_encoded', ?)""",
                (user_id,),
            )
        near_coords = [[51.5001, -0.1001], [51.502, -0.102]]
        import unittest.mock as mock
        with mock.patch("runcoach.web.api.decode_polyline", return_value=near_coords), \
             mock.patch("runcoach.web.ors.fetch_routes", return_value=[]):
            resp = client.post(
                "/api/v1/route-suggestion",
                json={"lat": 51.5, "lng": -0.1, "distance_m": 5000},
                headers=auth_headers,
            )
        data = resp.get_json()
        assert resp.status_code == 200
        prev_routes = [r for r in data["routes"] if r.get("source") == "previous"]
        assert len(prev_routes) == 1
        assert prev_routes[0]["name"] == "Tuesday Run"

    def test_deduplicates_previously_run_routes(self, client, auth_headers, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        for i in range(3):
            with db._connect() as conn:
                conn.execute(
                    """INSERT INTO runs (name, date, fit_path, stage, synced_at,
                       distance_m, strava_map_polyline, user_id)
                       VALUES (?, ?, 'r.fit', 'analyzed', datetime('now'), 5050, 'poly', ?)""",
                    (f"Run {i}", f"2026-03-0{i+1}", user_id),
                )
        near_coords = [[51.5001, -0.1001], [51.502, -0.102]]
        import unittest.mock as mock
        with mock.patch("runcoach.web.api.decode_polyline", return_value=near_coords), \
             mock.patch("runcoach.web.ors.fetch_routes", return_value=[]):
            resp = client.post(
                "/api/v1/route-suggestion",
                json={"lat": 51.5, "lng": -0.1, "distance_m": 5000},
                headers=auth_headers,
            )
        data = resp.get_json()
        prev_routes = [r for r in data["routes"] if r.get("source") == "previous"]
        assert len(prev_routes) == 1
```

- [ ] **Step 2: Run to confirm new tests fail**

```bash
pytest tests/test_api.py::TestRouteSuggestion -v
```

Expected: new tests fail (existing pass).

- [ ] **Step 3: Update `runcoach/web/api.py`**

First, add `decode_polyline` to the module-level imports at the top of `api.py` (alongside the existing `from runcoach.web.ors import fetch_routes`):

```python
from runcoach.strava import decode_polyline
```

Then replace the existing `api_route_suggestion` function (lines ~725-749) with:

```python
@api_bp.route("/route-suggestion", methods=["POST"])
@require_auth
def api_route_suggestion():
    body = request.get_json(silent=True) or {}
    try:
        lat = float(body["lat"])
        lng = float(body["lng"])
        distance_m = int(body["distance_m"])
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "lat, lng, and distance_m are required numeric fields"}), 400

    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return jsonify({"error": "lat/lng out of range"}), 400
    if distance_m <= 0:
        return jsonify({"error": "distance_m must be positive"}), 400

    from runcoach.web.ors import filter_routes_by_proximity, deduplicate_routes

    cfg: Config = current_app.config["config"]
    db = get_db()
    user_id = request.user_id
    all_routes: list[dict] = []

    # ORS algorithmically-generated routes
    if cfg.ors_api_key:
        ors_routes = fetch_routes(lat, lng, distance_m, cfg.ors_api_key)
        for r in ors_routes:
            r["source"] = "ors"
        all_routes.extend(ors_routes)

    # Strava saved routes (cached in DB)
    strava_db_routes = db.get_strava_routes(user_id)
    strava_candidates = []
    for r in strava_db_routes:
        if not r.get("polyline") or not r.get("distance_m"):
            continue
        coords = decode_polyline(r["polyline"])
        if not coords:
            continue
        strava_candidates.append({
            "coords": coords,
            "distance_m": int(r["distance_m"]),
            "source": "strava",
            "name": r.get("name"),
        })
    all_routes.extend(
        filter_routes_by_proximity(strava_candidates, lat, lng, distance_m)
    )

    # Previously-run routes (from Strava-linked activity polylines)
    prev_runs = db.get_runs_with_polylines(user_id, limit=200)
    prev_candidates = []
    for run in prev_runs:
        coords = decode_polyline(run["strava_map_polyline"])
        if not coords or not run.get("distance_m"):
            continue
        prev_candidates.append({
            "coords": coords,
            "distance_m": int(run["distance_m"]),
            "source": "previous",
            "name": run.get("name"),
        })
    prev_nearby = filter_routes_by_proximity(prev_candidates, lat, lng, distance_m)
    all_routes.extend(deduplicate_routes(prev_nearby))

    if not all_routes:
        if not cfg.ors_api_key:
            return jsonify({"error": "Route suggestions are not configured (ORS_API_KEY missing)"}), 503
        return jsonify({"error": "Route service unavailable"}), 502

    return jsonify({"routes": all_routes})
```

- [ ] **Step 4: Run full TestRouteSuggestion suite**

```bash
pytest tests/test_api.py::TestRouteSuggestion -v
```

Expected: all tests pass (including the existing ones that check for `coords` and `distance_m`).

- [ ] **Step 5: Run full API test suite to check for regressions**

```bash
pytest tests/test_api.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add runcoach/web/api.py tests/test_api.py
git commit -m "feat: extend route-suggestion endpoint with Strava saved routes and previously-run routes"
```

---

## Task 5: Flutter — source badge in `_RouteTab`

**Files:**
- Modify: `mobile/lib/screens/workout_detail_screen.dart`
- Modify: `mobile/test/screens/workout_detail_screen_test.dart`

The `_RouteTab` widget displays the current route on a map with prev/next navigation. Each route dict now has an optional `"source"` key. When source is `"strava"` show a "My routes" chip; when `"previous"` show a "Previously run" chip. ORS routes show no badge. Optionally show the route name below the badge if `"name"` is non-null.

- [ ] **Step 1: Write failing tests**

Add to `mobile/test/screens/workout_detail_screen_test.dart`:

```dart
import 'package:flutter_map/flutter_map.dart';

// Helper to build a _RouteTab-equivalent via WorkoutDetailScreen route tab
// We can't test _RouteTab directly (private class), so we test it via the
// route Map data rendered through the _RouteTab state.
// Instead, unit-test the badge logic by extracting it — but since _RouteTab
// is a private class in the same file, we write widget tests that pump
// _RouteTab indirectly.
//
// Approach: add a thin public test-helper constructor to the test, or
// test the label text that appears in the widget tree.

group('_RouteTab source badge', () {
  // Build a minimal WorkoutDetailScreen and jump to the Route tab,
  // injecting pre-fetched routes via a test seam.
  // Because _fetchRoutes() uses Geolocator which is unavailable in tests,
  // we verify the badge renders correctly by testing _RouteTab directly.
  // Since _RouteTab is private, we expose a testable wrapper.
  //
  // The simplest approach: extract badge logic into a top-level function
  // _routeSourceLabel(String? source) -> String? and test that.
  // The plan calls for adding _routeSourceLabel as a top-level function
  // in workout_detail_screen.dart (see implementation step).

  test('_routeSourceLabel returns null for ors source', () {
    expect(_routeSourceLabel('ors'), isNull);
  });

  test('_routeSourceLabel returns "My routes" for strava source', () {
    expect(_routeSourceLabel('strava'), equals('My routes'));
  });

  test('_routeSourceLabel returns "Previously run" for previous source', () {
    expect(_routeSourceLabel('previous'), equals('Previously run'));
  });

  test('_routeSourceLabel returns null for null source', () {
    expect(_routeSourceLabel(null), isNull);
  });
});
```

The tests reference `_routeSourceLabel` which will be a package-private function added in the next step. Add this import at the top of the test file:

```dart
import '../../lib/screens/workout_detail_screen.dart';
```

The function will be package-private (no leading underscore in the exported name). Actually, Dart doesn't have package-private — any top-level function in the library is accessible from tests in the same package. Name it `routeSourceLabel` (no underscore) so it can be called from the test.

Update the test to use `routeSourceLabel`:

```dart
test('routeSourceLabel returns null for ors source', () {
  expect(routeSourceLabel('ors'), isNull);
});

test('routeSourceLabel returns "My routes" for strava source', () {
  expect(routeSourceLabel('strava'), equals('My routes'));
});

test('routeSourceLabel returns "Previously run" for previous source', () {
  expect(routeSourceLabel('previous'), equals('Previously run'));
});

test('routeSourceLabel returns null for null source', () {
  expect(routeSourceLabel(null), isNull);
});
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd mobile && flutter test test/screens/workout_detail_screen_test.dart
```

Expected: compile error — `routeSourceLabel` not defined.

- [ ] **Step 3: Add `routeSourceLabel()` and badge widget to `workout_detail_screen.dart`**

Add a top-level function before the `WorkoutDetailScreen` class:

```dart
/// Returns the badge label for a route source, or null if no badge should be shown.
String? routeSourceLabel(String? source) => switch (source) {
  'strava' => 'My routes',
  'previous' => 'Previously run',
  _ => null,
};
```

In `_RouteTab.build()`, update the map display section. After the `Expanded(child: FlutterMap(...))` widget, inside the `Column`, add a badge overlay using a `Stack`. Replace the existing `Expanded(child: FlutterMap(...))` with:

```dart
Expanded(
  child: Stack(
    children: [
      FlutterMap(
        options: MapOptions(
          initialCameraFit: CameraFit.coordinates(
            coordinates: points,
            padding: const EdgeInsets.all(32),
          ),
          interactionOptions: const InteractionOptions(
            flags: InteractiveFlag.all & ~InteractiveFlag.rotate,
          ),
        ),
        children: [
          TileLayer(
            urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
            userAgentPackageName: 'com.runcoach.app',
          ),
          PolylineLayer(
            polylines: [
              Polyline(
                points: points,
                color: const Color(0xFFea580c),
                strokeWidth: 3,
              ),
            ],
          ),
          if (points.isNotEmpty)
            MarkerLayer(
              markers: [
                Marker(
                  point: points.first,
                  child: const Icon(
                    Icons.circle,
                    color: Color(0xFF4ADE80),
                    size: 12,
                  ),
                ),
              ],
            ),
        ],
      ),
      if (routeSourceLabel(route['source'] as String?) != null)
        Positioned(
          top: 12,
          left: 12,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
            decoration: BoxDecoration(
              color: Colors.black87,
              borderRadius: BorderRadius.circular(20),
            ),
            child: Text(
              routeSourceLabel(route['source'] as String?)!,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ),
      if ((route['name'] as String?) != null &&
          routeSourceLabel(route['source'] as String?) != null)
        Positioned(
          top: 44,
          left: 12,
          right: 12,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: Colors.black54,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(
              route['name'] as String,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 11,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ),
    ],
  ),
),
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd mobile && flutter test test/screens/workout_detail_screen_test.dart
```

Expected: all tests pass including the 4 new badge tests.

- [ ] **Step 5: Run full Flutter test suite**

```bash
cd mobile && flutter test
```

Expected: all pass.

- [ ] **Step 6: Run dart format**

```bash
cd mobile && dart format lib/screens/workout_detail_screen.dart test/screens/workout_detail_screen_test.dart
```

- [ ] **Step 7: Commit**

```bash
git add mobile/lib/screens/workout_detail_screen.dart mobile/test/screens/workout_detail_screen_test.dart
git commit -m "feat: show My Routes / Previously Run badge on Strava and historical routes in Route tab"
```

---

## Final Pre-Merge Checks

- [ ] **Run full Python test suite (unit + e2e)**

```bash
pytest && pytest -m e2e --no-cov -v
```

Expected: all pass.

- [ ] **Run full Flutter test suite**

```bash
cd mobile && dart format --output=none --set-exit-if-changed . && flutter test
```

Expected: all pass, no format issues.
