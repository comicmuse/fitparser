# DB Migration Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove dead migration guards from `_init_schema()` by moving all columns into `SCHEMA_SQL` and verifying the behaviour is correct via tests.

**Architecture:** `RunCoachDB._init_schema()` currently runs `SCHEMA_SQL` (base schema) then checks for ~15 missing columns and adds them via `ALTER TABLE`. Since production is already at the latest schema and we're the only user, the guards are dead code. We promote all columns into `SCHEMA_SQL` (which uses `CREATE TABLE IF NOT EXISTS`, so existing tables are untouched) and strip the `ALTER TABLE` guards. Two invariants that are not migrations — ensure-first-user-is-admin and coach_profile.txt seed — stay in `_init_schema()`.

**Tech Stack:** Python 3.11+, SQLite via stdlib `sqlite3`, pytest

---

## Files

- Modify: `runcoach/db.py` — update `SCHEMA_SQL` with all columns, simplify `_init_schema()`
- Modify: `tests/test_db.py` — add `TestDatabaseStartup` class with column-presence and reinit tests

---

### Task 1: Write failing tests for startup behaviour

These tests must pass against the current code (they document existing correct behaviour). We write them first so we have a green baseline before touching `db.py`.

**Files:**
- Modify: `tests/test_db.py`

- [ ] **Step 1: Add `TestDatabaseStartup` class to `tests/test_db.py`**

Append the following class to the bottom of `tests/test_db.py`:

```python
class TestDatabaseStartup:
    """Tests for _init_schema correctness — fresh DB and re-init of existing DB."""

    EXPECTED_RUNS_COLUMNS = {
        "id", "stryd_activity_id", "name", "date", "distance_m", "moving_time_s",
        "fit_path", "yaml_path", "md_path", "stage", "error_message", "avg_power_w",
        "avg_hr", "workout_name", "commentary", "analyzed_at", "model_used",
        "prompt_tokens", "completion_tokens", "synced_at", "parsed_at",
        "created_at", "updated_at", "is_manual_upload", "stryd_rss",
        "garmin_connect_id", "strava_activity_id", "strava_map_polyline", "user_id",
    }

    EXPECTED_USERS_COLUMNS = {
        "id", "username", "password_hash", "created_at", "last_login",
        "athlete_profile", "stryd_athlete_id", "strava_access_token",
        "strava_refresh_token", "strava_token_expires_at", "strava_athlete_id",
        "strava_webhook_subscription_id", "display_name", "race_date",
        "race_distance", "stryd_email", "stryd_password", "is_active", "is_admin",
    }

    EXPECTED_PLANNED_WORKOUTS_COLUMNS = {
        "id", "date", "title", "description", "workout_type", "duration_s",
        "distance_m", "stress", "intensity_zones", "activity_id", "raw_json",
        "created_at", "updated_at", "user_id",
    }

    EXPECTED_SYNC_LOG_COLUMNS = {
        "id", "started_at", "finished_at", "status", "activities_found",
        "activities_new", "error_message", "user_id",
    }

    def _get_columns(self, db: RunCoachDB, table: str) -> set[str]:
        with db._connect() as conn:
            rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {row[1] for row in rows}

    def test_fresh_db_runs_columns(self, tmp_path):
        """Fresh DB has all expected columns on the runs table."""
        db = RunCoachDB(tmp_path / "test.db")
        assert self.EXPECTED_RUNS_COLUMNS == self._get_columns(db, "runs")

    def test_fresh_db_users_columns(self, tmp_path):
        """Fresh DB has all expected columns on the users table."""
        db = RunCoachDB(tmp_path / "test.db")
        assert self.EXPECTED_USERS_COLUMNS == self._get_columns(db, "users")

    def test_fresh_db_planned_workouts_columns(self, tmp_path):
        """Fresh DB has all expected columns on the planned_workouts table."""
        db = RunCoachDB(tmp_path / "test.db")
        assert self.EXPECTED_PLANNED_WORKOUTS_COLUMNS == self._get_columns(db, "planned_workouts")

    def test_fresh_db_sync_log_columns(self, tmp_path):
        """Fresh DB has all expected columns on the sync_log table."""
        db = RunCoachDB(tmp_path / "test.db")
        assert self.EXPECTED_SYNC_LOG_COLUMNS == self._get_columns(db, "sync_log")

    def test_fresh_db_planned_workouts_unique_index_includes_user_id(self, tmp_path):
        """The unique index on planned_workouts must include user_id so two users
        can have a workout with the same date+title."""
        db = RunCoachDB(tmp_path / "test.db")
        db.ensure_default_user("user1", "hash1")
        db.ensure_default_user("user2", "hash2")
        # Both users can have a workout on the same date with the same title
        db.upsert_planned_workout(date="2026-05-01", title="Tempo", user_id=1)
        db.upsert_planned_workout(date="2026-05-01", title="Tempo", user_id=2)
        workouts = db.get_all_planned_workouts()
        assert len(workouts) == 2

    def test_reinit_existing_db_preserves_data(self, tmp_path):
        """Reinitialising against an existing fully-migrated DB does not destroy data."""
        db_path = tmp_path / "test.db"
        db = RunCoachDB(db_path)
        db.ensure_default_user("athlete", "hash")
        run_id = db.insert_run(
            stryd_activity_id=42,
            name="Test Run",
            date="2026-05-01",
            fit_path="activities/test.fit",
            user_id=1,
        )

        # Re-open (triggers _init_schema again)
        db2 = RunCoachDB(db_path)
        run = db2.get_run(run_id)
        assert run is not None
        assert run["name"] == "Test Run"

    def test_reinit_existing_db_schema_unchanged(self, tmp_path):
        """Reinitialising an existing DB does not add or remove columns."""
        db_path = tmp_path / "test.db"
        db = RunCoachDB(db_path)
        cols_before = self._get_columns(db, "runs")

        db2 = RunCoachDB(db_path)
        cols_after = self._get_columns(db2, "runs")

        assert cols_before == cols_after

    def test_first_user_is_always_admin(self, tmp_path):
        """The first user created is always promoted to admin by _init_schema."""
        db = RunCoachDB(tmp_path / "test.db")
        db.ensure_default_user("athlete", "hash")
        user = db.get_user_by_username("athlete")
        assert user["is_admin"] == 1

    def test_second_user_is_not_admin(self, tmp_path):
        """Subsequent users are not automatically admin."""
        db = RunCoachDB(tmp_path / "test.db")
        db.ensure_default_user("athlete", "hash")
        user2_id = db.create_user("guest", "hash2")
        user2 = db.get_user_by_id(user2_id)
        assert user2["is_admin"] == 0
```

- [ ] **Step 2: Run the new tests against current code to confirm they all pass**

```bash
source .venv/bin/activate
pytest tests/test_db.py::TestDatabaseStartup -v
```

Expected: all 9 tests **PASS**. If any fail, the current code has a bug — fix it before continuing.

- [ ] **Step 3: Commit the tests**

```bash
git add tests/test_db.py
git commit -m "test: add startup behaviour tests for DB schema and reinit"
```

---

### Task 2: Promote all columns into SCHEMA_SQL

Update `SCHEMA_SQL` in `runcoach/db.py` so it reflects the complete final schema. The `CREATE TABLE IF NOT EXISTS` guards mean existing tables are left untouched by this change.

**Files:**
- Modify: `runcoach/db.py:11-98`

- [ ] **Step 1: Replace `SCHEMA_SQL` with the complete schema**

Replace the entire `SCHEMA_SQL` string (lines 11–98) with:

```python
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stryd_activity_id INTEGER UNIQUE,
    name TEXT,
    date TEXT NOT NULL,
    distance_m REAL,
    moving_time_s INTEGER,
    fit_path TEXT,
    yaml_path TEXT,
    md_path TEXT,
    stage TEXT NOT NULL DEFAULT 'synced',
    error_message TEXT,
    avg_power_w REAL,
    avg_hr INTEGER,
    workout_name TEXT,
    commentary TEXT,
    analyzed_at TEXT,
    model_used TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    synced_at TEXT NOT NULL,
    parsed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    is_manual_upload INTEGER NOT NULL DEFAULT 0,
    stryd_rss REAL,
    garmin_connect_id TEXT,
    strava_activity_id TEXT,
    strava_map_polyline TEXT,
    user_id INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    activities_found INTEGER,
    activities_new INTEGER,
    error_message TEXT,
    user_id INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_runs_date ON runs(date);
CREATE INDEX IF NOT EXISTS idx_runs_stage ON runs(stage);
CREATE INDEX IF NOT EXISTS idx_runs_user_id ON runs(user_id);

CREATE TABLE IF NOT EXISTS planned_workouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    title TEXT,
    description TEXT,
    workout_type TEXT,
    duration_s REAL,
    distance_m REAL,
    stress REAL,
    intensity_zones TEXT,
    activity_id TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    user_id INTEGER NOT NULL DEFAULT 1
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_planned_date_title
    ON planned_workouts(date, title, user_id);
CREATE INDEX IF NOT EXISTS idx_planned_date ON planned_workouts(date);
CREATE INDEX IF NOT EXISTS idx_planned_workouts_user_id ON planned_workouts(user_id);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_login TEXT,
    athlete_profile TEXT,
    stryd_athlete_id TEXT,
    strava_access_token TEXT,
    strava_refresh_token TEXT,
    strava_token_expires_at INTEGER,
    strava_athlete_id TEXT,
    strava_webhook_subscription_id INTEGER,
    display_name TEXT,
    race_date TEXT,
    race_distance TEXT,
    stryd_email TEXT,
    stryd_password TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    is_admin INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS run_chat (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    message TEXT NOT NULL,
    model_used TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_run_chat_run_user ON run_chat(run_id, user_id);

"""
```

- [ ] **Step 2: Run tests — must still be green**

```bash
pytest tests/test_db.py::TestDatabaseStartup -v
```

Expected: all 9 tests PASS.

---

### Task 3: Simplify `_init_schema()`

Strip all `ALTER TABLE` guards and the table-rebuild migration. Keep only:
1. `conn.executescript(SCHEMA_SQL)`
2. Ensure-first-user-is-admin update
3. `coach_profile.txt` seed for `athlete_profile`

**Files:**
- Modify: `runcoach/db.py:117-298`

- [ ] **Step 1: Replace `_init_schema()` with the simplified version**

Replace the entire `_init_schema` method with:

```python
def _init_schema(self) -> None:
    with self._connect() as conn:
        conn.executescript(SCHEMA_SQL)
        # Always ensure the first-ever user is an admin (idempotent).
        conn.execute(
            """UPDATE users SET is_admin = 1
               WHERE id = (SELECT MIN(id) FROM users)
               AND NOT EXISTS (SELECT 1 FROM users WHERE is_admin = 1)"""
        )
        # Seed athlete_profile from coach_profile.txt on first startup if blank.
        seed_path = Path(__file__).resolve().parent.parent / "coach_profile.txt"
        if seed_path.exists():
            try:
                seed_text = seed_path.read_text(encoding="utf-8").strip()
                conn.execute(
                    """UPDATE users SET athlete_profile = ?
                       WHERE athlete_profile IS NULL AND id = (SELECT MIN(id) FROM users)""",
                    (seed_text,),
                )
            except Exception:
                log.exception("Failed to seed athlete_profile from coach_profile.txt")
```

- [ ] **Step 2: Run the full test suite**

```bash
pytest -v
```

Expected: all tests PASS. Pay attention to `TestDatabaseStartup` and `TestDatabaseInit`.

- [ ] **Step 3: Commit**

```bash
git add runcoach/db.py
git commit -m "refactor: remove dead ALTER TABLE migration guards from _init_schema"
```

---

### Task 4: Push and deploy

- [ ] **Step 1: Push**

```bash
git push
```

- [ ] **Step 2: Watch CI, then deploy**

```bash
gh run watch $(gh run list --limit 1 --json databaseId -q '.[0].databaseId')
cd /srv/runcoach && docker compose pull && docker compose up -d
```
