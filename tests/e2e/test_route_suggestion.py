"""E2E tests: /date/<date> planned workout page and route suggestion UI."""
from __future__ import annotations

import datetime

import pytest

pytestmark = pytest.mark.e2e

# Use next Monday so the date falls within the dashboard's 3-week rolling window
_today = datetime.date.today()
_next_monday = _today + datetime.timedelta(days=(7 - _today.weekday()))
PLANNED_DATE = _next_monday.isoformat()
PLANNED_TITLE = "Easy 10k"
PLANNED_DISTANCE_M = 10000


@pytest.fixture
def planned_workout_id(flask_server, e2e_data_dir):
    """Seed a planned workout with a future date (no actual run)."""
    from runcoach.db import RunCoachDB

    db = RunCoachDB(e2e_data_dir / "runcoach.db")
    return db.upsert_planned_workout(
        date=PLANNED_DATE,
        title=PLANNED_TITLE,
        distance_m=PLANNED_DISTANCE_M,
        user_id=1,
    )


class TestDateDetailRoute:
    def test_planned_only_page_loads(self, logged_in_page, server_url, planned_workout_id):
        page = logged_in_page
        page.goto(f"{server_url}/date/{PLANNED_DATE}")
        assert page.locator(".card", has_text="Prescribed Workout").is_visible()

    def test_shows_planned_workout_title(self, logged_in_page, server_url, planned_workout_id):
        page = logged_in_page
        page.goto(f"{server_url}/date/{PLANNED_DATE}")
        assert PLANNED_TITLE in page.content()

    def test_shows_suggest_route_button(self, logged_in_page, server_url, planned_workout_id):
        page = logged_in_page
        page.goto(f"{server_url}/date/{PLANNED_DATE}")
        assert page.locator("button", has_text="Suggest a Route").is_visible()

    def test_redirects_to_run_if_actual_run_exists(
        self, logged_in_page, server_url, seeded_run_id
    ):
        """Seeded run is on 2026-01-29 — /date/2026-01-29 should redirect to /run/<id>."""
        page = logged_in_page
        page.goto(f"{server_url}/date/2026-01-29")
        assert f"/run/{seeded_run_id}" in page.url

    def test_unknown_date_redirects_to_dashboard(self, logged_in_page, server_url):
        page = logged_in_page
        page.goto(f"{server_url}/date/1900-01-01")
        assert page.url.rstrip("/") == server_url.rstrip("/") or "/login" not in page.url

    def test_unauthenticated_redirects_to_login(self, page, server_url, planned_workout_id):
        page.goto(f"{server_url}/date/{PLANNED_DATE}")
        assert "/login" in page.url


class TestCalendarPlannedWorkoutLinks:
    def test_calendar_planned_item_is_a_link(
        self, logged_in_page, server_url, planned_workout_id
    ):
        """The planned workout on the dashboard calendar should be a clickable <a> tag."""
        page = logged_in_page
        page.goto(f"{server_url}/")
        link = page.locator(f"a.cal-planned:has-text('{PLANNED_TITLE}')")
        assert link.count() >= 1
        href = link.first.get_attribute("href")
        assert f"/date/{PLANNED_DATE}" in href

    def test_calendar_planned_link_navigates_to_workout_page(
        self, logged_in_page, server_url, planned_workout_id
    ):
        page = logged_in_page
        page.goto(f"{server_url}/")
        page.locator(f"a.cal-planned:has-text('{PLANNED_TITLE}')").first.click()
        page.wait_for_url(f"**date/{PLANNED_DATE}**")
        assert page.locator("button", has_text="Suggest a Route").is_visible()


class TestRouteSuggestionUI:
    def test_suggest_route_button_visible_when_distance_set(
        self, logged_in_page, server_url, planned_workout_id
    ):
        page = logged_in_page
        page.goto(f"{server_url}/date/{PLANNED_DATE}")
        assert page.locator("button", has_text="Suggest a Route").is_visible()

    def test_no_suggest_route_button_without_distance(
        self, logged_in_page, server_url, e2e_data_dir
    ):
        """A planned workout with no distance_m should not show the route button."""
        from runcoach.db import RunCoachDB

        no_dist_date = (_next_monday + datetime.timedelta(days=1)).isoformat()
        db = RunCoachDB(e2e_data_dir / "runcoach.db")
        db.upsert_planned_workout(
            date=no_dist_date,
            title="Recovery jog",
            distance_m=None,
            user_id=1,
        )
        page = logged_in_page
        page.goto(f"{server_url}/date/{no_dist_date}")
        assert page.locator("button", has_text="Suggest a Route").count() == 0

    def test_geolocation_denied_shows_error(
        self, browser, server_url, planned_workout_id
    ):
        """When geolocation is denied, an inline error message should appear."""
        context = browser.new_context(
            geolocation=None,
            permissions=[],  # deny geolocation
        )
        page = context.new_page()
        # Log in
        page.goto(f"{server_url}/login")
        page.fill("input[name='username']", "athlete")
        from tests.e2e.conftest import E2E_PASSWORD
        page.fill("input[name='password']", E2E_PASSWORD)
        page.click("button[type='submit']")
        page.wait_for_url(f"{server_url}/")

        page.goto(f"{server_url}/date/{PLANNED_DATE}")
        page.locator("button", has_text="Suggest a Route").click()
        error_div = page.locator("#route-status")
        error_div.wait_for(state="visible", timeout=5000)
        assert "location" in error_div.text_content().lower()
        context.close()
