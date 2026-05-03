"""Tests for runcoach.web.api — JWT-authenticated REST endpoints."""

from __future__ import annotations

import pytest
from unittest.mock import patch

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
