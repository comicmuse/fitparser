"""Shared fixtures for RunCoach Playwright E2E tests."""
from __future__ import annotations

import os
import shutil
import socket
import threading
import time
from pathlib import Path

import pytest

from tests.e2e.mock_ollama import start_mock_ollama_server

SAMPLE_DIR = Path(__file__).resolve().parents[1] / "fixtures"
SAMPLE_FIT_NAME = "20260129_day_25_-_testing.fit"
SAMPLE_YAML_NAME = "20260129_day_25_-_testing.yaml"

E2E_PASSWORD = "testpassword123"

# Relative paths as stored in the DB (relative to data_dir)
_ACT_REL = "activities/2026/01/20260129_day_25_-_testing"
SAMPLE_FIT_REL = f"{_ACT_REL}/{SAMPLE_FIT_NAME}"
SAMPLE_YAML_REL = f"{_ACT_REL}/{SAMPLE_YAML_NAME}"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def mock_ollama():
    """
    Provide an Ollama base URL for E2E tests.

    If OLLAMA_BASE_URL is set in the environment, the real local Ollama is used
    (no mock server started). This lets developers run E2E tests against a real
    model locally. Set E2E_OLLAMA_MODEL to choose a fast model (default: llama3.2).

    In CI (OLLAMA_BASE_URL unset), a lightweight mock HTTP server is started that
    returns a fixed response without any GPU/network dependency.
    """
    real_url = os.environ.get("OLLAMA_BASE_URL", "").strip()
    if real_url:
        yield real_url
        return

    server, base_url = start_mock_ollama_server()
    yield base_url
    server.shutdown()


@pytest.fixture(scope="session")
def e2e_ollama_model() -> str:
    """Model name to use when the real Ollama server is active."""
    return os.environ.get("E2E_OLLAMA_MODEL", os.environ.get("OLLAMA_MODEL", "llama3.2"))


@pytest.fixture(scope="session")
def e2e_data_dir(tmp_path_factory):
    """Session-scoped temp data dir with sample FIT/YAML copied in."""
    data_dir = tmp_path_factory.mktemp("e2e_data")
    dest = data_dir / _ACT_REL
    dest.mkdir(parents=True)
    shutil.copy(SAMPLE_DIR / SAMPLE_FIT_NAME, dest / SAMPLE_FIT_NAME)
    shutil.copy(SAMPLE_DIR / SAMPLE_YAML_NAME, dest / SAMPLE_YAML_NAME)
    return data_dir


@pytest.fixture(scope="session")
def flask_server(e2e_data_dir, mock_ollama, e2e_ollama_model):
    """Start a live Flask server in a daemon thread. Yields base URL."""
    from runcoach.config import Config
    from runcoach.web import create_app

    port = _free_port()

    # RUNCOACH_PASSWORD is read during create_app → _ensure_default_user
    os.environ["RUNCOACH_PASSWORD"] = E2E_PASSWORD

    config = Config(
        ollama_base_url=mock_ollama,
        ollama_model=e2e_ollama_model,
        data_dir=e2e_data_dir,
        timezone="Europe/London",
        secret_key="e2e-test-secret-key",
        sync_interval_hours=0,
        llm_auto_analyse=False,
    )
    app = create_app(config)
    app.config["WTF_CSRF_ENABLED"] = False

    def _run():
        app.run(host="127.0.0.1", port=port, threaded=True, use_reloader=False)

    threading.Thread(target=_run, daemon=True).start()
    base_url = f"http://127.0.0.1:{port}"

    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.2)

    yield base_url


@pytest.fixture(scope="session")
def seeded_run_id(flask_server, e2e_data_dir):
    """Insert a pre-parsed run (pointing at real YAML) once for the session."""
    from runcoach.db import RunCoachDB

    db = RunCoachDB(e2e_data_dir / "runcoach.db")
    existing = db.get_run_by_fit_path(SAMPLE_FIT_REL)
    if existing:
        return existing["id"]
    run_id = db.insert_manual_run(
        "Day 25 - Testing", "2026-01-29", SAMPLE_FIT_REL, 7070, 2700
    )
    db.update_parsed(run_id, SAMPLE_YAML_REL, 176.0, 145, "Day 25 - Testing")
    return run_id


@pytest.fixture
def server_url(flask_server):
    return flask_server


E2E_USERNAME = "athlete"
REGULAR_USERNAME = "e2e_regular"
REGULAR_PASSWORD = "regularpass123"


@pytest.fixture
def logged_in_page(page, flask_server):
    """Return a Playwright page already logged in as the admin user."""
    page.goto(f"{flask_server}/login")
    page.fill("input[name='username']", E2E_USERNAME)
    page.fill("input[name='password']", E2E_PASSWORD)
    page.click("button[type='submit']")
    page.wait_for_url(f"{flask_server}/")
    return page


@pytest.fixture(scope="session")
def regular_user(flask_server, e2e_data_dir):
    """Create a non-admin user once for the session."""
    from runcoach.auth import hash_password
    from runcoach.db import RunCoachDB

    db = RunCoachDB(e2e_data_dir / "runcoach.db")
    if not db.get_user_by_username(REGULAR_USERNAME):
        db.create_user(REGULAR_USERNAME, hash_password(REGULAR_PASSWORD))
    return {"username": REGULAR_USERNAME, "password": REGULAR_PASSWORD}


@pytest.fixture
def regular_user_page(page, flask_server, regular_user):
    """Return a Playwright page logged in as the non-admin regular user."""
    page.goto(f"{flask_server}/login")
    page.fill("input[name='username']", regular_user["username"])
    page.fill("input[name='password']", regular_user["password"])
    page.click("button[type='submit']")
    page.wait_for_url(f"{flask_server}/")
    return page


@pytest.fixture
def deactivation_victim(flask_server, e2e_data_dir):
    """Create (or reset) a user to be used in deactivation/reactivation tests."""
    from runcoach.auth import hash_password
    from runcoach.db import RunCoachDB

    db = RunCoachDB(e2e_data_dir / "runcoach.db")
    username = "e2e_victim_deactivate"
    password = "victimpass123"
    existing = db.get_user_by_username(username)
    if not existing:
        db.create_user(username, hash_password(password))
    else:
        db.set_user_active(existing["id"], True)
    return {"username": username, "password": password}


@pytest.fixture
def deletion_victim(flask_server, e2e_data_dir):
    """Create a fresh user to be deleted in deletion tests."""
    from runcoach.auth import hash_password
    from runcoach.db import RunCoachDB

    db = RunCoachDB(e2e_data_dir / "runcoach.db")
    username = "e2e_victim_delete"
    password = "deletepass123"
    existing = db.get_user_by_username(username)
    if existing:
        db.delete_user(existing["id"])
    db.create_user(username, hash_password(password))
    return {"username": username, "password": password}
