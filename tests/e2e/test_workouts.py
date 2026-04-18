"""E2E tests: workouts page (list view, pagination)."""
import pytest

from runcoach.db import RunCoachDB
from tests.e2e.conftest import SAMPLE_FIT_REL, SAMPLE_YAML_REL

pytestmark = pytest.mark.e2e


def test_workouts_page_loads(logged_in_page, server_url):
    page = logged_in_page
    page.goto(f"{server_url}/workouts")
    assert page.locator("h2", has_text="Upcoming Planned Workouts").is_visible()
    assert page.locator("h2", has_text="Activity Log").is_visible()


def test_workouts_shows_seeded_run(logged_in_page, server_url, seeded_run_id):
    page = logged_in_page
    page.goto(f"{server_url}/workouts")
    assert "Day 25" in page.content()


def test_workouts_shows_run_count(logged_in_page, server_url, seeded_run_id):
    page = logged_in_page
    page.goto(f"{server_url}/workouts")
    # "N runs total" label is always present
    assert "runs total" in page.content()


def test_pagination_links_appear_with_many_runs(logged_in_page, server_url, e2e_data_dir):
    """Insert >10 runs so the activity log pagination appears."""
    db = RunCoachDB(e2e_data_dir / "runcoach.db")
    inserted = []
    for i in range(12):
        run_id = db.insert_manual_run(
            f"Pagination Run {i}",
            f"2025-{(i % 12) + 1:02d}-15",
            f"activities/2025/{(i % 12) + 1:02d}/15/run_{i}.fit",
            5000,
            1800,
        )
        inserted.append(run_id)

    page = logged_in_page
    page.goto(f"{server_url}/workouts")
    # pagination div should be present with a page 2 link
    assert page.locator(".pagination").count() >= 1
    assert "2" in page.locator(".pagination").first.inner_text()


def test_pagination_next_page_navigates(logged_in_page, server_url):
    page = logged_in_page
    page.goto(f"{server_url}/workouts")
    pagination = page.locator(".pagination").first
    if pagination.count() == 0:
        pytest.skip("Not enough runs for pagination")

    # Click the page-2 link
    page.locator(".pagination a", has_text="2").first.click()
    page.wait_for_load_state("networkidle")
    assert "runs_page=2" in page.url or "page=2" in page.url or page.url != f"{server_url}/workouts"


def test_empty_planned_workouts_graceful(logged_in_page, server_url):
    page = logged_in_page
    page.goto(f"{server_url}/workouts")
    content = page.content()
    # Either shows "0 upcoming sessions" or "No upcoming workouts."
    assert "upcoming" in content.lower()
