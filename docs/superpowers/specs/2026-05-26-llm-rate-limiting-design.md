# LLM Rate Limiting — Design Spec

**Issue:** #37  
**Date:** 2026-05-26  
**Status:** Approved

---

## Overview

Each non-admin user has a configurable daily cap on LLM calls. Both run analyses and chat messages share a single counter. Admins are always exempt. Hitting the cap returns a clear message with the exact UTC reset time. All settings are runtime-editable by admins without a server restart.

---

## Data Model

### New table: `site_settings`

Key-value store for runtime-editable admin configuration.

```sql
CREATE TABLE IF NOT EXISTS site_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

Seeded on first startup with two rows:

| key | default value | meaning |
|---|---|---|
| `llm_limiting_enabled` | `'0'` | `'1'` enables limiting site-wide |
| `llm_daily_limit_default` | `'10'` | Default calls/day for all non-admin users |

### New table: `llm_usage`

One row per user per UTC calendar day. History is preserved indefinitely, enabling future analytics or adaptive cap evaluation.

```sql
CREATE TABLE IF NOT EXISTS llm_usage (
    user_id    INTEGER NOT NULL REFERENCES users(id),
    date       TEXT NOT NULL,   -- YYYY-MM-DD UTC
    call_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, date)
);
```

### Migration: `users` table

```sql
ALTER TABLE users ADD COLUMN llm_daily_limit INTEGER;
-- NULL = use global default; set by admin for per-user overrides
```

---

## New module: `runcoach/rate_limiter.py`

Single public function:

```python
def check_and_consume(db, user_id: int) -> tuple[bool, str | None]:
    """
    Returns (True, None) if the call is allowed and the counter has been incremented.
    Returns (False, reset_message) if the daily cap is reached.
    reset_message example: "Daily analysis limit reached. Resets at 00:00 UTC (in 3h 42m)."
    """
```

### Decision logic

1. If `site_settings.llm_limiting_enabled != '1'` → allow (short-circuit, no DB write)
2. If `users.is_admin == 1` → allow (short-circuit, no DB write)
3. Resolve effective limit: `users.llm_daily_limit` if not NULL, else `int(site_settings.llm_daily_limit_default)`
4. Compute today's date as `datetime.utcnow().strftime("%Y-%m-%d")`
5. Call `db.check_and_increment_llm_usage(user_id, today, limit)` inside a transaction
6. If incremented → allow
7. If denied → compute time until next midnight UTC, return formatted reset message

### Reset message format

```
Daily analysis limit reached. Resets at 00:00 UTC (in {H}h {M}m).
```

---

## DB methods (`runcoach/db.py`)

| Method | Signature | Notes |
|---|---|---|
| `get_site_setting` | `(key, default=None) → str \| None` | SELECT from `site_settings` |
| `set_site_setting` | `(key, value: str) → None` | INSERT OR REPLACE into `site_settings` |
| `get_user_by_id` | `(user_id) → dict \| None` | Reuse existing method if present, otherwise add |
| `check_and_increment_llm_usage` | `(user_id, today, limit) → tuple[bool, int]` | Atomic transaction; returns `(was_incremented, new_count)` |

### `check_and_increment_llm_usage` detail

Runs inside a single SQLite transaction:

1. `SELECT call_count FROM llm_usage WHERE user_id=? AND date=?`
2. `current = row.call_count if row else 0`
3. If `current < limit`:
   - `INSERT INTO llm_usage ... ON CONFLICT DO UPDATE SET call_count = call_count + 1`
   - Return `(True, current + 1)`
4. Else: return `(False, current)`

---

## Integration points

### `analyze_run_route` (`routes.py`)

Check **before** spawning the background analysis thread.

```python
allowed, msg = check_and_consume(db, user_id)
if not allowed:
    flash(msg)
    return redirect(url_for("main.run_detail", run_id=run_id))
```

### `run_chat` (`routes.py`)

Check **before** calling `_dispatch_llm()`.

```python
allowed, msg = check_and_consume(db, user_id)
if not allowed:
    return jsonify({"error": msg}), 429
```

### `pipeline.py`

Check **before** each `analyze_and_write()` call in the loop. On deny, log a warning and `continue`; the run stays in `"parsed"` stage and will be retried when the quota resets.

```python
allowed, msg = check_and_consume(db, user_id)
if not allowed:
    log.warning("LLM quota exceeded for user %s, skipping run %s", user_id, run["id"])
    continue
```

---

## Admin UI

### Global settings

New section on the admin page (or `/admin/settings` if the existing page is crowded). Two controls:

- **Enable/disable toggle** — checkbox bound to `llm_limiting_enabled`
- **Default daily limit** — number input bound to `llm_daily_limit_default`

Submitted via POST; handler calls `set_site_setting` for both keys.

### Per-user override

New **Limit** column in the user management table. Displays "Default" when `llm_daily_limit IS NULL`. Accepts an integer or blank (clears the override). Saved to `users.llm_daily_limit`.

---

## Window definition

Calendar day resetting at **midnight UTC**. The counter for a user is the `llm_usage.call_count` row for today's UTC date string. There is no rolling window.

## Admin exemption

`is_admin == 1` bypasses all checks. No `llm_usage` row is written for admin calls.

## Limiting disabled (default)

`llm_limiting_enabled = '0'` by default. The feature is fully inert until an admin enables it — no behaviour change on existing deployments.

---

## Tests

### `tests/test_rate_limiter.py` (new)

- Allow when `llm_limiting_enabled = '0'`
- Allow admin user regardless of count
- Allow user under limit, verify counter incremented
- Deny user at limit, verify reset message format
- Deny user over limit (idempotent — no double-increment)
- Pipeline skip: returns `(False, msg)` correctly at limit

### `tests/test_db.py` additions

- `get_site_setting` returns default when key absent
- `set_site_setting` upserts correctly
- `check_and_increment_llm_usage` increments on first call (inserts row)
- `check_and_increment_llm_usage` increments on subsequent calls
- `check_and_increment_llm_usage` denies at limit without incrementing

### `tests/test_web.py` additions

- `analyze_run_route`: 429-equivalent redirect + flash when rate-limited
- `analyze_run_route`: proceeds normally when under limit

### `tests/test_api.py` additions

- `run_chat`: returns `{"error": "..."}` with HTTP 429 when rate-limited
- `run_chat`: succeeds normally when under limit

### E2E (`tests/e2e/`)

- Flash message visible on run detail page after rate-limited analyze attempt

---

## Mobile considerations

### `run_chat` schema: `status` column

```sql
ALTER TABLE run_chat ADD COLUMN status TEXT NOT NULL DEFAULT 'ok';
```

Values: `'ok'` | `'rate_limited'`. All existing rows default to `'ok'`.

### Persisting rate-limited messages

When `run_chat` returns 429, the server saves the user message with `status='rate_limited'` before returning the error response. No assistant reply is added. This preserves the message in history so the user does not have to retype it.

The chat history API response includes the `status` field for each message.

### Retry button (mobile)

The mobile chat UI shows a **Retry** button on any `rate_limited` user message that has no subsequent assistant reply (i.e. it is the last unanswered message in the thread). The button is always tappable — no client-side quota calculation. When tapped it re-sends the message text through the normal send flow:

- **Success:** assistant reply is appended; the original `rate_limited` row is not modified, but the retry button disappears because the message is no longer the last unanswered one.
- **Still rate-limited:** server returns 429 again; the error message is re-shown via SnackBar.

### `sendChatMessage` — silent error swallow

**File:** `mobile/lib/providers/chat_provider.dart`

Currently uses `catch (_)` which silently discards all errors. When the server returns 429 the user's message appears in the chat with no reply and no explanation.

**Fix:** Catch `DioException`, extract `response.data['error']` from the response body, and surface it as a SnackBar. The `rate_limited` message loaded from history will show the retry button on next render.

### "Analyze Now" button — raw exception in SnackBar

**File:** `mobile/lib/widgets/coaching_chat_widget.dart`

The `_triggerAnalysis()` method catches exceptions and shows `'Failed to start analysis: $e'` — `$e` is the raw `DioException`, not the server's error message.

**Fix:** On `DioException`, check `e.response?.data['error']` and use that string in the SnackBar if present. Falls back to the generic message for non-server errors.

### Copy-paste in chat input

Flutter's `TextField` supports copy-paste natively on Android. Verify manually after install; no code change expected.

### Flutter tests

- `chat_provider`: 429 response surfaces the error message via SnackBar rather than silently swallowing
- `coaching_chat_widget`: 429 on analyze shows rate-limit message in SnackBar, not raw exception
- `coaching_chat_widget`: `rate_limited` message in history shows retry button; subsequent assistant reply hides it
