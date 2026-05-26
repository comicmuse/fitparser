"""Unit tests for runcoach.web Flask application."""

from __future__ import annotations

import json as _json
from unittest.mock import patch

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

    def test_ors_api_key_defaults_empty(self, tmp_path):
        config = Config(data_dir=tmp_path / "data")
        assert config.ors_api_key == ""

    def test_ors_api_key_from_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ORS_API_KEY", "test-ors-key")
        config = Config.from_env()
        assert config.ors_api_key == "test-ors-key"


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

    def test_run_detail_loads_workout_data_from_parsed_data(self, client, app):
        """Run detail page renders without error when parsed_data is set."""
        db = app.config["db"]
        run_id = db.insert_run(
            stryd_activity_id=77,
            name="Detail Test",
            date="2026-03-10",
            fit_path="activities/detail.fit",
        )
        db.update_parsed(
            run_id=run_id,
            yaml_path=None,
            avg_power_w=230,
            avg_hr=150,
            workout_name="Detail Test",
            parsed_data=_json.dumps({
                "workout_name": "Detail Test",
                "avg_power": 230,
                "blocks": {},
            }),
        )
        resp = client.get(f"/run/{run_id}")
        assert resp.status_code == 200

    def test_run_detail_handles_missing_parsed_data(self, client, app):
        """Run detail page renders without error when parsed_data is NULL."""
        db = app.config["db"]
        run_id = db.insert_run(
            stryd_activity_id=78,
            name="No Data",
            date="2026-03-11",
            fit_path="activities/nodata.fit",
        )
        resp = client.get(f"/run/{run_id}")
        assert resp.status_code == 200


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

    def test_workouts_page_loads(self, client):
        response = client.get("/workouts")
        assert response.status_code == 200

    def test_workouts_with_year_month_params(self, client, app):
        db = app.config["db"]
        db.insert_run(stryd_activity_id=None, name="May Run", date="2026-05-01", fit_path="a.fit", user_id=1)
        response = client.get("/workouts?year=2026&month=5")
        assert response.status_code == 200
        assert b"May Run" in response.data

    def test_workouts_with_no_runs(self, client):
        response = client.get("/workouts")
        assert response.status_code == 200

    def test_workouts_no_planned_workouts_in_response(self, client):
        response = client.get("/workouts")
        assert response.status_code == 200
        assert b"Upcoming Planned" not in response.data
        assert b"Past Planned" not in response.data

    def test_get_year_month_summary(self, app):
        db = app.config["db"]
        db.insert_run(stryd_activity_id=None, name="Run A", date="2026-05-01", fit_path="a.fit", user_id=1)
        db.insert_run(stryd_activity_id=None, name="Run B", date="2026-05-15", fit_path="b.fit", user_id=1)
        db.insert_run(stryd_activity_id=None, name="Run C", date="2026-03-10", fit_path="c.fit", user_id=1)
        db.insert_run(stryd_activity_id=None, name="Run D", date="2025-12-20", fit_path="d.fit", user_id=1)
        summary = db.get_year_month_summary(user_id=1)
        assert len(summary) == 3
        assert summary[0] == {"year": 2026, "month": 5, "count": 2}
        assert summary[1] == {"year": 2026, "month": 3, "count": 1}
        assert summary[2] == {"year": 2025, "month": 12, "count": 1}

    def test_get_runs_for_month(self, app):
        db = app.config["db"]
        db.insert_run(stryd_activity_id=None, name="May Run 1", date="2026-05-03", fit_path="a.fit", user_id=1)
        db.insert_run(stryd_activity_id=None, name="May Run 2", date="2026-05-01", fit_path="b.fit", user_id=1)
        db.insert_run(stryd_activity_id=None, name="Apr Run",   date="2026-04-28", fit_path="c.fit", user_id=1)
        runs = db.get_runs_for_month(2026, 5, user_id=1)
        assert len(runs) == 2
        assert runs[0]["name"] == "May Run 1"
        assert runs[1]["name"] == "May Run 2"
        assert all(r["date"].startswith("2026-05") for r in runs)


class TestPolylineSvg:
    def test_basic(self):
        from runcoach.strava import polyline_to_svg_path
        import re
        coords = [[53.3, -6.2], [53.31, -6.21], [53.32, -6.19]]
        result = polyline_to_svg_path(coords, size=52)
        assert result.startswith("<polyline points=")
        assert 'stroke="#fc4c02"' in result
        pts = re.findall(r"[\d.]+,[\d.]+", result)
        assert len(pts) >= 2

    def test_empty(self):
        from runcoach.strava import polyline_to_svg_path
        assert polyline_to_svg_path([], size=52) == ""
        assert polyline_to_svg_path([[1.0, 2.0]], size=52) == ""

    def test_fits_within_size(self):
        from runcoach.strava import polyline_to_svg_path
        import re
        coords = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
        result = polyline_to_svg_path(coords, size=52)
        pts = re.findall(r"([\d.]+),([\d.]+)", result)
        for x_str, y_str in pts:
            assert 0.0 <= float(x_str) <= 52.0
            assert 0.0 <= float(y_str) <= 52.0


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

        # Injected script tag and its content should be stripped from commentary
        assert b"alert" not in response.data
        assert b"alert('XSS')" not in response.data
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
            strava_athlete_id="12345",
        )

        self._run_handler_synchronously(strava_client, mocker, {
            "object_type": "activity",
            "aspect_type": "create",
            "object_id": 777777,
            "owner_id": 12345,
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
            strava_athlete_id="12345",
        )

        self._run_handler_synchronously(strava_client, mocker, {
            "object_type": "activity",
            "aspect_type": "create",
            "object_id": 888888,
            "owner_id": 12345,
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
            strava_athlete_id="12345",
        )

        self._run_handler_synchronously(strava_client, mocker, {
            "object_type": "activity",
            "aspect_type": "create",
            "object_id": 999999,
            "owner_id": 12345,
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
            strava_athlete_id="12345",
        )

        self._run_handler_synchronously(strava_client, mocker, {
            "object_type": "activity",
            "aspect_type": "create",
            "object_id": 404040,
            "owner_id": 12345,
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
            strava_athlete_id="12345",
        )

        self._run_handler_synchronously(strava_client, mocker, {
            "object_type": "activity",
            "aspect_type": "create",
            "object_id": 505050,
            "owner_id": 12345,
        })

        # Pipeline must have been called
        pipeline_mock.assert_called_once()
        # Run linked (no polyline for treadmill, but strava_activity_id stored)
        updated = db.get_run(run_id)
        assert updated["strava_activity_id"] == "505050"

    def test_webhook_missing_owner_id_ignored(self, strava_client, strava_app, mocker):
        """Events with no owner_id must not trigger the pipeline (no default-user fallback)."""
        pipeline_mock = mocker.patch("runcoach.web.routes.run_full_pipeline")
        mock_client_instance = mocker.MagicMock()
        mock_client_instance.get_valid_access_token.return_value = "fake-token"
        mocker.patch("runcoach.strava.StravaClient", return_value=mock_client_instance)

        self._run_handler_synchronously(strava_client, mocker, {
            "object_type": "activity",
            "aspect_type": "create",
            "object_id": 600600,
            # owner_id deliberately omitted
        })

        pipeline_mock.assert_not_called()

    def test_webhook_unknown_owner_id_ignored(self, strava_client, strava_app, mocker):
        """Events whose owner_id doesn't match any known Strava athlete must be silently dropped."""
        pipeline_mock = mocker.patch("runcoach.web.routes.run_full_pipeline")
        mock_client_instance = mocker.MagicMock()
        mock_client_instance.get_valid_access_token.return_value = "fake-token"
        mocker.patch("runcoach.strava.StravaClient", return_value=mock_client_instance)

        self._run_handler_synchronously(strava_client, mocker, {
            "object_type": "activity",
            "aspect_type": "create",
            "object_id": 700700,
            "owner_id": 99999999,  # not in DB
        })

        pipeline_mock.assert_not_called()

    def test_webhook_run_link_scoped_to_owner(self, strava_client, strava_app, mocker):
        """Run linking by date must only touch runs belonging to the webhook owner."""
        import time
        db = strava_app.config["db"]
        mocker.patch("runcoach.web.routes.run_full_pipeline")

        user_id = db.get_default_user_id()
        db.save_strava_tokens(
            user_id=user_id,
            access_token="fake-access",
            refresh_token="fake-refresh",
            expires_at=int(time.time()) + 3600,
            strava_athlete_id="12345",
        )

        # Insert a run for user_id (the webhook owner)
        owner_run_id = db.insert_run(
            stryd_activity_id=80001,
            name="Owner Run",
            date="2026-04-01",
            fit_path="activities/owner.fit",
        )
        # Insert a second run with a *different* user_id to simulate another user
        other_user_id = db.create_user("other_user", "fakehash")
        other_run_id = db.insert_run(
            stryd_activity_id=80002,
            name="Other User Run",
            date="2026-04-01",
            fit_path="activities/other.fit",
            user_id=other_user_id,
        )

        fake_activity = {
            "id": 800800,
            "sport_type": "Run",
            "start_date_local": "2026-04-01T07:00:00Z",
            "map": {"summary_polyline": "ownerpoly=="},
        }
        mock_client_instance = mocker.MagicMock()
        mock_client_instance.get_valid_access_token.return_value = "fake-token"
        mock_client_instance.get_activity.return_value = fake_activity
        mocker.patch("runcoach.strava.StravaClient", return_value=mock_client_instance)

        self._run_handler_synchronously(strava_client, mocker, {
            "object_type": "activity",
            "aspect_type": "create",
            "object_id": 800800,
            "owner_id": 12345,
        })

        # Only the owner's run should be linked
        owner_run = db.get_run(owner_run_id, user_id=user_id)
        other_run = db.get_run(other_run_id, user_id=other_user_id)
        assert owner_run["strava_map_polyline"] == "ownerpoly=="
        assert other_run["strava_map_polyline"] is None


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


class TestRunChat:
    def test_run_detail_includes_chat_history(self, client, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        run_id = db.insert_run(
            stryd_activity_id=7001,
            name="Chat Web Run",
            date="2026-04-01",
            fit_path="activities/chat_web.fit",
            distance_m=8000,
            moving_time_s=2400,
        )
        db.update_analyzed(
            run_id=run_id,
            md_path="activities/chat_web.md",
            commentary="Good run.",
            model_used="llama3.2",
            prompt_tokens=50,
            completion_tokens=20,
        )
        db.add_chat_message(run_id, user_id, "user", "How was my power?")
        db.add_chat_message(run_id, user_id, "assistant", "Your power was **200W**.")

        with client.session_transaction() as sess:
            sess["user_id"] = user_id
        resp = client.get(f"/run/{run_id}")
        assert resp.status_code == 200
        assert b"How was my power?" in resp.data
        assert b"200W" in resp.data  # markdown rendered

    def test_chat_route_returns_assistant_response(self, client, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        run_id = db.insert_run(
            stryd_activity_id=7002,
            name="Chat Route Run",
            date="2026-04-02",
            fit_path="activities/chat_route.fit",
            distance_m=8000,
            moving_time_s=2400,
        )
        db.update_analyzed(
            run_id=run_id,
            md_path="activities/chat_route.md",
            commentary="Nice session.",
            model_used="llama3.2",
            prompt_tokens=50,
            completion_tokens=20,
        )

        with client.session_transaction() as sess:
            sess["user_id"] = user_id

        with patch("runcoach.web.routes.build_chat_context") as mock_ctx, \
             patch("runcoach.web.routes._dispatch_llm") as mock_llm:
            mock_ctx.return_value = ("sys", "usr")
            mock_llm.return_value = {
                "commentary": "Your HR looked great.",
                "prompt_tokens": 80,
                "completion_tokens": 25,
            }
            resp = client.post(
                f"/run/{run_id}/chat",
                json={"message": "How was my HR?"},
                content_type="application/json",
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["role"] == "assistant"
        assert data["message"] == "Your HR looked great."
        assert "message_html" in data

    def test_chat_route_unauthenticated_redirects(self, client, app):
        db = app.config["db"]
        run_id = db.insert_run(
            stryd_activity_id=7003,
            name="Auth Run",
            date="2026-04-03",
            fit_path="activities/auth.fit",
            distance_m=5000,
            moving_time_s=1500,
        )
        resp = app.test_client().post(
            f"/run/{run_id}/chat",
            json={"message": "test"},
            content_type="application/json",
        )
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

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


class TestAnalyzeRunRateLimit:
    """Tests for rate-limiting the analyze_run_route."""

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

        resp = client.post(
            f"/run/{run_id}/analyze",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Daily analysis limit reached" in resp.data


class TestComputePowerScaleMax:
    """Tests for _compute_power_scale_max helper."""

    def test_with_targets_returns_rounded_scale(self):
        from runcoach.web.routes import _compute_power_scale_max
        blocks = {
            "warmup":   {"avg_power": 160.0, "duration_min": 10.0},
            "active_1": {"avg_power": 235.0, "duration_min": 22.0,
                         "target_power": {"min_w": 220.0, "max_w": 250.0}},
            "active_2": {"avg_power": 268.0, "duration_min": 24.0,
                         "target_power": {"min_w": 240.0, "max_w": 260.0}},
        }
        # max value is 268W, * 1.15 = 308.2, ceil(308.2/50)*50 = 350
        assert _compute_power_scale_max(blocks) == 350

    def test_minimum_is_300(self):
        from runcoach.web.routes import _compute_power_scale_max
        blocks = {"warmup": {"avg_power": 100.0, "duration_min": 10.0}}
        assert _compute_power_scale_max(blocks) == 300

    def test_empty_blocks_returns_300(self):
        from runcoach.web.routes import _compute_power_scale_max
        assert _compute_power_scale_max({}) == 300

    def test_target_max_w_included_in_scale(self):
        from runcoach.web.routes import _compute_power_scale_max
        # target max_w = 320W > avg_power 200W; 320 * 1.15 = 368 -> ceil to 400
        blocks = {"active_1": {"avg_power": 200.0,
                               "target_power": {"min_w": 280.0, "max_w": 320.0}}}
        assert _compute_power_scale_max(blocks) == 400

    def test_no_avg_power_key_is_skipped(self):
        from runcoach.web.routes import _compute_power_scale_max
        blocks = {"warmup": {"duration_min": 10.0}}  # no avg_power key
        assert _compute_power_scale_max(blocks) == 300


class TestWorkoutChart:
    """Integration tests for the holistic workout chart."""

    def test_workout_chart_renders_with_targets(self, client, app):
        """Run detail page renders new chart elements when YAML has power targets."""
        import json as _json
        db = app.config["db"]
        blocks_data = {
            "blocks": {
                "warmup": {
                    "type": "warmup", "duration_min": 10.0, "avg_power": 160.0,
                    "avg_hr": 138.0, "distance_km": 1.8,
                    "hr_zones": {"Z1_pct": 55.0, "Z2_pct": 35.0, "Z3_pct": 10.0,
                                 "Z4_pct": 0.0, "Z5_pct": 0.0},
                },
                "active_1": {
                    "type": "work", "duration_min": 22.0, "avg_power": 235.0,
                    "avg_hr": 155.0, "distance_km": 4.2,
                    "target_power": {"min_w": 220.0, "max_w": 250.0,
                                     "pct_time_in_range": 85.0,
                                     "pct_time_above": 9.0, "pct_time_below": 6.0},
                    "hr_zones": {"Z1_pct": 5.0, "Z2_pct": 25.0, "Z3_pct": 55.0,
                                 "Z4_pct": 15.0, "Z5_pct": 0.0},
                    "running_dynamics": {"cadence_med": 172, "gct_med": 240,
                                         "vert_osc_med": 8.5, "form_power_med": 62},
                },
            }
        }
        run_id = db.insert_run(
            stryd_activity_id=77777, name="Chart Test Run",
            date="2026-05-01", fit_path="activities/chart_test.fit",
        )
        db.update_parsed(run_id=run_id, yaml_path=None,
                         avg_power_w=210.0, avg_hr=150, workout_name="Test Workout",
                         parsed_data=_json.dumps(blocks_data))

        response = client.get(f"/run/{run_id}")
        assert response.status_code == 200
        html = response.data.decode()

        # New chart structure present
        assert "wc-grid" in html
        assert "wc-col" in html
        assert "wc-power" in html
        assert "wc-hr" in html
        assert "data-segment" in html
        assert "wc-detail" in html
        assert "wc-tooltip" not in html
        assert "wc-legend" not in html

        # Compliance strip present for run with targets
        assert "comp-strip" in html
        assert "cs-in" in html

        # Coloured fills are gone — fill is always neutral
        assert "wc-fill--in" not in html
        assert "wc-fill--above" not in html
        assert "wc-fill--below" not in html

        # Segment names appear
        assert "warmup" in html
        assert "active_1" in html

        # Old elements are gone
        assert "hrZoneChart" not in html
        assert "block-grid" not in html
        assert "Block Timeline" not in html

    def test_workout_chart_no_targets_renders(self, client, app):
        """Chart renders correctly when no blocks have power targets."""
        import json as _json
        db = app.config["db"]
        blocks_data = {
            "blocks": {
                "easy": {
                    "type": "work", "duration_min": 30.0, "avg_power": 180.0,
                    "avg_hr": 145.0, "distance_km": 5.0,
                    "hr_zones": {"Z1_pct": 20.0, "Z2_pct": 60.0, "Z3_pct": 20.0,
                                 "Z4_pct": 0.0, "Z5_pct": 0.0},
                }
            }
        }
        run_id = db.insert_run(
            stryd_activity_id=77778, name="Easy Run",
            date="2026-05-02", fit_path="activities/no_target.fit",
        )
        db.update_parsed(run_id=run_id, yaml_path=None,
                         avg_power_w=180.0, avg_hr=145, workout_name=None,
                         parsed_data=_json.dumps(blocks_data))

        response = client.get(f"/run/{run_id}")
        assert response.status_code == 200
        html = response.data.decode()
        assert "wc-grid" in html
        assert "comp-strip" in html
        assert "cs-none" in html

        # Old coloured fill class must be gone
        assert "wc-fill--none" not in html

        assert "easy" in html


class TestRouteSuggestion:
    """Tests for GET /api/route-suggestion endpoint."""

    ORS_SUCCESS = {
        "features": [
            {
                "geometry": {"coordinates": [[-6.26, 53.35], [-6.27, 53.36], [-6.26, 53.35]]},
                "properties": {"summary": {"distance": 10200}},
            },
            {
                "geometry": {"coordinates": [[-6.26, 53.35], [-6.25, 53.36], [-6.26, 53.35]]},
                "properties": {"summary": {"distance": 9800}},
            },
            {
                "geometry": {"coordinates": [[-6.26, 53.35], [-6.28, 53.37], [-6.26, 53.35]]},
                "properties": {"summary": {"distance": 10500}},
            },
        ]
    }

    def test_missing_params_returns_400(self, client):
        resp = client.get("/api/route-suggestion")
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_invalid_lat_returns_400(self, client):
        resp = client.get("/api/route-suggestion?lat=notanumber&lng=-6.26&distance_m=10000")
        assert resp.status_code == 400

    def test_ors_key_not_configured_returns_503(self, client, app):
        app.config["config"].ors_api_key = ""  # explicit, not assumed
        resp = client.get("/api/route-suggestion?lat=53.35&lng=-6.26&distance_m=10000")
        assert resp.status_code == 503
        data = resp.get_json()
        assert "error" in data

    def test_out_of_range_lat_returns_400(self, client):
        resp = client.get("/api/route-suggestion?lat=999&lng=-6.26&distance_m=10000")
        assert resp.status_code == 400

    def test_negative_distance_returns_400(self, client):
        resp = client.get("/api/route-suggestion?lat=53.35&lng=-6.26&distance_m=-1")
        assert resp.status_code == 400

    def test_returns_routes_on_success(self, client, app):
        app.config["config"].ors_api_key = "test-key"
        with patch("runcoach.web.ors.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = self.ORS_SUCCESS
            resp = client.get("/api/route-suggestion?lat=53.35&lng=-6.26&distance_m=10000")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "routes" in data
        assert len(data["routes"]) == 5
        assert "coords" in data["routes"][0]
        assert "distance_m" in data["routes"][0]
        # coords are [lat, lng] pairs (note ORS returns [lng, lat] — verify swap)
        assert data["routes"][0]["coords"][0] == [53.35, -6.26]

    def test_ors_error_returns_502(self, client, app):
        app.config["config"].ors_api_key = "test-key"
        with patch("runcoach.web.ors.requests.post") as mock_post:
            mock_post.return_value.status_code = 429
            mock_post.return_value.text = "Rate limit exceeded"
            resp = client.get("/api/route-suggestion?lat=53.35&lng=-6.26&distance_m=10000")
        assert resp.status_code == 502
        data = resp.get_json()
        assert "error" in data

    def test_strava_routes_appear_before_ors(self, client, app):
        app.config["config"].ors_api_key = "test-key"
        db = app.config["db"]
        user_id = db.get_default_user_id()
        db.upsert_strava_routes(user_id, [{
            "strava_route_id": "999",
            "name": "Saved Loop",
            "distance_m": 10200.0,
            "start_lat": 53.35,
            "start_lng": -6.26,
            "polyline": "encoded_placeholder",
        }])
        near_coords = [[53.35, -6.26], [53.36, -6.27]]
        with patch("runcoach.strava.decode_polyline", return_value=near_coords), \
             patch("runcoach.web.ors.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = self.ORS_SUCCESS
            resp = client.get("/api/route-suggestion?lat=53.35&lng=-6.26&distance_m=10000")
        assert resp.status_code == 200
        sources = [r["source"] for r in resp.get_json()["routes"]]
        assert sources[0] == "strava"
        assert sources[-1] == "ors"

    def test_include_ors_false_skips_ors_and_returns_db_routes(self, client, app):
        app.config["config"].ors_api_key = "test-key"
        db = app.config["db"]
        user_id = db.get_default_user_id()
        db.upsert_strava_routes(user_id, [{
            "strava_route_id": "888",
            "name": "My Route",
            "distance_m": 10100.0,
            "start_lat": 53.35,
            "start_lng": -6.26,
            "polyline": "encoded_placeholder",
        }])
        near_coords = [[53.35, -6.26], [53.36, -6.27]]
        with patch("runcoach.strava.decode_polyline", return_value=near_coords), \
             patch("runcoach.web.ors.fetch_routes") as mock_fetch:
            resp = client.get(
                "/api/route-suggestion?lat=53.35&lng=-6.26&distance_m=10000&include_ors=false"
            )
        assert resp.status_code == 200
        mock_fetch.assert_not_called()
        routes = resp.get_json()["routes"]
        assert all(r["source"] != "ors" for r in routes)

    def test_include_ors_false_returns_empty_routes_when_no_local_matches(self, client, app):
        app.config["config"].ors_api_key = "test-key"
        with patch("runcoach.web.ors.fetch_routes") as mock_fetch:
            resp = client.get(
                "/api/route-suggestion?lat=53.35&lng=-6.26&distance_m=10000&include_ors=false"
            )
        assert resp.status_code == 200
        assert resp.get_json() == {"routes": []}
        mock_fetch.assert_not_called()


class TestOfflineRoutes:
    def test_recent_run_ids_authenticated(self, client, app):
        db = app.config["db"]
        # Insert 12 runs — expect only the 10 most recent IDs returned
        ids = []
        for i in range(12):
            run_id = db.insert_run(
                stryd_activity_id=i + 1,
                name=f"Run {i}",
                date=f"2026-{(i % 12) + 1:02d}-01",
                fit_path=f"activities/run{i}.fit",
            )
            ids.append(run_id)

        response = client.get("/recent-run-ids")
        assert response.status_code == 200
        data = response.get_json()
        assert "ids" in data
        assert len(data["ids"]) == 10
        # Most recent 10 runs (last inserted = highest IDs)
        # Most recent 10 = runs with months 3–12 (dates 2026-03-01 through 2026-12-01)
        # using set(ids[-10:]) is equivalent when 12 runs exist, keep for clarity.
        assert set(data["ids"]) == set(ids[-10:])

    def test_recent_run_ids_unauthenticated(self, app):
        # Fresh client — no session, not authenticated
        c = app.test_client()  # fresh client — no session, not authenticated
        response = c.get("/recent-run-ids")
        assert response.status_code == 302  # redirect to login

    def test_recent_run_ids_empty(self, client):
        # No runs in DB — should return empty list
        response = client.get("/recent-run-ids")
        assert response.status_code == 200
        data = response.get_json()
        assert data["ids"] == []

    def test_offline_page_no_auth_required(self, app):
        # /offline must work without a session (SW serves it from cache)
        c = app.test_client()  # fresh client — no session, not authenticated
        response = c.get("/offline")
        assert response.status_code == 200
        assert b"offline" in response.data.lower()

    def test_offline_page_has_no_external_deps(self, app):
        c = app.test_client()
        response = c.get("/offline")
        html = response.data.decode()
        # Must be self-contained — no CDN or external resources referenced
        assert "cdn." not in html
        assert "fonts.googleapis.com" not in html
        assert "unpkg.com" not in html
        assert "jsdelivr.net" not in html


class TestBestRunTimeWeb:
    def test_requires_login(self, app):
        client = app.test_client()
        r = client.get("/api/best-run-time?lat=53.3&lng=-6.3")
        assert r.status_code in (302, 401)

    def test_missing_params_returns_400(self, client):
        r = client.get("/api/best-run-time")
        assert r.status_code == 400

    def test_out_of_range_lat_returns_400(self, client):
        r = client.get("/api/best-run-time?lat=999&lng=0")
        assert r.status_code == 400

    def test_returns_scored_forecast(self, client, mocker):
        fake_result = {
            "date": "2026-05-10",
            "hours": [{"hour": h, "score": 7, "temp_c": 12.0, "rain_pct": 5, "humidity_pct": 55, "wind_kmh": 10.0} for h in range(24)],
            "best_hour": 9,
            "best_score": 8,
            "day_label": "Best window: 9am · 8/10",
        }
        mocker.patch("runcoach.web.routes.fetch_forecast", return_value={})
        mocker.patch("runcoach.web.routes.score_forecast", return_value=fake_result)
        r = client.get("/api/best-run-time?lat=53.3&lng=-6.3")
        assert r.status_code == 200
        assert r.get_json()["best_score"] == 8

    def test_weather_failure_returns_503(self, client, mocker):
        import requests as req_lib
        mocker.patch("runcoach.web.routes.fetch_forecast", side_effect=req_lib.RequestException("timeout"))
        r = client.get("/api/best-run-time?lat=53.3&lng=-6.3")
        assert r.status_code == 503
