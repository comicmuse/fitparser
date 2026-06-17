"""Tests for runcoach.web.api — JWT-authenticated REST endpoints."""

from __future__ import annotations

import pytest
from unittest.mock import patch, ANY

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

    def test_login_inactive_user_rejected(self, client, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        with db._connect() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, is_active = 0 WHERE id = ?",
                (hash_password("pass123"), user_id),
            )

        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "athlete", "password": "pass123"},
        )
        assert resp.status_code == 403
        assert resp.get_json()["error"] == "Account is deactivated"

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

    def test_refresh_inactive_user_rejected(self, client, app):
        from runcoach.auth import create_refresh_token
        db = app.config["db"]
        user_id = db.get_default_user_id()
        refresh_tok = create_refresh_token(user_id, app.config["SECRET_KEY"])
        with db._connect() as conn:
            conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))

        resp = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_tok},
        )
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "Invalid or expired refresh token"

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

    def test_protected_route_with_inactive_user_token(self, client, auth_headers, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        with db._connect() as conn:
            conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))

        resp = client.get("/api/v1/runs", headers=auth_headers)
        assert resp.status_code == 401

    def test_protected_route_with_missing_user_token(self, client, app):
        token = create_access_token(99999, app.config["SECRET_KEY"])
        resp = client.get(
            "/api/v1/runs",
            headers={"Authorization": "Bearer " + token},
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
        assert "strava_map_polyline" in data

    def _insert_parsed_run(self, app) -> int:
        """Insert a run with parsed_data in the DB and return its ID."""
        import json as _json
        db = app.config["db"]
        user_id = db.get_default_user_id()
        run_id = db.insert_run(
            stryd_activity_id=42,
            name="Test Run",
            date="2026-03-07",
            fit_path="activities/test.fit",
            user_id=user_id,
        )
        db.update_parsed(
            run_id=run_id,
            yaml_path=None,
            avg_power_w=250,
            avg_hr=145,
            workout_name="Easy Run",
            parsed_data=_json.dumps({"workout_name": "Easy Run", "avg_power": 250}),
        )
        return run_id

    def test_get_run_includes_yaml_data(self, client, app, auth_headers):
        """GET /api/v1/runs/:id includes yaml_data sourced from parsed_data."""
        run_id = self._insert_parsed_run(app)
        resp = client.get(f"/api/v1/runs/{run_id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "yaml_data" in data
        assert data["yaml_data"]["avg_power"] == 250

    def test_get_run_yaml_data_none_when_no_parsed_data(self, client, app, auth_headers):
        """GET /api/v1/runs/:id returns yaml_data=None when parsed_data is NULL."""
        db = app.config["db"]
        user_id = db.get_default_user_id()
        run_id = db.insert_run(
            stryd_activity_id=99,
            name="Unparsed",
            date="2026-03-08",
            fit_path="activities/unparsed.fit",
            user_id=user_id,
        )
        resp = client.get(f"/api/v1/runs/{run_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.get_json()["yaml_data"] is None


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

    def test_update_profile(self, client, auth_headers):
        new_text = "Training for Berlin Marathon. CP: 280 W."
        resp = client.put(
            "/api/v1/athlete/profile",
            json={"profile": new_text},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.get_json()["profile"] == new_text
        # Ensure API returns Strava link field even when not connected (null) or when connected
        assert "strava_athlete_id" in resp.get_json()

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


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class TestRunChat:
    def test_get_chat_history_empty(self, client, auth_headers, app):
        db = app.config["db"]
        run_id = db.insert_run(
            stryd_activity_id=8001,
            name="Chat Run",
            date="2026-04-01",
            fit_path="activities/chat.fit",
            distance_m=8000,
            moving_time_s=2400,
        )
        resp = client.get(f"/api/v1/runs/{run_id}/chat", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["history"] == []

    def test_get_chat_history_with_messages(self, client, auth_headers, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        run_id = db.insert_run(
            stryd_activity_id=8002,
            name="Chat Run 2",
            date="2026-04-02",
            fit_path="activities/chat2.fit",
            distance_m=8000,
            moving_time_s=2400,
        )
        db.add_chat_message(run_id, user_id, "user", "How was my power?")
        db.add_chat_message(run_id, user_id, "assistant", "Your power was great.")

        resp = client.get(f"/api/v1/runs/{run_id}/chat", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["history"]) == 2
        assert data["history"][0]["role"] == "user"
        assert data["history"][1]["role"] == "assistant"

    def test_post_chat_returns_assistant_response(self, client, auth_headers, app):
        db = app.config["db"]
        run_id = db.insert_run(
            stryd_activity_id=8003,
            name="Chat Run 3",
            date="2026-04-03",
            fit_path="activities/chat3.fit",
            distance_m=8000,
            moving_time_s=2400,
        )

        with patch("runcoach.web.api.build_chat_context") as mock_ctx, \
             patch("runcoach.web.api._dispatch_llm") as mock_llm:
            mock_ctx.return_value = ("system prompt text", "user message text")
            mock_llm.return_value = {
                "commentary": "Your power was excellent at 220W average.",
                "prompt_tokens": 150,
                "completion_tokens": 60,
            }
            resp = client.post(
                f"/api/v1/runs/{run_id}/chat",
                json={"message": "How was my power?"},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["role"] == "assistant"
        assert data["message"] == "Your power was excellent at 220W average."
        assert data["prompt_tokens"] == 150
        assert data["completion_tokens"] == 60
        assert "created_at" in data

    def test_post_chat_persists_both_turns(self, client, auth_headers, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        run_id = db.insert_run(
            stryd_activity_id=8004,
            name="Chat Run 4",
            date="2026-04-04",
            fit_path="activities/chat4.fit",
            distance_m=8000,
            moving_time_s=2400,
        )

        with patch("runcoach.web.api.build_chat_context") as mock_ctx, \
             patch("runcoach.web.api._dispatch_llm") as mock_llm:
            mock_ctx.return_value = ("sys", "usr")
            mock_llm.return_value = {
                "commentary": "Great run!",
                "prompt_tokens": 100,
                "completion_tokens": 30,
            }
            client.post(
                f"/api/v1/runs/{run_id}/chat",
                json={"message": "Was it good?"},
                headers=auth_headers,
            )

        history = db.get_chat_history(run_id, user_id)
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["message"] == "Was it good?"
        assert history[1]["role"] == "assistant"
        assert history[1]["message"] == "Great run!"

    def test_post_chat_wrong_user_returns_404(self, client, app):
        from runcoach.auth import create_access_token, hash_password
        db = app.config["db"]

        other_user_id = db.create_user("other_user_chat", hash_password("pass"))
        other_token = create_access_token(other_user_id, app.config["SECRET_KEY"])
        other_headers = {"Authorization": f"Bearer {other_token}"}

        run_id = db.insert_run(
            stryd_activity_id=8005,
            name="Private Run",
            date="2026-04-05",
            fit_path="activities/private.fit",
            distance_m=8000,
            moving_time_s=2400,
        )

        resp = client.get(f"/api/v1/runs/{run_id}/chat", headers=other_headers)
        assert resp.status_code == 404

    def test_post_chat_empty_message_returns_400(self, client, auth_headers, app):
        db = app.config["db"]
        run_id = db.insert_run(
            stryd_activity_id=8006,
            name="Chat Run 6",
            date="2026-04-06",
            fit_path="activities/chat6.fit",
            distance_m=8000,
            moving_time_s=2400,
        )
        resp = client.post(
            f"/api/v1/runs/{run_id}/chat",
            json={"message": "  "},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_post_chat_llm_error_returns_502_nothing_persisted(self, client, auth_headers, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        run_id = db.insert_run(
            stryd_activity_id=8007,
            name="Chat Run 7",
            date="2026-04-07",
            fit_path="activities/chat7.fit",
            distance_m=8000,
            moving_time_s=2400,
        )

        with patch("runcoach.web.api.build_chat_context") as mock_ctx, \
             patch("runcoach.web.api._dispatch_llm") as mock_llm:
            mock_ctx.return_value = ("sys", "usr")
            mock_llm.side_effect = RuntimeError("LLM unavailable")
            resp = client.post(
                f"/api/v1/runs/{run_id}/chat",
                json={"message": "Test"},
                headers=auth_headers,
            )

        assert resp.status_code == 502
        assert db.get_chat_history(run_id, user_id) == []

    def test_post_chat_rate_limited_returns_429(self, client, app):
        # Use a second (non-default) user so _init_schema won't re-promote them
        db = app.config["db"]
        user_id = db.create_user("rl_user1", hash_password("pass"))
        token = create_access_token(user_id, app.config["SECRET_KEY"])
        headers = {"Authorization": f"Bearer {token}"}
        db.set_site_setting("llm_limiting_enabled", "1")
        db.set_site_setting("llm_daily_limit_default", "0")
        run_id = db.insert_run(
            stryd_activity_id=8020,
            name="API Rate Limit",
            date="2026-05-26",
            fit_path="activities/api_rl.fit",
            distance_m=5000,
            moving_time_s=1500,
            user_id=user_id,
        )
        resp = client.post(
            f"/api/v1/runs/{run_id}/chat",
            json={"message": "too many calls"},
            headers=headers,
        )
        assert resp.status_code == 429
        assert "Daily analysis limit reached" in resp.get_json()["error"]

    def test_post_chat_rate_limited_persists_user_message(self, client, app):
        # Use a second (non-default) user so _init_schema won't re-promote them
        db = app.config["db"]
        user_id = db.create_user("rl_user2", hash_password("pass"))
        token = create_access_token(user_id, app.config["SECRET_KEY"])
        headers = {"Authorization": f"Bearer {token}"}
        db.set_site_setting("llm_limiting_enabled", "1")
        db.set_site_setting("llm_daily_limit_default", "0")
        run_id = db.insert_run(
            stryd_activity_id=8021,
            name="API Persist",
            date="2026-05-26",
            fit_path="activities/api_persist.fit",
            distance_m=5000,
            moving_time_s=1500,
            user_id=user_id,
        )
        client.post(
            f"/api/v1/runs/{run_id}/chat",
            json={"message": "keep me"},
            headers=headers,
        )
        history = db.get_chat_history(run_id, user_id)
        assert len(history) == 1
        assert history[0]["status"] == "rate_limited"


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_dashboard_requires_auth(self, client):
        resp = client.get("/api/v1/dashboard")
        assert resp.status_code == 401

    def test_dashboard_returns_structure(self, client, auth_headers):
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

    def test_dashboard_next_workout_when_planned(self, client, auth_headers, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        # Insert a planned workout in the future
        from datetime import date, timedelta
        future_date = (date.today() + timedelta(days=1)).isoformat()
        db.upsert_planned_workout(
            date=future_date,
            title="Easy Recovery Run",
            description="45-60 min @ 220-240W",
            user_id=user_id,
        )

        resp = client.get("/api/v1/dashboard", headers=auth_headers)
        assert resp.status_code == 200
        nw = resp.get_json()["next_workout"]
        assert nw is not None
        assert nw["date"] == future_date
        assert nw["name"] == "Easy Recovery Run"
        assert "description" in nw

    def test_dashboard_next_workout_includes_new_fields(self, client, auth_headers, app):
        import json as json_mod
        from datetime import date, timedelta
        db = app.config["db"]
        user_id = db.get_default_user_id()
        future_date = (date.today() + timedelta(days=1)).isoformat()
        db.upsert_planned_workout(
            date=future_date,
            title="Interval Session",
            description="Hard effort",
            duration_s=2400.0,
            distance_m=6292.8,
            intensity_zones=json_mod.dumps([2340, 0, 0, 60, 0]),
            user_id=user_id,
        )
        resp = client.get("/api/v1/dashboard", headers=auth_headers)
        assert resp.status_code == 200
        nw = resp.get_json()["next_workout"]
        assert nw["id"] is not None
        assert nw["distance_m"] == pytest.approx(6292.8)
        assert nw["duration_s"] == pytest.approx(2400.0)
        assert nw["intensity_zones"] == [2340, 0, 0, 60, 0]

    def test_dashboard_next_workout_intensity_zones_null_when_unset(self, client, auth_headers, app):
        from datetime import date, timedelta
        db = app.config["db"]
        user_id = db.get_default_user_id()
        future_date = (date.today() + timedelta(days=2)).isoformat()
        db.upsert_planned_workout(
            date=future_date,
            title="Easy Run",
            description="Keep it easy",
            user_id=user_id,
        )
        resp = client.get("/api/v1/dashboard", headers=auth_headers)
        assert resp.status_code == 200
        nw = resp.get_json()["next_workout"]
        assert nw["intensity_zones"] is None
        assert nw["distance_m"] is None
        assert nw["duration_s"] is None

    def test_dashboard_next_workout_structure_parsed(self, client, auth_headers, app):
        import json as json_mod
        from datetime import date, timedelta
        db = app.config["db"]
        user_id = db.get_default_user_id()
        future_date = (date.today() + timedelta(days=3)).isoformat()
        raw_json = json_mod.dumps({
            "workout": {
                "blocks": [{
                    "repeat": 3,
                    "segments": [{
                        "intensity_class": "work",
                        "duration_time": {"hour": 0, "minute": 5, "second": 0},
                        "intensity_percent": {"value": 110, "min": 100, "max": 120},
                    }],
                }]
            }
        })
        db.upsert_planned_workout(
            date=future_date,
            title="Intervals",
            description="Hard",
            user_id=user_id,
            raw_json=raw_json,
        )
        resp = client.get("/api/v1/dashboard", headers=auth_headers)
        assert resp.status_code == 200
        nw = resp.get_json()["next_workout"]
        structure = nw["structure"]
        assert structure is not None
        assert len(structure) == 1
        block = structure[0]
        assert block["repeat"] == 3
        seg = block["segments"][0]
        assert seg["intensity_class"] == "work"
        assert seg["duration_s"] == 300
        assert seg["power_min_pct"] == 100
        assert seg["power_max_pct"] == 120

    def test_dashboard_next_workout_includes_stress(self, client, auth_headers, app):
        from datetime import date, timedelta
        db = app.config["db"]
        user_id = db.get_default_user_id()
        future_date = (date.today() + timedelta(days=1)).isoformat()
        db.upsert_planned_workout(
            date=future_date,
            title="Threshold Run",
            description="Hard effort",
            stress=62.5,
            user_id=user_id,
        )
        resp = client.get("/api/v1/dashboard", headers=auth_headers)
        assert resp.status_code == 200
        nw = resp.get_json()["next_workout"]
        assert nw["stress"] == pytest.approx(62.5)

    def test_dashboard_next_workout_stress_null_when_unset(self, client, auth_headers, app):
        from datetime import date, timedelta
        db = app.config["db"]
        user_id = db.get_default_user_id()
        future_date = (date.today() + timedelta(days=2)).isoformat()
        db.upsert_planned_workout(
            date=future_date,
            title="Easy Run",
            description="Recovery",
            user_id=user_id,
        )
        resp = client.get("/api/v1/dashboard", headers=auth_headers)
        assert resp.status_code == 200
        nw = resp.get_json()["next_workout"]
        assert nw["stress"] is None

    def test_dashboard_next_workout_skips_completed_date(self, client, auth_headers, app):
        from datetime import date, timedelta
        db = app.config["db"]
        user_id = db.get_default_user_id()
        today = date.today().isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        # Plan workouts for today AND tomorrow
        db.upsert_planned_workout(date=today, title="Today Run", description="easy", user_id=user_id)
        db.upsert_planned_workout(date=tomorrow, title="Tomorrow Run", description="hard", user_id=user_id)
        # Mark today as completed via any run (no Strava ID needed)
        db.insert_run(stryd_activity_id=None, name="Today Run", date=today, fit_path="", user_id=user_id)
        # Dashboard should skip today and return tomorrow
        resp = client.get("/api/v1/dashboard", headers=auth_headers)
        assert resp.status_code == 200
        nw = resp.get_json()["next_workout"]
        assert nw is not None
        assert nw["date"] == tomorrow
        assert nw["name"] == "Tomorrow Run"


class TestPlannedWorkouts:
    def test_requires_auth(self, client):
        resp = client.get("/api/v1/planned-workouts")
        assert resp.status_code == 401

    def test_returns_empty_list_when_none(self, client, auth_headers):
        resp = client.get("/api/v1/planned-workouts", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_returns_upcoming_workouts(self, client, auth_headers, app):
        from datetime import date, timedelta
        db = app.config["db"]
        user_id = db.get_default_user_id()
        future1 = (date.today() + timedelta(days=1)).isoformat()
        future2 = (date.today() + timedelta(days=3)).isoformat()
        db.upsert_planned_workout(
            date=future1, title="Easy Run", description="Recovery",
            distance_m=8000.0, duration_s=2700.0, stress=35.0, user_id=user_id,
        )
        db.upsert_planned_workout(
            date=future2, title="Intervals", description="Hard effort",
            stress=72.0, user_id=user_id,
        )
        resp = client.get("/api/v1/planned-workouts", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 2
        assert data[0]["date"] == future1
        assert data[0]["name"] == "Easy Run"
        assert data[0]["distance_m"] == pytest.approx(8000.0)
        assert data[0]["duration_s"] == pytest.approx(2700.0)
        assert data[0]["stress"] == pytest.approx(35.0)
        assert data[1]["name"] == "Intervals"

    def test_excludes_past_workouts(self, client, auth_headers, app):
        from datetime import date, timedelta
        db = app.config["db"]
        user_id = db.get_default_user_id()
        past = (date.today() - timedelta(days=1)).isoformat()
        future = (date.today() + timedelta(days=1)).isoformat()
        db.upsert_planned_workout(date=past, title="Past Run", description="", user_id=user_id)
        db.upsert_planned_workout(date=future, title="Future Run", description="", user_id=user_id)
        resp = client.get("/api/v1/planned-workouts", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        names = [w["name"] for w in data]
        assert "Past Run" not in names
        assert "Future Run" in names

    def test_hides_workout_when_run_exists_on_same_date(self, client, auth_headers, app):
        from datetime import date
        db = app.config["db"]
        user_id = db.get_default_user_id()
        today = date.today().isoformat()
        db.upsert_planned_workout(date=today, title="Today's Workout", description="", user_id=user_id)
        db.insert_run(stryd_activity_id=9999, name="Morning Run", date=today,
                      fit_path="activities/x.fit", user_id=user_id)
        resp = client.get("/api/v1/planned-workouts", headers=auth_headers)
        assert resp.status_code == 200
        names = [w["name"] for w in resp.get_json()]
        assert "Today's Workout" not in names

    def test_shows_workout_when_no_run_on_date(self, client, auth_headers, app):
        from datetime import date
        db = app.config["db"]
        user_id = db.get_default_user_id()
        today = date.today().isoformat()
        db.upsert_planned_workout(date=today, title="Today's Workout", description="", user_id=user_id)
        resp = client.get("/api/v1/planned-workouts", headers=auth_headers)
        assert resp.status_code == 200
        names = [w["name"] for w in resp.get_json()]
        assert "Today's Workout" in names


class TestBestRunTime:
    def test_requires_auth(self, client):
        r = client.get("/api/v1/best-run-time?lat=53.3&lng=-6.3")
        assert r.status_code == 401

    def test_missing_lat_returns_400(self, client, auth_headers):
        r = client.get("/api/v1/best-run-time?lng=-6.3", headers=auth_headers)
        assert r.status_code == 400

    def test_missing_lng_returns_400(self, client, auth_headers):
        r = client.get("/api/v1/best-run-time?lat=53.3", headers=auth_headers)
        assert r.status_code == 400

    def test_invalid_lat_returns_400(self, client, auth_headers):
        r = client.get("/api/v1/best-run-time?lat=999&lng=-6.3", headers=auth_headers)
        assert r.status_code == 400

    def test_returns_scored_forecast(self, client, auth_headers, mocker):
        fake_result = {
            "date": "2026-05-10",
            "hours": [{"hour": h, "score": 7, "temp_c": 12.0, "rain_pct": 5, "humidity_pct": 55, "wind_kmh": 10.0} for h in range(8)],
            "best_hour": 9,
            "best_score": 8,
            "day_label": "Best window: 9am · 8/10",
            "is_tomorrow": False,
        }
        mocker.patch("runcoach.web.api.fetch_forecast", return_value={})
        mocker.patch("runcoach.web.api.score_forecast", return_value=fake_result)

        r = client.get("/api/v1/best-run-time?lat=53.3&lng=-6.3", headers=auth_headers)
        assert r.status_code == 200
        data = r.get_json()
        assert data["best_score"] == 8
        assert len(data["hours"]) == 8
        assert data["is_tomorrow"] is False
        assert "day_label" in data

    def test_open_meteo_failure_returns_503(self, client, auth_headers, mocker):
        import requests as req_lib
        mocker.patch("runcoach.web.api.fetch_forecast", side_effect=req_lib.RequestException("timeout"))
        r = client.get("/api/v1/best-run-time?lat=53.3&lng=-6.3", headers=auth_headers)
        assert r.status_code == 503


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

    def test_cannot_delete_another_users_token(self, client, app):
        """User B must not be able to delete User A's device token."""
        db = app.config["db"]
        user_a_id = db.get_default_user_id()
        user_b_id = db.create_user("user_b", "hashed_pw")

        token_a = create_access_token(user_a_id, app.config["SECRET_KEY"])
        token_b = create_access_token(user_b_id, app.config["SECRET_KEY"])
        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # User A registers a device token
        client.post(
            "/api/v1/device-tokens",
            json={"token": "user-a-device-token", "platform": "android"},
            headers=headers_a,
        )

        # User B attempts to delete User A's token
        resp = client.delete(
            "/api/v1/device-tokens",
            json={"token": "user-a-device-token"},
            headers=headers_b,
        )
        assert resp.status_code == 200  # operation succeeds silently

        # User A's token must still be present
        tokens = db.get_device_tokens_for_user(user_a_id)
        assert any(t["token"] == "user-a-device-token" for t in tokens), \
            "User B was able to delete User A's device token — multi-user isolation broken"


class TestRouteSuggestion:
    def test_requires_auth(self, client):
        resp = client.post(
            "/api/v1/route-suggestion",
            json={"lat": 51.5, "lng": -0.1, "distance_m": 5000},
        )
        assert resp.status_code == 401

    def test_missing_ors_key_returns_503(self, client, auth_headers):
        resp = client.post(
            "/api/v1/route-suggestion",
            json={"lat": 51.5, "lng": -0.1, "distance_m": 5000},
            headers=auth_headers,
        )
        # Config has no ORS key in test fixture
        assert resp.status_code == 503

    def test_returns_routes_with_mocked_ors(self, client, auth_headers, app, monkeypatch):
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
        data = resp.get_json()
        assert "routes" in data
        assert len(data["routes"]) >= 1
        assert "coords" in data["routes"][0]
        assert "distance_m" in data["routes"][0]

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
        db.upsert_strava_routes(user_id, [{
            "strava_route_id": "999",
            "name": "My Strava Loop",
            "distance_m": 5100.0,
            "start_lat": 51.5001,
            "start_lng": -0.1001,
            "polyline": "encoded_placeholder",
        }])
        near_coords = [[51.5001, -0.1001], [51.5011, -0.1011]]
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
        strava_routes = [r for r in data["routes"] if r.get("source") == "strava"]
        assert len(strava_routes) == 1
        assert strava_routes[0]["name"] == "My Strava Loop"

    def test_includes_previously_run_routes(self, client, auth_headers, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
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

    def test_strava_routes_appear_before_ors(self, client, auth_headers, app):
        from runcoach.config import Config
        app.config["config"] = Config(
            openai_api_key="test-key",
            openai_model="gpt-4o",
            data_dir=app.config["config"].data_dir,
            timezone="Europe/London",
            secret_key="test-secret-key",
            ors_api_key="fake-ors-key",
        )
        db = app.config["db"]
        user_id = db.get_default_user_id()
        db.upsert_strava_routes(user_id, [{
            "strava_route_id": "888",
            "name": "My Loop",
            "distance_m": 5100.0,
            "start_lat": 51.5001,
            "start_lng": -0.1001,
            "polyline": "encoded_placeholder",
        }])
        near_coords = [[51.5001, -0.1001], [51.5011, -0.1011]]
        ors_response = {
            "features": [{
                "geometry": {"coordinates": [[-0.1, 51.5], [-0.11, 51.51]]},
                "properties": {"summary": {"distance": 5012}},
            }]
        }
        import unittest.mock as mock
        with mock.patch("runcoach.web.api.decode_polyline", return_value=near_coords), \
             mock.patch("runcoach.web.ors.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = ors_response
            resp = client.post(
                "/api/v1/route-suggestion",
                json={"lat": 51.5, "lng": -0.1, "distance_m": 5000},
                headers=auth_headers,
            )
        data = resp.get_json()
        assert resp.status_code == 200
        sources = [r["source"] for r in data["routes"]]
        assert sources[0] == "strava"
        assert sources[-1] == "ors"

    def test_include_ors_false_skips_ors_call(self, client, auth_headers, app):
        from runcoach.config import Config
        app.config["config"] = Config(
            openai_api_key="test-key",
            openai_model="gpt-4o",
            data_dir=app.config["config"].data_dir,
            timezone="Europe/London",
            secret_key="test-secret-key",
            ors_api_key="fake-ors-key",
        )
        db = app.config["db"]
        user_id = db.get_default_user_id()
        db.upsert_strava_routes(user_id, [{
            "strava_route_id": "777",
            "name": "Saved Route",
            "distance_m": 5050.0,
            "start_lat": 51.5001,
            "start_lng": -0.1001,
            "polyline": "encoded_placeholder",
        }])
        near_coords = [[51.5001, -0.1001], [51.5011, -0.1011]]
        import unittest.mock as mock
        with mock.patch("runcoach.web.api.decode_polyline", return_value=near_coords), \
             mock.patch("runcoach.web.ors.fetch_routes") as mock_fetch:
            resp = client.post(
                "/api/v1/route-suggestion",
                json={"lat": 51.5, "lng": -0.1, "distance_m": 5000, "include_ors": False},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        mock_fetch.assert_not_called()
        routes = resp.get_json()["routes"]
        assert all(r["source"] != "ors" for r in routes)

    def test_include_ors_false_returns_empty_routes_when_no_local_matches(self, client, auth_headers, app):
        from runcoach.config import Config
        import unittest.mock as mock

        app.config["config"] = Config(
            openai_api_key="test-key",
            openai_model="gpt-4o",
            data_dir=app.config["config"].data_dir,
            timezone="Europe/London",
            secret_key="test-secret-key",
            ors_api_key="fake-ors-key",
        )
        with mock.patch("runcoach.web.ors.fetch_routes") as mock_fetch:
            resp = client.post(
                "/api/v1/route-suggestion",
                json={"lat": 51.5, "lng": -0.1, "distance_m": 5000, "include_ors": False},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        assert resp.get_json() == {"routes": []}
        mock_fetch.assert_not_called()

    def test_strava_routes_include_strava_url(self, client, auth_headers, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        db.upsert_strava_routes(user_id, [{
            "strava_route_id": "555",
            "name": "Strava Loop",
            "distance_m": 5100.0,
            "start_lat": 51.5001,
            "start_lng": -0.1001,
            "polyline": "encoded_placeholder",
        }])
        near_coords = [[51.5001, -0.1001], [51.5011, -0.1011]]
        import unittest.mock as mock
        with mock.patch("runcoach.web.api.decode_polyline", return_value=near_coords), \
             mock.patch("runcoach.web.ors.fetch_routes", return_value=[]):
            resp = client.post(
                "/api/v1/route-suggestion",
                json={"lat": 51.5, "lng": -0.1, "distance_m": 5000},
                headers=auth_headers,
            )
        routes = resp.get_json()["routes"]
        strava = [r for r in routes if r.get("source") == "strava"]
        assert len(strava) == 1
        assert strava[0]["strava_url"] == "https://www.strava.com/routes/555"

    def test_previous_routes_with_strava_activity_id_include_url(self, client, auth_headers, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        with db._connect() as conn:
            conn.execute(
                """INSERT INTO runs (name, date, fit_path, stage, synced_at,
                   distance_m, strava_map_polyline, strava_activity_id, user_id)
                   VALUES ('Strava Run', '2026-04-01', 'r.fit', 'analyzed',
                   datetime('now'), 5050, 'poly_encoded', 12345678, ?)""",
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
        routes = resp.get_json()["routes"]
        prev = [r for r in routes if r.get("source") == "previous"]
        assert len(prev) == 1
        assert prev[0]["strava_url"] == "https://www.strava.com/activities/12345678"

    def test_previous_routes_without_strava_activity_id_have_null_url(self, client, auth_headers, app):
        db = app.config["db"]
        user_id = db.get_default_user_id()
        with db._connect() as conn:
            conn.execute(
                """INSERT INTO runs (name, date, fit_path, stage, synced_at,
                   distance_m, strava_map_polyline, user_id)
                   VALUES ('Manual Run', '2026-04-02', 'r.fit', 'analyzed',
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
        routes = resp.get_json()["routes"]
        prev = [r for r in routes if r.get("source") == "previous"]
        assert len(prev) == 1
        assert prev[0]["strava_url"] is None


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

        with patch("runcoach.analyzer.analyze_and_write") as mock_analyze, \
             patch("runcoach.notifications.send_analysis_notification") as mock_notify:
            mock_analyze.return_value = {
                "commentary": "Well done!",
                "prompt_tokens": 50,
                "completion_tokens": 25,
            }
            client.post(f"/api/v1/runs/{run_id}/analyze", headers=auth_headers)
            time.sleep(0.2)  # let background thread finish

        mock_notify.assert_called_once_with(run_id, "Test Run", user_id, ANY, ANY)

    def test_analyze_rate_limited_returns_429(self, client, app):
        # Use a non-default user so _init_schema won't re-promote them to admin
        db = app.config["db"]
        user_id = db.create_user("rl_analyze_user", hash_password("pass"))
        token = create_access_token(user_id, app.config["SECRET_KEY"])
        headers = {"Authorization": f"Bearer {token}"}
        db.set_site_setting("llm_limiting_enabled", "1")
        db.set_site_setting("llm_daily_limit_default", "0")
        run_id = db.insert_run(
            stryd_activity_id=9010,
            name="API Analyze Limit",
            date="2026-05-26",
            fit_path="activities/api_al.fit",
            distance_m=5000,
            moving_time_s=1500,
            user_id=user_id,
        )
        db.update_parsed(run_id, None, 200.0, 145, "API Analyze Limit")
        resp = client.post(f"/api/v1/runs/{run_id}/analyze", headers=headers)
        assert resp.status_code == 429
        assert "Daily analysis limit reached" in resp.get_json()["error"]


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
            # no strava_client_id
        )
        user_id = db.get_default_user_id()

        count = sync_strava_routes(db, user_id, cfg_no_strava)
        assert count == 0
