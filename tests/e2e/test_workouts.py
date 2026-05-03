"""E2E tests: All Activities page (year/month nav, run cards)."""
import pytest

from runcoach.db import RunCoachDB

pytestmark = pytest.mark.e2e


def test_workouts_page_loads(logged_in_page, server_url):
    page = logged_in_page
    page.goto(f"{server_url}/workouts")
    assert page.locator("h2", has_text="All Activities").is_visible()


def test_workouts_shows_seeded_run(logged_in_page, server_url, seeded_run_id):
    page = logged_in_page
    page.goto(f"{server_url}/workouts")
    # The seeded run name contains "Day 25" — navigate to its month if needed
    assert "Day 25" in page.content()


def test_workouts_no_planned_workouts_sections(logged_in_page, server_url):
    page = logged_in_page
    page.goto(f"{server_url}/workouts")
    content = page.content()
    assert "Upcoming Planned Workouts" not in content
    assert "Activity Log" not in content


def test_workouts_year_pills_present_with_runs(logged_in_page, server_url, seeded_run_id):
    """Year pills appear when there are runs."""
    page = logged_in_page
    page.goto(f"{server_url}/workouts")
    content = page.content()
    # At least one year should appear as a pill (seeded run has a date)
    import re
    assert re.search(r"20\d\d", content), "Expected a year pill in the page"


def test_workouts_month_navigation(logged_in_page, server_url, e2e_data_dir):
    """Insert runs in two months and verify month pills appear."""
    db = RunCoachDB(e2e_data_dir / "runcoach.db")
    db.insert_manual_run("Jan Run", "2025-01-15", "activities/jan.fit", 5000, 1800)
    db.insert_manual_run("Mar Run", "2025-03-10", "activities/mar.fit", 8000, 2700)

    page = logged_in_page
    page.goto(f"{server_url}/workouts?year=2025&month=1")
    assert "Jan Run" in page.content()
    assert "Mar Run" not in page.content()

    page.goto(f"{server_url}/workouts?year=2025&month=3")
    assert "Mar Run" in page.content()
    assert "Jan Run" not in page.content()
