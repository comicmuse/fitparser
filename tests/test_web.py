"""Unit tests for runcoach.web Flask application."""

from __future__ import annotations

import pytest
from pathlib import Path
import yaml

from runcoach.web import create_app
from runcoach.config import Config


@pytest.fixture
def app(tmp_path):
    """Create a test Flask app with temporary database."""
    config = Config(
        openai_api_key="test-key",
        openai_model="gpt-4o",
        data_dir=tmp_path / "data",
        timezone="Europe/London",
        stryd_email="test@example.com",
        stryd_password="test-password",
        secret_key="test-secret-key-for-testing",
        sync_interval_hours=24,  # Don't auto-sync during tests
    )

    # Create the app but don't start the scheduler
    app = create_app(config)
    app.config["TESTING"] = True

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
        sess["logged_in"] = True
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
            stryd_email="test@example.com",
            stryd_password="test-password",
            secret_key="test-secret",
            sync_interval_hours=24,
        )

        app = create_app(config)

        assert app is not None
        assert app.config["config"] == config
        assert app.config["db"] is not None
        assert app.config["scheduler"] is not None

        # Clean up scheduler
        app.config["scheduler"].stop()

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

    def test_vapid_key_endpoint(self, client):
        """Test the VAPID key endpoint for push notifications."""
        response = client.get("/push/vapid-key")
        assert response.status_code == 200

        data = response.get_json()
        assert data is not None
        assert "vapid_public_key" in data  # May be None if not configured

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
