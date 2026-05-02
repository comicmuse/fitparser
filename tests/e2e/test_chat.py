"""Playwright E2E tests for the coach chat feature."""
from __future__ import annotations

import pytest

from tests.e2e.conftest import SAMPLE_YAML_REL

pytestmark = pytest.mark.e2e


@pytest.fixture
def analyzed_run_id(flask_server, e2e_data_dir):
    """Insert a fresh analyzed run for chat tests (function-scoped for isolation)."""
    from runcoach.db import RunCoachDB

    db = RunCoachDB(e2e_data_dir / "runcoach.db")
    run_id = db.insert_manual_run(
        "Chat E2E Test Run", "2026-02-10",
        "activities/2026/02/chat_e2e/chat_e2e.fit", 9000, 2700,
    )
    db.update_parsed(run_id, SAMPLE_YAML_REL, 185.0, 148, "Chat E2E Test Run")
    db.update_analyzed(
        run_id=run_id,
        md_path="activities/2026/02/chat_e2e/chat_e2e.md",
        commentary=(
            "Great effort today! Power was consistent throughout the warmup. "
            "Heart rate stayed in Z2 — ideal for aerobic development."
        ),
        model_used="llama3.2",
        prompt_tokens=120,
        completion_tokens=55,
    )
    return run_id


@pytest.fixture
def parsed_only_run_id(flask_server, e2e_data_dir):
    """Insert a parsed-only run (no commentary) for testing chat panel absence."""
    from runcoach.db import RunCoachDB

    db = RunCoachDB(e2e_data_dir / "runcoach.db")
    run_id = db.insert_manual_run(
        "Parsed Only E2E Run", "2026-02-11",
        "activities/2026/02/parsed_only_e2e/parsed_only_e2e.fit", 5000, 1800,
    )
    db.update_parsed(run_id, SAMPLE_YAML_REL, 170.0, 140, "Parsed Only E2E Run")
    return run_id


def test_chat_panel_visible_on_analyzed_run(logged_in_page, server_url, analyzed_run_id):
    """The chat panel appears on an analyzed run page."""
    page = logged_in_page
    page.goto(f"{server_url}/run/{analyzed_run_id}")
    assert page.locator("#chat-panel").is_visible()
    assert page.locator("#chat-input").is_visible()
    assert page.locator("#chat-submit").is_visible()


def test_send_message_shows_response(logged_in_page, server_url, analyzed_run_id):
    """Submitting a question appends a coach response to the chat history."""
    page = logged_in_page
    page.goto(f"{server_url}/run/{analyzed_run_id}")
    page.locator("#chat-input").fill("What was my average heart rate?")
    page.locator("#chat-submit").click()
    page.wait_for_selector(".chat-message--assistant", timeout=30_000)

    assistant_messages = page.locator(".chat-message--assistant").all()
    assert len(assistant_messages) >= 1
    assert len(assistant_messages[-1].text_content().strip()) > 10


def test_chat_history_persists_after_reload(logged_in_page, server_url, analyzed_run_id):
    """After a chat turn, reloading the page still shows the conversation."""
    page = logged_in_page
    page.goto(f"{server_url}/run/{analyzed_run_id}")
    page.locator("#chat-input").fill("How did my power look in the warmup?")
    page.locator("#chat-submit").click()
    page.wait_for_selector(".chat-message--assistant", timeout=30_000)

    page.reload()
    page.wait_for_load_state("networkidle")

    assert page.locator(".chat-message--user").count() >= 1
    assert page.locator(".chat-message--assistant").count() >= 1


def test_chat_panel_not_shown_for_unanalyzed_run(
    logged_in_page, server_url, parsed_only_run_id
):
    """The chat panel is absent on a run that has not been analyzed yet."""
    page = logged_in_page
    page.goto(f"{server_url}/run/{parsed_only_run_id}")
    assert not page.locator("#chat-panel").is_visible()
