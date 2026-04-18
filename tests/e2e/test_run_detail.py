"""E2E tests: run detail page."""
import pytest

from tests.e2e.conftest import SAMPLE_YAML_REL

pytestmark = pytest.mark.e2e


def test_run_detail_loads(logged_in_page, server_url, seeded_run_id):
    page = logged_in_page
    page.goto(f"{server_url}/run/{seeded_run_id}")
    assert "Day 25" in page.content()


def test_shows_distance_metric(logged_in_page, server_url, seeded_run_id):
    page = logged_in_page
    page.goto(f"{server_url}/run/{seeded_run_id}")
    # Distance was seeded as 7070 m → 7.07 km
    assert "7.07" in page.content()


def test_shows_avg_hr(logged_in_page, server_url, seeded_run_id):
    page = logged_in_page
    page.goto(f"{server_url}/run/{seeded_run_id}")
    assert "145" in page.content()


def test_shows_workout_structure_card(logged_in_page, server_url, seeded_run_id):
    page = logged_in_page
    page.goto(f"{server_url}/run/{seeded_run_id}")
    assert page.locator("h2", has_text="Workout Structure").is_visible()


def test_shows_block_cards(logged_in_page, server_url, seeded_run_id):
    page = logged_in_page
    page.goto(f"{server_url}/run/{seeded_run_id}")
    assert page.locator(".block-card").count() >= 1


def test_shows_analyze_button_for_parsed_run(logged_in_page, server_url, seeded_run_id):
    page = logged_in_page
    page.goto(f"{server_url}/run/{seeded_run_id}")
    # Run is in 'parsed' stage — Analyze Now button should be present
    assert page.locator("button", has_text="Analyze Now").is_visible()


def test_shows_commentary_for_analyzed_run(logged_in_page, server_url, seeded_run_id, e2e_data_dir):
    """Pre-seed commentary, verify it renders on the page."""
    from runcoach.db import RunCoachDB

    db = RunCoachDB(e2e_data_dir / "runcoach.db")
    md_path = str(e2e_data_dir / "activities/2026/01/20260129_day_25_-_testing/20260129_day_25_-_testing.md")
    # Write a stub markdown file
    with open(md_path, "w") as f:
        f.write("# Pre-seeded Commentary\n\nExcellent baseline run.\n")
    db.update_analyzed(
        run_id=seeded_run_id,
        md_path=md_path,
        commentary="# Pre-seeded Commentary\n\nExcellent baseline run.\n",
        model_used="llama3.2",
        prompt_tokens=100,
        completion_tokens=20,
    )

    page = logged_in_page
    page.goto(f"{server_url}/run/{seeded_run_id}")
    assert page.locator(".commentary").is_visible()
    assert "Excellent baseline run" in page.text_content(".commentary")
    # Re-analyze button should now be visible too
    assert page.locator("button", has_text="Re-analyze").is_visible()
