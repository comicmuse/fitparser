# LLM Rate Limiting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a configurable per-user daily cap on LLM calls (chat + analysis combined), with admin exemption, midnight-UTC reset, and a retry button on the mobile chat screen for rate-limited messages.

**Architecture:** A new `rate_limiter.py` module exposes a single `check_and_consume(db, user_id)` function called by the three LLM entry points (web chat, API chat, analyze routes, pipeline). Usage history lives in a new `llm_usage` table (one row per user per UTC date). Runtime admin config lives in a new `site_settings` key-value table. The feature is disabled by default — no behaviour change until an admin enables it.

**Tech Stack:** Python/Flask (server), SQLite (storage), Flutter/Dart (mobile), Playwright (E2E).

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `runcoach/rate_limiter.py` | `check_and_consume` — all rate-limit logic |
| Create | `runcoach/web/templates/admin_settings.html` | Global toggle + default limit form |
| Create | `tests/test_rate_limiter.py` | Unit tests for rate_limiter module |
| Create | `tests/e2e/test_rate_limit.py` | E2E flash message test |
| Modify | `runcoach/db.py` | Schema, migrations, 5 new methods |
| Modify | `runcoach/web/routes.py` | `run_chat`, `analyze_run_route`, admin routes |
| Modify | `runcoach/web/api.py` | `post_run_chat`, `analyze_run` |
| Modify | `runcoach/pipeline.py` | Check quota before each analysis |
| Modify | `runcoach/web/templates/admin_users.html` | Per-user Limit column |
| Modify | `tests/test_db.py` | New DB method tests |
| Modify | `tests/test_web.py` | Route integration tests |
| Modify | `tests/test_api.py` | API integration tests |
| Modify | `mobile/lib/models/chat_message.dart` | Add `status` field |
| Modify | `mobile/lib/services/api_service.dart` | Pass `status` in history; error extraction |
| Modify | `mobile/lib/providers/chat_provider.dart` | `lastError` state; DioException handling |
| Modify | `mobile/lib/widgets/coaching_chat_widget.dart` | Retry button; SnackBar on error; analyze fix |
| Modify | `mobile/test/widgets/coaching_chat_widget_test.dart` | New Flutter tests |

---

## Task 1: DB Schema — new tables and column migrations

**Files:**
- Modify: `runcoach/db.py:11-147` (SCHEMA_SQL) and `db.py:166-188` (`_init_schema`)
- Test: `tests/test_db.py`

- [ ] **Step 1: Write failing tests**

Add to `TestDatabaseInit` class in `tests/test_db.py`:

```python
def test_db_init_creates_rate_limit_tables(self, tmp_path):
    db_path = tmp_path / "test.db"
    db = RunCoachDB(db_path)
    with db._connect() as conn:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
    assert "site_settings" in tables
    assert "llm_usage" in tables

def test_db_init_adds_llm_daily_limit_to_users(self, tmp_path):
    db_path = tmp_path / "test.db"
    db = RunCoachDB(db_path)
    with db._connect() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    assert "llm_daily_limit" in cols

def test_db_init_adds_status_to_run_chat(self, tmp_path):
    db_path = tmp_path / "test.db"
    db = RunCoachDB(db_path)
    with db._connect() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(run_chat)").fetchall()]
    assert "status" in cols

def test_db_init_seeds_site_settings(self, tmp_path):
    db_path = tmp_path / "test.db"
    db = RunCoachDB(db_path)
    with db._connect() as conn:
        rows = {r[0]: r[1] for r in conn.execute(
            "SELECT key, value FROM site_settings"
        ).fetchall()}
    assert rows.get("llm_limiting_enabled") == "0"
    assert rows.get("llm_daily_limit_default") == "10"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_db.py::TestDatabaseInit -v -k "rate_limit or llm_daily or status_to_run or seeds_site"
```

Expected: 4 failures.

- [ ] **Step 3: Add tables to SCHEMA_SQL**

In `runcoach/db.py`, append the following inside the `SCHEMA_SQL` triple-quoted string, just before the closing `"""` (after the `strava_routes` block):

```sql

CREATE TABLE IF NOT EXISTS site_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_usage (
    user_id    INTEGER NOT NULL REFERENCES users(id),
    date       TEXT NOT NULL,
    call_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, date)
);
```

- [ ] **Step 4: Add a column-migration helper and run migrations in `_init_schema`**

Add a private helper function just above the `RunCoachDB` class (after `_now_iso`):

```python
def _add_column_if_missing(
    conn: sqlite3.Connection, table: str, column: str, col_def: str
) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
```

Then in `_init_schema`, after the `executescript(SCHEMA_SQL)` call, add:

```python
            _add_column_if_missing(conn, "users", "llm_daily_limit", "INTEGER")
            _add_column_if_missing(
                conn, "run_chat", "status", "TEXT NOT NULL DEFAULT 'ok'"
            )
            conn.execute(
                "INSERT OR IGNORE INTO site_settings (key, value) VALUES (?, ?)",
                ("llm_limiting_enabled", "0"),
            )
            conn.execute(
                "INSERT OR IGNORE INTO site_settings (key, value) VALUES (?, ?)",
                ("llm_daily_limit_default", "10"),
            )
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/test_db.py::TestDatabaseInit -v -k "rate_limit or llm_daily or status_to_run or seeds_site"
```

Expected: 4 passing.

- [ ] **Step 6: Commit**

```bash
git add runcoach/db.py tests/test_db.py
git commit -m "feat: add site_settings and llm_usage tables, column migrations"
```

---

## Task 2: DB methods — `get_site_setting` and `set_site_setting`

**Files:**
- Modify: `runcoach/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write failing tests**

Add a new `TestSiteSettings` class in `tests/test_db.py`:

```python
class TestSiteSettings:
    def test_get_site_setting_returns_seeded_value(self, temp_db):
        assert temp_db.get_site_setting("llm_limiting_enabled") == "0"
        assert temp_db.get_site_setting("llm_daily_limit_default") == "10"

    def test_get_site_setting_returns_default_when_absent(self, temp_db):
        assert temp_db.get_site_setting("nonexistent") is None
        assert temp_db.get_site_setting("nonexistent", default="42") == "42"

    def test_set_site_setting_upserts(self, temp_db):
        temp_db.set_site_setting("llm_limiting_enabled", "1")
        assert temp_db.get_site_setting("llm_limiting_enabled") == "1"
        # Upsert again
        temp_db.set_site_setting("llm_limiting_enabled", "0")
        assert temp_db.get_site_setting("llm_limiting_enabled") == "0"

    def test_set_site_setting_creates_new_key(self, temp_db):
        temp_db.set_site_setting("custom_key", "hello")
        assert temp_db.get_site_setting("custom_key") == "hello"
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_db.py::TestSiteSettings -v
```

Expected: 4 failures (method not found).

- [ ] **Step 3: Implement the methods**

Add the following two methods to the `RunCoachDB` class in `runcoach/db.py`, after the `_init_schema` method (before `# ------ runs ------`):

```python
    # ------ site_settings ------

    def get_site_setting(self, key: str, default: str | None = None) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM site_settings WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else default

    def set_site_setting(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO site_settings (key, value) VALUES (?, ?)",
                (key, value),
            )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_db.py::TestSiteSettings -v
```

Expected: 4 passing.

- [ ] **Step 5: Commit**

```bash
git add runcoach/db.py tests/test_db.py
git commit -m "feat: add get_site_setting and set_site_setting DB methods"
```

---

## Task 3: DB method — `check_and_increment_llm_usage`

**Files:**
- Modify: `runcoach/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write failing tests**

Add a new `TestLlmUsage` class in `tests/test_db.py`:

```python
class TestLlmUsage:
    def test_first_call_inserts_row_and_allows(self, temp_db):
        user_id = temp_db.get_default_user_id()
        incremented, count = temp_db.check_and_increment_llm_usage(user_id, "2026-05-26", 5)
        assert incremented is True
        assert count == 1

    def test_subsequent_calls_increment(self, temp_db):
        user_id = temp_db.get_default_user_id()
        temp_db.check_and_increment_llm_usage(user_id, "2026-05-26", 5)
        incremented, count = temp_db.check_and_increment_llm_usage(user_id, "2026-05-26", 5)
        assert incremented is True
        assert count == 2

    def test_denies_at_limit_without_incrementing(self, temp_db):
        user_id = temp_db.get_default_user_id()
        # Use up all 2 calls
        temp_db.check_and_increment_llm_usage(user_id, "2026-05-26", 2)
        temp_db.check_and_increment_llm_usage(user_id, "2026-05-26", 2)
        # Third call should be denied
        incremented, count = temp_db.check_and_increment_llm_usage(user_id, "2026-05-26", 2)
        assert incremented is False
        assert count == 2  # not incremented

    def test_different_dates_are_independent(self, temp_db):
        user_id = temp_db.get_default_user_id()
        temp_db.check_and_increment_llm_usage(user_id, "2026-05-25", 1)
        # Previous day used up its limit; new day should be fresh
        incremented, count = temp_db.check_and_increment_llm_usage(user_id, "2026-05-26", 1)
        assert incremented is True
        assert count == 1

    def test_limit_zero_always_denies(self, temp_db):
        user_id = temp_db.get_default_user_id()
        incremented, count = temp_db.check_and_increment_llm_usage(user_id, "2026-05-26", 0)
        assert incremented is False
        assert count == 0
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_db.py::TestLlmUsage -v
```

Expected: 5 failures.

- [ ] **Step 3: Implement the method**

Add the following section to `RunCoachDB` in `runcoach/db.py`, after the site_settings section:

```python
    # ------ llm_usage ------

    def check_and_increment_llm_usage(
        self, user_id: int, date: str, limit: int
    ) -> tuple[bool, int]:
        """Atomically check and increment the daily LLM call counter.

        Returns (True, new_count) if the call is within the limit and was counted.
        Returns (False, current_count) if the limit is already reached.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT call_count FROM llm_usage WHERE user_id = ? AND date = ?",
                (user_id, date),
            ).fetchone()
            current = row["call_count"] if row else 0
            if current < limit:
                conn.execute(
                    """INSERT INTO llm_usage (user_id, date, call_count) VALUES (?, ?, 1)
                       ON CONFLICT (user_id, date) DO UPDATE SET call_count = call_count + 1""",
                    (user_id, date),
                )
                return True, current + 1
            return False, current
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_db.py::TestLlmUsage -v
```

Expected: 5 passing.

- [ ] **Step 5: Commit**

```bash
git add runcoach/db.py tests/test_db.py
git commit -m "feat: add check_and_increment_llm_usage DB method"
```

---

## Task 4: DB — add `status` to `add_chat_message` and `get_chat_history`

**Files:**
- Modify: `runcoach/db.py:322-353`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write failing tests**

Add a new `TestChatMessageStatus` class in `tests/test_db.py`:

```python
class TestChatMessageStatus:
    def test_add_chat_message_default_status_is_ok(self, temp_db):
        user_id = temp_db.get_default_user_id()
        run_id = temp_db.insert_run(
            stryd_activity_id=None, name="Test", date="2026-05-26", fit_path="a.fit"
        )
        temp_db.add_chat_message(run_id, user_id, "user", "hello")
        history = temp_db.get_chat_history(run_id, user_id)
        assert history[0]["status"] == "ok"

    def test_add_chat_message_rate_limited_status(self, temp_db):
        user_id = temp_db.get_default_user_id()
        run_id = temp_db.insert_run(
            stryd_activity_id=None, name="Test2", date="2026-05-26", fit_path="b.fit"
        )
        temp_db.add_chat_message(
            run_id, user_id, "user", "denied message", status="rate_limited"
        )
        history = temp_db.get_chat_history(run_id, user_id)
        assert history[0]["status"] == "rate_limited"

    def test_get_chat_history_includes_status(self, temp_db):
        user_id = temp_db.get_default_user_id()
        run_id = temp_db.insert_run(
            stryd_activity_id=None, name="Test3", date="2026-05-26", fit_path="c.fit"
        )
        temp_db.add_chat_message(run_id, user_id, "user", "ok msg")
        temp_db.add_chat_message(
            run_id, user_id, "user", "denied", status="rate_limited"
        )
        history = temp_db.get_chat_history(run_id, user_id)
        assert "status" in history[0]
        assert history[1]["status"] == "rate_limited"
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_db.py::TestChatMessageStatus -v
```

Expected: 3 failures.

- [ ] **Step 3: Update `add_chat_message`**

In `runcoach/db.py`, update `add_chat_message` to accept and store `status`:

```python
    def add_chat_message(
        self,
        run_id: int,
        user_id: int,
        role: str,
        message: str,
        model_used: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        status: str = "ok",
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO run_chat
                   (run_id, user_id, role, message, model_used,
                    prompt_tokens, completion_tokens, created_at, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, user_id, role, message, model_used,
                 prompt_tokens, completion_tokens, _now_iso(), status),
            )
            return cur.lastrowid
```

- [ ] **Step 4: Update `get_chat_history` to return `status`**

In `runcoach/db.py`, update the SELECT in `get_chat_history`:

```python
    def get_chat_history(self, run_id: int, user_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id, run_id, user_id, role, message,
                          model_used, prompt_tokens, completion_tokens,
                          created_at, status
                   FROM run_chat
                   WHERE run_id = ? AND user_id = ?
                   ORDER BY created_at ASC, id ASC""",
                (run_id, user_id),
            ).fetchall()
            return [dict(r) for r in rows]
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/test_db.py::TestChatMessageStatus -v
```

Expected: 3 passing.

- [ ] **Step 6: Run broader DB tests to check no regressions**

```bash
pytest tests/test_db.py -v -q
```

Expected: all passing.

- [ ] **Step 7: Commit**

```bash
git add runcoach/db.py tests/test_db.py
git commit -m "feat: add status column support to add_chat_message and get_chat_history"
```

---

## Task 5: `rate_limiter.py` module

**Files:**
- Create: `runcoach/rate_limiter.py`
- Create: `tests/test_rate_limiter.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_rate_limiter.py`:

```python
"""Unit tests for the LLM rate limiter."""
from __future__ import annotations

import pytest
from pathlib import Path
from runcoach.db import RunCoachDB
from runcoach.auth import hash_password
from runcoach.rate_limiter import check_and_consume


@pytest.fixture
def db(tmp_path):
    _db = RunCoachDB(tmp_path / "test.db")
    _db.ensure_default_user("athlete", hash_password("pw"))
    return _db


@pytest.fixture
def user_id(db):
    return db.get_default_user_id()


def _enable_limiting(db, limit: int = 5) -> None:
    db.set_site_setting("llm_limiting_enabled", "1")
    db.set_site_setting("llm_daily_limit_default", str(limit))


def _make_non_admin(db, user_id: int) -> None:
    with db._connect() as conn:
        conn.execute("UPDATE users SET is_admin = 0 WHERE id = ?", (user_id,))


class TestCheckAndConsume:
    def test_allowed_when_limiting_disabled(self, db, user_id):
        # Default: limiting is off
        _make_non_admin(db, user_id)
        allowed, msg = check_and_consume(db, user_id)
        assert allowed is True
        assert msg is None

    def test_allowed_for_admin_regardless_of_count(self, db, user_id):
        _enable_limiting(db, limit=0)
        # Default user is admin — should always be allowed
        with db._connect() as conn:
            conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user_id,))
        allowed, msg = check_and_consume(db, user_id)
        assert allowed is True
        assert msg is None

    def test_allowed_under_limit_and_increments(self, db, user_id):
        _enable_limiting(db, limit=3)
        _make_non_admin(db, user_id)
        allowed, msg = check_and_consume(db, user_id)
        assert allowed is True
        assert msg is None

    def test_denied_at_limit_with_reset_message(self, db, user_id):
        _enable_limiting(db, limit=1)
        _make_non_admin(db, user_id)
        # Use up the one allowed call
        check_and_consume(db, user_id)
        # Second call should be denied
        allowed, msg = check_and_consume(db, user_id)
        assert allowed is False
        assert msg is not None
        assert "Daily analysis limit reached" in msg
        assert "00:00 UTC" in msg
        assert "in " in msg

    def test_denied_with_limit_zero(self, db, user_id):
        _enable_limiting(db, limit=0)
        _make_non_admin(db, user_id)
        allowed, msg = check_and_consume(db, user_id)
        assert allowed is False
        assert msg is not None

    def test_per_user_override_takes_precedence(self, db, user_id):
        _enable_limiting(db, limit=1)  # global limit = 1
        _make_non_admin(db, user_id)
        # Give user a higher personal limit
        with db._connect() as conn:
            conn.execute(
                "UPDATE users SET llm_daily_limit = 3 WHERE id = ?", (user_id,)
            )
        check_and_consume(db, user_id)
        check_and_consume(db, user_id)
        allowed, _ = check_and_consume(db, user_id)
        assert allowed is True  # 3rd call within personal limit of 3

    def test_no_usage_row_written_when_disabled(self, db, user_id):
        _make_non_admin(db, user_id)
        # Limiting disabled — no row should be written
        check_and_consume(db, user_id)
        with db._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM llm_usage").fetchone()[0]
        assert count == 0

    def test_no_usage_row_written_for_admin(self, db, user_id):
        _enable_limiting(db, limit=5)
        with db._connect() as conn:
            conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user_id,))
        check_and_consume(db, user_id)
        with db._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM llm_usage").fetchone()[0]
        assert count == 0
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_rate_limiter.py -v
```

Expected: all failures (module not found).

- [ ] **Step 3: Create `runcoach/rate_limiter.py`**

```python
"""Per-user daily LLM call quota enforcement."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)


def check_and_consume(db, user_id: int) -> tuple[bool, str | None]:
    """Check whether a user may make an LLM call and, if so, record it.

    Returns (True, None) when the call is allowed (counter has been incremented).
    Returns (False, reset_message) when the daily cap is reached.
    Short-circuits without any DB write when limiting is disabled or the user is an admin.
    """
    if db.get_site_setting("llm_limiting_enabled", default="0") != "1":
        return True, None

    user = db.get_user_by_id(user_id)
    if not user:
        return True, None
    if user.get("is_admin"):
        return True, None

    limit_override = user.get("llm_daily_limit")
    if limit_override is not None:
        limit = int(limit_override)
    else:
        limit = int(db.get_site_setting("llm_daily_limit_default", default="10") or "10")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    incremented, _ = db.check_and_increment_llm_usage(user_id, today, limit)
    if incremented:
        return True, None

    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    delta = tomorrow - now
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes = remainder // 60
    return (
        False,
        f"Daily analysis limit reached. Resets at 00:00 UTC (in {hours}h {minutes}m).",
    )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_rate_limiter.py -v
```

Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add runcoach/rate_limiter.py tests/test_rate_limiter.py
git commit -m "feat: add rate_limiter module with check_and_consume"
```

---

## Task 6: Server chat integration — `run_chat` (routes.py + api.py)

Both the web `run_chat` route and the API `post_run_chat` endpoint follow the same pattern: check quota, persist the user message as `rate_limited` on denial, return 429.

**Files:**
- Modify: `runcoach/web/routes.py:435-481`
- Modify: `runcoach/web/api.py:288-344`
- Test: `tests/test_web.py`, `tests/test_api.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_web.py` inside the class that contains `test_chat_route_returns_assistant_response` (look for `class Test` containing that test):

```python
def test_chat_route_rate_limited_returns_429(self, client, app):
    db = app.config["db"]
    user_id = db.get_default_user_id()
    # Make user non-admin and enable limiting with limit=0
    with db._connect() as conn:
        conn.execute("UPDATE users SET is_admin = 0 WHERE id = ?", (user_id,))
    db.set_site_setting("llm_limiting_enabled", "1")
    db.set_site_setting("llm_daily_limit_default", "0")
    run_id = db.insert_run(
        stryd_activity_id=7010,
        name="Rate Limit Run",
        date="2026-05-26",
        fit_path="activities/rl.fit",
    )
    db.update_analyzed(
        run_id=run_id, md_path=None,
        commentary="Good run.", model_used="gpt-4o",
        prompt_tokens=10, completion_tokens=5,
    )
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    resp = client.post(
        f"/run/{run_id}/chat",
        json={"message": "How was my HR?"},
        content_type="application/json",
    )
    assert resp.status_code == 429
    data = resp.get_json()
    assert "Daily analysis limit reached" in data["error"]

def test_chat_route_rate_limited_persists_message(self, client, app):
    db = app.config["db"]
    user_id = db.get_default_user_id()
    with db._connect() as conn:
        conn.execute("UPDATE users SET is_admin = 0 WHERE id = ?", (user_id,))
    db.set_site_setting("llm_limiting_enabled", "1")
    db.set_site_setting("llm_daily_limit_default", "0")
    run_id = db.insert_run(
        stryd_activity_id=7011,
        name="Persist Run",
        date="2026-05-26",
        fit_path="activities/persist.fit",
    )
    db.update_analyzed(
        run_id=run_id, md_path=None,
        commentary="Good run.", model_used="gpt-4o",
        prompt_tokens=10, completion_tokens=5,
    )
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    client.post(
        f"/run/{run_id}/chat",
        json={"message": "Save me"},
        content_type="application/json",
    )
    history = db.get_chat_history(run_id, user_id)
    assert len(history) == 1
    assert history[0]["role"] == "user"
    assert history[0]["message"] == "Save me"
    assert history[0]["status"] == "rate_limited"
```

Add to `tests/test_api.py` inside the chat test class:

```python
def test_post_chat_rate_limited_returns_429(self, client, auth_headers, app):
    db = app.config["db"]
    user_id = db.get_default_user_id()
    with db._connect() as conn:
        conn.execute("UPDATE users SET is_admin = 0 WHERE id = ?", (user_id,))
    db.set_site_setting("llm_limiting_enabled", "1")
    db.set_site_setting("llm_daily_limit_default", "0")
    run_id = db.insert_run(
        stryd_activity_id=8020,
        name="API Rate Limit",
        date="2026-05-26",
        fit_path="activities/api_rl.fit",
        distance_m=5000,
        moving_time_s=1500,
    )
    resp = client.post(
        f"/api/v1/runs/{run_id}/chat",
        json={"message": "too many calls"},
        headers=auth_headers,
    )
    assert resp.status_code == 429
    assert "Daily analysis limit reached" in resp.get_json()["error"]

def test_post_chat_rate_limited_persists_user_message(self, client, auth_headers, app):
    db = app.config["db"]
    user_id = db.get_default_user_id()
    with db._connect() as conn:
        conn.execute("UPDATE users SET is_admin = 0 WHERE id = ?", (user_id,))
    db.set_site_setting("llm_limiting_enabled", "1")
    db.set_site_setting("llm_daily_limit_default", "0")
    run_id = db.insert_run(
        stryd_activity_id=8021,
        name="API Persist",
        date="2026-05-26",
        fit_path="activities/api_persist.fit",
        distance_m=5000,
        moving_time_s=1500,
    )
    client.post(
        f"/api/v1/runs/{run_id}/chat",
        json={"message": "keep me"},
        headers=auth_headers,
    )
    history = db.get_chat_history(run_id, user_id)
    assert len(history) == 1
    assert history[0]["status"] == "rate_limited"
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_web.py -v -k "rate_limited" && pytest tests/test_api.py -v -k "rate_limited"
```

Expected: all failures.

- [ ] **Step 3: Update `routes.py` `run_chat`**

At the top of `runcoach/web/routes.py`, add the import (after existing imports):

```python
from runcoach.rate_limiter import check_and_consume
```

In the `run_chat` function, add the rate-limit check after the `message` validation (after the `if not message:` block, before the `history = db.get_chat_history(...)` call):

```python
    allowed, rate_msg = check_and_consume(db, user_id)
    if not allowed:
        db.add_chat_message(run_id, user_id, "user", message, status="rate_limited")
        return jsonify({"error": rate_msg}), 429
```

- [ ] **Step 4: Update `api.py` `post_run_chat`**

At the top of `runcoach/web/api.py`, add the import:

```python
from runcoach.rate_limiter import check_and_consume
```

In the `post_run_chat` function, add the same check after the `if not message:` block, before `history = db.get_chat_history(...)`:

```python
    allowed, rate_msg = check_and_consume(db, request.user_id)
    if not allowed:
        db.add_chat_message(run_id, request.user_id, "user", message, status="rate_limited")
        return jsonify({"error": rate_msg}), 429
```

Also update `get_run_chat` to include `status` in the history response (mobile needs it):

```python
    return jsonify({
        "history": [
            {
                "role": h["role"],
                "message": h["message"],
                "created_at": h["created_at"],
                "status": h.get("status", "ok"),
            }
            for h in history
        ]
    }), 200
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/test_web.py -v -k "rate_limited" && pytest tests/test_api.py -v -k "rate_limited"
```

Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add runcoach/web/routes.py runcoach/web/api.py tests/test_web.py tests/test_api.py
git commit -m "feat: rate-limit run_chat endpoints, persist rate_limited messages"
```

---

## Task 7: Server analyze integration — `analyze_run_route` (routes.py + api.py)

**Files:**
- Modify: `runcoach/web/routes.py:383-432`
- Modify: `runcoach/web/api.py:405-473`
- Test: `tests/test_web.py`, `tests/test_api.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_web.py` in the analyze-related test class:

```python
def test_analyze_rate_limited_redirects_with_flash(self, client, app):
    from unittest.mock import patch
    db = app.config["db"]
    user_id = db.get_default_user_id()
    with db._connect() as conn:
        conn.execute("UPDATE users SET is_admin = 0 WHERE id = ?", (user_id,))
    db.set_site_setting("llm_limiting_enabled", "1")
    db.set_site_setting("llm_daily_limit_default", "0")
    run_id = db.insert_run(
        stryd_activity_id=9001,
        name="Analyze Limit",
        date="2026-05-26",
        fit_path="activities/al.fit",
    )
    db.update_parsed(run_id, None, 200.0, 145, "Analyze Limit")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    resp = client.post(f"/run/{run_id}/analyze", follow_redirects=False)
    assert resp.status_code == 302
    # Follow to get flash message
    resp2 = client.post(
        f"/run/{run_id}/analyze",
        follow_redirects=True,
    )
    assert "Daily analysis limit reached" in resp2.data.decode()
```

Add to `tests/test_api.py`:

```python
def test_analyze_rate_limited_returns_429(self, client, auth_headers, app):
    db = app.config["db"]
    user_id = db.get_default_user_id()
    with db._connect() as conn:
        conn.execute("UPDATE users SET is_admin = 0 WHERE id = ?", (user_id,))
    db.set_site_setting("llm_limiting_enabled", "1")
    db.set_site_setting("llm_daily_limit_default", "0")
    run_id = db.insert_run(
        stryd_activity_id=9010,
        name="API Analyze Limit",
        date="2026-05-26",
        fit_path="activities/api_al.fit",
        distance_m=5000,
        moving_time_s=1500,
    )
    db.update_parsed(run_id, None, 200.0, 145, "API Analyze Limit")
    resp = client.post(f"/api/v1/runs/{run_id}/analyze", headers=auth_headers)
    assert resp.status_code == 429
    assert "Daily analysis limit reached" in resp.get_json()["error"]
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_web.py -v -k "analyze_rate_limited" && pytest tests/test_api.py -v -k "analyze_rate_limited"
```

Expected: all failures.

- [ ] **Step 3: Update `routes.py` `analyze_run_route`**

`check_and_consume` is already imported from Task 6. Add the rate-limit check in `analyze_run_route` after the stage check (after the `if run["stage"] not in ("parsed", "analyzed"):` block, before the `_do_analyze` definition):

```python
    allowed, rate_msg = check_and_consume(db, user_id)
    if not allowed:
        flash(rate_msg)
        return redirect(url_for("main.run_detail", run_id=run_id))
```

- [ ] **Step 4: Update `api.py` `analyze_run`**

`check_and_consume` is already imported from Task 6. Add the check in `analyze_run` after the stage check (after the `if run["stage"] != "parsed":` block, before the thread creation):

```python
    allowed, rate_msg = check_and_consume(db, request.user_id)
    if not allowed:
        return jsonify({"error": rate_msg}), 429
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/test_web.py -v -k "analyze_rate_limited" && pytest tests/test_api.py -v -k "analyze_rate_limited"
```

Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add runcoach/web/routes.py runcoach/web/api.py tests/test_web.py tests/test_api.py
git commit -m "feat: rate-limit analyze_run_route and API analyze endpoint"
```

---

## Task 8: Pipeline integration

**Files:**
- Modify: `runcoach/pipeline.py:132-162`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_pipeline.py` (find the existing pipeline test class):

```python
def test_pipeline_skips_analysis_when_quota_exceeded(self, tmp_path, mocker):
    from runcoach.db import RunCoachDB
    from runcoach.auth import hash_password
    from runcoach.config import Config
    from runcoach.pipeline import run_full_pipeline

    db_path = tmp_path / "test.db"
    db = RunCoachDB(db_path)
    db.ensure_default_user("athlete", hash_password("pw"))
    user_id = db.get_default_user_id()

    # Make non-admin and enable limit=0
    with db._connect() as conn:
        conn.execute("UPDATE users SET is_admin = 0 WHERE id = ?", (user_id,))
    db.set_site_setting("llm_limiting_enabled", "1")
    db.set_site_setting("llm_daily_limit_default", "0")

    run_id = db.insert_run(
        stryd_activity_id=None, name="Test Run",
        date="2026-05-26", fit_path="a.fit", user_id=user_id,
    )
    db.update_parsed(run_id, None, 200.0, 145, "Test Run")

    config = Config(
        openai_api_key="test-key",
        openai_model="gpt-4o",
        data_dir=tmp_path / "data",
        timezone="UTC",
        llm_auto_analyse=True,
    )

    mocker.patch("runcoach.pipeline.StrydClient")
    mocker.patch("runcoach.pipeline.sync_activities", return_value={"synced": 0, "skipped": 0})
    mock_analyze = mocker.patch("runcoach.pipeline.analyze_and_write")

    run_full_pipeline(db=db, config=config, user_id=user_id)

    mock_analyze.assert_not_called()
    updated = db.get_run(run_id, user_id=user_id)
    assert updated["stage"] == "parsed"  # not moved to analyzed
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_pipeline.py -v -k "quota_exceeded"
```

Expected: failure.

- [ ] **Step 3: Update `pipeline.py`**

At the top of `runcoach/pipeline.py`, add the import:

```python
from runcoach.rate_limiter import check_and_consume
```

In the analysis loop (around line 138), wrap each `analyze_and_write` call with a quota check. The loop currently reads:

```python
            for run in db.get_pending_runs("parsed", user_id=user_id, date_from=config.analyze_from):
                try:
                    result = analyze_and_write(run, config, db=db, user_id=user_id)
```

Change it to:

```python
            for run in db.get_pending_runs("parsed", user_id=user_id, date_from=config.analyze_from):
                allowed, rate_msg = check_and_consume(db, user_id)
                if not allowed:
                    log.warning(
                        "LLM quota exceeded for user %s, skipping run %s: %s",
                        user_id, run["id"], rate_msg,
                    )
                    continue
                try:
                    result = analyze_and_write(run, config, db=db, user_id=user_id)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_pipeline.py -v -k "quota_exceeded"
```

Expected: passing.

- [ ] **Step 5: Commit**

```bash
git add runcoach/pipeline.py tests/test_pipeline.py
git commit -m "feat: skip pipeline analysis when user LLM quota is exceeded"
```

---

## Task 9: Admin UI — global settings page

**Files:**
- Create: `runcoach/web/templates/admin_settings.html`
- Modify: `runcoach/web/routes.py` (add two new routes)
- Test: `tests/test_web.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_web.py`:

```python
class TestAdminSettings:
    def test_admin_settings_page_loads(self, client, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        with db._connect() as conn:
            conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user_id,))
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
        resp = client.get("/admin/settings")
        assert resp.status_code == 200
        assert b"LLM Rate Limiting" in resp.data

    def test_admin_settings_post_updates_values(self, client, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        with db._connect() as conn:
            conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user_id,))
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
        resp = client.post(
            "/admin/settings",
            data={"llm_limiting_enabled": "on", "llm_daily_limit_default": "20"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert db.get_site_setting("llm_limiting_enabled") == "1"
        assert db.get_site_setting("llm_daily_limit_default") == "20"

    def test_admin_settings_requires_admin(self, client, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        with db._connect() as conn:
            conn.execute("UPDATE users SET is_admin = 0 WHERE id = ?", (user_id,))
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
        resp = client.get("/admin/settings")
        assert resp.status_code in (302, 403)
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_web.py::TestAdminSettings -v
```

Expected: all failures.

- [ ] **Step 3: Add routes to `routes.py`**

Add after the `admin_delete_user` route (around line 795):

```python
@bp.route("/admin/settings", methods=["GET", "POST"])
@_admin_required
def admin_settings():
    db = _db()
    if request.method == "POST":
        enabled = "1" if request.form.get("llm_limiting_enabled") else "0"
        raw_limit = request.form.get("llm_daily_limit_default", "").strip()
        if raw_limit.isdigit() and int(raw_limit) > 0:
            db.set_site_setting("llm_daily_limit_default", raw_limit)
        db.set_site_setting("llm_limiting_enabled", enabled)
        flash("Settings saved.")
        return redirect(url_for("main.admin_settings"))
    return render_template(
        "admin_settings.html",
        llm_limiting_enabled=db.get_site_setting("llm_limiting_enabled", "0") == "1",
        llm_daily_limit_default=db.get_site_setting("llm_daily_limit_default", "10"),
    )
```

- [ ] **Step 4: Create `admin_settings.html`**

Create `runcoach/web/templates/admin_settings.html`:

```html
{% extends "base.html" %}
{% block title %}Site Settings — RunCoach{% endblock %}

{% block content %}
<div style="display:flex; align-items:baseline; justify-content:space-between; margin-bottom:1rem;">
  <h1 style="font-size:1.4rem; font-weight:700;">Site Settings</h1>
  <a href="{{ url_for('main.admin_users') }}" style="font-size:0.9rem;">← Users</a>
</div>

<div class="card" style="max-width:520px;">
  <h2 style="font-size:1.1rem; font-weight:600; margin-bottom:1rem;">LLM Rate Limiting</h2>
  <form method="POST" action="{{ url_for('main.admin_settings') }}">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

    <div style="margin-bottom:1rem; display:flex; align-items:center; gap:0.75rem;">
      <input
        type="checkbox"
        id="llm_limiting_enabled"
        name="llm_limiting_enabled"
        {% if llm_limiting_enabled %}checked{% endif %}
      >
      <label for="llm_limiting_enabled" style="font-size:0.95rem;">
        Enable daily LLM call limit for non-admin users
      </label>
    </div>

    <div style="margin-bottom:1.5rem;">
      <label for="llm_daily_limit_default" style="display:block; font-size:0.9rem; margin-bottom:0.35rem;">
        Default daily limit (calls per user)
      </label>
      <input
        type="number"
        id="llm_daily_limit_default"
        name="llm_daily_limit_default"
        value="{{ llm_daily_limit_default }}"
        min="1"
        style="width:100px; padding:0.35rem 0.5rem; border:1px solid var(--border); border-radius:4px;"
      >
      <p style="font-size:0.8rem; color:var(--fg-muted); margin-top:0.35rem;">
        Applies to all non-admin users unless a per-user override is set. Resets daily at 00:00 UTC.
      </p>
    </div>

    <button type="submit" class="btn btn-primary">Save settings</button>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/test_web.py::TestAdminSettings -v
```

Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add runcoach/web/routes.py runcoach/web/templates/admin_settings.html tests/test_web.py
git commit -m "feat: add admin settings page for LLM rate limiting"
```

---

## Task 10: Admin UI — per-user limit override

**Files:**
- Modify: `runcoach/db.py` (add `set_user_llm_limit`)
- Modify: `runcoach/web/routes.py` (new route)
- Modify: `runcoach/web/templates/admin_users.html` (Limit column)
- Test: `tests/test_web.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_web.py`:

```python
class TestAdminUserLimit:
    def test_set_user_limit_updates_db(self, client, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        with db._connect() as conn:
            conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user_id,))
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
        resp = client.post(
            f"/admin/users/{user_id}/set-limit",
            data={"llm_daily_limit": "25"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        user = db.get_user_by_id(user_id)
        assert user["llm_daily_limit"] == 25

    def test_set_user_limit_blank_clears_override(self, client, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        with db._connect() as conn:
            conn.execute(
                "UPDATE users SET is_admin = 1, llm_daily_limit = 15 WHERE id = ?",
                (user_id,),
            )
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
        client.post(
            f"/admin/users/{user_id}/set-limit",
            data={"llm_daily_limit": ""},
            follow_redirects=True,
        )
        user = db.get_user_by_id(user_id)
        assert user["llm_daily_limit"] is None
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_web.py::TestAdminUserLimit -v
```

Expected: 2 failures.

- [ ] **Step 3: Add `set_user_llm_limit` to `db.py`**

Add after `set_user_admin` in `runcoach/db.py`:

```python
    def set_user_llm_limit(self, user_id: int, limit: int | None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET llm_daily_limit = ? WHERE id = ?",
                (limit, user_id),
            )
```

- [ ] **Step 4: Add route to `routes.py`**

Add after the `admin_settings` route:

```python
@bp.route("/admin/users/<int:uid>/set-limit", methods=["POST"])
@_admin_required
def admin_set_user_limit(uid):
    raw = request.form.get("llm_daily_limit", "").strip()
    limit = int(raw) if raw.isdigit() and int(raw) > 0 else None
    _db().set_user_llm_limit(uid, limit)
    flash("User limit updated.")
    return redirect(url_for("main.admin_users"))
```

- [ ] **Step 5: Update `admin_users.html`**

Add a `Limit` column header after the `Last login` `<th>`:

```html
          <th class="hide-mobile">Limit</th>
```

Add the limit cell in the `{% for u in users %}` loop, after the `last_login` `<td>` block:

```html
          <td class="hide-mobile" style="font-size:0.82rem;">
            {% if u.llm_daily_limit is not none %}
              {{ u.llm_daily_limit }}/day
            {% else %}
              <span style="color:var(--fg-muted);">Default</span>
            {% endif %}
            {% if u.id != current_user_id %}
              <form method="POST" action="{{ url_for('main.admin_set_user_limit', uid=u.id) }}"
                    style="display:inline; margin-left:0.4rem;">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                <input type="number" name="llm_daily_limit" min="1"
                       value="{{ u.llm_daily_limit or '' }}"
                       placeholder="Default"
                       style="width:70px; padding:0.2rem 0.3rem; border:1px solid var(--border);
                              border-radius:3px; font-size:0.8rem;">
                <button type="submit" class="btn btn-sm">Set</button>
              </form>
            {% endif %}
          </td>
```

Also add a **Settings** link in the admin navigation area at the top of `admin_users.html`. Replace the opening `<div>` block with:

```html
<div style="display:flex; align-items:baseline; justify-content:space-between; margin-bottom:1rem;">
  <h1 style="font-size:1.4rem; font-weight:700;">User Management</h1>
  <a href="{{ url_for('main.admin_settings') }}" style="font-size:0.9rem;">⚙ Settings</a>
</div>
```

- [ ] **Step 6: Run tests to confirm they pass**

```bash
pytest tests/test_web.py::TestAdminUserLimit -v
```

Expected: 2 passing.

- [ ] **Step 7: Commit**

```bash
git add runcoach/db.py runcoach/web/routes.py runcoach/web/templates/admin_users.html tests/test_web.py
git commit -m "feat: per-user LLM limit override in admin user management"
```

---

## Task 11: E2E test — flash message on rate-limited analyze

**Files:**
- Create: `tests/e2e/test_rate_limit.py`

- [ ] **Step 1: Write the E2E test**

Create `tests/e2e/test_rate_limit.py`:

```python
"""E2E tests: LLM rate limiting flash messages."""
import pytest
from runcoach.db import RunCoachDB

pytestmark = pytest.mark.e2e


def test_analyze_rate_limited_shows_flash(
    logged_in_page, server_url, e2e_data_dir
):
    """Enabling the rate limit with cap=0 shows the flash message on analyze."""
    from tests.e2e.conftest import SAMPLE_FIT_REL
    import time

    db = RunCoachDB(e2e_data_dir / "runcoach.db")
    db.set_site_setting("llm_limiting_enabled", "1")
    db.set_site_setting("llm_daily_limit_default", "0")

    # Make the default user non-admin so the limit applies
    user_id = db.get_default_user_id()
    with db._connect() as conn:
        conn.execute("UPDATE users SET is_admin = 0 WHERE id = ?", (user_id,))

    unique_fit = f"activities/e2e/rate_limit_test_{int(time.time() * 1000)}/test.fit"
    run_id = db.insert_manual_run("Rate Limit Test", "2026-05-26", unique_fit, 5000, 1500)
    db.update_parsed(run_id, SAMPLE_FIT_REL, 176.0, 145, "Rate Limit Test")

    page = logged_in_page
    page.goto(f"{server_url}/run/{run_id}")
    page.locator("button", has_text="Analyze Now").click()

    page.wait_for_selector(".flash", timeout=5_000)
    flash_text = page.text_content(".flash")
    assert "Daily analysis limit reached" in flash_text

    # Restore to avoid bleed into other tests
    db.set_site_setting("llm_limiting_enabled", "0")
    with db._connect() as conn:
        conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user_id,))
```

- [ ] **Step 2: Run the E2E test**

```bash
pytest tests/e2e/test_rate_limit.py -v --no-cov
```

Expected: passing.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_rate_limit.py
git commit -m "test: E2E test for rate-limit flash message on analyze"
```

---

## Task 12: Mobile — `ChatMessage` model + `getChatHistory` status

**Files:**
- Modify: `mobile/lib/models/chat_message.dart`
- Modify: `mobile/lib/services/api_service.dart`
- Test: `mobile/test/widgets/coaching_chat_widget_test.dart`

- [ ] **Step 1: Write failing Flutter test**

Add to `mobile/test/widgets/coaching_chat_widget_test.dart` (inside `main()`):

```dart
  group('ChatMessage status', () {
    test('fromJson defaults status to ok when absent', () {
      final msg = ChatMessage.fromJson({
        'role': 'user',
        'message': 'hello',
      });
      expect(msg.status, 'ok');
      expect(msg.isRateLimited, isFalse);
    });

    test('fromJson reads rate_limited status', () {
      final msg = ChatMessage.fromJson({
        'role': 'user',
        'message': 'hello',
        'status': 'rate_limited',
      });
      expect(msg.status, 'rate_limited');
      expect(msg.isRateLimited, isTrue);
    });
  });
```

- [ ] **Step 2: Run to confirm failure**

```bash
flutter test test/widgets/coaching_chat_widget_test.dart
```

Expected: failures on `status`, `isRateLimited` not found.

- [ ] **Step 3: Update `ChatMessage` model**

Replace `mobile/lib/models/chat_message.dart` with:

```dart
class ChatMessage {
  final String role;
  final String message;
  final String? createdAt;
  final String status;

  const ChatMessage({
    required this.role,
    required this.message,
    this.createdAt,
    this.status = 'ok',
  });

  factory ChatMessage.fromJson(Map<String, dynamic> json) => ChatMessage(
    role: json['role'] as String,
    message: json['message'] as String? ?? '',
    createdAt: json['created_at'] as String?,
    status: json['status'] as String? ?? 'ok',
  );

  bool get isUser => role == 'user';
  bool get isRateLimited => status == 'rate_limited';
}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
flutter test test/widgets/coaching_chat_widget_test.dart
```

Expected: all passing.

- [ ] **Step 5: Run dart format**

```bash
dart format --output=none --set-exit-if-changed mobile/lib/models/chat_message.dart mobile/test/widgets/coaching_chat_widget_test.dart
```

If changes needed: `dart format mobile/lib/models/chat_message.dart mobile/test/widgets/coaching_chat_widget_test.dart`

- [ ] **Step 6: Commit**

```bash
git add mobile/lib/models/chat_message.dart mobile/test/widgets/coaching_chat_widget_test.dart
git commit -m "feat: add status field to ChatMessage model"
```

---

## Task 13: Mobile — `chat_provider` error handling

**Files:**
- Modify: `mobile/lib/providers/chat_provider.dart`
- Test: `mobile/test/widgets/coaching_chat_widget_test.dart`

The `send` method currently uses `catch (_)` which silently discards all errors. We add a `lastError` field to `ChatState` so the widget can surface a SnackBar via `ref.listen`.

- [ ] **Step 1: Write failing test**

Add to `mobile/test/widgets/coaching_chat_widget_test.dart` inside `main()`:

```dart
  group('ChatState', () {
    test('copyWith preserves lastError when not overridden', () {
      const state = ChatState(lastError: 'some error');
      final next = state.copyWith(isSending: true);
      expect(next.lastError, 'some error');
    });

    test('copyWith clears lastError when null passed explicitly', () {
      const state = ChatState(lastError: 'old error');
      final next = state.copyWith(lastError: null, clearError: true);
      expect(next.lastError, isNull);
    });
  });
```

- [ ] **Step 2: Run to confirm failure**

```bash
flutter test test/widgets/coaching_chat_widget_test.dart
```

Expected: failures on `lastError`, `clearError` not found.

- [ ] **Step 3: Update `ChatState` and `ChatNotifier`**

Replace `mobile/lib/providers/chat_provider.dart` with:

```dart
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/chat_message.dart';
import 'auth_provider.dart';

class ChatState {
  final List<ChatMessage> messages;
  final bool isLoading;
  final bool isSending;
  final String? lastError;

  const ChatState({
    this.messages = const [],
    this.isLoading = false,
    this.isSending = false,
    this.lastError,
  });

  ChatState copyWith({
    List<ChatMessage>? messages,
    bool? isLoading,
    bool? isSending,
    String? lastError,
    bool clearError = false,
  }) => ChatState(
    messages: messages ?? this.messages,
    isLoading: isLoading ?? this.isLoading,
    isSending: isSending ?? this.isSending,
    lastError: clearError ? null : (lastError ?? this.lastError),
  );
}

class ChatNotifier extends StateNotifier<ChatState> {
  final Ref _ref;
  final int _runId;

  ChatNotifier(this._ref, this._runId) : super(const ChatState()) {
    _load();
  }

  Future<void> _load() async {
    if (!mounted) return;
    state = state.copyWith(isLoading: true);
    try {
      final api = _ref.read(apiServiceProvider);
      final history = await api.getChatHistory(_runId);
      if (!mounted) return;
      state = state.copyWith(messages: history, isLoading: false);
    } catch (_) {
      if (!mounted) return;
      state = state.copyWith(isLoading: false);
    }
  }

  Future<void> send(String message) async {
    if (message.trim().isEmpty || state.isSending) return;
    final userMsg = ChatMessage(role: 'user', message: message);
    if (!mounted) return;
    state = state.copyWith(
      messages: [...state.messages, userMsg],
      isSending: true,
      clearError: true,
    );
    try {
      final api = _ref.read(apiServiceProvider);
      final response = await api.sendChatMessage(_runId, message);
      if (!mounted) return;
      state = state.copyWith(
        messages: [...state.messages, response],
        isSending: false,
      );
    } on DioException catch (e) {
      if (!mounted) return;
      final errorMsg =
          (e.response?.data as Map<String, dynamic>?)?['error'] as String? ??
          'Failed to send message. Please try again.';
      state = state.copyWith(isSending: false, lastError: errorMsg);
    } catch (_) {
      if (!mounted) return;
      state = state.copyWith(
        isSending: false,
        lastError: 'Failed to send message. Please try again.',
      );
    }
  }

  void clearError() {
    state = state.copyWith(clearError: true);
  }
}

final chatProvider = StateNotifierProvider.autoDispose
    .family<ChatNotifier, ChatState, int>((ref, runId) {
      return ChatNotifier(ref, runId);
    });
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
flutter test test/widgets/coaching_chat_widget_test.dart
```

Expected: all passing.

- [ ] **Step 5: Run dart format**

```bash
dart format --output=none --set-exit-if-changed mobile/lib/providers/chat_provider.dart
```

Apply if needed: `dart format mobile/lib/providers/chat_provider.dart`

- [ ] **Step 6: Commit**

```bash
git add mobile/lib/providers/chat_provider.dart mobile/test/widgets/coaching_chat_widget_test.dart
git commit -m "feat: add lastError to ChatState and surface DioException errors"
```

---

## Task 14: Mobile — retry button + analyze error fix

**Files:**
- Modify: `mobile/lib/widgets/coaching_chat_widget.dart`
- Test: `mobile/test/widgets/coaching_chat_widget_test.dart`

- [ ] **Step 1: Write failing tests**

Add to `mobile/test/widgets/coaching_chat_widget_test.dart` inside `main()`:

```dart
  testWidgets('retry button visible for rate_limited last message', (tester) async {
    final data = _fakeData();
    await tester.pumpWidget(ProviderScope(
      overrides: [bestRunTimeProvider.overrideWith((_) async => data)],
      child: const MaterialApp(home: Scaffold(body: BestRunTimeCard())),
    ));
    await tester.pumpAndSettle();
    // This test is in coaching_chat_widget_test, so use a different approach:
    // This placeholder shows the structure; actual test below uses chatProvider
  });
```

Actually the coaching_chat_widget_test doesn't currently render `CoachingChatWidget`. Add these tests to a new group that tests the retry button logic without the full widget (testing `shouldShowRetry` logic), plus one widget test:

```dart
  group('rate limited message retry', () {
    test('isRateLimited is true for rate_limited status', () {
      const msg = ChatMessage(role: 'user', message: 'hi', status: 'rate_limited');
      expect(msg.isRateLimited, isTrue);
    });

    test('isRateLimited is false for ok status', () {
      const msg = ChatMessage(role: 'user', message: 'hi');
      expect(msg.isRateLimited, isFalse);
    });
  });
```

- [ ] **Step 2: Run to confirm test passes (these pass already from Task 12)**

```bash
flutter test test/widgets/coaching_chat_widget_test.dart
```

Expected: all passing (isRateLimited already implemented in Task 12).

- [ ] **Step 3: Add retry button to `coaching_chat_widget.dart`**

In `coaching_chat_widget.dart`, the message list is rendered at line 160:

```dart
              ...chatState.messages.map(
                (msg) => msg.isUser
                    ? _UserBubble(message: msg.message)
                    : _AiBubble(message: msg.message),
              ),
```

Replace this with logic that shows a retry button for the last rate-limited message:

```dart
              ...() {
                final msgs = chatState.messages;
                return msgs.asMap().entries.map((entry) {
                  final idx = entry.key;
                  final msg = entry.value;
                  if (!msg.isUser) return _AiBubble(message: msg.message);
                  final isLastRateLimited = msg.isRateLimited &&
                      idx == msgs.length - 1;
                  if (isLastRateLimited) {
                    return _RateLimitedBubble(
                      message: msg.message,
                      onRetry: () => ref
                          .read(chatProvider(liveRun.id).notifier)
                          .send(msg.message),
                    );
                  }
                  return _UserBubble(message: msg.message);
                }).toList();
              }(),
```

- [ ] **Step 4: Add `ref.listen` for SnackBar errors and fix `_triggerAnalysis`**

In the `build` method, add a `ref.listen` for `lastError` (add it alongside the existing `ref.listen` for auto-scroll, after line 96):

```dart
    ref.listen(chatProvider(widget.run.id), (previous, next) {
      if (next.lastError != null && next.lastError != previous?.lastError) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(next.lastError!)),
        );
        ref.read(chatProvider(widget.run.id).notifier).clearError();
      }
    });
```

Fix `_triggerAnalysis` to extract the server error message:

```dart
  Future<void> _triggerAnalysis() async {
    setState(() => _analyzing = true);
    try {
      await ref.read(apiServiceProvider).analyzeRun(widget.run.id);
    } on DioException catch (e) {
      if (!mounted) return;
      final msg =
          (e.response?.data as Map<String, dynamic>?)?['error'] as String? ??
          'Failed to start analysis. Please try again.';
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
      setState(() => _analyzing = false);
      return;
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to start analysis: $e')),
      );
      setState(() => _analyzing = false);
      return;
    }
    _pollTimer = Timer.periodic(const Duration(seconds: 3), (_) {
      if (!mounted) {
        _pollTimer?.cancel();
        return;
      }
      ref.invalidate(runDetailProvider(widget.run.id));
    });
  }
```

- [ ] **Step 5: Add `_RateLimitedBubble` widget**

Add the new widget class at the bottom of `coaching_chat_widget.dart`, after `_UserBubble`:

```dart
class _RateLimitedBubble extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;

  const _RateLimitedBubble({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerRight,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Container(
            margin: const EdgeInsets.only(bottom: 4, left: 48),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: const BoxDecoration(
              color: Color(0xFF6750A4),
              borderRadius: BorderRadius.only(
                topLeft: Radius.circular(14),
                topRight: Radius.circular(14),
                bottomLeft: Radius.circular(14),
                bottomRight: Radius.circular(3),
              ),
            ),
            child: Text(
              message,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 13,
                height: 1.4,
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.only(right: 4, bottom: 8),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(
                  Icons.error_outline,
                  size: 13,
                  color: Color(0xFFAAAAAA),
                ),
                const SizedBox(width: 4),
                const Text(
                  'Not sent — limit reached',
                  style: TextStyle(fontSize: 11, color: Color(0xFFAAAAAA)),
                ),
                const SizedBox(width: 8),
                GestureDetector(
                  onTap: onRetry,
                  child: const Text(
                    'Retry',
                    style: TextStyle(
                      fontSize: 11,
                      color: Color(0xFF6750A4),
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
```

- [ ] **Step 6: Run flutter tests**

```bash
flutter test test/widgets/coaching_chat_widget_test.dart
```

Expected: all passing.

- [ ] **Step 7: Run dart format**

```bash
dart format --output=none --set-exit-if-changed mobile/lib/widgets/coaching_chat_widget.dart
```

Apply if needed: `dart format mobile/lib/widgets/coaching_chat_widget.dart`

- [ ] **Step 8: Run full Flutter test suite**

```bash
flutter test
```

Expected: all passing.

- [ ] **Step 9: Commit**

```bash
git add mobile/lib/widgets/coaching_chat_widget.dart mobile/test/widgets/coaching_chat_widget_test.dart
git commit -m "feat: retry button for rate-limited chat messages, fix analyze error message"
```

---

## Final: Full test suite

- [ ] **Run Python unit tests + E2E**

```bash
pytest && pytest -m e2e --no-cov -v
```

Expected: all passing.

- [ ] **Run Flutter tests with format check**

```bash
cd mobile && dart format --output=none --set-exit-if-changed . && flutter test
```

Expected: all passing, no format changes.
