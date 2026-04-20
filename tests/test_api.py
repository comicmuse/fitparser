"""Tests for runcoach.web.api — JWT-authenticated REST endpoints."""

from __future__ import annotations

import pytest

from runcoach.web import create_app
from runcoach.config import Config
from runcoach.auth import hash_password, create_access_token


@pytest.fixture
def app(tmp_path):
    config = Config(
        openai_api_key="test-key",
        openai_model="gpt-4o",
        data_dir=tmp_path / "data",
        timezone="Europe/London",
        secret_key="test-secret-key",
        sync_interval_hours=0,
    )
    app = create_app(config)
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers(app):
    """Return Authorization header with a valid access token."""
    db = app.config["db"]
    user_id = db.get_default_user_id()
    token = create_access_token(user_id, app.config["SECRET_KEY"])
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

class TestAuthLogin:
    def test_login_returns_tokens(self, client, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        with db._connect() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (hash_password("pass123"), user_id),
            )

        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "athlete", "password": "pass123"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["username"] == "athlete"

    def test_login_wrong_password(self, client, app):
        db = app.config["db"]
        db.ensure_default_user("athlete", hash_password("rightpass"))

        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "athlete", "password": "wrongpass"},
        )
        assert resp.status_code == 401

    def test_login_missing_fields(self, client):
        resp = client.post("/api/v1/auth/login", json={"username": "athlete"})
        assert resp.status_code == 400

    def test_login_unknown_user(self, client):
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "nobody", "password": "x"},
        )
        assert resp.status_code == 401

    def test_refresh_token(self, client, app):
        from runcoach.auth import create_refresh_token
        db = app.config["db"]
        user_id = db.get_default_user_id()
        refresh_tok = create_refresh_token(user_id, app.config["SECRET_KEY"])

        resp = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_tok},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.get_json()

    def test_refresh_invalid_token(self, client):
        resp = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "not.a.token"},
        )
        assert resp.status_code == 401

    def test_logout(self, client, auth_headers):
        resp = client.post("/api/v1/auth/logout", headers=auth_headers)
        assert resp.status_code == 200

    def test_protected_route_without_token(self, client):
        resp = client.get("/api/v1/runs")
        assert resp.status_code == 401

    def test_protected_route_with_bad_token(self, client):
        resp = client.get(
            "/api/v1/runs",
            headers={"Authorization": "Bearer garbage"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

class TestAPIRuns:
    def test_list_runs_empty(self, client, auth_headers):
        resp = client.get("/api/v1/runs", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["runs"] == []
        assert data["pagination"]["total"] == 0

    def test_list_runs_pagination(self, client, auth_headers, app):
        db = app.config["db"]
        for i in range(5):
            db.insert_run(
                stryd_activity_id=i,
                name=f"Run {i}",
                date=f"2026-03-{i+1:02d}",
                fit_path=f"activities/run{i}.fit",
            )

        resp = client.get("/api/v1/runs?page=1&per_page=3", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["runs"]) == 3
        assert data["pagination"]["total"] == 5
        assert data["pagination"]["total_pages"] == 2

    def test_get_run_found(self, client, auth_headers, app):
        db = app.config["db"]
        run_id = db.insert_run(
            stryd_activity_id=42,
            name="My Run",
            date="2026-03-10",
            fit_path="activities/test.fit",
        )

        resp = client.get(f"/api/v1/runs/{run_id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == run_id
        assert data["name"] == "My Run"

    def test_get_run_not_found(self, client, auth_headers):
        resp = client.get("/api/v1/runs/99999", headers=auth_headers)
        assert resp.status_code == 404

    def test_run_response_includes_expected_fields(self, client, auth_headers, app):
        db = app.config["db"]
        run_id = db.insert_run(
            stryd_activity_id=1,
            name="Field Check",
            date="2026-03-01",
            fit_path="activities/x.fit",
            distance_m=10000,
            moving_time_s=3600,
        )
        resp = client.get(f"/api/v1/runs/{run_id}", headers=auth_headers)
        data = resp.get_json()
        for field in ("id", "name", "date", "stage", "distance_km", "duration_s"):
            assert field in data, f"missing field: {field}"

    def test_per_page_clamped(self, client, auth_headers):
        """per_page > 100 is silently reset to 20."""
        resp = client.get("/api/v1/runs?per_page=999", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.get_json()["pagination"]["per_page"] == 20


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

class TestAPISync:
    def test_sync_status(self, client, auth_headers):
        resp = client.get("/api/v1/sync/status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "stats" in data

    def test_trigger_sync_starts(self, client, auth_headers, monkeypatch):
        from runcoach import scheduler as sched_mod
        monkeypatch.setattr(sched_mod.Scheduler, "trigger_now", lambda self: None)
        resp = client.post("/api/v1/sync", headers=auth_headers)
        # 202 accepted or 409 if already syncing
        assert resp.status_code in (202, 409)


# ---------------------------------------------------------------------------
# Athlete Profile via API
# ---------------------------------------------------------------------------

class TestAPIAthleteProfile:
    def test_get_profile(self, client, auth_headers):
        resp = client.get("/api/v1/athlete/profile", headers=auth_headers)
        assert resp.status_code == 200
        assert "profile" in resp.get_json()

    def test_update_profile(self, client, auth_headers):
        new_text = "Training for Berlin Marathon. CP: 280 W."
        resp = client.put(
            "/api/v1/athlete/profile",
            json={"profile": new_text},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.get_json()["profile"] == new_text

    def test_update_profile_strips_control_chars(self, client, auth_headers):
        resp = client.put(
            "/api/v1/athlete/profile",
            json={"profile": "Good\x00profile\x07text"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        saved = resp.get_json()["profile"]
        assert "\x00" not in saved
        assert "\x07" not in saved
        assert "Good" in saved

    def test_update_profile_truncates_at_5000(self, client, auth_headers):
        resp = client.put(
            "/api/v1/athlete/profile",
            json={"profile": "X" * 10_000},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert len(resp.get_json()["profile"]) <= 5_000

    def test_update_profile_no_body(self, client, auth_headers):
        resp = client.put(
            "/api/v1/athlete/profile",
            data="not json",
            content_type="text/plain",
            headers=auth_headers,
        )
        assert resp.status_code in (400, 415)

    def test_update_profile_unknown_fields_ignored(self, client, auth_headers):
        resp = client.put(
            "/api/v1/athlete/profile",
            json={"not_a_known_field": "oops"},
            headers=auth_headers,
        )
        assert resp.status_code == 200

    def test_update_profile_wrong_type(self, client, auth_headers):
        resp = client.put(
            "/api/v1/athlete/profile",
            json={"profile": 12345},
            headers=auth_headers,
        )
        assert resp.status_code == 400
