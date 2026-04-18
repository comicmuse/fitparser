"""E2E tests: dashboard (index) page."""
import pytest

pytestmark = pytest.mark.e2e


def test_dashboard_loads(logged_in_page, server_url):
    page = logged_in_page
    assert "RunCoach" in page.content()
    assert page.url == f"{server_url}/"


def test_stats_bar_shows_run_count(logged_in_page, seeded_run_id):
    page = logged_in_page
    nums = page.locator(".hero-stat-num").all()
    assert len(nums) >= 1
    # Total runs should be at least 1 (the seeded run)
    total = int(nums[0].inner_text())
    assert total >= 1


def test_calendar_renders_three_weeks(logged_in_page):
    page = logged_in_page
    # Each day cell has a .cal-weekday span
    day_cells = page.locator(".cal-weekday").count()
    assert day_cells == 21  # 3 weeks × 7 days


def test_upload_form_hidden_by_default(logged_in_page):
    page = logged_in_page
    upload_div = page.locator("#upload-form")
    assert upload_div.count() == 1
    assert not upload_div.is_visible()


def test_upload_form_revealed_by_button(logged_in_page):
    page = logged_in_page
    page.locator("button", has_text="Upload").first.click()
    upload_div = page.locator("#upload-form")
    assert upload_div.is_visible()


def test_recent_runs_table_has_rows(logged_in_page, seeded_run_id):
    """At least one row appears in the recent runs table (seeded run or newer)."""
    page = logged_in_page
    # The table shows up to 5 most recent runs; just verify the table has content
    assert page.locator("table tbody tr").count() >= 1
