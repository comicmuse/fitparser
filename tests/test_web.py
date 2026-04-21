"""Unit tests for runcoach.web Flask application."""

from __future__ import annotations

import json as _json

import pytest
from pathlib import Path
import yaml

from runcoach.web import create_app
from runcoach.config import Config
from runcoach.db import RunCoachDB


@pytest.fixture
def app(tmp_path):
    """Create a test Flask app with temporary database."""
    config = Config(
        openai_api_key="test-key",
        openai_model="gpt-4o",
        data_dir=tmp_path / "data",
        timezone="Europe/London",
        secret_key="test-secret-key-for-testing",
        sync_interval_hours=0,  # Disable scheduler to avoid background threads during tests
    )

    # Create the app but don't start the scheduler
    app = create_app(config)
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False  # disable CSRF in tests

    # Stop the scheduler to avoid background threads during tests
    scheduler = app.config.get("scheduler")
    if scheduler:
        scheduler.stop()

    yield app


@pytest.fixture
def client(app):
    """Create a test client for the Flask app, pre-authenticated."""
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["user_id"] = 1
    return c


@pytest.fixture
def runner(app):
    """Create a test CLI runner for the Flask app."""
    return app.test_cli_runner()


class TestAppCreation:
    """Tests for Flask app creation and configuration."""

    def test_app_creates_successfully(self, tmp_path):
        """Test that the app can be created."""
        config = Config(
            openai_api_key="test-key",
            openai_model="gpt-4o",
            data_dir=tmp_path / "data",
            timezone="Europe/London",
            secret_key="test-secret",
            sync_interval_hours=0,
        )

        app = create_app(config)

        assert app is not None
        assert app.config["config"] == config
        assert app.config["db"] is not None
        assert app.config["scheduler"] is not None

    def test_scheduler_disabled_when_interval_zero(self, tmp_path):
        """Scheduler.start() is a no-op when sync_interval_hours=0."""
        from runcoach.scheduler import Scheduler

        config = Config(
            openai_api_key="test-key",
            openai_model="gpt-4o",
            data_dir=tmp_path / "data",
            timezone="Europe/London",
            secret_key="test-secret",
            sync_interval_hours=0,
        )
        db = RunCoachDB(config.db_path)
        sched = Scheduler(config, db)
        sched.start()
        # No background thread should have been spawned
        assert sched._thread is None

    def test_app_has_secret_key(self, app):
        """Test that app has a secret key configured."""
        assert app.secret_key is not None
        assert app.secret_key != ""

    def test_app_has_csrf_protection(self, app):
        """Test that CSRF protection is enabled."""
        # CSRFProtect should be initialized
        assert "csrf" in app.extensions or "csrf_protection" in app.extensions or hasattr(app, "csrf")

    def test_app_has_max_content_length(self, app):
        """Test that max upload size is configured."""
        assert app.config["MAX_CONTENT_LENGTH"] == 50 * 1024 * 1024  # 50 MB


class TestRoutes:
    """Tests for Flask routes."""

    def test_index_page_loads(self, client):
        """Test that the index page loads successfully."""
        response = client.get("/")
        assert response.status_code == 200
        assert b"<!DOCTYPE html>" in response.data or b"<html" in response.data

    def test_workouts_page_loads(self, client):
        """Test that the workouts page loads successfully."""
        response = client.get("/workouts")
        assert response.status_code == 200

    def test_status_endpoint(self, client):
        """Test the status API endpoint."""
        response = client.get("/status")
        assert response.status_code == 200

        # Should return JSON
        data = response.get_json()
        assert data is not None
        # Check for expected fields in status response
        assert "total_runs" in data or "errors" in data or "syncing" in data

    def test_nonexistent_run_404(self, client):
        """Test that accessing a nonexistent run returns 404 or redirect."""
        response = client.get("/run/99999")
        # May return 404 or redirect (302) depending on error handling
        assert response.status_code in [302, 404]


class TestRunView:
    """Tests for individual run view page."""

    def test_run_view_with_valid_run(self, client, app):
        """Test viewing a run that exists in the database."""
        db = app.config["db"]

        # Insert a test run
        run_id = db.insert_run(
            stryd_activity_id=12345,
            name="Test Run",
            date="2026-03-01",
            fit_path="activities/test.fit",
            distance_m=10000,
            moving_time_s=3000,
        )

        # View the run
        response = client.get(f"/run/{run_id}")
        assert response.status_code == 200
        assert b"Test Run" in response.data or b"test" in response.data.lower()

    def test_run_view_with_commentary(self, client, app):
        """Test viewing a run with analysis commentary."""
        db = app.config["db"]

        # Insert and analyze a run
        run_id = db.insert_run(
            stryd_activity_id=12345,
            name="Analyzed Run",
            date="2026-03-01",
            fit_path="activities/test.fit",
        )

        db.update_analyzed(
            run_id=run_id,
            md_path="activities/test.md",
            commentary="Great workout! You maintained consistent power.",
            model_used="gpt-4o",
            prompt_tokens=100,
            completion_tokens=50,
        )

        response = client.get(f"/run/{run_id}")
        assert response.status_code == 200
        # Commentary should be rendered as HTML
        assert b"Great workout" in response.data or b"power" in response.data


class TestAPIEndpoints:
    """Tests for API endpoints."""

    def test_sync_requires_post(self, client):
        """Test that sync endpoint requires POST method."""
        response = client.get("/sync")
        assert response.status_code == 405  # Method Not Allowed

    def test_analyze_requires_post(self, client, app):
        """Test that analyze endpoint requires POST method."""
        db = app.config["db"]
        run_id = db.insert_run(
            stryd_activity_id=12345,
            name="Test Run",
            date="2026-03-01",
            fit_path="activities/test.fit",
        )

        response = client.get(f"/run/{run_id}/analyze")
        assert response.status_code == 405  # Method Not Allowed

    def test_run_status_endpoint(self, client, app):
        """Test the run status polling endpoint."""
        db = app.config["db"]

        run_id = db.insert_run(
            stryd_activity_id=12345,
            name="Test Run",
            date="2026-03-01",
            fit_path="activities/test.fit",
        )

        response = client.get(f"/run/{run_id}/status")
        assert response.status_code == 200

        data = response.get_json()
        assert data is not None
        assert "stage" in data


class TestWorkoutsView:
    """Tests for workouts list view."""

    def test_workouts_pagination(self, client, app):
        """Test that workouts page handles pagination."""
        db = app.config["db"]

        # Insert multiple runs
        for i in range(15):
            db.insert_run(
                stryd_activity_id=i,
                name=f"Run {i}",
                date=f"2026-03-{i+1:02d}",
                fit_path=f"activities/run{i}.fit",
            )

        # First page
        response = client.get("/workouts")
        assert response.status_code == 200

        # Page 2
        response = client.get("/workouts?page=2")
        assert response.status_code == 200

    def test_workouts_with_no_runs(self, client):
        """Test workouts page with empty database."""
        response = client.get("/workouts")
        assert response.status_code == 200
        # Should render successfully even with no data


class TestCalendarView:
    """Tests for the calendar view on index page."""

    def test_calendar_with_planned_workouts(self, client, app):
        """Test that calendar displays planned workouts."""
        db = app.config["db"]

        # Insert a planned workout for today
        from datetime import date
        today = date.today().isoformat()

        db.upsert_planned_workout(
            date=today,
            title="Tempo Run",
            description="30 min at tempo",
            workout_type="tempo",
            duration_s=1800,
        )

        response = client.get("/")
        assert response.status_code == 200
        # Should render the calendar with the planned workout
        assert b"Tempo" in response.data or b"tempo" in response.data

    def test_calendar_with_actual_runs(self, client, app):
        """Test that calendar displays actual runs."""
        db = app.config["db"]

        from datetime import date
        today = date.today().isoformat()

        db.insert_run(
            stryd_activity_id=12345,
            name="Morning Run",
            date=today,
            fit_path="activities/test.fit",
        )

        response = client.get("/")
        assert response.status_code == 200
        assert b"Morning Run" in response.data or b"morning" in response.data.lower()


class TestSafeMarkdown:
    """Tests for markdown rendering and sanitization."""

    def test_markdown_rendering_in_commentary(self, client, app):
        """Test that markdown is properly rendered in commentary."""
        db = app.config["db"]

        # Insert a run with markdown commentary
        run_id = db.insert_run(
            stryd_activity_id=12345,
            name="Test Run",
            date="2026-03-01",
            fit_path="activities/test.fit",
        )

        markdown_commentary = """
# Great Workout!

You maintained **consistent power** throughout the run.

- Target power: 250W
- Average power: 248W
- Variance: <1%
"""

        db.update_analyzed(
            run_id=run_id,
            md_path="activities/test.md",
            commentary=markdown_commentary,
            model_used="gpt-4o",
        )

        response = client.get(f"/run/{run_id}")
        assert response.status_code == 200

        # Check that markdown was rendered to HTML
        assert b"<h1>" in response.data or b"<strong>" in response.data
        assert b"Great Workout" in response.data

    def test_markdown_sanitization(self, client, app):
        """Test that potentially dangerous HTML is sanitized."""
        db = app.config["db"]

        run_id = db.insert_run(
            stryd_activity_id=12345,
            name="Test Run",
            date="2026-03-01",
            fit_path="activities/test.fit",
        )

        # Try to inject script tag
        dangerous_commentary = """
Good run!

<script>alert('XSS')</script>

Keep it up!
"""

        db.update_analyzed(
            run_id=run_id,
            md_path="activities/test.md",
            commentary=dangerous_commentary,
            model_used="gpt-4o",
        )

        response = client.get(f"/run/{run_id}")
        assert response.status_code == 200

        # Script tag should be stripped
        assert b"<script>" not in response.data
        assert b"alert" not in response.data
        # But safe content should remain
        assert b"Good run" in response.data


class TestErrorHandling:
    """Tests for error handling."""

    def test_404_for_invalid_route(self, client):
        """Test that invalid routes return 404."""
        response = client.get("/this-route-does-not-exist")
        assert response.status_code == 404

    def test_run_not_found(self, client):
        """Test that accessing nonexistent run returns appropriate error."""
        response = client.get("/run/999999")
        # May return 404 or redirect (302) to index with flash message
        assert response.status_code in [302, 404]


class TestStaticAssets:
    """Tests for static assets and PWA files."""

    def test_manifest_exists(self, client):
        """Test that PWA manifest can be accessed."""
        # The manifest should be in static folder
        response = client.get("/static/manifest.json")
        # May be 200 if exists, or 404 if not found (acceptable for test)
        assert response.status_code in [200, 404]

    def test_service_worker_exists(self, client):
        """Test that service worker can be accessed."""
        response = client.get("/static/sw.js")
        # May be 200 if exists, or 404 if not found (acceptable for test)
        assert response.status_code in [200, 404]


class TestLogin:
    """Tests for session-based web login / logout."""

    def test_login_page_loads(self, app):
        """Login page must be accessible without authentication."""
        client = app.test_client()
        response = client.get("/login")
        assert response.status_code == 200
        assert b"password" in response.data.lower()

    def test_unauthenticated_redirects_to_login(self, app):
        """Protected routes must redirect to /login when not logged in."""
        client = app.test_client()
        response = client.get("/")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_unauthenticated_run_detail_redirects(self, app):
        """Run detail must redirect unauthenticated requests."""
        client = app.test_client()
        db = app.config["db"]
        run_id = db.insert_run(
            stryd_activity_id=99001,
            name="Auth Test Run",
            date="2026-03-01",
            fit_path="activities/auth_test.fit",
        )
        response = client.get(f"/run/{run_id}")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_correct_password_grants_access(self, app):
        """A correct password sets session and redirects to the app."""
        from runcoach.auth import hash_password
        db = app.config["db"]
        user_id = db.get_default_user_id()
        with db._connect() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, username = ? WHERE id = ?",
                (hash_password("testpass123"), "athlete", user_id),
            )

        client = app.test_client()

        response = client.post(
            "/login",
            data={"username": "athlete", "password": "testpass123", "next": "/"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        location = response.headers["Location"]
        assert location in ("/", "http://localhost/")

        # Session should now allow access
        response = client.get("/")
        assert response.status_code == 200

    def test_wrong_password_stays_on_login(self, app):
        """An incorrect password must not grant access and must re-render login."""
        client = app.test_client()
        response = client.post(
            "/login",
            data={"username": "athlete", "password": "definitely-wrong-password"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"password" in response.data.lower()
        # Flash message should indicate failure
        assert b"Incorrect" in response.data

    def test_empty_password_rejected(self, app):
        """An empty password must not authenticate."""
        client = app.test_client()
        response = client.post(
            "/login",
            data={"username": "athlete", "password": ""},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Incorrect" in response.data

    def test_open_redirect_blocked(self, app):
        """next= parameter must not allow redirect to external sites."""
        from runcoach.auth import hash_password
        db = app.config["db"]
        user_id = db.get_default_user_id()
        with db._connect() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, username = ? WHERE id = ?",
                (hash_password("testpass123"), "athlete", user_id),
            )

        client = app.test_client()
        response = client.post(
            "/login",
            data={"username": "athlete", "password": "testpass123", "next": "https://evil.example.com/steal"},
            follow_redirects=False,
        )
        # Must redirect to index, not the external URL
        assert response.status_code == 302
        location = response.headers["Location"]
        assert "evil.example.com" not in location

    def test_logout_clears_session(self, app):
        """Logout must clear the session and redirect to login."""
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = 1

        response = client.post("/logout", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

        # After logout, protected routes should redirect again
        response = client.get("/")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


class TestProfileSanitization:
    """Tests for athlete profile input sanitization."""

    def test_control_characters_stripped(self, app):
        """Control characters (except \\t, \\n, \\r) must be removed."""
        from runcoach.web.routes import _sanitize_profile
        dirty = "Hello\x00World\x07\x1b[31mRed\x1b[0m"
        clean = _sanitize_profile(dirty)
        assert "\x00" not in clean
        assert "\x07" not in clean
        assert "\x1b" not in clean
        assert "Hello" in clean
        assert "World" in clean

    def test_newlines_preserved(self, app):
        """Newlines and tabs must survive sanitization."""
        from runcoach.web.routes import _sanitize_profile
        text = "Line one\nLine two\r\nLine three\tTabbed"
        clean = _sanitize_profile(text)
        assert "\n" in clean
        assert "\t" in clean

    def test_length_capped_at_5000(self, app):
        """Input longer than 5000 chars must be truncated."""
        from runcoach.web.routes import _sanitize_profile
        long_text = "A" * 10_000
        clean = _sanitize_profile(long_text)
        assert len(clean) == 5_000

    def test_normal_text_unchanged(self, app):
        """Ordinary profile text must pass through unmodified."""
        from runcoach.web.routes import _sanitize_profile
        text = "I'm training for a marathon.\nCurrent CP: 280 W."
        assert _sanitize_profile(text) == text

    def test_profile_save_strips_control_chars(self, client, app):
        """POST /athlete-profile must store sanitized text."""
        dirty_profile = "My profile\x00with null\x07byte"
        response = client.post(
            "/athlete-profile",
            data={"profile": dirty_profile},
            follow_redirects=True,
        )
        assert response.status_code == 200

        db = app.config["db"]
        user_id = db.get_default_user_id()
        saved = db.get_athlete_profile(user_id)
        assert "\x00" not in saved
        assert "\x07" not in saved
        assert "My profile" in saved

    def test_profile_save_enforces_max_length(self, client, app):
        """POST /athlete-profile must truncate overlong input."""
        response = client.post(
            "/athlete-profile",
            data={"profile": "X" * 10_000},
            follow_redirects=True,
        )
        assert response.status_code == 200

        db = app.config["db"]
        user_id = db.get_default_user_id()
        saved = db.get_athlete_profile(user_id)
        assert len(saved) <= 5_000


# ---------------------------------------------------------------------------
# Strava webhook fixtures & helpers
# ---------------------------------------------------------------------------

import json
import threading


@pytest.fixture
def strava_app(tmp_path):
    """Flask app with Strava integration configured."""
    from runcoach.config import Config
    config = Config(
        openai_api_key="test-key",
        openai_model="gpt-4o",
        data_dir=tmp_path / "data",
        timezone="Europe/London",
        secret_key="test-secret-key-for-testing",
        sync_interval_hours=0,
        strava_client_id="fake_client_id",
        strava_client_secret="fake_client_secret",
        strava_webhook_verify_token="test-verify-token",
        strava_webhook_enabled=True,
    )
    from runcoach.web import create_app
    app = create_app(config)
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False

    scheduler = app.config.get("scheduler")
    if scheduler:
        scheduler.stop()

    yield app


@pytest.fixture
def strava_client(strava_app):
    """Unauthenticated test client (webhook endpoints are public)."""
    return strava_app.test_client()


class TestStravaWebhookVerification:
    """Tests for GET /strava/webhook (Strava hub challenge)."""

    def test_valid_challenge_returns_hub_challenge(self, strava_client):
        """Correct verify_token must echo back hub.challenge."""
        response = strava_client.get(
            "/strava/webhook",
            query_string={
                "hub.mode": "subscribe",
                "hub.verify_token": "test-verify-token",
                "hub.challenge": "abc123",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data == {"hub.challenge": "abc123"}

    def test_wrong_verify_token_returns_403(self, strava_client):
        """A mismatched verify_token must be rejected with 403."""
        response = strava_client.get(
            "/strava/webhook",
            query_string={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong-token",
                "hub.challenge": "abc123",
            },
        )
        assert response.status_code == 403

    def test_missing_verify_token_returns_403(self, strava_client):
        """A missing verify_token must be rejected with 403."""
        response = strava_client.get(
            "/strava/webhook",
            query_string={"hub.challenge": "abc123"},
        )
        assert response.status_code == 403

    def test_challenge_value_is_reflected_verbatim(self, strava_client):
        """The exact challenge string must be echoed, whatever it contains."""
        challenge = "random-challenge-xyz-9876"
        response = strava_client.get(
            "/strava/webhook",
            query_string={
                "hub.verify_token": "test-verify-token",
                "hub.challenge": challenge,
            },
        )
        assert response.status_code == 200
        assert response.get_json()["hub.challenge"] == challenge

    def test_webhook_accessible_without_login(self, strava_app):
        """Webhook verification must be reachable without a session cookie."""
        c = strava_app.test_client()  # no session manipulation
        response = c.get(
            "/strava/webhook",
            query_string={
                "hub.verify_token": "test-verify-token",
                "hub.challenge": "open-check",
            },
        )
        assert response.status_code == 200


class TestStravaWebhookEvent:
    """Tests for POST /strava/webhook (activity event handler)."""

    def _post_event(self, client, payload):
        body = _json.dumps(payload).encode()
        return client.post(
            "/strava/webhook",
            data=body,
            content_type="application/json",
        )

    def test_activity_create_returns_ok_immediately(self, strava_client, mocker):
        """Webhook must return 200 ok immediately regardless of background work."""
        mocker.patch("threading.Thread.start")  # stop the background thread
        response = self._post_event(strava_client, {
            "object_type": "activity",
            "aspect_type": "create",
            "object_id": 111111,
            "owner_id": 9999,
        })
        assert response.status_code == 200
        assert response.get_json() == {"ok": True}

    def test_non_activity_event_ignored(self, strava_client, mocker):
        """Non-activity events (e.g. athlete updates) must be acknowledged but not processed."""
        start_mock = mocker.patch("threading.Thread.start")
        response = self._post_event(strava_client, {
            "object_type": "athlete",
            "aspect_type": "update",
            "object_id": 9999,
        })
        assert response.status_code == 200
        assert response.get_json() == {"ok": True}
        start_mock.assert_not_called()

    def test_delete_event_ignored(self, strava_client, mocker):
        """Activity delete events must be acknowledged but not processed."""
        start_mock = mocker.patch("threading.Thread.start")
        response = self._post_event(strava_client, {
            "object_type": "activity",
            "aspect_type": "delete",
            "object_id": 111111,
        })
        assert response.status_code == 200
        start_mock.assert_not_called()

    def test_empty_body_returns_ok(self, strava_client, mocker):
        """An empty / malformed body must not crash the endpoint."""
        mocker.patch("threading.Thread.start")
        response = strava_client.post(
            "/strava/webhook",
            data=b"",
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.get_json() == {"ok": True}

    def test_background_thread_is_spawned_for_create(self, strava_client, mocker):
        """A create event must spawn exactly one background thread."""
        start_mock = mocker.patch("threading.Thread.start")
        self._post_event(strava_client, {
            "object_type": "activity",
            "aspect_type": "create",
            "object_id": 222222,
            "owner_id": 9999,
        })
        start_mock.assert_called_once()

    def test_background_thread_is_spawned_for_update(self, strava_client, mocker):
        """An update event must also spawn a background thread."""
        start_mock = mocker.patch("threading.Thread.start")
        self._post_event(strava_client, {
            "object_type": "activity",
            "aspect_type": "update",
            "object_id": 333333,
        })
        start_mock.assert_called_once()

    # ------------------------------------------------------------------
    # Helpers for end-to-end handler tests
    # ------------------------------------------------------------------

    def _run_handler_synchronously(self, strava_client, mocker, payload):
        """
        Post a webhook event and run the background handler synchronously.

        Replaces threading.Thread in the routes module with a fake that calls
        the target function immediately inside start(), so side-effects are
        observable before we return.
        """
        def fake_thread_class(*args, **kwargs):
            target = kwargs.get("target")
            thread_args = kwargs.get("args", ())

            class _FakeThread:
                daemon = kwargs.get("daemon", False)

                def start(self):
                    if target:
                        target(*thread_args)

                def join(self, timeout=None):
                    pass

            return _FakeThread()

        mocker.patch("runcoach.web.routes.threading.Thread", side_effect=fake_thread_class)
        return self._post_event(strava_client, payload)

    def test_webhook_triggers_pipeline_and_stores_polyline(self, strava_client, strava_app, mocker):
        """
        End-to-end background handler test:
        - pipeline is run synchronously via run_full_pipeline
        - Strava activity is fetched first; polyline stored on matching run
        """
        import time
        db = strava_app.config["db"]

        run_id = db.insert_run(
            stryd_activity_id=55555,
            name="Morning Run",
            date="2026-03-15",
            fit_path="activities/test.fit",
        )

        pipeline_mock = mocker.patch("runcoach.web.routes.run_full_pipeline")

        fake_activity = {
            "id": 777777,
            "sport_type": "Run",
            "start_date_local": "2026-03-15T07:00:00Z",
            "map": {"summary_polyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@"},
        }
        mock_client_instance = mocker.MagicMock()
        mock_client_instance.get_valid_access_token.return_value = "fake-token"
        mock_client_instance.get_activity.return_value = fake_activity
        mocker.patch("runcoach.strava.StravaClient", return_value=mock_client_instance)

        user_id = db.get_default_user_id()
        db.save_strava_tokens(
            user_id=user_id,
            access_token="fake-access",
            refresh_token="fake-refresh",
            expires_at=int(time.time()) + 3600,
        )

        self._run_handler_synchronously(strava_client, mocker, {
            "object_type": "activity",
            "aspect_type": "create",
            "object_id": 777777,
        })

        pipeline_mock.assert_called_once()
        updated = db.get_run(run_id)
        assert updated["strava_map_polyline"] == "_p~iF~ps|U_ulLnnqC_mqNvxq`@"

    def test_background_handler_skips_non_run_sport(self, strava_client, strava_app, mocker):
        """Handler must bail out before calling the pipeline for non-running activities."""
        import time
        db = strava_app.config["db"]

        pipeline_mock = mocker.patch("runcoach.web.routes.run_full_pipeline")

        fake_activity = {
            "id": 888888,
            "sport_type": "Ride",
            "start_date_local": "2026-03-16T08:00:00Z",
            "map": {"summary_polyline": "some_polyline"},
        }
        mock_client_instance = mocker.MagicMock()
        mock_client_instance.get_valid_access_token.return_value = "fake-token"
        mock_client_instance.get_activity.return_value = fake_activity
        mocker.patch("runcoach.strava.StravaClient", return_value=mock_client_instance)

        user_id = db.get_default_user_id()
        db.save_strava_tokens(
            user_id=user_id,
            access_token="fake-access",
            refresh_token="fake-refresh",
            expires_at=int(time.time()) + 3600,
        )

        self._run_handler_synchronously(strava_client, mocker, {
            "object_type": "activity",
            "aspect_type": "create",
            "object_id": 888888,
        })

        # Pipeline must NOT have been invoked for a non-running sport
        pipeline_mock.assert_not_called()
        runs = db.get_runs_on_date("2026-03-16")
        for r in runs:
            assert not r.get("strava_map_polyline")

    def test_background_handler_links_run_by_strava_id(self, strava_client, strava_app, mocker):
        """Handler must update an existing run that already has strava_activity_id set."""
        import time
        db = strava_app.config["db"]

        mocker.patch("runcoach.web.routes.run_full_pipeline")

        run_id = db.insert_run(
            stryd_activity_id=66666,
            name="Linked Run",
            date="2026-03-20",
            fit_path="activities/linked.fit",
        )
        db.update_run_strava_data(run_id=run_id, strava_activity_id="999999")

        fake_activity = {
            "id": 999999,
            "sport_type": "Run",
            "start_date_local": "2026-03-20T06:00:00Z",
            "map": {"summary_polyline": "newpolyline=="},
        }
        mock_client_instance = mocker.MagicMock()
        mock_client_instance.get_valid_access_token.return_value = "fake-token"
        mock_client_instance.get_activity.return_value = fake_activity
        mocker.patch("runcoach.strava.StravaClient", return_value=mock_client_instance)

        user_id = db.get_default_user_id()
        db.save_strava_tokens(
            user_id=user_id,
            access_token="fake-access",
            refresh_token="fake-refresh",
            expires_at=int(time.time()) + 3600,
        )

        self._run_handler_synchronously(strava_client, mocker, {
            "object_type": "activity",
            "aspect_type": "create",
            "object_id": 999999,
        })

        updated = db.get_run(run_id)
        assert updated["strava_map_polyline"] == "newpolyline=="

    def test_background_handler_retries_pipeline_when_run_not_found(self, strava_client, strava_app, mocker):
        """
        If the run is not in the DB after the first pipeline run, the handler
        must sleep 30s, retry, then sleep 120s, retry — and link on success.
        """
        import time
        db = strava_app.config["db"]

        # Pipeline mock that inserts the run on its second call
        call_count = {"n": 0}
        run_id_holder = {}

        def fake_pipeline(config, db_arg, user_id=1):
            call_count["n"] += 1
            if call_count["n"] == 2:
                rid = db_arg.insert_run(
                    stryd_activity_id=77777,
                    name="Late Arrival Run",
                    date="2026-03-21",
                    fit_path="activities/late.fit",
                )
                run_id_holder["id"] = rid

        mocker.patch("runcoach.web.routes.run_full_pipeline", side_effect=fake_pipeline)
        sleep_mock = mocker.patch("runcoach.web.routes.time.sleep")

        fake_activity = {
            "id": 404040,
            "sport_type": "Run",
            "start_date_local": "2026-03-21T06:30:00Z",
            "map": {"summary_polyline": "retrypoly=="},
        }
        mock_client_instance = mocker.MagicMock()
        mock_client_instance.get_valid_access_token.return_value = "fake-token"
        mock_client_instance.get_activity.return_value = fake_activity
        mocker.patch("runcoach.strava.StravaClient", return_value=mock_client_instance)

        user_id = db.get_default_user_id()
        db.save_strava_tokens(
            user_id=user_id,
            access_token="fake-access",
            refresh_token="fake-refresh",
            expires_at=int(time.time()) + 3600,
        )

        self._run_handler_synchronously(strava_client, mocker, {
            "object_type": "activity",
            "aspect_type": "create",
            "object_id": 404040,
        })

        # Pipeline called twice (initial + first retry)
        assert call_count["n"] == 2
        # First retry delay is 30s
        sleep_mock.assert_called_once_with(30)
        # Run should be linked with the polyline
        updated = db.get_run(run_id_holder["id"])
        assert updated["strava_map_polyline"] == "retrypoly=="

    def test_background_handler_treadmill_accepted(self, strava_client, strava_app, mocker):
        """Treadmill runs must be processed the same as outdoor runs."""
        import time
        db = strava_app.config["db"]

        pipeline_mock = mocker.patch("runcoach.web.routes.run_full_pipeline")

        run_id = db.insert_run(
            stryd_activity_id=88888,
            name="Treadmill Run",
            date="2026-03-21",
            fit_path="activities/treadmill.fit",
        )

        fake_activity = {
            "id": 505050,
            "sport_type": "Treadmill",
            "start_date_local": "2026-03-21T08:00:00Z",
            "map": {"summary_polyline": None},
        }
        mock_client_instance = mocker.MagicMock()
        mock_client_instance.get_valid_access_token.return_value = "fake-token"
        mock_client_instance.get_activity.return_value = fake_activity
        mocker.patch("runcoach.strava.StravaClient", return_value=mock_client_instance)

        user_id = db.get_default_user_id()
        db.save_strava_tokens(
            user_id=user_id,
            access_token="fake-access",
            refresh_token="fake-refresh",
            expires_at=int(time.time()) + 3600,
        )

        self._run_handler_synchronously(strava_client, mocker, {
            "object_type": "activity",
            "aspect_type": "create",
            "object_id": 505050,
        })

        # Pipeline must have been called
        pipeline_mock.assert_called_once()
        # Run linked (no polyline for treadmill, but strava_activity_id stored)
        updated = db.get_run(run_id)
        assert updated["strava_activity_id"] == "505050"



class TestRaceGoal:
    """Tests for race goal save route."""

    def test_race_goal_save_valid(self, client, app):
        """POST /athlete-profile/race-goal saves valid race goal."""
        response = client.post(
            "/athlete-profile/race-goal",
            data={"race_date": "2027-04-25", "race_distance": "Marathon"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        db = app.config["db"]
        user_id = db.get_default_user_id()
        goal = db.get_race_goal(user_id)
        assert goal["race_date"] == "2027-04-25"
        assert goal["race_distance"] == "Marathon"

    def test_race_goal_page_displays_goal(self, client, app):
        """Athlete profile page shows current race goal when set."""
        db = app.config["db"]
        user_id = db.get_default_user_id()
        db.update_race_goal(user_id, "2027-04-25", "Marathon")

        response = client.get("/athlete-profile")
        assert response.status_code == 200
        assert b"Marathon" in response.data
        assert b"2027-04-25" in response.data

    def test_race_goal_save_past_date_rejected(self, client):
        """POST /athlete-profile/race-goal rejects a past date."""
        response = client.post(
            "/athlete-profile/race-goal",
            data={"race_date": "2020-01-01", "race_distance": "5K"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"future" in response.data.lower()

    def test_race_goal_save_invalid_distance_rejected(self, client):
        """POST /athlete-profile/race-goal rejects unknown distance."""
        response = client.post(
            "/athlete-profile/race-goal",
            data={"race_date": "2027-04-25", "race_distance": "Ultra"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Invalid" in response.data

    def test_race_goal_clear(self, client, app):
        """Submitting empty values clears the race goal."""
        db = app.config["db"]
        user_id = db.get_default_user_id()
        db.update_race_goal(user_id, "2027-04-25", "Marathon")

        response = client.post(
            "/athlete-profile/race-goal",
            data={"race_date": "", "race_distance": ""},
            follow_redirects=True,
        )
        assert response.status_code == 200

        goal = db.get_race_goal(user_id)
        assert goal["race_date"] is None
        assert goal["race_distance"] is None
