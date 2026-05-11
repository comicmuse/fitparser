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
    page.wait_for_load_state("networkidle")
    page.locator("#hamburger-btn").click()
    page.wait_for_timeout(300)
    page.locator("#menu-upload-btn").click()
    page.wait_for_timeout(200)
    upload_div = page.locator("#upload-form")
    assert upload_div.is_visible()


def test_recent_runs_table_has_rows(logged_in_page, seeded_run_id):
    """At least one row appears in the recent runs table (seeded run or newer)."""
    page = logged_in_page
    # The table shows up to 5 most recent runs; just verify the table has content
    assert page.locator("table tbody tr").count() >= 1


def test_training_summary_card_present(logged_in_page, seeded_run_id):
    """Training summary card renders when at least one run exists."""
    page = logged_in_page
    page.reload()
    assert page.locator(".summary-grid").count() >= 1


def test_training_summary_grid_has_three_columns(logged_in_page, seeded_run_id):
    """Summary grid shows exactly 3 columns (1W, 4W avg, 16W avg)."""
    page = logged_in_page
    page.reload()
    assert page.locator(".summary-col").count() == 3


def test_training_summary_column_labels(logged_in_page, seeded_run_id):
    """Summary columns are labelled for each time window."""
    page = logged_in_page
    page.reload()
    labels = [el.inner_text() for el in page.locator(".summary-col-label").all()]
    label_text = " ".join(labels).lower()
    assert "week" in label_text


def test_rsb_chart_canvas_present(logged_in_page, seeded_run_id):
    """RSB history chart canvas is present in the DOM."""
    page = logged_in_page
    page.reload()
    assert page.locator("canvas#rsbHistoryChart").count() == 1


import json as _json


class TestBestRunTimeCard:
    def test_card_appears_when_geolocation_granted(self, browser, server_url):
        """Bar chart card should render when geolocation is available and API succeeds."""
        context = browser.new_context(
            geolocation={"latitude": 53.3498, "longitude": -6.2603},
            permissions=["geolocation"],
        )
        page = context.new_page()

        # Intercept the API call so the test doesn't hit Open-Meteo
        fake_payload = _json.dumps({
            "date": "2026-05-10",
            "hours": [
                {"hour": h, "score": 7 if h == 9 else 5,
                 "temp_c": 12.0, "rain_pct": 5, "humidity_pct": 55, "wind_kmh": 10.0}
                for h in range(24)
            ],
            "best_hour": 9,
            "best_score": 7,
            "day_label": "Best window: 9am · 7/10",
        })
        page.route("**/api/best-run-time**", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=fake_payload,
        ))

        # Log in
        page.goto(f"{server_url}/login")
        page.fill("input[name='username']", "athlete")
        from tests.e2e.conftest import E2E_PASSWORD
        page.fill("input[name='password']", E2E_PASSWORD)
        page.click("button[type='submit']")
        page.wait_for_url(f"{server_url}/")

        card = page.locator("#brt-card")
        card.wait_for(state="visible", timeout=5000)
        assert "Best window" in page.locator("#brt-label").text_content()
        context.close()
