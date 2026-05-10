# Push Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send Android push notifications when a run analysis completes, with a tap that deep-links to the run detail screen and a burnt-orange in-app banner when the app is already open.

**Architecture:** The server sends FCM messages via the Firebase Admin SDK after every successful analysis (pipeline and on-demand). The Flutter app registers its FCM token on startup, deregisters on logout, and handles notifications with a custom overlay banner for foreground delivery and GoRouter deep-linking for background/terminated taps.

**Tech Stack:** Firebase Cloud Messaging, `firebase-admin` Python SDK, `firebase_core` + `firebase_messaging` Flutter packages, SQLite device token storage, existing Flask JWT API.

**Spec:** `docs/superpowers/specs/2026-05-10-push-notifications-design.md`

---

## Prerequisites (manual — do before any code tasks)

1. Go to [Firebase Console](https://console.firebase.google.com/) → **Add project**
2. Click **Add app** → Android → package name `com.runcoach.mobile`
3. Download `google-services.json` → place at `mobile/android/app/google-services.json`
4. Go to **Project Settings → Service accounts → Generate new private key** → download JSON
5. Place service account JSON on the server (e.g. `/srv/runcoach/firebase-service-account.json`)

---

## File Map

**New files:**
- `runcoach/notifications.py` — `send_analysis_notification(run_id, run_name, user_id, db, config)`
- `mobile/lib/services/notification_service.dart` — FCM init, token registration, deregistration, message handlers
- `mobile/lib/widgets/in_app_notification_banner.dart` — burnt-orange animated overlay banner
- `tests/test_notifications.py` — unit tests for notifications module

**Modified files:**
- `runcoach/db.py` — `device_tokens` table + `upsert_device_token`, `get_device_tokens_for_user`, `delete_device_token`
- `runcoach/config.py` — `fcm_service_account_path` field
- `runcoach/pipeline.py` — call `send_analysis_notification` after each `db.update_analyzed()`
- `runcoach/web/api.py` — `POST/DELETE /api/v1/device-tokens`; capture `user_id` before background thread in `analyze_run`; call `send_analysis_notification` in thread
- `pyproject.toml` — `firebase-admin` optional extra
- `.env.example` — document `FCM_SERVICE_ACCOUNT_PATH`
- `mobile/pubspec.yaml` — add `firebase_core`, `firebase_messaging`
- `mobile/android/settings.gradle.kts` — register Google Services Gradle plugin
- `mobile/android/app/build.gradle.kts` — apply Google Services plugin
- `mobile/android/app/src/main/AndroidManifest.xml` — `POST_NOTIFICATIONS` permission
- `mobile/lib/services/api_service.dart` — `registerDeviceToken`, `deleteDeviceToken`
- `mobile/lib/providers/auth_provider.dart` — `notificationServiceProvider`; inject `NotificationService` into `AuthNotifier`
- `mobile/lib/main.dart` — `Firebase.initializeApp()` before `runApp()`
- `mobile/lib/app.dart` — `ConsumerStatefulWidget`, wire up `NotificationService` callbacks

---

## Task 1: DB — device_tokens table and methods

**Files:**
- Modify: `runcoach/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_db.py`:

```python
class TestDeviceTokens:
    def test_upsert_and_retrieve(self, tmp_path):
        from runcoach.auth import hash_password
        db = RunCoachDB(tmp_path / "db" / "runcoach.db")
        db.ensure_default_user("athlete", hash_password("x"))
        user_id = db.get_default_user_id()

        db.upsert_device_token(user_id, "token-abc", "android")
        tokens = db.get_device_tokens_for_user(user_id)
        assert len(tokens) == 1
        assert tokens[0]["token"] == "token-abc"
        assert tokens[0]["platform"] == "android"

    def test_upsert_is_idempotent(self, tmp_path):
        from runcoach.auth import hash_password
        db = RunCoachDB(tmp_path / "db" / "runcoach.db")
        db.ensure_default_user("athlete", hash_password("x"))
        user_id = db.get_default_user_id()

        db.upsert_device_token(user_id, "token-abc", "android")
        db.upsert_device_token(user_id, "token-abc", "android")
        assert len(db.get_device_tokens_for_user(user_id)) == 1

    def test_delete_device_token(self, tmp_path):
        from runcoach.auth import hash_password
        db = RunCoachDB(tmp_path / "db" / "runcoach.db")
        db.ensure_default_user("athlete", hash_password("x"))
        user_id = db.get_default_user_id()

        db.upsert_device_token(user_id, "token-xyz", "android")
        db.delete_device_token("token-xyz")
        assert db.get_device_tokens_for_user(user_id) == []

    def test_get_tokens_empty_for_new_user(self, tmp_path):
        from runcoach.auth import hash_password
        db = RunCoachDB(tmp_path / "db" / "runcoach.db")
        db.ensure_default_user("athlete", hash_password("x"))
        user_id = db.get_default_user_id()
        assert db.get_device_tokens_for_user(user_id) == []
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_db.py::TestDeviceTokens -v
```

Expected: `AttributeError: 'RunCoachDB' object has no attribute 'upsert_device_token'`

- [ ] **Step 3: Add table to SCHEMA_SQL in `runcoach/db.py`**

Find the closing `"""` of `SCHEMA_SQL`. Insert before it (after the `idx_run_chat_run_user` index):

```python
CREATE TABLE IF NOT EXISTS device_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token TEXT NOT NULL UNIQUE,
    platform TEXT NOT NULL DEFAULT 'android',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_device_tokens_user_id ON device_tokens(user_id);
```

- [ ] **Step 4: Add DB methods to `RunCoachDB`**

Append at the end of the class (before the final line):

```python
# ------ device_tokens ------

def upsert_device_token(
    self, user_id: int, token: str, platform: str = "android"
) -> None:
    """Register or update a device FCM token for push notifications."""
    now = _now_iso()
    with self._connect() as conn:
        conn.execute(
            """INSERT INTO device_tokens (user_id, token, platform, created_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(token) DO UPDATE SET
                 user_id = excluded.user_id,
                 platform = excluded.platform""",
            (user_id, token, platform, now),
        )

def get_device_tokens_for_user(self, user_id: int) -> list[dict]:
    """Return all FCM device tokens registered for a user."""
    with self._connect() as conn:
        rows = conn.execute(
            "SELECT * FROM device_tokens WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]

def delete_device_token(self, token: str) -> None:
    """Remove a device token (stale token cleanup or logout)."""
    with self._connect() as conn:
        conn.execute("DELETE FROM device_tokens WHERE token = ?", (token,))
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_db.py::TestDeviceTokens -v
```

Expected: 4 PASS

- [ ] **Step 6: Run full suite**

```bash
pytest --no-cov -q
```

Expected: all existing tests still pass

- [ ] **Step 7: Commit**

```bash
git add runcoach/db.py tests/test_db.py
git commit -m "feat(db): add device_tokens table for FCM push notification registration"
```

---

## Task 2: Config — FCM service account path

**Files:**
- Modify: `runcoach/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Add field to `Config` dataclass**

In `runcoach/config.py`, add after `ors_api_key: str = ""`:

```python
fcm_service_account_path: str = ""
```

- [ ] **Step 2: Parse from env in `Config.from_env()`**

In the `return cls(...)` call, add after `ors_api_key=...`:

```python
fcm_service_account_path=os.environ.get("FCM_SERVICE_ACCOUNT_PATH", ""),
```

- [ ] **Step 3: Document in `.env.example`**

Append to `.env.example`:

```
# Firebase Cloud Messaging — for Android push notifications (optional)
# Path to Firebase Admin SDK service account JSON.
# Download from Firebase Console → Project Settings → Service accounts → Generate new private key
FCM_SERVICE_ACCOUNT_PATH=
```

- [ ] **Step 4: Verify config loads without error**

```bash
python -c "from runcoach.config import Config; c = Config(); print(c.fcm_service_account_path)"
```

Expected: prints empty string (no crash)

- [ ] **Step 5: Commit**

```bash
git add runcoach/config.py .env.example
git commit -m "feat(config): add FCM_SERVICE_ACCOUNT_PATH for push notification credentials"
```

---

## Task 3: Server — notifications module

**Files:**
- Create: `runcoach/notifications.py`
- Create: `tests/test_notifications.py`

- [ ] **Step 1: Add `firebase-admin` to `pyproject.toml`**

In `pyproject.toml`, add a new optional extra after `claude = [...]`:

```toml
fcm = ["firebase-admin>=6.0"]
```

Install it:

```bash
pip install -e ".[fcm]"
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_notifications.py`:

```python
"""Tests for runcoach.notifications — FCM push notification sender."""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from runcoach.config import Config
from runcoach.db import RunCoachDB
from runcoach.auth import hash_password


@pytest.fixture
def db_with_token(tmp_path):
    db = RunCoachDB(tmp_path / "db" / "runcoach.db")
    db.ensure_default_user("athlete", hash_password("x"))
    user_id = db.get_default_user_id()
    db.upsert_device_token(user_id, "device-token-111", "android")
    return db, user_id


@pytest.fixture
def fcm_config(tmp_path):
    fake_sa = tmp_path / "sa.json"
    fake_sa.write_text("{}")
    return Config(
        openai_api_key="test",
        data_dir=tmp_path / "data",
        fcm_service_account_path=str(fake_sa),
    )


class TestSendAnalysisNotification:
    def test_returns_zero_when_fcm_not_configured(self, tmp_path):
        from runcoach.notifications import send_analysis_notification
        db = RunCoachDB(tmp_path / "db" / "runcoach.db")
        db.ensure_default_user("athlete", hash_password("x"))
        user_id = db.get_default_user_id()
        config = Config(data_dir=tmp_path / "data")  # no fcm path

        result = send_analysis_notification(1, "Morning Run", user_id, db, config)
        assert result == 0

    def test_returns_zero_when_no_tokens_registered(self, tmp_path, fcm_config):
        from runcoach.notifications import send_analysis_notification
        db = RunCoachDB(tmp_path / "db" / "runcoach.db")
        db.ensure_default_user("athlete", hash_password("x"))
        user_id = db.get_default_user_id()

        result = send_analysis_notification(42, "Evening Run", user_id, db, fcm_config)
        assert result == 0

    def test_sends_to_registered_token(self, db_with_token, fcm_config):
        from runcoach.notifications import send_analysis_notification
        db, user_id = db_with_token

        with patch("runcoach.notifications._init_firebase_app"), \
             patch("runcoach.notifications.messaging") as mock_messaging:
            mock_messaging.send.return_value = "projects/x/messages/123"
            result = send_analysis_notification(7, "Long Run", user_id, db, fcm_config)

        assert result == 1
        mock_messaging.send.assert_called_once()
        sent_msg = mock_messaging.send.call_args[0][0]
        assert sent_msg.data["run_id"] == "7"
        assert sent_msg.token == "device-token-111"

    def test_removes_stale_token_on_unregistered_error(self, db_with_token, fcm_config):
        from runcoach.notifications import send_analysis_notification
        import firebase_admin.messaging as real_messaging
        db, user_id = db_with_token

        with patch("runcoach.notifications._init_firebase_app"), \
             patch("runcoach.notifications.messaging") as mock_messaging:
            mock_messaging.UnregisteredError = real_messaging.UnregisteredError
            mock_messaging.send.side_effect = real_messaging.UnregisteredError("stale")
            result = send_analysis_notification(7, "Run", user_id, db, fcm_config)

        assert result == 0
        assert db.get_device_tokens_for_user(user_id) == []
```

- [ ] **Step 3: Run to confirm failure**

```bash
pytest tests/test_notifications.py -v
```

Expected: `ModuleNotFoundError: No module named 'runcoach.notifications'`

- [ ] **Step 4: Create `runcoach/notifications.py`**

```python
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

try:
    import firebase_admin
    from firebase_admin import credentials, messaging
    _FIREBASE_AVAILABLE = True
except ImportError:
    _FIREBASE_AVAILABLE = False


def _init_firebase_app(service_account_path: str) -> None:
    """Initialise the Firebase Admin app (idempotent)."""
    if not firebase_admin._apps:
        cred = credentials.Certificate(service_account_path)
        firebase_admin.initialize_app(cred)


def send_analysis_notification(
    run_id: int,
    run_name: str,
    user_id: int,
    db,
    config,
) -> int:
    """
    Send an FCM push notification to all registered devices for the user.

    Returns the number of messages successfully sent. Never raises — a
    notification failure must not affect the caller's control flow.
    """
    if not config.fcm_service_account_path:
        return 0

    if not _FIREBASE_AVAILABLE:
        log.warning(
            "firebase-admin is not installed. "
            "Install it with: pip install -e '.[fcm]'"
        )
        return 0

    tokens = db.get_device_tokens_for_user(user_id)
    if not tokens:
        return 0

    try:
        _init_firebase_app(config.fcm_service_account_path)
    except Exception as e:
        log.error("Failed to initialise Firebase app: %s", e)
        return 0

    sent = 0
    for token_row in tokens:
        token = token_row["token"]
        try:
            message = messaging.Message(
                notification=messaging.Notification(
                    title="New Analysis Ready",
                    body=f"Your coach has analysed: {run_name}",
                ),
                data={"run_id": str(run_id), "type": "analysis_ready"},
                token=token,
            )
            messaging.send(message)
            sent += 1
            log.info("FCM notification sent for run %s", run_id)
        except messaging.UnregisteredError:
            log.info("Removing stale FCM token for user %s", user_id)
            db.delete_device_token(token)
        except Exception as e:
            log.warning("FCM send failed: %s", e)

    return sent
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_notifications.py -v
```

Expected: 4 PASS

- [ ] **Step 6: Run full suite**

```bash
pytest --no-cov -q
```

Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add runcoach/notifications.py tests/test_notifications.py pyproject.toml
git commit -m "feat(notifications): FCM sender with stale token cleanup"
```

---

## Task 4: API — device token registration endpoints

**Files:**
- Modify: `runcoach/web/api.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_api.py`:

```python
class TestDeviceTokenEndpoints:
    def test_register_token(self, client, auth_headers):
        resp = client.post(
            "/api/v1/device-tokens",
            json={"token": "fcm-test-123", "platform": "android"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Device token registered"

    def test_register_token_idempotent(self, client, auth_headers):
        for _ in range(2):
            resp = client.post(
                "/api/v1/device-tokens",
                json={"token": "fcm-idem", "platform": "android"},
                headers=auth_headers,
            )
            assert resp.status_code == 200

    def test_register_token_missing_body(self, client, auth_headers):
        resp = client.post(
            "/api/v1/device-tokens",
            json={"platform": "android"},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_register_token_requires_auth(self, client):
        resp = client.post(
            "/api/v1/device-tokens",
            json={"token": "tok", "platform": "android"},
        )
        assert resp.status_code == 401

    def test_delete_token(self, client, auth_headers):
        client.post(
            "/api/v1/device-tokens",
            json={"token": "fcm-delete-me", "platform": "android"},
            headers=auth_headers,
        )
        resp = client.delete(
            "/api/v1/device-tokens",
            json={"token": "fcm-delete-me"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Device token removed"

    def test_delete_token_missing_body(self, client, auth_headers):
        resp = client.delete(
            "/api/v1/device-tokens",
            json={},
            headers=auth_headers,
        )
        assert resp.status_code == 400
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_api.py::TestDeviceTokenEndpoints -v
```

Expected: 404s (routes don't exist)

- [ ] **Step 3: Add endpoints to `runcoach/web/api.py`**

Append before the final blank line of the file:

```python
# ------ Device tokens (push notifications) ------

@api_bp.route("/device-tokens", methods=["POST"])
@require_auth
def register_device_token():
    """
    Register a device FCM token for push notifications.

    POST /api/v1/device-tokens
    Headers: Authorization: Bearer <access_token>
    Body: {"token": "...", "platform": "android"}
    Response: {"message": "Device token registered"}
    """
    data = request.get_json()
    if not data or not data.get("token"):
        return jsonify({"error": "token is required"}), 400
    token = str(data["token"]).strip()
    if not token:
        return jsonify({"error": "token must not be empty"}), 400
    platform = str(data.get("platform", "android")).strip() or "android"
    db = get_db()
    db.upsert_device_token(request.user_id, token, platform)
    return jsonify({"message": "Device token registered"}), 200


@api_bp.route("/device-tokens", methods=["DELETE"])
@require_auth
def unregister_device_token():
    """
    Remove a device FCM token.

    DELETE /api/v1/device-tokens
    Headers: Authorization: Bearer <access_token>
    Body: {"token": "..."}
    Response: {"message": "Device token removed"}
    """
    data = request.get_json()
    if not data or not data.get("token"):
        return jsonify({"error": "token is required"}), 400
    db = get_db()
    db.delete_device_token(str(data["token"]))
    return jsonify({"message": "Device token removed"}), 200
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_api.py::TestDeviceTokenEndpoints -v
```

Expected: 6 PASS

- [ ] **Step 5: Run full suite**

```bash
pytest --no-cov -q
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add runcoach/web/api.py tests/test_api.py
git commit -m "feat(api): add device token registration endpoints for FCM"
```

---

## Task 5: Pipeline — hook notification after analysis

**Files:**
- Modify: `runcoach/pipeline.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_pipeline.py`:

```python
class TestPipelineNotifications:
    def test_sends_notification_after_successful_analysis(self, tmp_path):
        import json
        from runcoach.auth import hash_password
        config = Config(
            openai_api_key="test-key",
            data_dir=tmp_path / "data",
            timezone="Europe/London",
            llm_auto_analyse=True,
            fcm_service_account_path="/fake/sa.json",
        )
        config.data_dir.mkdir(parents=True, exist_ok=True)
        db = RunCoachDB(config.db_path)
        db.ensure_default_user("athlete", hash_password("x"))
        user_id = db.get_default_user_id()

        with db._connect() as conn:
            conn.execute(
                """INSERT INTO runs
                   (name, date, fit_path, stage, synced_at, parsed_data, user_id)
                   VALUES (?, ?, ?, 'parsed', datetime('now'), ?, ?)""",
                ("Easy Run", "2026-05-10", "fake.fit",
                 json.dumps({"workout_name": "Easy Run", "blocks": []}), user_id),
            )
        run_id = db.get_pending_runs("parsed", user_id=user_id)[0]["id"]

        with patch("runcoach.pipeline.analyze_and_write") as mock_analyze, \
             patch("runcoach.notifications.send_analysis_notification") as mock_notify:
            mock_analyze.return_value = {
                "commentary": "Great run!",
                "prompt_tokens": 100,
                "completion_tokens": 50,
            }
            run_full_pipeline(config, db, user_id=user_id)

        mock_notify.assert_called_once_with(run_id, "Easy Run", user_id, db, config)
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_pipeline.py::TestPipelineNotifications -v
```

Expected: FAIL — `send_analysis_notification` not called

- [ ] **Step 3: Add notification call in `runcoach/pipeline.py`**

Find the analysis loop in `run_full_pipeline`. The section after `db.update_analyzed(...)` and `summary["analyzed"] += 1` should become:

```python
                    db.update_analyzed(
                        run_id=run["id"],
                        md_path=None,
                        commentary=result["commentary"],
                        model_used=config.active_model,
                        prompt_tokens=result.get("prompt_tokens"),
                        completion_tokens=result.get("completion_tokens"),
                    )
                    summary["analyzed"] += 1
                    try:
                        from runcoach.notifications import send_analysis_notification
                        send_analysis_notification(
                            run["id"], run.get("name", "Run"), user_id, db, config
                        )
                    except Exception:
                        log.warning(
                            "Push notification failed for run %s (non-fatal)", run["id"]
                        )
```

- [ ] **Step 4: Run test**

```bash
pytest tests/test_pipeline.py::TestPipelineNotifications -v
```

Expected: PASS

- [ ] **Step 5: Run full suite**

```bash
pytest --no-cov -q
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add runcoach/pipeline.py tests/test_pipeline.py
git commit -m "feat(pipeline): send FCM notification after each successful analysis"
```

---

## Task 6: API — notification in on-demand analyze endpoint

**Files:**
- Modify: `runcoach/web/api.py`
- Modify: `tests/test_api.py`

The `analyze_run` endpoint at `POST /api/v1/runs/<id>/analyze` runs analysis in a background thread. `request.user_id` is unavailable inside the thread (request context is gone), so it must be captured before the thread starts.

- [ ] **Step 1: Write failing test**

Add to `tests/test_api.py`:

```python
class TestAnalyzeRunNotification:
    def test_sends_notification_after_on_demand_analysis(self, client, auth_headers, app):
        import json, time
        db = app.config["db"]
        user_id = db.get_default_user_id()

        with db._connect() as conn:
            conn.execute(
                """INSERT INTO runs
                   (name, date, fit_path, stage, synced_at, parsed_data, user_id)
                   VALUES (?, ?, ?, 'parsed', datetime('now'), ?, ?)""",
                ("Test Run", "2026-05-10", "fake.fit",
                 json.dumps({"workout_name": "Test Run", "blocks": []}), user_id),
            )
        run_id = db.get_pending_runs("parsed", user_id=user_id)[0]["id"]

        with patch("runcoach.web.api.analyze_and_write") as mock_analyze, \
             patch("runcoach.notifications.send_analysis_notification") as mock_notify:
            mock_analyze.return_value = {
                "commentary": "Well done!",
                "prompt_tokens": 50,
                "completion_tokens": 25,
            }
            client.post(f"/api/v1/runs/{run_id}/analyze", headers=auth_headers)
            time.sleep(0.2)  # let background thread finish

        mock_notify.assert_called_once_with(run_id, "Test Run", user_id, db, ANY)
```

Add `from unittest.mock import ANY` to the imports at the top of `tests/test_api.py`.

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_api.py::TestAnalyzeRunNotification -v
```

Expected: FAIL — `send_analysis_notification` not called

- [ ] **Step 3: Update `analyze_run` in `runcoach/web/api.py`**

Find the `analyze_run` route function. Capture `user_id` before the thread, then add the notification call inside `analyze_task`. The full updated function:

```python
@api_bp.route("/runs/<int:run_id>/analyze", methods=["POST"])
@require_auth
def analyze_run(run_id: int):
    """
    Trigger analysis for a specific run.

    POST /api/v1/runs/:id/analyze
    Headers: Authorization: Bearer <access_token>
    Response: {"message": "Analysis started"}
    """
    db = get_db()
    run = db.get_run(run_id, user_id=request.user_id)

    if not run:
        return jsonify({"error": "Run not found"}), 404

    if run["stage"] != "parsed":
        return jsonify({"error": f"Run must be in 'parsed' stage (currently '{run['stage']}')"}), 400

    from runcoach.analyzer import analyze_and_write
    import threading

    app = current_app._get_current_object()
    captured_user_id = request.user_id  # capture before request context ends

    def analyze_task():
        with app.app_context():
            try:
                config: Config = app.config["RUNCOACH_CONFIG"]

                fresh_run = db.get_run(run_id)
                if not fresh_run:
                    log.error(f"Run {run_id} not found during analysis")
                    return

                result = analyze_and_write(fresh_run, config, db=db)
                db.update_analyzed(
                    run_id=fresh_run["id"],
                    md_path=None,
                    commentary=result["commentary"],
                    model_used=config.active_model,
                    prompt_tokens=result.get("prompt_tokens"),
                    completion_tokens=result.get("completion_tokens"),
                )
                log.info(f"Analysis complete for run {run_id}")

                try:
                    from runcoach.notifications import send_analysis_notification
                    send_analysis_notification(
                        fresh_run["id"],
                        fresh_run.get("name", "Run"),
                        captured_user_id,
                        db,
                        config,
                    )
                except Exception:
                    log.warning("Push notification failed for run %s (non-fatal)", run_id)

            except Exception as e:
                log.exception(f"Analysis failed for run {run_id}")
                db.update_error(run_id, f"Analysis error: {e}")

    thread = threading.Thread(target=analyze_task, daemon=True)
    thread.start()

    return jsonify({"message": "Analysis started"}), 202
```

- [ ] **Step 4: Run test**

```bash
pytest tests/test_api.py::TestAnalyzeRunNotification -v
```

Expected: PASS

- [ ] **Step 5: Run full suite**

```bash
pytest --no-cov -q
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add runcoach/web/api.py tests/test_api.py
git commit -m "feat(api): send FCM notification after on-demand run analysis"
```

---

## Task 7: Flutter — Firebase dependencies and Android config

**Files:**
- Modify: `mobile/pubspec.yaml`
- Modify: `mobile/android/settings.gradle.kts`
- Modify: `mobile/android/app/build.gradle.kts`
- Modify: `mobile/android/app/src/main/AndroidManifest.xml`

> `mobile/android/app/google-services.json` must exist before `flutter pub get` will succeed (see Prerequisites).

- [ ] **Step 1: Add packages to `mobile/pubspec.yaml`**

In `dependencies:`, add after `geolocator`:

```yaml
  firebase_core: ^3.13.1
  firebase_messaging: ^15.2.5
```

- [ ] **Step 2: Register Google Services plugin in `mobile/android/settings.gradle.kts`**

Add to the `plugins { }` block:

```kotlin
    id("com.google.gms.google-services") version "4.4.2" apply false
```

Full plugins block:

```kotlin
plugins {
    id("dev.flutter.flutter-plugin-loader") version "1.0.0"
    id("com.android.application") version "8.11.1" apply false
    id("org.jetbrains.kotlin.android") version "2.2.20" apply false
    id("com.google.gms.google-services") version "4.4.2" apply false
}
```

- [ ] **Step 3: Apply plugin in `mobile/android/app/build.gradle.kts`**

Add `id("com.google.gms.google-services")` to the plugins block:

```kotlin
plugins {
    id("com.android.application")
    id("kotlin-android")
    id("com.google.gms.google-services")
    id("dev.flutter.flutter-gradle-plugin")
}
```

- [ ] **Step 4: Add POST_NOTIFICATIONS permission to `AndroidManifest.xml`**

After the existing `uses-permission` lines, add:

```xml
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS"/>
```

- [ ] **Step 5: Install Flutter dependencies**

```bash
cd /home/colm/git/fitparser/mobile && flutter pub get
```

Expected: exits 0

- [ ] **Step 6: Verify dart format clean**

```bash
dart format --output=none --set-exit-if-changed .
```

Expected: exits 0

- [ ] **Step 7: Commit**

```bash
git add mobile/pubspec.yaml mobile/pubspec.lock mobile/android/settings.gradle.kts mobile/android/app/build.gradle.kts mobile/android/app/src/main/AndroidManifest.xml
git commit -m "feat(mobile): add Firebase Core and Messaging for push notifications"
```

---

## Task 8: Flutter — ApiService token methods

**Files:**
- Modify: `mobile/lib/services/api_service.dart`

- [ ] **Step 1: Add methods to `ApiService`**

In `mobile/lib/services/api_service.dart`, add after `postRouteSuggestion` (before the closing `}` of the class):

```dart
  Future<void> registerDeviceToken(String token) async {
    await _dio.post(
      '/device-tokens',
      data: {'token': token, 'platform': 'android'},
    );
  }

  Future<void> deleteDeviceToken(String token) async {
    await _dio.delete(
      '/device-tokens',
      data: {'token': token},
    );
  }
```

- [ ] **Step 2: Dart format**

```bash
cd /home/colm/git/fitparser/mobile && dart format --output=none --set-exit-if-changed lib/services/api_service.dart
```

Expected: exits 0

- [ ] **Step 3: Flutter tests**

```bash
flutter test
```

Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add mobile/lib/services/api_service.dart
git commit -m "feat(mobile): add registerDeviceToken and deleteDeviceToken to ApiService"
```

---

## Task 9: Flutter — NotificationService

**Files:**
- Create: `mobile/lib/services/notification_service.dart`

- [ ] **Step 1: Create `mobile/lib/services/notification_service.dart`**

```dart
import 'package:firebase_messaging/firebase_messaging.dart';
import 'api_service.dart';

/// Top-level handler for background FCM messages. Must be a top-level function.
@pragma('vm:entry-point')
Future<void> _firebaseBackgroundMessageHandler(RemoteMessage message) async {
  // No action needed here — navigation on tap is handled by onMessageOpenedApp
  // when the user taps the notification from the system tray.
}

class NotificationService {
  final ApiService _api;

  /// Called when the user taps a notification (background or terminated).
  /// Receives the run ID to navigate to.
  void Function(int runId)? onNotificationTap;

  /// Called when a notification arrives while the app is in the foreground.
  /// Receives the run ID and run name for the in-app banner.
  void Function(int runId, String runName)? onForegroundMessage;

  NotificationService(this._api);

  Future<void> initialize() async {
    FirebaseMessaging.onBackgroundMessage(_firebaseBackgroundMessageHandler);

    final settings = await FirebaseMessaging.instance.requestPermission(
      alert: true,
      badge: true,
      sound: true,
    );

    if (settings.authorizationStatus == AuthorizationStatus.authorized ||
        settings.authorizationStatus == AuthorizationStatus.provisional) {
      await _registerCurrentToken();
      FirebaseMessaging.instance.onTokenRefresh.listen(_registerToken);
    }

    _setupHandlers();
  }

  /// Deregister the current FCM token on logout. Swallows all errors so
  /// logout always completes even if FCM is unavailable.
  Future<void> deregister() async {
    try {
      final token = await FirebaseMessaging.instance.getToken();
      if (token != null) await _api.deleteDeviceToken(token);
    } catch (_) {}
  }

  Future<void> _registerCurrentToken() async {
    final token = await FirebaseMessaging.instance.getToken();
    if (token != null) await _registerToken(token);
  }

  Future<void> _registerToken(String token) async {
    try {
      await _api.registerDeviceToken(token);
    } catch (_) {}
  }

  void _setupHandlers() {
    // Foreground: fire callback for in-app banner
    FirebaseMessaging.onMessage.listen((message) {
      final runIdStr = message.data['run_id'];
      if (runIdStr == null) return;
      final runId = int.tryParse(runIdStr);
      if (runId == null) return;
      final runName = message.notification?.body ?? 'New run';
      onForegroundMessage?.call(runId, runName);
    });

    // Background: user tapped notification in system tray
    FirebaseMessaging.onMessageOpenedApp.listen(_handleTap);

    // Terminated: app launched by tapping notification
    FirebaseMessaging.instance.getInitialMessage().then((message) {
      if (message != null) _handleTap(message);
    });
  }

  void _handleTap(RemoteMessage message) {
    final runIdStr = message.data['run_id'];
    if (runIdStr == null) return;
    final runId = int.tryParse(runIdStr);
    if (runId != null) onNotificationTap?.call(runId);
  }
}
```

- [ ] **Step 2: Dart format**

```bash
cd /home/colm/git/fitparser/mobile && dart format --output=none --set-exit-if-changed lib/services/notification_service.dart
```

Expected: exits 0

- [ ] **Step 3: Flutter tests**

```bash
flutter test
```

Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add mobile/lib/services/notification_service.dart
git commit -m "feat(mobile): add NotificationService with FCM token lifecycle and message handlers"
```

---

## Task 10: Flutter — foreground in-app banner widget

**Files:**
- Create: `mobile/lib/widgets/in_app_notification_banner.dart`

- [ ] **Step 1: Create `mobile/lib/widgets/in_app_notification_banner.dart`**

```dart
import 'package:flutter/material.dart';

/// Burnt-orange banner that slides down from the top of the screen when a
/// new analysis notification arrives while the app is in the foreground.
class InAppNotificationBanner extends StatefulWidget {
  final String runName;
  final VoidCallback onTap;
  final VoidCallback onDismiss;

  const InAppNotificationBanner({
    super.key,
    required this.runName,
    required this.onTap,
    required this.onDismiss,
  });

  @override
  State<InAppNotificationBanner> createState() =>
      _InAppNotificationBannerState();
}

class _InAppNotificationBannerState extends State<InAppNotificationBanner>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<Offset> _slide;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 300),
    );
    _slide = Tween<Offset>(
      begin: const Offset(0, -1),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeOut));

    _controller.forward();
    Future.delayed(const Duration(seconds: 4), () {
      if (mounted) _dismiss();
    });
  }

  void _dismiss() {
    _controller.reverse().then((_) => widget.onDismiss());
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SlideTransition(
      position: _slide,
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
          child: Material(
            color: Colors.transparent,
            child: GestureDetector(
              onTap: () {
                _dismiss();
                widget.onTap();
              },
              child: Container(
                decoration: BoxDecoration(
                  color: const Color(0xFFC45C1A),
                  borderRadius: BorderRadius.circular(10),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withOpacity(0.3),
                      blurRadius: 12,
                      offset: const Offset(0, 4),
                    ),
                  ],
                ),
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 12,
                ),
                child: Row(
                  children: [
                    Container(
                      width: 34,
                      height: 34,
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.2),
                        shape: BoxShape.circle,
                      ),
                      child: const Center(
                        child: Text('🏃', style: TextStyle(fontSize: 16)),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Text(
                            'New Analysis Ready',
                            style: TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w700,
                              fontSize: 14,
                            ),
                          ),
                          Text(
                            '${widget.runName} · Tap to view',
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ),
                    ),
                    GestureDetector(
                      onTap: _dismiss,
                      child: const Icon(
                        Icons.close,
                        color: Colors.white54,
                        size: 20,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Inserts a [InAppNotificationBanner] into [overlay] and manages its lifecycle.
/// The returned [OverlayEntry] is removed automatically on dismiss or tap.
OverlayEntry showInAppNotificationBanner({
  required OverlayState overlay,
  required String runName,
  required VoidCallback onTap,
}) {
  late OverlayEntry entry;
  entry = OverlayEntry(
    builder: (_) => Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: InAppNotificationBanner(
        runName: runName,
        onTap: () {
          entry.remove();
          onTap();
        },
        onDismiss: entry.remove,
      ),
    ),
  );
  overlay.insert(entry);
  return entry;
}
```

- [ ] **Step 2: Dart format**

```bash
cd /home/colm/git/fitparser/mobile && dart format --output=none --set-exit-if-changed lib/widgets/in_app_notification_banner.dart
```

Expected: exits 0

- [ ] **Step 3: Flutter tests**

```bash
flutter test
```

Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add mobile/lib/widgets/in_app_notification_banner.dart
git commit -m "feat(mobile): burnt-orange in-app notification banner with slide animation"
```

---

## Task 11: Flutter — inject NotificationService into AuthNotifier

**Files:**
- Modify: `mobile/lib/providers/auth_provider.dart`

`AuthNotifier` needs to call `notifService.deregister()` on logout, so `NotificationService` is added as a constructor dependency. A `notificationServiceProvider` is also added here.

- [ ] **Step 1: Update `mobile/lib/providers/auth_provider.dart`**

Replace the entire file with:

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../services/api_service.dart';
import '../services/notification_service.dart';
import '../services/secure_storage_service.dart';

final secureStorageProvider = Provider<SecureStorageService>(
  (ref) => SecureStorageService(),
);

const _defaultServerUrl = String.fromEnvironment(
  'BASE_URL',
  defaultValue: 'https://runcoach.linehan.me.uk/api/v1',
);

class ServerUrlNotifier extends AsyncNotifier<String> {
  @override
  Future<String> build() async {
    final storage = ref.read(secureStorageProvider);
    return await storage.getServerUrl() ?? _defaultServerUrl;
  }

  Future<void> setUrl(String url) async {
    final trimmed = url.trimRight().replaceAll(RegExp(r'/$'), '');
    await ref.read(secureStorageProvider).saveServerUrl(trimmed);
    state = AsyncData(trimmed);
  }
}

final serverUrlProvider = AsyncNotifierProvider<ServerUrlNotifier, String>(
  ServerUrlNotifier.new,
);

final apiServiceProvider = Provider<ApiService>((ref) {
  final urlAsync = ref.watch(serverUrlProvider);
  final url = urlAsync.valueOrNull ?? _defaultServerUrl;
  return ApiService(ref.read(secureStorageProvider), baseUrl: url);
});

final notificationServiceProvider = Provider<NotificationService>((ref) {
  return NotificationService(ref.read(apiServiceProvider));
});

enum AuthStatus { unknown, authenticated, unauthenticated }

class AuthNotifier extends StateNotifier<AuthStatus> {
  final SecureStorageService _storage;
  final ApiService _api;
  final NotificationService _notifService;

  AuthNotifier(this._storage, this._api, this._notifService)
      : super(AuthStatus.unknown) {
    _checkAuth();
  }

  Future<void> _checkAuth() async {
    final token = await _storage.getAccessToken();
    state =
        token != null ? AuthStatus.authenticated : AuthStatus.unauthenticated;
  }

  void revalidate() => _checkAuth();

  Future<void> login(String username, String password) async {
    final tokens = await _api.login(username, password);
    await _storage.saveTokens(
      access: tokens['access_token']!,
      refresh: tokens['refresh_token']!,
    );
    state = AuthStatus.authenticated;
  }

  Future<void> logout() async {
    await _notifService.deregister();
    await _api.logout();
    await _storage.clearTokens();
    state = AuthStatus.unauthenticated;
  }
}

final authProvider =
    StateNotifierProvider<AuthNotifier, AuthStatus>((ref) {
  final api = ref.read(apiServiceProvider);
  final notif = ref.read(notificationServiceProvider);
  final notifier =
      AuthNotifier(ref.read(secureStorageProvider), api, notif);
  api.onAuthFailed = notifier.revalidate;
  return notifier;
});

final athleteProfileProvider = FutureProvider<Map<String, dynamic>>((
  ref,
) async {
  return ref.watch(apiServiceProvider).getAthleteProfile();
});
```

- [ ] **Step 2: Dart format**

```bash
cd /home/colm/git/fitparser/mobile && dart format --output=none --set-exit-if-changed lib/providers/auth_provider.dart
```

Expected: exits 0

- [ ] **Step 3: Flutter tests**

```bash
flutter test
```

Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add mobile/lib/providers/auth_provider.dart
git commit -m "feat(mobile): inject NotificationService into AuthNotifier, deregister FCM token on logout"
```

---

## Task 12: Flutter — wire up main.dart and app.dart

**Files:**
- Modify: `mobile/lib/main.dart`
- Modify: `mobile/lib/app.dart`

- [ ] **Step 1: Update `mobile/lib/main.dart`**

Replace entire file:

```dart
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'app.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp();
  runApp(const ProviderScope(child: RunCoachApp()));
}
```

- [ ] **Step 2: Update `mobile/lib/app.dart`**

Replace entire file:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'providers/auth_provider.dart';
import 'screens/login_screen.dart';
import 'screens/home_screen.dart';
import 'screens/activities_screen.dart';
import 'screens/profile_screen.dart';
import 'screens/run_detail_screen.dart';
import 'screens/workout_detail_screen.dart';
import 'models/planned_workout.dart';
import 'widgets/in_app_notification_banner.dart';

final _rootNavKey = GlobalKey<NavigatorState>();
final _shellNavKey = GlobalKey<NavigatorState>();

class _RouterNotifier extends ChangeNotifier {
  AuthStatus _authStatus = AuthStatus.unknown;
  AuthStatus get authStatus => _authStatus;
  void update(AuthStatus status) {
    _authStatus = status;
    notifyListeners();
  }
}

final _routerNotifierProvider = Provider<_RouterNotifier>((ref) {
  final notifier = _RouterNotifier();
  ref.listen<AuthStatus>(authProvider, (_, next) => notifier.update(next));
  ref.onDispose(notifier.dispose);
  return notifier;
});

final routerProvider = Provider<GoRouter>((ref) {
  final notifier = ref.watch(_routerNotifierProvider);

  return GoRouter(
    navigatorKey: _rootNavKey,
    refreshListenable: notifier,
    redirect: (context, state) {
      final isLoginRoute = state.matchedLocation == '/login';
      final authStatus = notifier.authStatus;
      if (authStatus == AuthStatus.unauthenticated && !isLoginRoute)
        return '/login';
      if (authStatus == AuthStatus.authenticated && isLoginRoute)
        return '/home';
      return null;
    },
    routes: [
      GoRoute(path: '/login', builder: (_, __) => const LoginScreen()),
      GoRoute(
        path: '/workout-detail',
        parentNavigatorKey: _rootNavKey,
        builder: (context, state) =>
            WorkoutDetailScreen(workout: state.extra as PlannedWorkout),
      ),
      ShellRoute(
        navigatorKey: _shellNavKey,
        builder: (context, state, child) => ScaffoldWithNavBar(child: child),
        routes: [
          GoRoute(
            path: '/home',
            builder: (_, __) => const HomeScreen(),
            routes: [
              GoRoute(
                path: 'run/:id',
                parentNavigatorKey: _rootNavKey,
                builder: (_, state) => RunDetailScreen(
                  runId: int.parse(state.pathParameters['id']!),
                ),
              ),
            ],
          ),
          GoRoute(
            path: '/activities',
            builder: (_, __) => const ActivitiesScreen(),
            routes: [
              GoRoute(
                path: 'run/:id',
                parentNavigatorKey: _rootNavKey,
                builder: (_, state) => RunDetailScreen(
                  runId: int.parse(state.pathParameters['id']!),
                ),
              ),
            ],
          ),
          GoRoute(path: '/profile', builder: (_, __) => const ProfileScreen()),
        ],
      ),
    ],
    initialLocation: '/home',
  );
});

class ScaffoldWithNavBar extends ConsumerWidget {
  final Widget child;
  const ScaffoldWithNavBar({required this.child, super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final location = GoRouterState.of(context).matchedLocation;
    final index = switch (location) {
      String l when l.startsWith('/home') => 0,
      String l when l.startsWith('/activities') => 1,
      String l when l.startsWith('/profile') => 2,
      _ => 0,
    };

    return Scaffold(
      body: child,
      bottomNavigationBar: NavigationBar(
        selectedIndex: index,
        onDestinationSelected: (i) {
          switch (i) {
            case 0:
              context.go('/home');
            case 1:
              context.go('/activities');
            case 2:
              context.go('/profile');
          }
        },
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home),
            label: 'Home',
          ),
          NavigationDestination(
            icon: Icon(Icons.list_outlined),
            selectedIcon: Icon(Icons.list),
            label: 'Activities',
          ),
          NavigationDestination(
            icon: Icon(Icons.person_outline),
            selectedIcon: Icon(Icons.person),
            label: 'Profile',
          ),
        ],
      ),
    );
  }
}

class RunCoachApp extends ConsumerStatefulWidget {
  const RunCoachApp({super.key});

  @override
  ConsumerState<RunCoachApp> createState() => _RunCoachAppState();
}

class _RunCoachAppState extends ConsumerState<RunCoachApp> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final notifService = ref.read(notificationServiceProvider);

      notifService.onNotificationTap = (runId) {
        _rootNavKey.currentContext?.go('/home/run/$runId');
      };

      notifService.onForegroundMessage = (runId, runName) {
        final ctx = _rootNavKey.currentContext;
        if (ctx == null) return;
        final overlay = Overlay.of(ctx);
        showInAppNotificationBanner(
          overlay: overlay,
          runName: runName,
          onTap: () => ctx.go('/home/run/$runId'),
        );
      };

      notifService.initialize();
    });
  }

  @override
  Widget build(BuildContext context) {
    final router = ref.watch(routerProvider);
    return MaterialApp.router(
      title: 'RunCoach',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF6750A4),
          brightness: Brightness.light,
        ).copyWith(surface: Colors.white, onSurface: const Color(0xFF1A1A1A)),
        scaffoldBackgroundColor: const Color(0xFFF5F5F5),
        cardTheme: const CardThemeData(
          color: Colors.white,
          elevation: 1,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.all(Radius.circular(12)),
          ),
        ),
        useMaterial3: true,
      ),
      routerConfig: router,
    );
  }
}
```

- [ ] **Step 3: Dart format**

```bash
cd /home/colm/git/fitparser/mobile && dart format --output=none --set-exit-if-changed .
```

Expected: exits 0

- [ ] **Step 4: Flutter tests**

```bash
flutter test
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add mobile/lib/main.dart mobile/lib/app.dart
git commit -m "feat(mobile): initialise Firebase and wire up NotificationService with banner and deep-link"
```

---

## Task 13: Build, deploy, and verify

- [ ] **Step 1: Configure server with FCM credentials**

On the production server, add to `/srv/runcoach/.env`:

```
FCM_SERVICE_ACCOUNT_PATH=/srv/runcoach/firebase-service-account.json
```

Copy the service account JSON to `/srv/runcoach/firebase-service-account.json`. If using Docker, mount it read-only in `docker-compose.yml`:

```yaml
volumes:
  - ./firebase-service-account.json:/srv/runcoach/firebase-service-account.json:ro
```

Redeploy:

```bash
cd /srv/runcoach && docker compose pull && docker compose up -d
```

- [ ] **Step 2: Run full Python test suite**

```bash
cd /home/colm/git/fitparser
pytest && pytest -m e2e --no-cov -v
```

Expected: all pass

- [ ] **Step 3: Build release APK**

```bash
cd /home/colm/git/fitparser/mobile && flutter build apk --release
```

Expected: `✓ Built build/app/outputs/flutter-apk/app-release.apk`

- [ ] **Step 4: Install on phone**

```bash
adb connect 192.168.1.91:45015
adb -s 192.168.1.91:45015 install -r build/app/outputs/flutter-apk/app-release.apk
```

Expected: `Success`

- [ ] **Step 5: Manual E2E verification**

1. Open RunCoach on phone → accept notification permission when prompted
2. Check server logs: `docker logs runcoach` — confirm FCM token registered (`device_tokens` row inserted)
3. Trigger a pipeline run (Sync Now, or wait for Strava webhook)
4. **Background test**: put app in background → finish a run → verify notification appears in system tray with title "New Analysis Ready" → tap → app opens at correct run detail screen
5. **Foreground test**: keep app open → trigger on-demand analysis from a parsed run → verify burnt-orange banner slides in from top → tap → navigates to run detail → auto-dismisses after 4 seconds if not tapped
6. **Logout test**: log out → check server logs that DELETE /api/v1/device-tokens was called

---

## Self-review

**Spec coverage:**
- ✅ FCM delivery → Tasks 3, 7
- ✅ Token registered on startup → Task 9 (`initialize()`)
- ✅ Token deregistered on logout → Tasks 9 (`deregister()`), 11 (`AuthNotifier`)
- ✅ `POST/DELETE /api/v1/device-tokens` → Task 4
- ✅ Pipeline hook after analysis → Task 5
- ✅ On-demand API hook after analysis → Task 6
- ✅ `user_id` captured before background thread → Task 6
- ✅ Burnt-orange foreground banner → Task 10
- ✅ Deep-link on background/terminated tap → Task 12 (`onNotificationTap`)
- ✅ Stale token cleanup (`UnregisteredError`) → Task 3
- ✅ FCM opt-in (no-op if not configured) → Task 3

**Type/name consistency:**
- `send_analysis_notification(run_id, run_name, user_id, db, config)` — Tasks 3, 5, 6 ✅
- `upsert_device_token / get_device_tokens_for_user / delete_device_token` — Tasks 1, 3, 4 ✅
- `registerDeviceToken / deleteDeviceToken` — Tasks 8, 9, 11 ✅
- `notificationServiceProvider` — Tasks 11, 12 ✅
- `onForegroundMessage / onNotificationTap` — Tasks 9, 12 ✅
- `showInAppNotificationBanner` — Tasks 10, 12 ✅
- `InAppNotificationBanner` — Tasks 10, 12 ✅

**No placeholders:** All steps contain complete code or exact commands.
